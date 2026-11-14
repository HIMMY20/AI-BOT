from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Delta AI Trading Platform"
    database_url: str = "sqlite:///./data/delta_ai.db"
    jwt_secret: str = ""
    fernet_key: str = ""
    admin_email: str = "owner@example.com"
    admin_password: str = ""
    delta_env: str = "live"  # Public market data environment; independent of user credentials.
    enable_demo_orders: bool = False
    enable_live_orders: bool = False
    risk_per_trade_pct: float = 0.5
    max_daily_loss_pct: float = 2.0
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()
