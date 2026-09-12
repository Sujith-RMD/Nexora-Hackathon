"""Deterministic, flag-only role-level mismatch review."""

import re


def flag_overqualification(jd: dict, candidate: dict) -> dict:
    role = str((jd or {}).get("role_level", "unknown")).lower()
    text = "\n".join(str((candidate.get("sections") or {}).get(key, "")) for key in ("experience", "projects"))
    reasons = []
    if role in {"intern", "junior"}:
        if re.search(r"\b(senior|staff|principal|lead|director|manager)\b", text, re.I):
            reasons.append("Senior-level role language appears in experience or project text.")
        years = re.findall(r"\b(\d{1,2})\s*\+?\s*(?:years|yrs)\b", text, re.I)
        if any(int(value) >= (5 if role == "intern" else 7) for value in years):
            reasons.append("Experience-length language appears substantially above the role level.")
    result = {"flag": bool(reasons), "reasons": reasons}
    candidate["overqualification"] = result
    return result
