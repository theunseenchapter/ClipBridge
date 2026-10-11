# ClipBridge protocol, security and architecture

## Topology
Windows agent = TLS **server** (port 48500, advertised via mDNS `_clipbridge._tcp`, TXT `id`,`name`,`fp`).
Android = TLS **client** that keeps one persistent connection (foreground service) and reconnects with backoff;
after 2 failures it re-resolves the laptop IP via mDNS (NsdManager).

## Framing
`uint32 big-endian length` + UTF-8 JSON object with field `t`. Max frame 32 MiB.

| `t` | direction | purpose |
|---|---|---|
| `challenge` | S→C | 16-byte random nonce (hex), per connection |
| `hello` | C→S | `device_id`, `name`, `mac = HMAC-SHA256(secret, nonce ‖ device_id)` |
| `pair` | C→S | `device_id`, `name`, single-use `token` |
| `ready` / `pair_ok` / `error` | S→C | `pair_ok` carries the 32-byte shared secret (base64) |
| `clip` | both | `item` (see `shared/schemas/clip_item.schema.json`) |
| `ack` | both | `id`, `status` = applied, stale, duplicate, replay, rejected, unsupported, paused, write_failed |
| `ping` / `pong` | both | keepalive (60 s idle timeout) |

## Ordering and conflicts
Each device keeps a Lamport counter `lamport` and a per-device `seq`. A new local copy gets
`lamport = max(seen)+1`. Total order key = `(lamport, origin_device_id)`; no wall clock is used.
An incoming item becomes the active clipboard only if its key is greater than the active key; otherwise it is
stored as `stale` in history only. The sender queues pending items durably (SQLite outbox / Room `pending`) and on
(re)connect sends **only the newest** pending item, marking older ones `superseded`, so an old item can never
overwrite a newer state after reconnection.

## Dedup / loop prevention / replay
* Unique UUID per genuine copy event (hash alone is not used, repeated copies are legitimate).
* Windows: own writes are recorded by `GetClipboardSequenceNumber()` and ignored by the listener. Android: `suppressText`.
* Receivers drop duplicate IDs, and any item with `seq <= last_seq[origin]` (replay). `origin` must equal the authenticated peer.
* Integrity: `size` and SHA-256 are verified before acceptance.

## Pairing
1. Windows tray → "Pair new phone" generates a 5-minute, single-use token and shows a QR:
   `{v,id,name,host,port,fp,tok}` where `fp` = SHA-256 of the laptop's TLS certificate (DER).
2. Phone connects with TLS **pinned to `fp`** (a wrong certificate aborts the handshake), sends `pair` + token.
3. Windows shows a modal confirmation with the phone's name. On "Yes" it creates a random 32-byte secret, stores it
   (DPAPI), returns it over the pinned TLS channel. Phone stores it wrapped by an Android Keystore AES-GCM key.
4. Later connections authenticate with the HMAC challenge response; unpaired or revoked devices get `error` and are closed.
Same Wi-Fi is never authorization. Peers with non-private IPs are rejected.

## Key lifecycle / storage
* Laptop identity: ECDSA P-256 self-signed cert, 10 years. Private key file is encrypted; its password is protected by DPAPI (current Windows user).
* Paired-device secrets: `devices.bin`, DPAPI-protected.
* **Rotation / re-pairing:** `python -m clipbridge --reset-identity` deletes cert, key and devices; every phone must re-scan a new QR (pin changes).
* **Revocation:** tray → Paired devices → Revoke (secret wiped, live connection closed). Phone side: re-pairing overwrites; "unpair" occurs automatically on `unauthorized`.
* Logs never contain clipboard text, tokens, secrets or keys.

## Threat model (summary)
In scope: other devices on the LAN (scan, connect, sniff, MITM, replay), stale/replayed messages, oversized/malformed input.
Mitigations: pinned TLS ≥1.2, token + explicit confirmation, HMAC auth per connection with fresh nonce, validation, size limits.
Out of scope / limitations: malware running as your user (can read clipboard/DPAPI), a compromised phone, physical access,
TLS pinning protects only after pairing (QR is the trust root; shield it while on screen), no forward secrecy of the shared secret
(TLS session keys are forward-secret). Clipboard history is stored unencrypted in SQLite under `%APPDATA%\ClipBridge` and in the app's private storage.

## Android clipboard limits (documented, not bypassed)
Since Android 10 apps can read the clipboard only when focused. ClipBridge therefore captures: (a) while the app is in the
foreground, (b) via the share sheet ("Share → ClipBridge"), (c) via the notification action **Send clipboard** (opens a
transparent activity that briefly gains focus). Receiving *writes* the clipboard from the service and also posts a Copy
notification as fallback (some OEM builds may block background writes). No accessibility service is used.
