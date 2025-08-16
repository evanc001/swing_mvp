import streamlit as st
import pandas as pd
from ...config.settings import SYMBOLS, BASE_CAPITAL, MIN_RR, CACHE_TTL
from ...data.binance_feed import MarketDataProvider
from ...core.levels import LevelBuilder
from ...core.risk import RiskScorer, PositionSizer
from ...strategies.pullback import PullbackEMA21
from ...strategies.breakout import BreakoutRange
from ...services.journal import TradeJournal
from ...services.llm import llm_suggest

@st.cache_data(ttl=CACHE_TTL)
def load_klines(symbol: str, tf: str, limit: int = 500) -> pd.DataFrame:
    provider = MarketDataProvider()
    return provider.klines(symbol, interval=tf, limit=limit)

SETUPS = {"Пробой": BreakoutRange, "Откат к EMA21": PullbackEMA21, "Ретест": None, "Slingshot": None}

def tab_entry(journal: TradeJournal):
    st.subheader("Вкладка 1 — Расчёт входа")
    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.radio("Монета", SYMBOLS, horizontal=True)
    with col2:
        tf = st.radio("ТФ", ["4h","1d"], horizontal=True, index=0)
    with col3:
        setup_name = st.radio("Сетап", ["Пробой","Откат к EMA21"], horizontal=True)

    st.divider()

    data = load_klines(symbol, tf)
    lb = LevelBuilder(data)
    context = lb.build_summary()

    st.write(f"Структура: **{context['structure']}** | ATR14: {context['atr14']:.2f} | EMA21/50/100: {context['ema21']:.2f}/{context['ema50']:.2f}/{context['ema100']:.2f}")

    with st.expander("ИИ-подсказка (опционально)"):
        if st.button("Запросить совет ассистента"):
            serial = {k: (vars(v) if hasattr(v, '__dict__') else v) for k, v in context.items()}
            hint = llm_suggest(serial)
            if hint.get("enabled"):
                st.json(hint["data"])
            else:
                st.info(f"Подсказка недоступна: {hint.get('reason')}")

    against_htf = False
    if tf == "4h":
        htf = load_klines(symbol, "1d")
        from ...core.levels import LevelBuilder as LB2
        htf_lb = LB2(htf)
        htf_dir = htf_lb.htf_trend()
        st.write(f"HTF (D1) тренд: **{htf_dir}**")
        against_htf = (htf_dir == "up" and context['structure'] == "down") or (htf_dir == "down" and context['structure'] == "up")

    near_news = st.toggle("Новости в 24–48ч (режим осторожности)", value=False)

    StrategyCls = SETUPS[setup_name]
    entry = stop = None
    if StrategyCls:
        sig = StrategyCls(data).signal()
        if sig:
            entry, stop = sig
    if not entry or not stop:
        entry = float(data["close"].iloc[-1])
        stop = float(min(data["low"].iloc[-1], entry - 0.5 * context['atr14']))

    rs = RiskScorer(min_rr=MIN_RR)
    advice = rs.recommend(context, against_htf=against_htf, near_news=near_news)

    st.markdown(f"**Предложенный риск:** {advice.percent:.1f}% ({advice.bracket}), причина: {advice.reason}")

    risk_choice = st.radio(
    "Выбери риск",
    options=["Низкий (0.5–1%)", "Средний (1–2%)", "Высокий (2–3%)"],
    index=1,
    horizontal=True,
    key="risk_choice"
    )

    if risk_choice.startswith("Низкий"):
        risk_pct = 1.0
    elif risk_choice.startswith("Высокий"):
        risk_pct = 2.5
    else:
        risk_pct = 1.5
    risk_pct = min(3.0, max(0.5, risk_pct, advice.percent))

    sz = PositionSizer(BASE_CAPITAL)
    sizing = sz.size(entry, stop, risk_pct)

    colA, colB, colC, colD = st.columns(4)
    with colA:
        st.metric("Entry", f"{entry:.4f}")
    with colB:
        st.metric("Stop", f"{stop:.4f}")
    with colC:
        st.metric("Риск, $", f"{sizing['risk_$']}")
    with colD:
        st.metric("Кол-во", f"{sizing['qty']}")

    tp1 = entry + (entry - stop) * 1.0
    tp2 = entry + (entry - stop) * 1.5
    tp3 = entry + (entry - stop) * 2.0
    st.write(f"TP1: **{tp1:.4f}** | TP2: **{tp2:.4f}** | TP3: **{tp3:.4f}**  | Минимум RR: **{(tp2-entry)/abs(entry-stop):.2f}R**")

    with st.expander("Мини-отчёт по сетапу"):
        st.json({
            "symbol": symbol,
            "tf": tf,
            "setup": setup_name,
            "structure": context['structure'],
            "bos": context['bos'],
            "zone_demand": vars(context['demand']) if context['demand'] else None,
            "zone_supply": vars(context['supply']) if context['supply'] else None,
            "atr14": round(context['atr14'], 4),
            "risk_%": risk_pct,
            "entry": round(entry, 6),
            "stop": round(stop, 6),
            "tp1": round(tp1, 6),
            "tp2": round(tp2, 6),
            "tp3": round(tp3, 6)
        })

    colX, colY = st.columns(2)
    with colX:
        accept = st.button("Принять план", type="primary")
    with colY:
        reject = st.button("Отменить")

    if accept:
        journal.append({
            "time": str(pd.Timestamp.utcnow()),
            "symbol": symbol,
            "tf": tf,
            "setup": setup_name,
            "entry": entry,
            "stop": stop,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "rr_min": (tp2-entry)/abs(entry-stop) if (entry-stop)!=0 else 0,
            "risk_%": risk_pct,
            "risk_$": sizing['risk_$'],
            "qty": sizing['qty'],
            "decision": "planned"
        })
        st.success("План записан в журнал.")
    if reject:
        st.info("План отклонён.")
