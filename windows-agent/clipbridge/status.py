from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class StatusEntry:
    label: str
    detail: str
    severity: str = "info"


@dataclass
class StatusManager:
    """Simple status manager that can be surfaced through a tray or notifications."""

    status: str = "idle"
    connected_devices: List[str] = field(default_factory=list)
    messages: List[StatusEntry] = field(default_factory=list)

    def set_status(self, status: str, detail: Optional[str] = None) -> None:
        self.status = status
        if detail is not None:
            self.messages.append(StatusEntry(label=status, detail=detail, severity="info"))

    def add_notification(self, message: str, *, severity: str = "info") -> None:
        self.messages.append(StatusEntry(label="notification", detail=message, severity=severity))

    def clear_messages(self) -> None:
        self.messages.clear()

    def snapshot(self) -> dict:
        return {
            "status": self.status,
            "connected_devices": list(self.connected_devices),
            "messages": [entry.__dict__ for entry in self.messages],
        }
