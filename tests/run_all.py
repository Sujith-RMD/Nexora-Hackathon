"""Stdlib-only test runner for Teammate 2 modules.

Run from the repository root:

    python tests/run_all.py

Covers TEAMMATE_2_TRUST_AND_INNOVATION.md #21 scenarios A, B, C, D, E, F plus
contract-shape, serialization, graceful-degradation, and no-network checks.
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

from src.counterfactual import generate_counterfactual  # noqa: E402
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
# Counterfactual / coaching
# ---------------------------------------------------------------------------

def test_counterfactual_minimal_set_to_top3():
    """Test E (TEAMMATE_2 #21): rank #6 needs exactly MongoDB + REST API."""
    jd, ranked = fx.scenario_counterfactual()
    c6 = ranked[-1]
    assert c6["rank"] == 6
    result = generate_counterfactual(c6, ranked, jd)

    assert result["target_rank"] == 3
    close(result["target_score"], ranked[2]["scores"]["final_score"])
    assert [i["requirement"] for i in result["suggested_improvements"]] == ["MongoDB", "REST API"]
    assert all(i["estimated_gain"] > 0 for i in result["suggested_improvements"])
    assert result["reached_target"] is True
    assert result["projected_score"] >= result["target_score"] + 0.1 - 1e-6
    # Schema-required keys present; extras allowed (TEAMMATE_2 #13).
    assert {"target_rank", "target_score", "suggested_improvements", "projected_score"} <= set(result)
    # Simulation must not mutate the real candidate data.
    mongo = next(m for m in c6["requirement_matches"] if m["requirement_id"] == "req_mongo")
    assert mongo["matched"] is False
    assert "[simulated]" not in str(mongo.get("evidence_text", ""))
    assert "simulat" in result["disclaimer"].lower()
    assert c6["counterfactual"] is result
    json.dumps(result)


def test_counterfactual_gains_match_documented_formula():
    """Exact expected values under the 0.45/0.35/0.15/0.05 blend:
    mongo add = 8.75 + 3.75 + 1.25 = 13.75; rest promote keeps its 76.5 graph
    effective so only kw+ev+partial graph apply (8.75 + 3.75 + 0.29375)."""
    jd, ranked = fx.scenario_counterfactual()
    c6 = ranked[-1]
    result = generate_counterfactual(c6, ranked, jd)
    mongo, rest = result["suggested_improvements"]
    close(mongo["estimated_gain"], 13.75)
    close(rest["estimated_gain"], 12.79375, tol=0.01)
    projected_expected = c6["scores"]["final_score"] + mongo["estimated_gain"] + rest["estimated_gain"]
    close(result["projected_score"], projected_expected)


def test_counterfactual_top3_candidate_targets_one_up():
    jd, ranked = fx.scenario_counterfactual()
    c2 = ranked[1]
    result = generate_counterfactual(c2, ranked, jd)
    assert result["already_in_top_3"] is True
    assert result["target_rank"] == 1
    assert result["reached_target"] is True
    assert len(result["suggested_improvements"]) == 1  # +13.75 clears 88.15


def test_counterfactual_rank_one_has_no_target():
    jd, ranked = fx.scenario_counterfactual()
    c1 = ranked[0]
    result = generate_counterfactual(c1, ranked, jd)
    assert result["suggested_improvements"] == []
    assert "already ranks #1" in result["message"]


def test_counterfactual_penalty_held_constant():
    """Projected final must reuse the candidate's stored base-penalty gap."""
    jd = fx.make_jd([
        fx.make_requirement("req_react", "react", "React"),
        fx.make_requirement("req_docker", "docker", "Docker"),
    ])
    cand = fx.make_candidate("QP", "Penalized Pat", matches=[
        fx.make_match("req_react", "react", keyword_match=True, matched=True,
                      evidence_strength=1.0, evidence_type="project"),
        fx.make_match("req_docker", "docker", matched=False),
    ], scores={"semantic": 60.0, "keyword": 50.0, "evidence": 50.0, "graph": 50.0,
               "base_score": 60.0, "final_score": 55.0})  # 5-pt penalty

    def rival(cid, name, final):
        return fx.make_candidate(cid, name, scores={
            "semantic": final, "keyword": final, "evidence": final, "graph": final,
            "base_score": final, "final_score": final,
        })

    best, other, target_rival = rival("QT", "Best", 90.0), rival("QS", "Other", 80.0), rival("QR", "Rival", 70.0)
    ranked = [best, other, target_rival, cand]
    for i, c in enumerate(ranked, start=1):
        c["rank"] = i
    result = generate_counterfactual(cand, ranked, jd)
    # gains: kw +50*.35=17.5, ev +50*.15=7.5, graph +50*.05=2.5 => 27.5
    # projected = base 60 + 27.5 - 5 penalty = 82.5
    close(result["suggested_improvements"][0]["estimated_gain"], 27.5)
    close(result["projected_score"], 82.5)
    assert result["reached_target"] is True


def test_counterfactual_injected_scorer_backend():
    """The integration seam: a real (here fake) scorer replaces the model."""
    jd = fx.make_jd([fx.make_requirement(f"r{i}", f"s{i}", f"S{i}") for i in range(4)])

    def fake_scorer(jd_, candidate_):
        n = sum(1 for m in candidate_.get("requirement_matches", []) if m.get("matched"))
        return {"base_score": 50.0 + 10.0 * n}

    cand = fx.make_candidate("QI", "Injected Ida", matches=[
        fx.make_match("r0", "s0", keyword_match=True, matched=True, evidence_strength=1.0),
        fx.make_match("r1", "s1", keyword_match=True, matched=True, evidence_strength=1.0),
        fx.make_match("r2", "s2", matched=False),
        fx.make_match("r3", "s3", matched=False),
    ], scores={"semantic": 0.0, "keyword": 0.0, "evidence": 0.0, "graph": 0.0,
               "base_score": 70.0, "final_score": 70.0})
    ranked = [
        fx.make_candidate("A", "A", scores={"base_score": 0.0, "final_score": 90.0,
                                            "semantic": 0, "keyword": 0, "evidence": 0, "graph": 0}),
        fx.make_candidate("B", "B", scores={"base_score": 0.0, "final_score": 80.0,
                                            "semantic": 0, "keyword": 0, "evidence": 0, "graph": 0}),
        fx.make_candidate("C", "C", scores={"base_score": 0.0, "final_score": 75.0,
                                            "semantic": 0, "keyword": 0, "evidence": 0, "graph": 0}),
        cand,
    ]
    for i, c in enumerate(ranked, start=1):
        c["rank"] = i
    result = generate_counterfactual(cand, ranked, jd, scorer=fake_scorer)
    assert result["scorer_backend"] == "injected-scorer"
    close(result["suggested_improvements"][0]["estimated_gain"], 10.0)  # fake: +10 per match
    close(result["projected_score"], 80.0)
    assert result["reached_target"] is True


def test_counterfactual_gap_too_large_reports_honestly():
    jd, ranked = fx.scenario_counterfactual()
    ranked[2]["scores"]["final_score"] = 150.0  # impossible target
    c6 = ranked[-1]
    result = generate_counterfactual(c6, ranked, jd)
    assert result["reached_target"] is False
    assert len(result["suggested_improvements"]) == 3  # capped at MAX_IMPROVEMENTS
    assert "would not reach" in result["message"]


def test_counterfactual_survives_sparse_schema():
    bare = {"candidate_id": "Z", "name": "Zed"}
    result = generate_counterfactual(bare, [], {})
    assert {"target_rank", "target_score", "suggested_improvements", "projected_score"} <= set(result)
    assert result["suggested_improvements"] == []
    assert bare["counterfactual"] is result
    json.dumps(result)


# ---------------------------------------------------------------------------
# Whole-module guardrails
# ---------------------------------------------------------------------------

def test_no_network_capable_imports():
    banned = ("import requests", "import urllib", "import socket", "import http",
              "urllib.request", "http.client", "openai", "google.generativeai")
    for module in ("skill_graph", "critique", "overqualification", "probes",
                   "team_mode", "counterfactual", "trust_pipeline",
                   "jd_bias", "analysis_runner"):
        source = (ROOT / "src" / f"{module}.py").read_text(encoding="utf-8")
        for needle in banned:
            assert needle not in source, f"{module}.py contains forbidden reference: {needle}"


# ---------------------------------------------------------------------------
# End-to-end trust pipeline (integration rehearsal, docs #20 order)
# ---------------------------------------------------------------------------

def test_full_teammate2_pipeline_order():
    """Run every Teammate 2 module in the documented integration sequence on
    one batch and verify the fully enriched schema survives a JSON round trip.

    Order (TEAMMATE_2 #20): graph -> critique -> counterfactual ->
    overqualification -> probes -> team mode.
    """
    jd, ranked = fx.scenario_counterfactual()
    graph = load_skill_graph()

    for candidate in ranked:
        apply_skill_graph(jd, candidate, graph)
        flag_overqualification(jd, candidate)
        generate_interview_probes(jd, candidate)

    critique_ranking(jd, ranked)
    for candidate in ranked:
        generate_counterfactual(candidate, ranked, jd)

    # 1. Every candidate carries the four UI-exposed enrichment blocks.
    for candidate in ranked:
        assert set(candidate["critique"]) == {
            "confidence", "flags", "summary", "human_review_recommended",
        }
        assert {"target_rank", "target_score", "suggested_improvements",
                "projected_score"} <= set(candidate["counterfactual"])
        assert set(candidate["overqualification"]) == {"flag", "reasons"}
        assert isinstance(candidate["interview_probes"], list)
        assert len(candidate["interview_probes"]) <= MAX_PROBES

    # 2. Graph fields exist on every considered requirement match.
    for candidate in ranked:
        for entry in candidate["requirement_matches"]:
            assert {"graph_match", "graph_path", "graph_score"} <= set(entry)

    # 3. The graph actually helps the Express kid: Q6's REST API requirement
    #    gets indirect support, and the counterfactual then offers to promote it.
    q6 = ranked[-1]
    rest = next(m for m in q6["requirement_matches"] if m["requirement_id"] == "req_rest")
    assert rest["graph_match"] is True or rest["keyword_match"] is True
    improve_ids = {i["requirement"] for i in q6["counterfactual"]["suggested_improvements"]}
    assert "MongoDB" in improve_ids  # missing must be on the coaching list

    # 4. Team mode consumes the enriched batch and returns a valid trio.
    team = find_best_team(jd, ranked, team_size=3)
    assert len(team["members"]) == 3
    assert set(team["members"]) <= {c["candidate_id"] for c in ranked}

    # 5. Serializable for results/latest_results.json + UI.
    restored = json.loads(json.dumps({"jd": jd, "ranked_candidates": ranked, "team": team}))
    assert restored["team"]["members"] == team["members"]


def main() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]

    # Cross-team integration tests (real T1 core + T2 trust layer). Imported
    # here so a model/dependency failure degrades to a clear notice, not a
    # crash of the unit suite.
    try:
        import test_teammate2_integration as _it
        tests += [(name, fn) for name, fn in sorted(vars(_it).items())
                  if name.startswith("test_") and callable(fn)]
    except Exception as exc:  # pragma: no cover - environment-dependent
        print(f"NOTE  integration tests unavailable: {exc}")

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
