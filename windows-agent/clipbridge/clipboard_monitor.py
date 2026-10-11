from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from clipbridge.clipboard_types import ClipboardEvent, ClipboardItem


@dataclass
class ClipboardMonitor:
    """Abstract clipboard monitor that emits a changed item when the Win32 sequence changes."""

    device_id: str
    sequence: int = 0
    on_change: Optional[Callable[[ClipboardEvent], None]] = None

    def set_on_change(self, callback: Callable[[ClipboardEvent], None]) -> None:
        self.on_change = callback

    def read_current_text(self) -> str:
        return ""

    def get_sequence(self) -> int:
        return self.sequence

    def observe(self) -> Optional[ClipboardEvent]:
        current_text = self.read_current_text()
        if not current_text:
            return None
        item = ClipboardItem.from_text(
            current_text,
            device_id=self.device_id,
            sequence=self.sequence + 1,
            logical_clock=self.sequence + 1,
        )
        event = ClipboardEvent(item=item)
        self.sequence = item.origin_seq
        if self.on_change is not None:
            self.on_change(event)
        return event

    def emit_local_copy(self, text: str) -> ClipboardEvent:
        item = ClipboardItem.from_text(
            text,
            device_id=self.device_id,
            sequence=self.sequence + 1,
            logical_clock=self.sequence + 1,
            source="local",
            internal_generated=False,
        )
        self.sequence = item.origin_seq
        event = ClipboardEvent(item=item)
        if self.on_change is not None:
            self.on_change(event)
        return event
