import logging
from typing import Callable, List, Optional

from app.core.config import settings
from app.services.guardrails import check_input
from app.services.rag_service import rag_service

logger = logging.getLogger("healthpa.ai.agent")

# Shared in-process conversational memory for the QA agent, keyed by conversation_id.
_agent_checkpointer = None


def _get_agent_checkpointer():
    global _agent_checkpointer
    if _agent_checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        _agent_checkpointer = MemorySaver()
    return _agent_checkpointer


def _format_policy(docs) -> str:
    if not docs:
        return "No matching policy found in this hospital's corpus."
    lines = []
    for doc in docs:
        label = f"{doc.metadata.get('source_doc', 'policy')}#{doc.metadata.get('chunk', 0)}"
        lines.append(f"[{label}] {doc.page_content}")
    return "\n".join(lines)


def build_tools(
    hospital_id,
    *,
    pa_lookup: Optional[Callable[[str], str]] = None,
    codes_lookup: Optional[Callable[[str], str]] = None,
    llm=None,
):
    from langchain_core.tools import StructuredTool

    def search_policies(query: str) -> str:
        """Search this hospital's payer/coding policy corpus for relevant text."""
        docs = rag_service.retrieve(hospital_id, query, llm=llm)
        return _format_policy(docs)

    def get_pa_case(pa_id: str) -> str:
        """Look up a prior-authorization case by id."""
        return pa_lookup(pa_id) if pa_lookup else "PA case lookup is not available here."

    def get_extracted_codes(pa_id: str) -> str:
        """Get the AI-proposed/extracted codes for a PA case."""
        return codes_lookup(pa_id) if codes_lookup else "Extracted codes are not available here."

    tools = [
        StructuredTool.from_function(func=search_policies, name="search_policies"),
        StructuredTool.from_function(func=get_pa_case, name="get_pa_case"),
        StructuredTool.from_function(func=get_extracted_codes, name="get_extracted_codes"),
    ]

    if settings.ENABLE_WEB_SEARCH and settings.TAVILY_API_KEY:
        try:
            from langchain_tavily import TavilySearch

            web = TavilySearch(max_results=3, tavily_api_key=settings.TAVILY_API_KEY)
            web.name = "web_search"
            web.description = (
                "Search the web for general coding-guideline context. NON-AUTHORITATIVE: "
                "do not assign codes from web results; prefer search_policies."
            )
            tools.append(web)
        except Exception:  # pragma: no cover - optional dependency / network
            logger.warning("Tavily web search unavailable; continuing without it")

    return tools


_SYSTEM = (
    "You are a medical-coding assistant. Use search_policies to ground answers in "
    "this hospital's payer/coding policy; cite the [source#chunk] labels. Only assign "
    "codes that appear in retrieved policy. Web results (if any) are background only — "
    "never assign a code from them. Answer concisely."
)


class CodingAgent:
    def run(
        self,
        hospital_id,
        message: str,
        conversation_id: str,
        *,
        llm=None,
        pa_lookup=None,
        codes_lookup=None,
    ) -> dict:
        guard = check_input(message)
        if not guard.allowed:
            return {
                "answer": "I can't process that request.",
                "status": "blocked",
                "sources": [],
                "grounded": False,
                "guardrails": {"input": guard.flags, "reason": guard.reason},
            }

        if llm is None:
            return self._rag_fallback(hospital_id, message, guard.flags)

        try:
            from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
            from langgraph.prebuilt import create_react_agent

            tools = build_tools(
                hospital_id, pa_lookup=pa_lookup, codes_lookup=codes_lookup, llm=llm
            )
            agent = create_react_agent(
                llm, tools, prompt=_SYSTEM, checkpointer=_get_agent_checkpointer()
            )
            result = agent.invoke(
                {"messages": [HumanMessage(content=message)]},
                {"configurable": {"thread_id": conversation_id}},
            )
            messages = result["messages"]
            answer = ""
            for message_obj in reversed(messages):
                if isinstance(message_obj, AIMessage) and message_obj.content:
                    answer = (
                        message_obj.content
                        if isinstance(message_obj.content, str)
                        else str(message_obj.content)
                    )
                    break
            sources = [
                {"tool": message_obj.name, "detail": str(message_obj.content)}
                for message_obj in messages
                if isinstance(message_obj, ToolMessage)
            ]
            return {
                "answer": answer or "I couldn't produce an answer.",
                "status": "completed",
                "sources": sources,
                "grounded": any(src["tool"] == "search_policies" for src in sources),
                "guardrails": {"input": guard.flags},
            }
        except Exception:
            logger.warning("ReAct agent failed; using RAG fallback")
            return self._rag_fallback(hospital_id, message, guard.flags)

    def _rag_fallback(self, hospital_id, message: str, input_flags) -> dict:
        docs = rag_service.retrieve(hospital_id, message)
        if not docs:
            return {
                "answer": "No matching policy was found for this hospital.",
                "status": "completed",
                "sources": [],
                "grounded": False,
                "guardrails": {"input": input_flags},
            }
        sources = [
            {
                "tool": "search_policies",
                "detail": doc.page_content,
                "source_doc": doc.metadata.get("source_doc"),
                "chunk": doc.metadata.get("chunk"),
            }
            for doc in docs
        ]
        answer = "Based on this hospital's policy:\n" + _format_policy(docs)
        return {
            "answer": answer,
            "status": "completed",
            "sources": sources,
            "grounded": True,
            "guardrails": {"input": input_flags},
        }


coding_agent = CodingAgent()
