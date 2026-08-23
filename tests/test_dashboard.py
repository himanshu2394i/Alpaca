"""Dashboard data shaping and rendering. No server, no network."""
import pytest

from agent import dashboard, store

POS = dict(underlying="SPY", right="call", qty=7, entry_price=2.00,
           entry_underlying=765.0, stop_underlying=760.0,
           target_underlying=775.0, expiry="2026-09-11")


def test_summary_of_an_empty_database(conn):
    s = dashboard.summary(conn)
    assert s["equity"] == 0.0 and s["open"] == 0 and s["closed"] == 0
    assert s["realised"] == 0.0 and s["win_rate"] is None


def test_summary_counts_and_realised_pnl(conn):
    store.record_equity(conn, "2026-08-24T14:00:00Z", 100_000)
    store.record_equity(conn, "2026-08-25T14:00:00Z", 101_500)
    store.open_position(conn, symbol="SPY260911C00765000",
                        entry_ts="2026-08-24T14:05:00Z", **POS)
    store.open_position(conn, symbol="SPY260911C00770000",
                        entry_ts="2026-08-24T14:06:00Z", **POS)
    store.close_position(conn, "SPY260911C00770000", exit_price=3.00,
                         exit_ts="2026-08-25T15:00:00Z", exit_reason="target")

    s = dashboard.summary(conn)
    assert s["equity"] == 101_500
    assert s["open"] == 1 and s["closed"] == 1
    assert s["realised"] == pytest.approx((3.00 - 2.00) * 7 * 100)
    assert s["win_rate"] == pytest.approx(1.0)


def test_realised_pnl_handles_losses_and_win_rate(conn):
    for i, exit_px in enumerate([3.00, 1.00, 1.20]):
        sym = f"SPY260911C0076{i}000"
        store.open_position(conn, symbol=sym, entry_ts=f"2026-08-24T14:0{i}:00Z", **POS)
        store.close_position(conn, sym, exit_price=exit_px,
                             exit_ts=f"2026-08-25T15:0{i}:00Z", exit_reason="r")
    s = dashboard.summary(conn)
    assert s["realised"] == pytest.approx((1.00 - 1.00 - 0.80) * 7 * 100)
    assert s["win_rate"] == pytest.approx(1 / 3)


def test_sparkline_of_a_flat_series_does_not_divide_by_zero(conn):
    store.record_equity(conn, "2026-08-24T14:00:00Z", 100_000)
    store.record_equity(conn, "2026-08-24T14:01:00Z", 100_000)
    svg = dashboard.sparkline(store.equity_series(conn))
    assert "<svg" in svg and "NaN" not in svg


def test_sparkline_is_empty_without_data(conn):
    assert "no equity" in dashboard.sparkline(store.equity_series(conn))


def test_sparkline_plots_every_point(conn):
    for i in range(5):
        store.record_equity(conn, f"2026-08-24T14:0{i}:00Z", 100_000 + i * 100)
    svg = dashboard.sparkline(store.equity_series(conn))
    assert svg.count(",") >= 5 and "NaN" not in svg


def test_render_escapes_text_from_the_database(conn):
    # Thesis text is written by the model; it must never become markup.
    store.record_decision(conn, "2026-08-24T14:00:00Z", "SPY", "entry",
                          detail="<script>alert(1)</script>", thesis="x & y")
    html = dashboard.render(conn)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html and "x &amp; y" in html


def test_render_includes_the_headline_numbers(conn):
    store.record_equity(conn, "2026-08-24T14:00:00Z", 101_500)
    store.open_position(conn, symbol="SPY260911C00765000",
                        entry_ts="2026-08-24T14:05:00Z", **POS)
    html = dashboard.render(conn)
    assert "101,500" in html
    assert "SPY260911C00765000" in html
    assert "<svg" in html


def test_render_works_on_an_empty_database(conn):
    html = dashboard.render(conn)
    assert "<html" in html.lower() and "no equity" in html
