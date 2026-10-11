from __future__ import annotations

import json
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse


class ControlApi:
    """Loopback-only API and browser dashboard for the Windows agent."""

    def __init__(self, engine_getter: Callable, settings, history, show_pair: Callable[[], None],
                 show_history: Callable[[], None]) -> None:
        self.engine_getter = engine_getter
        self.settings = settings
        self.history = history
        self.show_pair = show_pair
        self.show_history = show_history
        self.server: ThreadingHTTPServer | None = None

    def start(self) -> None:
        api = self
        dashboard = Path(__file__).with_name("web")

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args) -> None:
                return

            def _send(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _send_file(self, path: Path, content_type: str) -> None:
                try:
                    body = path.read_bytes()
                except OSError:
                    self._send(404, {"error": "not_found"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                route = parsed.path
                if route in ("/", "/dashboard", "/dashboard/"):
                    self._send_file(dashboard / "index.html", "text/html; charset=utf-8")
                    return
                if route == "/dashboard/app.js":
                    self._send_file(dashboard / "app.js", "text/javascript; charset=utf-8")
                    return
                if route == "/dashboard/styles.css":
                    self._send_file(dashboard / "styles.css", "text/css; charset=utf-8")
                    return
                engine = api.engine_getter()
                if route == "/api/history":
                    query = parse_qs(parsed.query).get("q", [""])[0][:200]
                    rows = api.history.search(query, limit=50)
                    items = [{
                        "id": row["id"],
                        "text": row["text"] or f"{row['kind']} item",
                        "kind": row["kind"],
                        "created": row["created"],
                        "direction": row["direction"],
                        "pinned": bool(row["pinned"]),
                        "source": (api.settings.device_name if row["origin"] == api.settings.device_id
                                   else engine.devices.name(row["origin"])),
                    } for row in rows]
                    self._send(200, {"items": items})
                    return
                if route != "/api/state":
                    self._send(404, {"error": "not_found"})
                    return
                devices = [
                    {"id": d, "name": engine.devices.name(d), "connected": d in engine.peers}
                    for d in engine.devices.active_ids()
                ]
                self._send(200, {
                    "paused": api.settings.paused,
                    "devices": devices,
                    "connected": len(engine.peers),
                })

            def do_POST(self) -> None:
                engine = api.engine_getter()
                if self.path == "/api/pair":
                    api.show_pair()
                    self._send(202, {"ok": True})
                    return
                if self.path == "/api/history":
                    api.show_history()
                    self._send(202, {"ok": True})
                    return
                if self.path in ("/api/restore", "/api/pin", "/api/delete"):
                    raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
                    try:
                        item_id = json.loads(raw or b"{}").get("item_id")
                    except (TypeError, ValueError):
                        self._send(400, {"error": "invalid_json"})
                        return
                    if not item_id:
                        self._send(400, {"error": "missing_item_id"})
                        return
                    if self.path == "/api/restore":
                        ok = engine.restore(item_id)
                    elif self.path == "/api/pin":
                        row = api.history.get(item_id)
                        if not row:
                            self._send(404, {"error": "not_found"})
                            return
                        api.history.set_pinned(item_id, not bool(row["pinned"]))
                        ok = True
                    else:
                        api.history.delete(item_id)
                        ok = True
                    self._send(200, {"ok": ok})
                    return
                if self.path == "/api/pause":
                    api.settings.paused = not api.settings.paused
                    api.settings.save()
                    self._send(200, {"paused": api.settings.paused})
                    return
                if self.path == "/api/disconnect":
                    raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
                    try:
                        requested = json.loads(raw or b"{}").get("device_id")
                    except (TypeError, ValueError):
                        self._send(400, {"error": "invalid_json"})
                        return
                    targets = [requested] if requested else engine.devices.active_ids()
                    for device_id in targets:
                        if device_id in engine.devices.active_ids():
                            engine.revoke(device_id)
                    self._send(200, {"ok": True})
                    return
                self._send(404, {"error": "not_found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 48501), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True, name="control-api").start()

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
