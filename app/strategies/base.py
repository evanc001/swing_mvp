from abc import ABC, abstractmethod
from typing import Optional, Tuple
import pandas as pd

class StrategyBase(ABC):
    name: str = "Base"

    def __init__(self, df: pd.DataFrame):
        self.df = df

    @abstractmethod
    def signal(self) -> Optional[Tuple[float, float]]:
        """Return (entry, stop) or None."""
        raise NotImplementedError
