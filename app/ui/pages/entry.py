import math
import random
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st

# ============================ THEME / CSS ============================
DARK = True
PRIMARY = "#ff3b3b"

PAGE_CSS = f"""
<style>
.block-container {{ padding-top: 1rem; max-width: 1260px; }}

.overlay {{
  position: fixed; inset: 0; background: rgba(0,0,0,.65);
  z-index: 9999; display: flex; align-items: center; justify-content: center;
}}
.modal {{
  width: 92%; max-width: 1120px; background: {'#0f1116' if DARK else '#fff'};
  border: 1px solid #2b2f36; border-radius: 14px; padding: 14px 18px;
  box-shadow: 0 20px 50px rgba(0,0,0,.55);
}}
.modal-header {{
  display:flex; align-items:center; justify-content:space-between; gap: 10px; margin-bottom: 6px;
}}
.btn-close {{
  background: {PRIMARY}; color: #fff; border: none; padding: 6px 10px;
  border-radius: 8px; cursor: pointer; font-weight: 600;
}}
.caption-note {{ font-size:12px; opacity:.75; margin-top:-6px; }}
</style>
"""

# ============================ HELPERS ============================
def to_datetime_utc(ts: int) -> datetime:
    return datetime.fromtimestamp((ts / 1000) if ts > 10**12 else ts, tz=timezone.utc)

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def rr_targets(entry: float, stop: float, multiples=(1.0, 1.5, 2.0)):
    r = abs(entry - stop)
    long_side = entry < stop  # стоп выше => short, ниже => long
    sign = 1 if long_side else -1
    return [entry + sign * m * r for m in multiples]

def color_levels(fig, y_values, labels, color, dash="dash", row=1, col=1):
    for y, label in zip(y_values, labels):
        fig.add_hline(y=y, line=dict(color=color, width=1.6, dash=dash),
                      annotation_text=label, annotation_position="right", row=row, col=col)

# ============================ DATA FETCH (ROBUST) ============================
BINANCE_HEADERS = {"User-Agent": "swing-mvp/1.0"}

def _klines_to_df(data):
    cols = ["open_time","open","high","low","close","volume","close_time","qav","trades","taker_base","taker_quote","ignore"]
    df = pd.DataFrame(data, columns=cols)
    df["open_time"]  = df["open_time"].apply(to_datetime_utc)
    df["close_time"] = df["close_time"].apply(to_datetime_utc)
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    return df[["open_time","open","high","low","close","volume","close_time"]]

@st.cache_data(ttl=60*30, show_spinner=False)
def _binance_primary(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    r = requests.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        headers=BINANCE_HEADERS, timeout=15,
    )
    r.raise_for_status()
    return _klines_to_df(r.json())

@st.cache_data(ttl=60*30, show_spinner=False)
def _binance_mirror(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    r = requests.get(
        "https://data-api.binance.vision/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        headers=BINANCE_HEADERS, timeout=15,
    )
    r.raise_for_status()
    return _klines_to_df(r.json())

COINGECKO_IDS = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "BNBUSDT": "binancecoin",
    "SOLUSDT": "solana",
    "XRPUSDT": "ripple",
}

@st.cache_data(ttl=60*60, show_spinner=False)
def _coingecko_ohlc(symbol: str, interval: str) -> pd.DataFrame:
    cg_id = COINGECKO_IDS.get(symbol, "bitcoin")
    days = 30 if interval.lower() == "4h" else 180
    r = requests.get(
        f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc",
        params={"vs_currency": "usd", "days": days},
        headers=BINANCE_HEADERS, timeout=20,
    )
    r.raise_for_status()
    arr = r.json()  # [[ts,o,h,l,c],...]
    if not arr:
        raise RuntimeError("CoinGecko вернул пусто")
    df = pd.DataFrame(arr, columns=["ts", "open", "high", "low", "close"])
    df["open_time"] = df["ts"].apply(lambda x: datetime.fromtimestamp(x/1000, tz=timezone.utc))
    df["close_time"] = df["open_time"]
    df["volume"] = 0.0
    return df[["open_time","open","high","low","close","volume","close_time"]]

def get_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    for attempt in range(2):
        try:
            return _binance_primary(symbol, interval, limit)
        except Exception:
            time.sleep(0.6 + attempt*0.8)
    try:
        return _binance_mirror(symbol, interval, limit)
    except Exception:
        pass
    try:
        df = _coingecko_ohlc(symbol, interval)
        return df.tail(limit).reset_index(drop=True)
    except Exception as e:
        st.error(f"Не удалось получить котировки {symbol} ({interval}): {e}")
        return pd.DataFrame(columns=["open_time","open","high","low","close","volume","close_time"])

# Fear & Greed
@st.cache_data(ttl=60*60*3, show_spinner=False)
def get_fear_greed_df(limit_days: int = 180) -> pd.DataFrame:
    try:
        r = requests.get("https://api.alternative.me/fng/", params={"limit": limit_days, "format": "json"}, timeout=15)
        r.raise_for_status()
        raw = r.json()["data"]
        df = pd.DataFrame(raw)
        df["timestamp"] = df["timestamp"].astype(int).apply(to_datetime_utc)
        df["value"] = df["value"].astype(int)
        return df.sort_values("timestamp").reset_index(drop=True)
    except Exception as e:
        st.warning(f"Fear & Greed недоступен: {e}")
        return pd.DataFrame(columns=["timestamp","value"])

# ============================ MODAL RENDER ============================
def _render_fear_greed_modal():
    fg_df = get_fear_greed_df(170)

    st.markdown('<div class="overlay"><div class="modal">', unsafe_allow_html=True)
    st.markdown(
        '<div class="modal-header"><h3 style="margin:0">Индекс страха и жадности</h3>'
        '<form method="post"><button class="btn-close" name="close_fg">Закрыть</button></form></div>',
        unsafe_allow_html=True
    )

    if fg_df.empty:
        st.info("Нет данных Fear & Greed. Попробуй позже.")
        st.markdown('</div></div>', unsafe_allow_html=True)
        return

    start_date = fg_df["timestamp"].min().date() - timedelta(days=5)
    end_date = fg_df["timestamp"].max().date() + timedelta(days=2)
    btc_day = get_klines("BTCUSDT", "1d", 600)
    btc_day = btc_day[(btc_day["open_time"].dt.date >= start_date) & (btc_day["open_time"].dt.date <= end_date)]

    sub = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12, row_heights=[0.62, 0.38])

    sub.add_trace(go.Scatter(x=fg_df["timestamp"], y=fg_df["value"], mode="lines+markers",
                             name="Fear & Greed", line=dict(width=1.7)), row=1, col=1)

    bands = [
        (0, 25, "#ff6666"), (25, 45, "#ffcc80"),
        (45, 55, "#ffe082"), (55, 75, "#c5e1a5"), (75, 100, "#81c784"),
    ]
    for y0, y1, color in bands:
        sub.add_hrect(y0=y0, y1=y1, line_width=0, fillcolor=color, opacity=0.25, row=1, col=1)

    if not btc_day.empty:
        sub.add_trace(go.Scatter(x=btc_day["open_time"], y=btc_day["close"], name="BTCUSDT (close)"), row=2, col=1)

    sub.update_layout(
        height=720, template="plotly_dark" if DARK else "plotly_white",
        margin=dict(l=10, r=10, t=35, b=10),
        title_text="Индекс страха и жадности BTC · сравнение с ценой BTC",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )
    sub.update_yaxes(range=[0, 100], row=1, col=1, title_text="F&G")
    sub.update_yaxes(title_text="Цена BTC ($)", row=2, col=1)

    st.plotly_chart(sub, use_container_width=True, theme=None)
    st.markdown('</div></div>', unsafe_allow_html=True)

# ============================ PUBLIC ENTRY ============================
def tab_entry():
    """Главная вкладка «Расчёт входа». Убраны «Новости» и «ИИ подсказка». Есть всплывающий график F&G."""
    st.markdown(PAGE_CSS, unsafe_allow_html=True)

    st.title("Вкладка 1 — Расчёт входа")

    # --- Controls ---
    coins = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"]
    tf_map = {"4h": "4h", "1d": "1d"}

    c1, c2, c3 = st.columns([2, 1.2, 1.6])
    with c1:
        symbol = st.radio("Монета", coins, horizontal=True, index=0)
    with c2:
        tf_label = st.radio("ТФ", list(tf_map.keys()), horizontal=True, index=1)
        interval = tf_map[tf_label]
    with c3:
        setup = st.radio("Сетап", ["Пробой", "Откат к EMA21"], horizontal=True, index=0)

    # Кнопка модалки
    top = st.columns([1, 1, 2.2])
    with top[0]:
        if st.button("Индекс страха и жадности"):
            st.session_state["fg_open"] = True

    # --- Data ---
    limit = 500 if interval == "4h" else 400
    df = get_klines(symbol, interval, limit)
    if df.empty:
        st.stop()

    df["ema21"] = ema(df["close"], 21)
    df["ema50"] = ema(df["close"], 50)
    df["ema100"] = ema(df["close"], 100)
    df["atr14"] = atr(df, 14)

    last = df.iloc[-1]

    if setup == "Откат к EMA21":
        entry = float(last["ema21"])
        direction = "long" if last["close"] >= last["ema21"] else "short"
    else:
        prev = df.iloc[-2]
        direction = "long" if last["close"] >= last["ema21"] else "short"
        entry = float(prev["high"] if direction == "long" else prev["low"])

    risk_choice = st.radio("Выбери риск", ["Низкий (0.5–1%)", "Средний (1–2%)", "Высокий (2–3%)"], horizontal=True, index=0)
    atr_mult = 1.2 if "Низкий" in risk_choice else (1.6 if "Средний" in risk_choice else 2.0)

    if direction == "long":
        stop = entry - atr_mult * float(last["atr14"])
    else:
        stop = entry + atr_mult * float(last["atr14"])

    tps = rr_targets(entry, stop, (1.0, 1.5, 2.0))

    st.caption(f"ATR14: {last['atr14']:.2f} | EMA21/50/100: {last['ema21']:.2f}/{last['ema50']:.2f}/{last['ema100']:.2f}")

    # --- Chart ---
    fig = make_subplots(rows=1, cols=1, shared_xaxes=True)
    fig.add_trace(go.Candlestick(
        x=df["open_time"], open=df["open"], high=df["high"], low=df["low"], close=df["close"], name=symbol
    ))
    fig.add_trace(go.Scatter(x=df["open_time"], y=df["ema21"], name="EMA21", line=dict(width=1.3)))
    fig.add_trace(go.Scatter(x=df["open_time"], y=df["ema50"], name="EMA50", line=dict(width=1.0, dash="dot")))
    fig.add_trace(go.Scatter(x=df["open_time"], y=df["ema100"], name="EMA100", line=dict(width=1.0, dash="dot")))

    color_levels(fig, [entry], [f"Entry {entry:,.2f}"], "#0bd37d", dash="solid")
    color_levels(fig, [stop], [f"Stop {stop:,.2f}"], "#ff5252", dash="solid")
    color_levels(fig, tps, [f"TP{i+1} {v:,.2f}" for i, v in enumerate(tps)], "#9be22a", dash="dash")

    fig.update_layout(
        height=520, margin=dict(l=20, r=20, t=30, b=20),
        xaxis_rangeslider_visible=False,
        template="plotly_dark" if DARK else "plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )
    st.plotly_chart(fig, use_container_width=True, theme=None)

    rr_abs = abs(entry - stop)
    rr_ratio = (
        max((tps[0] - entry) / rr_abs, 0.01) if direction == "long"
        else max((entry - tps[0]) / rr_abs, 0.01)
    )
    st.markdown(
        f"**Предложенный риск-контекст:** `RR≈{rr_ratio:.2f}R`, направление: **{direction}**  \n"
        f"<span class='caption-note'>Уровни рассчитаны из сетапа «{setup}» и ATR×{atr_mult:.1f}.</span>",
        unsafe_allow_html=True,
    )

    # --- Modal draw ---
    if st.session_state.get("fg_open"):
        _render_fear_greed_modal()