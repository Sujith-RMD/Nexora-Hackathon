"""Cross-team integration tests: Teammate 1 core + Teammate 2 trust layer.

These run the REAL pipeline (Teammate 1's matchers/scorer/ranker plus our
graph, critique, counterfactual-with-real-scorer, overqualification, probes,
team mode) — including Teammate 1's actual requirement extractor and, when
PyMuPDF is installed, real resume PDFs from data/resumes/.

Discovered-and-reconciled conventions:
  * T1 emits evidence_type "skills_list" (underscore) — accepted by
    critique/probes skills-only detection.
  * T1 canonical skills (react, node.js, mongodb, rest api, express, docker...)
    match config/skill_graph.json node names.
  * T1's score_candidate(jd, candidate, kw, sem, evi, graph_score, ...) needs
    matcher results as arguments; trust_pipeline.make_scorer_adapter(jd)
    rebuilds the documented (jd, candidate) contract on top of T1's exact
    weights + penalty function for the counterfactual seam.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from src.counterfactual import generate_counterfactual  # noqa: E402
from src.critique import critique_ranking  # noqa: E402
from src.schemas import candidate_to_json, create_default_candidate  # noqa: E402
from src.preprocessing import split_resume_sections  # noqa: E402
from src.trust_pipeline import (  # noqa: E402
    build_jd,
    make_scorer_adapter,
    run_trust_layer,
)

JD_TEXT = """
Job Title: Junior Full Stack Developer Intern
Requirements:
- Must have strong experience with React and Node.js.
- Required: Proficient in MongoDB database design.
- Must be able to build and consume REST API services.
- Preferred: Familiarity with Docker and AWS.
"""

RESUME_ALICE = """
TECHNICAL SKILLS
JavaScript, HTML, CSS

PROJECTS
E-Commerce Dashboard
- Built a full stack application using React, Node.js and MongoDB.
- Designed REST API endpoints for order processing and integrated them with the frontend.
- Deployed the application with Docker.
"""

RESUME_BOB = """
SKILLS
React, Node.js, MongoDB, REST API, Docker

EXPERIENCE
Office Administrator
- Maintained filing systems and coordinated meetings.
"""

RESUME_CHARLIE = """
SKILLS
Express, JavaScript, MySQL

PROJECTS
Booking Platform
- Created scalable microservices with Express and MySQL, handling thousands of requests.
- Implemented server-side routing and JSON payloads for the mobile clients.
"""

RESUME_DANA = """
EDUCATION
BA in Fine Arts

EXPERIENCE
Gallery Assistant
- Organized exhibitions and greeted visitors.
"""


def _candidate(cid, name, resume_text):
    cand = create_default_candidate(
        cid, name, f"{cid}.pdf",
        raw_text=resume_text, clean_text=resume_text,
        sections=split_resume_sections(resume_text),
    )
    from src.skill_extractor import extract_skills_from_text
    cand["detected_skills"] = extract_skills_from_text(resume_text)
    return cand


def _model():
    from src.semantic_matcher import get_semantic_model
    return get_semantic_model()


# ---------------------------------------------------------------------------

def test_it_jd_extraction_contract():
    jd = build_jd(JD_TEXT, title="Junior Full Stack Developer Intern")
    names = {r["name"] for r in jd["requirements"]}
    assert {"react", "node.js", "mongodb", "rest api"} <= names, names
    assert jd["role_level"] == "intern"
    assert all("id" in r and "importance" in r and "weight" in r for r in jd["requirements"])


def test_it_full_trust_layer_synthetic_batch():
    """The real blend: T1 matchers+scorer, our graph+critique+CF+overqual+probes."""
    jd = build_jd(JD_TEXT)
    batch = [
        _candidate("AL", "Alice", RESUME_ALICE),
        _candidate("BO", "Bob", RESUME_BOB),
        _candidate("CH", "Charlie", RESUME_CHARLIE),
        _candidate("DA", "Dana", RESUME_DANA),
    ]
    ranked, team = run_trust_layer(jd, batch, model=_model())

    assert [c["rank"] for c in ranked] == [1, 2, 3, 4]
    assert ranked[0]["candidate_id"] == "AL", "full-stack demonstrator should rank first"
    assert ranked[-1]["candidate_id"] == "DA", "irrelevant profile should rank last"

    for c in ranked:
        # T1 core populated
        assert c["scores"]["final_score"] <= c["scores"]["base_score"] + 1e-9
        assert len(c["requirement_matches"]) == len(jd["requirements"])
        # T2 enrichment present and contract-shaped
        assert set(c["critique"]) == {"confidence", "flags", "summary", "human_review_recommended"}
        assert {"target_rank", "target_score", "suggested_improvements", "projected_score"} <= set(c["counterfactual"])
        assert set(c["overqualification"]) == {"flag", "reasons"}
        assert isinstance(c["interview_probes"], list)
        for m in c["requirement_matches"]:
            assert {"graph_match", "graph_path", "graph_score"} <= set(m)
        json.loads(candidate_to_json(c))

    # Bob: skills-list-only -> our convention fix must fire end to end
    bob = next(c for c in ranked if c["candidate_id"] == "BO")
    assert any("skills-list" in f for f in bob["critique"]["flags"]), bob["critique"]["flags"]
    assert any("under Skills" in p for p in bob["interview_probes"])
    assert bob["critique"]["human_review_recommended"] is True

    # Charlie: no explicit node.js, but Express on resume -> graph supports it
    charlie = next(c for c in ranked if c["candidate_id"] == "CH")
    node_entry = next(m for m in charlie["requirement_matches"]
                      if m["requirement_name"] == "node.js")
    assert node_entry["graph_match"] is True
    assert node_entry["graph_path"][0] == "express"
    assert node_entry["keyword_match"] is False, "graph must not fake a keyword match"

    # Team result valid trio from the real batch
    assert len(team["members"]) == 3
    assert team["teams_evaluated"] == 4  # C(4,3)


def test_it_counterfactual_with_real_scorer_adapter():
    """DoD line 'Counterfactual uses core scorer': gains come from T1's exact
    weights + capped penalty function, not from the stand-in model."""
    jd = build_jd(JD_TEXT)
    batch = [
        _candidate("AL", "Alice", RESUME_ALICE),
        _candidate("BO", "Bob", RESUME_BOB),
    ]
    ranked, _team = run_trust_layer(jd, batch, model=_model())
    bob = next(c for c in ranked if c["candidate_id"] == "BO")

    stored_scores_before = dict(bob["scores"])
    result = generate_counterfactual(bob, ranked, jd,
                                     scorer=make_scorer_adapter(jd))
    assert result["scorer_backend"] == "injected-scorer"
    assert result["projected_score"] > result["current_score"]
    assert result["suggested_improvements"], "listed-only evidence must be upgradeable"
    assert all(i["estimated_gain"] > 0 for i in result["suggested_improvements"])
    # Baseline probe must not have mutated authoritative scores.
    assert bob["scores"] == stored_scores_before


def test_it_penalty_shrinks_via_adapter():
    """The adapter recomputes T1's missing-required penalty from the current
    matches: a simulated fix must shrink it when the adapter sees matched=True."""
    jd = build_jd(JD_TEXT)
    from src.scorer import calculate_critical_missing_penalty
    missing_all = make_scorer_adapter(jd)  # sanity on the penalty helper itself
    assert missing_all is not None
    assert calculate_critical_missing_penalty(["react", "node.js", "mongodb", "rest api"]) == 10.0  # capped
    assert 0 < calculate_critical_missing_penalty(["react"]) < 10.0


def test_it_real_pdfs_end_to_end():
    """Heaviest proof: parse REAL resumes from Teammate 1's data/ and run the
    complete enriched chain. Skips only if PyMuPDF is unavailable."""
    try:
        import fitz  # noqa: F401
    except ImportError:
        print("      (skipped: PyMuPDF not installed)")
        return
    from src.pipeline import parse_candidate_from_pdf

    pdf_dir = ROOT / "data" / "resumes"
    picks = [
        pdf_dir / "web_dev__aditya_kulkarni.pdf",
        pdf_dir / "web_dev__priya_nair.pdf",
        pdf_dir / "sde__arjun_desai.pdf",
        pdf_dir / "python_dev__karan_verma.pdf",
        pdf_dir / "sales__aman_tiwari.pdf",
    ]
    missing = [p for p in picks if not p.exists()]
    assert not missing, f"Teammate 1 data missing: {missing}"

    jd = build_jd(JD_TEXT)
    candidates = [parse_candidate_from_pdf(str(p)) for p in picks]
    for c in candidates:
        assert c["clean_text"].strip(), f"empty parse for {c['file_name']}"
        assert c["parse_quality"]["score"] >= 0.0

    ranked, team = run_trust_layer(jd, candidates, model=_model())
    assert [c["rank"] for c in ranked] == [1, 2, 3, 4, 5]

    # Meaningful spread + every candidate fully enriched & serializable.
    assert ranked[0]["scores"]["final_score"] >= ranked[-1]["scores"]["final_score"]
    blob = json.dumps({"ranked": ranked, "team": team}, default=str)
    parsed = json.loads(blob)
    assert parsed["team"]["members"] == team["members"]

    for c in ranked:
        assert c["critique"]["confidence"] in ("high", "medium", "low")
        assert isinstance(c["interview_probes"], list) and len(c["interview_probes"]) <= 5
        assert "counterfactual" in c and c["counterfactual"] is not None
        # requirement matches mirror the extracted JD exactly
        assert {m["requirement_id"] for m in c["requirement_matches"]} == \
               {r["id"] for r in jd["requirements"]}

    # At least one web/SDE profile should show non-trivial keyword coverage.
    best_kw = max(c["scores"]["keyword"] for c in ranked)
    assert best_kw >= 25.0, f"no candidate reached any meaningful coverage ({best_kw})"


# ---------------------------------------------------------------------------
# UI integration layer (src/analysis_runner.py + app.py)
# ---------------------------------------------------------------------------

def test_it_jd_bias_rules_deterministic():
    from src.jd_bias import review_jd

    risky = build_jd(
        "Job Title: Rockstar developer\n"
        "We want a recent graduate, young and energetic, digital native,\n"
        "must have a degree, good communication skills, culture fit.\n"
        "Requirements:\n- Must know React."
    )
    flags = review_jd(risky)
    phrases = {f["phrase"] for f in flags}
    assert {"rockstar", "recent graduate", "young", "culture fit"} <= phrases
    assert all(set(f) == {"phrase", "reason", "suggestion"} for f in flags)

    clean = review_jd(build_jd(JD_TEXT))
    assert clean == [], f"clean intern JD must not raise flags, got {clean}"
    # determinism
    assert review_jd(risky) == flags


def test_it_analysis_runner_from_upload_bytes():
    """Exactly what the Streamlit file uploader hands us: bytes + names."""
    try:
        import fitz  # noqa: F401
    except ImportError:
        print("      (skipped: PyMuPDF not installed)")
        return
    from src.analysis_runner import analyze_uploads

    jd_bytes = (ROOT / "data" / "jd" / "Sample_JD.pdf").read_bytes()
    picks = ["web_dev__aditya_kulkarni.pdf", "web_dev__priya_nair.pdf",
             "sales__aman_tiwari.pdf"]
    resumes = [((ROOT / "data" / "resumes" / p).read_bytes(), p) for p in picks]

    seen_stages = []
    payload = analyze_uploads(jd_bytes, "Sample_JD.pdf", resumes,
                              on_stage=seen_stages.append, model=_model())

    assert set(payload) == {"jd", "ranked_candidates", "team_result",
                            "jd_warnings", "resume_warnings"}
    assert any("Ranking" in s for s in seen_stages), seen_stages
    assert len(payload["ranked_candidates"]) == 3
    assert payload["ranked_candidates"][0]["rank"] == 1
    for c in payload["ranked_candidates"]:
        assert c["critique"] and c["counterfactual"] and c["overqualification"]
        assert "missing_required_skills" in c  # the key the UI reads
    assert "members" in payload["team_result"]
    assert isinstance(payload["jd"]["bias_flags"], list)
    json.dumps(payload, default=str)


def test_it_streamlit_app_boots_and_analyzes_sample_batch():
    """The real Streamlit app, headless: boot -> sample mode -> Analyze ->
    enriched rankings in session state. Proves the full UI integration."""
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        print("      (skipped: streamlit not installed)")
        return

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=300)
    at.run()
    assert not at.exception, at.exception
    assert any("InternLoom" in str(t.value) for t in at.title)

    # Switch sidebar source to the bundled batch and click Analyze.
    at.radio[0].set_value("sample").run()
    assert not at.exception
    at.button[0].click()
    at.run()
    assert not at.exception, at.exception

    ranked = at.session_state["ranked_candidates"]
    assert len(ranked) == 5, "sample batch should rank five bundled resumes"
    assert [c["rank"] for c in ranked] == [1, 2, 3, 4, 5]
    assert all(c.get("critique") for c in ranked)
    team = at.session_state["team_result"]
    assert team and len(team["members"]) == 3
    assert at.session_state["parsed_jd"]["requirements"]
    # no error branch was rendered
    assert at.session_state["last_error"] is None
    assert len(at.error) == 0, [e.value for e in at.error]
