import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from ...config.settings import SYMBOLS, BASE_CAPITAL, MIN_RR, CACHE_TTL
from ...data.binance_feed import MarketDataProvider
from ...core.levels import LevelBuilder
from ...core.risk import RiskScorer, PositionSizer
from ...strategies.pullback import PullbackEMA21
from ...strategies.breakout import BreakoutRange
from ...services.journal import TradeJournal
from ...services.llm import llm_suggest


# -----------------------------
# Data
# -----------------------------
@st.cache_data(ttl=CACHE_TTL)
def load_klines(symbol: str, tf: str, limit: int = 500) -> pd.DataFrame:
    provider = MarketDataProvider()
    return provider.klines(symbol, interval=tf, limit=limit)


# -----------------------------
# Helpers (levels, stops, targets)
# -----------------------------
def _zone_avg(z):
    if z is None:
        return None
    # объект из LevelBuilder.Zone
    lo = float(getattr(z, "start_price", None) or getattr(z, "lo", 0.0))
    hi = float(getattr(z, "end_price", None) or getattr(z, "hi", 0.0))
    if lo and hi:
        return (lo + hi) / 2.0
    return None


def infer_side(context: dict, htf_dir: str) -> str:
    """
    Выбор направления сделки: long/short
    - по умолчанию в сторону HTF
    - если HTF=range, берём сторону micro-structure
    """
    if htf_dir in ("up", "down"):
        return "long" if htf_dir == "up" else "short"
    if context.get("structure") == "up":
        return "long"
    if context.get("structure") == "down":
        return "short"
    return "long"


def swing_entry_stop(df: pd.DataFrame, context: dict, side: str) -> tuple[float, float]:
    """
    Вход из зоны спроса/предложения или от EMA21-отката.
    Стоп: за последний пивот и не меньше 1.5×ATR.
    Возвращает (entry, stop).
    """
    atr = float(context["atr14"])
    ema21 = float(context["ema21"])
    last_close = float(df["close"].iloc[-1])

    if side == "long":
        # приоритет: зона спроса
        e = _zone_avg(context.get("demand"))
        if e is None:
            # fallback: откат к EMA21
            e = ema21
        entry = e

        # стоп за свинг-лоу последних 10 баров
        swing_low = float(df["low"].iloc[-10:].min())
        stop = min(swing_low, entry - 1.5 * atr)

        # если цена слишком далеко от точки входа, используем текущую как лимит
        if abs(last_close - entry) > 2.5 * atr:
            entry = last_close

    else:
        # short
        e = _zone_avg(context.get("supply"))
        if e is None:
            e = ema21  # как ретест с другой стороны
        entry = e

        swing_high = float(df["high"].iloc[-10:].max())
        stop = max(swing_high, entry + 1.5 * atr)

        if abs(last_close - entry) > 2.5 * atr:
            entry = last_close

    return float(entry), float(stop)


def targets_by_r(entry: float, stop: float, r_list=(1.0, 1.5, 2.0)) -> list[float]:
    sign = 1.0 if entry > stop else -1.0  # long if stop < entry
    r = abs(entry - stop)
    return [entry + sign * r * rr for rr in r_list]


def render_chart(df: pd.DataFrame, entry: float, stop: float, tps: list[float], side: str):
    fig = go.Figure(data=[go.Candlestick(
        x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close']
    )])

    buy = (side == "long")
    entry_color = "green" if buy else "red"
    stop_color  = "red" if buy else "green"
    tp_color    = "green" if buy else "red"

    # ENTRY
    fig.add_hline(y=entry, line_color=entry_color, line_width=2,
                  annotation_text=f"Entry {entry:.2f}", annotation_position="top left")

    # STOP
    fig.add_hline(y=stop, line_color=stop_color, line_width=2,
                  annotation_text=f"Stop {stop:.2f}", annotation_position="bottom left")

    # TP1/2/3 пунктиром
    for i, tpv in enumerate(tps, start=1):
        fig.add_hline(y=tpv, line_color=tp_color, line_dash="dot", line_width=2,
                      annotation_text=f"TP{i} {tpv:.2f}", annotation_position="top right")

    fig.update_layout(height=580, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True)


# -----------------------------
# UI
# -----------------------------
SETUPS = {
    "Пробой": BreakoutRange,
    "Откат к EMA21": PullbackEMA21,
}


def tab_entry(journal: TradeJournal):
    st.subheader("Вкладка 1 — Расчёт входа")

    # Верхняя панель выбора
    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.radio("Монета", SYMBOLS, horizontal=True, index=0)
    with col2:
        tf = st.radio("ТФ", ["4h", "1d"], horizontal=True, index=0)
    with col3:
        setup_name = st.radio("Сетап", list(SETUPS.keys()), horizontal=True)

    st.divider()

    # Данные и контекст
    data = load_klines(symbol, tf)
    lb = LevelBuilder(data)
    context = lb.build_summary()

    st.write(
        f"Структура: **{context['structure']}** | "
        f"ATR14: {context['atr14']:.2f} | "
        f"EMA21/50/100: {context['ema21']:.2f}/{context['ema50']:.2f}/{context['ema100']:.2f}"
    )

    # HTF контекст
    against_htf = False
    htf_dir = "range"
    if tf == "4h":
        htf_df = load_klines(symbol, "1d")
        from ...core.levels import LevelBuilder as LB2
        htf_dir = LB2(htf_df).htf_trend()
        st.write(f"HTF (D1) тренд: **{htf_dir}**")
        if context['structure'] in ("up", "down") and htf_dir in ("up", "down"):
            against_htf = (
                (htf_dir == "up" and context['structure'] == "down")
                or (htf_dir == "down" and context['structure'] == "up")
            )

    # Новости (ручной режим осторожности)
    near_news = st.toggle("Новости в 24–48ч (режим осторожности)", value=False)

    # ИИ-подсказка (прячем кнопку, если ключа нет)
    with st.expander("ИИ-подсказка (опционально)"):
        if st.button("Запросить совет ассистента"):
            serial = {k: (vars(v) if hasattr(v, "__dict__") else v) for k, v in context.items()}
            hint = llm_suggest(serial)
            if hint.get("enabled"):
                st.json(hint["data"])
            else:
                st.info(f"Подсказка недоступна: {hint.get('reason')}")

    # Направление
    side = infer_side(context, htf_dir)

    # Сигнал от выбранной стратегии (используем как подсказку)
    StrategyCls = SETUPS.get(setup_name)
    strat_entry, strat_stop = None, None
    if StrategyCls is not None:
        sig = StrategyCls(data).signal()
        if sig:
            strat_entry, strat_stop = sig

    # Свинговый план (главный)
    entry, stop = swing_entry_stop(data, context, side)

    # Если стратегия дала валидный сигнал и он ближе к рынку — подмешиваем
    if strat_entry and strat_stop:
        if abs(float(data["close"].iloc[-1]) - strat_entry) < abs(float(data["close"].iloc[-1]) - entry):
            entry, stop = float(strat_entry), float(strat_stop)

    # Цели
    tp_levels = targets_by_r(entry, stop, r_list=(1.0, 1.5, 2.0))
    rr_min = (tp_levels[1] - entry) / abs(entry - stop) if (entry - stop) != 0 else 0.0
    st.write(f"Предложенный риск-контекст: RR≈**{rr_min:.2f}R**, направление: **{side}**")

    # Риск (кнопки)
    risk_choice = st.radio(
        "Выбери риск",
        options=["Низкий (0.5–1%)", "Средний (1–2%)", "Высокий (2–3%)"],
        index=1,
        horizontal=True,
        key="risk_choice",
    )
    if risk_choice.startswith("Низкий"):
        risk_pct = 1.0
    elif risk_choice.startswith("Высокий"):
        risk_pct = 2.5
    else:
        risk_pct = 1.5

    # Скоринг риска с учётом HTF/новостей
    rs = RiskScorer(min_rr=MIN_RR)
    advice = rs.recommend(context, against_htf=against_htf, near_news=near_news)
    # берём максимум между выбранным и рекомендуемым, но не > 3%
    risk_pct = min(3.0, max(risk_pct, advice.percent))

    # Размер позиции
    sz = PositionSizer(BASE_CAPITAL)
    sizing = sz.size(entry, stop, risk_pct)

    # График с уровнями
    render_chart(data, entry, stop, tp_levels, side)

    # Метрики
    colA, colB, colC, colD = st.columns(4)
    with colA:
        st.metric("Entry", f"{entry:.4f}")
    with colB:
        st.metric("Stop", f"{stop:.4f}")
    with colC:
        st.metric("Риск, $", f"{sizing['risk_$']}")
    with colD:
        st.metric("Кол-во", f"{sizing['qty']}")

    st.write(
        f"TP1: **{tp_levels[0]:.4f}** | TP2: **{tp_levels[1]:.4f}** | TP3: **{tp_levels[2]:.4f}** "
        f"| Минимум RR: **{rr_min:.2f}R**"
    )

    # Мини-отчёт
    with st.expander("Мини-отчёт по сетапу"):
        st.json(
            {
                "symbol": symbol,
                "tf": tf,
                "setup": setup_name,
                "side": side,
                "structure": context["structure"],
                "bos": context["bos"],
                "zone_demand": vars(context["demand"]) if context["demand"] else None,
                "zone_supply": vars(context["supply"]) if context["supply"] else None,
                "atr14": round(context["atr14"], 4),
                "risk_%": risk_pct,
                "entry": round(entry, 6),
                "stop": round(stop, 6),
                "tp1": round(tp_levels[0], 6),
                "tp2": round(tp_levels[1], 6),
                "tp3": round(tp_levels[2], 6),
                "rr_min": round(rr_min, 3),
                "advice": {"bucket": advice.bracket, "why": advice.reason},
            }
        )

    # Кнопки плана (отложки)
    col1, col2, col3 = st.columns(3)
    disabled_rr = rr_min < MIN_RR
    msg_rr = f"RR {rr_min:.2f} < {MIN_RR} — план не допускается." if disabled_rr else None

    with col1:
        btn_plan = st.button("Поставить ордер", type="primary", disabled=disabled_rr)
    with col2:
        btn_activated = st.button("Активировался")
    with col3:
        btn_cancel = st.button("Отменён")

    if msg_rr and btn_plan:
        st.warning(msg_rr)

    # Журнал
    decision = None
    if btn_plan:
        decision = "planned"
    elif btn_activated:
        decision = "activated"
    elif btn_cancel:
        decision = "cancelled"

    if decision:
        journal.append(
            {
                "time": str(pd.Timestamp.utcnow()),
                "symbol": symbol,
                "tf": tf,
                "setup": setup_name,
                "entry": entry,
                "stop": stop,
                "tp1": tp_levels[0],
                "tp2": tp_levels[1],
                "tp3": tp_levels[2],
                "rr_min": rr_min,
                "risk_%": risk_pct,
                "risk_$": sizing["risk_$"],
                "qty": sizing["qty"],
                "decision": decision,
            }
        )
        st.success(
            "Записано в журнал: "
            + ("План" if decision == "planned" else "Активировался" if decision == "activated" else "Отменён")
        )
