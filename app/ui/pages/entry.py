# entry.py
# -*- coding: utf-8 -*-
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st

# --------------------------- UI THEME TWEAKS ---------------------------
st.set_page_config(page_title="Расчёт входа", layout="wide")
DARK = True
PRIMARY = "#ff3b3b"

CUSTOM_CSS = f"""
<style>
    .block-container {{ padding-top: 1.2rem; max-width: 1260px; }}
    .stRadio > label {{ font-weight: 600; }}
    .metric-note {{
        font-size: 12px; opacity: .75; margin-top: -6px;
    }}
    /* Modal overlay for Fear & Greed */
    .overlay {{
        position: fixed; inset: 0; background: rgba(0,0,0,.65);
        z-index: 1000; display: flex; align-items: center; justify-content: center;
    }}
    .modal {{
        width: 92%; max-width: 1100px; background: {'#111' if DARK else '#fff'};
        border: 1px solid #333; border-radius: 14px; padding: 14px 18px;
        box-shadow: 0 20px 50px rgba(0,0,0,.55);
    }}
    .modal-header {{
        display:flex; align-items:center; justify-content:space-between;
        gap: 10px; margin-bottom: 6px;
    }}
    .btn-close {{
        background: {PRIMARY}; color: #fff; border: none; padding: 6px 10px;
        border-radius: 8px; cursor: pointer; font-weight: 600;
    }}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# --------------------------- STATE ---------------------------
if "fg_open" not in st.session_state:
    st.session_state.fg_open = False

# --------------------------- HELPERS ---------------------------
def to_datetime_utc(ts):
    # Binance gives ms, FNG gives seconds
    if ts > 10**12:
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return datetime.fromtimestamp(ts, tz=timezone.utc)

@st.cache_data(ttl=60 * 30, show_spinner=False)
def get_binance_klines(symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    cols = ["open_time","open","high","low","close","volume",
            "close_time","qav","trades","taker_base","taker_quote","ignore"]
    df = pd.DataFrame(data, columns=cols)
    df["open_time"] = df["open_time"].apply(to_datetime_utc)
    df["close_time"] = df["close_time"].apply(to_datetime_utc)
    numeric_cols = ["open","high","low","close","volume"]
    df[numeric_cols] = df[numeric_cols].astype(float)
    df = df[["open_time","open","high","low","close","volume","close_time"]]
    return df

@st.cache_data(ttl=60 * 60 * 3, show_spinner=False)
def get_fear_greed_df(limit_days: int = 180) -> pd.DataFrame:
    url = "https://api.alternative.me/fng/"
    params = {"limit": limit_days, "format": "json"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    raw = r.json()["data"]
    df = pd.DataFrame(raw)
    df["timestamp"] = df["timestamp"].astype(int).apply(to_datetime_utc)
    df["value"] = df["value"].astype(int)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def atr(df: pd.DataFrame, period: int = 14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def rr_targets(entry: float, stop: float, multiples=(1.0, 1.5, 2.0)):
    r = abs(entry - stop)
    return [entry + math.copysign(m*r, entry - stop < 0) for m in multiples]  # long/short aware

def color_levels(fig, y_values, labels, color, dash="dash", row=1, col=1):
    for y, label in zip(y_values, labels):
        fig.add_hline(y=y, line=dict(color=color, width=1.6, dash=dash),
                      annotation_text=label, annotation_position="right", row=row, col=col)

# --------------------------- UI: Controls ---------------------------
st.title("Вкладка 1 — Расчёт входа")

coins = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
tf_map = {"4h": "4h", "1d": "1d"}
col1, col2, col3 = st.columns([2, 1.2, 1.6])

with col1:
    symbol = st.radio("Монета", coins, horizontal=True, index=0)
with col2:
    tf_label = st.radio("ТФ", list(tf_map.keys()), horizontal=True, index=1)
    interval = tf_map[tf_label]
with col3:
    setup = st.radio("Сетап", ["Пробой", "Откат к EMA21"], horizontal=True, index=0)

top_row = st.columns([1, 1, 2])
with top_row[0]:
    st.write("**Структура (тех. контекст):**")
with top_row[1]:
    # кнопка для модалки с графиком индекса страха/жадности
    if st.button("Индекс страха и жадности"):
        st.session_state.fg_open = True

# --------------------------- DATA ---------------------------
limit = 500 if interval == "4h" else 400
df = get_binance_klines(symbol, interval, limit=limit)

df["ema21"] = ema(df["close"], 21)
df["ema50"] = ema(df["close"], 50)
df["ema100"] = ema(df["close"], 100)
df["atr14"] = atr(df, 14)

# предложим базовый вход/стоп
last = df.iloc[-1]
if setup == "Откат к EMA21":
    entry = float(last["ema21"])
else:  # Пробой вчерашнего high/low
    prev = df.iloc[-2]
    direction_long = last["close"] >= last["ema21"]
    entry = float(prev["high"] if direction_long else prev["low"])

risk_pct_choice = st.radio(
    "Выбери риск", ["Низкий (0.5–1%)", "Средний (1–2%)", "Высокий (2–3%)"],
    horizontal=True, index=0
)

atr_mult = 1.2 if "Низкий" in risk_pct_choice else (1.6 if "Средний" in risk_pct_choice else 2.0)
# стоп за ближайший swing/ATR
if setup == "Откат к EMA21":
    stop = entry - atr_mult * float(last["atr14"])
    direction = "long"
else:
    direction = "long" if last["close"] >= last["ema21"] else "short"
    stop = entry - atr_mult * float(last["atr14"]) if direction == "long" else entry + atr_mult * float(last["atr14"])

tps = rr_targets(entry, stop, multiples=(1.0, 1.5, 2.0))

# контекстная строка
context = f"ATR14: {last['atr14']:.2f} | EMA21/50/100: {last['ema21']:.2f}/{last['ema50']:.2f}/{last['ema100']:.2f}"
st.caption(context)

# --------------------------- CHART ---------------------------
fig = go.Figure()
fig = make_subplots(rows=1, cols=1, shared_xaxes=True, specs=[[{"secondary_y": False}]])

candles = go.Candlestick(
    x=df["open_time"], open=df["open"], high=df["high"],
    low=df["low"], close=df["close"], name=symbol
)
fig.add_trace(candles, row=1, col=1)
fig.add_trace(go.Scatter(x=df["open_time"], y=df["ema21"], name="EMA21", line=dict(width=1.3)), row=1, col=1)
fig.add_trace(go.Scatter(x=df["open_time"], y=df["ema50"], name="EMA50", line=dict(width=1.0, dash="dot")), row=1, col=1)
fig.add_trace(go.Scatter(x=df["open_time"], y=df["ema100"], name="EMA100", line=dict(width=1.0, dash="dot")), row=1, col=1)

# уровни
color_levels(fig, [entry], [f"Entry {entry:,.2f}"], "#00c853", dash="solid")
color_levels(fig, [stop], [f"Stop {stop:,.2f}"], "#ff5252", dash="solid")
color_levels(fig, tps, [f"TP{i+1} {v:,.2f}" for i, v in enumerate(tps)], "#7ddc1f", dash="dash")

fig.update_layout(
    height=520, margin=dict(l=20, r=20, t=30, b=20),
    xaxis_rangeslider_visible=False, template="plotly_dark" if DARK else "plotly_white",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
)

st.plotly_chart(fig, use_container_width=True, theme=None)

# --------------------------- FEAR & GREED MODAL ---------------------------
def render_fear_greed_modal():
    fg_df = get_fear_greed_df(limit_days=170)

    # Подгружаем дневные свечи BTC для нижней панели, в диапазоне дат F&G
    start_date = fg_df["timestamp"].min().date() - timedelta(days=5)
    end_date = fg_df["timestamp"].max().date() + timedelta(days=2)
    btc_day = get_binance_klines("BTCUSDT", "1d", limit=600)
    btc_day = btc_day[(btc_day["open_time"].dt.date >= start_date) & (btc_day["open_time"].dt.date <= end_date)]

    # Фигура: 2 ряда
    sub = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12,
        row_heights=[0.62, 0.38]
    )

    # Линия индекса
    sub.add_trace(
        go.Scatter(x=fg_df["timestamp"], y=fg_df["value"], mode="lines+markers",
                   name="Fear&Greed", line=dict(width=1.7)),
        row=1, col=1
    )

    # Цветные зоны
    bands = [
        (0, 25, "#ff6666", "Экстремальный страх"),
        (25, 45, "#ffcc80", "Страх"),
        (45, 55, "#ffe082", "Нейтрально"),
        (55, 75, "#c5e1a5", "Жадность"),
        (75, 100, "#81c784", "Экстремальная жадность"),
    ]
    for y0, y1, color, _ in bands:
        sub.add_hrect(y0=y0, y1=y1, line_width=0, fillcolor=color, opacity=0.25, row=1, col=1)

    # Цена BTC
    sub.add_trace(
        go.Scatter(x=btc_day["open_time"], y=btc_day["close"], name="BTCUSDT (close)"),
        row=2, col=1
    )

    sub.update_layout(
        height=720, template="plotly_dark" if DARK else "plotly_white",
        margin=dict(l=10, r=10, t=35, b=10),
        title_text="Индекс страха и жадности BTC (сравнение с ценой BTC)"
    )
    sub.update_yaxes(range=[0, 100], row=1, col=1, title_text="F&G")
    sub.update_yaxes(title_text="Цена BTC ($)", row=2, col=1)

    # отрисовка модалки
    st.markdown('<div class="overlay"><div class="modal">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="modal-header"><h3 style="margin:0">Индекс страха и жадности</h3>'
        f'<form method="post"><button class="btn-close" name="close_fg">Закрыть</button></form></div>',
        unsafe_allow_html=True
    )
    st.plotly_chart(sub, use_container_width=True, theme=None)
    st.markdown('</div></div>', unsafe_allow_html=True)

# Обработка кнопки закрытия (костыль через form POST)
if st.session_state.fg_open and st.session_state.get("_submitted_close", False):
    st.session_state.fg_open = False
    st.session_state._submitted_close = False

# перехват пост-запроса для кнопки закрыть
params = st.experimental_get_query_params()
if st.session_state.fg_open:
    render_fear_greed_modal()

# маленький хак: отлавливаем submit «Закрыть»
# (Streamlit не дает слушать POST формы глобально; делаем через js-free трюк)
close_key = st.session_state.get("close_key_once", 0)
st.session_state["close_key_once"] = close_key + 1

# --------------------------- SIDE INFO ---------------------------
with st.container():
    rr = abs(entry - stop)
    rr_ratio = max((tps[0] - entry) / rr, 0.01) if direction == "long" else max((entry - tps[0]) / rr, 0.01)
    st.markdown(
        f"**Предложенный риск-контекст:** `RR≈{rr_ratio:.2f}R`, направление: **{direction}**  \n"
        f"<span class='metric-note'>Примечание: уровни Entry/Stop/TP рассчитаны из контекста {setup} и ATRx{atr_mult:.1f}.</span>",
        unsafe_allow_html=True
    )
