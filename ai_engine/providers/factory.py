from __future__ import annotations

from functools import lru_cache

from ai_engine.providers.base import AIProvider


class AINotConfigured(RuntimeError):
    pass


@lru_cache
def build_gemini(api_key: str, model: str, embedding_model: str, vision_model: str, dimensions: int, timeout: int,
                 retries: int, base_url: str) -> AIProvider:
    missing = [n for n, v in (("GEMINI_API_KEY", api_key), ("GEMINI_MODEL", model), ("GEMINI_EMBEDDING_MODEL", embedding_model)) if not v]
    if missing:
        raise AINotConfigured(f"AI features need {', '.join(missing)}. Get a key at https://aistudio.google.com/apikey "
                              "and pick current model ids from https://ai.google.dev/models.")
    from ai_engine.providers.gemini import GeminiProvider
    return GeminiProvider(api_key=api_key, model=model, embedding_model=embedding_model, vision_model=vision_model,
                          dimensions=dimensions, timeout=timeout, max_retries=retries, base_url=base_url)
