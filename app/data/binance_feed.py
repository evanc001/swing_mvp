import requests
import pandas as pd
from typing import Optional, List
from ..config.settings import BINANCE_BASE

INTERVAL_MAP = {
    "4h": "4h",
    "1d": "1d",
}

class MarketDataProvider:
    """Public REST Spot data from Binance."""
    def __init__(self, base_url: str = BINANCE_BASE, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def klines(self, symbol: str, interval: str = "4h", limit: int = 500) -> pd.DataFrame:
        assert interval in INTERVAL_MAP, f"Unsupported interval: {interval}"
        url = f"{self.base_url}/api/v3/klines"
        params = {"symbol": symbol.upper(), "interval": INTERVAL_MAP[interval], "limit": int(limit)}
        r = requests.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        raw = r.json()
        cols = [
            "open_time","open","high","low","close","volume","close_time","qav","trades","taker_base","taker_quote","ignore"
        ]
        df = pd.DataFrame(raw, columns=cols)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
        for c in ["open","high","low","close","volume"]:
            df[c] = df[c].astype(float)
        df = df[["open_time","open","high","low","close","volume","close_time"]]
        df.rename(columns={"open_time":"time"}, inplace=True)
        df.set_index("time", inplace=True)
        return df

    def depth(self, symbol: str, limit: int = 50) -> dict:
        url = f"{self.base_url}/api/v3/depth"
        params = {"symbol": symbol.upper(), "limit": int(limit)}
        r = requests.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def exchange_info(self, symbol: str) -> dict:
        url = f"{self.base_url}/api/v3/exchangeInfo"
        params = {"symbol": symbol.upper()}
        r = requests.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()
