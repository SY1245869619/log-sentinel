"""安全工具：BCrypt 密码、JWT、AES（敏感字段加密存储）。"""
import base64
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from ..config import settings

# ---------------- 密码（BCrypt） ----------------

def hash_password(plain: str) -> str:
    # bcrypt 限制 72 字节
    pwd = plain.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except ValueError:
        return False


# ---------------- JWT ----------------

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def create_token(user_id: int, username: str, token_type: str, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "uid": user_id,
        "sub": username,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def create_access_token(user_id: int, username: str) -> str:
    return create_token(user_id, username, TOKEN_TYPE_ACCESS,
                        timedelta(minutes=settings.jwt_access_ttl_minutes))


def create_refresh_token(user_id: int, username: str) -> str:
    return create_token(user_id, username, TOKEN_TYPE_REFRESH,
                        timedelta(days=settings.jwt_refresh_ttl_days))


def parse_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


# ---------------- AES（ECB + PKCS7，密钥正好 16 字节） ----------------

def _check_key() -> bytes:
    key = settings.aes_key.encode("utf-8")
    if len(key) != 16:
        raise ValueError("AES_KEY 长度必须正好 16 字节")
    return key


def aes_encrypt(plain: str | None) -> str | None:
    if not plain:
        return plain
    key = _check_key()
    padder = PKCS7(128).padder()
    data = padder.update(plain.encode("utf-8")) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return base64.b64encode(encryptor.update(data) + encryptor.finalize()).decode("utf-8")


def aes_decrypt(cipher_text: str | None) -> str | None:
    if not cipher_text:
        return cipher_text
    key = _check_key()
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    padded = decryptor.update(base64.b64decode(cipher_text)) + decryptor.finalize()
    unpadder = PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


def mask(value: str | None) -> str | None:
    """脱敏显示。"""
    return "******" if value else value
