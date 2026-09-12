"""Schema-valid fixture factories for Teammate 2 modules (tests only).

These build dictionaries that conform to MASTER_CONTEXT.md #7.1/#7.2 so that
Teammate 2 modules can be developed and verified without the core pipeline.
The score helper here mirrors the DOCUMENTED blend (#8) — it is a test
stand-in for Teammate 1's real scorer, not a second ranking engine.
"""

from __future__ import annotations

BASE_WEIGHTS = {"semantic": 0.45, "keyword": 0.35, "evidence": 0.15, "graph": 0.05}
PENALTY_CAP = 10.0
IMPORTANCE_WEIGHTS = {"required": 3.0, "preferred": 2.0, "context": 1.0}


def compute_scores(semantic=0.0, keyword=0.0, evidence=0.0, graph=0.0, missing_penalty=0.0):
    base = (
        BASE_WEIGHTS["semantic"] * semantic
        + BASE_WEIGHTS["keyword"] * keyword
        + BASE_WEIGHTS["evidence"] * evidence
        + BASE_WEIGHTS["graph"] * graph
    )
    final = base - max(0.0, min(missing_penalty, PENALTY_CAP))
    return {
        "semantic": semantic,
        "keyword": keyword,
        "evidence": evidence,
        "graph": graph,
        "base_score": base,
        "final_score": final,
    }


def make_requirement(rid, name=None, display_name=None, importance="required",
                     weight=None, category="skill", source_text=""):
    name = name or rid
    return {
        "id": rid,
        "name": name,
        "display_name": display_name or name,
        "category": category,
        "importance": importance,
        "weight": weight if weight is not None else IMPORTANCE_WEIGHTS[importance],
        "source_text": source_text,
    }


def make_jd(requirements, role_level="junior", title="Junior Full Stack Developer Intern"):
    return {
        "title": title,
        "raw_text": title,
        "clean_text": title,
        "requirements": requirements,
        "role_level": role_level,
        "bias_flags": [],
    }


def make_match(rid, requirement_name=None, *, keyword_match=False, keyword_score=0.0,
               semantic_score=0.0, graph_match=False, graph_path=None, graph_score=0.0,
               evidence_strength=0.0, evidence_type="none", evidence_text="", matched=None):
    if matched is None:
        matched = bool(keyword_match)
    return {
        "requirement_id": rid,
        "requirement_name": requirement_name or rid,
        "keyword_match": keyword_match,
        "keyword_score": keyword_score,
        "semantic_score": semantic_score,
        "graph_match": graph_match,
        "graph_path": list(graph_path or []),
        "graph_score": graph_score,
        "evidence_strength": evidence_strength,
        "evidence_type": evidence_type,
        "evidence_text": evidence_text,
        "matched": matched,
    }


def make_candidate(cid, name, *, scores=None, matches=None, detected_skills=None,
                   sections=None, parse_quality=None, rank=0):
    return {
        "candidate_id": cid,
        "name": name,
        "file_name": f"{cid}.pdf",
        "raw_text": "",
        "clean_text": "",
        "sections": {
            "skills": "", "experience": "", "projects": "",
            "education": "", "certifications": "", "other": "",
            **(sections or {}),
        },
        "parse_quality": parse_quality if parse_quality is not None else {"score": 100.0, "warnings": []},
        "detected_skills": list(detected_skills or []),
        "requirement_matches": list(matches or []),
        "scores": scores if scores is not None else compute_scores(),
        "matched_required_skills": [],
        "missing_required_skills": [],
        "matched_preferred_skills": [],
        "rank": rank,
    }


def rank_candidates(candidates):
    """Mirror Teammate 1's documented ranking (final desc; evidence then
    semantic as explicit tie-breakers). Assigns 1-based 'rank' in place."""
    ordered = sorted(
        candidates,
        key=lambda c: (
            -c["scores"]["final_score"],
            -c["scores"]["evidence"],
            -c["scores"]["semantic"],
        ),
    )
    for i, c in enumerate(ordered, start=1):
        c["rank"] = i
    return ordered


# ---------------------------------------------------------------------------
# Reusable scenarios (TEAMMATE_2 #21 test scenarios minus counterfactual)
# ---------------------------------------------------------------------------

def scenario_graph_hidden_match():
    """Test B: candidate has Express experience; JD requires 'api development'
    explicitly but the exact phrase is absent. Graph should support it."""
    jd = make_jd([make_requirement("req_api", "api development", "API Development")])
    candidate = make_candidate(
        "C01", "Graph Kid",
        matches=[make_match("req_api", "api development", semantic_score=70.0)],
        detected_skills=["express"],
    )
    return jd, candidate


def scenario_weight_instability():
    """Test D: candidate #1 under semantic-heavy weights slides to #3 under
    keyword-heavy weights."""
    x = make_candidate("CX", "Semantic Sam", scores=compute_scores(90, 50, 70, 0))
    z = make_candidate("CZ", "Middle Mia", scores=compute_scores(75, 65, 70, 0))
    y = make_candidate("CY", "Keyword Kate", scores=compute_scores(60, 80, 70, 0))
    ranked = rank_candidates([x, z, y])
    return make_jd([]), ranked


def scenario_close_pair():
    """Test C: 84.2 vs 83.6 final scores -> close decision flags."""
    a = make_candidate("CA", "Almost Alice",
                       scores={"semantic": 85.0, "keyword": 85.0, "evidence": 85.0,
                               "graph": 85.0, "base_score": 85.0, "final_score": 84.2})
    b = make_candidate("CB", "Barely Bob",
                       scores={"semantic": 84.0, "keyword": 84.0, "evidence": 84.0,
                               "graph": 84.0, "base_score": 84.0, "final_score": 83.6})
    ranked = rank_candidates([a, b])
    return make_jd([]), ranked


def scenario_weak_evidence_top():
    """Test A: lots of listed skills, no demonstrated evidence."""
    matches = [
        make_match("req_react", "react", keyword_match=True, keyword_score=100.0,
                   evidence_strength=0.35, evidence_type="skills"),
        make_match("req_node", "node.js", keyword_match=True, keyword_score=100.0,
                   evidence_strength=0.35, evidence_type="skills"),
        make_match("req_mongo", "mongodb", keyword_match=True, keyword_score=100.0,
                   evidence_strength=0.35, evidence_type="skills"),
    ]
    c1 = make_candidate("CW1", "Lister Larry", matches=matches,
                        detected_skills=["react", "node.js", "mongodb"],
                        scores=compute_scores(88, 88, 50))
    c2 = make_candidate("CW2", "Solid Susan", scores=compute_scores(70, 70, 70))
    ranked = rank_candidates([c1, c2])
    jd = make_jd([
        make_requirement("req_react", "react", "React"),
        make_requirement("req_node", "node.js", "Node.js"),
        make_requirement("req_mongo", "mongodb", "MongoDB"),
    ])
    return jd, ranked, c1


def scenario_probe_targets():
    """One candidate with all five probe-relevant requirement situations."""
    jd = make_jd([
        make_requirement("req_mongo", "mongodb", "MongoDB"),
        make_requirement("req_react", "react", "React"),
        make_requirement("req_rest", "rest api", "REST API"),
        make_requirement("req_docker", "docker", "Docker"),
    ])
    matches = [
        make_match("req_mongo", "mongodb", keyword_match=True, evidence_strength=0.5,
                   evidence_type="project"),
        make_match("req_react", "react", keyword_match=True, evidence_strength=0.35,
                   evidence_type="skills"),
        make_match("req_rest", "rest api", graph_match=True, matched=False,
                   graph_path=["node.js", "express", "rest api"], graph_score=76.5),
        make_match("req_docker", "docker", matched=False),
    ]
    candidate = make_candidate("CP", "Probe Pat", matches=matches,
                               detected_skills=["mongodb", "react", "node.js"],
                               scores=compute_scores(55, 40, 50))
    return jd, candidate


def scenario_team_trio():
    """Test F: frontend / backend / database specialists beat a strong
    but redundant generalist."""
    jd = make_jd([
        make_requirement("req_react", "react", "React"),
        make_requirement("req_node", "node.js", "Node.js"),
        make_requirement("req_mongo", "mongodb", "MongoDB"),
    ])

    def cov(rid, strength=0.75):
        return make_match(rid, rid, keyword_match=True, matched=True,
                          evidence_strength=strength, evidence_type="project")

    f = make_candidate("TF", "Front Fiona", matches=[cov("req_react")],
                       scores=compute_scores(80, 60, 60))
    b = make_candidate("TB", "Back Ben", matches=[cov("req_node")],
                       scores=compute_scores(85, 60, 60))
    d = make_candidate("TD", "Data Dan", matches=[cov("req_mongo")],
                       scores=compute_scores(75, 60, 60))
    w = make_candidate("TW", "Wide Wendy", matches=[cov("req_react"), cov("req_node"),
                                                    make_match("req_mongo", "mongodb", matched=False)],
                       scores=compute_scores(90, 80, 60))
    v = make_candidate("TV", "Vacuous Vera", scores=compute_scores(50, 40, 40))
    ranked = rank_candidates([f, b, d, w, v])
    return jd, ranked


def scenario_graph_only_not_coverage():
    """Guardrail test: graph-only support must not count as team coverage."""
    jd = make_jd([make_requirement("req_react", "react", "React"),
                  make_requirement("req_node", "node.js", "Node.js"),
                  make_requirement("req_mongo", "mongodb", "MongoDB")])
    g = make_candidate("TG", "Graph-only Greg", matches=[
        make_match("req_react", "react", matched=False, graph_match=True,
                   graph_path=["javascript", "react"], graph_score=90.0),
    ], scores=compute_scores(80, 50, 40))
    b = make_candidate("TB", "Back Ben",
                       matches=[make_match("req_node", "node.js", keyword_match=True,
                                           matched=True, evidence_strength=0.75,
                                           evidence_type="project")],
                       scores=compute_scores(85, 60, 60))
    d = make_candidate("TD", "Data Dan",
                       matches=[make_match("req_mongo", "mongodb", keyword_match=True,
                                           matched=True, evidence_strength=0.75,
                                           evidence_type="project")],
                       scores=compute_scores(75, 60, 60))
    ranked = rank_candidates([g, b, d])
    return jd, ranked


SENIOR_RESUME_EXPERIENCE = (
    "Professional Experience\n"
    "Senior Software Engineer, Acme Corp (2019-2023)\n"
    "Led a team of 5 developers shipping the payments platform.\n"
    "Managed a team of engineers across two squads.\n"
    "Mentored junior interns and reviewed all architecture decisions.\n"
    "8+ years of experience building distributed systems.\n"
)

JUNIOR_RESUME_EXPERIENCE = (
    "Experience\n"
    "Software Engineering Intern, BetaWorks\n"
    "Built React components and fixed bugs under supervision.\n"
    "2 years of coursework projects.\n"
)
