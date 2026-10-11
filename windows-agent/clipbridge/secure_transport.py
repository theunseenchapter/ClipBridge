from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict

from clipbridge.protocol import DeviceIdentity, MessageFrame, PairingChallenge, ProtocolError


@dataclass
class DeviceRegistry:
    devices: Dict[str, DeviceIdentity] = field(default_factory=dict)

    def register(self, device: DeviceIdentity) -> None:
        device.validate()
        self.devices[device.device_id] = device

    def is_authorized(self, device_id: str) -> bool:
        device = self.devices.get(device_id)
        return device is not None and not device.revoked

    def revoke(self, device_id: str) -> None:
        if device_id in self.devices:
            self.devices[device_id] = DeviceIdentity(
                device_id=device_id,
                public_key_fingerprint=self.devices[device_id].public_key_fingerprint,
                certificate_pinned=True,
                revoked=True,
            )


@dataclass
class SecureTransport:
    registry: DeviceRegistry = field(default_factory=DeviceRegistry)
    paired_devices: Dict[str, DeviceIdentity] = field(default_factory=dict)
    pairing_challenges: Dict[str, PairingChallenge] = field(default_factory=dict)
    tls_required: bool = True

    @staticmethod
    def _fingerprint(device_id: str) -> str:
        return hashlib.sha256(f"clipbridge:{device_id}:v1".encode("utf-8")).hexdigest()

    def request_pairing(self, device_id: str) -> PairingChallenge:
        challenge = PairingChallenge.create(device_id)
        self.pairing_challenges[challenge.challenge_id] = challenge
        return challenge

    def confirm_pairing(self, challenge_id: str, device_id: str) -> bool:
        challenge = self.pairing_challenges.get(challenge_id)
        if challenge is None or challenge.device_id != device_id or not challenge.is_valid():
            raise ProtocolError("invalid or expired challenge")
        device = DeviceIdentity(
            device_id=device_id,
            public_key_fingerprint=self._fingerprint(device_id),
            certificate_pinned=True,
            revoked=False,
        )
        self.paired_devices[device_id] = device
        self.registry.register(device)
        return True

    def validate_peer(self, device_id: str) -> None:
        if not self.registry.is_authorized(device_id):
            raise ProtocolError("unpaired or revoked device")

    def send(self, device_id: str, kind: str, payload: Dict[str, object]) -> MessageFrame:
        self.validate_peer(device_id)
        frame = MessageFrame(message_id=f"msg-{device_id}-{len(payload)}", kind=kind, payload=payload)
        return frame

    def health_check(self, device_id: str) -> Dict[str, object]:
        self.validate_peer(device_id)
        return {"status": "ok", "device_id": device_id, "tls": self.tls_required}
