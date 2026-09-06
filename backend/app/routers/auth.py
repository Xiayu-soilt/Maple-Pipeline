from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth_db import User, get_auth_db
from app.services.security import (
    create_token, decode_token, hash_password, verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)


class AuthForm(BaseModel):
    username: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=64)


class TokenOut(BaseModel):
    token: str
    username: str


class UserOut(BaseModel):
    id: int
    username: str
    created_at: str


def require_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """业务路由统一认证依赖：校验 Bearer token，返回用户信息。"""
    if creds is None:
        raise HTTPException(401, "未登录，请先登录")
    payload = decode_token(creds.credentials)
    if payload is None:
        raise HTTPException(401, "登录已过期或 token 无效，请重新登录")
    return payload


@router.post("/register", status_code=201)
def register(form: AuthForm, db: Session = Depends(get_auth_db)):
    exists = db.query(User).filter(User.username == form.username).first()
    if exists:
        raise HTTPException(400, "用户名已被注册")
    user = User(username=form.username, password_hash=hash_password(form.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "用户名已被注册")
    return {"message": "注册成功，请登录"}


@router.post("/login", response_model=TokenOut)
def login(form: AuthForm, db: Session = Depends(get_auth_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return TokenOut(token=create_token(user.id, user.username), username=user.username)


@router.get("/me")
def me(payload: dict = Depends(require_auth), db: Session = Depends(get_auth_db)):
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "用户不存在")
    return UserOut(id=user.id, username=user.username, created_at=user.created_at.isoformat())
