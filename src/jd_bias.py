"""Deterministic detector for potentially narrow job-description phrasing."""

from __future__ import annotations

import json
from pathlib import Path
import re


_DEFAULT_RULES = Path(__file__).resolve().parent.parent / "config" / "bias_rules.json"


def _load_rules(path: str | Path | None = None) -> list[dict]:
    target = Path(path) if path else _DEFAULT_RULES
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [rule for rule in data if isinstance(rule, dict) and rule.get("pattern")]


def detect_jd_bias(jd_text: str) -> list[dict]:
    """Return rule matches as potentially narrow phrasing, never a legal finding."""
    if not isinstance(jd_text, str) or not jd_text.strip():
        return []
    flags = []
    lowered = jd_text.casefold()
    for rule in _load_rules():
        phrase = str(rule["pattern"])
        if re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", lowered):
            flags.append(
                {
                    "phrase": phrase,
                    "reason": str(rule.get("reason", "Potentially narrow phrasing.")),
                    "suggestion": str(rule.get("suggestion", "Describe the job requirement more precisely.")),
                }
            )
    return flags
