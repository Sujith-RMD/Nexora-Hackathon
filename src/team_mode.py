"""Team composition mode — Differentiator D5 (Teammate 2).

Contract: MASTER_CONTEXT.md #5.3-D5, #15, #20 and
TEAMMATE_2_TRUST_AND_INNOVATION.md #14.

    find_best_team(jd: dict, ranked_candidates: list[dict], team_size: int = 3) -> dict

Answers: "Which N candidates TOGETHER cover the JD requirements best?"

Secondary mode only — it never replaces the individual ranking.

For C(18, 3) = 816 combinations brute force is trivial; every trio is scored:

    team_score = 0.60 * coverage_of_required_requirements
               + 0.20 * average_evidence_strength       (best member per requirement)
               + 0.15 * average_semantic_relevance
               + 0.05 * complementary_skill_bonus       (unique single-member covers)

Guardrail (MASTER_CONTEXT #25): related/graph evidence NEVER counts toward
hard required-skill coverage; only explicit matches with sufficient evidence.
All outputs are plain JSON-serializable structures (TEAMMATE_2 #19).
"""

from __future__ import annotations

from itertools import combinations

# --- Objective weights (MASTER_CONTEXT #5.3-D5) ------------------------------
TEAM_WEIGHTS = {
    "coverage": 0.60,
    "evidence": 0.20,
    "semantic": 0.15,
    "complementarity": 0.05,
}

# A requirement counts as covered for team purposes only when the member has
# an explicit match with at least this evidence strength (0.60 = repeated
# sections or better per MASTER_CONTEXT #5.3-D2 table).
EVIDENCE_COVERAGE_MIN = 0.60
WEAK_COVERAGE_MIN = 0.35  # still contributes to the evidence average, weakly

DEFAULT_IMPORTANCE_WEIGHT = {"required": 3.0, "preferred": 2.0, "context": 1.0}
RUNNER_UP_TEAMS = 3
MODE_NOTE = (
    "Secondary view: this collaboration mode does not replace the required "
    "individual ranking."
)


def _required_requirements(jd: dict) -> list[dict]:
    return [
        r for r in (jd.get("requirements") or [])
        if isinstance(r, dict) and r.get("importance") == "required"
    ]


def _candidate_coverage(candidate: dict) -> dict[str, dict]:
    """{requirement_id: {"strength": float, "entry": dict}} for REQUIRED
    requirements this candidate explicitly covers with evidence."""
    covered: dict[str, dict] = {}
    for entry in candidate.get("requirement_matches") or []:
        if not isinstance(entry, dict) or not entry.get("matched"):
            continue
        # Guardrail: graph-only support is not proof of the explicit requirement.
        strength = float(entry.get("evidence_strength") or 0.0)
        if strength >= EVIDENCE_COVERAGE_MIN:
            covered[str(entry.get("requirement_id"))] = {"strength": strength, "entry": entry}
    return covered


def _display_name(req: dict) -> str:
    return str(req.get("display_name") or req.get("name") or req.get("id") or "")


def _score_team(
    team: tuple[dict, ...],
    requirements: list[dict],
    coverage_maps: list[dict[str, dict]],
) -> dict:
    req_ids = [str(r.get("id")) for r in requirements]

    if req_ids:
        # Coverage: fraction of required requirements covered by >= 1 member.
        covered_ids = set()
        for cmap in coverage_maps:
            covered_ids.update(cmap.keys())
        covered_ids &= set(req_ids)
        coverage_score = 100.0 * len(covered_ids) / len(req_ids)

        # Evidence: strongest member evidence per requirement (0 if nobody).
        evidence_total = 0.0
        for rid in req_ids:
            best = max((cm[rid]["strength"] for cm in coverage_maps if rid in cm), default=0.0)
            evidence_total += best
        evidence_score = 100.0 * evidence_total / len(req_ids)

        # Complementarity: requirements covered by exactly one member.
        unique_counts = {rid: 0 for rid in req_ids}
        for cmap in coverage_maps:
            for rid in cmap:
                if rid in unique_counts:
                    unique_counts[rid] += 1
        unique_total = sum(1 for rid, n in unique_counts.items() if n == 1)
        complementarity_score = (
            100.0 * unique_total / len(covered_ids) if covered_ids else 0.0
        )
    else:
        coverage_score = evidence_score = complementarity_score = 0.0
        covered_ids = set()
        unique_counts = {}

    semantic_score = sum(
        float(((c.get("scores") or {}).get("semantic")) or 0.0) for c in team
    ) / len(team)

    team_score = (
        TEAM_WEIGHTS["coverage"] * coverage_score
        + TEAM_WEIGHTS["evidence"] * evidence_score
        + TEAM_WEIGHTS["semantic"] * semantic_score
        + TEAM_WEIGHTS["complementarity"] * complementarity_score
    )

    return {
        "team_score": team_score,
        "coverage_score": coverage_score,
        "evidence_score": evidence_score,
        "semantic_score": semantic_score,
        "complementarity_score": complementarity_score,
        "covered_ids": covered_ids,
        "unique_counts": unique_counts,
    }


def find_best_team(
    jd: dict,
    ranked_candidates: list[dict],
    team_size: int = 3,
) -> dict:
    """Brute-force the best complementary team and return a serializable
    result object (TEAMMATE_2 #14 shape)."""
    requirements = _required_requirements(jd)
    req_display = {str(r.get("id")): _display_name(r) for r in requirements}

    empty_result = {
        "members": [],
        "member_names": [],
        "team_score": 0.0,
        "required_skill_coverage": 0.0,
        "member_contributions": {},
        "member_scores": {},
        "remaining_gaps": [name for name in req_display.values()],
        "runner_up_teams": [],
        "team_size": team_size,
        "teams_evaluated": 0,
        "note": MODE_NOTE,
    }

    pool = [c for c in ranked_candidates if isinstance(c, dict)]
    if len(pool) < team_size or team_size < 1:
        empty_result["note"] = (
            f"Team mode needs at least {team_size} ranked candidates "
            f"(found {len(pool)}). " + MODE_NOTE
        )
        return empty_result

    coverage_maps = [_candidate_coverage(c) for c in pool]

    scored: list[tuple[dict, tuple[dict, ...]]] = []
    for idx_team in combinations(range(len(pool)), team_size):
        team = tuple(pool[i] for i in idx_team)
        maps = [coverage_maps[i] for i in idx_team]
        scored.append((_score_team(team, requirements, maps), team))

    # Deterministic ordering: score desc, then lexicographic member ids.
    scored.sort(
        key=lambda pair: (
            -pair[0]["team_score"],
            tuple(sorted(str(c.get("candidate_id")) for c in pair[1])),
        )
    )

    best, best_team = scored[0]

    member_ids = [str(c.get("candidate_id")) for c in best_team]
    member_contributions: dict[str, list[str]] = {}
    member_scores: dict[str, dict[str, float]] = {}
    for position, (candidate, cmap) in enumerate(zip(best_team, coverage_maps)):
        cid = member_ids[position]
        unique = [
            req_display.get(rid, rid)
            for rid, n in best["unique_counts"].items()
            if n == 1 and rid in cmap
        ]
        member_contributions[cid] = sorted(unique)
        scores = candidate.get("scores") or {}
        member_scores[cid] = {
            "final_score": float(scores.get("final_score") or 0.0),
            "rank": int(candidate.get("rank") or 0),
        }

    remaining_gaps = sorted(
        req_display.get(rid, rid) for rid in req_display if rid not in best["covered_ids"]
    )

    runner_ups = [
        {
            "members": [str(c.get("candidate_id")) for c in team],
            "member_names": [str(c.get("name") or c.get("candidate_id")) for c in team],
            "team_score": round(scores["team_score"], 4),
            "required_skill_coverage": round(scores["coverage_score"], 4),
        }
        for scores, team in scored[1 : 1 + RUNNER_UP_TEAMS]
    ]

    return {
        "members": member_ids,
        "member_names": [str(c.get("name") or c.get("candidate_id")) for c in best_team],
        "team_score": best["team_score"],
        "required_skill_coverage": best["coverage_score"],
        "evidence_score": best["evidence_score"],
        "semantic_score": best["semantic_score"],
        "complementarity_score": best["complementarity_score"],
        "member_contributions": member_contributions,
        "member_scores": member_scores,
        "remaining_gaps": remaining_gaps,
        "runner_up_teams": runner_ups,
        "team_size": team_size,
        "teams_evaluated": len(scored),
        "note": MODE_NOTE,
    }
