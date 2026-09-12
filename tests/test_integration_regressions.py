"""Regressions found while merging all three teammate branches."""
import copy
import socket
from pathlib import Path
from unittest.mock import patch

from src.keyword_matcher import keyword_match
from src.evidence import score_evidence
from src.requirement_extractor import extract_requirements
from src.trust_pipeline import build_jd, run_trust_layer, make_scorer_adapter
from src.team_mode import find_best_team
from src.critique import critique_ranking

JD = """Junior Full Stack Developer Intern
Must have strong programming knowledge in Python or JavaScript.
Required: Hands-on experience developing web applications with React or Node.js.
Must know database management with MongoDB or PostgreSQL.
Preferred: REST API and Git.
Docker is a bonus.
"""


def test_or_groups_accept_each_side_and_do_not_double_count():
    jd = build_jd(JD)
    required = [r for r in jd["requirements"] if r["importance"] == "required"]
    assert len(required) == 3
    assert all(r["weight"] == 3 and r["match_mode"] == "any" for r in required)
    only_required = {"requirements": required}
    for skills in ("Python React PostgreSQL", "JavaScript NodeJS MongoDB", "Python JavaScript React Node.js MongoDB PostgreSQL"):
        candidate = {"sections": {"projects": f"Built an application using {skills} for managing customer data."}}
        result = keyword_match(only_required, candidate)
        assert result["keyword_score"] == 100
        assert result["missing_required"] == []
        assert len(result["requirement_matches"]) == 3
        assert score_evidence(only_required, candidate)["evidence_score"] == 100
    assert len(keyword_match(only_required, {"sections": {"skills": "Docker"}})["missing_required"]) == 3


def test_and_and_separate_required_occurrences_are_preserved():
    reqs = extract_requirements("Required: Python and JavaScript. Preferred: Python or JavaScript.")
    assert {r["name"] for r in reqs if r["importance"] == "required"} == {"python", "javascript"}
    assert len(reqs) == 3
    reqs = extract_requirements("Required:\nPython or JavaScript\nPreferred:\nDocker")
    assert next(r for r in reqs if r.get("alternatives"))["importance"] == "required"
    for text in ("Required: Python, JavaScript, or Java.", "Must know Python or\nJavaScript."):
        reqs = extract_requirements(text)
        assert len(reqs) == 1 and reqs[0]["match_mode"] == "any"


def test_inline_skill_heading_keeps_evidence_tier():
    from src.preprocessing import split_resume_sections
    candidate = {"sections": split_resume_sections("Skills: React\nEducation: Computer Science")}
    jd = build_jd("Required: React")
    assert keyword_match(jd, candidate)["keyword_score"] == 100
    assert score_evidence(jd, candidate)["evidence_score"] == 35


def test_team_contributions_follow_selected_members():
    jd = {"requirements": [{"id": "a", "name": "a", "importance": "required"}, {"id": "b", "name": "b", "importance": "required"}]}
    def candidate(cid, rid):
        return {"candidate_id": cid, "name": cid, "scores": {"semantic": 50}, "requirement_matches": [{"requirement_id": rid, "matched": True, "keyword_match": True, "evidence_strength": 1}]}
    team = find_best_team(jd, [candidate("zero", "none"), candidate("one", "a"), candidate("two", "b")], team_size=2)
    assert team["members"] == ["one", "two"]
    assert team["member_contributions"] == {"one": ["a"], "two": ["b"]}


def test_zero_parse_quality_is_flagged():
    candidate = {"candidate_id": "bad", "rank": 1, "scores": {}, "parse_quality": {"score": 0}}
    critique_ranking({}, [candidate])
    assert any("extraction quality is low" in flag for flag in candidate["critique"]["flags"])


def test_real_model_and_full_pipeline_without_network():
    from src import semantic_matcher
    from src.pipeline import parse_candidate_from_pdf
    # Force a cold model load while all Python outbound sockets are blocked.
    semantic_matcher._CACHED_MODEL = None
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden")), patch.object(socket, "create_connection", side_effect=AssertionError("Network forbidden")):
        model = semantic_matcher.get_semantic_model()
        root = Path(__file__).resolve().parents[1]
        paths = sorted((root / "data/resumes").glob("*.pdf"))[:4]
        jd = build_jd(JD + "\nContext: CSS")
        ranked, team = run_trust_layer(jd, [parse_candidate_from_pdf(str(p)) for p in paths], model=model)
    assert len(ranked) == 4 and len(team["members"]) == 3
    adapter = make_scorer_adapter(jd)
    for candidate in ranked:
        assert adapter(jd, copy.deepcopy(candidate))["scores"] == candidate["scores"]


def test_missing_model_does_not_use_fake_semantics():
    from src import semantic_matcher
    with patch.object(semantic_matcher, "_CACHED_MODEL", None), patch.object(semantic_matcher, "SentenceTransformer", side_effect=OSError("model missing")):
        import pytest
        with pytest.raises(RuntimeError, match="real semantic model"):
            semantic_matcher.get_semantic_model()


def test_uploads_and_all_ui_tabs_with_real_results():
    import fitz
    from app import run_analysis
    from streamlit.testing.v1 import AppTest
    class Upload:
        type = "application/pdf"
        def __init__(self, name, data):
            self.name, self.data = name, data
        def getvalue(self):
            return self.data
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 50), JD, fontsize=10)
        jd_upload = Upload("job.pdf", doc.tobytes())
    root = Path(__file__).resolve().parents[1]
    paths = [root / "data/resumes" / name for name in ("web_dev__aditya_kulkarni.pdf", "web_dev__priya_nair.pdf", "sde__arjun_desai.pdf", "sales__aman_tiwari.pdf")]
    uploads = [Upload(p.name, p.read_bytes()) for p in paths]
    uploads.append(Upload(paths[0].name, paths[0].read_bytes()))
    ranked, jd, team = run_analysis(jd_upload, uploads)
    assert len({c["candidate_id"] for c in ranked}) == 5
    assert {c["file_name"] for c in ranked} == {p.name for p in paths}
    assert "Aditya Kulkarni" in {c["name"] for c in ranked}
    assert all(c["counterfactual"]["scorer_backend"] == "injected-scorer" for c in ranked)
    at = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
    assert not at.exception
    at.session_state["ranked_candidates"] = ranked
    at.session_state["parsed_jd"] = jd
    at.session_state["team_result"] = team
    at.run()
    assert not at.exception
    assert len(at.tabs) == 4
    assert not at.text_area
    visible_text = "\n".join(element.value for element in at.markdown)
    assert all(name in visible_text for name in team["member_names"])
    assert at.dataframe[0].value["Required Matched"].astype(int).max() <= 3
    at.selectbox[0].select_index(len(ranked) - 1).run()
    assert not at.exception
    assert at.text_area
    at.selectbox(key="compare_candidate_b").select_index(0).run()
    assert not at.exception
    assert any("two different" in warning.value for warning in at.warning)


def test_counterfactual_recomputes_penalty_and_preserves_original():
    from src.counterfactual import generate_counterfactual, _apply_change
    jd = build_jd("Required: Python or JavaScript. Preferred: Docker.")
    candidate = {"candidate_id": "C", "rank": 4, "requirement_matches": [], "scores": {"semantic": 50}}
    adapter = make_scorer_adapter(jd)
    adapter(jd, candidate)
    old = copy.deepcopy(candidate)
    ranked = [{"scores": {"final_score": score}} for score in (90, 80, 60)] + [candidate]
    result = generate_counterfactual(candidate, ranked, jd, scorer=adapter)
    simulated = copy.deepcopy(old)
    for change in result["suggested_improvements"]:
        simulated = _apply_change(simulated, {**change, "requirement_name": change["requirement"]})
    assert result["projected_score"] == adapter(jd, simulated)["scores"]["final_score"]
    assert candidate["scores"] == old["scores"]
    assert candidate["requirement_matches"] == old["requirement_matches"]


def test_demo_button_runs_full_app_and_invalid_upload_clears_old_results():
    from streamlit.testing.v1 import AppTest
    root = Path(__file__).resolve().parents[1]
    at = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
    next(button for button in at.button if button.label == "Run bundled sample demo").click().run()
    assert not at.exception
    assert len(at.session_state["ranked_candidates"]) == 54
    assert len(at.session_state["parsed_jd"]["requirements"]) == 6
    next(button for button in at.button if button.label == "Analyze Candidates").click().run()
    assert not at.exception
    assert at.error
    assert at.session_state["ranked_candidates"] == []


def test_corrupt_resume_is_retained_with_warning_and_no_claimed_evidence(tmp_path):
    from src.pipeline import parse_candidate_from_pdf
    bad = tmp_path / "unreadable.pdf"
    bad.write_bytes(b"not a PDF")
    jd = build_jd(JD)
    candidate = parse_candidate_from_pdf(str(bad))
    ranked, team = run_trust_layer(jd, [candidate])
    assert len(ranked) == 1 and not team["members"]
    assert ranked[0]["parse_quality"]["score"] == 0
    assert ranked[0]["scores"]["final_score"] == 0
    assert ranked[0]["parse_quality"]["warnings"]
    assert all(not m["evidence_text"] for m in ranked[0]["requirement_matches"])
    assert any("extraction quality is low" in flag for flag in ranked[0]["critique"]["flags"])
