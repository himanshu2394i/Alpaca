from datetime import datetime, timedelta, timezone


def make_bars(symbol="SPY", n=10, start_price=100.0, step=1.0):
    """Deterministic ascending bars, one minute apart, from 2026-08-24T13:30:00Z."""
    t0 = datetime(2026, 8, 24, 13, 30, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        price = start_price + i * step
        ts = (t0 + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append((symbol, ts, price, price + 0.5, price - 0.5, price, 1000 + i))
    return rows
