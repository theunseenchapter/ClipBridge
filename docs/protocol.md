# ClipBridge protocol

## Core item envelope

Every clipboard item is represented by a JSON-compatible envelope:

```json
{
  "protocol_version": 1,
  "item_id": "0d3f2d5a-4e29-47e7-b998-36e5a75ff9cf",
  "origin_device_id": "WIN-LAPTOP-01",
  "origin_seq": 342,
  "logical_clock": 342,
  "created_at": "2026-10-11T13:00:00Z",
  "content_type": "text/plain",
  "mime_type": "text/plain; charset=utf-8",
  "content_size": 128,
  "sha256": "abcd...",
  "transfer_id": null,
  "payload": "... optional content or metadata"
}
```

## Ordering rules

- Each device keeps a monotonic local sequence counter for genuine user copy events.
- A remote item can replace the active clipboard only when its logical clock is newer than the current active version.
- Old or replayed items are rejected to maintain a single active state.
- Different device clocks are compared via logical clocks and origin device IDs, not wall-clock timestamps.

## Transfer model

- Text and URLs are carried inline.
- Images and file payloads use a transfer ID and a streamed binary transport.
- The SHA-256 hash is verified before accepting a file or image transfer.
- Transfer acknowledgement and retry state are persisted in SQLite/Room.

## Security contracts

- Pairing uses QR codes and a short-lived challenge.
- Device identities use persistent key pairs and pinned certificates.
- TLS is mandatory for all network traffic.
- Local logging excludes sensitive clipboard content and pairing secrets.
