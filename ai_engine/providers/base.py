"""Provider boundary: swapping Gemini for another model touches only this package."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class AIError(RuntimeError):
    """The model could not produce a valid response after retries."""


class AITransientError(AIError):
    """Worth retrying the whole job later: rate limit, timeout, 5xx."""


@dataclass
class ImageInput:
    data: bytes
    mime_type: str = "image/jpeg"
    label: str = ""


@dataclass
class StructuredResult(Generic[T]):
    data: T
    model: str
    attempts: int = 1
    usage: dict = field(default_factory=dict)


class AIProvider(ABC):
    @abstractmethod
    def generate(self, *, system: str, prompt: str, schema: type[T], images: list[ImageInput] | None = None,
                 purpose: str, temperature: float = 0.1, vision: bool = False) -> StructuredResult[T]:
        """Return `schema` validated. Raises AIError if validation keeps failing."""

    @abstractmethod
    def embed(self, texts: list[str], *, task: Literal["document", "query"]) -> list[list[float]]:
        ...

    @property
    @abstractmethod
    def embedding_model(self) -> str:
        ...
