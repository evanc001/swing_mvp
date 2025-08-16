# Swing Trading MVP (Streamlit)

Две вкладки:
1) **Расчёт входа** — анализ через Binance REST (Spot), авто-свинг-уровни, ATR/EMA, BOS/зоны demand/supply, рекомендации по риску (≤3%), размер позиции от капитала 100$.
2) **Отчётность** — журнал сделок (CSV) и базовые метрики.

## Запуск

```bash
pip install -r requirements.txt
streamlit run app/main.py
```

Интернет обязателен: тянем свечи с публичных REST-эндпоинтов Binance.

## Ключи OpenAI (опционально)

ИИ-подсказка включается, если есть ключ в `st.secrets` или переменных окружения..

### Вариант A: Streamlit secrets (локально)

Создай файл `.streamlit/secrets.toml` (НЕ коммить его):

```toml
[openai]
api_key = "sk-proj-..."
```

### Вариант B: Переменные окружения

```bash
export OPENAI_API_KEY="sk-proj-..."
```

### Вариант C: Шифрование (только шифротекст в репо)

1) Сгенерируй ключ Fernet и положи его ТОЛЬКО в переменную окружения `OPENAI_FERNET_KEY` на хостинге.
2) Зашифруй свой OpenAI API ключ и вставь **только шифротекст** в `secrets.toml` как `api_key_enc`.

## Деплой в Streamlit Community Cloud

1) Заливаешь репозиторий на GitHub.
2) В настройках приложения в облаке добавляешь `secrets` (вставь содержимое `.streamlit/secrets.toml`).
3) Запускаешь. Никаких приватных ключей в репозитории.

## Структура

```
app/
  config/settings.py         # константы проекта
  data/binance_feed.py       # OHLCV c Binance REST
  core/indicators.py         # EMA/ATR/RSI/Anchored VWAP
  core/levels.py             # свинги/BOS/зоны/HTF-тренд
  core/risk.py               # RiskScorer/PositionSizer
  strategies/                # сигналы (пробой, откат)
  services/journal.py        # CSV-журнал
  services/llm.py            # опциональная ИИ-подсказка
  ui/pages/entry.py          # вкладка расчёта
  ui/pages/reporting.py      # вкладка отчётности
  main.py                    # запуск приложения
```

## Предупреждения

- Volume-by-price реализован как упрощённая оценка через ATR/зоны. Для точности подключите aggTrades и профиль цены позже.
- Рекомендация риска является подсказкой, а не приказом.
