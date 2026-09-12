"""Deterministic, clearly labelled Top-3 counterfactual guidance."""

from __future__ import annotations


def generate_counterfactual(candidate: dict, ranked_candidates: list[dict], jd: dict, scorer=None) -> dict:
    scores = candidate.get("scores") or {}
    current = scores.get("final_score", 0.0) if isinstance(scores.get("final_score", 0.0), (int, float)) else 0.0
    rank = candidate.get("rank") or 0
    if rank and rank <= 3:
        result = {"target_rank": rank, "target_score": current, "suggested_improvements": [], "projected_score": current, "current_score": current, "reached_target": True, "message": "Candidate is already in the Top 3.", "disclaimer": "Simulation — not a hiring guarantee."}
        candidate["counterfactual"] = result
        return result
    ranked = [item for item in ranked_candidates or [] if isinstance(item, dict)]
    target = ((ranked[2].get("scores") or {}).get("final_score", 0.0) if len(ranked) >= 3 else current)
    improvements = []
    for match in candidate.get("requirement_matches", []) or []:
        if not isinstance(match, dict) or match.get("matched") is True:
            continue
        name = match.get("requirement_name") or match.get("requirement") or "the requirement"
        improvements.append({"requirement": name, "change": f"Add strong demonstrated project/work evidence for {name}.", "estimated_gain": "Not available"})
        if len(improvements) == 3:
            break
    result = {"target_rank": 3, "target_score": target, "suggested_improvements": improvements, "projected_score": "Not available", "current_score": current, "reached_target": False, "message": "The following simulated evidence improvements could strengthen the candidate's position.", "disclaimer": "Simulation — not a hiring guarantee."}
    candidate["counterfactual"] = result
    return result
