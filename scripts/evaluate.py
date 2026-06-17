"""Evaluate grounded coding over the labelled dataset (app/eval/cases.json).

Metrics: code-extraction precision/recall/F1 (vs gold), retrieval recall@k, and
(optional) LLM-as-judge citation faithfulness.

Self-contained + offline by default: forces the in-memory vector backend and
hashing embeddings so it runs with no Pinecone/LM Studio. Extraction uses the
chat model from .env when reachable, else the deterministic rule-based backstop.

Usage (from project root):
    python -m scripts.evaluate            # offline, no judge
    python -m scripts.evaluate --judge    # add LLM-as-judge (needs a chat model)
    python -m scripts.evaluate --use-llm  # use the configured chat model for extraction
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate grounded coding.")
    parser.add_argument("--judge", action="store_true", help="enable LLM-as-judge")
    parser.add_argument("--use-llm", action="store_true", help="use chat model for extraction")
    parser.add_argument("--ragas", action="store_true", help="also run RAGAS metrics (needs a chat model)")
    args = parser.parse_args()

    # Self-contained offline retrieval.
    settings.RAG_VECTOR_BACKEND = "memory"
    settings.EMBEDDING_PROVIDER = "local"
    settings.LANGSMITH_TRACING = False

    from app.eval.evaluators import run_evaluation
    from app.services.grounded_extractor import extract_codes, format_context
    from app.services.llm_provider import get_chat_model_safe
    from app.services.rag_service import build_documents, rag_service

    cases_path = os.path.join(os.path.dirname(__file__), "..", "app", "eval", "cases.json")
    with open(cases_path) as fh:
        dataset = json.load(fh)

    extract_llm = get_chat_model_safe() if (args.use_llm or args.ragas) else None
    judge_llm = get_chat_model_safe() if args.judge else None

    ragas_samples = []

    def answer_fn(case: dict) -> dict:
        hospital = f"eval-{case['id']}"
        docs, ids = build_documents(
            case["policy"], hospital_id=hospital, source_doc=f"{case['id']}.txt"
        )
        rag_service.reindex(hospital, docs, ids, force=True)
        retrieved = rag_service.retrieve(hospital, case["clinical_notes"], k=4)
        proposed = extract_codes(case["clinical_notes"], retrieved, llm=extract_llm)
        if args.ragas:
            from app.eval.ragas_eval import build_ragas_sample

            ragas_samples.append(
                build_ragas_sample(
                    clinical_notes=case["clinical_notes"],
                    proposed=proposed,
                    retrieved=retrieved,
                    gold_codes=case.get("gold_codes", []),
                )
            )
        return {
            "codes": [code.code for code in proposed.codes],
            "retrieved": retrieved,
            "context": format_context(retrieved),
        }

    report = run_evaluation(dataset, answer_fn, judge_llm=judge_llm)
    print("== deterministic metrics ==")
    print(json.dumps(report["aggregate"], indent=2))
    for item in report["items"]:
        print(
            f"  {item['id']}: pred={item['predicted']} gold={item['gold']} "
            f"P={item['precision']:.2f} R={item['recall']:.2f} "
            f"recall@k={item['retrieval_recall']}"
        )

    if args.ragas:
        from app.eval.ragas_eval import run_ragas

        print("\n== RAGAS metrics ==")
        ragas_result = run_ragas(ragas_samples, llm=extract_llm)
        print(json.dumps(ragas_result, indent=2))


if __name__ == "__main__":
    main()
