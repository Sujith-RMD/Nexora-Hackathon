"""JD bias / narrow-phrasing reviewer — lightweight integration fallback.

NOTE FOR TEAMMATE 3: ``src/jd_bias.py`` and ``config/bias_rules.json`` were
never delivered on teammate-3. Teammate 2 wrote this MINIMAL deterministic
version during branch integration so the JD Review tab shows real analysis
instead of a stub. It fills the exact ``bias_flags`` slot from
MASTER_CONTEXT #7.1 (``{phrase, reason, suggestion}``). Replace freely —
keep the function name ``review_jd(jd) -> list[dict]`` and the key contract.

Fully local, rule-based, deterministic. No LLM, no APIs. It flags risky
PHRASING in the job description text itself (never people), and every hint
quotes the exact phrase found.
"""

from __future__ import annotations

from typing import Any, Dict, List

# (phrase, reason, suggestion) — lowercase substring rules.
PHRASING_RULES: List[tuple] = [
    ("rockstar",
     "Mythologized-role wording can discourage qualified applicants.",
     "Consider simply: 'full stack developer'."),
    ("ninja",
     "Mythologized-role wording can discourage qualified applicants.",
     "Consider simply: 'developer'."),
    ("wizard",
     "Mythologized-role wording can discourage qualified applicants.",
     "Consider simply: 'developer'."),
    ("guru",
     "Self-labels like 'guru' measure identity, not skills.",
     "Describe the expected skill depth instead."),
    ("digital native",
     "Implies an age cohort rather than a skill.",
     "State the specific tool-comfort level you actually need."),
    ("young",
     "Age-coded wording in a job ad.",
     "Remove it; age is not a job requirement."),
    ("recent graduate",
     "Filters by life stage, not capability.",
     "Try: 'open to candidates with up to 1 year of experience'."),
    ("energetic",
     "Energy/vibe wording is subjective and often age- or health-coded.",
     "Describe the actual working cadence required."),
    ("culture fit",
     "'Fit' historically masks demographic preferences.",
     "Consider 'culture add' with concrete, stated values."),
    ("he/she",
     "Gendered default pronoun.",
     "Use 'they'."),
    ("mankind",
     "Gendered word for people.",
     "Use 'humankind'."),
    ("must have a degree",
     "A hard degree gate narrows the funnel, especially for intern roles.",
     "Consider 'degree or equivalent practical experience'."),
    ("topper",
     "Rank/grade elitism proxies are noisy and exclusionary.",
     "Ask for a demonstrated project or exercise instead."),
    ("good communication",
     "Vague soft-skill phrasing is unmeasurable at shortlisting time.",
     "Specify the artifact: e.g. 'writes clear PR descriptions'."),
]

# Beyond this many hard requirements, an intern/junior JD reads as a wish list.
MAX_REASONABLE_REQUIRED = 10


def review_jd(jd: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return bias-flag dicts ``{phrase, reason, suggestion}`` for the JD.

    Deterministic rule scan; same input always yields identical output.
    """
    text = str(jd.get("clean_text") or jd.get("raw_text") or "").lower()
    flags: List[Dict[str, str]] = []
    seen: set = set()

    for phrase, reason, suggestion in PHRASING_RULES:
        if phrase in text and phrase not in seen:
            seen.add(phrase)
            flags.append({
                "phrase": phrase,
                "reason": reason,
                "suggestion": suggestion,
            })

    requirements = jd.get("requirements") or []
    required_count = sum(1 for r in requirements if r.get("importance") == "required")
    if required_count > MAX_REASONABLE_REQUIRED:
        flags.append({
            "phrase": f"{required_count} required skills",
            "reason": "A long hard-requirement list on an intern/junior role "
                      "sharpens the missing-skill penalty cliff and shrinks "
                      "the funnel.",
            "suggestion": "Re-audit: keep only what is truly non-negotiable "
                          "and move the rest to 'preferred'.",
        })
    return flags
