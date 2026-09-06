"""认证数据源：MySQL 独立用户库（与业务 SQLite 分离）。

启动时自动创建数据库与表；User 表存 bcrypt 密码哈希。
"""
from datetime import datetime

import pymysql
from sqlalchemy import DateTime, String, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import MYSQL_URL


def _ensure_database(url: str) -> None:
    """SQLAlchemy 连接前库必须存在，这里先裸连 server 建库。"""
    parsed = make_url(url)
    conn = pymysql.connect(
        host=parsed.host or "127.0.0.1", port=parsed.port or 3306,
        user=parsed.username, password=parsed.password, connect_timeout=5,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{parsed.database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


try:
    _ensure_database(MYSQL_URL)
    auth_engine = create_engine(MYSQL_URL, pool_pre_ping=True, pool_recycle=3600)
    with auth_engine.connect():
        pass
except (pymysql.err.OperationalError, OperationalError) as e:
    raise RuntimeError(
        f"MySQL 连接失败（{e}）：请确认本机 MySQL 已启动、.env 中 MYSQL_URL 的账号密码正确"
    ) from e

AuthSessionLocal = sessionmaker(bind=auth_engine, autoflush=False, autocommit=False)


class AuthBase(DeclarativeBase):
    pass


class User(AuthBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def get_auth_db():
    db = AuthSessionLocal()
    try:
        yield db
    finally:
        db.close()
