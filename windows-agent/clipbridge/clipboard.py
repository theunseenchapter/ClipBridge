"""Native Windows clipboard: event-driven (AddClipboardFormatListener), no polling."""
from __future__ import annotations
import ctypes, logging, threading, time
from ctypes import wintypes as w
from typing import Callable

log = logging.getLogger("clipbridge.clipboard")
CF_UNICODETEXT, CF_DIB, CF_HDROP = 13, 8, 15
WM_CLIPBOARDUPDATE = 0x031D
u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
P = ctypes.c_void_p
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, P, w.UINT, w.WPARAM, w.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", P), ("hIcon", P), ("hCursor", P),
                ("hbrBackground", P), ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR)]


u32.DefWindowProcW.argtypes = [P, w.UINT, w.WPARAM, w.LPARAM]
u32.DefWindowProcW.restype = LRESULT
u32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
u32.RegisterClassW.restype = w.ATOM
u32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, P, P, P, P]
u32.CreateWindowExW.restype = P
u32.AddClipboardFormatListener.argtypes = [P]
u32.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), P, w.UINT, w.UINT]
u32.TranslateMessage.argtypes = [ctypes.POINTER(w.MSG)]
u32.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
u32.DispatchMessageW.restype = LRESULT
u32.OpenClipboard.argtypes = [P]
u32.GetClipboardData.argtypes = [w.UINT]
u32.GetClipboardData.restype = P
u32.SetClipboardData.argtypes = [w.UINT, P]
u32.SetClipboardData.restype = P
u32.IsClipboardFormatAvailable.argtypes = [w.UINT]
u32.RegisterClipboardFormatW.argtypes = [w.LPCWSTR]
k32.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
k32.GlobalAlloc.restype = P
k32.GlobalLock.argtypes = [P]
k32.GlobalLock.restype = P
k32.GlobalUnlock.argtypes = [P]
k32.GlobalFree.argtypes = [P]
k32.GetModuleHandleW.argtypes = [w.LPCWSTR]
k32.GetModuleHandleW.restype = P

_EXCLUDE_FMT = u32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")


def _open() -> bool:
    for _ in range(10):
        if u32.OpenClipboard(None):
            return True
        time.sleep(0.03)
    return False


def read_text() -> str | None:
    if not u32.IsClipboardFormatAvailable(CF_UNICODETEXT) or not _open():
        return None
    try:
        h = u32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        ptr = k32.GlobalLock(h)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


class ClipboardMonitor:
    def __init__(self, on_text: Callable[[str], None]) -> None:
        self.on_text = on_text
        self._own: list[int] = []
        self._proc = WNDPROC(self._wndproc)  # keep reference (GC safety)
        self._lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="clipboard").start()

    def write_text(self, text: str) -> bool:
        """Replace the system clipboard. The resulting change is tagged as internal."""
        data = (text + "\0").encode("utf-16-le")
        h = k32.GlobalAlloc(0x0002, len(data))
        if not h:
            return False
        ptr = k32.GlobalLock(h)
        ctypes.memmove(ptr, data, len(data))
        k32.GlobalUnlock(h)
        if not _open():
            k32.GlobalFree(h)
            return False
        try:
            u32.EmptyClipboard()
            if not u32.SetClipboardData(CF_UNICODETEXT, h):
                k32.GlobalFree(h)
                return False
        finally:
            u32.CloseClipboard()
        with self._lock:
            self._own.append(u32.GetClipboardSequenceNumber())
            self._own = self._own[-16:]
        return True

    def _wndproc(self, hwnd, msg, wp, lp):
        if msg == WM_CLIPBOARDUPDATE:
            try:
                self._changed()
            except Exception:
                log.exception("clipboard handler failed")
            return 0
        return u32.DefWindowProcW(hwnd, msg, wp, lp)

    def _changed(self) -> None:
        seq = u32.GetClipboardSequenceNumber()
        with self._lock:
            if seq in self._own:
                return  # our own write: never rebroadcast
        if u32.IsClipboardFormatAvailable(_EXCLUDE_FMT):
            return  # password managers etc. ask not to be monitored
        text = read_text()
        if text is None:
            if u32.IsClipboardFormatAvailable(CF_DIB) or u32.IsClipboardFormatAvailable(CF_HDROP):
                log.info("unsupported clipboard content (image/file): not synced in this build")
            return
        if text:
            self.on_text(text)

    def _loop(self) -> None:
        cls = WNDCLASSW()
        cls.lpfnWndProc = self._proc
        cls.hInstance = k32.GetModuleHandleW(None)
        cls.lpszClassName = "ClipBridgeListener"
        u32.RegisterClassW(ctypes.byref(cls))
        hwnd = u32.CreateWindowExW(0, "ClipBridgeListener", "ClipBridge", 0, 0, 0, 0, 0,
                                   ctypes.c_void_p(-3), None, cls.hInstance, None)  # HWND_MESSAGE
        if not hwnd or not u32.AddClipboardFormatListener(hwnd):
            log.error("could not register clipboard listener")
            return
        msg = w.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
