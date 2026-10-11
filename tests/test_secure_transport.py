from __future__ import annotations

import pytest

from clipbridge.protocol import ProtocolError
from clipbridge.secure_transport import SecureTransport


def test_pairing_and_authorization_flow() -> None:
    transport = SecureTransport()
    challenge = transport.request_pairing("android-1")

    assert transport.confirm_pairing(challenge.challenge_id, "android-1") is True
    transport.validate_peer("android-1")

    frame = transport.send("android-1", "clipboard", {"item_id": "abc-123"})
    assert frame.kind == "clipboard"


def test_rejected_unpaired_device() -> None:
    transport = SecureTransport()
    with pytest.raises(ProtocolError):
        transport.validate_peer("unknown-device")


def test_revoked_device_cannot_reconnect() -> None:
    transport = SecureTransport()
    challenge = transport.request_pairing("android-2")
    transport.confirm_pairing(challenge.challenge_id, "android-2")
    transport.registry.revoke("android-2")

    with pytest.raises(ProtocolError):
        transport.validate_peer("android-2")
