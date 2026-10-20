"""Input/output guardrails.

1. **Prompt-injection screening** of user input *and retrieved documents*.
   Indirect injection (instructions hidden in a PDF/contract) is the real
   threat for RAG; retrieved text is always data, never instructions.
2. **PII redaction** before anything is logged or cached.
3. **Numeric grounding** – the hallucination check that matters for a
   decision tool: every number in the answer must be traceable to a tool
   output. An ungrounded number is the most dangerous kind of hallucination
   because it looks authoritative.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)",
    r"disregard (the )?(system|previous) (prompt|instructions)",
    r"you are now (?!able)",
    r"reveal (your|the) (system prompt|instructions|api key)",
    r"\bact as (an? )?(admin|developer|dan)\b",
    r"print (your|the) (system prompt|secrets?)",
    r"<\s*/?\s*system\s*>",
]
_INJ = re.compile("|".join(INJECTION_PATTERNS), re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?\d{10}(?!\d)")
_NUM = re.compile(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?(?![\w])")
_IDLIKE = re.compile(r"\b(?:S\d{2}|SKU\d{3}|SUP\d{2}|\d{8}T\d+Z|20\d{2}-\d{2}-\d{2})\b")


def looks_like_injection(text: str) -> bool:
    return bool(_INJ.search(text))


def redact_pii(text: str) -> str:
    return _PHONE.sub("[PHONE]", _EMAIL.sub("[EMAIL]", text))


def _numbers(text: str) -> list[float]:
    cleaned = _IDLIKE.sub(" ", text)
    out = []
    for m in _NUM.findall(cleaned):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            continue
    return out


def _evidence_numbers(evidence: Any) -> list[float]:
    found: list[float] = []

    def walk(x: Any) -> None:
        if isinstance(x, bool):
            return
        if isinstance(x, int | float):
            found.append(float(x))
        elif isinstance(x, str):
            found.extend(_numbers(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list | tuple):
            for v in x:
                walk(v)

    walk(evidence)
    return found


@dataclass
class GroundingReport:
    score: float
    checked: int
    ungrounded: list[float]

    @property
    def passed(self) -> bool:
        return not self.ungrounded


def numeric_grounding(answer: str, evidence: Any, rel_tol: float = 0.02) -> GroundingReport:
    """Fraction of numbers in ``answer`` that match a number in ``evidence``.

    Small integers (<= 31) are skipped: they are mostly ranks, horizons,
    percentages restated from the question or dates, and checking them adds
    noise. Rounded values match within ``rel_tol``. Percentages match either
    the raw value or value/100 (0.95 vs 95%).
    """
    ev = _evidence_numbers(evidence if not isinstance(evidence, str) else json.loads(evidence))
    ev_all = ev + [v * 100 for v in ev] + [v / 100 for v in ev]
    nums = [n for n in _numbers(answer) if abs(n) > 31]
    bad = []
    for n in nums:
        if not any(abs(n - e) <= max(rel_tol * max(abs(e), 1e-9), 0.51) for e in ev_all):
            bad.append(n)
    checked = len(nums)
    return GroundingReport(score=1.0 if checked == 0 else 1 - len(bad) / checked, checked=checked, ungrounded=bad)
