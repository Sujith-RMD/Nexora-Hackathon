"""Candidate ranking and top-candidate explanation data module.

Sorts candidates with explicit multi-tier tie-breakers (evidence authenticity ->
required skill coverage -> semantic relevance) and constructs transparent explanation data.
"""

from typing import Any, Dict, List


def _build_explanation_data(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Generate structured top-candidate explanation payload per TEAMMATE_1_CORE_MATCHING.md."""
    req_matches = candidate.get("requirement_matches", [])
    scores = candidate.get("scores", {})

    # Strongest matches: sorted by combined evidence strength and semantic score
    matched_reqs = [m for m in req_matches if m.get("matched", False) or m.get("keyword_match", False)]
    matched_reqs.sort(
        key=lambda m: (float(m.get("evidence_strength", 0.0)), float(m.get("semantic_score", 0.0))),
        reverse=True,
    )

    strongest_matches = [
        {
            "requirement_id": m["requirement_id"],
            "requirement_name": m["requirement_name"],
            "keyword_match": m["keyword_match"],
            "semantic_score": m["semantic_score"],
            "evidence_strength": m["evidence_strength"],
        }
        for m in matched_reqs[:5]
    ]

    # Best evidence snippets (projects/experience with high evidence strength)
    evidence_items = [
        {
            "requirement_name": m["requirement_name"],
            "evidence_type": m["evidence_type"],
            "evidence_strength": m["evidence_strength"],
            "evidence_text": m["evidence_text"],
        }
        for m in req_matches
        if m.get("evidence_text") and m.get("evidence_strength", 0.0) > 0.0
    ]
    evidence_items.sort(key=lambda x: float(x["evidence_strength"]), reverse=True)

    return {
        "strongest_matches": strongest_matches,
        "important_missing": list(candidate.get("missing_required_skills", [])),
        "best_evidence": evidence_items[:4],
        "score_breakdown": dict(scores),
    }


def rank_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rank all candidates using final scores with deterministic multi-tier tie-breakers.

    Tie-break hierarchy per TEAMMATE_1_CORE_MATCHING.md:
      1. final_score (descending)
      2. evidence authenticity score (descending)
      3. count of matched required skills (descending)
      4. semantic score (descending)
    """
    def tie_break_key(c: Dict[str, Any]) -> tuple:
        scores = c.get("scores", {})
        final_score = float(scores.get("final_score", 0.0))
        evidence_score = float(scores.get("evidence", 0.0))
        matched_req_count = len(c.get("matched_required_skills", []))
        semantic_score = float(scores.get("semantic", 0.0))
        return (final_score, evidence_score, matched_req_count, semantic_score)

    ranked = sorted(candidates, key=tie_break_key, reverse=True)

    for i, c in enumerate(ranked, start=1):
        c["rank"] = i
        # Populate explanation data for top candidates
        c["explanation_data"] = _build_explanation_data(c)

    return ranked
