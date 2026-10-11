from __future__ import annotations
import asyncio, ctypes, logging, sys, threading, webbrowser
from pathlib import Path
import pystray
from PIL import Image, ImageDraw

from . import clipboard
from .config import APP_DIR, Settings
from .control_api import ControlApi
from .discovery import start_advertising
from .history import History
from .security import DeviceStore, Identity, PairingManager
from .sync import SyncEngine
from .ui import UI

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_INSTANCE_MUTEX = None


def _acquire_single_instance() -> bool:
    """Prevent two ClipBridge backends from competing for the sync port."""
    global _INSTANCE_MUTEX
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _INSTANCE_MUTEX = kernel32.CreateMutexW(None, True, "Local\\ClipBridge")
    if not _INSTANCE_MUTEX:
        return True
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(
            0,
            "ClipBridge is already running. Use the tray icon or close the existing copy first.",
            "ClipBridge",
            0x40 | 0x1000,
        )
        return False
    return True


def _startup_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "ClipBridge")
            return True
    except OSError:
        return False


def _set_startup(on: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            exe = sys.executable.replace("python.exe", "pythonw.exe")
            cmd = f'"{sys.executable}"' if getattr(sys, "frozen", False) else f'"{exe}" -m clipbridge'
            winreg.SetValueEx(k, "ClipBridge", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(k, "ClipBridge")
            except OSError:
                pass


def _branding_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "branding" / "clipbridge-icon.png"


def _icon(color: str) -> Image.Image:
    try:
        im = Image.open(_branding_path()).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
    except (FileNotFoundError, OSError):
        im = Image.new("RGBA", (64, 64), (15, 23, 42, 255))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((8, 8, 56, 56), 12, fill="#2563eb")
    d = ImageDraw.Draw(im)
    d.ellipse((44, 44, 62, 62), fill=color, outline="#ffffff", width=2)
    return im


def main() -> None:
    if "--reset-identity" in sys.argv:
        Identity.reset(APP_DIR)
        print("Identity and paired devices removed. Re-pair all phones.")
        return
    if not _acquire_single_instance():
        return
    APP_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(APP_DIR / "clipbridge.log"), level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")  # never log payloads
    s = Settings.load()
    hist = History(APP_DIR / "history.db")
    ident = Identity.load_or_create(APP_DIR)
    devices = DeviceStore(APP_DIR / "devices.bin")
    pairing = PairingManager()
    state = {"n": 0}
    engine: SyncEngine | None = None
    ui = UI(lambda: engine, hist, s)
    icon: pystray.Icon | None = None

    def on_status(n: int) -> None:
        state["n"] = n
        if icon:
            icon.icon = _icon("#2ecc71" if n else "#e67e22")
            icon.update_menu()

    def confirm(name: str) -> bool:  # MB_YESNO | MB_ICONQUESTION | MB_TOPMOST
        return ctypes.windll.user32.MessageBoxW(0, f"Pair with device “{name}”?\nOnly confirm if you just scanned the QR code.",
                                                "ClipBridge pairing", 0x24 | 0x40000) == 6

    mon = clipboard.ClipboardMonitor(lambda t: engine and engine.on_local_copy(t))
    engine = SyncEngine(s, hist, devices, pairing, ident, mon.write_text, ui.toast, on_status, confirm)
    control_api = ControlApi(lambda: engine, s, hist, lambda: ui.post(ui.show_pair),
                             lambda: ui.post(ui.show_history))
    control_api.start()
    webbrowser.open("http://127.0.0.1:48501/dashboard")
    mon.start()
    threading.Thread(target=lambda: asyncio.run(engine.serve()), daemon=True, name="net").start()
    zc = start_advertising(s.device_id, s.device_name, ident.fingerprint)

    def toggle_pause(_i, _it):
        s.paused = not s.paused
        s.save()

    def toggle_startup(_i, _it):
        _set_startup(not _startup_enabled())

    def revoke_items():
        items = [pystray.MenuItem(f"Revoke {devices.name(d)}", (lambda d: lambda i, it: engine.revoke(d))(d))
                 for d in devices.active_ids()]
        return items or [pystray.MenuItem("No paired devices", None, enabled=False)]

    def quit_(i, _it):
        i.stop()
        control_api.stop()
        zc.close()
        ui.post(ui.root.destroy)

    def open_dashboard(_i, _it):
        webbrowser.open("http://127.0.0.1:48501/dashboard")

    menu = pystray.Menu(
        pystray.MenuItem(lambda i: f"{'Connected' if state['n'] else 'Waiting for phone'}"
                                   f"{' (paused)' if s.paused else ''}", None, enabled=False),
        pystray.MenuItem("History…", lambda i, it: ui.post(ui.show_history), default=True),
        pystray.MenuItem("Pair new phone…", lambda i, it: ui.post(ui.show_pair)),
        pystray.MenuItem("Open web dashboard", open_dashboard),
        pystray.MenuItem("Disconnect phone", lambda i, it: ui.post(ui.confirm_disconnect)),
        pystray.MenuItem("Pause sync", toggle_pause, checked=lambda it: s.paused),
        pystray.MenuItem("Start with Windows", toggle_startup, checked=lambda it: _startup_enabled()),
        pystray.MenuItem("Paired devices", pystray.Menu(revoke_items)),
        pystray.MenuItem("Quit", quit_))
    icon = pystray.Icon("ClipBridge", _icon("#e67e22"), "ClipBridge", menu)
    icon.run_detached()
    ui.run()
