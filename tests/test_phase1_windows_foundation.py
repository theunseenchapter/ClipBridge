from __future__ import annotations

from clipbridge.clipboard_types import ClipboardItem
from clipbridge.clipboard_monitor import ClipboardMonitor
from clipbridge.history import ClipboardHistory
from clipbridge.status import StatusManager


def test_clipboard_item_hash_and_validation() -> None:
    item = ClipboardItem.from_text(
        "hello from ClipBridge",
        device_id="win-01",
        sequence=7,
        logical_clock=7,
    )

    assert item.protocol_version == 1
    assert item.origin_device_id == "win-01"
    assert item.content_type == "text/plain"
    assert len(item.sha256) == 64
    assert item.content_size == len("hello from ClipBridge".encode("utf-8"))

    item.validate()


def test_history_roundtrip_and_search() -> None:
    history = ClipboardHistory(db_path="D:/ClipBridge/tests/.tmp_history.db", retention_limit=5)
    try:
        item = ClipboardItem.from_text(
            "searchable text",
            device_id="android-01",
            sequence=1,
            logical_clock=1,
            source="remote",
        )
        history.add_item(item)

        recent = history.get_recent(limit=10)
        assert any(x.item_id == item.item_id for x in recent)

        search = history.search("searchable", limit=10)
        assert any(x.item_id == item.item_id for x in search)

        history.pin_item(item.item_id)
        history.delete_item(item.item_id)
        assert all(x.item_id != item.item_id for x in history.get_recent(limit=10))
    finally:
        history.close()


def test_status_manager_snapshot() -> None:
    manager = StatusManager(status="connected", connected_devices=["win-01"])
    manager.add_notification("Copied from your phone", severity="info")

    snapshot = manager.snapshot()
    assert snapshot["status"] == "connected"
    assert snapshot["connected_devices"] == ["win-01"]
    assert snapshot["messages"][-1]["detail"] == "Copied from your phone"


def test_monitor_emits_event_for_local_copy() -> None:
    monitor = ClipboardMonitor(device_id="win-01", sequence=10)
    seen = []

    def on_change(event):
        seen.append(event.item.payload)

    monitor.set_on_change(on_change)
    event = monitor.emit_local_copy("remote content")

    assert event.item.origin_seq == 11
    assert seen == ["remote content"]
    assert monitor.get_sequence() == 11
