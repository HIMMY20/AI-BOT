# Delta AI Trading Platform — refreshed project (v2.2)

A multi-user market-analysis workspace with FastAPI, React/Vite, Delta Exchange public market data, admin approval, per-user encrypted private API credentials, candlestick charts, rule-based LONG/SHORT/WAIT analysis, risk sizing estimate, backtest preview and a trade journal.

## Important limitations — read before use

- This is an **analysis and account-read foundation**, not a certified trading system.
- No strategy can guarantee profit. A signal score is indicator agreement, **not** a probability of winning.
- Target percentages show estimated price movement from the entry reference. They are **not actual account P&L** and exclude quantity, contract multiplier, fees, funding, slippage and liquidation effects.
- Public market data environment (`DELTA_ENV`) is separate from each user's private credential environment.
- Order placement is intentionally disabled in this build. Both demo and live order execution are unavailable.
- The scanner uses REST candle snapshots. It is not a low-latency WebSocket terminal.
- Validate symbols, candle timestamps, contract specifications and market-data freshness with Delta before relying on any analysis.
- If you provide this platform to other people in India, obtain professional legal/regulatory advice first.

## Requirements

- Windows 10/11
- Python 3.11 (recommended)
- Node.js 20 LTS
- Internet connection for Delta public market data and package installation

## 1. Configure backend (Windows PowerShell)

From the project root:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`setup.ps1` creates `backend/.env`, generates a JWT signing secret and Fernet encryption key, and asks you to create the first admin password. Keep `backend/.env` private. Never paste it into chat or commit it to Git.

If you do not have Python 3.11, install it first or use `python -m venv .venv` with a compatible Python 3.11/3.12 installation.

### Market data environment

Open `backend/.env` and set:

```env
DELTA_ENV=live
ENABLE_DEMO_ORDERS=false
ENABLE_LIVE_ORDERS=false
```

`DELTA_ENV=live` selects Delta India production **public market data**. It does not enable order placement. User API credentials are separately selected on the Connect Exchange page for private wallet/position reads.

## 2. Start backend

From the `backend` directory, with the virtual environment activated:

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

Check:

- Health: http://127.0.0.1:8000/health
- API docs: http://127.0.0.1:8000/docs

The first startup creates the admin account from `ADMIN_EMAIL` and `ADMIN_PASSWORD` in `.env`.

## 3. Start frontend

Open a **second PowerShell** window at the project root:

```powershell
cd frontend
npm install
$env:VITE_API_URL="http://127.0.0.1:8000"
npm run dev
```

Open http://localhost:5173

To create a production frontend build:

```powershell
npm run build
```

## 4. Admin and user workflow

1. Sign in using the admin email/password you set in `backend/.env`.
2. A new user registers from the Create account tab.
3. Open User Management as admin and approve the pending user.
4. The approved user can scan public market data without entering private API credentials.
5. For wallet/position reads, the user can save their own environment-matched Delta API key and secret in Connect Exchange. Credentials are encrypted at rest with Fernet.
6. Never enable withdrawal permissions on exchange API keys. Use least-privilege permissions and IP restrictions where available.

## 5. Scanner behavior

1. Open Market Scanner.
2. Enter a supported Delta symbol such as `BTCUSD`.
3. Select a timeframe and click Analyse market.
4. The backend fetches candles, calculates EMA 9/21/50/200, RSI, MACD, ATR, ADX, VWAP and Bollinger Bands, and returns LONG, SHORT or WAIT.
5. If the confluence filter is met, the UI displays an entry reference, ATR-derived stop, three estimated target levels, price-movement percentages, and chart overlays. Otherwise WAIT is returned.

The confluence filter is intentionally conservative and can return WAIT frequently. The indicator score is not a backtested win rate. Backtest is an educational EMA crossover simulation and does not model the full derivatives market.

## 6. Common Windows commands

Run backend syntax check:

```powershell
python -m py_compile app\main.py app\strategy.py app\delta.py app\config.py
```

Run frontend build:

```powershell
cd ..\frontend
npm run build
```

If the backend fails to start, inspect the first complete traceback in the backend terminal. Do not paste `.env` contents; redact all credentials and secrets.

## 7. Project structure

```text
backend/
  app/
    config.py       environment settings
    db.py           SQLAlchemy engine/session
    models.py       users, credentials, audit, journal models
    security.py     password hashing, JWT and Fernet encryption
    delta.py        Delta REST client (public + private reads)
    strategy.py     candle normalization, indicators, signals, risk sizing, backtest
    main.py         FastAPI routes and admin/user workflows
frontend/
  src/
    App.tsx         React dashboard and scanner
    api.ts          API client and token handling
    main.tsx        React entry point
    style.css       dashboard styles
setup.ps1           local environment bootstrap
```

## 8. Production hardening still required

PostgreSQL and migrations, secure refresh sessions, MFA, password reset/email verification, rate limiting, stronger audit retention, secrets manager/KMS, encryption-key rotation, WebSocket streaming and reconnects, market-data freshness checks, multi-tenant security tests, monitoring, backup/restore tests and independent security review. Order execution requires a separate carefully tested implementation and is not included here.
