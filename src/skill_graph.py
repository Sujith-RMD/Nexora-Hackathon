"""Small deterministic related-skill graph enrichment layer."""

from __future__ import annotations

import json
from pathlib import Path
from collections import deque

_DEFAULT_GRAPH = Path(__file__).resolve().parent.parent / "config" / "skill_graph.json"


def load_skill_graph(path=None):
    target = Path(path) if path else _DEFAULT_GRAPH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _paths(graph, start, target, max_hops=2):
    if start == target:
        return [start]
    queue = deque([(start, [start])])
    seen = {start}
    while queue:
        node, path = queue.popleft()
        if len(path) - 1 >= max_hops:
            continue
        for edge in graph.get(node, []) or []:
            if not isinstance(edge, dict):
                continue
            nxt = str(edge.get("target", "")).casefold()
            if not nxt or nxt in seen:
                continue
            new_path = path + [nxt]
            if nxt == target:
                return new_path
            seen.add(nxt)
            queue.append((nxt, new_path))
    return []


def apply_skill_graph(jd, candidate, graph=None):
    """Add graph support to requirement matches; graph-only support is not a match."""
    graph = graph if graph is not None else load_skill_graph()
    matches = candidate.get("requirement_matches") or []
    detected = {str(skill).casefold() for skill in candidate.get("detected_skills", [])}
    total = 0.0
    for match in matches:
        if not isinstance(match, dict):
            continue
        requirement = str(match.get("requirement_name") or match.get("requirement") or "").casefold()
        direct = bool(match.get("keyword_match") is True)
        path = []
        graph_score = 100.0 if direct else 0.0
        if not direct:
            for skill in detected:
                path = _paths(graph, skill, requirement)
                if path:
                    graph_score = min(85.0, 100.0 * (0.85 ** (len(path) - 1)))
                    break
        match["graph_match"] = bool(path) if not direct else False
        match["graph_path"] = path
        match["graph_score"] = round(graph_score, 2)
        total += graph_score
    scores = candidate.setdefault("scores", {})
    scores["graph"] = round(total / len(matches), 2) if matches else 0.0
    return candidate
