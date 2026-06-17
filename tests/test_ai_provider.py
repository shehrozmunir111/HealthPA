"""Phase 0 — provider abstraction + vector-store factory (offline).

These tests never touch a network: embeddings use the deterministic hashing
model and the vector store uses the in-process memory backend (both forced by
the autouse ``ai_offline_defaults`` fixture in conftest).
"""

from app.services.llm_provider import HashingEmbeddings, get_embeddings
from app.services.vector_store import (
    get_vector_store,
    memory_namespace,
    policy_namespace,
)


def test_get_embeddings_local_is_hashing():
    emb = get_embeddings()
    assert isinstance(emb, HashingEmbeddings)


def test_hashing_embeddings_are_deterministic_and_sized():
    emb = HashingEmbeddings(dim=768)
    v1 = emb.embed_query("chest x-ray for pneumonia")
    v2 = emb.embed_query("chest x-ray for pneumonia")
    assert v1 == v2                      # deterministic
    assert len(v1) == 768                # matches configured dim
    # different text yields a different vector
    assert emb.embed_query("knee MRI") != v1


def test_memory_vector_store_add_and_search():
    emb = HashingEmbeddings()
    store = get_vector_store(policy_namespace("hosp-A"), embeddings=emb)
    store.add_texts(
        texts=[
            "ICD-10 J18.9 covers pneumonia, unspecified organism.",
            "CPT 71046 is a chest x-ray, single view.",
        ],
        metadatas=[{"code_system": "ICD10"}, {"code_system": "CPT"}],
        ids=["doc-1", "doc-2"],
    )
    hits = store.similarity_search("pneumonia chest x-ray", k=2)
    assert hits, "expected at least one hit from the populated store"
    joined = " ".join(h.page_content for h in hits)
    assert "pneumonia" in joined or "chest x-ray" in joined


def test_namespaces_are_tenant_isolated():
    emb = HashingEmbeddings()
    store_a = get_vector_store(policy_namespace("hosp-A"), embeddings=emb)
    store_a.add_texts(["Hospital A private coding policy."], ids=["a-1"])

    # A different hospital's namespace must not see hospital A's documents.
    store_b = get_vector_store(policy_namespace("hosp-B"), embeddings=emb)
    assert store_b.similarity_search("coding policy", k=5) == []

    # Long-term memory namespace is also separate from the policy namespace.
    ltm_a = get_vector_store(memory_namespace("hosp-A"), embeddings=emb)
    assert ltm_a.similarity_search("coding policy", k=5) == []
