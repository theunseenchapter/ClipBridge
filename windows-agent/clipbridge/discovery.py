from __future__ import annotations
import logging, socket, threading
from zeroconf import ServiceInfo, Zeroconf
from .config import PORT, SERVICE_TYPE
from .security import local_ip

log = logging.getLogger("clipbridge.mdns")


def start_advertising(device_id: str, name: str, fingerprint: str) -> Zeroconf:
    zc = Zeroconf()
    info = ServiceInfo(SERVICE_TYPE, f"ClipBridge-{device_id[:8]}.{SERVICE_TYPE}",
                       addresses=[socket.inet_aton(local_ip())], port=PORT,
                       properties={"id": device_id, "name": name, "fp": fingerprint[:16]})
    threading.Thread(target=zc.register_service, args=(info,), daemon=True).start()
    return zc
