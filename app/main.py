import streamlit as st
from app.ui.pages.entry import tab_entry
from app.ui.pages.reporting import tab_reporting
from app.services.journal import TradeJournal
from app.config.settings import JOURNAL_CSV

st.set_page_config(page_title="Swing MVP", layout="wide")

journal = TradeJournal(JOURNAL_CSV)

tab1, tab2 = st.tabs(["Расчёт входа", "Отчётность"])
with tab1:
    tab_entry(journal)
with tab2:
    tab_reporting()

st.caption("MVP: авто-свинг уровни, риск ≤ 3%, кнопочный интерфейс. Данные — публичные REST Binance.")