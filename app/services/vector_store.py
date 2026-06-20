import logging
import threading
from typing import Optional

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore, VectorStore

from app.core.config import settings
from app.services.llm_provider import get_embeddings

logger = logging.getLogger("healthpa.ai.vectorstore")

# Per-namespace in-memory stores (test/offline backend); module-level so a namespace maps to one store per process.
_memory_stores: dict[str, InMemoryVectorStore] = {}
_lock = threading.Lock()
_pinecone_index_ready = False


def policy_namespace(hospital_id) -> str:
    """Namespace holding a hospital's ingested policy corpus."""
    return str(hospital_id)


def memory_namespace(hospital_id) -> str:
    """Namespace holding a hospital's long-term coding memory."""
    return f"ltm-{hospital_id}"


def _get_memory_store(namespace: str, embeddings: Embeddings) -> InMemoryVectorStore:
    with _lock:
        store = _memory_stores.get(namespace)
        if store is None:
            store = InMemoryVectorStore(embedding=embeddings)
            _memory_stores[namespace] = store
        return store


def _ensure_pinecone_index(dim: int) -> None:
    """Create the Pinecone index (sized to the embedding dim) if absent."""
    global _pinecone_index_ready
    if _pinecone_index_ready:
        return
    # Double-checked locking so concurrent threadpool calls don't race to create.
    with _lock:
        if _pinecone_index_ready:
            return
        from pinecone import Pinecone, ServerlessSpec

        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        existing = {index["name"] for index in pc.list_indexes()}
        if settings.PINECONE_INDEX not in existing:
            logger.info("Creating Pinecone index %s (dim=%d)", settings.PINECONE_INDEX, dim)
            pc.create_index(
                name=settings.PINECONE_INDEX,
                dimension=dim,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=settings.PINECONE_CLOUD,
                    region=settings.PINECONE_REGION,
                ),
            )
            # Wait until the freshly created serverless index reports ready before the first upsert.
            import time

            for _ in range(60):
                try:
                    if pc.describe_index(settings.PINECONE_INDEX).status["ready"]:
                        break
                except Exception:
                    pass
                time.sleep(1)
        _pinecone_index_ready = True


def get_vector_store(
    namespace: str,
    embeddings: Optional[Embeddings] = None,
) -> VectorStore:
    """Return a tenant-scoped vector store for ``namespace``."""
    embeddings = embeddings or get_embeddings()
    backend = (settings.RAG_VECTOR_BACKEND or "pinecone").lower()

    if backend == "memory":
        return _get_memory_store(namespace, embeddings)

    _ensure_pinecone_index(settings.EMBEDDING_DIM)
    from langchain_pinecone import PineconeVectorStore

    return PineconeVectorStore(
        index_name=settings.PINECONE_INDEX,
        embedding=embeddings,
        namespace=namespace,
        pinecone_api_key=settings.PINECONE_API_KEY or None,
    )


def clear_namespace(namespace: str, embeddings: Optional[Embeddings] = None) -> None:
    """Remove all vectors in ``namespace`` (used to rebuild a hospital's corpus)."""
    backend = (settings.RAG_VECTOR_BACKEND or "pinecone").lower()
    if backend == "memory":
        with _lock:
            _memory_stores.pop(namespace, None)
        return
    try:
        store = get_vector_store(namespace, embeddings)
        store.delete(delete_all=True, namespace=namespace)
    except Exception:  # pragma: no cover - network path
        logger.warning("clear_namespace failed for %s", namespace)


def reset_memory_stores() -> None:
    """Drop all in-memory stores. Used by test fixtures for isolation."""
    with _lock:
        _memory_stores.clear()
    global _pinecone_index_ready
    _pinecone_index_ready = False
