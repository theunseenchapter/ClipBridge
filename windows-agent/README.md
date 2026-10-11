# ClipBridge Windows Agent

This package contains the Windows foundation for ClipBridge, including:

- clipboard read/write adapters
- clipboard event monitoring via Win32 sequence numbers
- persistent SQLite history with FTS5 search
- status and tray abstractions for user notifications

## Install

```powershell
cd D:\ClipBridge\windows-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

## Local SQLite history

Data is stored in the default path:

`D:\ClipBridge\windows-agent\clipbridge-data\history.db`

The store keeps the latest 100 items unless a different retention limit is configured.
