"""Core hybrid scoring module.

Combines semantic relevance, explicit keyword coverage, evidence authenticity,
and skill graph scores into a unified hybrid score with transparent critical-missing penalties.
"""

from typing import Any, Dict, List, Optional, Tuple


def calculate_critical_missing_penalty(
    missing_required_skills: List[str],
    max_penalty: float = 10.0,
    penalty_per_missing: float = 3.5,
) -> float:
    """Calculate bounded penalty for missing mandatory requirements.

    Never deducts more than max_penalty (default 10 points) to avoid distorting ranking.
    """
    count = len(missing_required_skills)
    if count == 0:
        return 0.0
    return min(max_penalty, count * penalty_per_missing)


def merge_requirement_matches(
    keyword_matches: List[Dict[str, Any]],
    semantic_matches: List[Dict[str, Any]],
    evidence_matches: List[Dict[str, Any]],
    graph_matches: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Synthesize requirement-level results into the shared MASTER_CONTEXT.md structure."""
    sem_map = {m["requirement_id"]: m for m in semantic_matches}
    evi_map = {m["requirement_id"]: m for m in evidence_matches}
    grp_map = {m["requirement_id"]: m for m in (graph_matches or [])}

    unified: List[Dict[str, Any]] = []

    for kw in keyword_matches:
        req_id = kw["requirement_id"]
        req_name = kw["requirement_name"]

        sem = sem_map.get(req_id, {})
        evi = evi_map.get(req_id, {})
        grp = grp_map.get(req_id, {})

        is_kw_match = bool(kw.get("keyword_match", False))
        sem_score = float(sem.get("semantic_score", 0.0))
        evi_strength = float(evi.get("evidence_strength", 0.0))
        grp_score = float(grp.get("graph_score", 0.0))

        # Overall requirement matched flag: true if direct keyword or strong semantic/evidence support
        overall_matched = is_kw_match or (sem_score >= 65.0 and evi_strength >= 0.35)

        # Best explanatory snippet: prefer evidence text if available, fallback to semantic best chunk
        evidence_snippet = evi.get("evidence_text", "")
        if not evidence_snippet and sem.get("best_chunk"):
            evidence_snippet = sem.get("best_chunk", "")

        unified.append(
            {
                "requirement_id": req_id,
                "requirement_name": req_name,
                "keyword_match": is_kw_match,
                "keyword_score": float(kw.get("keyword_score", 0.0)),
                "semantic_score": sem_score,
                "graph_match": bool(grp.get("graph_match", False)),
                "graph_path": list(grp.get("graph_path", [])),
                "graph_score": grp_score,
                "evidence_strength": evi_strength,
                "evidence_type": str(evi.get("evidence_type", "none")),
                "evidence_text": evidence_snippet,
                "matched": overall_matched,
            }
        )

    return unified


def score_candidate(
    jd: Dict[str, Any],
    candidate: Dict[str, Any],
    keyword_result: Dict[str, Any],
    semantic_result: Dict[str, Any],
    evidence_result: Dict[str, Any],
    graph_score: float = 0.0,
    graph_matches: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Calculate hybrid score components and update candidate dictionary in place.

    Weights per MASTER_CONTEXT.md:
      - Semantic: 45%
      - Keyword: 35%
      - Evidence: 15%
      - Graph: 5%
    """
    sem_score = float(semantic_result.get("semantic_score", 0.0))
    kw_score = float(keyword_result.get("keyword_score", 0.0))
    evi_score = float(evidence_result.get("evidence_score", 0.0))
    grp_score = float(graph_score)

    base_score = (
        0.45 * sem_score
        + 0.35 * kw_score
        + 0.15 * evi_score
        + 0.05 * grp_score
    )

    missing_required = keyword_result.get("missing_required", [])
    penalty = calculate_critical_missing_penalty(missing_required)
    final_score = max(0.0, base_score - penalty)

    unified_matches = merge_requirement_matches(
        keyword_result.get("requirement_matches", []),
        semantic_result.get("requirement_matches", []),
        evidence_result.get("requirement_matches", []),
        graph_matches,
    )

    candidate["requirement_matches"] = unified_matches
    candidate["matched_required_skills"] = keyword_result.get("matched_required", [])
    candidate["missing_required_skills"] = missing_required
    candidate["matched_preferred_skills"] = keyword_result.get("matched_preferred", [])

    candidate["scores"] = {
        "semantic": round(sem_score, 2),
        "keyword": round(kw_score, 2),
        "evidence": round(evi_score, 2),
        "graph": round(grp_score, 2),
        "base_score": round(base_score, 2),
        "final_score": round(final_score, 2),
    }

    return candidate
