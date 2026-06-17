"""Per-coder / per-hospital long-term semantic memory.

Persists memorable facts (e.g. a coder's recurring corrections/preferences) in
the tenant's memory namespace so the system can recall them across PA cases and
sessions. Hard tenant isolation is via ``namespace == "ltm-{hospital_id}"``;
recall is further scoped to a ``user_id`` via a metadata post-filter (kept
backend-agnostic so the in-memory test backend works the same as Pinecone).
"""

import logging
import uuid
from typing import List, Optional

from app.core.config import settings
from app.services.llm_provider import get_embeddings
from app.services.vector_store import get_vector_store, memory_namespace

logger = logging.getLogger("healthpa.ai.ltm")


class LongTermMemory:
    def _store(self, hospital_id, embeddings=None):
        return get_vector_store(
            memory_namespace(hospital_id), embeddings or get_embeddings()
        )

    def add(self, hospital_id, user_id, text: str, *, kind: str = "note", embeddings=None) -> None:
        if not settings.LONG_TERM_MEMORY or not text:
            return
        try:
            self._store(hospital_id, embeddings).add_texts(
                texts=[text],
                metadatas=[{"user_id": str(user_id), "kind": kind}],
                ids=[f"{user_id}:{uuid.uuid4().hex}"],
            )
        except Exception:
            logger.warning("LTM add failed for hospital %s", hospital_id)

    def add_correction(
        self, hospital_id, user_id, *, before, after, note: str = "", embeddings=None
    ) -> None:
        """Record a reviewer's edit so the system can learn recurring fixes."""
        text = f"Coder corrected codes from {before} to {after}."
        if note:
            text += f" Note: {note}"
        self.add(hospital_id, user_id, text, kind="correction", embeddings=embeddings)

    def recall(
        self, hospital_id, user_id, query: str, *, k: int = 3, embeddings=None
    ) -> List[str]:
        if not settings.LONG_TERM_MEMORY:
            return []
        # Over-fetch generously before the per-coder post-filter so a busy
        # shared hospital namespace doesn't crowd out this coder's memories.
        try:
            docs = self._store(hospital_id, embeddings).similarity_search(
                query, k=max(k * 10, 25)
            )
        except Exception:
            logger.warning("LTM recall failed for hospital %s", hospital_id)
            return []
        # Scope to this coder (backend-agnostic post-filter).
        scoped = [doc for doc in docs if doc.metadata.get("user_id") == str(user_id)]
        return [doc.page_content for doc in scoped[:k]]

    def recall_text(
        self, hospital_id, user_id, query: str, *, k: int = 3, embeddings=None
    ) -> str:
        memories = self.recall(hospital_id, user_id, query, k=k, embeddings=embeddings)
        if not memories:
            return ""
        return "Relevant past coder corrections:\n" + "\n".join(
            f"- {memory}" for memory in memories
        )


long_term_memory = LongTermMemory()
