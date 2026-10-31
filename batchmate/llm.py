"""LLM fallback chain: Ollama (Qwen3 8B) → Groq → Gemini, with an 'offline' mode.

Every agent calls `structured(schema, system, user, offline=...)`. The `offline` callable is a
deterministic heuristic, used when LLM_CHAIN=offline or when every provider fails, so the demo
never dies on stage.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Callable, TypeVar

from pydantic import BaseModel

from . import config

T = TypeVar("T", bound=BaseModel)


def _build(provider: str):
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        # reasoning=False keeps Qwen3's <think> traces out of structured output.
        return ChatOllama(model=config.OLLAMA_MODEL, base_url=config.OLLAMA_BASE_URL,
                          temperature=0.3, reasoning=False)
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=config.GROQ_MODEL, temperature=0.3)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=config.GEMINI_MODEL, temperature=0.3)
    raise ValueError(provider)


@lru_cache(maxsize=None)
def _model(provider: str):
    return _build(provider)


def _providers() -> list[str]:
    return [p for p in config.LLM_CHAIN if p != "offline"]


def _parse_json(text: str, schema: type[T]) -> T:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    return schema.model_validate(json.loads(m.group(0) if m else text))


def structured(schema: type[T], system: str, user: str, offline: Callable[[], T]) -> T:
    from_errors = []
    for p in _providers():
        try:
            model = _model(p)
            try:
                return model.with_structured_output(schema).invoke(
                    [("system", system), ("human", user)])
            except NotImplementedError:
                hint = f"\nReply with only JSON matching this schema:\n{json.dumps(schema.model_json_schema())}"
                out = model.invoke([("system", system + hint), ("human", user)])
                return _parse_json(out.content, schema)
        except Exception as e:  # provider down, rate-limited, bad JSON… try the next one
            from_errors.append(f"{p}: {e.__class__.__name__}: {str(e)[:300]}")
    if from_errors:
        print("[llm] all providers failed, using offline heuristic:", "; ".join(from_errors))
    return offline()
