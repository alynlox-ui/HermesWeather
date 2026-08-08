import json
import subprocess
import sys
import time
import urllib.request

API = "https://api.render.com/v1"
API_IP = "216.24.57.7"
CLIENT_ID = "429024F5E608930E2A65EF92591A25CC"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
SERVICE_NAME = "hermes-weather-news-alynlox-ui"
PUBLIC_URL = "https://hermes-weather-news-alynlox-ui.onrender.com/"


def api(method, path, body=None, token=None):
    cmd = [
        "curl", "-4", "-sS", "--fail-with-body",
        "--resolve", f"api.render.com:443:{API_IP}",
        "--connect-timeout", "10", "--max-time", "45",
        "-X", method,
    ]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "--data", json.dumps(body, separators=(",", ":"))]
    if token:
        cmd += ["-H", f"Authorization: Bearer {token}"]
    cmd.append(API + path)
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.returncode, result.stdout, result.stderr


def main():
    rc, out, err = api("POST", "/device-grant", {"client_id": CLIENT_ID})
    if rc != 0:
        print("DEVICE_GRANT_FAILED", out or err, flush=True)
        return 1
    grant = json.loads(out)
    device_code = grant["device_code"]
    verify_url = grant["verification_uri_complete"]
    print("AUTH_URL", verify_url, flush=True)
    try:
        subprocess.Popen([EDGE, verify_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
    deadline = time.time() + 590
    token = None
    while time.time() < deadline:
        rc, out, err = api("POST", "/device-token", {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": CLIENT_ID,
            "device_code": device_code,
        })
        try:
            data = json.loads(out)
        except Exception:
            data = {}
        if rc == 0 and data.get("access_token"):
            token = data["access_token"]
            print("AUTH_OK", flush=True)
            break
        if data.get("error") not in ("authorization_pending", "slow_down", None):
            print("AUTH_FAILED", data.get("error", out or err), flush=True)
            return 2
        time.sleep(3)
    if not token:
        print("AUTH_TIMEOUT", flush=True)
        return 3

    rc, out, err = api("GET", "/services?limit=100", token=token)
    if rc != 0:
        print("SERVICE_LIST_FAILED", out or err, flush=True)
        return 4
    rows = json.loads(out)
    service = None
    for row in rows:
        candidate = row.get("service", row)
        if candidate.get("name") == SERVICE_NAME:
            service = candidate
            break
    if not service:
        print("SERVICE_NOT_FOUND", SERVICE_NAME, flush=True)
        return 5
    service_id = service["id"]
    print("SERVICE_FOUND", service_id, SERVICE_NAME, flush=True)

    rc, out, err = api("POST", f"/services/{service_id}/deploys", {"clearCache": "do_not_clear"}, token)
    if rc != 0:
        print("DEPLOY_CREATE_FAILED", out or err, flush=True)
        return 6
    deploy = json.loads(out)
    deploy_id = deploy["id"]
    print("DEPLOY_CREATED", deploy_id, flush=True)

    terminal = {"live", "deactivated", "build_failed", "update_failed", "canceled", "pre_deploy_failed"}
    deadline = time.time() + 900
    status = deploy.get("status", "")
    while time.time() < deadline:
        rc, out, err = api("GET", f"/services/{service_id}/deploys/{deploy_id}", token=token)
        if rc == 0:
            deploy = json.loads(out)
            next_status = deploy.get("status", "")
            if next_status != status:
                status = next_status
                print("DEPLOY_STATUS", status, flush=True)
            if status in terminal:
                break
        time.sleep(10)
    if status != "live":
        print("DEPLOY_FAILED", status, flush=True)
        return 7

    req = urllib.request.Request(PUBLIC_URL + "?public_verify=" + str(time.time()), headers={"User-Agent": "Mozilla/5.0 MicroMessenger/8.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        body = resp.read()
        drawer = all(marker in body for marker in (
            b'id="dockToggle"', b'id="dockBackdrop"', b'data-view="sites"',
            b'id="sitesView"', b'transform:translateX(-105%)', b'body.dock-open .sidebar',
            b'.shell{z-index:auto;display:block', b'pointer-events:none;transition:.25s', b'id="siteSearch"', b'SITE_EXTRA_SOFTWARE', b'function siteMatchScore(',
        ))
        sites_expanded = body.count(b"{cat:") == 159 and all(marker in body for marker in (
            b"name:'Playnite'", b"name:'Heroic Games Launcher'", b"name:'Anytype'", b"name:'Zed'",
            b"name:'Penpot'", b"name:'Jellyfin'", b"name:'EarTrumpet'",
            b"assets/site-icons/playnite.png", b"assets/site-icons/eartrumpet.png",
        ))
        settings_clean = b'id="autoSearch"' not in body and b'id="defaultPlace"' not in body
        print("PUBLIC_ROOT", resp.status, len(body), "VERSION", b"1.16.0-official-icons" in body, "STUDY", b"study-nav-icon" in body, "LEFT_DRAWER", drawer, "SITES_EXPANDED", sites_expanded, "SETTINGS_CLEAN", settings_clean, flush=True)
        if b"1.16.0-official-icons" not in body or b"study-nav-icon" not in body or not drawer or not sites_expanded or not settings_clean:
            print("PUBLIC_VERSION_MISMATCH", flush=True)
            return 8
    with urllib.request.urlopen(PUBLIC_URL + "study-goal-tracker.html?public_verify=" + str(time.time()), timeout=90) as resp:
        study = resp.read()
        tabs = b".page-title{display:none}" in study and b".topbar-nav{display:flex;gap:8px;width:100%" in study
        compact_icons = b".weekly-four-item .form-label svg{width:14px;height:14px;flex:0 0 14px}" in study
        print("PUBLIC_STUDY", resp.status, len(study), "STORAGE", b"wb_study_goal_tracker_data" in study, "NO_EXAMPLES", b"id:'ex-1'" not in study, "DARK_UI", b"--bg:#080a0d" in study, "WEATHER_STYLE_TABS", tabs, "COMPACT_WEEKLY_ICONS", compact_icons, flush=True)
        if b"wb_study_goal_tracker_data" not in study or b"id:'ex-1'" in study or b"--bg:#080a0d" not in study or not tabs or not compact_icons:
            return 10
    with urllib.request.urlopen(PUBLIC_URL + "health?public_verify=" + str(time.time()), timeout=90) as resp:
        health = json.loads(resp.read())
        revision = health.get("crawlerRevision")
        print("PUBLIC_HEALTH", resp.status, revision, flush=True)
        if revision != "web-1.15.0-niche-sites-icons":
            return 11
    with urllib.request.urlopen(PUBLIC_URL + "hot-news.json?public_verify=" + str(time.time()), timeout=90) as resp:
        snapshot = resp.read()
        payload = json.loads(snapshot)
        keys = list(payload.get("sources", {}))
        print("PUBLIC_HOT_NEWS", resp.status, len(snapshot), "SOURCES", keys, flush=True)
        if set(keys) != {"thepaper", "bilibili", "qbitai", "36kr"}:
            print("PUBLIC_SOURCE_MISMATCH", keys, flush=True)
            return 9
    return 0


if __name__ == "__main__":
    sys.exit(main())
