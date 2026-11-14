import math

from app.strategy import frame_from_candles, signal, simple_backtest, size_for_risk


def sample_rows(count=260):
    rows = []
    price = 100.0
    for index in range(count):
        price += 0.15 + math.sin(index / 8) * 0.3
        rows.append({
            "time": 1_700_000_000 + index * 900,
            "open": price - 0.1,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 100 + index,
        })
    return rows


def test_candle_normalization_objects_and_arrays():
    frame = frame_from_candles(sample_rows(80))
    assert len(frame) == 80
    array_rows = [[1_700_000_000 + i * 60, 100, 101, 99, 100.5, 10] for i in range(80)]
    assert len(frame_from_candles(array_rows)) == 80


def test_signal_contract_matches_frontend():
    frame = frame_from_candles(sample_rows())
    result = signal(frame, "BTCUSD", "15m")
    assert result["signal"] in {"LONG", "SHORT", "WAIT"}
    assert "score" in result
    assert isinstance(result["targets"], list)
    assert isinstance(result["votes"], dict)
    assert "timeframe" in result
    if result["signal"] == "WAIT":
        assert result["stop_loss"] is None
        assert result["targets"] == []
    else:
        assert len(result["targets"]) == 3
        assert len(result["target_profit_pct"]) == 3


def test_risk_size_and_backtest():
    assert size_for_risk(10_000, 100, 98, 0.5, 1) == 25
    result = simple_backtest(frame_from_candles(sample_rows()))
    assert result["candles_tested"] == 260
    assert "net_return_pct" in result
