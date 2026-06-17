"""Multi-agent supervisor: routes a coder request to the right path.

Routes to one of:
- ``extract``  — run grounded extraction over a PA note (the HITL graph)
- ``review``   — act on a pending review (approve/reject/edit)
- ``qa``       — answer a policy/coding question (the ReAct/RAG agent)

LLM-first classification (structured output) with a deterministic keyword
fallback so routing always works offline.
"""

import logging
import re

from app.schemas.codes import GradeVerdict  # noqa: F401  (kept for schema parity)

logger = logging.getLogger("healthpa.ai.supervisor")

_EXTRACT_RE = re.compile(
    r"\b(extract|code this|assign codes?|what codes?|icd|cpt)\b", re.IGNORECASE
)
_REVIEW_RE = re.compile(r"\b(approve|reject|sign off|finalize|review (the )?codes?)\b", re.IGNORECASE)


def classify(message: str, llm=None) -> str:
    """Return 'extract' | 'review' | 'qa' for ``message``."""
    if llm is not None:
        from pydantic import BaseModel, Field
        from langchain_core.prompts import ChatPromptTemplate

        class _Route(BaseModel):
            route: str = Field(description="One of: extract, review, qa")

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "Route a medical-coding request. 'extract' = assign codes to a note; "
                    "'review' = approve/reject/edit proposed codes; 'qa' = answer a policy "
                    "or coding question. Return only the route.",
                ),
                ("human", "{q}"),
            ]
        )
        try:
            res = (prompt | llm.with_structured_output(_Route)).invoke({"q": message})
            route = (getattr(res, "route", "") or "").strip().lower()
            if route in ("extract", "review", "qa"):
                return route
        except Exception:
            logger.debug("LLM classify failed; using keyword fallback")

    text = message or ""
    if _REVIEW_RE.search(text):
        return "review"
    if _EXTRACT_RE.search(text):
        return "extract"
    return "qa"


class CodingSupervisor:
    def route(self, message: str, *, llm=None) -> str:
        return classify(message, llm=llm)


supervisor = CodingSupervisor()
