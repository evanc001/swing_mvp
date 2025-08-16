import time
import requests
import pandas as pd
from typing import Optional, List

BINANCE_MIRRORS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    # иногда официальное зеркало с публичными данными работает стабильнее в облаках:
    "https://data-api.binance.vision"
]

INTERVAL_MAP = {"4h": "4h", "1d": "1d"}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StreamlitBinanceClient/1.0",
    "Accept": "application/json"
}

class MarketDataProvider:
    """Публичные REST-данные (Spot) с зеркалами и ретраями."""

    def __init__(self, timeout: int = 12, retries: int = 3, backoff: float = 0.7):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def _request(self, path: str, params: dict) -> dict | list:
        last_err = None
        for mirror in BINANCE_MIRRORS:
            url = f"{mirror}/api/v3/{path.lstrip('/')}"
            for attempt in range(self.retries):
                try:
                    r = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=self.timeout)
                    # 429 (rate limit) или 418/451/403 — даём ещё шанс и пробуем след. зеркало
                    if r.status_code in (429, 418):
                        time.sleep(self.backoff * (attempt + 1))
                        continue
                    if r.status_code in (451, 403, 502, 503, 520, 522):
                        # попробуем другое зеркало
                        last_err = Exception(f"{r.status_code} from {url}: {r.text[:200]}")
                        break
                    r.raise_for_status()
                    return r.json()
                except requests.RequestException as e:
                    last_err = e
                    time.sleep(self.backoff * (attempt + 1))
            # следующая итерация — другое зеркало
        # если тут — все зеркала умерли
        raise RuntimeError(f"Binance API error: {last_err}")

    def klines(self, symbol: str, interval: str = "4h", limit: int = 500) -> pd.DataFrame:
        assert interval in INTERVAL_MAP, f"Unsupported interval: {interval}"
        raw = self._request("klines", {
            "symbol": symbol.upper(),
            "interval": INTERVAL_MAP[interval],
            "limit": int(limit)
        })
        cols = ["open_time","open","high","low","close","volume","close_time","qav","trades","taker_base","taker_quote","ignore"]
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
        return self._request("depth", {"symbol": symbol.upper(), "limit": int(limit)})

    def exchange_info(self, symbol: str) -> dict:
        return self._request("exchangeInfo", {"symbol": symbol.upper()})
