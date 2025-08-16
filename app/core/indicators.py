import numpy as np
import pandas as pd

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]; low = df["low"]; close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.clip(lower=0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def anchored_vwap(df: pd.DataFrame, anchor_idx: int) -> float:
    """Simple anchored VWAP from anchor_idx to current."""
    if anchor_idx < 0:
        anchor_idx = 0
    prices = df["close"].values
    vols = df["volume"].values
    p = prices[anchor_idx:]
    v = vols[anchor_idx:]
    if v.sum() == 0:
        return float(p[-1])
    return float((p * v).sum() / v.sum())
