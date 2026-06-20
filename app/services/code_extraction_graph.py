"""HITL grounded-coding graph (LangGraph).

Flow: ``retrieve -> grade -> (rewrite loop) -> extract -> interrupt(review)``.
Adaptive RAG: if the graded policy is weak, the query is rewritten and retrieval
retried up to ``CHAT_MAX_REWRITES``. After grounded extraction the graph
``interrupt()``s with the proposed codes and pauses; a reviewer resumes via
``Command(resume=ReviewDecision)`` to approve / reject / edit. State is persisted
by a checkpointer keyed by ``thread_id == PA case id`` — with a Postgres saver
(durable across restarts) and an in-memory fallback for tests/offline.
"""

import logging
from typing import List, Optional

from langchain_core.documents import Document
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict

from app.core.config import settings
from app.schemas.codes import ProposedCodes
from app.services.grounded_extractor import extract_codes
from app.services.llm_provider import get_chat_model_safe
from app.services.rag_service import rag_service

logger = logging.getLogger("healthpa.ai.graph")

# Keep PostgresSaver context managers alive for the process lifetime; otherwise
# the cm is GC'd after _build_checkpointer returns and its connection closes,
# breaking durable resume/get_proposed on later requests.
_open_checkpointer_cms = []


class ExtractionState(TypedDict, total=False):
    hospital_id: str
    pa_id: str
    clinical_notes: str
    query: str
    payer: Optional[str]
    code_system: Optional[str]
    rewrites: int
    relevant: bool
    documents: List[dict]      # serialized: {page_content, metadata}
    proposed: dict             # ProposedCodes.model_dump()
    decision: dict             # ReviewDecision payload
    final_codes: List[dict]
    status: str


def _ser(docs: List[Document]) -> List[dict]:
    return [{"page_content": doc.page_content, "metadata": doc.metadata} for doc in docs]


def _deser(rows: List[dict]) -> List[Document]:
    return [
        Document(page_content=row["page_content"], metadata=row.get("metadata", {}))
        for row in rows
    ]


def _build_checkpointer():
    """Postgres saver when configured + reachable; else in-memory."""
    backend = (settings.HITL_CHECKPOINTER or "memory").lower()
    if backend == "postgres" and settings.DATABASE_URL.startswith("postgresql"):
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            conn = settings.DATABASE_URL.replace("+asyncpg", "").replace("+psycopg", "")
            cm = PostgresSaver.from_conn_string(conn)
            saver = cm.__enter__()
            saver.setup()
            _open_checkpointer_cms.append(cm)  # prevent GC closing the connection
            logger.info("HITL checkpointer: PostgresSaver")
            return saver
        except Exception as exc:  # pragma: no cover - network path
            logger.warning("PostgresSaver unavailable (%s); using MemorySaver", exc)
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


class CodeExtractionGraph:
    """Compiles the extraction graph with a shared checkpointer; bind the LLM
    per request so tests can inject fakes."""

    def __init__(self, checkpointer=None):
        # Lazy: don't connect to Postgres at import; build on first use, after
        # settings (incl. test overrides) are in effect.
        self._checkpointer = checkpointer

    def _cp(self):
        if self._checkpointer is None:
            self._checkpointer = _build_checkpointer()
        return self._checkpointer

    # -- nodes (closures over the request LLM) -----------------------------

    def _compile(self, llm):
        def retrieve(state: ExtractionState) -> dict:
            query = state.get("query") or state["clinical_notes"]
            docs = rag_service.retrieve(
                state["hospital_id"],
                query,
                payer=state.get("payer"),
                code_system=state.get("code_system"),
                llm=llm,
            )
            return {"documents": _ser(docs), "query": query}

        def grade(state: ExtractionState) -> dict:
            docs = _deser(state.get("documents", []))
            relevant = rag_service.grade(state["query"], docs, llm=llm)
            return {"relevant": relevant}

        def rewrite(state: ExtractionState) -> dict:
            new_q = rag_service.rewrite_query(state["query"], llm=llm)
            return {"query": new_q, "rewrites": state.get("rewrites", 0) + 1}

        def extract(state: ExtractionState) -> dict:
            docs = _deser(state.get("documents", []))
            proposed = extract_codes(state["clinical_notes"], docs, llm=llm)
            return {"proposed": proposed.model_dump(), "status": "pending_review"}

        def review(state: ExtractionState) -> dict:
            proposed = state.get("proposed", {})
            decision = interrupt(
                {
                    "pa_id": state.get("pa_id"),
                    "proposed": proposed,
                    "summary": f"Review {len(proposed.get('codes', []))} proposed code(s)",
                }
            ) or {}
            verdict = (decision.get("decision") or "approve").lower()
            if verdict == "reject":
                final = []
            elif verdict == "edit":
                final = decision.get("edited_codes") or []
            else:  # approve
                final = proposed.get("codes", [])
            return {"decision": decision, "final_codes": final, "status": f"reviewed:{verdict}"}

        def decide(state: ExtractionState) -> str:
            if state.get("relevant"):
                return "extract"
            if state.get("rewrites", 0) >= settings.CHAT_MAX_REWRITES:
                return "extract"
            return "rewrite"

        graph = StateGraph(ExtractionState)
        graph.add_node("retrieve", retrieve)
        graph.add_node("grade", grade)
        graph.add_node("rewrite", rewrite)
        graph.add_node("extract", extract)
        graph.add_node("review", review)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "grade")
        graph.add_conditional_edges("grade", decide, {"extract": "extract", "rewrite": "rewrite"})
        graph.add_edge("rewrite", "retrieve")
        graph.add_edge("extract", "review")
        graph.add_edge("review", END)
        return graph.compile(checkpointer=self._cp())

    # -- public API --------------------------------------------------------

    def start(
        self,
        *,
        hospital_id,
        pa_id,
        clinical_notes: str,
        payer: Optional[str] = None,
        code_system: Optional[str] = None,
        llm=None,
    ) -> dict:
        """Run retrieve→grade→extract and pause at review. Returns the proposed
        codes + interrupt info (``status='pending_review'``)."""
        llm = llm if llm is not None else get_chat_model_safe()
        graph = self._compile(llm)
        config = {"configurable": {"thread_id": str(pa_id)}}
        # Each "Run extraction" must be a FRESH run. The checkpointer is keyed by
        # thread_id == pa_id; without clearing it, re-invoking resumes the prior
        # (already-reviewed/ended) thread and returns stale/empty state
        # ("0 of 0 codes"). Drop any existing thread so the graph restarts.
        try:
            self._cp().delete_thread(str(pa_id))
        except Exception:
            logger.debug("delete_thread unavailable / no prior thread for %s", pa_id)
        result = graph.invoke(
            {
                "hospital_id": str(hospital_id),
                "pa_id": str(pa_id),
                "clinical_notes": clinical_notes,
                "payer": payer,
                "code_system": code_system,
                "rewrites": 0,
            },
            config,
        )
        interrupts = result.get("__interrupt__")
        if interrupts:
            payload = interrupts[0].value
            return {
                "status": "pending_review",
                "proposed": payload.get("proposed", {}),
                "summary": payload.get("summary", ""),
            }
        # No interrupt (shouldn't normally happen) — return whatever we have.
        return {"status": result.get("status", "done"), "proposed": result.get("proposed", {})}

    def resume(self, *, pa_id, decision: dict, llm=None) -> dict:
        """Resume a paused review with a ReviewDecision payload; finalize codes."""
        llm = llm if llm is not None else get_chat_model_safe()
        graph = self._compile(llm)
        config = {"configurable": {"thread_id": str(pa_id)}}
        result = graph.invoke(Command(resume=decision), config)
        return {
            "status": result.get("status", "reviewed"),
            "final_codes": result.get("final_codes", []),
            "decision": result.get("decision", {}),
            "proposed": result.get("proposed", {}),
        }

    def get_proposed(self, *, pa_id) -> dict:
        """Read the current proposed codes from the persisted checkpoint."""
        graph = self._compile(None)
        config = {"configurable": {"thread_id": str(pa_id)}}
        snap = graph.get_state(config)
        values = snap.values if snap else {}
        return {"proposed": values.get("proposed", {}), "status": values.get("status", "")}


code_extraction_graph = CodeExtractionGraph()
