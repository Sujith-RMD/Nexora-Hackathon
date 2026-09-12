"""Over-qualification flag — Differentiator D6 (Teammate 2).

Contract: MASTER_CONTEXT.md #5.3-D6, #20 and TEAMMATE_2_TRUST_AND_INNOVATION.md #15.

    flag_overqualification(jd: dict, candidate: dict) -> dict
        -> {"flag": bool, "reasons": list[str]}

Design rules (hard):
  * This is primarily a RECRUITER FLAG, never a ranking penalty. We do not
    touch ``scores`` or ``final_score`` here.
  * Only applies when the JD role level is ``intern`` or ``junior``.
  * Signals come from seniority language in the resume only:
    compound senior/lead/staff titles, explicit years-of-experience claims,
    and leadership concentration.
  * Deliberately AVOIDS: age inference, graduation-year estimates, and any
    demographic assumption. Education sections are never scanned.
"""

from __future__ import annotations

import re

# Only these JD levels make over-qualification worth checking.
APPLICABLE_ROLE_LEVELS = {"intern", "junior"}

# Minimum claimed years of experience that is "substantially above" role level.
YEARS_THRESHOLD = {"intern": 5, "junior": 7}

# Compound title patterns (kept compound on purpose: a bare word like
# "senior" or "lead" in prose would be a false-positive machine).
SENIOR_TITLE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("senior-level title", re.compile(
        r"\bsenior\b[^.\n]{0,40}?\b(developer|engineer|programmer|consultant|analyst)\b",
        re.IGNORECASE,
    )),
    ("lead role", re.compile(
        r"\b(tech|technical|team|engineering)?\s*lead\s+(developer|engineer|software|full[- ]?stack|frontend|backend)\b"
        r"|\b(tech|technical|team)\s+lead\b",
        re.IGNORECASE,
    )),
    ("staff/principal role", re.compile(
        r"\b(staff|principal)\s+(engineer|developer|architect)\b", re.IGNORECASE,
    )),
    ("management role", re.compile(
        r"\b(engineering manager|software manager|development manager|head of engineering"
        r"|vp of engineering|vp engineering|director of engineering|cto)\b", re.IGNORECASE,
    )),
    ("architect role", re.compile(
        r"\b(solution|software|systems|enterprise|solutions)\s+architect\b", re.IGNORECASE,
    )),
]

# Explicit experience-length claims, e.g. "5+ years of experience", "7 yrs".
YEARS_PATTERN = re.compile(r"\b(\d{1,2})\s*\+?\s*(?:years|yrs)\b", re.IGNORECASE)

# Leadership-concentration cues (deliberately narrow to avoid "managed state"
# style false positives from frontend prose).
LEADERSHIP_PATTERNS = [
    re.compile(r"\bteam of \d+\b", re.IGNORECASE),
    re.compile(r"\bled (?:a |the )?(?:team|group|squad|developers|engineers|interns)\b", re.IGNORECASE),
    re.compile(r"\bmanaged (?:a )?(?:team|group|squad|developers|engineers)\b", re.IGNORECASE),
    re.compile(r"\bmentored\b", re.IGNORECASE),
    re.compile(r"\breported directly\b", re.IGNORECASE),
]
LEADERSHIP_MIN_HITS = 3


def _resume_seniority_text(jd: dict, candidate: dict) -> str:
    """Text sources safe to scan: work experience, projects, and clean/raw
    text fallbacks. Education is intentionally excluded (no age inference)."""
    sections = candidate.get("sections") or {}
    parts = [
        str(sections.get("experience") or ""),
        str(sections.get("projects") or ""),
    ]
    if not any(part.strip() for part in parts):
        parts.append(str(candidate.get("clean_text") or candidate.get("raw_text") or ""))
    return "\n".join(part for part in parts if part)


def flag_overqualification(jd: dict, candidate: dict) -> dict:
    """Evaluate the candidate and return ``{"flag", "reasons"}``.

    Also attaches the same dict to ``candidate["overqualification"]`` so the
    shared schema is populated for Teammate 3's UI.
    """
    result: dict = {"flag": False, "reasons": []}

    role_level = str(jd.get("role_level") or "unknown").strip().lower()
    if role_level not in APPLICABLE_ROLE_LEVELS:
        candidate["overqualification"] = result
        return result

    text = _resume_seniority_text(jd, candidate)
    if not text.strip():
        candidate["overqualification"] = result
        return result

    reasons: list[str] = []

    # 1. Senior/lead/staff title language.
    detected_titles: list[str] = []
    for label, pattern in SENIOR_TITLE_PATTERNS:
        if pattern.search(text):
            detected_titles.append(label)

    if len(detected_titles) >= 2:
        reasons.append(
            "Multiple senior-level title patterns detected ("
            + "; ".join(detected_titles)
            + ")."
        )
    elif len(detected_titles) == 1:
        reasons.append(f"Senior-level role language detected: {detected_titles[0]}.")

    # 2. Explicit experience-length claims far above the role level.
    claimed_years = [int(m) for m in YEARS_PATTERN.findall(text)]
    # Ignore implausible values (typos/years like 1995 captured accidentally).
    claimed_years = [y for y in claimed_years if y <= 40]
    threshold = YEARS_THRESHOLD.get(role_level, 6)
    if claimed_years and max(claimed_years) >= threshold:
        reasons.append(
            f"Experience level appears substantially above this {role_level}-level "
            f"role (claims up to {max(claimed_years)} years)."
        )

    # 3. Leadership-heavy resume.
    leadership_hits = sum(len(p.findall(text)) for p in LEADERSHIP_PATTERNS)
    if leadership_hits >= LEADERSHIP_MIN_HITS:
        reasons.append(
            "Resume is leadership-heavy "
            f"({leadership_hits} team-lead/management cues), which may not align "
            "with an individual-contributor intern/junior role."
        )

    result["flag"] = bool(reasons)
    result["reasons"] = reasons
    candidate["overqualification"] = result
    return result
