from typing import Optional, Tuple
import pandas as pd
from ..core.indicators import ema, atr
from .base import StrategyBase

class PullbackEMA21(StrategyBase):
    name = "Откат к EMA21"

    def signal(self) -> Optional[Tuple[float, float]]:
        df = self.df.copy()
        df["ema21"] = ema(df["close"], 21)
        df["atr14"] = atr(df, 14)
        c = float(df["close"].iloc[-1])
        e = float(df["ema21"].iloc[-1])
        a = float(df["atr14"].iloc[-1])
        if e > float(df["ema21"].iloc[-5]) and abs(c - e) <= 0.2 * a:
            entry = c
            stop = min(float(df["low"].iloc[-1]), e - 1.5 * a)
            return (entry, stop)
        return None
