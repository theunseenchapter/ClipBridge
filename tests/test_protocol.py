from __future__ import annotations

from clipbridge.protocol import DeviceIdentity, MessageFrame, PairingChallenge, ProtocolEnvelope, ProtocolError


def test_protocol_envelope_is_valid_and_deterministic_for_text() -> None:
    env = ProtocolEnvelope.from_payload(
        origin_device_id="windows-laptop",
        origin_seq=4,
        logical_clock=4,
        content_type="text/plain",
        mime_type="text/plain; charset=utf-8",
        payload="hello",
    )

    assert env.protocol_version == 1
    assert env.content_size == 5
    assert len(env.sha256) == 64
    env.validate()


def test_message_frame_roundtrip() -> None:
    frame = MessageFrame(message_id="m-1", kind="clipboard", payload={"item_id": "abc"})
    raw = frame.encode()
    decoded = MessageFrame.decode(raw)

    assert decoded.kind == "clipboard"
    assert decoded.payload["item_id"] == "abc"


def test_pairing_challenge_expiration() -> None:
    challenge = PairingChallenge.create("windows-laptop")
    assert challenge.is_valid() is True


def test_unpaired_device_is_rejected() -> None:
    device = DeviceIdentity(device_id="unknown", public_key_fingerprint="abc", revoked=False)
    try:
        device.validate()
        assert False, "should reject invalid fingerprint"
    except ProtocolError:
        pass
