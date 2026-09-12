"""Trust-layer orchestration — Teammate 2's integration glue (src/trust_pipeline.py).

This is the ONLY module that is allowed to import across team boundaries:
Teammate 1's core pipeline + Teammate 2's trust/innovation modules, wired in
the exact order required by MASTER_CONTEXT.md #22 and TEAMMATE_2 #18/#20:

    parsed candidates
      -> keyword / semantic / evidence matchers      (Teammate 1)
      -> requirement_matches merge, pass 1           (Teammate 1 scorer, graph=0)
      -> apply_skill_graph                            (Teammate 2  -> D4)
      -> rescore with real graph aggregate            (Teammate 1 scorer, rerun)
      -> rank_candidates                              (Teammate 1)
      -> critique_ranking                             (Teammate 2  -> D1)
      -> flag_overqualification                       (Teammate 2  -> D6)
      -> generate_interview_probes                    (Teammate 2  -> D7)
      -> generate_counterfactual (with real-scorer
         seam via make_scorer_adapter)                (Teammate 2  -> D3)
      -> find_best_team                               (Teammate 2  -> D5)

Teammate 3's UI can call one function:

    ranked, team_result = run_trust_layer(jd, candidates, model=...)

or the convenience wrapper run_full_pipeline(jd_text, resume_paths, ...) which
also builds the JD via Teammate 1's extractor.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

# --- Teammate 1 core ---------------------------------------------------------
from .evidence import score_evidence
from .keyword_matcher import keyword_match
from .ranker import rank_candidates
from .requirement_extractor import detect_role_level, extract_requirements
from .scorer import calculate_critical_missing_penalty, score_candidate
from .semantic_matcher import semantic_match

# --- Teammate 2 trust layer --------------------------------------------------
from .critique import critique_ranking
from .counterfactual import generate_counterfactual
from .overqualification import flag_overqualification
from .probes import generate_interview_probes
from .skill_graph import apply_skill_graph, load_skill_graph
from .team_mode import find_best_team

__all__ = [
    "build_jd",
    "make_scorer_adapter",
    "score_with_graph",
    "run_trust_layer",
    "run_full_pipeline",
]

# Documented blend (MASTER_CONTEXT #8) — kept local so this module fails
# loudly if T1's scorer ever diverges from the shared contract.
_BLEND = {"semantic": 0.45, "keyword": 0.35, "evidence": 0.15, "graph": 0.05}


# ---------------------------------------------------------------------------
# JD helper
# ---------------------------------------------------------------------------

def build_jd(jd_text: str, title: str = "") -> Dict[str, Any]:
    """Create a schema-compliant JD dict from raw JD text using Teammate 1's
    deterministic extractor (no PDF required)."""
    requirements = extract_requirements(jd_text)
    return {
        "title": title or (requirements[0]["name"].title() if requirements else ""),
        "raw_text": jd_text,
        "clean_text": jd_text,
        "requirements": requirements,
        "role_level": detect_role_level(jd_text),
        "bias_flags": [],
    }


# ---------------------------------------------------------------------------
# Graph-integrated scoring (TEAMMATE_2 #18: enrich, then rerun scorer/ranker)
# ---------------------------------------------------------------------------

def _graph_matches_list(candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "requirement_id": m.get("requirement_id"),
            "graph_match": bool(m.get("graph_match")),
            "graph_path": list(m.get("graph_path") or []),
            "graph_score": float(m.get("graph_score") or 0.0),
        }
        for m in (candidate.get("requirement_matches") or [])
        if isinstance(m, dict)
    ]


def score_with_graph(
    jd: Dict[str, Any],
    candidate: Dict[str, Any],
    keyword_result: Dict[str, Any],
    semantic_result: Dict[str, Any],
    evidence_result: Dict[str, Any],
    graph: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Two-pass scoring: pass 1 builds merged requirement_matches with
    graph=0, then apply_skill_graph enriches them, then pass 2 reruns Teammate
    1's scorer so the 5% graph component is genuinely inside base_score."""
    score_candidate(jd, candidate, keyword_result, semantic_result,
                    evidence_result, graph_score=0.0)
    apply_skill_graph(jd, candidate, graph)
    graph_component = float((candidate.get("scores") or {}).get("graph", 0.0))
    score_candidate(jd, candidate, keyword_result, semantic_result,
                    evidence_result, graph_score=graph_component,
                    graph_matches=_graph_matches_list(candidate))
    return candidate


# ---------------------------------------------------------------------------
# Counterfactual seam: reuse the REAL scoring formula + penalty function
# ---------------------------------------------------------------------------

def make_scorer_adapter(jd: Dict[str, Any]) -> Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]:
    """Return a ``scorer(jd, candidate) -> candidate`` callable for
    ``generate_counterfactual(scorer=...)``.

    It recomputes Teammate 1's aggregates (keyword coverage, evidence average,
    graph coverage) from the candidate's CURRENT requirement_matches — so
    simulated improvements change the score exactly as the real pipeline would
    — then reuses Teammate 1's weight blend, penalty cap
    (``calculate_critical_missing_penalty``) and rounding. Semantic is held at
    the stored candidate value: re-embedding simulated text offline would
    fabricate precision we cannot defend (conservative by design).
    """
    requirements = jd.get("requirements") or []
    total_w = sum(float(r.get("weight", 1.0)) for r in requirements)

    def scorer(_jd: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        matches = {
            str(m.get("requirement_id")): m
            for m in (candidate.get("requirement_matches") or [])
            if isinstance(m, dict)
        }
        kw_sum = 0.0
        ev_sum = 0.0
        graph_sum = 0.0
        missing_required: List[str] = []
        for req in requirements:
            w = float(req.get("weight", 1.0))
            m = matches.get(str(req.get("id"))) or {}
            kw = bool(m.get("keyword_match"))
            if kw:
                kw_sum += w
            else:
                if req.get("importance") == "required":
                    missing_required.append(str(req.get("name", "")))
            try:
                ev_sum += w * float(m.get("evidence_strength") or 0.0)
            except (TypeError, ValueError):
                pass
            graph_sum += w * (100.0 if kw else float(m.get("graph_score") or 0.0))

        if total_w > 0:
            kw_score = 100.0 * kw_sum / total_w
            ev_score = 100.0 * ev_sum / total_w
            graph_score = graph_sum / total_w
        else:
            kw_score = ev_score = graph_score = 0.0

        stored = candidate.get("scores") or {}
        try:
            sem_score = float(stored.get("semantic", 0.0))
        except (TypeError, ValueError):
            sem_score = 0.0

        base = (
            _BLEND["semantic"] * sem_score
            + _BLEND["keyword"] * round(kw_score, 2)
            + _BLEND["evidence"] * round(ev_score, 2)
            + _BLEND["graph"] * round(graph_score, 2)
        )
        penalty = calculate_critical_missing_penalty(missing_required)
        final = max(0.0, base - penalty)

        candidate["scores"] = {
            "semantic": round(sem_score, 2),
            "keyword": round(kw_score, 2),
            "evidence": round(ev_score, 2),
            "graph": round(graph_score, 2),
            "base_score": round(base, 2),
            "final_score": round(final, 2),
        }
        return candidate

    return scorer


# ---------------------------------------------------------------------------
# The one-call trust layer
# ---------------------------------------------------------------------------

def run_trust_layer(
    jd: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    model: Optional[Any] = None,
    graph: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    team_size: int = 3,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Full Teammate 1 + Teammate 2 chain (semantic model injected or lazy-
    loaded). Returns ``(ranked_candidates, team_result)``. Every candidate is
    enriched in place with critique/counterfactual/overqualification/
    interview_probes plus graph_* fields — exactly the shapes promised in
    TEAMMATE_2 #24 and renderable by Teammate 3 without reading internals."""
    graph = graph if graph is not None else load_skill_graph()
    active_model = model
    scorer_adapter = make_scorer_adapter(jd)

    for candidate in candidates:
        if not candidate.get("detected_skills"):
            from .skill_extractor import extract_skills_from_text  # local import avoids cycles
            candidate["detected_skills"] = extract_skills_from_text(
                candidate.get("clean_text") or ""
            )
        kw = keyword_match(jd, candidate)
        if active_model is None:
            from .semantic_matcher import get_semantic_model
            active_model = get_semantic_model()
        sem = semantic_match(jd, candidate, model=active_model)
        evi = score_evidence(jd, candidate)
        score_with_graph(jd, candidate, kw, sem, evi, graph)

    ranked = rank_candidates(candidates)
    critique_ranking(jd, ranked)

    for candidate in ranked:
        flag_overqualification(jd, candidate)
        generate_interview_probes(jd, candidate)
        generate_counterfactual(candidate, ranked, jd, scorer=scorer_adapter)

    team_result = find_best_team(jd, ranked, team_size=team_size)
    return ranked, team_result


def run_full_pipeline(
    jd_text: str,
    resume_paths: List[str],
    model: Optional[Any] = None,
    title: str = "",
    team_size: int = 3,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Convenience wrapper: JD text + resume PDF paths -> enriched, ranked
    candidates + team result (uses Teammate 1's PDF parser)."""
    from .pipeline import parse_candidate_from_pdf  # Teammate 1-owned parser

    jd = build_jd(jd_text, title=title)
    candidates = [parse_candidate_from_pdf(p) for p in resume_paths]
    return run_trust_layer(jd, candidates, model=model, team_size=team_size)
