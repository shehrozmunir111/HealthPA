from typing import List, Literal, Optional

from pydantic import BaseModel, Field

CodeSystem = Literal["ICD10", "CPT", "HCPCS", "OTHER"]


class Citation(BaseModel):
    """Pointer to the policy evidence that grounds a code."""

    source_doc: str = Field(description="Policy document the evidence came from")
    chunk: Optional[int] = Field(default=None, description="Chunk index within the document")
    quote: str = Field(default="", description="Short supporting excerpt from the policy")


class ProposedCode(BaseModel):
    code: str = Field(description="The code, e.g. 'J18.9' or '71046'")
    description: str = Field(default="", description="Human-readable description")
    code_system: CodeSystem = "OTHER"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    citations: List[Citation] = Field(default_factory=list)
    grounded: bool = Field(
        default=False,
        description="True once verified present in cited policy context",
    )


class ProposedCodes(BaseModel):
    """Result of a grounded extraction over a clinical note + policy context."""

    codes: List[ProposedCode] = Field(default_factory=list)
    rationale: str = ""
    grounded: bool = Field(default=False, description="True if every emitted code is grounded")
    fallback_used: bool = Field(default=False, description="True if the rule-based backstop ran")
    notes: str = Field(default="", description="e.g. 'no policy found'")


class ReviewDecision(BaseModel):
    """A reviewer's sign-off on proposed codes (HITL resume payload)."""

    decision: Literal["approve", "reject", "edit"]
    edited_codes: Optional[List[ProposedCode]] = None
    reviewer_notes: str = ""


class GradeVerdict(BaseModel):
    """Relevance grade for retrieved policy (adaptive RAG)."""

    relevant: bool = Field(
        description="True if the policy is relevant AND sufficient to assign codes"
    )


class AskRequest(BaseModel):
    """Body for the coder policy-QA endpoint."""

    message: str
    conversation_id: Optional[str] = None


class ReindexRequest(BaseModel):
    """Body for the policy reindex endpoint."""

    force: bool = False


class JudgeVerdict(BaseModel):
    """LLM-as-judge verdict for the eval harness."""

    faithful: bool = Field(description="Answer/codes are supported by context; nothing invented")
    relevant: bool = Field(description="Answer addresses the question")
    correct: bool = Field(description="Answer is factually correct given the context")
