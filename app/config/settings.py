SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
BASE_CAPITAL = 100.0  # $
RISK_STEPS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]  # %
MIN_RR = 1.5
DEFAULT_TF = "4h"  # options: "4h", "1d"
BINANCE_BASE = "https://api.binance.com"
CACHE_TTL = 60  # seconds for market data cache
JOURNAL_CSV = "journal.csv"

# LLM (optional)
OPENAI_MODEL = "gpt-4o-mini"  # override via secrets/env if needed
