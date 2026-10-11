# ClipBridge architecture

## Design goals

- Trusted local network, no cloud dependency
- Bidirectional clipboard sync between Windows and Android
- Deterministic ordering and replay protection
- Local-only history with search, pinning, and restore
- Explicit pairing and device revocation

## Components

### Windows agent

The Windows agent owns:

- native clipboard monitoring
- local SQLite storage
- tray/status notifications
- secure transport and discovery
- deduplication and ordering rules

### Android app

The Android app owns:

- QR-code pairing
- local Room/SQLite history
- clipboard capture and injection
- notification actions for copy/open/dismiss
- encrypted transport and sync state

### Shared protocol

A small shared schema ensures both ends agree on:

- protocol version
- item ID and origin device ID
- logical sequence and ordering metadata
- MIME content type and size
- SHA-256 content hash
- transfer IDs for binary payloads

## Key decisions

1. Use device IDs and secure keys, not Wi-Fi SSID trust.
2. Require authenticated TLS and certificate/public-key pinning.
3. Preserve item IDs during restore and rebroadcast suppression.
4. Treat remote writes as accepted updates only if their version is newer and valid.
5. Keep raw binary payloads in transfer chunks rather than storing them inline in the protocol envelope.

## Phase 1 implementation

The current workspace includes the first production-ready building blocks:

- clipboard read/write adapter
- local history DB
- search and retention logic
- user-visible status abstraction for tray notifications
