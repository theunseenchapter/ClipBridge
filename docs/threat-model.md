# ClipBridge threat model

## Assets

- clipboard payloads
- pairing secrets
- device identity keys
- local history metadata
- transport integrity and confidentiality

## Trust boundaries

- local device operating systems
- same-network peer discovery
- local SQLite/Room storage
- encrypted peer-to-peer channel

## Threats considered

- rogue device on the same Wi-Fi claiming to be paired
- replay of stale clipboard data
- malicious clipboard re-write loops
- content tampering during transfer
- binary payload corruption or truncation
- theft of clipboard history

## Controls

- QR-code pairing required before trust is established
- explicit confirmation of the device being paired
- single-use pairing credentials with expiry
- authenticated TLS and pinning
- rejection of unpaired and revoked devices
- SHA-256 verification and transfer deduplication
- local encryption of private keys via Windows DPAPI and Android Keystore
- no cloud telemetry or external upload path

## Limitations

- same Wi-Fi is not authorization
- Android background capture is subject to OS restrictions and user consent
- clipboard access is limited by the OS when a user denies permission or when a background app cannot observe system clipboard events
