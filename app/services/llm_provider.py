"""Provider-agnostic factories for the grounded-coding AI layer.

The engine is configurable via ``.env``. Because LM Studio exposes an
OpenAI-compatible API, the default ``openai`` provider drives a local LM Studio
server simply by pointing ``LLM_BASE_URL`` at it (e.g. http://localhost:1234/v1).
Cloud Groq / Anthropic are selectable via ``CHAT_LLM_PROVIDER``. All third-party
imports are lazy so an unused provider's package never has to be installed, and
the offline ``HashingEmbeddings`` keeps tests network-free.
"""

import hashlib
import logging
import math
import re
from typing import List, Optional

from langchain_core.embeddings import Embeddings

from app.core.config import settings

logger = logging.getLogger("healthpa.ai.provider")


def get_chat_model(streaming: bool = False, temperature: Optional[float] = None):
    """Return an LCEL-compatible chat model selected by ``CHAT_LLM_PROVIDER``.

    Defaults to an OpenAI-compatible client, which also drives LM Studio when
    ``LLM_BASE_URL`` is set. Raises on misconfiguration; callers that need a
    backstop should use :func:`get_chat_model_safe`.
    """
    provider = (settings.CHAT_LLM_PROVIDER or "openai").lower()
    temp = settings.CHAT_LLM_TEMPERATURE if temperature is None else temperature

    if provider in ("openai", "lmstudio", "lm_studio"):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.CHAT_LLM_MODEL,
            base_url=settings.LLM_BASE_URL or None,
            api_key=settings.OPENAI_API_KEY or "lm-studio",
            temperature=temp,
            max_tokens=settings.CHAT_MAX_TOKENS,
            timeout=settings.CHAT_LLM_TIMEOUT,
            max_retries=1,
            streaming=streaming,
        )

    if provider == "groq":
        from langchain_groq import ChatGroq

        if not settings.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is not set")
        return ChatGroq(
            model=settings.CHAT_LLM_MODEL or "llama-3.1-8b-instant",
            api_key=settings.GROQ_API_KEY,
            temperature=temp,
            max_tokens=settings.CHAT_MAX_TOKENS,
            timeout=settings.CHAT_LLM_TIMEOUT,
            max_retries=1,
            streaming=streaming,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not settings.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        return ChatAnthropic(
            model=settings.CHAT_LLM_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=temp,
            max_tokens=settings.CHAT_MAX_TOKENS,
            timeout=settings.CHAT_LLM_TIMEOUT,
            streaming=streaming,
        )

    raise ValueError(f"Unknown CHAT_LLM_PROVIDER: {provider!r}")


def get_chat_model_safe(streaming: bool = False, temperature: Optional[float] = None):
    """Return a chat model, or ``None`` if AI is disabled / the provider fails.

    Every AI step is expected to degrade gracefully to the rule-based path when
    this returns ``None`` — the flow must never block on an unreachable LLM.
    """
    if not settings.AI_ENABLED:
        return None
    try:
        return get_chat_model(streaming=streaming, temperature=temperature)
    except Exception as exc:  # pragma: no cover - exercised via fallback tests
        logger.warning("chat model unavailable (%s); falling back", exc)
        return None


def get_embeddings() -> Embeddings:
    """Return an embeddings model for retrieval.

    ``EMBEDDING_PROVIDER=local`` returns a dependency-free, offline embedding
    (used by tests / no-network fallback). Otherwise an OpenAI-compatible
    embeddings client is returned, which serves LM Studio's nomic model when
    ``EMBEDDING_BASE_URL``/``LLM_BASE_URL`` points at it.
    """
    provider = (settings.EMBEDDING_PROVIDER or "openai").lower()

    if provider == "local":
        return HashingEmbeddings(dim=settings.EMBEDDING_DIM)

    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        base_url=settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL or None,
        api_key=settings.OPENAI_API_KEY or "lm-studio",
        # nomic / non-OpenAI models aren't in tiktoken; send raw strings.
        check_embedding_ctx_length=False,
    )


class HashingEmbeddings(Embeddings):
    """Deterministic, dependency-free bag-of-words hashing embedding.

    Offline and reproducible, so tests need no network and no model download.
    It captures keyword overlap well enough for a small curated policy corpus;
    it is intentionally not a semantic model. Production uses real embeddings
    (nomic via LM Studio, or a cloud provider).
    """

    def __init__(self, dim: int = 768):
        self.dim = dim

    def _embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for token in re.findall(r"[a-z0-9]+", (text or "").lower()):
            hashed = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[hashed % self.dim] += 1.0 if (hashed >> 8) % 2 == 0 else -1.0
        norm = math.sqrt(sum(component * component for component in vec)) or 1.0
        return [component / norm for component in vec]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)
