"""Counterfactual / coaching ranking — Differentiator D3 (Teammate 2).

Contract: MASTER_CONTEXT.md #5.3-D3, #13, #20 and
TEAMMATE_2_TRUST_AND_INNOVATION.md #11-#13.

    generate_counterfactual(candidate, ranked_candidates, jd) -> dict

Answers: "What would need to change for this candidate to reach the Top 3?"

How the estimate works (and why it is honest):
  The base score is a documented LINEAR blend
      base = 0.45*semantic + 0.35*keyword + 0.15*evidence + 0.05*graph.
  A simulated improvement changes only the keyword/evidence/graph aggregate of
  ONE requirement, so per-requirement gains are INDEPENDENT and additive:
      delta_base = 0.35*d_keyword + 0.15*d_evidence + 0.05*d_graph
  (d_semantic is held at 0 — conservative, since we cannot re-embed resumed
  text offline). Greedy "take biggest gains first until the threshold" is
  therefore exactly the minimal-change set.

  Deltas are applied to the candidate's already-computed base_score and the
  critical-missing penalty is held constant, so every projected gain is a
  CONSERVATIVE lower bound (fixing a missing required skill could also shrink
  the real penalty in Teammate 1's scorer).

Integration seam (TEAMMATE_2 #12: "reuse the core scorer"):
  Pass ``scorer=score_candidate`` (Teammate 1's function) and every projection
  is computed by deep-copying the candidate, applying simulated changes and
  calling the REAL scorer instead of the linear model. The MASTER_CONTEXT #20
  3-argument contract is preserved; ``scorer`` is an optional keyword — a
  one-line swap at integration time.

Guardrails: hypotheticals are always labeled as simulated; the result carries
a disclaimer; the improvement set is capped; no hiring guarantees.
"""

from __future__ import annotations

import copy
from typing import Callable, Optional

# --- Documented blend weights (MASTER_CONTEXT #8) ----------------------------
WEIGHTS = {"semantic": 0.45, "keyword": 0.35, "evidence": 0.15, "graph": 0.05}

CONSIDERED_IMPORTANCES = {"required", "preferred"}
DEFAULT_IMPORTANCE_WEIGHT = {"required": 3.0, "preferred": 2.0, "context": 1.0}

# Evidence levels (MASTER_CONTEXT #5.3-D2 table).
STRONG_EVIDENCE = 1.0
DEMONSTRATED_FLOOR = 0.75   # >= this already counts as project/work context

TARGET_EPSILON = 0.1        # "rank-3 score + a hair" (TEAMMATE_2 #11)
TOP_RANK = 3
MAX_IMPROVEMENTS = 3        # keep coaching advice realistic ("smallest set")

CHANGE_LABELS = {
    "add_missing": "Add strong demonstrated project/work evidence for {skill}.",
    "upgrade_weak": "Turn the current mention of {skill} into clearly "
                    "demonstrated project/work evidence (context + your role).",
    "promote_graph": "Convert related-skill evidence into direct, demonstrated "
                     "experience with {skill}.",
}

DISCLAIMER = (
    "Model simulation only — not a hiring guarantee. Gains assume other "
    "candidates are unchanged, hold the critical-missing penalty constant, "
    "and treat simulated evidence as hypothetical, never as fact."
)

SCORER_STANDIN = "documented-linear-model"


def _weight(req: dict) -> float:
    try:
        return float(req.get("weight") or DEFAULT_IMPORTANCE_WEIGHT.get(req.get("importance"), 1.0))
    except (TypeError, ValueError):
        return 1.0


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _considered_requirements(jd: dict) -> list[dict]:
    return [
        r for r in (jd.get("requirements") or [])
        if isinstance(r, dict) and r.get("importance") in CONSIDERED_IMPORTANCES
    ]


def _matches_by_id(candidate: dict) -> dict[str, dict]:
    return {
        str(m.get("requirement_id")): m
        for m in (candidate.get("requirement_matches") or [])
        if isinstance(m, dict)
    }


def _effective_graph(match: Optional[dict]) -> float:
    """Per-requirement graph coverage: direct keyword match counts as 100,
    otherwise the stored graph_score, else 0. Mirrors src/skill_graph.py."""
    if match is None:
        return 0.0
    if match.get("keyword_match"):
        return 100.0
    return _as_float(match.get("graph_score"), 0.0)


def _model_base_component(jd: dict, candidate: dict) -> float:
    """Model-computed share of the base score contributed by the three
    requirement-aggregated components (keyword + evidence + graph). Semantic is
    intentionally excluded: it never changes under these simulations, so it
    cancels out of every delta."""
    reqs = _considered_requirements(jd)
    total_w = sum(_weight(r) for r in reqs)
    if total_w <= 0:
        return 0.0
    matches = _matches_by_id(candidate)
    keyword = 0.0
    evidence = 0.0
    graph = 0.0
    for r in reqs:
        w = _weight(r) / total_w
        m = matches.get(str(r.get("id")))
        if m and m.get("keyword_match"):
            keyword += 100.0 * w
        evidence += 100.0 * w * _as_float((m or {}).get("evidence_strength"), 0.0)
        graph += w * _effective_graph(m)
    return (
        WEIGHTS["keyword"] * keyword
        + WEIGHTS["evidence"] * evidence
        + WEIGHTS["graph"] * graph
    )


# ---------------------------------------------------------------------------
# Simulation mechanics
# ---------------------------------------------------------------------------

def _apply_change(candidate: dict, change: dict) -> dict:
    """Deep-copy the candidate and write one simulated improvement into its
    requirement_matches. Simulated evidence text is explicitly labeled
    ``[simulated]`` so it can never be mistaken for resume fact."""
    sim = copy.deepcopy(candidate)
    rid = str(change["requirement_id"])
    matches = sim.setdefault("requirement_matches", [])
    target = next(
        (m for m in matches if isinstance(m, dict) and str(m.get("requirement_id")) == rid),
        None,
    )
    if target is None:
        target = {"requirement_id": rid, "requirement_name": change["requirement_name"]}
        matches.append(target)
    target.update({
        "keyword_match": True,
        "keyword_score": 100.0,
        "matched": True,
        "evidence_strength": STRONG_EVIDENCE,
        "evidence_type": "project",
        "evidence_text": "[simulated] demonstrated project/work evidence",
    })
    return sim


def _base_of(jd: dict, candidate: dict, scorer: Optional[Callable]) -> float:
    """Base score under the chosen backend (real scorer if injected)."""
    if scorer is not None:
        rescored = scorer(jd, candidate) or {}
        if isinstance(rescored.get("scores"), dict):
            return _as_float(rescored["scores"].get("base_score"))
        return _as_float(rescored.get("base_score"))
    return _model_base_component(jd, candidate)


def _delta_base(candidate: dict, changes: list[dict], jd: dict,
                scorer: Optional[Callable]) -> float:
    """Base-score gain of applying a set of changes (independent + additive)."""
    working = candidate
    for change in changes:
        working = _apply_change(working, change)
    return _base_of(jd, working, scorer) - _base_of(jd, candidate, scorer)


def _enumerate_changes(jd: dict, candidate: dict) -> list[dict]:
    """All realistic single-requirement improvements, one per requirement."""
    matches = _matches_by_id(candidate)
    changes: list[dict] = []
    for req in _considered_requirements(jd):
        rid = str(req.get("id"))
        skill = str(req.get("display_name") or req.get("name") or rid)
        m = matches.get(rid)

        if m is None:
            kind = "add_missing"
        elif not m.get("keyword_match"):
            kind = "promote_graph" if m.get("graph_match") else "add_missing"
        elif _as_float(m.get("evidence_strength"), 0.0) < DEMONSTRATED_FLOOR:
            kind = "upgrade_weak"
        else:
            continue  # already strong + demonstrated: nothing to simulate

        changes.append({
            "requirement_id": rid,
            "requirement_name": skill,
            "kind": kind,
            "importance": req.get("importance"),
            "weight": _weight(req),
            "change": CHANGE_LABELS[kind].format(skill=skill),
        })
    return changes


# ---------------------------------------------------------------------------
# Public function (MASTER_CONTEXT #20 contract, scorer seam optional)
# ---------------------------------------------------------------------------

def generate_counterfactual(
    candidate: dict,
    ranked_candidates: list[dict],
    jd: dict,
    scorer: Optional[Callable] = None,
) -> dict:
    """Populate ``candidate["counterfactual"]`` and return it.

    Output keys follow MASTER_CONTEXT #7.2 (``target_rank``, ``target_score``,
    ``suggested_improvements``, ``projected_score``) plus additive,
    UI-friendly fields: ``current_score``, ``score_gap_to_target``,
    ``reached_target``, ``already_in_top_3``, ``message``, ``scorer_backend``
    and ``disclaimer``. Everything is JSON-serializable (TEAMMATE_2 #19).
    """
    scores = candidate.get("scores") or {}
    current_base = _as_float(scores.get("base_score"), 0.0)
    current_final = _as_float(scores.get("final_score"), 0.0)
    penalty = current_base - current_final  # transparent adjustment, held constant
    rank = int(candidate.get("rank") or 0)
    ranked = [c for c in ranked_candidates if isinstance(c, dict)]

    def finish(result: dict) -> dict:
        result["scorer_backend"] = SCORER_STANDIN if scorer is None else "injected-scorer"
        result["disclaimer"] = DISCLAIMER
        candidate["counterfactual"] = result
        return result

    # --- Target selection (TEAMMATE_2 #11) ----------------------------------
    if 0 < rank <= TOP_RANK and rank == 1:
        return finish({
            "target_rank": 1,
            "target_score": round(current_final, 4),
            "suggested_improvements": [],
            "projected_score": round(current_final, 4),
            "current_score": round(current_final, 4),
            "score_gap_to_target": 0.0,
            "reached_target": True,
            "already_in_top_3": True,
            "message": "Candidate already ranks #1 — no Top-3 target applies.",
        })
    target_rank = (rank - 1) if 0 < rank <= TOP_RANK else TOP_RANK
    already_top3 = 0 < rank <= TOP_RANK

    target_index = target_rank - 1
    if target_index >= len(ranked) or target_index < 0:
        return finish({
            "target_rank": 0,
            "target_score": 0.0,
            "suggested_improvements": [],
            "projected_score": round(current_final, 4),
            "current_score": round(current_final, 4),
            "score_gap_to_target": 0.0,
            "reached_target": False,
            "already_in_top_3": already_top3,
            "message": "Not enough ranked candidates to define a target.",
        })

    target_score = _as_float(
        (ranked[target_index].get("scores") or {}).get("final_score"), 0.0
    )
    needed = target_score + TARGET_EPSILON

    # --- Evaluate each improvement individually, sort by gain ---------------
    evaluated: list[tuple[float, dict]] = []
    for change in _enumerate_changes(jd, candidate):
        evaluated.append((_delta_base(candidate, [change], jd, scorer), change))
    evaluated.sort(
        key=lambda pair: (-pair[0], -pair[1]["weight"], pair[1]["requirement_id"])
    )

    # --- Greedy minimal set (exact here: gains are independent) -------------
    applied: list[dict] = []
    applied_gains: list[float] = []
    projected_final = current_final
    for gain, change in evaluated:
        if projected_final >= needed or len(applied) >= MAX_IMPROVEMENTS:
            break
        if gain <= 1e-6:
            continue
        applied.append(change)
        applied_gains.append(gain)
        projected_final = current_base + sum(applied_gains) - penalty

    reached = projected_final >= needed
    if not applied:
        message = (
            "Already at or above the target score; no improvement needed."
            if current_final >= needed
            else "No remaining requirement improvements could move this candidate "
                 "under the current scoring model."
        )
    elif reached:
        verb = ("reach rank #" + str(target_rank)) if not already_top3 else "reach rank #" + str(target_rank)
        message = (
            f"Within this ranking model, {len(applied)} simulated improvement"
            f"{'s' if len(applied) > 1 else ''} would {verb}."
        )
    else:
        message = (
            f"Even {len(applied)} improvement(s) (+{projected_final - current_final:.1f} "
            f"simulated points) would not reach rank #{target_rank}; the gap is too "
            "large for realistic single-cycle coaching."
        )

    return finish({
        "target_rank": target_rank,
        "target_score": round(target_score, 4),
        "suggested_improvements": [
            {
                "requirement": c["requirement_name"],
                "change": c["change"],
                "kind": c["kind"],
                "importance": c["importance"],
                "estimated_gain": round(g, 4),
            }
            for c, g in zip(applied, applied_gains)
        ],
        "projected_score": round(projected_final, 4),
        "current_score": round(current_final, 4),
        "score_gap_to_target": round(max(0.0, needed - current_final), 4),
        "reached_target": bool(reached),
        "already_in_top_3": already_top3,
        "message": message,
    })
