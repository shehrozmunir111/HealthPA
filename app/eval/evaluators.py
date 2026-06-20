import logging
from typing import Callable, Dict, List, Optional

from langchain_core.documents import Document

from app.schemas.codes import JudgeVerdict

logger = logging.getLogger("healthpa.ai.eval")


def _norm(code: str) -> str:
    return (code or "").strip().upper()


def code_set_metrics(predicted: List[str], gold: List[str]) -> Dict[str, float]:
    """Precision / recall / F1 of predicted codes against gold codes."""
    pred = {_norm(code) for code in predicted if code}
    gold_set = {_norm(code) for code in gold if code}
    if not pred and not gold_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    tp = len(pred & gold_set)
    precision = tp / len(pred) if pred else 0.0
    recall = tp / len(gold_set) if gold_set else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def retrieval_recall_at_k(retrieved: List[Document], gold_terms: List[str]) -> Optional[float]:
    """Fraction of gold terms that appear in any retrieved chunk (recall@k)."""
    if not gold_terms:
        return None
    hay = " ".join(doc.page_content for doc in retrieved).upper()
    hits = sum(1 for term in gold_terms if _norm(term) in hay)
    return hits / len(gold_terms)


def judge_faithfulness(
    clinical_notes: str, codes: List[str], context: str, judge_llm=None
) -> Optional[JudgeVerdict]:
    """LLM-as-judge: are the codes faithful to / supported by the context?"""
    if judge_llm is None:
        return None
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a strict medical-coding evaluator. Judge ONLY from the provided "
                "policy context. faithful=false if any code is not supported by the context.",
            ),
            (
                "human",
                "Clinical note:\n{note}\n\nPolicy context:\n{ctx}\n\nProposed codes:\n{codes}",
            ),
        ]
    )
    try:
        return (prompt | judge_llm.with_structured_output(JudgeVerdict)).invoke(
            {"note": clinical_notes, "ctx": context, "codes": ", ".join(codes)}
        )
    except Exception:
        logger.debug("judge failed; returning None")
        return None


def _mean(values: List[float]) -> Optional[float]:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def run_evaluation(
    dataset: List[dict],
    answer_fn: Callable[[dict], dict],
    judge_llm=None,
) -> dict:
    """Evaluate ``answer_fn`` over ``dataset``."""
    items = []
    for case in dataset:
        out = answer_fn(case)
        codes = out.get("codes", [])
        retrieved = out.get("retrieved", [])
        context = out.get("context", "")

        metrics = code_set_metrics(codes, case.get("gold_codes", []))
        recall = retrieval_recall_at_k(retrieved, case.get("retrieval_terms", []))
        verdict = judge_faithfulness(case.get("clinical_notes", ""), codes, context, judge_llm)

        items.append(
            {
                "id": case.get("id"),
                "predicted": codes,
                "gold": case.get("gold_codes", []),
                **metrics,
                "retrieval_recall": recall,
                "judge": verdict.model_dump() if verdict else None,
            }
        )

    aggregate = {
        "n": len(items),
        "precision": _mean([item["precision"] for item in items]),
        "recall": _mean([item["recall"] for item in items]),
        "f1": _mean([item["f1"] for item in items]),
        "retrieval_recall@k": _mean([item["retrieval_recall"] for item in items]),
    }
    judged = [item["judge"] for item in items if item["judge"]]
    if judged:
        aggregate["judge_faithful"] = _mean(
            [1.0 if verdict["faithful"] else 0.0 for verdict in judged]
        )
        aggregate["judge_correct"] = _mean(
            [1.0 if verdict["correct"] else 0.0 for verdict in judged]
        )
    return {"items": items, "aggregate": aggregate}
