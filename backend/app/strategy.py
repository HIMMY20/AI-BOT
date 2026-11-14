"""Rule-based market analysis. Signals are estimates, not guaranteed outcomes."""

import numpy as np
import pandas as pd


ALIASES = {
    "time": ("time", "timestamp", "t"),
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c"),
    "volume": ("volume", "v"),
}


def frame_from_candles(rows):
    """Normalize Delta candle objects or [time, open, high, low, close, volume] rows."""
    if isinstance(rows, dict):
        rows = rows.get("result", rows.get("candles", []))
    if rows is None or len(rows) == 0:
        raise ValueError("Delta Exchange returned no candles for this symbol/timeframe")

    if isinstance(rows[0], dict):
        source = pd.DataFrame(rows)
        source.columns = [str(column).lower() for column in source.columns]
        normalized = {}
        for target, candidates in ALIASES.items():
            for candidate in candidates:
                if candidate in source.columns:
                    normalized[target] = source[candidate]
                    break
        frame = pd.DataFrame(normalized)
    else:
        # Delta history candle arrays are commonly [time, open, high, low, close, volume].
        frame = pd.DataFrame(
            rows,
            columns=["time", "open", "high", "low", "close", "volume"],
        )

    for column in ("open", "high", "low", "close"):
        if column not in frame.columns:
            raise ValueError(f"Candle response is missing '{column}'")
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if "volume" not in frame.columns:
        frame["volume"] = 0.0
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce").fillna(0.0)

    if "time" in frame.columns:
        numeric_time = pd.to_numeric(frame["time"], errors="coerce")
        if numeric_time.notna().sum() == 0:
            parsed_time = pd.to_datetime(frame["time"], utc=True, errors="coerce")
            frame["time"] = parsed_time.astype("int64") // 10**9
            frame.loc[parsed_time.isna(), "time"] = np.nan
        else:
            frame["time"] = numeric_time
        frame = frame.dropna(subset=["time"])

    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame = frame[
        (frame["open"] > 0)
        & (frame["high"] > 0)
        & (frame["low"] > 0)
        & (frame["close"] > 0)
        & (frame["high"] >= frame["low"])
    ]

    if "time" in frame.columns:
        frame = frame.sort_values("time").drop_duplicates("time", keep="last")
    frame = frame.reset_index(drop=True)

    if len(frame) < 60:
        raise ValueError(f"Only {len(frame)} valid candles; at least 60 are required")
    return frame


def enrich(frame):
    x = frame.copy()
    close, high, low, volume = x["close"], x["high"], x["low"], x["volume"]

    for period in (9, 21, 50, 200):
        x[f"ema{period}"] = close.ewm(span=period, adjust=False).mean()

    change = close.diff()
    gains = change.clip(lower=0)
    losses = -change.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / 14, adjust=False).mean()
    average_loss = losses.ewm(alpha=1 / 14, adjust=False).mean()
    rs = average_gain / average_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.where(average_loss != 0, 100.0)
    rsi = rsi.where(average_gain != 0, 0.0)
    x["rsi"] = rsi.fillna(50)

    macd_fast = close.ewm(span=12, adjust=False).mean()
    macd_slow = close.ewm(span=26, adjust=False).mean()
    x["macd"] = macd_fast - macd_slow
    x["macd_signal"] = x["macd"].ewm(span=9, adjust=False).mean()
    x["macd_histogram"] = x["macd"] - x["macd_signal"]

    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    x["atr"] = true_range.ewm(alpha=1 / 14, adjust=False).mean()

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=x.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=x.index
    )
    atr_safe = x["atr"].replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1 / 14, adjust=False).mean() / atr_safe
    minus_di = 100 * minus_dm.ewm(alpha=1 / 14, adjust=False).mean() / atr_safe
    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    x["adx"] = dx.ewm(alpha=1 / 14, adjust=False).mean().fillna(0)

    typical_price = (high + low + close) / 3
    rolling_volume = volume.rolling(20, min_periods=1).sum()
    x["vwap"] = (
        (typical_price * volume).rolling(20, min_periods=1).sum()
        / rolling_volume.replace(0, np.nan)
    ).fillna(close)

    middle = close.rolling(20).mean()
    deviation = close.rolling(20).std()
    x["bb_middle"] = middle
    x["bb_upper"] = middle + 2 * deviation
    x["bb_lower"] = middle - 2 * deviation
    return x


def signal(frame, symbol, tf):
    if frame is None or len(frame) < 60:
        raise ValueError("At least 60 valid candles are required for analysis")

    x = enrich(frame)
    # Use the last completed bar so a forming candle does not change the signal intrabar.
    row = x.iloc[-2]
    fields = [
        "close", "atr", "rsi", "ema9", "ema21", "ema50", "ema200",
        "macd", "macd_signal", "adx", "vwap",
    ]
    if any(pd.isna(row[field]) for field in fields):
        raise ValueError("Indicator calculation is incomplete; fetch more candles")

    price = float(row["close"])
    atr = float(row["atr"])
    rsi = float(row["rsi"])
    adx = float(row["adx"])

    long_checks = {
        "EMA trend": row["ema9"] > row["ema21"] > row["ema50"],
        "EMA 200": price > row["ema200"],
        "MACD momentum": row["macd"] > row["macd_signal"],
        "RSI momentum": 50 < rsi < 70,
        "VWAP": price > row["vwap"],
        "ADX strength": adx >= 18,
    }
    short_checks = {
        "EMA trend": row["ema9"] < row["ema21"] < row["ema50"],
        "EMA 200": price < row["ema200"],
        "MACD momentum": row["macd"] < row["macd_signal"],
        "RSI momentum": 30 < rsi < 50,
        "VWAP": price < row["vwap"],
        "ADX strength": adx >= 18,
    }

    long_count = sum(bool(value) for value in long_checks.values())
    short_count = sum(bool(value) for value in short_checks.values())

    # Conservative filter: if conditions disagree or trend is weak, return WAIT.
    side = "WAIT"
    if long_count >= 5 and long_count > short_count and adx >= 18 and rsi < 70:
        side = "LONG"
    elif short_count >= 5 and short_count > long_count and adx >= 18 and rsi > 30:
        side = "SHORT"

    entry = price
    stop_loss = None
    targets = []
    target_profit_pct = []
    risk_reward = []

    if side == "LONG":
        stop_loss = entry - 1.5 * atr
        risk_distance = entry - stop_loss
        targets = [entry + risk_distance, entry + 2 * risk_distance, entry + 3 * risk_distance]
    elif side == "SHORT":
        stop_loss = entry + 1.5 * atr
        risk_distance = stop_loss - entry
        targets = [entry - risk_distance, entry - 2 * risk_distance, entry - 3 * risk_distance]

    if side != "WAIT":
        target_profit_pct = [round(abs((target - entry) / entry) * 100, 4) for target in targets]
        risk_reward = [1.0, 2.0, 3.0]

    # Always report the indicator direction, including when the final decision is WAIT.
    if side == "LONG":
        vote_direction = "LONG"
    elif side == "SHORT":
        vote_direction = "SHORT"
    else:
        vote_direction = "LONG" if long_count > short_count else "SHORT" if short_count > long_count else "NONE"

    selected_checks = long_checks if vote_direction == "LONG" else short_checks if vote_direction == "SHORT" else None
    opposite_checks = short_checks if vote_direction == "LONG" else long_checks
    votes = {}
    for name in long_checks:
        if name == "ADX strength" and adx < 18:
            votes[name] = "Weak"
        elif selected_checks is None:
            votes[name] = "Neutral"
        elif selected_checks[name]:
            votes[name] = "Bullish" if vote_direction == "LONG" else "Bearish"
        elif opposite_checks[name]:
            votes[name] = "Bearish" if vote_direction == "LONG" else "Bullish"
        else:
            votes[name] = "Not confirmed"

    score = round(max(long_count, short_count) / 6 * 100, 1)

    return {
        "symbol": str(symbol).upper(),
        "timeframe": tf,
        "resolution": tf,
        "candle_time": int(row["time"]) if "time" in row.index and pd.notna(row["time"]) else None,
        "signal": side,
        "entry": round(entry, 8),
        "stop_loss": round(stop_loss, 8) if stop_loss is not None else None,
        "targets": [round(value, 8) for value in targets],
        "target_profit_pct": target_profit_pct,
        "risk_reward": risk_reward,
        "score": score,
        "votes": votes,
        "indicators": {
            key: round(float(row[key]), 8)
            for key in (
                "ema9", "ema21", "ema50", "ema200", "rsi", "macd",
                "macd_signal", "macd_histogram", "atr", "adx", "vwap",
                "bb_middle", "bb_upper", "bb_lower",
            )
        },
        "status": "ANALYSIS_ONLY" if side != "WAIT" else "NO_TRADE",
        "disclaimer": (
            "Indicator agreement score is not a win probability. Targets are estimates, "
            "not guaranteed outcomes; fees, funding, slippage and contract sizing are excluded."
        ),
    }


def size_for_risk(equity, entry, stop, risk_pct, contract_multiplier=1):
    values = [equity, entry, stop, risk_pct, contract_multiplier]
    if any(not np.isfinite(float(value)) for value in values):
        raise ValueError("Risk inputs must be finite numbers")
    if equity <= 0 or entry <= 0 or stop <= 0 or contract_multiplier <= 0:
        raise ValueError("Equity, prices and contract multiplier must be positive")
    if not 0 < risk_pct <= 2:
        raise ValueError("risk_pct must be greater than 0 and no more than 2")
    loss_per_contract = abs(entry - stop) * contract_multiplier
    if loss_per_contract <= 0:
        raise ValueError("Entry and stop loss cannot be equal")
    return round((equity * risk_pct / 100) / loss_per_contract, 8)


def simple_backtest(frame, fee_rate=0.0005, slippage=0.0002):
    """Educational EMA crossover backtest; not a derivatives execution simulator."""
    if frame is None or len(frame) < 60:
        raise ValueError("At least 60 candles are required for backtesting")
    if fee_rate < 0 or slippage < 0:
        raise ValueError("Fee and slippage cannot be negative")

    x = enrich(frame)
    desired = np.where(x["ema9"] > x["ema21"], 1, np.where(x["ema9"] < x["ema21"], -1, 0))
    # A signal calculated at bar i becomes active from bar i+1.
    positions = pd.Series(desired, index=x.index).shift(1).fillna(0).to_numpy()
    market_returns = x["close"].pct_change().fillna(0).to_numpy()
    previous_positions = np.r_[0, positions[:-1]]
    turnover = np.abs(positions - previous_positions)
    transaction_cost = (fee_rate + slippage) * turnover
    strategy_returns = positions * market_returns - transaction_cost
    strategy_returns = np.maximum(strategy_returns, -0.999999)
    equity_curve = np.cumprod(1 + strategy_returns)
    peaks = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve / peaks - 1) * 100

    trade_events = int(np.count_nonzero(turnover))
    return {
        "trade_events": trade_events,
        "net_return_pct": round((float(equity_curve[-1]) - 1) * 100, 4),
        "max_drawdown_pct": round(float(np.min(drawdowns)), 4),
        "candles_tested": int(len(x)),
        "assumptions": (
            "Illustrative bar-based EMA crossover test only. It excludes funding, liquidation, "
            "contract multipliers, order-book depth and exchange execution effects."
        ),
    }
