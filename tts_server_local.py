import os
from io import BytesIO
import requests
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

PROVIDER = os.environ.get("TTS_PROVIDER", "gtts").lower()

ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVEN_BASE = "https://api.elevenlabs.io/v1"
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
def tts_post():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "empty_text"}), 400
    if PROVIDER == "eleven":
        return tts_eleven(text, voice_id=data.get("voice_id"))
    elif PROVIDER == "google":
        return tts_google(text, lang_code=data.get("lang") or "bn-IN", voice_name=data.get("voice_name"))
    else:
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

@app.route("/api/tts/health")
def health_alias():
    return jsonify({"ok": True, "provider": PROVIDER})

@app.route("/health")
def health():
    return jsonify({"ok": True, "provider": PROVIDER})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)

