"""Deterministic recruiter outcome drafts and possible role directions."""

from __future__ import annotations

import json
from pathlib import Path


_DEFAULT_CLUSTERS = Path(__file__).resolve().parent.parent / "config" / "role_clusters.json"


def _load_clusters(path: str | Path | None = None) -> dict[str, list[str]]:
    try:
        data = json.loads((Path(path) if path else _DEFAULT_CLUSTERS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(key): list(value) for key, value in data.items() if isinstance(value, list)}


def _candidate_terms(candidate: dict) -> set[str]:
    terms = {str(skill).casefold() for skill in candidate.get("detected_skills", []) if skill}
    for match in candidate.get("requirement_matches", []) or []:
        if not isinstance(match, dict):
            continue
        if match.get("matched") is True:
            name = match.get("requirement_name") or match.get("requirement") or match.get("skill")
            if name:
                terms.add(str(name).casefold())
    return terms


def route_alternative_role(candidate: dict, clusters_path: str | Path | None = None) -> dict:
    """Return the strongest possible role direction from demonstrated skill data."""
    terms = _candidate_terms(candidate if isinstance(candidate, dict) else {})
    best_cluster = "general software engineering"
    best_hits: list[str] = []
    for cluster, skills in _load_clusters(clusters_path).items():
        hits = [skill for skill in skills if str(skill).casefold() in terms]
        if len(hits) > len(best_hits):
            best_cluster, best_hits = cluster, hits
    if best_hits:
        reason = "Strongest structured skill evidence includes " + ", ".join(best_hits[:3]) + "."
    else:
        reason = "The available structured evidence does not indicate a more specific direction."
    result = {"cluster": best_cluster, "reason": reason}
    if isinstance(candidate, dict):
        candidate["alternative_role"] = result
    return result


def generate_rejection_draft(candidate: dict, jd: dict) -> str:
    """Create a recruiter-review draft using only supplied candidate fields."""
    candidate = candidate if isinstance(candidate, dict) else {}
    jd = jd if isinstance(jd, dict) else {}
    name = str(candidate.get("name") or "Candidate")
    role = str(jd.get("title") or "the role")
    matched = candidate.get("matched_required_skills") or []
    missing = candidate.get("missing_required_skills") or []
    alternative = candidate.get("alternative_role") or {}
    strengths = ", ".join(str(item) for item in matched[:3]) or "the strengths reflected in the submitted resume"
    gaps = ", ".join(str(item) for item in missing[:3]) or "No specific gap was recorded by the analysis"
    direction = alternative.get("cluster") if isinstance(alternative, dict) else None
    direction_line = (
        f"The resume may be better aligned with {direction}-focused opportunities."
        if direction else "No alternative role direction was identified from the structured results."
    )
    return (
        "Recruiter-review draft\n\n"
        f"Subject: Update on your application for {role}\n\n"
        f"Hi {name},\n\n"
        f"Thank you for your interest in {role}. After reviewing the application, we will not be moving forward in this process.\n\n"
        f"The strongest relevant areas recorded were: {strengths}.\n"
        f"Important requirements not fully demonstrated in the structured review were: {gaps}.\n\n"
        f"{direction_line}\n\n"
        "Thank you again for your time and interest.\n\n"
        "This draft is for recruiter review and should be finalized by a human."
    )
