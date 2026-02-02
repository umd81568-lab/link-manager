import argparse
import json
import sys
import requests

def post_form(url, headers=None, data=None):
    try:
        r = requests.post(url, headers=headers or {}, data=data or {}, timeout=15)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text}
    except Exception as e:
        return 0, {"error": str(e)}

def get(url, headers=None, params=None):
    try:
        r = requests.get(url, headers=headers or {}, params=params or {}, timeout=15)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text}
    except Exception as e:
        return 0, {"error": str(e)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("action")
    p.add_argument("--base", default="http://127.0.0.1:5002")
    p.add_argument("--password", default="")
    p.add_argument("--token", default="")
    p.add_argument("--key", default="")
    p.add_argument("--url", dest="link_url", default="")
    p.add_argument("--mode", default="redirect")
    p.add_argument("--status", type=int, default=302)
    p.add_argument("--banner_html", default="")
    p.add_argument("--replace_pairs_json", default="")
    p.add_argument("--asset_proxy", action="store_true")
    p.add_argument("--new_token", default="")
    args = p.parse_args()

    base = args.base.rstrip("/")
    action = args.action.lower()

    if action == "login":
        status, body = post_form(base + "/api/admin/login", data={"password": args.password})
        print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
        return 0 if status == 200 and body.get("ok") else 1

    if action == "quota":
        status, body = get(base + "/api/links/quota", headers={"X-Admin-Token": args.token})
        print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
        return 0 if status == 200 else 1

    if action == "list":
        status, body = get(base + "/api/links/list", headers={"X-Admin-Token": args.token})
        print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
        return 0 if status == 200 else 1

    if action == "get":
        status, body = get(base + "/api/links/get", headers={"X-Admin-Token": args.token}, params={"key": args.key})
        print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
        return 0 if status == 200 else 1

    if action == "set":
        data = {
            "key": args.key,
            "url": args.link_url,
            "mode": args.mode,
            "status": args.status,
            "banner_html": args.banner_html,
            "asset_proxy": args.asset_proxy,
        }
        if args.replace_pairs_json:
            try:
                data["replace_pairs"] = json.loads(args.replace_pairs_json)
            except Exception:
                data["replace_pairs"] = []
        status, body = post_form(base + "/api/links/set", headers={"X-Admin-Token": args.token}, data=data)
        print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
        return 0 if status == 200 and body.get("ok") else 1

    if action == "update":
        data = {
            "key": args.key,
            "url": args.link_url,
            "mode": args.mode,
            "status": args.status,
            "banner_html": args.banner_html,
            "asset_proxy": args.asset_proxy,
        }
        if args.replace_pairs_json:
            try:
                data["replace_pairs"] = json.loads(args.replace_pairs_json)
            except Exception:
                data["replace_pairs"] = []
        status, body = post_form(base + "/api/links/update", headers={"X-Admin-Token": args.token}, data=data)
        print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
        return 0 if status == 200 and body.get("ok") else 1

    if action == "token_set":
        status, body = post_form(base + "/api/admin/token/set", headers={"X-Admin-Token": args.token}, data={"token": args.new_token})
        print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
        return 0 if status == 200 and body.get("ok") else 1

    if action == "token_rotate":
        status, body = post_form(base + "/api/admin/token/rotate", headers={"X-Admin-Token": args.token})
        print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
        return 0 if status == 200 and body.get("ok") else 1

    if action == "security_status":
        status, body = get(base + "/api/admin/security/status", headers={"X-Admin-Token": args.token})
        print(json.dumps({"status": status, "body": body}, ensure_ascii=False))
        return 0 if status == 200 else 1

    print(json.dumps({"error": "unknown_action"}))
    return 1

if __name__ == "__main__":
    sys.exit(main())

