"""Skill graph matcher — Differentiator D4 (Teammate 2, Trust & Innovation layer).

Contract: MASTER_CONTEXT.md #14, #20 and TEAMMATE_2_TRUST_AND_INNOVATION.md #6/#7.

    apply_skill_graph(jd: dict, candidate: dict, graph) -> dict

For every *unmet or weak* requirement the matcher looks at the candidate's
``detected_skills``, searches graph paths of length 1-2, computes a decayed
relationship score (product of edge weights * 100) and preserves the path so
the UI can explain *why* related experience counts as partial evidence.

Guardrails (hard requirements from the docs):
  * A graph relation is SUPPORTING evidence, never proof. The matcher never
    touches ``matched`` / ``keyword_match`` / ``evidence_strength`` and never
    lets an indirect path exceed ``INDIRECT_MAX_SCORE``.
  * Direct keyword matches are not relabeled as graph matches.
  * Paths are limited to ``MAX_HOPS`` to prevent nonsense.
  * Only ``required`` + ``preferred`` requirements are considered (transparent
    precedent: MASTER_CONTEXT #10 keyword aggregation).

Deterministic, offline, stdlib-only, JSON-serializable output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants (tunable, but shared behavior must stay explainable)
# ---------------------------------------------------------------------------

DEFAULT_GRAPH_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "skill_graph.json"
)

MAX_HOPS = 2                 # path length limit (1-hop and 2-hop paths only)
INDIRECT_MAX_SCORE = 85.0    # an indirect relation never fully satisfies a requirement
DIRECT_MATCH_SCORE = 100.0   # used only inside the candidate-level aggregate
CONSIDERED_IMPORTANCES = frozenset({"required", "preferred"})
DEFAULT_IMPORTANCE_WEIGHT = {"required": 3.0, "preferred": 2.0, "context": 1.0}

_META_KEYS = frozenset({"_meta"})


# ---------------------------------------------------------------------------
# Graph loading
# ---------------------------------------------------------------------------

def load_skill_graph(path: Optional[str] = None) -> dict[str, list[dict[str, Any]]]:
    """Load ``config/skill_graph.json`` and symmetrize it into an undirected
    adjacency map: ``{node: [{target, relation, weight}, ...]}``.

    Edges are authored once in the JSON; every edge is added in both directions
    here so path search is direction-agnostic. The private ``_meta`` key is
    ignored.
    """
    raw = json.loads(Path(path or DEFAULT_GRAPH_PATH).read_text(encoding="utf-8"))
    graph: dict[str, list[dict[str, Any]]] = {}
    for source, edges in raw.items():
        if source in _META_KEYS or not isinstance(edges, list):
            continue
        node = graph.setdefault(source.strip().lower(), [])
        for edge in edges:
            target = str(edge["target"]).strip().lower()
            relation = str(edge["relation"])
            weight = float(edge["weight"])
            node.append({"target": target, "relation": relation, "weight": weight})
            graph.setdefault(target, []).append(
                {"target": source.strip().lower(), "relation": relation, "weight": weight}
            )
    return graph


# ---------------------------------------------------------------------------
# Path search
# ---------------------------------------------------------------------------

def best_graph_path(
    graph: dict[str, list[dict[str, Any]]],
    start: str,
    target: str,
) -> Optional[tuple[float, list[str]]]:
    """Return ``(score, path)`` of the strongest decayed path between two
    distinct nodes within ``MAX_HOPS``, or ``None``.

    Decay rule (TEAMMATE_2 #6):
        1-hop  = edge_weight * 100
        2-hop  = product(edge_weights) * 100
    Result is capped at ``INDIRECT_MAX_SCORE``.
    """
    if not start or not target or start == target:
        return None

    best: Optional[tuple[float, list[str]]] = None

    def consider(score: float, path: list[str]) -> None:
        nonlocal best
        score = min(score, INDIRECT_MAX_SCORE)
        if best is None or score > best[0]:
            best = (score, path)

    for edge in graph.get(start, []):
        hop1 = edge["target"]
        weight1 = float(edge["weight"])
        if hop1 == target:
            consider(weight1 * 100.0, [start, target])
            continue
        if MAX_HOPS < 2:
            continue
        for edge2 in graph.get(hop1, []):
            hop2 = edge2["target"]
            if hop2 in (start, hop1):
                continue  # no backtracking / no self loops
            if hop2 == target:
                consider(weight1 * float(edge2["weight"]) * 100.0, [start, hop1, target])

    return best


def find_related_evidence(
    graph: dict[str, list[dict[str, Any]]],
    requirement_name: str,
    detected_skills: list[str],
) -> Optional[tuple[float, list[str]]]:
    """Best indirect graph support for ``requirement_name`` given the
    candidate's skills. Exact-name overlap is deliberately NOT a graph hit —
    that is keyword matching's job — so those starts are skipped."""
    req = (requirement_name or "").strip().lower()
    best: Optional[tuple[float, list[str]]] = None
    for skill in sorted({(s or "").strip().lower() for s in detected_skills if s}):
        if skill == req:
            continue
        found = best_graph_path(graph, skill, req)
        if found and (best is None or found[0] > best[0]):
            best = found
    return best


# ---------------------------------------------------------------------------
# Public integration function (MASTER_CONTEXT #20)
# ---------------------------------------------------------------------------

def apply_skill_graph(
    jd: dict,
    candidate: dict,
    graph: Optional[dict[str, list[dict[str, Any]]]] = None,
) -> dict:
    """Enrich ``candidate`` in place with graph fields and return it.

    Per requirement match entry (schema keys from MASTER_CONTEXT #7.2):
      * ``graph_match``  — True only when an *indirect* relation was found.
      * ``graph_path``   — e.g. ``["express", "rest api", "api development"]``.
      * ``graph_score``  — 0-100, capped at ``INDIRECT_MAX_SCORE``.

    Candidate level:
      * ``candidate["scores"]["graph"]`` = importance-weighted average of
        effective coverage, where a directly keyword-matched requirement
        counts as ``DIRECT_MATCH_SCORE`` and an unmet requirement uses its
        indirect graph score (0 if no relation exists). This keeps the graph
        component small (5% of base score per MASTER_CONTEXT #8) without
        punishing candidates whose requirements are directly satisfied.

    The scorer/ranker (Teammate 1's, owned elsewhere) should be rerun after
    this enrichment — see TEAMMATE_2 #18.
    """
    if graph is None:
        graph = load_skill_graph()

    requirements = [
        r for r in (jd.get("requirements") or [])
        if isinstance(r, dict) and r.get("importance") in CONSIDERED_IMPORTANCES
    ]
    detected = [str(s) for s in (candidate.get("detected_skills") or [])]
    matches_by_id = {
        m.get("requirement_id"): m
        for m in (candidate.get("requirement_matches") or [])
        if isinstance(m, dict)
    }

    total_weight = 0.0
    weighted_sum = 0.0

    for req in requirements:
        rid = req.get("id")
        name = str(req.get("name") or "").strip().lower()
        weight = float(req.get("weight") or DEFAULT_IMPORTANCE_WEIGHT.get(req.get("importance"), 1.0))
        total_weight += weight

        entry = matches_by_id.get(rid)
        direct = bool(entry.get("keyword_match")) if entry is not None else False

        graph_match = False
        graph_path: list[str] = []
        graph_score = 0.0

        if not direct:
            options = [find_related_evidence(graph, alternative, detected) for alternative in req.get("alternatives", [name])]
            found = max((option for option in options if option is not None), key=lambda option: option[0], default=None)
            if found is not None:
                graph_score, graph_path = found
                graph_match = True

        if entry is not None:
            # Write ONLY our own graph_* keys — never touch matched/keyword/evidence.
            entry["graph_match"] = graph_match
            entry["graph_path"] = graph_path
            entry["graph_score"] = round(graph_score, 4)

        effective = DIRECT_MATCH_SCORE if direct else graph_score
        weighted_sum += weight * effective

    graph_component = weighted_sum / total_weight if total_weight > 0 else 0.0

    scores = candidate.setdefault("scores", {})
    scores["graph"] = graph_component

    return candidate
