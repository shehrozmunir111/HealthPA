"""Live end-to-end verification of the AI grounded-coding layer.

Exercises the REAL stack from .env: LM Studio (chat + nomic embeddings),
Pinecone (vector store), the HITL LangGraph, the ReAct policy-QA agent, and
RAGAS — no test fakes. Run from the project root:

    python -m scripts.verify_live
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402

# Activate LangSmith tracing (the SDK reads os.environ, not pydantic settings).
if settings.LANGSMITH_TRACING:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT

from app.services.code_extraction_graph import code_extraction_graph  # noqa: E402
from app.services.coding_agent import coding_agent  # noqa: E402
from app.services.rag_service import rag_service  # noqa: E402

HOSPITAL_ID = "demo-hospital-0001"
PA_ID = "demo-pa-0001"
CLINICAL_NOTE = (
    "Adult patient presents with productive cough, fever, and right basal crackles. "
    "Assessment: pneumonia, unspecified organism. A two-view chest x-ray was performed."
)


def banner(title):
    print("\n" + "=" * 70 + f"\n{title}\n" + "=" * 70)


def main():
    print(f"Chat={settings.CHAT_LLM_MODEL} | Embed={settings.EMBEDDING_MODEL} | "
          f"Vectors={settings.RAG_VECTOR_BACKEND}/{settings.PINECONE_INDEX} | "
          f"HITL={settings.HITL_CHECKPOINTER} | LangSmith={settings.LANGSMITH_TRACING}")

    banner("1) INGEST policy corpus into Pinecone (per-hospital namespace)")
    sample_dir = os.path.join(os.path.dirname(__file__), "..", "samples", "policies")
    items = [
        {"path": os.path.join(sample_dir, "aetna_respiratory.txt"), "payer": "Aetna"},
        {"path": os.path.join(sample_dir, "cigna_msk.txt"), "payer": "Cigna"},
    ]
    result = rag_service.ingest_paths(HOSPITAL_ID, items, force=True)
    print(f"ingest: {result}")
    cached = rag_service.ingest_paths(HOSPITAL_ID, items)
    print(f"re-ingest (should be cached): {cached}")

    banner("2) RETRIEVE grounded policy for the clinical note")
    docs = rag_service.retrieve(HOSPITAL_ID, CLINICAL_NOTE, k=4)
    for doc in docs:
        print(f"  [{doc.metadata.get('source_doc')}#{doc.metadata.get('chunk')}] "
              f"{doc.page_content[:90]}...")

    banner("3) EXTRACT (HITL graph) -> pause for review")
    started = code_extraction_graph.start(
        hospital_id=HOSPITAL_ID, pa_id=PA_ID, clinical_notes=CLINICAL_NOTE, payer="Aetna"
    )
    print(f"status: {started['status']}")
    for code in started["proposed"].get("codes", []):
        cites = ", ".join(f"{c['source_doc']}#{c.get('chunk')}" for c in code.get("citations", []))
        print(f"  {code['code']} ({code['code_system']}) conf={code.get('confidence')} "
              f"grounded={code.get('grounded')} cites=[{cites}]")

    banner("4) REVIEW -> approve -> finalize")
    reviewed = code_extraction_graph.resume(pa_id=PA_ID, decision={"decision": "approve"})
    print(f"status: {reviewed['status']}")
    print(f"final codes: {[c['code'] for c in reviewed['final_codes']]}")

    banner("5) ASK (ReAct policy-QA agent, web search enabled)")
    answer = coding_agent.run(
        HOSPITAL_ID,
        "Which CPT code applies to a two-view chest x-ray, per policy?",
        conversation_id="demo-conv-1",
    )
    print(f"grounded={answer['grounded']} status={answer['status']}")
    print(f"answer: {answer['answer'][:400]}")

    banner("6) RAGAS evaluation of the extraction")
    try:
        from app.eval.ragas_eval import build_ragas_sample, run_ragas
        from app.services.grounded_extractor import extract_codes
        from app.services.llm_provider import get_chat_model_safe

        # RAGAS issues long multi-call prompts; give the local model a much larger
        # HTTP request timeout (so calls aren't cut at CHAT_LLM_TIMEOUT=120s) and
        # more output headroom (faithfulness/context_recall emit long lists and
        # otherwise hit LLMDidNotFinishException at CHAT_MAX_TOKENS=1024).
        settings.CHAT_LLM_TIMEOUT = 600
        settings.CHAT_MAX_TOKENS = 4096
        judge = get_chat_model_safe()
        proposed = extract_codes(CLINICAL_NOTE, docs, llm=judge)
        sample = build_ragas_sample(
            clinical_notes=CLINICAL_NOTE,
            proposed=proposed,
            retrieved=docs,
            gold_codes=["J18.9", "71046"],
        )
        metrics = run_ragas([sample], llm=judge)
        print(f"RAGAS: {metrics}")
    except Exception as exc:
        print(f"RAGAS skipped/failed: {exc}")

    banner("DONE — full AI stack exercised live")


if __name__ == "__main__":
    main()
