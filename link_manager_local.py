import os, json
import re
import uuid
from urllib.parse import urlencode, urlparse
from flask import Flask, request, jsonify, redirect, Response, send_from_directory
try:
    import requests
except Exception:
    requests = None
try:
    import qrcode
except Exception:
    qrcode = None

app = Flask(__name__)
# Portable storage paths (Windows-friendly). Allow override via environment.
DATA_DIR = os.environ.get("LINK_DATA_DIR") or os.path.join(os.getcwd(), "data")
MAP_FILE = os.environ.get("LINK_MAP_FILE") or os.path.join(DATA_DIR, "links.json")
ADMIN_TOKEN = os.environ.get("LINK_ADMIN_TOKEN", "changeme")
ADMIN_USER = os.environ.get("LINK_ADMIN_USER", "admin")
ADMIN_LOGIN_PASSWORD = os.environ.get("LINK_LOGIN_PASSWORD", "admin")
FREEZE_CREATE = os.environ.get("LINK_FREEZE_CREATE", "0") == "1"
META_FILE = os.environ.get("LINK_META_FILE") or os.path.join(DATA_DIR, "links.meta.json")
CREATE_LIMIT = int(os.environ.get("LINK_CREATE_LIMIT", "50") or "50")
UPDATE_LIMIT = int(os.environ.get("LINK_UPDATE_LIMIT", "200") or "200")
SAFE_MODE = os.environ.get("LINK_SAFE_MODE", "1") == "1"
ALLOWED_HOSTS = [x.strip().lower() for x in (os.environ.get("LINK_ALLOWED_HOSTS") or "").split(",") if x.strip()]
BLOCK_PATTERNS = [x.strip() for x in (os.environ.get("LINK_BLOCK_PATTERNS") or "").split(",") if x.strip()]
LIVE_FILE = os.environ.get("LINK_LIVE_FILE") or os.path.join(DATA_DIR, "live_links.json")
LIVE_TEMPLATE_DIR = os.environ.get("LINK_LIVE_TEMPLATE_DIR") or os.path.join(DATA_DIR, "live_templates")
LIVE_QR_DIR = os.environ.get("LINK_LIVE_QR_DIR") or os.path.join(DATA_DIR, "live_qr")

try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    pass
try:
    os.makedirs(LIVE_TEMPLATE_DIR, exist_ok=True)
except Exception:
    pass
try:
    os.makedirs(LIVE_QR_DIR, exist_ok=True)
except Exception:
    pass

def load_map():
    try:
        with open(MAP_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_map(m):
    try:
        os.makedirs(os.path.dirname(MAP_FILE), exist_ok=True)
    except Exception:
        pass
    with open(MAP_FILE, "w") as f:
        json.dump(m, f)

def today_str():
    try:
        import datetime
        return datetime.date.today().isoformat()
    except Exception:
        return "1970-01-01"

def load_meta():
    m = load_map()
    default = {"date": today_str(), "creates": 0, "updates": 0, "total_keys": len(m)}
    try:
        with open(META_FILE, "r") as f:
            meta = json.load(f)
    except Exception:
        meta = default
    if meta.get("date") != today_str():
        meta["date"] = today_str()
        meta["creates"] = 0
        meta["updates"] = 0
    meta.setdefault("total_keys", len(m))
    return meta

def load_live():
    default = {"domains": [], "templates": [], "links": []}
    try:
        with open(LIVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return default
            data.setdefault("domains", [])
            data.setdefault("templates", [])
            data.setdefault("links", [])
            return data
    except Exception:
        return default

def save_live(data):
    try:
        os.makedirs(os.path.dirname(LIVE_FILE), exist_ok=True)
    except Exception:
        pass
    with open(LIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def save_meta(meta):
    try:
        os.makedirs(os.path.dirname(META_FILE), exist_ok=True)
    except Exception:
        pass
    with open(META_FILE, "w") as f:
        json.dump(meta, f)

def current_token():
    meta = load_meta()
    t = meta.get("admin_token")
    return (t or ADMIN_TOKEN)

def client_ip():
    h = request.headers.get("X-Forwarded-For") or ""
    if h:
        return h.split(",")[0].strip()
    return request.remote_addr or ""

def admin_auth_ok():
    tok = request.headers.get("X-Admin-Token") or request.args.get("token")
    if tok == current_token():
        return True
    pwd = request.headers.get("X-Login-Password") or request.args.get("password") or request.args.get("pwd") or ""
    if pwd == ADMIN_LOGIN_PASSWORD:
        return True
    return False

def admin_auth_token_only():
    tok = request.headers.get("X-Admin-Token") or request.args.get("token")
    if tok != current_token():
        return False
    return True

def _host_of(u: str):
    try:
        m = re.match(r"^https?://([^/]+)", u or "")
        return (m.group(1) or "").strip().lower() if m else ""
    except Exception:
        return ""

def normalize_domain(v: str):
    s = (v or "").strip()
    if not s:
        return ""
    if not s.startswith("http://") and not s.startswith("https://"):
        s = "https://" + s
    try:
        p = urlparse(s)
        if p.scheme not in ("http", "https"):
            return ""
        if not p.netloc:
            return ""
        return f"{p.scheme}://{p.netloc}".rstrip("/")
    except Exception:
        return ""

def extract_placeholders(html: str):
    found = []
    seen = set()
    try:
        for m in re.finditer(r"{{\s*([a-zA-Z0-9_]+)\s*}}", html or ""):
            key = m.group(1)
            if key and key not in seen:
                seen.add(key)
                found.append(key)
    except Exception:
        return []
    return found

def render_live_template(html: str, params: dict):
    def _repl(m):
        k = m.group(1)
        val = params.get(k, "")
        return "" if val is None else str(val)
    try:
        return re.sub(r"{{\s*([a-zA-Z0-9_]+)\s*}}", _repl, html or "")
    except Exception:
        return html or ""

def parse_fields_override(raw):
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        t = raw.strip()
        if not t:
            return []
        try:
            obj = json.loads(t)
            if isinstance(obj, list):
                return [str(x).strip() for x in obj if str(x).strip()]
        except Exception:
            pass
        return [x.strip() for x in t.split(",") if x.strip()]
    return []

def url_allowed(u: str):
    s = (u or "").strip()
    if not s:
        return False
    h = _host_of(s)
    if ALLOWED_HOSTS:
        ok = False
        for ah in ALLOWED_HOSTS:
            if h == ah or (h.endswith("." + ah)):
                ok = True
                break
        if not ok:
            return False
    ls = s.lower()
    for pat in BLOCK_PATTERNS:
        try:
            if re.search(pat, ls, flags=re.IGNORECASE):
                return False
        except Exception:
            if pat and (pat in ls):
                return False
    return True

@app.route("/health")
def health():
    return jsonify({"ok": True})

@app.route("/dashboard/")
def dashboard_root():
    p = os.path.join(os.getcwd(), "dashboard")
    index = "index.html"
    try:
        return send_from_directory(p, index)
    except Exception:
        return jsonify({"error":"dashboard_not_found"}), 404

@app.route("/dashboard/<path:path>")
def dashboard_static(path):
    p = os.path.join(os.getcwd(), "dashboard")
    try:
        return send_from_directory(p, path)
    except Exception:
        return jsonify({"error":"asset_not_found"}), 404

@app.route("/assets/<path:path>")
def assets_static(path):
    p = os.path.join(os.getcwd(), "dashboard", "assets")
    try:
        return send_from_directory(p, path)
    except Exception:
        return jsonify({"error":"asset_not_found"}), 404

@app.route("/panel/live")
def live_panel():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Live Link Manager</title>
  <style>
    body{font-family:Arial,sans-serif;max-width:980px;margin:20px auto;padding:0 12px}
    .card{border:1px solid #ddd;border-radius:8px;padding:14px;margin-bottom:14px}
    input,select,textarea,button{width:100%;padding:9px;margin-top:8px;box-sizing:border-box}
    .row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
    table{width:100%;border-collapse:collapse}
    th,td{border:1px solid #ddd;padding:8px;font-size:12px}
    @media(max-width:760px){.row{grid-template-columns:1fr}}
  </style>
  <script>
    async function j(url, opts){
      const r = await fetch(url, opts);
      const d = await r.json();
      if(!r.ok){ throw new Error(d.error || "request_failed"); }
      return d;
    }
    async function refresh() {
      const data = await j('/api/live/state' + window.location.search);
      const ds = document.getElementById('domains');
      ds.innerHTML = data.domains.map(d => `<option value="${d}">${d}</option>`).join('');
      const ts = document.getElementById('templates');
      ts.innerHTML = data.templates.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
      const rows = data.links.map(l => `<tr><td>${l.id}</td><td>${l.domain}</td><td><a target="_blank" href="${l.url}">${l.url}</a></td><td><a target="_blank" href="${l.qr_url}">QR</a></td></tr>`).join('');
      document.getElementById('links').innerHTML = rows;
    }
    async function addDomain(e){
      e.preventDefault();
      const domain = document.getElementById('domainInput').value;
      await j('/api/live/domains/add' + window.location.search, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({domain})});
      document.getElementById('domainInput').value = '';
      await refresh();
    }
    async function detectTemplate(e){
      e.preventDefault();
      const fd = new FormData(document.getElementById('templateForm'));
      const d = await fetch('/api/live/templates/detect' + window.location.search, {method:'POST', body:fd}).then(x=>x.json());
      if(!d.ok && d.error){ throw new Error(d.error); }
      document.getElementById('fields').value = (d.fields || []).join(', ');
    }
    async function saveTemplate(e){
      e.preventDefault();
      const fd = new FormData(document.getElementById('templateForm'));
      await fetch('/api/live/templates/create' + window.location.search, {method:'POST', body:fd}).then(async r=>{
        const d = await r.json();
        if(!r.ok){ throw new Error(d.error || 'save_failed'); }
      });
      document.getElementById('templateName').value='';
      document.getElementById('templateHtml').value='';
      document.getElementById('templateFile').value='';
      await refresh();
    }
    async function makeLink(e){
      e.preventDefault();
      const payload = {
        domain: document.getElementById('domains').value,
        template_id: document.getElementById('templates').value,
        params_json: document.getElementById('paramsJson').value,
        custom_query: document.getElementById('customQuery').value
      };
      const d = await j('/api/live/links/create' + window.location.search, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
      document.getElementById('lastLink').innerHTML = `<a target="_blank" href="${d.url}">${d.url}</a> | <a target="_blank" href="${d.qr_url}">QR</a>`;
      await refresh();
    }
    window.addEventListener('load', () => {
      refresh().catch(e => alert(e.message));
      document.getElementById('domainForm').addEventListener('submit', e => addDomain(e).catch(x=>alert(x.message)));
      document.getElementById('detectBtn').addEventListener('click', e => detectTemplate(e).catch(x=>alert(x.message)));
      document.getElementById('templateForm').addEventListener('submit', e => saveTemplate(e).catch(x=>alert(x.message)));
      document.getElementById('linkForm').addEventListener('submit', e => makeLink(e).catch(x=>alert(x.message)));
    });
  </script>
</head>
<body>
  <h2>Live Link Manager</h2>
  <div class="card">
    <h3>1) Multiple Domain</h3>
    <form id="domainForm"><input id="domainInput" placeholder="example.com or https://example.com" required /><button>Add Domain</button></form>
  </div>
  <div class="card">
    <h3>2) HTML Template Upload/Input</h3>
    <form id="templateForm" enctype="multipart/form-data">
      <input id="templateName" name="name" placeholder="Template name" required />
      <textarea id="templateHtml" name="html" rows="8" placeholder="Paste full HTML with placeholders like {{name}}"></textarea>
      <input id="templateFile" type="file" name="html_file" accept=".html,text/html" />
      <button id="detectBtn" type="button">Detect Fields</button>
      <input id="fields" name="fields_override" placeholder="Detected/editable fields (comma separated)" />
      <button type="submit">Save Template</button>
    </form>
  </div>
  <div class="card">
    <h3>3) Generate Live Link + QR</h3>
    <form id="linkForm">
      <div class="row">
        <div><label>Domain</label><select id="domains" required></select></div>
        <div><label>Template</label><select id="templates" required></select></div>
      </div>
      <textarea id="paramsJson" rows="5" placeholder='{"key1":"value1","key2":"value2"}'></textarea>
      <input id="customQuery" placeholder="key1=value1&key2=value2" />
      <button>Create Live Link</button>
    </form>
    <div id="lastLink"></div>
  </div>
  <div class="card">
    <h3>Saved Links</h3>
    <table><thead><tr><th>ID</th><th>Domain</th><th>URL</th><th>QR</th></tr></thead><tbody id="links"></tbody></table>
  </div>
</body>
</html>"""

@app.route("/live/qr/<path:name>")
def live_qr(name):
    try:
        return send_from_directory(LIVE_QR_DIR, name)
    except Exception:
        return jsonify({"error":"not_found"}), 404

@app.route("/live/<link_id>")
def live_render(link_id):
    data = load_live()
    link = next((x for x in data.get("links", []) if x.get("id") == link_id), None)
    if not link:
        return jsonify({"error":"not_found"}), 404
    template_id = link.get("template_id")
    tpl = next((x for x in data.get("templates", []) if x.get("id") == template_id), None)
    if not tpl:
        return jsonify({"error":"template_not_found"}), 404
    try:
        with open(tpl.get("path"), "r", encoding="utf-8") as f:
            html = f.read()
    except Exception:
        return jsonify({"error":"template_missing"}), 404
    params = {}
    params.update(link.get("params") or {})
    try:
        params.update({k: v for k, v in request.args.items()})
    except Exception:
        pass
    out = render_live_template(html, params)
    return Response(out.encode("utf-8", errors="ignore"), content_type="text/html; charset=utf-8")

@app.route("/api/live/state")
def api_live_state():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    data = load_live()
    links = []
    for x in data.get("links", []):
        links.append({
            "id": x.get("id"),
            "domain": x.get("domain"),
            "url": x.get("url"),
            "qr_url": x.get("qr_url"),
            "template_id": x.get("template_id")
        })
    return jsonify({
        "ok": True,
        "domains": data.get("domains", []),
        "templates": [{"id": t.get("id"), "name": t.get("name"), "fields": t.get("fields", [])} for t in data.get("templates", [])],
        "links": links
    })

@app.route("/api/live/domains/add", methods=["POST"])
def api_live_domain_add():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    if not data and request.form:
        data = request.form.to_dict()
    domain = normalize_domain(data.get("domain") or "")
    if not domain:
        return jsonify({"error":"invalid_domain"}), 400
    live = load_live()
    if domain not in live["domains"]:
        live["domains"].append(domain)
        save_live(live)
    return jsonify({"ok": True, "domain": domain})

def _read_template_content():
    content = ""
    if request.files and request.files.get("html_file"):
        f = request.files.get("html_file")
        try:
            content = f.read().decode("utf-8", errors="ignore")
        except Exception:
            content = ""
    if not content:
        content = (request.form.get("html") or "").strip()
    if not content:
        data = request.get_json(silent=True) or {}
        content = (data.get("html") or "").strip()
    return content

@app.route("/api/live/templates/detect", methods=["POST"])
def api_live_template_detect():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    content = _read_template_content()
    if not content:
        return jsonify({"error":"html_required"}), 400
    fields = extract_placeholders(content)
    return jsonify({"ok": True, "fields": fields})

@app.route("/api/live/templates/create", methods=["POST"])
def api_live_template_create():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    name = (request.form.get("name") or "").strip()
    if not name:
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
    content = _read_template_content()
    if not name or not content:
        return jsonify({"error":"invalid_input"}), 400
    fields_raw = request.form.get("fields_override")
    if not fields_raw:
        body = request.get_json(silent=True) or {}
        fields_raw = body.get("fields_override")
    auto_fields = extract_placeholders(content)
    edited_fields = parse_fields_override(fields_raw)
    fields = edited_fields if edited_fields else auto_fields

    live = load_live()
    template_id = uuid.uuid4().hex[:10]
    template_path = os.path.join(LIVE_TEMPLATE_DIR, f"{template_id}.html")
    with open(template_path, "w", encoding="utf-8") as f:
        f.write(content)
    live["templates"].append({
        "id": template_id,
        "name": name,
        "path": template_path,
        "fields": fields
    })
    save_live(live)
    return jsonify({"ok": True, "id": template_id, "fields": fields})

@app.route("/api/live/links/create", methods=["POST"])
def api_live_link_create():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    if not data and request.form:
        data = request.form.to_dict()
    domain = normalize_domain(data.get("domain") or "")
    template_id = (data.get("template_id") or "").strip()
    params_json = data.get("params_json")
    custom_query = (data.get("custom_query") or "").strip().lstrip("?")
    if not domain or not template_id:
        return jsonify({"error":"invalid_input"}), 400

    live = load_live()
    if domain not in live.get("domains", []):
        return jsonify({"error":"domain_not_found"}), 404
    tpl = next((x for x in live.get("templates", []) if x.get("id") == template_id), None)
    if not tpl:
        return jsonify({"error":"template_not_found"}), 404
    try:
        params = json.loads(params_json) if isinstance(params_json, str) and params_json.strip() else (params_json or {})
        if not isinstance(params, dict):
            return jsonify({"error":"params_must_be_object"}), 400
    except Exception:
        return jsonify({"error":"invalid_params_json"}), 400

    link_id = uuid.uuid4().hex[:10]
    q1 = urlencode({k: "" if v is None else str(v) for k, v in params.items()}, doseq=True)
    query = "&".join([x for x in [q1, custom_query] if x])
    url = f"{domain}/live/{link_id}"
    if query:
        url = f"{url}?{query}"

    if qrcode is None:
        return jsonify({"error":"qrcode_dependency_missing"}), 500
    qr_name = f"{link_id}.png"
    qr_path = os.path.join(LIVE_QR_DIR, qr_name)
    qrobj = qrcode.QRCode(version=1, box_size=8, border=2)
    qrobj.add_data(url)
    qrobj.make(fit=True)
    img = qrobj.make_image(fill_color="black", back_color="white")
    img.save(qr_path)
    qr_url = f"/live/qr/{qr_name}"

    live["links"].append({
        "id": link_id,
        "domain": domain,
        "template_id": template_id,
        "params": params,
        "custom_query": custom_query,
        "url": url,
        "qr_path": qr_path,
        "qr_url": qr_url
    })
    save_live(live)
    return jsonify({"ok": True, "id": link_id, "url": url, "qr_url": qr_url})

def _inject_banner(html: str, banner_html: str) -> str:
    try:
        if not banner_html:
            return html
        # insert CSS for banner at head if exists
        css = """<style>#lm-banner{position:fixed;top:0;left:0;right:0;background:#002b5c;color:#fff;padding:10px 14px;z-index:9999;font-family:system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;box-shadow:0 2px 6px rgba(0,0,0,0.2);}body{margin-top:52px !important;}</style>"""
        html = re.sub(r"</head>", css+"</head>", html, count=1, flags=re.IGNORECASE)
        # insert banner DIV at top of body
        banner = f"<div id=\"lm-banner\">{banner_html}</div>"
        html = re.sub(r"<body[^>]*>", lambda m: m.group(0)+banner, html, count=1, flags=re.IGNORECASE)
        return html
    except Exception:
        return html

def _apply_replacements(html: str, pairs):
    if not pairs:
        return html
    try:
        for p in pairs:
            f = (p.get("find") or "")
            r = (p.get("replace") or "")
            if not f:
                continue
            use_regex = bool(p.get("regex"))
            ignore_case = bool(p.get("ignore_case"))
            if use_regex:
                try:
                    flags = re.IGNORECASE if ignore_case else 0
                    html = re.sub(f, r, html, flags=flags)
                except Exception:
                    pass
            else:
                if ignore_case:
                    try:
                        html = re.sub(re.escape(f), r, html, flags=re.IGNORECASE)
                    except Exception:
                        html = html.replace(f, r)
                else:
                    html = html.replace(f, r)
        return html
    except Exception:
        return html

def _inject_base_href(html: str, url: str):
    try:
        if not url:
            return html
        m = re.match(r"^(https?://[^/]+)", url)
        if not m:
            return html
        base = m.group(1).strip()
        # If a <base> tag already exists, skip
        if re.search(r"<base\s+href=", html, flags=re.IGNORECASE):
            return html
        tag = f"<base href=\"{base}/\">"
        # Insert before first <meta> or after <head>
        html = re.sub(r"<head[^>]*>", lambda mm: mm.group(0) + tag, html, count=1, flags=re.IGNORECASE)
        return html
    except Exception:
        return html

def _rewrite_root_urls(html: str, url: str):
    try:
        if not url:
            return html
        m = re.match(r"^(https?://[^/]+)", url)
        if not m:
            return html
        base = m.group(1).strip()
        def repl_attr(ma):
            pre = ma.group(1)
            path = ma.group(2)
            return f"{pre}{base}/{path}"
        # Rewrite href/src/action="/..." to absolute
        html = re.sub(r"((?:href|src|action)\s*=\s*[\"'])/(?!/)([^\"']*)", repl_attr, html, flags=re.IGNORECASE)
        return html
    except Exception:
        return html

def _proxy_to_pcc(subpath: str):
    try:
        if requests is None:
            return jsonify({"error":"proxy_unavailable","detail":"requests_not_installed"}), 500
        base = "https://pcc.police.gov.bd/"
        qs = request.query_string.decode("utf-8")
        remote = base + (subpath.lstrip("/"))
        if qs:
            remote = remote + ("?" + qs)
        r = requests.get(remote, timeout=20, headers={
            "User-Agent": "LinkManager/1.0",
            "Referer": base,
            "Host": "pcc.police.gov.bd"
        })
        content_type = r.headers.get("Content-Type", "application/octet-stream")
        return Response(r.content, content_type=content_type, status=r.status_code)
    except Exception as e:
        return jsonify({"error":"asset_proxy_failed","detail": str(e)}), 502

@app.route("/i/<path:sub>")
def proxy_pcc_i(sub):
    return _proxy_to_pcc(f"i/{sub}")

@app.route("/ords/<path:sub>")
def proxy_pcc_ords(sub):
    return _proxy_to_pcc(f"ords/{sub}")

def _inject_client_replacer(html: str, pairs):
    try:
        arr = []
        try:
            for p in pairs or []:
                arr.append({
                    "find": p.get("find") or "",
                    "replace": p.get("replace") or "",
                    "regex": bool(p.get("regex")),
                    "ignore_case": bool(p.get("ignore_case"))
                })
        except Exception:
            arr = []
        js = (
            "<script>(function(){"+
            "var P=" + json.dumps(arr) + ";"+
            "function applyHtml(){try{var html=document.body.innerHTML;for(var j=0;j<P.length;j++){var p=P[j];if(!p.find) continue;var rep=(p.replace||'').replace(/\\\\([1-9])/g,'$$$1');try{if(p.regex){var f=new RegExp(p.find,p.ignore_case?'gi':'g');html=html.replace(f,rep);}else{var esc=p.find.replace(/[.*+?^${}()|[\\]\\]/g,'\\$&');var f=new RegExp(esc,p.ignore_case?'gi':'g');html=html.replace(f,rep);}}catch(e){}}document.body.innerHTML=html;}catch(e){}}"+
            "function run(){applyHtml()}"+
            "document.addEventListener('DOMContentLoaded',run);"+
            "window.addEventListener('load',run);"+
            "var mo=new MutationObserver(function(){run()});mo.observe(document.documentElement,{childList:true,subtree:true});"+
            "setTimeout(run,500);setTimeout(run,1500);setTimeout(run,3000);"+
            "})();</script>"
        )
        html = re.sub(r"</body>", js+"</body>", html, count=1, flags=re.IGNORECASE)
        return html
    except Exception:
        return html

def _sanitize_min(html: str):
    try:
        html = re.sub(r"<script[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"<link[^>]*>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"<style[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"<meta[^>]*>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"<head[\s\S]*?</head>", "", html, flags=re.IGNORECASE)
        return html
    except Exception:
        return html

@app.route("/r/<key>")
def redirect_key(key):
    m = load_map()
    entry = m.get(key)
    if not entry:
        return jsonify({"error":"not_found"}), 404
    # backward compatibility: if entry is str, redirect 302
    if isinstance(entry, str):
        status = int(request.args.get("status") or 302)
        return redirect(entry, code=status if status in (301,302) else 302)
    # object form
    mode = (entry.get("mode") or "redirect").lower()
    url = entry.get("url")
    status = int(entry.get("status") or (request.args.get("status") or 302))
    if SAFE_MODE and mode != "redirect":
        mode = "redirect"
    if mode == "render":
        if requests is None:
            return jsonify({"error":"proxy_unavailable","detail":"requests_not_installed"}), 500
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent":"LinkManager/1.0"})
            body = r.text
            body = _sanitize_min(body)
            body = _apply_replacements(body, entry.get("replace_pairs"))
            body = _inject_client_replacer(body, entry.get("replace_pairs"))
            html = """<!doctype html><html><head><meta charset=\"utf-8\"><title>View</title><style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;padding:20px;line-height:1.6} .card{max-width:900px;margin:0 auto;border:1px solid #ddd;border-radius:8px;padding:20px;background:#fff} .note{color:#666;font-size:.9rem;margin-top:10px}</style></head><body><div class=\"card\">""" + body + """<div class=\"note\">Rendered via Link Manager</div></div></body></html>"""
            return Response(html.encode("utf-8", errors="ignore"), content_type="text/html")
        except Exception as e:
            return jsonify({"error":"proxy_failed","detail":str(e)}), 502
    if mode == "template":
        try:
            m = entry.get("meta") or {}
            name = m.get("name") or ""
            father = m.get("father") or ""
            address = m.get("address") or ""
            passport = m.get("passport") or ""
            issue = m.get("issueDate") or ""
            html = (
                "<!doctype html><html><head><meta charset=\"utf-8\"><title>Certificate</title>"+
                "<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#f7f7f7;margin:0;padding:20px} .card{max-width:900px;margin:0 auto;background:#fff;border:1px solid #ddd;border-radius:8px;padding:24px} h1{margin:0 0 12px;font-size:1.4rem;color:#002b5c} .row{margin:6px 0} b{color:#111} .muted{color:#666;font-size:.9rem;margin-top:14px}</style></head><body>"+
                "<div class=\"card\"><h1>POLICE CLEARANCE CERTIFICATE</h1>"+
                f"<div class=\"row\">The character and antecedents of Mr. <b>{name}</b> Son of <b>{father}</b></div>"+
                f"<div class=\"row\">Address: <b>{address}</b></div>"+
                f"<div class=\"row\">Passport No: <b>{passport}</b></div>"+
                f"<div class=\"row\">Issued on: <b>{issue}</b></div>"+
                "<div class=\"muted\">Rendered via Link Manager (template)</div></div></body></html>"
            )
            return Response(html.encode("utf-8", errors="ignore"), content_type="text/html")
        except Exception as e:
            return jsonify({"error":"template_failed","detail":str(e)}), 500
    if mode == "redirect":
        return redirect(url, code=status if status in (301,302) else 302)
    # proxy mode
    if requests is None:
        return jsonify({"error":"proxy_unavailable","detail":"requests_not_installed"}), 500
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent":"LinkManager/1.0"})
        content_type = r.headers.get("Content-Type","text/html")
        body = r.text
        asset_proxy = bool(entry.get("asset_proxy"))
        if not asset_proxy:
            body = _rewrite_root_urls(body, url)
            body = _inject_base_href(body, url)
        body = _inject_banner(body, entry.get("banner_html") or "")
        body = _apply_replacements(body, entry.get("replace_pairs"))
        body = _inject_client_replacer(body, entry.get("replace_pairs"))
        return Response(body.encode("utf-8", errors="ignore"), content_type=content_type)
    except Exception as e:
        return jsonify({"error":"proxy_failed","detail":str(e)}), 502

# --- PCC Extractor ---
def _extract_pcc_from_html(html: str):
    try:
        data = {}
        m = re.search(r"Ref\s*No\.\s*([A-Z0-9]+)", html, flags=re.IGNORECASE)
        if m: data["ref"] = m.group(1)
        m = re.search(r"Dated:\s*([0-9]{2}-[A-Z]{3}-[0-9]{2})", html, flags=re.IGNORECASE)
        if m: data["dated"] = m.group(1)
        m = re.search(r"Passport\s+No\.\s*([A-Z0-9]+)", html, flags=re.IGNORECASE)
        if m: data["passport"] = m.group(1)
        m = re.search(r"Issued\s+at\s+([A-Z/\- ]+?)\s+on\s+([0-9]{2}-[A-Z]{3}-[0-9]{2})", html, flags=re.IGNORECASE)
        if m:
            data["place"] = m.group(1).strip()
            data["issueDate"] = m.group(2).strip()
        m = re.search(r"The character.*?of\s+(Mr\.|Ms\.|Mrs\.)?\s*([^\n<]+?)\s+Son\s+of\s+(.+?)(?=\s*Village/\s*Area:)", html, flags=re.IGNORECASE|re.DOTALL)
        if m:
            data["name"] = m.group(2).strip()
            data["father"] = m.group(3).strip()
        m = re.search(r"Village/\s*Area:\s*([^,]+),\s*P/O:\s*([^,]+),\s*Post\s*Code:\s*([0-9]+),\s*P/S:\s*([^,]+),\s*District:\s*([^\n<]+?)(?=\s*(holder|Passport|Issued|on|$))", html, flags=re.IGNORECASE)
        if m:
            data["village"] = m.group(1).strip()
            data["po"] = m.group(2).strip()
            data["postcode"] = m.group(3).strip()
            data["ps"] = m.group(4).strip()
            data["district"] = m.group(5).strip()
            data["address"] = ", ".join([x for x in [data.get("village"), f"P/O: {data.get('po')}" if data.get('po') else None, f"P/S: {data.get('ps')}" if data.get('ps') else None, f"District: {data.get('district')}" if data.get('district') else None] if x])
        return data
    except Exception:
        return {}

@app.route("/api/extract/pcc", methods=["POST"])
def api_extract_pcc():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    if requests is None:
        return jsonify({"error":"requests_not_installed"}), 500
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error":"invalid_input"}), 400
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent":"LinkManager/1.0"})
        if r.status_code >= 400:
            return jsonify({"error":"fetch_failed","status": r.status_code}), 502
        fields = _extract_pcc_from_html(r.text)
        return jsonify({"ok": True, **fields})
    except Exception as e:
        return jsonify({"error":"fetch_error","detail": str(e)}), 502

def _extract_apostille_from_url(u: str):
    try:
        data = {}
        m = re.search(r"/application-details/(\d+)", u)
        if m:
            data["application_id"] = m.group(1)
            data["ref"] = m.group(1)
        mt = re.search(r"[?&]t=([^&]+)", u)
        if mt:
            data["token"] = mt.group(1)
        return data
    except Exception:
        return {}

@app.route("/api/extract/apostille", methods=["POST"])
def api_extract_apostille():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error":"invalid_input"}), 400
    fields = _extract_apostille_from_url(url)
    return jsonify({"ok": True, **fields})

@app.route("/api/links/list")
def list_links():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    return jsonify(load_map())

@app.route("/api/links/quota")
def quota():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    meta = load_meta()
    return jsonify({
        "date": meta.get("date"),
        "freeze_create": FREEZE_CREATE,
        "creates": meta.get("creates", 0),
        "updates": meta.get("updates", 0),
        "create_limit": CREATE_LIMIT,
        "update_limit": UPDATE_LIMIT,
        "total_keys": meta.get("total_keys", 0)
    })

@app.route("/api/links/get")
def get_link():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    key = (request.args.get("key") or "").strip()
    if not key:
        return jsonify({"error":"invalid_input"}), 400
    m = load_map()
    e = m.get(key)
    if e is None:
        return jsonify({"error":"not_found"}), 404
    if isinstance(e, str):
        e = {"url": e, "mode": "redirect", "status": 302, "banner_html": "", "replace_pairs": [], "meta": {}}
    e.setdefault("meta", {})
    return jsonify({"key": key, **e})

@app.route("/api/links/set", methods=["POST"])
def set_link():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    if not data and request.form:
        data = request.form.to_dict()
    key = (data.get("key") or "").strip()
    url = (data.get("url") or "").strip()
    if not key or not url:
        return jsonify({"error":"invalid_input"}), 400
    if not url_allowed(url):
        return jsonify({"error":"url_not_allowed"}), 400
    m = load_map()
    exists = key in m
    if FREEZE_CREATE and not exists:
        return jsonify({"error":"creation_frozen"}), 403
    meta = load_meta()
    entry = {
        "url": url,
        "mode": (data.get("mode") or "redirect").lower(),
        "status": int(data.get("status") or 302),
        "banner_html": data.get("banner_html") or "",
        "replace_pairs": data.get("replace_pairs") or [],
        "meta": data.get("meta") or {},
        "asset_proxy": bool(data.get("asset_proxy"))
    }
    if SAFE_MODE and entry["mode"] != "redirect":
        entry["mode"] = "redirect"
    if exists:
        if meta.get("updates", 0) >= UPDATE_LIMIT:
            return jsonify({"error":"too_many_updates"}), 429
        meta["updates"] = meta.get("updates", 0) + 1
    else:
        if meta.get("creates", 0) >= CREATE_LIMIT:
            return jsonify({"error":"too_many_creates"}), 429
        meta["creates"] = meta.get("creates", 0) + 1
        meta["total_keys"] = meta.get("total_keys", 0) + 1
    m[key]=entry; save_map(m); save_meta(meta)
    return jsonify({"ok":True, "key":key, **entry})

@app.route("/api/links/update", methods=["POST"])
def update_link():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    if not data and request.form:
        data = request.form.to_dict()
    key = (data.get("key") or "").strip()
    m = load_map()
    if key not in m:
        return jsonify({"error":"not_found"}), 404
    sys_meta = load_meta()
    if sys_meta.get("updates", 0) >= UPDATE_LIMIT:
        return jsonify({"error":"too_many_updates"}), 429
    url = (data.get("url") or m[key] if isinstance(m[key], str) else m[key].get("url") or "").strip()
    if not url_allowed(url):
        return jsonify({"error":"url_not_allowed"}), 400
    mode = (data.get("mode") or (m[key].get("mode") if isinstance(m[key], dict) else "redirect")).lower()
    status = int(data.get("status") or (m[key].get("status") if isinstance(m[key], dict) else 302))
    banner_html = data.get("banner_html") if data.get("banner_html") is not None else (m[key].get("banner_html") if isinstance(m[key], dict) else "")
    replace_pairs = data.get("replace_pairs") if data.get("replace_pairs") is not None else (m[key].get("replace_pairs") if isinstance(m[key], dict) else [])
    entry_meta = data.get("meta") if data.get("meta") is not None else (m[key].get("meta") if isinstance(m[key], dict) else {})
    asset_proxy = bool(data.get("asset_proxy")) if data.get("asset_proxy") is not None else (m[key].get("asset_proxy") if isinstance(m[key], dict) else False)
    if SAFE_MODE and mode != "redirect":
        mode = "redirect"
    entry = {"url": url, "mode": mode, "status": status, "banner_html": banner_html or "", "replace_pairs": replace_pairs or [], "meta": entry_meta or {}, "asset_proxy": bool(asset_proxy)}
    m[key] = entry
    sys_meta["updates"] = sys_meta.get("updates", 0) + 1
    save_map(m); save_meta(sys_meta)
    return jsonify({"ok": True, "key": key, **entry})

@app.route("/api/links/reset", methods=["POST"])
def reset_link():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    if not data and request.form:
        data = request.form.to_dict()
    scope = (data.get("scope") or "key").strip()
    m = load_map(); meta = load_meta()
    if scope == "key":
        key = (data.get("key") or "").strip()
        if key not in m:
            return jsonify({"error":"not_found"}), 404
        url = m[key] if isinstance(m[key], str) else m[key].get("url")
        old_meta = m[key].get("meta") if isinstance(m[key], dict) else {}
        m[key] = {"url": url, "mode": "redirect", "status": 302, "banner_html": "", "replace_pairs": [], "meta": old_meta}
        meta["updates"] = meta.get("updates", 0) + 1
        save_map(m); save_meta(meta)
        return jsonify({"ok": True, "key": key})
    if scope == "counters":
        meta["date"] = today_str(); meta["creates"] = 0; meta["updates"] = 0
        save_meta(meta)
        return jsonify({"ok": True})
    if scope == "factory":
        save_map({}); meta = {"date": today_str(), "creates": 0, "updates": 0, "total_keys": 0}
        save_meta(meta)
        return jsonify({"ok": True})
    return jsonify({"error":"invalid_scope"}), 400

@app.route("/api/links/delete", methods=["POST"])
def delete_link():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    if not data and request.form:
        data = request.form.to_dict()
    key = (data.get("key") or "").strip()
    m = load_map(); meta = load_meta()
    if key not in m:
        return jsonify({"error":"not_found"}), 404
    del m[key]
    meta["total_keys"] = max(0, meta.get("total_keys", 0) - 1)
    save_map(m); save_meta(meta)
    return jsonify({"ok": True})

@app.route("/api/links/purge", methods=["POST"])
def purge_links():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    confirm = (request.args.get("confirm") or "").strip()
    if confirm != "PURGE":
        return jsonify({"error":"confirm_required"}), 400
    save_map({}); meta = {"date": today_str(), "creates": 0, "updates": 0, "total_keys": 0}
    save_meta(meta)
    return jsonify({"ok": True})

@app.route("/api/admin/token/set", methods=["POST"])
def admin_token_set():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    if not data and request.form:
        data = request.form.to_dict()
    newt = (data.get("token") or "").strip()
    if not newt:
        return jsonify({"error":"invalid_input"}), 400
    meta = load_meta(); meta["admin_token"] = newt; save_meta(meta)
    return jsonify({"ok": True})

@app.route("/api/admin/token/rotate", methods=["POST"])
def admin_token_rotate():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    import secrets
    newt = secrets.token_urlsafe(32)
    meta = load_meta(); meta["admin_token"] = newt; save_meta(meta)
    return jsonify({"ok": True, "token": newt})

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    if not data and request.form:
        data = request.form.to_dict()
    u = (data.get("username") or "").strip()
    p = (data.get("password") or "").strip()
    # Simple password-only mode
    if p == ADMIN_LOGIN_PASSWORD:
        return jsonify({"ok": True, "token": current_token()})
    # Fallback to username + token combo
    if u != ADMIN_USER or p != current_token():
        return jsonify({"error":"invalid_credentials"}), 401
    return jsonify({"ok": True, "token": current_token()})

@app.route("/api/admin/ip/set", methods=["POST"])
def admin_ip_set():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    if not data and request.form:
        data = request.form.to_dict()
    ips = data.get("ips")
    if isinstance(ips, str):
        ips = [x.strip() for x in ips.split(",") if x.strip()]
    if not isinstance(ips, list):
        ips = []
    meta = load_meta(); meta["admin_allow_ips"] = ips; save_meta(meta)
    return jsonify({"ok": True, "ips": ips})

@app.route("/api/admin/security/status")
def admin_security_status():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    meta = load_meta()
    return jsonify({
        "admin_allow_ips": meta.get("admin_allow_ips") or [],
        "token_len": len(current_token()),
        "ip": client_ip(),
        "device_token_set": bool(meta.get("device_token"))
    })

@app.route("/api/admin/device/activate", methods=["POST"])
def admin_device_activate():
    if not admin_auth_token_only():
        return jsonify({"error":"unauthorized"}), 401
    meta = load_meta()
    if meta.get("device_token"):
        return jsonify({"error":"already_activated"}), 409
    data = request.get_json(silent=True) or {}
    if not data and request.form:
        data = request.form.to_dict()
    dtoken = (data.get("device_token") or "").strip()
    if not dtoken:
        import secrets
        dtoken = secrets.token_urlsafe(32)
    meta["device_token"] = dtoken
    save_meta(meta)
    return jsonify({"ok": True, "device_token": dtoken})

@app.route("/api/admin/device/reset", methods=["POST"])
def admin_device_reset():
    if not admin_auth_ok():
        return jsonify({"error":"unauthorized"}), 401
    meta = load_meta(); meta.pop("device_token", None); save_meta(meta)
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
