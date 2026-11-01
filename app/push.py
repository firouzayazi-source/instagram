"""اعلان پوش وب (RFC 8291 / 8292) فقط با cryptography؛ بدون وابستگی اضافه.

ساخت کلید VAPID:  python -m app.push --gen
"""
import base64
import json
import os
import sys
import time
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import config, db

_X962 = (serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def gen_vapid() -> tuple[str, str]:
    priv = ec.generate_private_key(ec.SECP256R1())
    raw = priv.private_numbers().private_value.to_bytes(32, "big")
    return b64u(raw), b64u(priv.public_key().public_bytes(*_X962))


def load_private(b64: str):
    return ec.derive_private_key(int.from_bytes(b64d(b64), "big"), ec.SECP256R1())


def vapid_jwt(priv, audience: str, subject: str) -> str:
    header = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    claims = b64u(json.dumps({"aud": audience, "exp": int(time.time()) + 12 * 3600, "sub": subject}).encode())
    der = priv.sign(f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    return f"{header}.{claims}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(plaintext: bytes, p256dh: str, auth: str) -> bytes:
    """رمزنگاری aes128gcm برای مرورگر گیرنده."""
    ua_pub_raw, auth_secret = b64d(p256dh), b64d(auth)
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub_raw)
    as_priv = ec.generate_private_key(ec.SECP256R1())
    as_pub_raw = as_priv.public_key().public_bytes(*_X962)
    ikm = _hkdf(auth_secret, as_priv.exchange(ec.ECDH(), ua_pub), b"WebPush: info\x00" + ua_pub_raw + as_pub_raw, 32)
    salt = os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    header = salt + (4096).to_bytes(4, "big") + bytes([len(as_pub_raw)]) + as_pub_raw
    return header + AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)


async def send_one(client: httpx.AsyncClient, sub: dict, payload: dict) -> int:
    endpoint = sub["endpoint"]
    u = urlsplit(endpoint)
    priv = load_private(config.VAPID_PRIVATE_KEY)
    body = encrypt(json.dumps(payload, ensure_ascii=False).encode(), sub["keys"]["p256dh"], sub["keys"]["auth"])
    headers = {
        "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream",
        "TTL": "86400",
        "Urgency": "high",
        "Authorization": f"vapid t={vapid_jwt(priv, f'{u.scheme}://{u.netloc}', config.VAPID_SUBJECT)}, k={config.VAPID_PUBLIC_KEY}",
    }
    r = await client.post(endpoint, content=body, headers=headers, timeout=15)
    return r.status_code


async def notify_all(title: str, body: str, url: str = "/") -> None:
    """به همه‌ی دستگاه‌های ثبت‌شده می‌فرستد؛ اشتراک‌های منقضی را حذف می‌کند."""
    if not config.VAPID_PRIVATE_KEY:
        return
    with db.connect() as c:
        subs = db.push_subs(c)
    if not subs:
        return
    async with httpx.AsyncClient() as client:
        for sub in subs:
            try:
                status = await send_one(client, sub, {"title": title, "body": body, "url": url})
            except Exception:  # noqa: BLE001
                continue
            if status in (404, 410):
                with db.connect() as c:
                    db.delete_push_sub(c, sub["endpoint"])


if __name__ == "__main__":
    if "--gen" in sys.argv:
        priv, pub = gen_vapid()
        print(f"VAPID_PRIVATE_KEY={priv}\nVAPID_PUBLIC_KEY={pub}")
