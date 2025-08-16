import streamlit as st
import pandas as pd
import os
from ...config.settings import JOURNAL_CSV

METRICS = ["Winrate","Avg R","Expectancy","Max DD","Profit Factor"]

@st.cache_data
def load_journal() -> pd.DataFrame:
    if not os.path.exists(JOURNAL_CSV):
        return pd.DataFrame()
    return pd.read_csv(JOURNAL_CSV)

def compute_metrics(df: pd.DataFrame) -> dict:
    res = {m: None for m in METRICS}
    if df.empty:
        return res
    r = (df["tp2"] - df["entry"]).abs() / (df["entry"] - df["stop"]).abs()
    res["Avg R"] = float(r.mean()) if len(r) else None
    return res

def tab_reporting():
    st.subheader("Вкладка 2 — Отчётность")
    df = load_journal()
    if df.empty:
        st.info("Журнал пуст. Прими хотя бы один план на вкладке 1.")
        return
    st.dataframe(df.tail(50), use_container_width=True)
    metrics = compute_metrics(df)
    cols = st.columns(len(METRICS))
    for (k,v), c in zip(metrics.items(), cols):
        c.metric(k, f"{v:.2f}" if isinstance(v, float) else "—")
