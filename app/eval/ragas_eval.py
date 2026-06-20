import logging
from typing import List

from langchain_core.documents import Document

from app.schemas.codes import ProposedCodes

logger = logging.getLogger("healthpa.ai.ragas")


def proposed_to_response(proposed: ProposedCodes) -> str:
    """Render proposed codes as a natural-language answer for RAGAS judging."""
    if not proposed.codes:
        return "No codes could be assigned from the available policy."
    parts = [
        f"{code.code} ({code.code_system}) {code.description}".strip()
        for code in proposed.codes
    ]
    return "Proposed codes: " + "; ".join(parts)


def build_ragas_sample(
    *,
    clinical_notes: str,
    proposed: ProposedCodes,
    retrieved: List[Document],
    gold_codes: List[str],
) -> dict:
    """Build a single RAGAS single-turn sample dict."""
    return {
        "user_input": clinical_notes,
        "response": proposed_to_response(proposed),
        "retrieved_contexts": [doc.page_content for doc in retrieved] or [""],
        "reference": ", ".join(gold_codes),
    }


def run_ragas(samples: List[dict], llm=None, embeddings=None, metrics=None) -> dict:
    """Evaluate ``samples`` with RAGAS; returns aggregate metric means, or ``{"skipped": ...}`` when unavailable."""
    if llm is None:
        return {"skipped": "no chat model configured for RAGAS"}
    if not samples:
        return {"skipped": "no samples"}

    try:
        from ragas import EvaluationDataset, evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )
        from ragas.run_config import RunConfig
    except Exception as exc:  # pragma: no cover - optional dependency
        return {"skipped": f"ragas unavailable: {exc}"}

    from app.services.llm_provider import get_embeddings

    wrapped_llm = LangchainLLMWrapper(llm)
    wrapped_emb = LangchainEmbeddingsWrapper(embeddings or get_embeddings())

    # Newer Ragas requires metric instances bound to the specific LLM/Embeddings wrapper.
    if metrics is None:
        chosen = [
            Faithfulness(llm=wrapped_llm),
            AnswerRelevancy(llm=wrapped_llm, embeddings=wrapped_emb),
            ContextPrecision(llm=wrapped_llm),
            ContextRecall(llm=wrapped_llm),
        ]
    else:
        chosen = metrics

    try:
        dataset = EvaluationDataset.from_list(samples)
        # Generous timeout, low concurrency: local models are slow and don't parallelize well.
        run_config = RunConfig(timeout=1800, max_workers=1, max_retries=1)
        result = evaluate(
            dataset=dataset,
            metrics=chosen,
            llm=wrapped_llm,
            embeddings=wrapped_emb,
            raise_exceptions=False,
            run_config=run_config,
        )
        
        df = result.to_pandas()
        numeric = df.select_dtypes(include="number")
        
        # Drop NaN per column before averaging (failed rows yield NaN with raise_exceptions=False).
        summary = {}
        for col in numeric.columns:
            mean_val = df[col].dropna()
            summary[col] = float(mean_val.mean()) if not mean_val.empty else 0.0
            
        return summary
        
    except Exception as exc:  # pragma: no cover - network/LLM path
        logger.warning("RAGAS evaluation failed: %s", exc)
        return {"skipped": f"ragas evaluation error: {exc}"}