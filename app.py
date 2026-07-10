import os
import json
from flask import Flask, request, jsonify, redirect, send_from_directory

app = Flask(__name__)

MAP_FILE = os.environ.get("LINKS_FILE", "/data/links.json")
ADMIN_TOKEN = os.environ.get("LINK_ADMIN_TOKEN", "changeme")
DASH_DIR = os.path.join(os.path.dirname(__file__), "dashboard")


def load_map():
    try:
        with open(MAP_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_map(m):
    os.makedirs(os.path.dirname(MAP_FILE), exist_ok=True)
    with open(MAP_FILE, "w") as f:
        json.dump(m, f)


@app.route("/health")
def health():
    return jsonify({"ok": True})


@app.route("/")
def index():
    dash_index = os.path.join(DASH_DIR, "index.html")
    if os.path.isfile(dash_index):
        return send_from_directory(DASH_DIR, "index.html")
    links = load_map()
    rows = "".join(
        f"<tr><td>{k}</td><td><a href='{v}'>{v}</a></td></tr>" for k, v in links.items()
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Link Manager</title>
<style>body{{font-family:sans-serif;max-width:800px;margin:40px auto;padding:0 20px}}
table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #ddd;padding:8px}}
th{{background:#f4f4f4}}</style></head>
<body>
<h1>🔗 Link Manager</h1>
<table><tr><th>Key</th><th>URL</th></tr>{rows}</table>
<p><a href="/dashboard/">Dashboard</a></p>
</body></html>"""


@app.route("/dashboard/")
@app.route("/dashboard/<path:path>")
def dashboard(path="index.html"):
    try:
        return send_from_directory(DASH_DIR, path)
    except Exception:
        return jsonify({"error": "not_found"}), 404


@app.route("/r/<key>")
def redirect_key(key):
    url = load_map().get(key)
    if not url:
        return jsonify({"error": "not_found"}), 404
    return redirect(url, code=302)


def _auth(req):
    tok = req.headers.get("X-Admin-Token") or req.args.get("token")
    return tok == ADMIN_TOKEN


@app.route("/api/links", methods=["GET"])
def list_links():
    if not _auth(request):
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(load_map())


@app.route("/api/links/set", methods=["POST"])
def set_link():
    if not _auth(request):
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    url = (data.get("url") or "").strip()
    if not key or not url:
        return jsonify({"error": "invalid_input"}), 400
    m = load_map()
    m[key] = url
    save_map(m)
    return jsonify({"ok": True, "key": key, "url": url})


@app.route("/api/links/delete", methods=["POST"])
def delete_link():
    if not _auth(request):
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    if not key:
        return jsonify({"error": "invalid_input"}), 400
    m = load_map()
    if key not in m:
        return jsonify({"error": "not_found"}), 404
    del m[key]
    save_map(m)
    return jsonify({"ok": True, "deleted": key})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
