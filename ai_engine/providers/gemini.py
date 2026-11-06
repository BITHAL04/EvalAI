"""Google Gemini implementation using JSON-schema constrained output."""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Literal, TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from ai_engine.providers.base import AIError, AIProvider, AITransientError, ImageInput, StructuredResult

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger("evalai.ai")
EMBED_BATCH = 64
TRANSIENT = {408, 429, 500, 502, 503, 504}


class GeminiProvider(AIProvider):
    def __init__(self, *, api_key: str, model: str, embedding_model: str, vision_model: str = "", dimensions: int = 768,
                 timeout: int = 120, max_retries: int = 3, base_url: str = ""):
        http = types.HttpOptions(timeout=timeout * 1000, **({"base_url": base_url} if base_url else {}))
        self._client = genai.Client(api_key=api_key, http_options=http)
        self._model, self._vision = model, vision_model or model
        self._embedding_model, self._dims = embedding_model, dimensions
        self._retries = max_retries

    @property
    def embedding_model(self) -> str:
        return self._embedding_model

    def generate(self, *, system: str, prompt: str, schema: type[T], images: list[ImageInput] | None = None,
                 purpose: str, temperature: float = 0.1, vision: bool = False) -> StructuredResult[T]:
        model = self._vision if vision else self._model
        parts: list = [prompt]
        for img in images or []:
            if img.label:
                parts.append(img.label)
            parts.append(types.Part.from_bytes(data=img.data, mime_type=img.mime_type))
        config = types.GenerateContentConfig(system_instruction=system, temperature=temperature,
                                             response_mime_type="application/json",
                                             response_json_schema=schema.model_json_schema())
        last: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                resp = self._client.models.generate_content(model=model, contents=parts, config=config)
                data = schema.model_validate(json.loads(resp.text or ""))
                usage = resp.usage_metadata.model_dump(exclude_none=True) if resp.usage_metadata else {}
                log.info("ai call ok purpose=%s model=%s attempt=%s", purpose, model, attempt)
                return StructuredResult(data=data, model=model, attempts=attempt, usage=usage)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last = exc
                log.warning("invalid model output purpose=%s attempt=%s: %s", purpose, attempt, str(exc)[:300])
            except errors.APIError as exc:
                last = exc
                log.warning("gemini error purpose=%s attempt=%s code=%s", purpose, attempt, exc.code)
                if exc.code not in TRANSIENT:
                    raise AIError(f"Gemini rejected the request ({exc.code}): {exc.message}") from exc
            except Exception as exc:  # network / timeout
                last = exc
                log.warning("gemini transport failure purpose=%s attempt=%s: %s", purpose, attempt, exc)
            time.sleep(min(2 ** attempt, 20) + random.random())
        if isinstance(last, (json.JSONDecodeError, ValidationError, ValueError)):
            raise AIError(f"{purpose}: model output failed validation after {self._retries} attempts: {str(last)[:300]}")
        raise AITransientError(f"{purpose}: Gemini unavailable: {str(last)[:300]}")

    def embed(self, texts: list[str], *, task: Literal["document", "query"]) -> list[list[float]]:
        task_type = "RETRIEVAL_DOCUMENT" if task == "document" else "RETRIEVAL_QUERY"
        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self._dims)
        out: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            for attempt in range(1, self._retries + 1):
                try:
                    resp = self._client.models.embed_content(model=self._embedding_model, contents=batch, config=config)
                    vectors = [e.values for e in resp.embeddings or []]
                    if len(vectors) != len(batch) or any(len(v or []) != self._dims for v in vectors):
                        raise AIError("Embedding response has the wrong shape; check GEMINI_EMBEDDING_MODEL and EMBEDDING_DIMENSIONS")
                    out.extend(vectors)
                    break
                except errors.APIError as exc:
                    if exc.code not in TRANSIENT:
                        raise AIError(f"Embedding rejected ({exc.code}): {exc.message}") from exc
                    if attempt == self._retries:
                        raise AITransientError(f"Embedding unavailable: {exc.message}") from exc
                    time.sleep(2 ** attempt)
        return out


__all__ = ["GeminiProvider", "ImageInput"]
