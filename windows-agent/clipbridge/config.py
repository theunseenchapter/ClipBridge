from __future__ import annotations
import json, os, socket, uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "ClipBridge"
PORT = 48500
SERVICE_TYPE = "_clipbridge._tcp.local."


@dataclass
class Settings:
    device_id: str = ""
    device_name: str = ""
    max_item_bytes: int = 25 * 1024 * 1024
    retention: int = 100
    paused: bool = False
    exclude_patterns: list[str] = field(default_factory=lambda: [
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"^\s*(ghp_|sk-|AKIA)[A-Za-z0-9_\-]{16,}\s*$",
    ])

    @classmethod
    def load(cls) -> "Settings":
        APP_DIR.mkdir(parents=True, exist_ok=True)
        p = APP_DIR / "settings.json"
        s = cls()
        if p.exists():
            data = json.loads(p.read_text("utf-8"))
            for k, v in data.items():
                if hasattr(s, k):
                    setattr(s, k, v)
        if not s.device_id:
            s.device_id = str(uuid.uuid4())
            s.device_name = socket.gethostname()
        s.save()
        return s

    def save(self) -> None:
        (APP_DIR / "settings.json").write_text(json.dumps(asdict(self), indent=2), "utf-8")
