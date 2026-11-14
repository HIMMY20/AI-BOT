from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
def utcnow(): return datetime.now(timezone.utc)
class User(Base):
    __tablename__="users"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    email:Mapped[str]=mapped_column(String(255),unique=True,index=True)
    full_name:Mapped[str]=mapped_column(String(160))
    password_hash:Mapped[str]=mapped_column(String(255))
    role:Mapped[str]=mapped_column(String(20),default="user")
    status:Mapped[str]=mapped_column(String(20),default="pending")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
class DeltaCredential(Base):
    __tablename__="delta_credentials"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id"),unique=True,index=True)
    api_key_enc:Mapped[str]=mapped_column(Text)
    api_secret_enc:Mapped[str]=mapped_column(Text)
    environment:Mapped[str]=mapped_column(String(10),default="demo")
class AuditLog(Base):
    __tablename__="audit_logs"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    actor_id:Mapped[int|None]=mapped_column(Integer,nullable=True)
    target_id:Mapped[int|None]=mapped_column(Integer,nullable=True)
    action:Mapped[str]=mapped_column(String(80))
    details:Mapped[str]=mapped_column(Text,default="")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
class TradeRecord(Base):
    __tablename__="trade_records"
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey("users.id"),index=True)
    symbol:Mapped[str]=mapped_column(String(80))
    side:Mapped[str]=mapped_column(String(10))
    entry_price:Mapped[float]=mapped_column(Float)
    exit_price:Mapped[float|None]=mapped_column(Float,nullable=True)
    quantity:Mapped[float]=mapped_column(Float)
    pnl:Mapped[float|None]=mapped_column(Float,nullable=True)
    status:Mapped[str]=mapped_column(String(20),default="open")
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
