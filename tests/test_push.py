"""رمزگشایی سمت مرورگر را شبیه‌سازی می‌کنیم تا مطمئن شویم رمزنگاری با RFC 8291 سازگار است."""
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app import push


def hkdf(salt, ikm, info, n):
    return HKDF(algorithm=hashes.SHA256(), length=n, salt=salt, info=info).derive(ikm)


def test_encrypt_roundtrip():
    ua_priv = ec.generate_private_key(ec.SECP256R1())
    ua_pub_raw = ua_priv.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    auth = os.urandom(16)
    body = push.encrypt('{"title":"سلام"}'.encode(), push.b64u(ua_pub_raw), push.b64u(auth))

    salt, rs, idlen = body[:16], int.from_bytes(body[16:20], "big"), body[20]
    as_pub_raw = body[21:21 + idlen]
    ciphertext = body[21 + idlen:]
    assert rs == 4096 and idlen == 65
    shared = ua_priv.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub_raw))
    ikm = hkdf(auth, shared, b"WebPush: info\x00" + ua_pub_raw + as_pub_raw, 32)
    cek = hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    plain = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert plain == '{"title":"سلام"}'.encode() + b'\x02'


def test_vapid_jwt_verifies():
    priv_b64, pub_b64 = push.gen_vapid()
    priv = push.load_private(priv_b64)
    token = push.vapid_jwt(priv, "https://fcm.googleapis.com", "mailto:a@b.c")
    h, c, s = token.split(".")
    claims = json.loads(push.b64d(c))
    assert claims["aud"] == "https://fcm.googleapis.com" and claims["sub"] == "mailto:a@b.c"
    sig = push.b64d(s)
    der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), push.b64d(pub_b64))
    pub.verify(der, f"{h}.{c}".encode(), ec.ECDSA(hashes.SHA256()))  # raises on failure
