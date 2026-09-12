"""Self-critiquing / red-team ranking — Differentiator D1 (Teammate 2).

Contract: MASTER_CONTEXT.md #12, #20 and TEAMMATE_2_TRUST_AND_INNOVATION.md #8-#10.

    critique_ranking(jd: dict, ranked_candidates: list[dict]) -> list[dict]

Populates ``candidate["critique"]`` in place with the shared schema shape:

    {"confidence": "high|medium|low",
     "flags": list[str],
     "summary": str,
     "human_review_recommended": bool}

Implemented checks (transparent rules only — the critic must not invent facts):

    R1  Semantic vs keyword disagreement   (gap >= 25 minor, >= 35 major)
    R2  High rank with weak evidence       (top-3, evidence < 60)
    R3  Missing critical requirement       (top-3, high-weight required missing)
    R4  Close ranking margin               (neighbor gap < 2.5 points)
    R5  Weight sensitivity                 (re-rank under safe presets)
    R6  Low parse quality                  (parse_quality.score < 55)
    R7  Skills-list concentration          (majority of matches listed-only)

R5 note: this module deliberately does NOT import the core scorer. The base
score is a pinned, documented formula (MASTER_CONTEXT #8), and every component
(semantic/keyword/evidence/graph) is stored on the candidate, so sensitivity
re-ranking is computed locally with evidence/graph weights held fixed.
"""

from __future__ import annotations

from typing import Any

# --- Documented base-score blend (MASTER_CONTEXT #8) ------------------------
BASE_WEIGHTS = {"semantic": 0.45, "keyword": 0.35, "evidence": 0.15, "graph": 0.05}

# Sensitivity presets vary only semantic vs keyword; their combined share is
# renormalized to the fixed 0.80 so evidence (0.15) and graph (0.05) weights
# stay untouched — option 2 in TEAMMATE_2 #9 R5.
SEM_KW_SHARE = BASE_WEIGHTS["semantic"] + BASE_WEIGHTS["keyword"]  # 0.80
WEIGHT_PRESETS = [
    {"semantic": 0.55, "keyword": 0.45},
    {"semantic": 0.45, "keyword": 0.55},
    {"semantic": 0.60, "keyword": 0.40},
    {"semantic": 0.40, "keyword": 0.60},
]

# --- Thresholds (deterministic, single source of truth) ---------------------
GAP_MINOR = 25.0
GAP_MAJOR = 35.0
EVIDENCE_WEAK_THRESHOLD = 60.0
TOP_RANK_CUTOFF = 3
CLOSE_MARGIN_POINTS = 2.5
PARSE_QUALITY_LOW = 55.0
SKILLS_ONLY_MAX_STRENGTH = 0.35
SKILLS_ONLY_SHARE_FLAG = 0.60
SKILLS_ONLY_MIN_MATCHES = 3
CRITICAL_WEIGHT = 3.0
RANK_MOVE_MAJOR = 2          # positions moved under presets that count as major
TOP3_STABILITY_KEY = "stable_top3"


def _score(candidate: dict, key: str) -> float:
    try:
        return float((candidate.get("scores") or {}).get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _recomputed_base(candidate: dict) -> float:
    return (
        BASE_WEIGHTS["semantic"] * _score(candidate, "semantic")
        + BASE_WEIGHTS["keyword"] * _score(candidate, "keyword")
        + BASE_WEIGHTS["evidence"] * _score(candidate, "evidence")
        + BASE_WEIGHTS["graph"] * _score(candidate, "graph")
    )


def _blended_for_preset(candidate: dict, preset: dict[str, float]) -> float:
    sem_w = preset["semantic"] * SEM_KW_SHARE
    kw_w = preset["keyword"] * SEM_KW_SHARE
    return (
        sem_w * _score(candidate, "semantic")
        + kw_w * _score(candidate, "keyword")
        + BASE_WEIGHTS["evidence"] * _score(candidate, "evidence")
        + BASE_WEIGHTS["graph"] * _score(candidate, "graph")
    )


def _presenter_rankings(
    candidates: list[dict],
) -> list[dict[str, list[str]]]:
    """Return one ``{preset_label: [candidate_id ordered by rank]}`` per preset.
    Each candidate keeps its existing transparent adjustment (final - base), so
    only the semantic/keyword balance actually changes."""
    rankings: dict[str, list[str]] = {}
    for preset in WEIGHT_PRESETS:
        label = f"sem{int(preset['semantic'] * 100)}/kw{int(preset['keyword'] * 100)}"
        adjusted = []
        for cand in candidates:
            penalty = _score(cand, "final_score") - _recomputed_base(cand)
            adjusted.append((_blended_for_preset(cand, preset) + penalty, cand))
        ordered = sorted(adjusted, key=lambda pair: (-pair[0], str(pair[1].get("candidate_id"))))
        rankings[label] = [str(c.get("candidate_id")) for _, c in ordered]
    return rankings


def _requirements_by_id(jd: dict) -> dict[str, dict[str, Any]]:
    return {
        r.get("id"): r
        for r in (jd.get("requirements") or [])
        if isinstance(r, dict)
    }


def _missing_critical_weighted(candidate: dict, reqs: dict[str, dict]) -> list[str]:
    """Display names of high-weight *required* requirements that are not matched."""
    missing = []
    for entry in candidate.get("requirement_matches") or []:
        if not isinstance(entry, dict) or entry.get("matched"):
            continue
        req = reqs.get(entry.get("requirement_id")) or {}
        if req.get("importance") == "required" and float(req.get("weight") or 3.0) >= CRITICAL_WEIGHT:
            missing.append(str(req.get("display_name") or entry.get("requirement_name") or entry.get("requirement_id")))
    return missing


def _skills_only_share(candidate: dict) -> tuple[int, int]:
    """(listed_only_matches, total_matches) among keyword-matched requirements."""
    total = 0
    listed_only = 0
    for entry in candidate.get("requirement_matches") or []:
        if not isinstance(entry, dict) or not entry.get("keyword_match"):
            continue
        total += 1
        etype = str(entry.get("evidence_type") or "").lower()
        strength = float(entry.get("evidence_strength") or 0.0)
        if etype in {"skills", "skills_section", "skills-list"} or strength <= SKILLS_ONLY_MAX_STRENGTH:
            listed_only += 1
    return listed_only, total


def _evaluate_candidate(
    candidate: dict,
    ranked: list[dict],
    reqs: dict[str, dict],
    preset_ranks: list[dict[str, list[str]]],
    base_order: list[str],
    base_top3: set[str],
) -> dict[str, Any]:
    """Run all checks for one candidate; returns {"flags", "severity", "sensitivity"}."""
    flags: list[tuple[str, str]] = []  # (message, "major"|"minor")
    cid = str(candidate.get("candidate_id"))
    rank = int(candidate.get("rank") or 0)

    semantic = _score(candidate, "semantic")
    keyword = _score(candidate, "keyword")
    evidence = _score(candidate, "evidence")

    # R1 — semantic vs keyword disagreement
    gap = abs(semantic - keyword)
    if gap >= GAP_MINOR:
        if semantic > keyword:
            message = (
                f"High semantic relevance ({semantic:.1f}) but relatively low explicit "
                f"requirement coverage ({keyword:.1f})."
            )
        else:
            message = (
                f"Strong explicit keyword coverage ({keyword:.1f}) but relatively weak "
                f"semantic relevance ({semantic:.1f})."
            )
        flags.append((message, "major" if gap >= GAP_MAJOR else "minor"))

    # R2 — high rank with weak evidence
    if 0 < rank <= TOP_RANK_CUTOFF and evidence < EVIDENCE_WEAK_THRESHOLD:
        flags.append(
            (
                f"Ranks #{rank}, but the match is weakly demonstrated "
                f"(evidence authenticity {evidence:.1f} < {EVIDENCE_WEAK_THRESHOLD:.0f}).",
                "major",
            )
        )

    # R3 — missing critical required requirement at high rank
    if 0 < rank <= TOP_RANK_CUTOFF:
        missing = _missing_critical_weighted(candidate, reqs)
        if missing:
            flags.append(
                (
                    "High rank may be masking missing explicit requirement(s): "
                    + ", ".join(missing)
                    + ".",
                    "major",
                )
            )

    # R4 — close ranking margin against immediate neighbors
    if rank > 0:
        own = _score(candidate, "final_score")
        neighbors = []
        if rank >= 2:
            neighbors.append(rank - 1)
        if rank < len(ranked):
            neighbors.append(rank + 1)
        for other_rank in neighbors:
            other = ranked[other_rank - 1]
            diff = abs(own - _score(other, "final_score"))
            if diff < CLOSE_MARGIN_POINTS:
                flags.append(
                    (
                        f"Effectively a close decision with #{other_rank} "
                        f"({other.get('name', other.get('candidate_id'))}): "
                        f"only {diff:.1f} point(s) apart.",
                        "minor",
                    )
                )

    # R5 — weight sensitivity
    rank_positions = [base_order.index(cid) + 1 if cid in base_order else None]
    for ranks in preset_ranks:
        if cid in ranks:
            rank_positions.append(ranks.index(cid) + 1)
    positions = [p for p in rank_positions if p is not None]
    rank_min, rank_max = (min(positions), max(positions)) if positions else (rank, rank)
    top3_shift = any(
        set(ranks[:TOP_RANK_CUTOFF]) != base_top3 for ranks in preset_ranks
    )
    sensitivity = {"rank_min": rank_min, "rank_max": rank_max, TOP3_STABILITY_KEY: not top3_shift}
    move = rank_max - rank_min
    if move >= RANK_MOVE_MAJOR or (top3_shift and rank <= TOP_RANK_CUTOFF):
        flags.append(
            (
                f"Position is weight-sensitive: moves between #{rank_min} and #{rank_max} "
                "under reasonable semantic/keyword weighting presets.",
                "major",
            )
        )
    elif move >= 1:
        flags.append(
            (
                f"Minor weight sensitivity: position shifts between #{rank_min} and "
                f"#{rank_max} across scoring presets.",
                "minor",
            )
        )

    # R6 — parse quality
    parse_score = float(((candidate.get("parse_quality") or {}).get("score")) or 100.0)
    if parse_score < PARSE_QUALITY_LOW:
        flags.append(
            (
                f"Ranking confidence reduced because resume extraction quality is low "
                f"({parse_score:.0f}/100).",
                "minor",
            )
        )

    # R7 — skills-list concentration
    listed_only, total_matches = _skills_only_share(candidate)
    if total_matches >= SKILLS_ONLY_MIN_MATCHES and listed_only / total_matches >= SKILLS_ONLY_SHARE_FLAG:
        flags.append(
            (
                f"Keyword coverage is high, but {listed_only}/{total_matches} matched "
                "requirements appear only as skills-list mentions with limited "
                "demonstrated project/work evidence.",
                "minor",
            )
        )

    return {"flags": flags, "sensitivity": sensitivity}


def _confidence_for(major: int, minor: int) -> str:
    """Deterministic confidence rule (TEAMMATE_2 #10)."""
    if major >= 2 or (major >= 1 and minor >= 2) or minor >= 4:
        return "low"
    if major >= 1 or minor >= 1:
        return "medium"
    return "high"


def _summary_for(confidence: str, major: int, minor: int) -> str:
    if confidence == "high":
        return (
            "No significant concerns detected: scores are internally consistent, "
            "the position is stable under weighting presets, and evidence quality "
            "supports the rank."
        )
    parts = []
    if major:
        parts.append(f"{major} major concern(s)")
    if minor:
        parts.append(f"{minor} warning(s)")
    joined = " and ".join(parts)
    if confidence == "low":
        return f"{joined} detected. This ranking position is unreliable; human review is recommended."
    return f"{joined} detected. Review the flags before treating this position as final."


def critique_ranking(jd: dict, ranked_candidates: list[dict]) -> list[dict]:
    """Enrich every candidate's ``critique`` block in place and return the list.

    Expects ``ranked_candidates`` sorted by rank ascending (rank 1 first), as
    produced by Teammate 1's ranker. Missing schema fields degrade gracefully
    (parallel-development safety, TEAMMATE_2 #18).
    """
    ranked = list(ranked_candidates)
    reqs = _requirements_by_id(jd)

    base_order = [str(c.get("candidate_id")) for c in ranked]
    base_top3 = set(base_order[:TOP_RANK_CUTOFF])
    preset_rankings_map = _presenter_rankings(ranked)
    preset_lists = list(preset_rankings_map.values())

    for candidate in ranked:
        evaluation = _evaluate_candidate(
            candidate, ranked, reqs, preset_lists, base_order, base_top3
        )
        flag_pairs = evaluation["flags"]
        major = sum(1 for _, severity in flag_pairs if severity == "major")
        minor = sum(1 for _, severity in flag_pairs if severity == "minor")
        confidence = _confidence_for(major, minor)

        candidate["critique"] = {
            "confidence": confidence,
            "flags": [message for message, _ in flag_pairs],
            "summary": _summary_for(confidence, major, minor),
            "human_review_recommended": confidence == "low" or major >= 1,
        }

    return ranked
