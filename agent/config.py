"""Static configuration. No logic lives here."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "market.db"

# Free-tier websocket caps subscriptions at 30 symbols. All 30 are underlyings:
# nothing subscribes to option contracts today, so the reserve the first draft
# set aside for them was idle. Streaming held options again means dropping
# symbols here first - _stream_once() raises rather than silently over-subscribing.
UNIVERSE = [
    # Index / sector ETFs and large caps - the original list. Liquid, but they
    # correlate hard with SPY, so a quiet tape leaves every one of them below
    # the 0.5-ADR trigger at once.
    "SPY", "QQQ", "IWM", "DIA",
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL",
    "TSLA", "AMD", "NFLX", "AVGO", "MU",
    "JPM", "XLF", "XLE", "COIN", "SMCI",
    # High-beta names, added so the screener has candidates that can clear
    # 0.5 ADR on a day the mega-caps do not move. Chosen for options liquidity
    # first - a wide spread just gets rejected by gates.approve() later.
    "PLTR", "MSTR", "HOOD", "ARM", "APP",
    "CVNA", "NET", "RDDT", "SHOP", "SOXL",
]

MAX_WS_SYMBOLS = 30


def api_keys() -> tuple[str, str]:
    """Read Alpaca credentials from the environment.

    Raises RuntimeError rather than returning None so a misconfigured
    process fails at startup instead of at the first API call.
    """
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError(
            "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set. "
            "Copy .env.example to .env and fill it in."
        )
    return key, secret
