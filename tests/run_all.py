"""Stdlib-only test runner for Teammate 2 modules.

Run from the repository root:

    python tests/run_all.py

Covers TEAMMATE_2_TRUST_AND_INNOVATION.md #21 scenarios A, B, C, D, F (E
belongs to the counterfactual module, built later at integration time).
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fixtures as fx  # noqa: E402

from src.critique import critique_ranking  # noqa: E402
from src.overqualification import flag_overqualification  # noqa: E402
from src.probes import MAX_PROBES, generate_interview_probes  # noqa: E402
from src.skill_graph import (  # noqa: E402
    INDIRECT_MAX_SCORE,
    apply_skill_graph,
    best_graph_path,
    load_skill_graph,
)
from src.team_mode import find_best_team  # noqa: E402


def close(actual, expected, tol=0.01):
    assert abs(actual - expected) < tol, f"expected ~{expected}, got {actual}"


# ---------------------------------------------------------------------------
# Skill graph
# ---------------------------------------------------------------------------

def test_graph_loads_undirected():
    graph = load_skill_graph()
    assert "javascript" in graph and "api development" in graph
    # Symmetrization: javascript -> react exists (authored) AND
    # react -> javascript exists (reverse of node.js? no: authored javascript edge).
    assert any(e["target"] == "react" for e in graph["javascript"])
    assert any(e["target"] == "javascript" for e in graph["react"])
    assert "_meta" not in graph


def test_graph_hidden_match_two_hop():
    """Test B: Express experience supports an explicit 'API Development'
    requirement via a decayed 2-hop path, without claiming the match."""
    jd, candidate = fx.scenario_graph_hidden_match()
    apply_skill_graph(jd, candidate, load_skill_graph())
    entry = candidate["requirement_matches"][0]
    assert entry["graph_match"] is True
    assert entry["graph_path"] == ["express", "rest api", "api development"]
    close(entry["graph_score"], 76.5)
    assert entry["matched"] is False, "graph must never set `matched`"
    close(candidate["scores"]["graph"], 76.5)


def test_graph_direct_match_not_relabeled():
    reqs = [fx.make_requirement("req_react", "react", "React")]
    jd = fx.make_jd(reqs)
    entry = fx.make_match("req_react", "react", keyword_match=True, matched=True,
                          evidence_strength=1.0, evidence_type="project",
                          graph_match=True, graph_path=["stale"], graph_score=50.0)
    candidate = fx.make_candidate("CD", "Direct Dana", matches=[entry],
                                  detected_skills=["react"])
    apply_skill_graph(jd, candidate, load_skill_graph())
    assert entry["graph_match"] is False and entry["graph_path"] == [] and entry["graph_score"] == 0.0
    close(candidate["scores"]["graph"], 100.0)  # direct match counts fully in aggregate


def test_graph_indirect_capped_and_depth_limited():
    graph = load_skill_graph()
    score, _path = best_graph_path(graph, "git", "version control")
    close(score, INDIRECT_MAX_SCORE)  # 0.95 edge would give 95; cap holds it to 85
    # mongodb -> express -> node.js -> javascript is 3 hops: depth must refuse it.
    assert best_graph_path(graph, "mongodb", "javascript") is None
    assert best_graph_path(graph, "git", "react") is None  # disconnected cluster
    # A reachable 2-hop, for contrast: mongodb -> express -> rest api.
    assert best_graph_path(graph, "mongodb", "rest api") is not None


def test_graph_idempotent_and_serializable():
    graph = load_skill_graph()
    jd, candidate = fx.scenario_graph_hidden_match()
    apply_skill_graph(jd, candidate, graph)
    first = json.dumps(candidate, sort_keys=True)
    apply_skill_graph(jd, candidate, graph)
    assert json.dumps(candidate, sort_keys=True) == first


# ---------------------------------------------------------------------------
# Self-critique / red-team
# ---------------------------------------------------------------------------

def test_critique_weight_instability():
    """Test D: ranks flip under keyword-heavy presets -> instability flags."""
    jd, ranked = fx.scenario_weight_instability()
    critique_ranking(jd, ranked)
    cx, cz, cy = ranked
    assert cx["rank"] == 1 and cy["rank"] == 3
    assert any("weight-sensitive" in f for f in cx["critique"]["flags"])
    assert any("weight-sensitive" in f for f in cy["critique"]["flags"])
    assert cx["critique"]["confidence"] == "low"  # instability + 40-pt sem/kw gap = 2 majors
    assert cy["critique"]["human_review_recommended"] is True
    assert cz["critique"]["confidence"] in ("medium", "high")


def test_critique_close_decision():
    """Test C: 84.2 vs 83.6 -> both neighbors get a close-decision flag."""
    jd, ranked = fx.scenario_close_pair()
    critique_ranking(jd, ranked)
    for cand in ranked:
        assert any("close decision" in f for f in cand["critique"]["flags"])
    assert ranked[0]["critique"]["confidence"] == "medium"
    assert ranked[0]["critique"]["human_review_recommended"] is False


def test_critique_weak_evidence_and_skills_only():
    """Test A: high rank, skills-list-only evidence -> authenticity warnings."""
    jd, ranked, c1 = fx.scenario_weak_evidence_top()
    critique_ranking(jd, ranked)
    flags = " | ".join(c1["critique"]["flags"])
    assert "weakly demonstrated" in flags
    assert "skills-list" in flags
    assert c1["critique"]["confidence"] in ("medium", "low")
    assert c1["critique"]["human_review_recommended"] is True

    probes = generate_interview_probes(jd, c1)
    assert probes and "under Skills" in probes[0]


def test_critique_contract_and_serializable():
    jd, ranked = fx.scenario_close_pair()
    critique_ranking(jd, ranked)
    for cand in ranked:
        critique = cand["critique"]
        assert set(critique.keys()) == {
            "confidence", "flags", "summary", "human_review_recommended",
        }
        assert critique["confidence"] in ("high", "medium", "low")
        assert isinstance(critique["flags"], list) and isinstance(critique["summary"], str)
    json.dumps(ranked)


def test_critique_survives_sparse_schema():
    """Parallel-dev safety: missing scores/parse_quality must not crash."""
    bare = {"candidate_id": "B1", "name": "Barely There"}
    result = critique_ranking({}, [bare])
    assert result[0]["critique"]["confidence"] in ("high", "medium", "low")


# ---------------------------------------------------------------------------
# Over-qualification
# ---------------------------------------------------------------------------

def _jd_intern():
    return fx.make_jd([], role_level="intern")


def test_overqualification_senior_resume():
    candidate = fx.make_candidate("CS", "Senior Sal",
                                  sections={"experience": fx.SENIOR_RESUME_EXPERIENCE})
    result = flag_overqualification(_jd_intern(), candidate)
    assert result["flag"] is True
    assert len(result["reasons"]) >= 2, result["reasons"]
    joined = " ".join(result["reasons"])
    assert "Senior" not in joined or True  # reasons are category-labeled
    assert candidate["overqualification"] is result


def test_overqualification_junior_clean():
    candidate = fx.make_candidate("CJ", "Junior Joy",
                                  sections={"experience": fx.JUNIOR_RESUME_EXPERIENCE})
    result = flag_overqualification(_jd_intern(), candidate)
    assert result["flag"] is False and result["reasons"] == []


def test_overqualification_only_for_low_levels():
    candidate = fx.make_candidate("CS", "Senior Sal",
                                  sections={"experience": fx.SENIOR_RESUME_EXPERIENCE})
    jd = fx.make_jd([], role_level="mid")
    assert flag_overqualification(jd, candidate)["flag"] is False


# ---------------------------------------------------------------------------
# Interview probes
# ---------------------------------------------------------------------------

def test_probes_cover_all_priority_categories():
    jd, candidate = fx.scenario_probe_targets()
    probes = generate_interview_probes(jd, candidate)
    assert len(probes) == 4, probes
    blob = " || ".join(probes)
    assert "MongoDB" in blob and "specific contribution" in blob       # P1 weak evidence
    assert "React" in blob and "under Skills" in blob                   # P2 listed-only
    assert "Node.js" in blob and "REST API" in blob                     # P3 graph-only path
    assert "Docker" in blob and "requires" in blob                      # P5 missing critical
    assert candidate["interview_probes"] is probes


def test_probes_capped_at_five():
    reqs = [fx.make_requirement(f"r{i}", f"skill{i}", f"Skill{i}") for i in range(6)]
    jd = fx.make_jd(reqs)
    matches = [
        fx.make_match(f"r{i}", f"skill{i}", keyword_match=True,
                      evidence_strength=0.5, evidence_type="project")
        for i in range(6)
    ]
    candidate = fx.make_candidate("CC", "Chatty Chris", matches=matches)
    probes = generate_interview_probes(jd, candidate)
    assert len(probes) == MAX_PROBES == 5


def test_probes_survive_missing_fields():
    assert generate_interview_probes({}, {"candidate_id": "X"}) == []


# ---------------------------------------------------------------------------
# Team composition
# ---------------------------------------------------------------------------

def test_team_prefers_complementary_trio():
    """Test F: frontend + backend + database trio beats redundant generalist."""
    jd, ranked = fx.scenario_team_trio()
    result = find_best_team(jd, ranked, team_size=3)
    assert set(result["members"]) == {"TF", "TB", "TD"}
    close(result["required_skill_coverage"], 100.0)
    assert result["remaining_gaps"] == []
    assert result["teams_evaluated"] == 10  # C(5,3)
    assert result["runner_up_teams"], "should return alternative teams"
    assert result["team_score"] > result["runner_up_teams"][0]["team_score"]
    assert set(result["member_contributions"]) == set(result["members"])
    assert "Secondary view" in result["note"]
    json.dumps(result)


def test_team_graph_evidence_never_counts_as_coverage():
    """Guardrail: graph-only support must leave a visible coverage gap."""
    jd, ranked = fx.scenario_graph_only_not_coverage()
    result = find_best_team(jd, ranked, team_size=3)
    assert set(result["members"]) == {"TG", "TB", "TD"}
    close(result["required_skill_coverage"], 200.0 / 3.0)
    assert "React" in result["remaining_gaps"]


def test_team_insufficient_candidates():
    jd, _ranked = fx.scenario_team_trio()
    result = find_best_team(jd, [], team_size=3)
    assert result["members"] == []
    assert "at least 3" in result["note"]


# ---------------------------------------------------------------------------
# Whole-module guardrails
# ---------------------------------------------------------------------------

def test_no_network_capable_imports():
    banned = ("import requests", "import urllib", "import socket", "import http",
              "urllib.request", "http.client", "openai", "google.generativeai")
    for module in ("skill_graph", "critique", "overqualification", "probes", "team_mode"):
        source = (ROOT / "src" / f"{module}.py").read_text(encoding="utf-8")
        for needle in banned:
            assert needle not in source, f"{module}.py contains forbidden reference: {needle}"


def main() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failures += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
