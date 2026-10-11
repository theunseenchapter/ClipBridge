from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import hashlib
import json
import uuid


@dataclass
class ClipboardItem:
    """Immutable clipboard payload with version metadata."""

    item_id: str
    origin_device_id: str
    origin_seq: int
    logical_clock: int
    created_at: str
    content_type: str
    mime_type: str
    content_size: int
    sha256: str
    transfer_id: Optional[str] = None
    payload: Optional[str] = None
    protocol_version: int = 1
    source: str = "local"
    internal_generated: bool = False

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        device_id: str,
        sequence: int,
        logical_clock: int,
        source: str = "local",
        internal_generated: bool = False,
    ) -> "ClipboardItem":
        content = text.encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        return cls(
            item_id=str(uuid.uuid4()),
            origin_device_id=device_id,
            origin_seq=sequence,
            logical_clock=logical_clock,
            created_at=datetime.now(timezone.utc).isoformat(),
            content_type="text/plain",
            mime_type="text/plain; charset=utf-8",
            content_size=len(content),
            sha256=digest,
            transfer_id=None,
            payload=text,
            source=source,
            internal_generated=internal_generated,
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "protocol_version": self.protocol_version,
            "item_id": self.item_id,
            "origin_device_id": self.origin_device_id,
            "origin_seq": self.origin_seq,
            "logical_clock": self.logical_clock,
            "created_at": self.created_at,
            "content_type": self.content_type,
            "mime_type": self.mime_type,
            "content_size": self.content_size,
            "sha256": self.sha256,
            "transfer_id": self.transfer_id,
            "payload": self.payload,
            "source": self.source,
            "internal_generated": self.internal_generated,
        }
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClipboardItem":
        return cls(
            protocol_version=int(data.get("protocol_version", 1)),
            item_id=str(data["item_id"]),
            origin_device_id=str(data["origin_device_id"]),
            origin_seq=int(data["origin_seq"]),
            logical_clock=int(data["logical_clock"]),
            created_at=str(data["created_at"]),
            content_type=str(data["content_type"]),
            mime_type=str(data["mime_type"]),
            content_size=int(data["content_size"]),
            sha256=str(data["sha256"]),
            transfer_id=data.get("transfer_id"),
            payload=data.get("payload"),
            source=data.get("source", "remote"),
            internal_generated=bool(data.get("internal_generated", False)),
        )

    def validate(self) -> None:
        if len(self.sha256) != 64:
            raise ValueError("Invalid SHA-256 hash length")
        if self.content_size < 0:
            raise ValueError("Content size cannot be negative")
        if self.content_size != 0 and self.payload is None:
            raise ValueError("Payload must be present when content has bytes")


@dataclass
class ClipboardEvent:
    item: ClipboardItem
    change_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_id": self.change_id,
            "observed_at": self.observed_at,
            "item": self.item.to_dict(),
        }
