"""Evidence Authenticity Scoring module.

Distinguishes between skills merely listed in a 'Skills' catalog and skills actively
demonstrated in project or work experience with strong context and action verbs.
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from .skill_extractor import find_skill_matches, load_skill_aliases, normalize_skill


ACTION_VERBS = {
    "built",
    "developed",
    "implemented",
    "designed",
    "created",
    "deployed",
    "integrated",
    "optimized",
    "maintained",
    "tested",
    "architected",
    "engineered",
    "automated",
    "configured",
    "authored",
    "spearheaded",
    "launched",
    "refactored",
    "scaled",
    "analyzed",
    "migrated",
}


def _has_action_verb(sentence: str) -> bool:
    """Check whether a sentence contains strong technical action verbs."""
    tokens = re.findall(r"\b[a-zA-Z]+\b", sentence.lower())
    return any(t in ACTION_VERBS for t in tokens)


def _find_matching_sentences(skill: str, text: str, aliases: Optional[Dict[str, str]] = None) -> List[str]:
    """Find sentences or bullet points in text where the skill is mentioned."""
    if not text:
        return []
    # Split on newlines, bullet points, semicolons, or sentence-ending periods followed by whitespace
    raw_sentences = re.split(r"\n+|[•;]|\s+[-*]\s+|\.\s+(?=[A-Z0-9\"'(\[])", text)
    sentences = [s.strip() for s in raw_sentences if s.strip()]
    matches: List[str] = []
    for s in sentences:
        is_m, _ = find_skill_matches(skill, s, aliases)
        if is_m:
            matches.append(s)
    return matches


def evaluate_requirement_evidence(
    requirement: Dict[str, Any],
    candidate_sections: Dict[str, str],
    aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Evaluate evidence authenticity for a single requirement across resume sections."""
    alias_dict = aliases if aliases is not None else load_skill_aliases()
    if requirement.get("alternatives"):
        results = [evaluate_requirement_evidence({**requirement, "name": name, "alternatives": []}, candidate_sections, alias_dict) for name in requirement["alternatives"]]
        best = max(results, key=lambda r: r["evidence_strength"])
        return {**best, "requirement_name": requirement["name"], "evidence_alternative": best["requirement_name"] if best["evidence_strength"] else ""}
    req_name = str(requirement.get("name", ""))
    canonical = normalize_skill(req_name, alias_dict)

    found_sections: Dict[str, List[str]] = {}
    for section_name in ["projects", "experience", "certifications", "skills", "education", "other"]:
        sec_text = candidate_sections.get(section_name, "")
        if not sec_text:
            continue
        matching_sents = _find_matching_sentences(canonical, sec_text, alias_dict)
        if matching_sents:
            found_sections[section_name] = matching_sents

    # Determine highest authenticity tier
    strength = 0.0
    evidence_type = "none"
    evidence_text = ""

    # Tier 1: Projects or Experience
    proj_sents = found_sections.get("projects", [])
    exp_sents = found_sections.get("experience", [])
    action_sents = proj_sents + exp_sents

    if action_sents:
        # Check for action verb & contextual depth
        best_sentence = max(action_sents, key=lambda s: (_has_action_verb(s) and len(s) >= 35, _has_action_verb(s), len(s)))
        has_action = _has_action_verb(best_sentence)
        has_context = len(best_sentence) >= 35

        # Select the most detailed sentence as representative snippet
        evidence_text = best_sentence

        if best_sentence in proj_sents:
            evidence_type = "project"
        else:
            evidence_type = "experience"

        if has_action and has_context:
            strength = 1.00
        elif has_action or has_context:
            strength = 0.85
        else:
            strength = 0.75

    # Tier 2: Certifications
    elif "certifications" in found_sections:
        strength = 0.65
        evidence_type = "certification"
        evidence_text = found_sections["certifications"][0]

    # Tier 3: Multiple other sections (e.g. Skills + Education)
    elif len(found_sections) > 1:
        strength = 0.60
        evidence_type = "multi_section"
        first_sec = list(found_sections.keys())[0]
        evidence_text = found_sections[first_sec][0]

    # Tier 4: Skills section only
    elif "skills" in found_sections:
        strength = 0.35
        evidence_type = "skills_list"
        evidence_text = found_sections["skills"][0]

    # Tier 5: Other section
    elif "other" in found_sections or "education" in found_sections:
        strength = 0.30
        sec_key = "education" if "education" in found_sections else "other"
        evidence_type = sec_key
        evidence_text = found_sections[sec_key][0]

    return {
        "requirement_id": requirement.get("id", f"req_{canonical}"),
        "requirement_name": canonical,
        "evidence_strength": strength,
        "evidence_type": evidence_type,
        "evidence_text": evidence_text,
    }


def score_evidence(
    jd: Dict[str, Any],
    candidate: Dict[str, Any],
    aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Calculate requirement-level and aggregate evidence authenticity scores.

    Returns:
      {
        "evidence_score": float (0-100),
        "requirement_matches": list of dicts
      }
    """
    alias_dict = aliases if aliases is not None else load_skill_aliases()
    requirements = jd.get("requirements", [])
    sections = candidate.get("sections", {})

    total_weight = 0.0
    weighted_strength_sum = 0.0
    req_matches: List[Dict[str, Any]] = []

    for req in requirements:
        weight = float(req.get("weight", 1.0))
        total_weight += weight

        res = evaluate_requirement_evidence(req, sections, alias_dict)
        req_matches.append(res)
        weighted_strength_sum += res["evidence_strength"] * weight

    # Scale 0.0-1.0 to 0-100
    aggregate_score = (
        round(100.0 * (weighted_strength_sum / total_weight), 2)
        if total_weight > 0
        else 0.0
    )

    return {
        "evidence_score": aggregate_score,
        "requirement_matches": req_matches,
    }
