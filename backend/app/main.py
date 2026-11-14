from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, SessionLocal, engine, get_db
from app.models import AuditLog, DeltaCredential, TradeRecord, User
from app.security import (
    admin,
    approved,
    current_user,
    decrypt,
    encrypt,
    hash_password,
    token_for,
    verify_password,
)
from app.delta import DeltaAPIError, DeltaClient
from app.strategy import frame_from_candles, signal, size_for_risk, simple_backtest


Base.metadata.create_all(bind=engine)
app = FastAPI(
    title=settings.app_name,
    version="2.2.0",
    description="Market analysis and account workspace. Order execution is disabled.",
)

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


# --------------------------------------------------
# REQUEST MODELS
# --------------------------------------------------

class Register(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=72)


class Credential(BaseModel):
    api_key: str = Field(min_length=8, max_length=256)
    api_secret: str = Field(min_length=12, max_length=256)
    environment: str = "demo"


class StatusUpdate(BaseModel):
    status: str


class Analyze(BaseModel):
    symbol: str = Field(min_length=2, max_length=40)
    resolution: str = "15m"
    limit: int = Field(default=250, ge=60, le=500)


class RiskRequest(BaseModel):
    equity: float = Field(gt=0)
    entry: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    risk_pct: float = Field(default=0.5, gt=0, le=2)
    contract_multiplier: float = Field(default=1, gt=0)


class JournalEntry(BaseModel):
    symbol: str = Field(min_length=2, max_length=80)
    side: str
    entry_price: float = Field(gt=0)
    quantity: float = Field(gt=0)


# --------------------------------------------------
# STARTUP / ADMIN SEED
# --------------------------------------------------

@app.on_event("startup")
def startup_checks_and_seed():
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        raise RuntimeError(
            "JWT_SECRET is missing/too short. Run setup.ps1 or configure backend/.env first."
        )
    if not settings.fernet_key:
        raise RuntimeError(
            "FERNET_KEY is missing. Run setup.ps1 or configure backend/.env first."
        )
    if settings.delta_env not in {"demo", "live"}:
        raise RuntimeError("DELTA_ENV must be either 'demo' or 'live'")

    if not settings.admin_email or not settings.admin_password:
        raise RuntimeError("Set ADMIN_EMAIL and ADMIN_PASSWORD in backend/.env")

    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.email == settings.admin_email.lower()))
        if not existing:
            owner = User(
                email=settings.admin_email.lower(),
                full_name="Platform Owner",
                password_hash=hash_password(settings.admin_password),
                role="admin",
                status="approved",
            )
            db.add(owner)
            db.commit()
    finally:
        db.close()


# --------------------------------------------------
# HEALTH
# --------------------------------------------------

@app.get("/health")
def health():
    return {
        "ok": True,
        "market_data_environment": settings.delta_env,
        "live_orders_enabled": False,
        "demo_orders_enabled": False,
        "order_execution": "disabled",
    }


@app.get("/market/status")
def market_status(user: User = Depends(approved)):
    return {
        "environment": settings.delta_env,
        "market_data_environment": settings.delta_env,
        "order_execution": "disabled",
        "note": "Market data environment is independent of each user's private API credentials.",
    }


# --------------------------------------------------
# AUTHENTICATION
# --------------------------------------------------

@app.post("/auth/register", status_code=201)
def register(body: Register, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=email,
        full_name=body.full_name.strip(),
        password_hash=hash_password(body.password),
        role="user",
        status="pending",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(AuditLog(target_id=user.id, action="register", details="Pending admin approval"))
    db.commit()
    return {"status": "pending", "message": "Registration received; admin approval required"}


@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "access_token": token_for(user),
        "token_type": "bearer",
        "role": user.role,
        "status": user.status,
    }


@app.get("/me")
def me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "status": user.status,
    }


# --------------------------------------------------
# ADMIN
# --------------------------------------------------

@app.get("/admin/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(admin)):
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return [
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "status": user.status,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
        for user in users
    ]


@app.patch("/admin/users/{user_id}/status")
def update_user_status(
    user_id: int,
    body: StatusUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(admin),
):
    if body.status not in {"approved", "rejected", "suspended", "pending"}:
        raise HTTPException(status_code=400, detail="Invalid account status")

    user = db.get(User, user_id)
    if not user or user.role == "admin":
        raise HTTPException(status_code=404, detail="User not found")

    user.status = body.status
    db.add(
        AuditLog(
            actor_id=actor.id,
            target_id=user.id,
            action=f"status_{body.status}",
        )
    )
    db.commit()
    return {"id": user.id, "status": user.status}


@app.get("/admin/audit")
def audit_logs(db: Session = Depends(get_db), _: User = Depends(admin)):
    logs = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500)
    ).all()
    return [
        {
            "id": item.id,
            "actor_id": item.actor_id,
            "target_id": item.target_id,
            "action": item.action,
            "details": item.details,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in logs
    ]


# --------------------------------------------------
# PER-USER DELTA CREDENTIALS
# --------------------------------------------------

@app.put("/delta/credentials")
def save_credentials(
    body: Credential,
    db: Session = Depends(get_db),
    user: User = Depends(approved),
):
    if body.environment not in {"demo", "live"}:
        raise HTTPException(status_code=400, detail="Environment must be demo or live")

    # Private credentials are saved for private account reads only.
    # This does NOT enable order execution.
    record = db.scalar(
        select(DeltaCredential).where(DeltaCredential.user_id == user.id)
    )
    if record is None:
        record = DeltaCredential(
            user_id=user.id,
            api_key_enc="",
            api_secret_enc="",
            environment=body.environment,
        )
        db.add(record)

    record.api_key_enc = encrypt(body.api_key)
    record.api_secret_enc = encrypt(body.api_secret)
    record.environment = body.environment
    db.commit()
    return {"connected": True, "credential_environment": record.environment}


def user_client(db: Session, user: User) -> DeltaClient:
    record = db.scalar(
        select(DeltaCredential).where(DeltaCredential.user_id == user.id)
    )
    if not record:
        raise HTTPException(status_code=400, detail="Connect your Delta API credentials first")
    return DeltaClient(
        decrypt(record.api_key_enc),
        decrypt(record.api_secret_enc),
        record.environment,
    )


@app.get("/delta/status")
def delta_status(db: Session = Depends(get_db), user: User = Depends(approved)):
    record = db.scalar(
        select(DeltaCredential).where(DeltaCredential.user_id == user.id)
    )
    return {
        "connected": bool(record),
        "market_data_environment": settings.delta_env,
        "credential_environment": record.environment if record else None,
        "order_execution": "disabled",
    }


# --------------------------------------------------
# PUBLIC MARKET DATA AND ANALYSIS
# --------------------------------------------------

@app.get("/market/products")
def market_products(_: User = Depends(approved)):
    try:
        return DeltaClient(env=settings.delta_env).products()
    except (DeltaAPIError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/market/tickers")
def market_tickers(_: User = Depends(approved)):
    try:
        return DeltaClient(env=settings.delta_env).tickers()
    except (DeltaAPIError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def fetch_analysis_data(body: Analyze):
    try:
        raw = DeltaClient(env=settings.delta_env).candles(
            body.symbol,
            body.resolution,
            body.limit,
        )
        frame = frame_from_candles(raw)
        return raw, frame
    except (DeltaAPIError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/analysis/signal")
def analyze(body: Analyze, _: User = Depends(approved)):
    _, frame = fetch_analysis_data(body)
    try:
        result = signal(frame, body.symbol.strip().upper(), body.resolution)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/analysis/candles")
def analysis_candles(body: Analyze, _: User = Depends(approved)):
    _, frame = fetch_analysis_data(body)
    records = frame.to_dict(orient="records")
    candles = []
    for item in records:
        candles.append({
            "time": int(item["time"]) if "time" in item and item["time"] is not None else None,
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
            "volume": float(item.get("volume", 0)),
        })
    return {
        "symbol": body.symbol.strip().upper(),
        "resolution": body.resolution,
        "candles": candles,
    }


@app.post("/analysis/backtest")
def backtest(body: Analyze, _: User = Depends(approved)):
    _, frame = fetch_analysis_data(body)
    try:
        return simple_backtest(frame)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# --------------------------------------------------
# RISK / JOURNAL / PRIVATE ACCOUNT READS
# --------------------------------------------------

@app.post("/risk/position-size")
def position_size(body: RiskRequest, _: User = Depends(approved)):
    try:
        quantity = size_for_risk(
            body.equity,
            body.entry,
            body.stop_loss,
            body.risk_pct,
            body.contract_multiplier,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "estimated_contract_quantity": quantity,
        "risk_cash": round(body.equity * body.risk_pct / 100, 2),
        "note": "Confirm the exchange contract multiplier, minimum quantity, tick size, fees, slippage and margin before using this estimate.",
    }


@app.get("/account/wallet")
def wallet(db: Session = Depends(get_db), user: User = Depends(approved)):
    try:
        return user_client(db, user).wallet()
    except (DeltaAPIError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/account/positions")
def positions(db: Session = Depends(get_db), user: User = Depends(approved)):
    try:
        return user_client(db, user).positions()
    except (DeltaAPIError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/journal")
def create_journal_entry(
    body: JournalEntry,
    db: Session = Depends(get_db),
    user: User = Depends(approved),
):
    side = body.side.upper()
    if side not in {"LONG", "SHORT"}:
        raise HTTPException(status_code=400, detail="Side must be LONG or SHORT")

    record = TradeRecord(
        user_id=user.id,
        symbol=body.symbol.strip().upper(),
        side=side,
        entry_price=body.entry_price,
        quantity=body.quantity,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "status": record.status}


@app.get("/journal")
def list_journal(db: Session = Depends(get_db), user: User = Depends(approved)):
    records = db.scalars(
        select(TradeRecord)
        .where(TradeRecord.user_id == user.id)
        .order_by(TradeRecord.created_at.desc())
        .limit(200)
    ).all()
    return [
        {
            "id": record.id,
            "symbol": record.symbol,
            "side": record.side,
            "entry_price": record.entry_price,
            "exit_price": record.exit_price,
            "quantity": record.quantity,
            "pnl": record.pnl,
            "status": record.status,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
        for record in records
    ]


# Deliberately disabled: there is no order-placement implementation in this build.
@app.post("/trading/demo-order")
def disabled_demo_order(_: User = Depends(approved)):
    raise HTTPException(
        status_code=403,
        detail="Order execution is disabled in this build. Use analysis and paper review only.",
    )
