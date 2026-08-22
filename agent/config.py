"""Static configuration. No logic lives here."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "market.db"

# Free-tier websocket caps subscriptions at 30 symbols.
# 20 underlyings here; 10 slots reserved for held option contracts.
UNIVERSE = [
    "SPY", "QQQ", "IWM", "DIA",
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL",
    "TSLA", "AMD", "NFLX", "AVGO", "MU",
    "JPM", "XLF", "XLE", "COIN", "SMCI",
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
