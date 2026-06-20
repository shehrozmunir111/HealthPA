import re
from dataclasses import dataclass, field
from typing import List, Tuple

from app.schemas.codes import ProposedCode

MAX_INPUT_CHARS = 4000

_INJECTION_PATTERNS = [
    r"ignore (all|any|previous|prior|the above)",
    r"disregard (all|any|previous|prior|the above)",
    r"you are now",
    r"system prompt",
    r"developer mode",
    r"jailbreak",
    r"reveal (your|the) (instructions|prompt|system)",
]

# Soft PHI signals (flag, never block).
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PHONE_RE = re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b")


@dataclass
class InputGuard:
    allowed: bool
    reason: str = ""
    flags: List[str] = field(default_factory=list)


@dataclass
class OutputGuard:
    passed: bool
    grounded: bool
    flags: List[str] = field(default_factory=list)
    ungrounded_codes: List[str] = field(default_factory=list)


def check_input(message: str) -> InputGuard:
    """Validate a free-text coder query before it reaches the agent."""
    text = (message or "").strip()
    flags: List[str] = []

    if not text:
        return InputGuard(allowed=False, reason="empty message")
    if len(text) > MAX_INPUT_CHARS:
        return InputGuard(allowed=False, reason="message too long", flags=["too_long"])

    low = text.lower()
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, low):
            return InputGuard(
                allowed=False, reason="possible prompt injection", flags=["prompt_injection"]
            )

    if _SSN_RE.search(text):
        flags.append("possible_phi_ssn")
    if _PHONE_RE.search(text):
        flags.append("possible_phi_phone")

    return InputGuard(allowed=True, flags=flags)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).upper()


def code_is_grounded(code: ProposedCode, context: str) -> bool:
    """Grounded if the code carries a citation and appears as a whole token in the policy context."""
    if not code.citations:
        return False
    pattern = re.compile(rf"(?<![\w.]){re.escape(_normalize(code.code))}(?!\w)")
    return bool(pattern.search(_normalize(context)))


def check_code_grounding(
    codes: List[ProposedCode], context: str
) -> Tuple[List[ProposedCode], List[ProposedCode]]:
    """Partition codes into (grounded, flagged) and stamp ``code.grounded``."""
    grounded: List[ProposedCode] = []
    flagged: List[ProposedCode] = []
    for code in codes:
        ok = code_is_grounded(code, context)
        code.grounded = ok
        (grounded if ok else flagged).append(code)
    return grounded, flagged


def check_output_text(answer: str, context: str) -> OutputGuard:
    """Flag any code-like token in a free-text answer that is absent from the supporting context."""
    code_re = re.compile(r"\b[A-TV-Z]\d{2}(?:\.\d{1,4})?\b|\b\d{5}\b")
    ctx = _normalize(context)
    ungrounded = []
    for token in code_re.findall(answer or ""):
        if _normalize(token) not in ctx:
            ungrounded.append(token)
    grounded = not ungrounded
    flags = [] if grounded else ["ungrounded_codes"]
    return OutputGuard(
        passed=grounded, grounded=grounded, flags=flags, ungrounded_codes=ungrounded
    )
