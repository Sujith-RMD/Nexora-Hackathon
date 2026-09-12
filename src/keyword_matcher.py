"""Explicit keyword matching module.

Performs section-aware canonical and alias matching across candidate sections
and calculates weighted aggregate keyword scores.
"""

from typing import Any, Dict, List, Optional
from .skill_extractor import find_skill_matches, load_skill_aliases, normalize_skill


# Priority order when reporting where a keyword appeared
SECTION_PRIORITY = ["projects", "experience", "certifications", "skills", "education", "other"]


def match_requirement_keywords(
    requirement: Dict[str, Any],
    candidate_sections: Dict[str, str],
    aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Test if a single requirement is present in candidate sections.

    Returns requirement match metadata including matched variant and highest priority section.
    """
    alias_dict = aliases if aliases is not None else load_skill_aliases()
    req_name = str(requirement.get("name", ""))
    canonical = normalize_skill(req_name, alias_dict)

    matched = False
    best_section = "none"
    matched_variant = None

    for section in SECTION_PRIORITY:
        sec_text = candidate_sections.get(section, "")
        if not sec_text:
            continue
        is_m, variant = find_skill_matches(canonical, sec_text, alias_dict)
        if is_m:
            matched = True
            if best_section == "none":
                best_section = section
                matched_variant = variant

    return {
        "requirement_id": requirement.get("id", f"req_{canonical}"),
        "requirement_name": canonical,
        "keyword_match": matched,
        "keyword_score": 100.0 if matched else 0.0,
        "matched_variant": matched_variant or "",
        "section": best_section,
    }


def keyword_match(
    jd: Dict[str, Any],
    candidate: Dict[str, Any],
    aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Calculate keyword matches for all JD requirements against candidate sections.

    Returns:
      {
        "keyword_score": float (0-100),
        "requirement_matches": list of dicts,
        "matched_required": list of str,
        "missing_required": list of str,
        "matched_preferred": list of str
      }
    """
    alias_dict = aliases if aliases is not None else load_skill_aliases()
    requirements = jd.get("requirements", [])
    sections = candidate.get("sections", {})

    total_weight = 0.0
    matched_weight = 0.0

    req_matches: List[Dict[str, Any]] = []
    matched_required: List[str] = []
    missing_required: List[str] = []
    matched_preferred: List[str] = []

    for req in requirements:
        weight = float(req.get("weight", 1.0))
        total_weight += weight
        importance = req.get("importance", "context")
        name = str(req.get("name", ""))

        res = match_requirement_keywords(req, sections, alias_dict)
        req_matches.append(res)

        if res["keyword_match"]:
            matched_weight += weight
            if importance == "required":
                matched_required.append(name)
            elif importance == "preferred":
                matched_preferred.append(name)
        else:
            if importance == "required":
                missing_required.append(name)

    aggregate_score = (100.0 * matched_weight / total_weight) if total_weight > 0 else 0.0

    return {
        "keyword_score": round(aggregate_score, 2),
        "requirement_matches": req_matches,
        "matched_required": matched_required,
        "missing_required": missing_required,
        "matched_preferred": matched_preferred,
    }
