from __future__ import annotations
import asyncio, base64, ipaddress, logging, os, re, secrets, threading
from typing import Callable

from . import protocol as P
from .config import PORT, Settings
from .history import History
from .security import DeviceStore, Identity, PairingManager, mac

log = logging.getLogger("clipbridge.sync")
_UUID = re.compile(P._UUID.pattern)


class SyncEngine:
    def __init__(self, settings: Settings, hist: History, devices: DeviceStore, pairing: PairingManager,
                 identity: Identity, write_clip: Callable[[str], bool],
                 notify: Callable[[str, str], None], on_status: Callable[[int], None],
                 confirm_pair: Callable[[str], bool]) -> None:
        self.s, self.h, self.devices, self.pairing, self.identity = settings, hist, devices, pairing, identity
        self.write_clip, self.notify, self.on_status, self.confirm_pair = write_clip, notify, on_status, confirm_pair
        self.peers: dict[str, asyncio.StreamWriter] = {}
        self.loop: asyncio.AbstractEventLoop | None = None
        self.lock = threading.Lock()

    # ---------------- local copy ----------------
    def excluded(self, text: str) -> bool:
        for p in self.s.exclude_patterns:
            try:
                if re.search(p, text, re.M):
                    return True
            except re.error:
                continue
        return False

    def on_local_copy(self, text: str) -> None:
        if self.s.paused or self.excluded(text):
            return
        if len(text.encode("utf-8")) > self.s.max_item_bytes:
            log.warning("item exceeds size limit; not synced")
            return
        with self.lock:
            seq = int(self.h.kv("seq", 0)) + 1
            lam = int(self.h.kv("lamport", 0)) + 1
            self.h.kv_set("seq", seq)
            self.h.kv_set("lamport", lam)
            item = P.make_item(self.s.device_id, seq, lam, text)
            self.h.add(item, "local", "local")
            self.h.kv_set("active", [item["lamport"], item["origin"], item["id"]])
            for d in self.devices.active_ids():
                self.h.outbox_add(item["id"], d)
            self.h.prune(self.s.retention)
        self._schedule(self._push_all())

    def restore(self, item_id: str) -> bool:
        """Copy Again: puts the stored item on the clipboard, same ID, not rebroadcast."""
        row = self.h.get(item_id)
        return bool(row and row["text"] is not None and self.write_clip(row["text"]))

    def _schedule(self, coro) -> None:
        if self.loop:
            asyncio.run_coroutine_threadsafe(coro, self.loop)

    # ---------------- outbound ----------------
    async def _flush(self, dev: str, w: asyncio.StreamWriter) -> None:
        rows = self.h.outbox_items(dev)
        if not rows:
            return
        rows.sort(key=P.order_key, reverse=True)
        for r in rows[1:]:  # never let an older queued item follow/overwrite a newer one
            self.h.outbox_remove(r["id"], dev)
            self.h.set_status(r["id"], "superseded")
        await P.write_frame(w, {"t": "clip", "item": P.wire_item(rows[0])})

    async def _push_all(self) -> None:
        for dev, w in list(self.peers.items()):
            try:
                await self._flush(dev, w)
            except Exception:
                log.info("push failed; item stays queued")

    # ---------------- inbound ----------------
    async def _on_remote(self, item_raw: dict, dev: str, w: asyncio.StreamWriter) -> None:
        try:
            item = P.validate_item(item_raw, self.s.max_item_bytes)
        except P.ProtocolError as e:
            log.warning("rejected item: %s", e)
            await P.write_frame(w, {"t": "ack", "id": str(item_raw.get("id", ""))[:40], "status": "rejected"})
            return
        if item["origin"] != dev:
            await P.write_frame(w, {"t": "ack", "id": item["id"], "status": "rejected"})
            return
        if self.h.has(item["id"]):  # duplicate delivery
            await P.write_frame(w, {"t": "ack", "id": item["id"], "status": "duplicate"})
            return
        last = int(self.h.kv(f"lastseq:{dev}", 0))
        if item["seq"] <= last:  # replay / reordering of an old sequence number
            await P.write_frame(w, {"t": "ack", "id": item["id"], "status": "replay"})
            return
        self.h.kv_set(f"lastseq:{dev}", item["seq"])
        if item["kind"] not in ("text", "url"):
            self.h.add(item, "remote", "unsupported", dev)
            await P.write_frame(w, {"t": "ack", "id": item["id"], "status": "unsupported"})
            return
        if self.s.paused:
            self.h.add(item, "remote", "paused", dev)
            await P.write_frame(w, {"t": "ack", "id": item["id"], "status": "paused"})
            return
        with self.lock:
            self.h.kv_set("lamport", max(int(self.h.kv("lamport", 0)), item["lamport"]))
            act = self.h.kv("active", [0, ""])
            newer = P.order_key(item) > (int(act[0]), str(act[1]))
            status = "stale"
            if newer:
                ok = await asyncio.get_running_loop().run_in_executor(None, self.write_clip, item["text"])
                status = "applied" if ok else "write_failed"
                if ok:
                    self.h.kv_set("active", [item["lamport"], item["origin"], item["id"]])
            self.h.add(item, "remote", status, dev)
            self.h.prune(self.s.retention)
        await P.write_frame(w, {"t": "ack", "id": item["id"], "status": status})
        if status == "applied":
            self.notify("Copied from your phone", "Link" if item["kind"] == "url" else "Text")

    # ---------------- server ----------------
    async def serve(self) -> None:
        self.loop = asyncio.get_running_loop()
        server = await asyncio.start_server(self._handle, "0.0.0.0", PORT, ssl=self.identity.server_context())
        log.info("listening on %d", PORT)
        async with server:
            await server.serve_forever()

    async def _authenticate(self, msg: dict, nonce: bytes, w: asyncio.StreamWriter) -> str | None:
        dev, name = msg.get("device_id"), str(msg.get("name", ""))[:64]
        if not isinstance(dev, str) or not _UUID.match(dev):
            return None
        if msg.get("t") == "hello":
            secret = self.devices.secret(dev)
            import hmac as _h
            if secret and isinstance(msg.get("mac"), str) and _h.compare_digest(msg["mac"], mac(secret, nonce, dev)):
                await P.write_frame(w, {"t": "ready", "v": P.VERSION, "device_id": self.s.device_id,
                                        "name": self.s.device_name})
                return dev
            await P.write_frame(w, {"t": "error", "code": "unauthorized"})
            return None
        if msg.get("t") == "pair":
            tok = msg.get("token")
            if not isinstance(tok, str) or not self.pairing.consume(tok):
                await P.write_frame(w, {"t": "error", "code": "bad_token"})
                return None
            ok = await asyncio.get_running_loop().run_in_executor(None, self.confirm_pair, name or "Unknown device")
            if not ok:
                await P.write_frame(w, {"t": "error", "code": "denied"})
                return None
            secret = secrets.token_bytes(32)
            self.devices.add(dev, name or "phone", secret)
            await P.write_frame(w, {"t": "pair_ok", "secret": base64.b64encode(secret).decode(),
                                    "device_id": self.s.device_id, "name": self.s.device_name})
            return dev
        return None

    async def _handle(self, r: asyncio.StreamReader, w: asyncio.StreamWriter) -> None:
        dev: str | None = None
        try:
            ip = str(w.get_extra_info("peername")[0]).split("%")[0]
            if not ipaddress.ip_address(ip).is_private:
                return  # local network only
            nonce = os.urandom(16)
            await P.write_frame(w, {"t": "challenge", "v": P.VERSION, "nonce": nonce.hex()})
            first = await asyncio.wait_for(P.read_frame(r), 10)
            dev = await self._authenticate(first, nonce, w)
            if not dev:
                await asyncio.sleep(1)
                return
            old = self.peers.get(dev)
            if old:
                old.close()
            self.peers[dev] = w
            self.on_status(len(self.peers))
            await self._flush(dev, w)
            while True:
                m = await asyncio.wait_for(P.read_frame(r), 60)
                t = m["t"]
                if t == "clip":
                    await self._on_remote(m.get("item"), dev, w)
                elif t == "ack":
                    iid = str(m.get("id", ""))
                    self.h.outbox_remove(iid, dev)
                    if self.h.has(iid):
                        self.h.set_status(iid, str(m.get("status", "delivered")) if m.get("status") != "applied" else "delivered")
                elif t == "ping":
                    await P.write_frame(w, {"t": "pong"})
                if self.devices.secret(dev) is None:  # revoked mid-session
                    return
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, P.ProtocolError, ValueError, OSError):
            pass
        except Exception:
            log.exception("connection handler error")
        finally:
            if dev and self.peers.get(dev) is w:
                del self.peers[dev]
                self.on_status(len(self.peers))
            try:
                w.close()
            except Exception:
                pass

    def revoke(self, dev: str) -> None:
        self.devices.revoke(dev)
        writer = self.peers.pop(dev, None)
        if writer:
            writer.close()
        self.on_status(len(self.peers))
        w = self.peers.get(dev)
        if w and self.loop:
            self.loop.call_soon_threadsafe(w.close)
