"""Phase 2 — grounded extraction: grounding filter, auto-citation, fallback."""

from app.schemas.codes import Citation, ProposedCode, ProposedCodes
from app.services.grounded_extractor import extract_codes, rule_based_extract
from app.services.rag_service import build_documents
from tests.ai_fakes import BoomLLM, StructuredFakeChatModel

H1 = "11111111-1111-1111-1111-111111111111"
POLICY = (
    "Aetna policy: Pneumonia, unspecified organism is ICD-10 J18.9. "
    "Two-view chest x-ray is CPT 71046."
)
NOTE = "Patient with pneumonia; chest x-ray two views ordered. Codes J18.9 and 71046."


def _docs():
    docs, _ = build_documents(POLICY, hospital_id=H1, source_doc="aetna.txt", payer="Aetna")
    return docs


def _fake(*proposed):
    return StructuredFakeChatModel(responses=["x"], structured_outputs=list(proposed))


def test_rule_based_extract_finds_codes_and_flags_fallback():
    result = rule_based_extract(NOTE)
    codes = {c.code for c in result.codes}
    assert "J18.9" in codes
    assert "71046" in codes
    assert result.fallback_used is True
    assert result.grounded is False


def test_extract_falls_back_without_llm():
    result = extract_codes(NOTE, _docs(), llm=None)
    assert result.fallback_used is True


def test_extract_falls_back_without_policy():
    result = extract_codes(NOTE, [], llm=_fake(ProposedCodes()))
    assert result.fallback_used is True
    assert "no policy found" in result.notes


def test_extract_keeps_grounded_code_with_citation():
    proposed = ProposedCodes(
        codes=[
            ProposedCode(
                code="J18.9",
                code_system="ICD10",
                confidence=0.9,
                citations=[Citation(source_doc="aetna.txt", chunk=0, quote="J18.9")],
            )
        ]
    )
    result = extract_codes(NOTE, _docs(), llm=_fake(proposed))
    assert result.fallback_used is False
    assert result.grounded is True
    assert [c.code for c in result.codes] == ["J18.9"]
    assert result.codes[0].grounded is True


def test_extract_auto_cites_code_present_in_policy():
    # LLM forgot the citation, but the code is literally in the policy -> auto-cited.
    proposed = ProposedCodes(codes=[ProposedCode(code="71046", code_system="CPT")])
    result = extract_codes(NOTE, _docs(), llm=_fake(proposed))
    assert result.grounded is True
    assert result.codes[0].citations  # auto-attached


def test_extract_drops_ungrounded_code():
    # Code not present in the policy context -> dropped (no evidence).
    proposed = ProposedCodes(
        codes=[
            ProposedCode(
                code="Z99.9",
                code_system="ICD10",
                citations=[Citation(source_doc="aetna.txt", chunk=0)],
            )
        ]
    )
    result = extract_codes(NOTE, _docs(), llm=_fake(proposed))
    assert result.codes == []
    assert result.grounded is False


def test_extract_handles_llm_error_with_fallback():
    result = extract_codes(NOTE, _docs(), llm=BoomLLM())
    assert result.fallback_used is True
