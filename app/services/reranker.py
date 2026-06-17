"""Reranking for retrieved policy chunks.

Default is a deterministic, offline **lexical** reranker (length-normalized term
frequency) so retrieval quality improves without any network call and tests stay
reproducible. An optional **LLM** reranker (structured 0-1 relevance scoring) is
used when ``RAG_RERANK_LLM`` is on and a chat model is supplied; it degrades
gracefully to the lexical order on any failure.
"""

import logging
import re
from collections import Counter
from typing import List, Optional

from langchain_core.documents import Document

from app.core.config import settings

logger = logging.getLogger("healthpa.ai.reranker")


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def lexical_score(query_tokens: List[str], doc_text: str) -> float:
    tokens = _tokenize(doc_text)
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    term_freq = sum(counts.get(token, 0) for token in query_tokens)
    return term_freq / (len(tokens) ** 0.5)  # length-normalized term frequency


def lexical_rerank(query: str, docs: List[Document], top_n: int) -> List[Document]:
    query_tokens = list(dict.fromkeys(_tokenize(query)))  # unique, order-preserving
    # Stable sort: ties keep the original (vector-similarity) ordering.
    scored = sorted(
        enumerate(docs),
        key=lambda pair: (-lexical_score(query_tokens, pair[1].page_content), pair[0]),
    )
    return [doc for _, doc in scored[:top_n]]


def llm_rerank(query: str, docs: List[Document], top_n: int, llm) -> List[Document]:
    from pydantic import BaseModel, Field
    from langchain_core.prompts import ChatPromptTemplate

    class _Score(BaseModel):
        relevance: float = Field(description="0.0 (irrelevant) to 1.0 (highly relevant)")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "Score how relevant the policy excerpt is to the coding question. Reply 0-1."),
            ("human", "Question: {question}\n\nPolicy excerpt: {excerpt}"),
        ]
    )

    scored = []
    for index, doc in enumerate(docs):
        try:
            result = (prompt | llm.with_structured_output(_Score)).invoke(
                {"question": query, "excerpt": doc.page_content}
            )
            score = float(result.relevance)
        except Exception:
            logger.debug("llm_rerank failed on doc %d; scoring 0", index)
            score = 0.0
        scored.append((score, index, doc))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [doc for _, _, doc in scored[:top_n]]


def rerank(
    query: str,
    docs: List[Document],
    top_n: int,
    llm=None,
) -> List[Document]:
    """Rerank ``docs`` for ``query`` down to ``top_n``.

    Uses the LLM reranker only when explicitly enabled and an ``llm`` is given;
    otherwise the deterministic lexical reranker.
    """
    if not docs:
        return []
    if llm is not None and settings.RAG_RERANK_LLM:
        return llm_rerank(query, docs, top_n, llm)
    return lexical_rerank(query, docs, top_n)
