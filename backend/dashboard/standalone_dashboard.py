#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone lightweight dashboard for TG Archive.

Reads status files from backend and serves a single-page HTML dashboard.
Alternative to the full React frontend for headless/minimal deployments.

Usage:
    python standalone_dashboard.py [--port 6186] [--status-dir /path/to/status]
"""
import argparse
import json
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_PORT = 6186
STALLED_SEC = 900
RATE_WINDOW = 15
EVENTS_TAIL = 80

_lock = threading.Lock()
_rate_state = {}


def read_json(p):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def parse_status_epoch(s):
    import datetime
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except Exception:
        return 0


def classify_phase(phase):
    p = phase or ""
    if "下载" in p or "download" in p.lower() or "续传" in p:
        return "📥", "下载中"
    if "上传" in p or "upload" in p.lower():
        return "📤", "上传中"
    if "校验" in p or "verify" in p.lower():
        return "🔍", "校验中"
    if "缓存" in p:
        return "⏳", "缓存中"
    if "完成" in p or "completed" in p.lower():
        return "✅", "已完成"
    if "失败" in p or "error" in p.lower():
        return "❌", "出错"
    if "准备" in p:
        return "🔧", "准备中"
    return "🔄", (p[:10] or "处理中")


def service_pid(unit):
    try:
        r = subprocess.run(
            ["systemctl", "show", "-p", "MainPID", "--value", unit],
            capture_output=True, text=True, timeout=3)
        pid = int(r.stdout.strip() or 0)
        return pid or None
    except Exception:
        return None


def compute_rate(ch_id, run_bytes):
    now = time.time()
    with _lock:
        prev = _rate_state.get(ch_id)
        if prev is None:
            _rate_state[ch_id] = {"t": now, "rb": run_bytes, "rate": 0.0}
            return 0.0
        dt = now - prev["t"]
        if dt < RATE_WINDOW:
            return prev["rate"]
        if run_bytes >= prev["rb"] and dt > 0:
            rate = (run_bytes - prev["rb"]) / dt
        else:
            rate = 0.0
        _rate_state[ch_id] = {"t": now, "rb": run_bytes, "rate": rate}
        return rate


def channel_payload(ch, status_dir, log_root, now):
    status_file = status_dir / f"tg-archive-status-{ch['id']}.json"
    st = read_json(status_file)
    if not isinstance(st, dict) or not st:
        return {
            "id": ch["id"], "name": ch["name"], "tag": ch["tag"],
            "state": "missing", "phase_icon": "⚪", "phase_label": "数据缺失",
            "pid": service_pid(ch["unit"]), "rate_bps": 0.0,
            "stalled": False, "error": None, "updated_age": None,
        }
    state = st.get("state") or "unknown"
    icon, label = classify_phase(st.get("transfer_phase") or st.get("phase") or "")
    epoch = parse_status_epoch(st.get("updated_at") or "")
    age = int(now - epoch) if epoch else None
    pid = service_pid(ch["unit"])
    rate = compute_rate(ch["id"], st.get("run_transfer_bytes") or 0)
    stalled = (state == "running" and age is not None and age > STALLED_SEC)
    
    finished_epoch = parse_status_epoch(st.get("finished_at") or "") if st.get("finished_at") else None
    
    return {
        "id": ch["id"], "name": ch["name"], "tag": ch["tag"],
        "state": state,
        "phase_icon": icon, "phase_label": label,
        "phase_raw": st.get("transfer_phase") or st.get("phase") or "",
        "messages_done": st.get("messages_done") or 0,
        "messages_total": st.get("messages_total") or 0,
        "media_uploaded": st.get("media_uploaded") or 0,
        "media_total": st.get("media_total") or 0,
        "media_total_bytes": st.get("media_total_bytes") or 0,
        "current_message": st.get("current_message"),
        "current_group": st.get("current_group"),
        "groups_total": st.get("groups_total") or 0,
        "current_file": st.get("current_file") or "",
        "current_bytes": st.get("current_bytes") or 0,
        "current_total": st.get("current_total") or 0,
        "run_transfer_bytes": st.get("run_transfer_bytes") or 0,
        "bytes_uploaded": st.get("bytes_uploaded") or 0,
        "finished_at_epoch": finished_epoch,
        "rate_bps": round(rate, 1),
        "pid": pid,
        "stalled": stalled,
        "error": st.get("error"),
        "updated_age": age,
        "updated_at_epoch": epoch or None,
    }


def build_status(channels, status_dir, log_root):
    now = time.time()
    chans = [channel_payload(ch, status_dir, log_root, now) for ch in channels]

    u = shutil.disk_usage(str(status_dir.parent))
    disk = {
        "path": str(status_dir.parent),
        "pct": round(u.used / u.total * 100, 1),
        "used": u.used,
        "total": u.total,
    }

    events = {}
    for ch in channels:
        log_file = log_root / f"tg-archive-{ch['id']}" / "log.json"
        data = read_json(log_file)
        lst = data[-EVENTS_TAIL:] if isinstance(data, list) else []
        out = []
        for e in lst:
            if not isinstance(e, dict):
                continue
            out.append({
                "t": e.get("t") or "",
                "ts": 0,  # Simplified for standalone
                "m": e.get("m") or "",
            })
        events[ch["id"]] = out

    return {"ts": now, "disk": disk, "channels": chans, "events": events}


class Handler(BaseHTTPRequestHandler):
    server_version = "tg-dash-standalone/1.0"
    channels = []
    status_dir = Path("/home/hermes")
    log_root = Path("/data")

    def log_message(self, format: str, *args) -> None:
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/", "/index.html"):
                html_path = Path(__file__).parent / "dashboard.html"
                if not html_path.exists():
                    self._send(500, "dashboard.html missing", "text/plain; charset=utf-8")
                    return
                html = html_path.read_text(encoding="utf-8")
                self._send(200, html, "text/html; charset=utf-8")
            elif path == "/api/status":
                status = build_status(self.channels, self.status_dir, self.log_root)
                self._send(200, json.dumps(status, ensure_ascii=False),
                           "application/json; charset=utf-8")
            elif path == "/healthz":
                self._send(200, "ok", "text/plain; charset=utf-8")
            else:
                self._send(404, "not found", "text/plain; charset=utf-8")
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    parser = argparse.ArgumentParser(description="TG Archive standalone dashboard")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--status-dir", type=Path, default=Path("/home/hermes"))
    parser.add_argument("--log-root", type=Path, default=Path("/data"))
    parser.add_argument("--channels", type=str, required=True,
                        help="JSON array of channel configs: [{id, name, tag, unit}, ...]")
    args = parser.parse_args()

    channels = json.loads(args.channels)
    Handler.channels = channels
    Handler.status_dir = args.status_dir
    Handler.log_root = args.log_root

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"TG Archive dashboard listening on 127.0.0.1:{args.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
