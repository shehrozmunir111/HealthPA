"""Phase 6 — RAGAS integration (offline-safe parts).

The actual RAGAS metrics are LLM-judged and need a reachable chat model, so they
run in the VERIFY step (LM Studio/Groq). Here we cover the offline-safe surface:
sample construction and the graceful skip when no LLM is configured.
"""

from langchain_core.documents import Document

from app.eval.ragas_eval import build_ragas_sample, proposed_to_response, run_ragas
from app.schemas.codes import Citation, ProposedCode, ProposedCodes


def _proposed():
    return ProposedCodes(
        codes=[
            ProposedCode(
                code="J18.9",
                code_system="ICD10",
                description="Pneumonia, unspecified organism",
                citations=[Citation(source_doc="aetna.txt", chunk=0)],
            )
        ]
    )


def test_proposed_to_response_lists_codes():
    text = proposed_to_response(_proposed())
    assert "J18.9" in text

    empty = proposed_to_response(ProposedCodes())
    assert "No codes" in empty


def test_build_ragas_sample_shape():
    sample = build_ragas_sample(
        clinical_notes="pneumonia, two-view chest x-ray",
        proposed=_proposed(),
        retrieved=[Document(page_content="J18.9 policy"), Document(page_content="71046 policy")],
        gold_codes=["J18.9", "71046"],
    )
    assert sample["user_input"]
    assert "J18.9" in sample["response"]
    assert sample["retrieved_contexts"] == ["J18.9 policy", "71046 policy"]
    assert sample["reference"] == "J18.9, 71046"


def test_run_ragas_skips_without_llm():
    sample = build_ragas_sample(
        clinical_notes="x", proposed=_proposed(), retrieved=[], gold_codes=["J18.9"]
    )
    result = run_ragas([sample], llm=None)
    assert "skipped" in result
