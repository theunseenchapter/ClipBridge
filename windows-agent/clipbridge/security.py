from __future__ import annotations
import base64, datetime as dt, hashlib, hmac, json, os, secrets, ssl, socket, threading, time
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from . import dpapi


@dataclass
class Identity:
    cert_path: Path
    key_path: Path
    password: bytes
    fingerprint: str  # sha256 of cert DER, lowercase hex (pinned by peers)

    @staticmethod
    def load_or_create(d: Path) -> "Identity":
        cert, key, pw = d / "cert.pem", d / "key.pem", d / "key.pw"
        if not (cert.exists() and key.exists() and pw.exists()):
            password = secrets.token_bytes(32)
            priv = ec.generate_private_key(ec.SECP256R1())
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ClipBridge-" + socket.gethostname())])
            now = dt.datetime.now(dt.timezone.utc)
            c = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(priv.public_key())
                 .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
                 .not_valid_after(now + dt.timedelta(days=3650)).sign(priv, hashes.SHA256()))
            key.write_bytes(priv.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.BestAvailableEncryption(base64.b64encode(password))))
            pw.write_bytes(dpapi.protect(base64.b64encode(password)))  # password only recoverable by this Windows user
            cert.write_bytes(c.public_bytes(serialization.Encoding.PEM))
        password = dpapi.unprotect(pw.read_bytes())
        der = x509.load_pem_x509_certificate(cert.read_bytes()).public_bytes(serialization.Encoding.DER)
        return Identity(cert, key, password, hashlib.sha256(der).hexdigest())

    def server_context(self) -> ssl.SSLContext:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(str(self.cert_path), str(self.key_path), password=self.password)
        return ctx

    @staticmethod
    def reset(d: Path) -> None:
        """Key rotation: delete identity. All phones must re-pair (new fingerprint)."""
        for n in ("cert.pem", "key.pem", "key.pw", "devices.bin"):
            (d / n).unlink(missing_ok=True)


def mac(secret: bytes, nonce: bytes, device_id: str) -> str:
    return hmac.new(secret, nonce + device_id.encode(), hashlib.sha256).hexdigest()


class DeviceStore:
    """Paired devices + per-device shared secrets, DPAPI-encrypted at rest."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.data: dict[str, dict] = {}
        if path.exists():
            self.data = json.loads(dpapi.unprotect(path.read_bytes()))

    def _save(self) -> None:
        self.path.write_bytes(dpapi.protect(json.dumps(self.data).encode()))

    def add(self, dev_id: str, name: str, secret: bytes) -> None:
        with self.lock:
            self.data[dev_id] = {"name": name, "secret": base64.b64encode(secret).decode(),
                                 "revoked": False, "added": time.time()}
            self._save()

    def secret(self, dev_id: str) -> bytes | None:
        d = self.data.get(dev_id)
        return base64.b64decode(d["secret"]) if d and not d["revoked"] else None

    def name(self, dev_id: str) -> str:
        return self.data.get(dev_id, {}).get("name", "device")

    def active_ids(self) -> list[str]:
        return [k for k, v in self.data.items() if not v["revoked"]]

    def revoke(self, dev_id: str) -> None:
        with self.lock:
            if dev_id in self.data:
                self.data[dev_id]["revoked"] = True
                self.data[dev_id]["secret"] = ""
                self._save()


class PairingManager:
    """Short-lived (5 min), single-use pairing tokens."""

    def __init__(self, ttl: int = 300) -> None:
        self.ttl, self.tokens, self.lock = ttl, {}, threading.Lock()

    def create(self) -> str:
        t = secrets.token_urlsafe(24)
        with self.lock:
            self.tokens = {k: v for k, v in self.tokens.items() if v > time.time()}
            self.tokens[t] = time.time() + self.ttl
        return t

    def consume(self, token: str) -> bool:
        with self.lock:
            ok = False
            for k, exp in list(self.tokens.items()):
                if hmac.compare_digest(k, token) and exp > time.time():
                    ok = True
                    del self.tokens[k]
            return ok

    def clear(self) -> None:
        with self.lock:
            self.tokens.clear()


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
