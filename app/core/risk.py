from dataclasses import dataclass
from typing import Optional

@dataclass
class RiskAdvice:
    bracket: str  # 'low', 'mid', 'high'
    percent: float
    reason: str

class RiskScorer:
    def __init__(self, min_rr: float = 1.5):
        self.min_rr = min_rr

    def recommend(self, context: dict, against_htf: bool, near_news: bool) -> RiskAdvice:
        score = 0
        if context.get("structure") == "up":
            score += 2
        elif context.get("structure") == "down":
            score += 0
        else:
            score += 1
        if context.get("bos"):
            score += 2
        if context.get("demand") or context.get("supply"):
            score += 2
        if near_news:
            score -= 2
        if against_htf:
            score -= 2
        if score <= 2:
            return RiskAdvice("low", 0.5, f"score={score}")
        if score <= 5:
            return RiskAdvice("mid", 1.5, f"score={score}")
        if score <= 7:
            return RiskAdvice("high", 2.0, f"score={score}")
        return RiskAdvice("high", 2.5, f"score={score}")

class PositionSizer:
    def __init__(self, capital: float):
        self.capital = capital

    def size(self, entry: float, stop: float, risk_pct: float) -> dict:
        risk_dollars = self.capital * (risk_pct / 100.0)
        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            return {"qty": 0.0, "risk_$": 0.0}
        qty = risk_dollars / stop_distance
        return {"qty": round(qty, 6), "risk_$": round(risk_dollars, 2)}
