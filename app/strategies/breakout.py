from typing import Optional, Tuple
import pandas as pd
from .base import StrategyBase

class BreakoutRange(StrategyBase):
    name = "Пробой диапазона"

    def signal(self) -> Optional[Tuple[float, float]]:
        df = self.df.copy()
        hi = float(df["high"].iloc[-20:].max())
        lo = float(df["low"].iloc[-20:].min())
        close = float(df["close"].iloc[-1])
        if close > hi:
            stop = (hi + lo) / 2
            return (close, stop)
        if close < lo:
            stop = (hi + lo) / 2
            return (close, stop)
        return None
