"""ClipBridge wire protocol v1: 4-byte big-endian length + UTF-8 JSON frames."""
from __future__ import annotations
import asyncio, hashlib, json, re, struct, time, uuid
from typing import Any

VERSION = 1
MAX_FRAME = 32 * 1024 * 1024
KINDS = {"text", "url", "html", "image", "file"}
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_URL = re.compile(r"^https?://\S+$", re.I)
WIRE_FIELDS = ("id", "origin", "seq", "lamport", "created", "kind", "mime", "size", "sha256", "text")


class ProtocolError(Exception):
    pass


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def classify(text: str) -> tuple[str, str]:
    return ("url", "text/uri-list") if _URL.match(text.strip()) else ("text", "text/plain")


def make_item(origin: str, seq: int, lamport: int, text: str) -> dict[str, Any]:
    data = text.encode("utf-8")
    kind, mime = classify(text)
    return {"v": VERSION, "id": str(uuid.uuid4()), "origin": origin, "seq": seq, "lamport": lamport,
            "created": time.time(), "kind": kind, "mime": mime, "size": len(data),
            "sha256": sha256_hex(data), "text": text}


def wire_item(row: dict[str, Any]) -> dict[str, Any]:
    d = {k: row[k] for k in WIRE_FIELDS}
    d["v"] = VERSION
    return d


def validate_item(d: Any, max_bytes: int) -> dict[str, Any]:
    if not isinstance(d, dict) or d.get("v") != VERSION:
        raise ProtocolError("bad version")
    if not isinstance(d.get("id"), str) or not _UUID.match(d["id"]):
        raise ProtocolError("bad id")
    if not isinstance(d.get("origin"), str) or not _UUID.match(d["origin"]):
        raise ProtocolError("bad origin")
    for k in ("seq", "lamport", "size"):
        if not isinstance(d.get(k), int) or isinstance(d.get(k), bool) or d[k] < 0:
            raise ProtocolError(f"bad {k}")
    if not isinstance(d.get("created"), (int, float)):
        raise ProtocolError("bad created")
    if d.get("kind") not in KINDS or not isinstance(d.get("mime"), str) or len(d["mime"]) > 100:
        raise ProtocolError("bad kind/mime")
    if d["size"] > max_bytes:
        raise ProtocolError("too large")
    if d["kind"] in ("text", "url", "html"):
        t = d.get("text")
        if not isinstance(t, str):
            raise ProtocolError("missing text")
        raw = t.encode("utf-8")
        if len(raw) != d["size"] or sha256_hex(raw) != d.get("sha256"):
            raise ProtocolError("integrity check failed")
    return {k: d.get(k) for k in WIRE_FIELDS}


def order_key(item: dict[str, Any]) -> tuple[int, str]:
    """Total order independent of wall clocks: (Lamport counter, origin device id)."""
    return (int(item["lamport"]), str(item["origin"]))


async def read_frame(r: asyncio.StreamReader) -> dict[str, Any]:
    (n,) = struct.unpack(">I", await r.readexactly(4))
    if n < 2 or n > MAX_FRAME:
        raise ProtocolError("bad frame length")
    obj = json.loads((await r.readexactly(n)).decode("utf-8"))
    if not isinstance(obj, dict) or not isinstance(obj.get("t"), str):
        raise ProtocolError("bad frame")
    return obj


async def write_frame(w: asyncio.StreamWriter, obj: dict[str, Any]) -> None:
    b = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    w.write(struct.pack(">I", len(b)) + b)
    await w.drain()
