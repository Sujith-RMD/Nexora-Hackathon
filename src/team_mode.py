"""Deterministic complementary team selection."""

from itertools import combinations


def find_best_team(jd: dict, ranked_candidates: list[dict], team_size: int = 3) -> dict:
    candidates = [candidate for candidate in ranked_candidates or [] if isinstance(candidate, dict)]
    required = {str(req.get("name")) for req in (jd or {}).get("requirements", []) if req.get("importance") == "required"}
    best = None
    for team in combinations(candidates, min(team_size, len(candidates))):
        covered = set()
        evidence = []
        semantic = []
        for candidate in team:
            for match in candidate.get("requirement_matches", []) or []:
                if isinstance(match, dict) and match.get("matched") is True and float(match.get("evidence_strength", 0) or 0) >= 0.6:
                    covered.add(str(match.get("requirement_name")))
            scores = candidate.get("scores") or {}
            if isinstance(scores.get("evidence"), (int, float)): evidence.append(scores["evidence"])
            if isinstance(scores.get("semantic"), (int, float)): semantic.append(scores["semantic"])
        coverage = len(covered & required) / len(required) if required else 0.0
        avg_evidence = sum(evidence) / len(evidence) if evidence else 0.0
        avg_semantic = sum(semantic) / len(semantic) if semantic else 0.0
        score = 0.60 * coverage * 100 + 0.20 * avg_evidence + 0.15 * avg_semantic
        result = {"members": list(team), "selected_candidates": list(team), "covered_required_skills": sorted(covered & required), "remaining_gaps": sorted(required - covered), "required_skill_coverage": round(coverage * 100, 2), "average_evidence": round(avg_evidence, 2), "average_semantic": round(avg_semantic, 2), "team_score": round(score, 2), "complementary_strengths": sorted(covered)}
        if best is None or result["team_score"] > best["team_score"]:
            best = result
    return best or {"members": [], "selected_candidates": [], "covered_required_skills": [], "remaining_gaps": sorted(required), "required_skill_coverage": 0.0, "average_evidence": 0.0, "average_semantic": 0.0, "team_score": 0.0, "complementary_strengths": []}
