"""Windows DPAPI wrapper (per-user encryption). Non-Windows fallback is identity: DEV/TEST ONLY."""
from __future__ import annotations
import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]

    _c = ctypes.WinDLL("crypt32", use_last_error=True)
    _k = ctypes.WinDLL("kernel32", use_last_error=True)
    _k.LocalFree.argtypes = [ctypes.c_void_p]

    def _run(fn, data: bytes) -> bytes:
        buf = ctypes.create_string_buffer(data, len(data))
        inb = _BLOB(len(data), ctypes.cast(buf, ctypes.c_void_p))
        out = _BLOB()
        if not fn(ctypes.byref(inb), None, None, None, None, 0, ctypes.byref(out)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            _k.LocalFree(out.pbData)

    def protect(data: bytes) -> bytes:
        return _run(_c.CryptProtectData, data)

    def unprotect(data: bytes) -> bytes:
        return _run(lambda a, b, c, d, e, f, g: _c.CryptUnprotectData(a, None, b, c, d, f, g), data)
else:  # pragma: no cover
    def protect(data: bytes) -> bytes:
        return data

    def unprotect(data: bytes) -> bytes:
        return data
