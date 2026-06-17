"""Phase 5 — AI endpoints (JWT + hospital scoped), offline.

The HITL graph's LLM is monkeypatched to a fake; embeddings/vector store/
checkpointer are offline via the autouse fixture. The policy corpus is seeded
directly for the test hospital.
"""

from types import SimpleNamespace

import app.routes.pa_ai as pa_ai_mod
import app.services.code_extraction_graph as graph_mod
from app.core.config import settings
from app.schemas.codes import Citation, ProposedCode, ProposedCodes
from app.services.rag_service import build_documents, rag_service
from tests.ai_fakes import StructuredFakeChatModel

POLICY = "Aetna policy: pneumonia is ICD-10 J18.9; two-view chest x-ray is CPT 71046."


def _seed(hospital_id):
    docs, ids = build_documents(
        POLICY, hospital_id=hospital_id, source_doc="aetna.txt", payer="Test Payer"
    )
    rag_service.reindex(hospital_id, docs, ids)


def _fake_factory():
    def make(*_a, **_k):
        proposed = ProposedCodes(
            codes=[
                ProposedCode(
                    code="J18.9",
                    code_system="ICD10",
                    confidence=0.9,
                    citations=[Citation(source_doc="aetna.txt", chunk=0)],
                )
            ]
        )
        return StructuredFakeChatModel(
            responses=["x"], structured_outputs=[SimpleNamespace(relevant=True), proposed]
        )

    return make


async def test_extract_proposes_grounded_codes(auth_client, test_hospital, test_pa_request, monkeypatch):
    _seed(test_hospital.id)
    monkeypatch.setattr(graph_mod, "get_chat_model_safe", _fake_factory())

    r = await auth_client.post(f"/api/v1/pa/{test_pa_request.id}/extract")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending_review"
    assert any(c["code"] == "J18.9" for c in body["proposed"]["codes"])


async def test_proposed_codes_reads_paused_state(auth_client, test_hospital, test_pa_request, monkeypatch):
    _seed(test_hospital.id)
    monkeypatch.setattr(graph_mod, "get_chat_model_safe", _fake_factory())
    await auth_client.post(f"/api/v1/pa/{test_pa_request.id}/extract")

    r = await auth_client.get(f"/api/v1/pa/{test_pa_request.id}/proposed-codes")
    assert r.status_code == 200
    assert r.json()["proposed"]["codes"]


async def test_review_approve_finalizes_and_updates_pa(auth_client, test_hospital, test_pa_request, monkeypatch):
    _seed(test_hospital.id)
    monkeypatch.setattr(graph_mod, "get_chat_model_safe", _fake_factory())
    await auth_client.post(f"/api/v1/pa/{test_pa_request.id}/extract")

    r = await auth_client.post(
        f"/api/v1/pa/{test_pa_request.id}/review", json={"decision": "approve"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "reviewed:approve"
    assert [c["code"] for c in body["final_codes"]] == ["J18.9"]


async def test_review_reject_yields_no_codes(auth_client, test_hospital, test_pa_request, monkeypatch):
    _seed(test_hospital.id)
    monkeypatch.setattr(graph_mod, "get_chat_model_safe", _fake_factory())
    await auth_client.post(f"/api/v1/pa/{test_pa_request.id}/extract")

    r = await auth_client.post(
        f"/api/v1/pa/{test_pa_request.id}/review", json={"decision": "reject"}
    )
    assert r.status_code == 200
    assert r.json()["final_codes"] == []


async def test_ask_returns_grounded_answer(auth_client, test_hospital, test_pa_request, monkeypatch):
    _seed(test_hospital.id)
    monkeypatch.setattr(pa_ai_mod, "get_chat_model_safe", lambda *a, **k: None)

    r = await auth_client.post(
        f"/api/v1/pa/{test_pa_request.id}/ask",
        json={"message": "What is the code for pneumonia?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["grounded"] is True
    assert "J18.9" in body["answer"]


async def test_extract_is_tenant_isolated(client, user_2_token, test_pa_request):
    # user_2 (hospital 2) cannot touch a hospital-1 PA.
    client.headers["Authorization"] = f"Bearer {user_2_token}"
    r = await client.post(f"/api/v1/pa/{test_pa_request.id}/extract")
    assert r.status_code == 404


async def test_reindex_cached_then_force_rebuilt(auth_client, test_hospital, monkeypatch, tmp_path):
    corpus = tmp_path / str(test_hospital.id)
    corpus.mkdir()
    (corpus / "aetna.txt").write_text(POLICY, encoding="utf-8")
    monkeypatch.setattr(settings, "POLICY_DOCS_DIR", str(tmp_path))

    r1 = await auth_client.post("/api/v1/policies/reindex", json={})
    assert r1.json()["status"] == "rebuilt"
    assert r1.json()["documents"] >= 1

    r2 = await auth_client.post("/api/v1/policies/reindex", json={})
    assert r2.json()["status"] == "cached"

    r3 = await auth_client.post("/api/v1/policies/reindex", json={"force": True})
    assert r3.json()["status"] == "rebuilt"
