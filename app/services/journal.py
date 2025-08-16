import os
import csv
from typing import Dict

class TradeJournal:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.fields = [
            "time","symbol","tf","setup","entry","stop","tp1","tp2","tp3","rr_min","risk_%","risk_$","qty","decision"
        ]
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.fields)
                writer.writeheader()

    def append(self, row: Dict):
        row2 = {k: row.get(k, "") for k in self.fields}
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.fields)
            writer.writerow(row2)
