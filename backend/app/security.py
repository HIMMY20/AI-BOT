from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.config import settings
from app.db import get_db
from app.models import User

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 UTF-8 bytes")
    return pwd.hash(value)


def verify_password(value: str, hashed: str) -> bool:
    if len(value.encode("utf-8")) > 72:
        return False
    try:
        return pwd.verify(value, hashed)
    except (ValueError, TypeError):
        return False


def token_for(user: User) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=8)
    return jwt.encode(
        {"sub": str(user.id), "exp": expires},
        settings.jwt_secret,
        algorithm="HS256",
    )


def fernet() -> Fernet:
    if not settings.fernet_key:
        raise RuntimeError("FERNET_KEY is not configured in backend/.env")
    try:
        return Fernet(settings.fernet_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("FERNET_KEY is invalid; generate a Fernet key") from exc


def encrypt(value: str) -> str:
    return fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(value: str) -> str:
    try:
        return fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Credential decryption failed; check FERNET_KEY") from exc


def current_user(token: str = Depends(oauth), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
        user_id = int(payload["sub"])
        user = db.get(User, user_id)
    except (JWTError, ValueError, KeyError, TypeError):
        user = None

    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired login")
    return user


def approved(user: User = Depends(current_user)) -> User:
    if user.status == "suspended":
        raise HTTPException(status_code=403, detail="Account suspended")
    if user.role != "admin" and user.status != "approved":
        raise HTTPException(
            status_code=403,
            detail=f"Account {user.status}; admin approval required",
        )
    return user


def admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user
