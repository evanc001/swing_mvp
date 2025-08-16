from dataclasses import dataclass
from typing import List, Tuple, Optional
import pandas as pd
import numpy as np
from .indicators import ema, atr, anchored_vwap

@dataclass
class SwingPoint:
    idx: int
    price: float
    kind: str  # 'high' or 'low'

@dataclass
class Zone:
    kind: str  # 'demand' or 'supply'
    start_price: float
    end_price: float
    anchor_idx: int

class LevelBuilder:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.df["ema21"] = ema(self.df["close"], 21)
        self.df["ema50"] = ema(self.df["close"], 50)
        self.df["ema100"] = ema(self.df["close"], 100)
        self.df["atr14"] = atr(self.df, 14)

    def find_swings(self, lookback: int = 2) -> List[SwingPoint]:
        highs = self.df["high"].values
        lows = self.df["low"].values
        swings: List[SwingPoint] = []
        for i in range(lookback, len(self.df) - lookback):
            window_h = highs[i-lookback:i+lookback+1]
            window_l = lows[i-lookback:i+lookback+1]
            if highs[i] == window_h.max() and (highs[i] > window_h[:-1]).all() and (highs[i] > window_h[1:]).all():
                swings.append(SwingPoint(i, float(highs[i]), 'high'))
            if lows[i] == window_l.min() and (lows[i] < window_l[:-1]).all() and (lows[i] < window_l[1:]).all():
                swings.append(SwingPoint(i, float(lows[i]), 'low'))
        swings.sort(key=lambda s: s.idx)
        return swings

    def last_structure(self, swings: List[SwingPoint]) -> str:
        sh = [s for s in swings if s.kind=='high'][-3:]
        sl = [s for s in swings if s.kind=='low'][-3:]
        direction = "range"
        if len(sh) >= 2 and len(sl) >= 2:
            if sh[-1].price > sh[-2].price and sl[-1].price > sl[-2].price:
                direction = "up"
            elif sh[-1].price < sh[-2].price and sl[-1].price < sl[-2].price:
                direction = "down"
        return direction

    def bos(self, swings: List[SwingPoint]) -> Optional[Tuple[str,int,float]]:
        if len(swings) < 3:
            return None
        last = swings[-1]
        prev_same = [s for s in swings[:-1] if s.kind==last.kind]
        if not prev_same:
            return None
        prev = prev_same[-1]
        if last.kind=='high' and last.price > prev.price:
            return ("bull", last.idx, last.price)
        if last.kind=='low' and last.price < prev.price:
            return ("bear", last.idx, last.price)
        return None

    def impulse_zone(self, kind: str, bars_back: int = 3) -> Optional[Zone]:
        swings = self.find_swings()
        b = self.bos(swings)
        if b is None:
            return None
        side, idx, _ = b
        if (kind=="demand" and side!="bull") or (kind=="supply" and side!="bear"):
            return None
        base_idx = max(0, idx - bars_back)
        atr_buf = float(self.df["atr14"].iloc[idx]) * 0.25
        if kind == "demand":
            lo = float(self.df["low"].iloc[base_idx])
            hi = float(self.df["close"].iloc[base_idx])
        else:
            hi = float(self.df["high"].iloc[base_idx])
            lo = float(self.df["close"].iloc[base_idx])
        lo2 = max(0.0, lo - atr_buf)
        hi2 = hi + atr_buf
        return Zone(kind=kind, start_price=lo2 if kind=="demand" else lo, end_price=hi2 if kind=="supply" else hi, anchor_idx=base_idx)

    def htf_trend(self) -> str:
        e100 = self.df["ema100"]
        slope = float(e100.iloc[-1] - e100.iloc[-10])
        if slope > 0 and float(self.df["close"].iloc[-1]) > float(self.df["ema50"].iloc[-1]):
            return "up"
        if slope < 0 and float(self.df["close"].iloc[-1]) < float(self.df["ema50"].iloc[-1]):
            return "down"
        return "range"

    def build_summary(self) -> dict:
        swings = self.find_swings()
        structure = self.last_structure(swings)
        bos_info = self.bos(swings)
        demand = self.impulse_zone("demand")
        supply = self.impulse_zone("supply")
        return {
            "structure": structure,
            "bos": bos_info,
            "demand": demand,
            "supply": supply,
            "ema21": float(self.df["ema21"].iloc[-1]),
            "ema50": float(self.df["ema50"].iloc[-1]),
            "ema100": float(self.df["ema100"].iloc[-1]),
            "atr14": float(self.df["atr14"].iloc[-1]),
        }
