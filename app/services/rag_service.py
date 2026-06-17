"""Production RAG over per-hospital payer/coding-policy corpora.

Pipeline: load (PDF/txt) -> chunk (RecursiveCharacterTextSplitter) -> embed ->
upsert into the tenant's vector-store namespace. Ingestion is **idempotent**
(stable per-chunk ids -> upsert, no duplicates) and **fingerprint-cached**
(a per-hospital signature skips re-embedding when the corpus hasn't changed).
Retrieval is hard-scoped to ``namespace == hospital_id`` and supports
``payer``/``code_system`` metadata filters, with reranking down to top-k.

Adaptive/Corrective RAG helpers (``grade`` / ``rewrite_query``) live here and
are consumed by the extraction graph in Phase 3.

Everything is synchronous (matching the LangChain/LangGraph patterns); async
callers should invoke via ``fastapi.concurrency.run_in_threadpool``.
"""

import hashlib
import json
import logging
import os
import threading
from typing import List, Optional, Tuple

from langchain_core.documents import Document

from app.core.config import settings
from app.services.llm_provider import get_embeddings
from app.services.reranker import rerank
from app.services.vector_store import (
    clear_namespace,
    get_vector_store,
    policy_namespace,
)

logger = logging.getLogger("healthpa.ai.rag")

_lock = threading.Lock()


def _sha1(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Loading + chunking
# ---------------------------------------------------------------------------

def load_text(path: str) -> str:
    """Read a policy document (.pdf via pypdf, otherwise plain text)."""
    if path.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def _splitter():
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def build_documents(
    text: str,
    *,
    hospital_id,
    source_doc: str,
    payer: Optional[str] = None,
    code_system: Optional[str] = None,
) -> Tuple[List[Document], List[str]]:
    """Chunk ``text`` into (documents, stable_ids) carrying tenant metadata.

    The id is ``"{source_doc}::{chunk_index}"`` — stable across re-ingestion of
    the same document, so re-running ingestion upserts in place (no duplicates).
    """
    chunks = [chunk for chunk in _splitter().split_text(text or "") if chunk.strip()]
    docs: List[Document] = []
    ids: List[str] = []
    for i, chunk in enumerate(chunks):
        metadata = {
            "hospital_id": str(hospital_id),
            "source_doc": source_doc,
            "chunk": i,
            "content_hash": _sha1(chunk),
        }
        if payer:
            metadata["payer"] = payer
        if code_system:
            metadata["code_system"] = code_system
        docs.append(Document(page_content=chunk, metadata=metadata))
        ids.append(f"{source_doc}::{i}")
    return docs, ids


# ---------------------------------------------------------------------------
# Fingerprint cache (per hospital)
# ---------------------------------------------------------------------------

def _fingerprint_path(hospital_id) -> str:
    return os.path.join(settings.RAG_STATE_DIR, f"policy_fp_{hospital_id}.json")


def _read_fingerprint(hospital_id) -> Optional[str]:
    try:
        with open(_fingerprint_path(hospital_id)) as fh:
            return json.load(fh).get("signature")
    except Exception:
        return None


def _write_fingerprint(hospital_id, signature: str, n_docs: int) -> None:
    os.makedirs(settings.RAG_STATE_DIR, exist_ok=True)
    with open(_fingerprint_path(hospital_id), "w") as fh:
        json.dump({"signature": signature, "documents": n_docs}, fh)


def _signature(ids: List[str], docs: List[Document]) -> str:
    """Stable signature of a corpus: id + content hash of every chunk."""
    pairs = sorted(
        (doc_id, doc.metadata.get("content_hash", _sha1(doc.page_content)))
        for doc_id, doc in zip(ids, docs)
    )
    return _sha1(json.dumps(pairs, sort_keys=True))


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class RAGService:
    """Ingest + retrieve + grade + rewrite over per-hospital policy corpora."""

    def reindex(
        self,
        hospital_id,
        docs: List[Document],
        ids: List[str],
        *,
        force: bool = False,
        embeddings=None,
    ) -> dict:
        """Rebuild a hospital's **entire** policy corpus from ``docs``.

        ``docs``/``ids`` must be the full corpus for the hospital. Skips when the
        corpus signature is unchanged (fingerprint cache). On change it clears
        the namespace first (so removed chunks don't linger) and re-adds with
        stable ids. Returns ``{"status": "cached"|"rebuilt", "documents": n}``.
        """
        embeddings = embeddings or get_embeddings()
        ns = policy_namespace(hospital_id)
        signature = _signature(ids, docs)

        with _lock:
            if not force and signature == _read_fingerprint(hospital_id):
                return {"status": "cached", "documents": len(docs)}

            clear_namespace(ns, embeddings)
            store = get_vector_store(ns, embeddings)
            if docs:
                store.add_documents(docs, ids=ids)
            _write_fingerprint(hospital_id, signature, len(docs))
            return {"status": "rebuilt", "documents": len(docs)}

    def ingest_paths(
        self,
        hospital_id,
        items: List[dict],
        *,
        force: bool = False,
        embeddings=None,
    ) -> dict:
        """Load + chunk multiple policy files and reindex them as one corpus.

        ``items``: list of ``{"path", "source_doc"?, "payer"?, "code_system"?}``.
        All files are aggregated into a single corpus before reindexing, so they
        coexist in the hospital's namespace.
        """
        all_docs: List[Document] = []
        all_ids: List[str] = []
        for item in items:
            path = item["path"]
            docs, ids = build_documents(
                load_text(path),
                hospital_id=hospital_id,
                source_doc=item.get("source_doc") or os.path.basename(path),
                payer=item.get("payer"),
                code_system=item.get("code_system"),
            )
            all_docs.extend(docs)
            all_ids.extend(ids)
        return self.reindex(hospital_id, all_docs, all_ids, force=force, embeddings=embeddings)

    def retrieve(
        self,
        hospital_id,
        query: str,
        *,
        k: Optional[int] = None,
        payer: Optional[str] = None,
        code_system: Optional[str] = None,
        llm=None,
        embeddings=None,
    ) -> List[Document]:
        """Retrieve top-k policy chunks for a hospital, filtered + reranked.

        Tenant isolation is enforced by the namespace; ``payer``/``code_system``
        are applied as a backend-agnostic post-filter before reranking.
        """
        embeddings = embeddings or get_embeddings()
        k = k or settings.RAG_TOP_K
        ns = policy_namespace(hospital_id)
        store = get_vector_store(ns, embeddings)

        # Widen the candidate pool when a metadata filter is applied, so the
        # backend-agnostic post-filter doesn't starve when payer/code_system
        # chunks rank just below the default cutoff.
        fetch_k = max(k, settings.RAG_FETCH_K)
        if payer or code_system:
            fetch_k = max(fetch_k, settings.RAG_FETCH_K * 5)
        try:
            candidates = store.similarity_search(query, k=fetch_k)
        except Exception:
            logger.warning("similarity_search failed for hospital %s", hospital_id)
            return []

        def _match(doc: Document) -> bool:
            if payer and doc.metadata.get("payer") != payer:
                return False
            if code_system and doc.metadata.get("code_system") != code_system:
                return False
            return True

        filtered = [doc for doc in candidates if _match(doc)]
        if not filtered:
            return []
        if settings.RAG_RERANK:
            return rerank(query, filtered, k, llm=llm)
        return filtered[:k]

    # -- Adaptive / Corrective RAG -----------------------------------------

    def grade(self, query: str, docs: List[Document], llm=None) -> bool:
        """Return True if the retrieved policy is relevant + sufficient.

        Falls back to "relevant when any docs exist" if the LLM is unavailable,
        so the flow never blocks.
        """
        if not docs:
            return False
        if llm is None:
            return True

        from pydantic import BaseModel, Field
        from langchain_core.prompts import ChatPromptTemplate

        class _GradeDecision(BaseModel):
            relevant: bool = Field(
                description="True if the policy excerpts are relevant AND sufficient "
                "to assign codes for the clinical note."
            )

        context = "\n\n".join(doc.page_content for doc in docs)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "You grade whether retrieved payer/coding policy is sufficient."),
                (
                    "human",
                    "Clinical query:\n{q}\n\nRetrieved policy:\n{ctx}\n\n"
                    "Is this policy relevant and sufficient to assign codes?",
                ),
            ]
        )
        try:
            decision = (prompt | llm.with_structured_output(_GradeDecision)).invoke(
                {"q": query, "ctx": context}
            )
            return bool(decision.relevant)
        except Exception:
            logger.debug("structured grade failed; treating retrieval as usable")
            return True

    def rewrite_query(self, query: str, llm=None) -> str:
        """Rewrite a weak query to make payer/code terms explicit. No-op on failure."""
        if llm is None:
            return query

        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Rewrite the clinical/coding query into a single standalone search "
                    "query. Make diagnoses, procedures, payer, and code system (ICD-10 / "
                    "CPT) explicit. Return ONLY the rewritten query.",
                ),
                ("human", "{q}"),
            ]
        )
        try:
            new_q = (prompt | llm | StrOutputParser()).invoke({"q": query}).strip()
            return new_q or query
        except Exception:
            logger.debug("query rewrite failed; reusing original query")
            return query


rag_service = RAGService()
