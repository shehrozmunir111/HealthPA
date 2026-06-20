import logging
import re
from typing import List, Optional

from langchain_core.documents import Document

from app.schemas.codes import Citation, ProposedCode, ProposedCodes
from app.services.guardrails import check_code_grounding

logger = logging.getLogger("healthpa.ai.extractor")

# ICD-10-CM: letter + 2 digits + optional .subcategory. CPT/HCPCS: 5 digits.
_ICD10_RE = re.compile(r"\b[A-TV-Z]\d{2}(?:\.\d{1,4})?\b")
_CPT_RE = re.compile(r"\b\d{5}\b")


def format_context(docs: List[Document]) -> str:
    """Label each policy chunk so the model can cite it as ``[source_doc#chunk]``."""
    parts = []
    for doc in docs:
        label = f"{doc.metadata.get('source_doc', 'policy')}#{doc.metadata.get('chunk', 0)}"
        parts.append(f"[{label}]\n{doc.page_content}")
    return "\n\n".join(parts)


def _attach_citations(codes: List[ProposedCode], docs: List[Document]) -> None:
    """Attach an auto-citation for any policy chunk literally containing the code."""
    for code in codes:
        if code.citations:
            continue
        code_token = code.code.upper()
        for doc in docs:
            if code_token in doc.page_content.upper():
                code.citations.append(
                    Citation(
                        source_doc=str(doc.metadata.get("source_doc", "policy")),
                        chunk=doc.metadata.get("chunk"),
                        quote=doc.page_content[:200],
                    )
                )
                break


def rule_based_extract(clinical_notes: str, *, reason: str = "") -> ProposedCodes:
    """Deterministic regex backstop. Ungrounded, low-confidence, for review."""
    text = clinical_notes or ""
    cpt_hits = set(_CPT_RE.findall(text))
    # ICD-10 carry a leading letter, CPT are bare 5-digit, so scans can't double-count.
    icd_hits = _ICD10_RE.findall(text)
    codes: List[ProposedCode] = []
    for code in dict.fromkeys(icd_hits):
        codes.append(ProposedCode(code=code, code_system="ICD10", confidence=0.3))
    for code in dict.fromkeys(cpt_hits):
        codes.append(ProposedCode(code=code, code_system="CPT", confidence=0.3))
    return ProposedCodes(
        codes=codes,
        rationale="Rule-based extraction (AI/policy unavailable).",
        grounded=False,
        fallback_used=True,
        notes=reason or "fallback: pattern match only, not policy-grounded",
    )


def extract_codes(
    clinical_notes: str,
    docs: List[Document],
    llm=None,
) -> ProposedCodes:
    """Grounded extraction returning ``ProposedCodes`` with citations (rule-based backstop if no LLM/policy)."""
    if llm is None or not docs:
        return rule_based_extract(
            clinical_notes,
            reason="no policy found" if not docs else "LLM unavailable",
        )

    context = format_context(docs)
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a medical coding expert. Using ONLY the payer/coding policy "
                "excerpts provided, extract the ICD-10 and CPT codes supported for the "
                "clinical note. Do NOT invent codes that are not present in the policy. "
                "For each code include a citation to the policy excerpt it came from.",
            ),
            (
                "human",
                "Clinical note:\n{note}\n\nPolicy excerpts:\n{ctx}\n\n"
                "Return the supported codes with citations.",
            ),
        ]
    )

    try:
        result: ProposedCodes = (prompt | llm.with_structured_output(ProposedCodes)).invoke(
            {"note": clinical_notes, "ctx": context}
        )
    except Exception:
        logger.warning("grounded extraction failed; using rule-based backstop")
        return rule_based_extract(clinical_notes, reason="extraction error; pattern match only")

    if result is None:
        return rule_based_extract(clinical_notes, reason="empty extraction; pattern match only")

    # Auto-cite from policy, then enforce grounding: drop ungrounded codes.
    _attach_citations(result.codes, docs)
    grounded, flagged = check_code_grounding(result.codes, context)
    if flagged:
        logger.info("dropping %d ungrounded code(s): %s", len(flagged), [code.code for code in flagged])
    result.codes = grounded
    result.fallback_used = False
    result.grounded = bool(grounded)
    if not grounded:
        result.notes = result.notes or "no policy-grounded codes found"
    return result
