"""Phase 3 — HITL extraction graph: interrupt + approve/reject/edit resume,
adaptive rewrite loop, and tenant-isolated fallback.

Offline: in-memory checkpointer, hashing embeddings, memory vector backend,
fake LLMs.
"""

from types import SimpleNamespace

from langgraph.checkpoint.memory import MemorySaver

from app.schemas.codes import Citation, ProposedCode, ProposedCodes
from app.services.code_extraction_graph import CodeExtractionGraph
from app.services.rag_service import build_documents, rag_service
from tests.ai_fakes import StructuredFakeChatModel

H1 = "aaaaaaaa-0000-0000-0000-000000000001"
H2 = "bbbbbbbb-0000-0000-0000-000000000002"

POLICY = (
    "Aetna policy: Pneumonia, unspecified organism is ICD-10 J18.9. "
    "Two-view chest x-ray is CPT 71046. Document medical necessity."
)
NOTE = "Patient presents with pneumonia; ordered two-view chest x-ray."


def _seed(hospital_id):
    docs, ids = build_documents(POLICY, hospital_id=hospital_id, source_doc="aetna.txt", payer="Aetna")
    rag_service.reindex(hospital_id, docs, ids)


def _graph():
    return CodeExtractionGraph(checkpointer=MemorySaver())


def _llm(*, relevant=True, codes=None):
    proposed = ProposedCodes(
        codes=codes
        if codes is not None
        else [
            ProposedCode(
                code="J18.9",
                code_system="ICD10",
                confidence=0.9,
                citations=[Citation(source_doc="aetna.txt", chunk=0)],
            )
        ]
    )
    return StructuredFakeChatModel(
        responses=["pneumonia J18.9 chest x-ray CPT 71046 Aetna"],
        structured_outputs=[SimpleNamespace(relevant=relevant), proposed],
    )


def test_start_pauses_for_review_with_grounded_codes():
    _seed(H1)
    g = _graph()
    out = g.start(hospital_id=H1, pa_id="pa-1", clinical_notes=NOTE, payer="Aetna", llm=_llm())
    assert out["status"] == "pending_review"
    codes = [c["code"] for c in out["proposed"]["codes"]]
    assert "J18.9" in codes


def test_resume_approve_finalizes_proposed():
    _seed(H1)
    g = _graph()
    g.start(hospital_id=H1, pa_id="pa-approve", clinical_notes=NOTE, payer="Aetna", llm=_llm())
    res = g.resume(pa_id="pa-approve", decision={"decision": "approve"}, llm=_llm())
    assert res["status"] == "reviewed:approve"
    assert [c["code"] for c in res["final_codes"]] == ["J18.9"]


def test_resume_reject_yields_no_codes():
    _seed(H1)
    g = _graph()
    g.start(hospital_id=H1, pa_id="pa-reject", clinical_notes=NOTE, payer="Aetna", llm=_llm())
    res = g.resume(pa_id="pa-reject", decision={"decision": "reject"}, llm=_llm())
    assert res["status"] == "reviewed:reject"
    assert res["final_codes"] == []


def test_resume_edit_uses_reviewer_codes():
    _seed(H1)
    g = _graph()
    g.start(hospital_id=H1, pa_id="pa-edit", clinical_notes=NOTE, payer="Aetna", llm=_llm())
    edited = [{"code": "71046", "code_system": "CPT", "description": "CXR two views"}]
    res = g.resume(pa_id="pa-edit", decision={"decision": "edit", "edited_codes": edited}, llm=_llm())
    assert res["status"] == "reviewed:edit"
    assert [c["code"] for c in res["final_codes"]] == ["71046"]


def test_get_proposed_reads_paused_state():
    _seed(H1)
    g = _graph()
    g.start(hospital_id=H1, pa_id="pa-read", clinical_notes=NOTE, payer="Aetna", llm=_llm())
    snap = g.get_proposed(pa_id="pa-read")
    assert snap["status"] == "pending_review"
    assert snap["proposed"]["codes"]


def test_weak_grade_triggers_rewrite_then_extracts():
    _seed(H1)
    g = _graph()
    # First grade weak -> rewrite -> retrieve -> grade strong -> extract.
    llm = StructuredFakeChatModel(
        responses=["pneumonia J18.9 chest x-ray Aetna"],
        structured_outputs=[
            SimpleNamespace(relevant=False),
            SimpleNamespace(relevant=True),
            ProposedCodes(
                codes=[
                    ProposedCode(
                        code="J18.9",
                        code_system="ICD10",
                        citations=[Citation(source_doc="aetna.txt", chunk=0)],
                    )
                ]
            ),
        ],
    )
    out = g.start(hospital_id=H1, pa_id="pa-rewrite", clinical_notes=NOTE, payer="Aetna", llm=llm)
    assert out["status"] == "pending_review"
    assert [c["code"] for c in out["proposed"]["codes"]] == ["J18.9"]


def test_no_corpus_falls_back_and_is_tenant_isolated():
    # H2 has no policy corpus -> extraction degrades to rule-based backstop.
    _seed(H1)
    g = _graph()
    out = g.start(hospital_id=H2, pa_id="pa-h2", clinical_notes=NOTE + " J18.9", llm=_llm())
    assert out["status"] == "pending_review"
    assert out["proposed"]["fallback_used"] is True
