"""Phase 6 — eval evaluators + offline harness run."""

from types import SimpleNamespace

from langchain_core.documents import Document

from app.eval.evaluators import (
    code_set_metrics,
    judge_faithfulness,
    retrieval_recall_at_k,
    run_evaluation,
)
from tests.ai_fakes import StructuredFakeChatModel


def test_code_set_metrics_precision_recall_f1():
    m = code_set_metrics(["J18.9", "71046"], ["J18.9", "71046"])
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["f1"] == 1.0

    partial = code_set_metrics(["J18.9", "Z99.9"], ["J18.9", "71046"])
    assert partial["precision"] == 0.5
    assert partial["recall"] == 0.5


def test_code_set_metrics_normalizes_case():
    m = code_set_metrics(["j18.9"], ["J18.9"])
    assert m["recall"] == 1.0


def test_retrieval_recall_at_k():
    docs = [Document(page_content="Pneumonia is J18.9; chest x-ray is 71046.")]
    assert retrieval_recall_at_k(docs, ["J18.9", "71046"]) == 1.0
    assert retrieval_recall_at_k(docs, ["J18.9", "99999"]) == 0.5
    assert retrieval_recall_at_k(docs, []) is None


def test_judge_faithfulness_offline_is_none_without_judge():
    assert judge_faithfulness("note", ["J18.9"], "ctx", judge_llm=None) is None


def test_judge_faithfulness_uses_structured_verdict():
    judge = StructuredFakeChatModel(
        responses=["x"],
        structured_outputs=[SimpleNamespace(faithful=True, relevant=True, correct=True)],
    )
    v = judge_faithfulness("note", ["J18.9"], "J18.9 policy", judge_llm=judge)
    assert v.faithful is True


def test_run_evaluation_aggregates():
    dataset = [
        {
            "id": "c1",
            "clinical_notes": "pneumonia",
            "gold_codes": ["J18.9", "71046"],
            "retrieval_terms": ["J18.9"],
        }
    ]

    def answer_fn(case):
        return {
            "codes": ["J18.9", "71046"],
            "retrieved": [Document(page_content="J18.9 policy")],
            "context": "J18.9 policy",
        }

    report = run_evaluation(dataset, answer_fn, judge_llm=None)
    agg = report["aggregate"]
    assert agg["n"] == 1
    assert agg["precision"] == 1.0
    assert agg["recall"] == 1.0
    assert agg["retrieval_recall@k"] == 1.0
