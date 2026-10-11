# Manual test procedure (not yet executed — this build was delivered untested)
1. `scripts\setup.ps1`, `scripts\firewall.ps1` (admin), `scripts\run.ps1`. Tray icon appears.
2. Copy text on Windows → History window shows `[loc/local]`.
3. Tray → Pair new phone; install APK; Pair (scan QR); confirm on Windows. Phone shows "Connected".
4. Copy text in Windows → phone notification "Copied from <laptop>", Copy action works.
5. On phone copy text, open ClipBridge (or tap *Send clipboard* / Share) → Windows toast, Ctrl+V pastes it; history shows `[rem/applied]`; no echo back.
6. Disable phone Wi-Fi, copy A then B on Windows, re-enable → only B arrives (A `superseded`).
7. Revoke device in tray → phone gets `unauthorized`, cannot connect. 8. Unknown device without token → rejected.
9. Copy a private key header / password-manager entry → not synced.
Automated: `cd windows-agent && pip install -r requirements.txt && cd .. && pytest tests`
