#!/bin/bash

# Log file
LOG_FILE="/root/server_setup.log"
exec > >(tee -a $LOG_FILE) 2>&1

export DEBIAN_FRONTEND=noninteractive
export CF_ENFORCE="${CF_ENFORCE:-0}"
set -o pipefail

wait_for_oracle_ready() {
    echo "Waiting for Oracle XE to become ready..."
    local attempts=0
    local max_attempts=90
    while [ $attempts -lt $max_attempts ]; do
        if docker logs oracle-db 2>&1 | grep -q "DATABASE IS READY TO USE"; then
            echo "Oracle XE is ready."
            return 0
        fi
        attempts=$((attempts+1))
        sleep 10
    done
    echo "Oracle XE did not become ready in time." >&2
    return 1
}

# --- SECURITY HARDENING (CLOAKING & FIREWALL) ---
setup_security_shield() {
    echo "Engaging Security Shield (IP Masking & Firewall)..."
    
    # Install Firewall & Fail2Ban
    apt-get install -y ufw fail2ban

    # 1. Setup Fail2Ban to block brute-force attacks
    cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
    systemctl enable fail2ban
    systemctl start fail2ban

    # 2. Configure UFW (Firewall)
    ufw default deny incoming
    ufw default allow outgoing
    
    # Allow SSH (Important: Don't lock ourselves out!)
    ufw allow ssh

    # 3. Web Access Policy
    if [ "$CF_ENFORCE" = "1" ]; then
        # IP CLOAKING: Only allow Cloudflare IPs to access Web Ports (80, 443)
        # This prevents direct IP access/attacks, hiding the real server behind Cloudflare
        echo "Downloading Cloudflare IP ranges for Cloaking..."

        # IPv4
        for ip in $(curl -s https://www.cloudflare.com/ips-v4); do
            ufw allow from $ip to any port 80
            ufw allow from $ip to any port 443
        done

        # IPv6
        for ip in $(curl -s https://www.cloudflare.com/ips-v6); do
            ufw allow from $ip to any port 80
            ufw allow from $ip to any port 443
        done

        echo "y" | ufw enable
        echo "Security Shield ENGAGED. Direct IP access is now BLOCKED (Cloudflare-only)."
    else
        # Temporary open access for direct testing until Cloudflare DNS is configured
        ufw allow 80/tcp
        ufw allow 443/tcp
        echo "y" | ufw enable
        echo "Cloudflare cloaking DISABLED temporarily. Direct access to 80/443 is allowed."
    fi
}

# Run Security Setup
setup_security_shield

echo "==============================================================="

# Configuration
DB_PASSWORD="Sovereign_Db_Pass_$(date +%s)"
ORDS_PASSWORD="Sovereign_Ords_Pass_$(date +%s)"
APEX_VERSION="latest" # Downloads latest

# 1. System Update
echo "[1/8] Updating System..."
apt-get update -y && apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg lsb-release ufw fail2ban nano unzip openjdk-17-jdk wget
apt-get install -y python3 python3-pip
pip3 install --no-cache-dir flask requests gTTS google-cloud-texttospeech

# 2. Firewall
echo "[2/8] Configuring Firewall..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8080/tcp
ufw --force enable

# 3. Docker Installation
echo "[3/8] Installing Docker..."
if ! command -v docker &> /dev/null; then
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

# 4. Oracle Database (Docker)
echo "[4/8] Deploying Oracle Database 21c XE..."
docker stop oracle-db || true
docker rm oracle-db || true
mkdir -p /opt/oracle/oradata
chown -R 54321:54321 /opt/oracle/oradata

docker run -d \
  --name oracle-db \
  -p 1521:1521 \
  -e ORACLE_PASSWORD=$DB_PASSWORD \
  -v /opt/oracle/oradata:/opt/oracle/oradata \
  --restart unless-stopped \
  gvenzl/oracle-xe:21-slim

wait_for_oracle_ready || {
  echo "Database not ready, retrying short wait..."
  sleep 60
}

# 5. Download & Install APEX
echo "[5/8] Downloading & Installing APEX (This takes time)..."
mkdir -p /opt/software
cd /opt/software
if [ ! -f "apex-latest.zip" ]; then
    echo "Downloading APEX..."
    wget https://download.oracle.com/otn_software/apex/apex-latest.zip
fi
unzip -q -o apex-latest.zip
cd apex

# Copy APEX files to container
docker cp . oracle-db:/opt/oracle/apex

# Run APEX Installation inside Container
echo "Running APEX Installation SQL (may take 10-15 mins)..."
docker exec oracle-db sh -c "cd /opt/oracle/apex && sqlplus sys/$DB_PASSWORD@//localhost:1521/XE as sysdba @apexins.sql SYSAUX SYSAUX TEMP /i/" || echo "APEX install step reported an error"

# Unlock Accounts
echo "Unlocking APEX Public User..."
docker exec oracle-db sh -c "cd /opt/oracle/apex && sqlplus sys/$DB_PASSWORD@//localhost:1521/XE as sysdba @apxchpwd.sql $DB_PASSWORD"
docker exec oracle-db sh -c "sqlplus sys/$DB_PASSWORD@//localhost:1521/XE as sysdba <<EOF
ALTER USER APEX_PUBLIC_USER ACCOUNT UNLOCK;
ALTER USER APEX_PUBLIC_USER IDENTIFIED BY $ORDS_PASSWORD;
EXIT;
EOF"

# 6. Download & Configure ORDS
echo "[6/8] Setting up ORDS..."
mkdir -p /opt/ords /opt/ords/config
cd /opt/ords
if [ ! -f "ords-latest.zip" ]; then
    echo "Downloading ORDS..."
    wget https://download.oracle.com/otn_software/java/ords/ords-latest.zip
fi
unzip -q -o ords-latest.zip

# Configure ORDS (Interactive mode automated via input redirection usually, but CLI is better)
# Installing ORDS in standalone mode
echo "Configuring ORDS..."
./bin/ords --config /opt/ords/config install \
    --log-folder /opt/ords/logs \
    --admin-user SYS \
    --db-hostname localhost \
    --db-port 1521 \
    --db-servicename XE \
    --feature-sdw true \
    --password-stdin <<EOF
$DB_PASSWORD
$ORDS_PASSWORD
EOF

# 7. Start ORDS
echo "[7/8] Starting ORDS..."
nohup ./bin/ords --config /opt/ords/config serve --port 8080 > /var/log/ords.log 2>&1 &

# 8. Caddy Reverse Proxy
echo "[8/8] Configuring Caddy..."
if ! command -v caddy &> /dev/null; then
    apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -y
    apt-get install -y caddy
fi

# Write Caddyfile
cat > /etc/caddy/Caddyfile <<EOF
:80 {
    # Serve Dashboard
    root * /var/www/dashboard
    file_server

    # Reverse Proxy for ORDS
    handle /ords/* {
        reverse_proxy localhost:8080 {
             header_up Host {host}
             header_up X-Real-IP {remote}
             header_up X-Forwarded-For {remote}
             header_up X-Forwarded-Proto {scheme}
        }
    }
    handle /api/tts* {
        reverse_proxy localhost:5001
    }
    handle_path /go/* {
        reverse_proxy localhost:5002
    }
}
EOF

systemctl reload caddy

mkdir -p /opt/tts
python3 -m venv /opt/tts/venv || true
(/opt/tts/venv/bin/pip install --no-cache-dir flask requests gTTS google-cloud-texttospeech) || true
cat > /opt/tts/tts_server.py <<'EOF'
import os
from io import BytesIO
import requests
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

PROVIDER = os.environ.get("TTS_PROVIDER", "gtts").lower()

# ElevenLabs config
ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVEN_BASE = "https://api.elevenlabs.io/v1"

# Google Cloud TTS config
GOOGLE_CREDS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "/etc/google-tts.json")

def eleven_default_voice():
    if not ELEVEN_KEY:
        return None
    try:
        r = requests.get(f"{ELEVEN_BASE}/voices", headers={"xi-api-key": ELEVEN_KEY}, timeout=10)
        j = r.json()
        if isinstance(j, dict) and j.get("voices"):
            return j["voices"][0].get("voice_id")
    except:
        return None
    return None

ELEVEN_DEFAULT_VOICE = eleven_default_voice()

def tts_gtts(text, lang="bn"):
    from gtts import gTTS
    buf = BytesIO()
    gTTS(text=text, lang=lang).write_to_fp(buf)
    buf.seek(0)
    return Response(buf.read(), content_type="audio/mpeg")

def tts_eleven(text, voice_id=None):
    if not ELEVEN_KEY:
        return jsonify({"error": "missing_api_key"}), 400
    voice_id = voice_id or ELEVEN_DEFAULT_VOICE
    if not voice_id:
        return jsonify({"error": "missing_voice"}), 400
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    headers = {"xi-api-key": ELEVEN_KEY, "accept": "audio/mpeg", "content-type": "application/json"}
    url = f"{ELEVEN_BASE}/text-to-speech/{voice_id}/stream?optimize_streaming_latency=4"
    r = requests.post(url, headers=headers, json=payload, stream=True, timeout=60)
    if r.status_code != 200:
        try:
            return jsonify({"error": "tts_failed", "detail": r.json()}), 502
        except:
            return jsonify({"error": "tts_failed", "status": r.status_code}), 502
    return Response(r.iter_content(chunk_size=4096), content_type="audio/mpeg")

def tts_google(text, lang_code="bn-IN", voice_name=None):
    try:
        from google.cloud import texttospeech
    except Exception as e:
        return jsonify({"error": "google_tts_not_installed", "detail": str(e)}), 500
    try:
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", GOOGLE_CREDS)
        client = texttospeech.TextToSpeechClient()
        input_text = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(language_code=lang_code, name=voice_name)
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
        response = client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
        return Response(response.audio_content, content_type="audio/mpeg")
    except Exception as e:
        return jsonify({"error": "google_tts_failed", "detail": str(e)}), 502

@app.route("/api/tts", methods=["POST"])
def tts():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "empty_text"}), 400
    if PROVIDER == "eleven":
        return tts_eleven(text, voice_id=data.get("voice_id"))
    elif PROVIDER == "google":
        return tts_google(text, lang_code=data.get("lang") or "bn-IN", voice_name=data.get("voice_name"))
    else:
        # default gTTS
        return tts_gtts(text, lang=data.get("lang") or "bn")

@app.route("/api/tts", methods=["GET"])
def tts_get():
    text = (request.args.get("text") or "").strip()
    lang = request.args.get("lang") or ("bn" if PROVIDER=="gtts" else "bn-IN")
    if not text:
        return jsonify({"error": "empty_text"}), 400
    if PROVIDER == "eleven":
        return tts_eleven(text)
    elif PROVIDER == "google":
        return tts_google(text, lang_code=lang)
    else:
        return tts_gtts(text, lang=lang)

@app.route("/health")
def health():
    return jsonify({"ok": True, "provider": PROVIDER})

@app.route("/api/tts/health")
def health_alias():
    return jsonify({"ok": True, "provider": PROVIDER})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
EOF

cat > /etc/systemd/system/tts.service <<'EOF'
[Unit]
Description=TTS Proxy
After=network.target

[Service]
EnvironmentFile=/etc/tts.env
WorkingDirectory=/opt/tts
ExecStart=/opt/tts/venv/bin/python /opt/tts/tts_server.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

touch /etc/tts.env
# Initialize env with defaults if missing
if [ ! -s /etc/tts.env ]; then
cat > /etc/tts.env <<'EOF'
TTS_PROVIDER=gtts
# For Google Cloud TTS later, upload JSON to /etc/google-tts.json and uncomment:
# GOOGLE_APPLICATION_CREDENTIALS=/etc/google-tts.json
# For ElevenLabs later, set:
# ELEVENLABS_API_KEY=your_key_here
EOF
fi
systemctl daemon-reload
systemctl enable tts
systemctl restart tts

# Link Manager Service (Shortlinks & Redirects)
mkdir -p /opt/links
python3 -m venv /opt/links/venv || true
/opt/links/venv/bin/pip install --no-cache-dir flask
cat > /opt/links/link_manager.py <<'EOF'
import os, json
from flask import Flask, request, jsonify, redirect, send_from_directory

app = Flask(__name__)
MAP_FILE = "/etc/links.json"
ADMIN_TOKEN = os.environ.get("LINK_ADMIN_TOKEN", "changeme")
DASH_DIR = "/opt/links/dashboard"
ASSETS_DIR = os.path.join(DASH_DIR, "assets")

def load_map():
    try:
        with open(MAP_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_map(m):
    with open(MAP_FILE, "w") as f:
        json.dump(m, f)

@app.route("/health")
def health():
    return jsonify({"ok": True})

@app.route("/dashboard/")
def dashboard_root():
    try:
        return send_from_directory(DASH_DIR, "index.html")
    except Exception:
        return jsonify({"error":"dashboard_not_found"}), 404

@app.route("/dashboard/<path:path>")
def dashboard_static(path):
    try:
        return send_from_directory(DASH_DIR, path)
    except Exception:
        return jsonify({"error":"asset_not_found"}), 404

@app.route("/assets/<path:path>")
def assets_static(path):
    try:
        return send_from_directory(ASSETS_DIR, path)
    except Exception:
        return jsonify({"error":"asset_not_found"}), 404

@app.route("/r/<key>")
def redirect_key(key):
    m = load_map()
    url = m.get(key)
    if not url:
        return jsonify({"error":"not_found"}), 404
    return redirect(url, code=302)

@app.route("/api/links/set", methods=["POST"])
def set_link():
    tok = request.headers.get("X-Admin-Token") or request.args.get("token")
    if tok != ADMIN_TOKEN:
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    url = (data.get("url") or "").strip()
    if not key or not url:
        return jsonify({"error":"invalid_input"}), 400
    m = load_map(); m[key]=url; save_map(m)
    return jsonify({"ok":True, "key":key, "url":url})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
EOF

cat > /etc/systemd/system/links.service <<'EOF'
[Unit]
Description=Link Manager
After=network.target

[Service]
EnvironmentFile=/etc/links.env
WorkingDirectory=/opt/links
ExecStart=/opt/links/venv/bin/python /opt/links/link_manager.py
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

touch /etc/links.env
if [ ! -s /etc/links.env ]; then
cat > /etc/links.env <<'EOF'
LINK_ADMIN_TOKEN=changeme
EOF
fi

if [ ! -f /etc/links.json ]; then
cat > /etc/links.json <<'EOF'
{
  "test": "https://example.com"
}
EOF
fi

# Prepare dashboard assets for Link Manager to serve directly
mkdir -p /opt/links/dashboard
if [ -d /var/www/dashboard ]; then
  cp -r /var/www/dashboard/* /opt/links/dashboard/ || true
fi

systemctl daemon-reload
systemctl enable links
systemctl restart links

echo "=================================================="
echo "INSTALLATION COMPLETE!"
echo "APEX/ORDS should be accessible at http://<YOUR_IP>/ords"
echo "Admin Password: $DB_PASSWORD"
echo "=================================================="
