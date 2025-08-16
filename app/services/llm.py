import os
from typing import Dict, Any

try:
    import streamlit as st
except Exception:
    st = None

try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

from ..config.settings import OPENAI_MODEL

def _load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    if st is not None:
        try:
            val = st.secrets.get("openai", {}).get("api_key", "")
            if val:
                return val
        except Exception:
            pass
        try:
            enc = st.secrets.get("openai", {}).get("api_key_enc", "")
            if enc and Fernet is not None:
                fkey = os.environ.get("OPENAI_FERNET_KEY", "")
                if not fkey:
                    return ""
                f = Fernet(fkey.encode())
                return f.decrypt(enc.encode()).decode()
        except Exception:
            return ""
    return ""

def llm_suggest(context: Dict[str, Any]) -> Dict[str, Any]:
    api_key = _load_api_key()
    if not api_key or OpenAI is None:
        return {"enabled": False, "reason": "Нет API ключа или пакета openai"}

    client = OpenAI(api_key=api_key)

    prompt = (
        "Ты помощник по свинг-трейдингу. Дай краткую подсказку в JSON с полями: "
        "{'bias': 'up|down|range', 'entry_hint': 'string', 'stop_hint': 'string', "
        "'risk_bucket': 'low|mid|high', 'why': '1-2 фразы'}. "
        "Опирайся на контекст: структура (up/down/range), ATR, наличие BOS, зоны demand/supply, EMA21/50/100. "
        "Минимум текста, без пояснений вне JSON."
    )

    messages = [
        {"role": "system", "content": "Краткость. Конкретика. Никакой воды."},
        {"role": "user", "content": f"Контекст: {context}"},
    ]

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        import json
        data = json.loads(content)
        return {"enabled": True, "data": data}
    except Exception as e:
        return {"enabled": False, "reason": str(e)}
