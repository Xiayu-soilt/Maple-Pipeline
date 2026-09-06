"""密码哈希（bcrypt）与 JWT 签发/校验。"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import JWT_SECRET

TOKEN_TTL = timedelta(hours=24)
_ALGO = "HS256"


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def create_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.now(timezone.utc) + TOKEN_TTL,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=_ALGO)


def decode_token(token: str) -> dict | None:
    """校验签名与过期时间，合法返回 payload，否则 None。"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[_ALGO])
    except jwt.PyJWTError:
        return None
