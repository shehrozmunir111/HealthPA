"""Phase 1 — RAG ingestion, fingerprint cache, retrieval, filters, rerank, grade.

Fully offline (hashing embeddings + in-memory vector backend via the autouse
fixture). No ``db_session`` is requested, so these run without touching tables.
"""

from types import SimpleNamespace

from langchain_core.documents import Document

from app.services.rag_service import build_documents, rag_service
from app.services.reranker import lexical_rerank
from tests.ai_fakes import StructuredFakeChatModel, fake_llm

H1 = "11111111-1111-1111-1111-111111111111"
H2 = "22222222-2222-2222-2222-222222222222"

PNEUMONIA_POLICY = (
    "Aetna prior authorization policy for lower respiratory infections. "
    "Pneumonia, unspecified organism is coded J18.9 under ICD-10. "
    "A single-view chest x-ray is CPT 71045; two-view is CPT 71046. "
    "Documentation must support medical necessity for imaging."
)

KNEE_POLICY = (
    "Cigna policy for knee complaints. An MRI of the knee without contrast is "
    "CPT 73721. Osteoarthritis of the knee is ICD-10 M17.11 (right) / M17.12 (left)."
)


def _ingest(hospital_id, text, source_doc, **kw):
    docs, ids = build_documents(text, hospital_id=hospital_id, source_doc=source_doc, **kw)
    return rag_service.reindex(hospital_id, docs, ids)


def _ingest_many(hospital_id, specs):
    """specs: list of (text, source_doc, kwargs) -> reindex as one corpus."""
    all_docs, all_ids = [], []
    for text, source_doc, kw in specs:
        docs, ids = build_documents(text, hospital_id=hospital_id, source_doc=source_doc, **kw)
        all_docs.extend(docs)
        all_ids.extend(ids)
    return rag_service.reindex(hospital_id, all_docs, all_ids)


def test_build_documents_metadata_and_stable_ids():
    docs, ids = build_documents(
        PNEUMONIA_POLICY,
        hospital_id=H1,
        source_doc="aetna.txt",
        payer="Aetna",
        code_system="ICD10",
    )
    assert docs and ids
    assert ids[0] == "aetna.txt::0"
    meta = docs[0].metadata
    assert meta["hospital_id"] == H1
    assert meta["payer"] == "Aetna"
    assert meta["code_system"] == "ICD10"
    assert "content_hash" in meta


def test_ingest_is_fingerprint_cached_until_forced():
    first = _ingest(H1, PNEUMONIA_POLICY, "aetna.txt", payer="Aetna")
    assert first["status"] == "rebuilt"

    # Same corpus again -> cached (no re-embed).
    again = _ingest(H1, PNEUMONIA_POLICY, "aetna.txt", payer="Aetna")
    assert again["status"] == "cached"

    # Changed corpus -> rebuilt.
    changed = _ingest(H1, PNEUMONIA_POLICY + " Updated 2026.", "aetna.txt", payer="Aetna")
    assert changed["status"] == "rebuilt"


def test_retrieve_returns_relevant_policy():
    _ingest(H1, PNEUMONIA_POLICY, "aetna.txt", payer="Aetna", code_system="ICD10")
    hits = rag_service.retrieve(H1, "chest x-ray for pneumonia", k=3)
    assert hits
    assert any("J18.9" in h.page_content or "71046" in h.page_content for h in hits)


def test_retrieve_is_tenant_isolated():
    _ingest(H1, PNEUMONIA_POLICY, "aetna.txt")
    # Hospital 2 has no corpus -> must see nothing from hospital 1.
    assert rag_service.retrieve(H2, "pneumonia chest x-ray", k=5) == []


def test_retrieve_respects_metadata_filter():
    _ingest_many(
        H1,
        [
            (PNEUMONIA_POLICY, "aetna.txt", {"payer": "Aetna", "code_system": "ICD10"}),
            (KNEE_POLICY, "cigna.txt", {"payer": "Cigna", "code_system": "ICD10"}),
        ],
    )

    aetna_only = rag_service.retrieve(H1, "policy", k=10, payer="Aetna")
    assert aetna_only
    assert all(h.metadata.get("payer") == "Aetna" for h in aetna_only)


def test_lexical_rerank_orders_by_overlap():
    docs = [
        Document(page_content="knee MRI osteoarthritis"),
        Document(page_content="pneumonia chest x-ray J18.9 71046"),
    ]
    ranked = lexical_rerank("pneumonia chest x-ray", docs, top_n=2)
    assert "pneumonia" in ranked[0].page_content


def test_grade_no_docs_is_false_without_llm():
    assert rag_service.grade("anything", [], llm=None) is False


def test_grade_fallback_true_when_llm_absent_but_docs_present():
    docs = [Document(page_content=PNEUMONIA_POLICY)]
    assert rag_service.grade("pneumonia", docs, llm=None) is True


def test_grade_uses_structured_llm_verdict():
    docs = [Document(page_content=PNEUMONIA_POLICY)]
    weak_llm = StructuredFakeChatModel(
        responses=["x"], structured_outputs=[SimpleNamespace(relevant=False)]
    )
    assert rag_service.grade("unrelated dental query", docs, llm=weak_llm) is False

    strong_llm = StructuredFakeChatModel(
        responses=["x"], structured_outputs=[SimpleNamespace(relevant=True)]
    )
    assert rag_service.grade("pneumonia chest x-ray", docs, llm=strong_llm) is True


def test_rewrite_query_passthrough_without_llm_and_rewrites_with_llm():
    assert rag_service.rewrite_query("codes?", llm=None) == "codes?"
    llm = fake_llm("pneumonia J18.9 chest x-ray CPT 71046 Aetna ICD-10")
    out = rag_service.rewrite_query("what codes?", llm=llm)
    assert "71046" in out
