"""Recruiter-facing Streamlit shell for InternLoom AI.

The UI consumes the shared core and trust pipeline. Scoring is implemented
in the pipeline modules, with the real semantic model required locally.
"""

from pathlib import PurePath, Path
import os
import tempfile
import hashlib
import json

import streamlit as st
from src.trust_pipeline import run_trust_layer

from src.candidate_outcomes import generate_rejection_draft, route_alternative_role
from src.jd_bias import detect_jd_bias
from src.pipeline import parse_candidate_from_pdf
from src.requirement_extractor import detect_role_level, extract_requirements
from src.semantic_matcher import get_semantic_model


STATE_DEFAULTS = {
	"parsed_jd": None,
	"ranked_candidates": [],
	"team_result": None,
	"selected_candidates": [],
}


def initialize_session_state() -> None:
	"""Create the state owned by the recruiter experience."""
	for key, default in STATE_DEFAULTS.items():
		if key not in st.session_state:
			st.session_state[key] = default.copy() if isinstance(default, list) else default


def is_pdf_upload(uploaded_file) -> bool:
	"""Return whether an upload has a PDF filename and, when available, MIME type."""
	if uploaded_file is None:
		return False

	has_pdf_extension = PurePath(uploaded_file.name).suffix.lower() == ".pdf"
	reported_type = getattr(uploaded_file, "type", None)
	has_valid_type = not reported_type or reported_type == "application/pdf"
	return has_pdf_extension and has_valid_type


def validate_uploads(jd_file, resume_files) -> list[str]:
	"""Return recruiter-facing validation messages for the selected files."""
	errors = []

	if jd_file is None:
		errors.append("Upload one job description PDF before analyzing candidates.")
	elif not is_pdf_upload(jd_file):
		errors.append("The job description must be a PDF file.")

	if not resume_files:
		errors.append("Upload at least one resume PDF before analyzing candidates.")
	else:
		invalid_resumes = [
			resume.name for resume in resume_files if not is_pdf_upload(resume)
		]
		if invalid_resumes:
			errors.append(
				"These resume files are not valid PDFs: " + ", ".join(invalid_resumes)
			)

	return errors


def render_empty_state(message: str) -> None:
	"""Render a consistent empty state until the corresponding pipeline is connected."""
	st.info(message)


def _as_display_text(value, fallback: str = "Not available") -> str:
	"""Convert optional structured values into readable UI text."""
	if value is None or value == "":
		return fallback
	if isinstance(value, (list, tuple, set)):
		return ", ".join(str(item) for item in value) if value else fallback
	if isinstance(value, dict):
		return "; ".join(f"{key}: {item}" for key, item in value.items())
	return str(value)


def _candidate_confidence(candidate: dict) -> str:
	"""Read an existing confidence value without deriving one."""
	confidence = candidate.get("confidence")
	critique = candidate.get("critique")
	if confidence is None and isinstance(critique, dict):
		confidence = critique.get("confidence")
	return _as_display_text(confidence)


def _role_level_mismatch(candidate: dict) -> str:
	"""Render the existing overqualification assessment, if present."""
	overqualification = candidate.get("overqualification")
	if overqualification is None:
		return "Not assessed"
	if isinstance(overqualification, dict):
		flag = overqualification.get("overqualification_flag")
		if flag is None:
			flag = overqualification.get("flag")
		if flag is not None:
			return "Yes" if flag else "No"
	return _as_display_text(overqualification)


def _requirement_items(value) -> list:
	"""Return structured requirement records from common schema shapes."""
	if isinstance(value, dict):
		return [
			{"requirement": key, **item} if isinstance(item, dict) else {"requirement": key, "matched": item}
			for key, item in value.items()
		]
	if isinstance(value, (list, tuple)):
		return list(value)
	return []


def _count_structured_requirements(candidate: dict, matched: bool):
	"""Count only explicit structured match or missing indicators."""
	requirement_matches = _requirement_items(candidate.get("requirement_matches"))
	if not requirement_matches:
		return None

	count = 0
	for item in requirement_matches:
		if not isinstance(item, dict):
			return None
		item_matched = item.get("matched")
		if item_matched is None:
			item_matched = item.get("is_matched")
		if not isinstance(item_matched, bool):
			return None
		if item_matched is matched:
			count += 1
	return count


def _candidate_label(candidate: dict, index: int) -> str:
	"""Create a stable selector label without changing candidate data."""
	name = _as_display_text(candidate.get("name"), "Unnamed candidate")
	rank = candidate.get("rank")
	return f"#{rank} — {name}" if rank is not None else f"{name} — entry {index + 1}"


def _sort_candidates(candidates: list) -> list[dict]:
	"""Display valid candidate dictionaries in their supplied rank order."""
	valid_candidates = [candidate for candidate in candidates if isinstance(candidate, dict)]
	return sorted(
		valid_candidates,
		key=lambda candidate: (
			candidate.get("rank") is None,
			candidate.get("rank") if isinstance(candidate.get("rank"), (int, float)) else 0,
		),
	)


def _ranking_rows(candidates: list[dict]) -> list[dict]:
	"""Build display rows directly from candidate fields without recalculating scores."""
	rows = []
	for candidate in candidates:
		scores = candidate.get("scores")
		scores = scores if isinstance(scores, dict) else {}
		rows.append(
			{
				"Rank": _as_display_text(candidate.get("rank")),
				"Candidate": _as_display_text(candidate.get("name"), "Unnamed candidate"),
				"Final Score": _as_display_text(scores.get("final_score")),
				"Semantic Relevance": _as_display_text(scores.get("semantic")),
				"Explicit Requirement Coverage": _as_display_text(scores.get("keyword")),
				"Evidence Authenticity": _as_display_text(scores.get("evidence")),
				"Related-Skill Evidence": _as_display_text(scores.get("graph")),
				"Ranking Confidence": _candidate_confidence(candidate),
				"Required Matched": len(candidate.get("matched_required_skills", [])),
				"Required Missing": len(candidate.get("missing_required_skills", [])),
				"Role-level mismatch to review": _role_level_mismatch(candidate),
			}
		)
	return rows


def _render_evidence(requirement_matches) -> None:
	"""Show structured requirement matches and any supplied evidence."""
	requirement_rows = []
	for item in _requirement_items(requirement_matches):
		if not isinstance(item, dict):
			continue
		requirement = item.get("requirement_name") or item.get("requirement")
		if requirement is None:
			requirement = item.get("skill")
		if requirement is None:
			requirement = item.get("name")
		matched = item.get("matched")
		if matched is None:
			matched = item.get("is_matched")
		strength = item.get("evidence_strength")
		if strength is None:
			strength = item.get("strength")
		evidence = item.get("evidence_text")
		if evidence is None:
			evidence = item.get("evidence")
		if evidence is None:
			evidence = item.get("snippet")
		requirement_rows.append(
			{
				"Requirement / skill": _as_display_text(requirement),
				"Matched": _as_display_text(matched),
				"Evidence strength": _as_display_text(strength),
				"Direct evidence snippet": _as_display_text(evidence),
				"Best semantic passage (similarity only)": _as_display_text(item.get("semantic_evidence_text")),
				"Matched alternative": _as_display_text(item.get("matched_alternative")),
				"Related-skill path": " → ".join(item.get("graph_path") or []),
			}
		)

	if requirement_rows:
		st.dataframe(requirement_rows, use_container_width=True, hide_index=True)
	else:
		st.caption("Not available")


def _render_top_three_explanations(candidates: list[dict]) -> None:
	"""Render explanations from the structured explanation payload only."""
	top_three = [candidate for candidate in candidates if candidate.get("rank", 0) <= 3]
	if not top_three:
		return
	st.markdown("### Top 3 explanations")
	for candidate in top_three:
		st.markdown(f"#### #{candidate.get('rank', 'Not available')} — {_as_display_text(candidate.get('name'), 'Unnamed candidate')}")
		scores = candidate.get("scores") if isinstance(candidate.get("scores"), dict) else {}
		explanation_data = candidate.get("explanation_data") if isinstance(candidate.get("explanation_data"), dict) else {}
		strongest = explanation_data.get("strongest_matches") or []
		missing = explanation_data.get("important_missing") or candidate.get("missing_required_skills") or []
		st.write(
			f"Final score: {_as_display_text(scores.get('final_score'))}. "
			f"Semantic relevance: {_as_display_text(scores.get('semantic'))}; "
			f"explicit requirement coverage: {_as_display_text(scores.get('keyword'))}."
		)
		if strongest:
			strongest_text = []
			for item in strongest:
				if isinstance(item, dict):
					name = item.get("requirement_name", "Not available")
					strength = item.get("evidence_strength", "Not available")
					strongest_text.append(f"{name} (evidence strength: {strength})")
			st.write("Strongest matching requirements:", ", ".join(strongest_text) or "Not available")
		else:
			st.write("Strongest matching requirements: Not available")
		st.write("Important missing requirements:", _as_display_text(missing, "None identified"))
		critique = candidate.get("critique") or {}
		st.write("Ranking confidence:", _as_display_text(critique.get("confidence") if isinstance(critique, dict) else None))
		st.write("System self-critique:", _as_display_text(critique.get("summary") if isinstance(critique, dict) else None))


def render_candidate_detail(candidate: dict) -> None:
	"""Render optional candidate details defensively."""
	st.subheader(_as_display_text(candidate.get("name"), "Unnamed candidate"))
	left, right = st.columns(2)
	with left:
		st.metric("Rank", _as_display_text(candidate.get("rank")))
	with right:
		scores = candidate.get("scores")
		scores = scores if isinstance(scores, dict) else {}
		st.metric("Final score", _as_display_text(scores.get("final_score")))

	st.markdown("#### Score breakdown")
	scores = candidate.get("scores")
	scores = scores if isinstance(scores, dict) else {}
	st.dataframe(
		[
			{"Measure": "Semantic relevance", "Score": scores.get("semantic", "Not available")},
			{"Measure": "Explicit requirement coverage", "Score": scores.get("keyword", "Not available")},
			{"Measure": "Evidence authenticity", "Score": scores.get("evidence", "Not available")},
			{"Measure": "Related-skill evidence", "Score": scores.get("graph", "Not available")},
		],
		use_container_width=True,
		hide_index=True,
	)

	st.markdown("#### Requirement evidence")
	matched_requirements = candidate.get("requirement_matches")
	_render_evidence(matched_requirements)
	st.markdown("#### Missing requirements")
	st.write(_as_display_text(candidate.get("missing_required_skills") or candidate.get("missing_skills"), "None identified"))
	st.write("Missing-required penalty:", (candidate.get("score_adjustments") or {}).get("critical_missing_penalty", 0))

	optional_details = [
		("Parse quality", candidate.get("parse_quality")),
		("Ranking confidence", _candidate_confidence(candidate)),
		("Self-critique", candidate.get("critique")),
		("Role-level mismatch to review", _role_level_mismatch(candidate)),
	]
	for label, value in optional_details:
		st.markdown(f"#### {label}")
		st.write(_as_display_text(value))

	st.markdown("#### Interview verification questions")
	probes = candidate.get("interview_probes")
	if isinstance(probes, list) and probes:
		for probe in probes[:5]:
			st.write(f"- {probe}")
	else:
		st.caption("Not available")

	st.markdown("#### Counterfactual")
	counterfactual = candidate.get("counterfactual")
	if counterfactual:
		st.caption("Simulation — not a hiring guarantee")
		st.write(_as_display_text(counterfactual))
	else:
		st.caption("Not available")

	st.markdown("#### Alternative role direction")
	st.write(_as_display_text(candidate.get("alternative_role")))

	if 0 < candidate.get("rank", 0) <= 3:
		return
	st.markdown("#### Recruiter-review rejection draft")
	jd = st.session_state.get("parsed_jd") or {}
	st.text_area(
		"Draft",
		generate_rejection_draft(candidate, jd),
		height=220,
		label_visibility="collapsed",
	)


def render_ranking_tab() -> None:
	"""Render supplied ranked candidates without modifying their ranking."""
	ranked_candidates = st.session_state.get("ranked_candidates", [])
	if not isinstance(ranked_candidates, list) or not ranked_candidates:
		render_empty_state(
			"Ranked candidates will appear here after the analysis pipeline is connected."
		)
		return

	candidates = _sort_candidates(ranked_candidates)
	if not candidates:
		render_empty_state("Ranked candidates will appear here after the analysis pipeline is connected.")
		return

	st.dataframe(_ranking_rows(candidates), use_container_width=True, hide_index=True)
	st.download_button("Download full results (JSON)", json.dumps({"jd": st.session_state.get("parsed_jd"), "ranked_candidates": candidates, "team": st.session_state.get("team_result")}, indent=2, allow_nan=False), file_name="internloom_results.json", mime="application/json")
	labels = [_candidate_label(candidate, index) for index, candidate in enumerate(candidates)]
	selected_label = st.selectbox("Select a candidate for details", labels)
	selected_index = labels.index(selected_label)
	selected_candidate = candidates[selected_index]
	st.session_state["selected_candidates"] = [selected_candidate]
	st.markdown("### Candidate details")
	render_candidate_detail(selected_candidate)


def render_compare_tab() -> None:
	candidates = st.session_state.get("ranked_candidates", [])
	if len(candidates) < 2:
		render_empty_state("Candidate comparisons will appear here after at least two candidates are ranked.")
		return
	from src.compare import compare_candidates

	labels = [_candidate_label(candidate, index) for index, candidate in enumerate(candidates)]
	left, right = st.columns(2)
	with left:
		label_a = st.selectbox("Candidate A", labels, key="compare_candidate_a")
	with right:
		label_b = st.selectbox("Candidate B", labels, index=1, key="compare_candidate_b")
	if label_a == label_b:
		st.warning("Select two different candidates to compare.")
		return
	a = candidates[labels.index(label_a)]
	b = candidates[labels.index(label_b)]
	comparison = compare_candidates(a, b, st.session_state.get("parsed_jd") or {})
	st.info(comparison.get("explanation", "Not available"))
	st.dataframe(
		[
			{"Measure": "Final score difference (A - B)", "Value": _as_display_text(comparison.get("score_difference"))},
			{"Measure": "Semantic difference (A - B)", "Value": _as_display_text(comparison.get("semantic_difference"))},
			{"Measure": "Keyword difference (A - B)", "Value": _as_display_text(comparison.get("keyword_difference"))},
			{"Measure": "Evidence difference (A - B)", "Value": _as_display_text(comparison.get("evidence_difference"))},
			{"Measure": "A unique matches", "Value": _as_display_text(comparison.get("a_unique_matches"))},
			{"Measure": "B unique matches", "Value": _as_display_text(comparison.get("b_unique_matches"))},
			{"Measure": "A missing requirements", "Value": _as_display_text(comparison.get("a_missing"))},
			{"Measure": "B missing requirements", "Value": _as_display_text(comparison.get("b_missing"))},
		],
		use_container_width=True,
		hide_index=True,
	)


def render_team_mode_tab() -> None:
	team_result = st.session_state.get("team_result")
	if not team_result:
		render_empty_state("Team recommendations will appear here after analysis is complete.")
		return
	st.subheader("Best Complementary 3-Person Team")
	st.write(", ".join(team_result.get("member_names") or []) or team_result.get("note", "Not available"))
	st.dataframe(
		[
			{"Measure": "Required skill coverage", "Value": _as_display_text(team_result.get("required_skill_coverage"))},
			{"Measure": "Required evidence coverage", "Value": _as_display_text(team_result.get("evidence_score"))},
			{"Measure": "Average semantic relevance", "Value": _as_display_text(team_result.get("semantic_score"))},
			{"Measure": "Team score", "Value": _as_display_text(team_result.get("team_score"))},
		],
		use_container_width=True,
		hide_index=True,
	)
	st.write("Unique contributions by member:", _as_display_text(team_result.get("member_contributions")))
	st.write("Remaining gaps:", _as_display_text(team_result.get("remaining_gaps")))


def render_jd_review_tab() -> None:
	jd = st.session_state.get("parsed_jd") or {}
	if not jd:
		render_empty_state("Job description insights will appear here after analysis is complete.")
		return
	st.subheader("Potentially narrow phrasing")
	flags = jd.get("bias_flags") or []
	if not flags:
		st.success("No potentially narrow phrasing was detected by the configured rules.")
		return
	st.dataframe(flags, use_container_width=True, hide_index=True)


def _uploaded_file_to_temp(uploaded_file) -> str:
	"""Write an upload to a temporary PDF path for the existing path-based parser."""
	suffix = PurePath(uploaded_file.name).suffix.lower() or ".pdf"
	with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
		handle.write(uploaded_file.getvalue())
		return handle.name


@st.cache_resource(show_spinner=False)
def _load_local_semantic_model():
	return get_semantic_model()


def run_analysis(jd_file, resume_files) -> tuple[list[dict], dict, dict]:
	"""Run the existing local pipeline and add trust-layer enrichments."""
	temporary_paths = []
	try:
		jd_path = _uploaded_file_to_temp(jd_file)
		temporary_paths.append(jd_path)
		jd_parsed = __import__("src.pdf_parser", fromlist=["parse_pdf_with_metadata"]).parse_pdf_with_metadata(jd_path)
		jd_text = str(jd_parsed.get("text", ""))
		requirements = extract_requirements(jd_text)
		if not jd_text.strip() or not requirements:
			raise ValueError("The JD has no readable, recognized requirements. Use a text-based PDF containing the role's skills.")
		jd = {
			"title": jd_text.splitlines()[0].strip() if jd_text.splitlines() else "Job description",
			"raw_text": str(jd_parsed.get("raw_text", "")),
			"clean_text": jd_text,
			"requirements": requirements,
			"role_level": detect_role_level(jd_text),
			"bias_flags": detect_jd_bias(jd_text),
		}
		model = _load_local_semantic_model()
		candidates = []
		for index, resume_file in enumerate(resume_files):
			resume_path = _uploaded_file_to_temp(resume_file)
			temporary_paths.append(resume_path)
			cid = f"C{index + 1:03d}_" + hashlib.sha256(resume_file.getvalue()).hexdigest()[:8]
			candidate = parse_candidate_from_pdf(resume_path, candidate_id=cid, source_name=resume_file.name)
			candidates.append(candidate)
		ranked, team_result = run_trust_layer(jd, candidates, model=model)
		for candidate in ranked:
			route_alternative_role(candidate)
		return ranked, jd, team_result
	finally:
		for path in temporary_paths:
			try:
				os.unlink(path)
			except OSError:
				pass


def render_input_panel() -> tuple[object, list[object], bool]:
	"""Render file inputs and return the selected files plus the analyze action."""
	with st.sidebar:
		st.header("Analysis inputs")
		jd_file = st.file_uploader(
			"Job description PDF",
			type=["pdf"],
			accept_multiple_files=False,
			help="Upload the job description you want to use for shortlisting.",
		)
		resume_files = st.file_uploader(
			"Resume PDFs",
			type=["pdf"],
			accept_multiple_files=True,
			help="Upload one or more candidate resumes.",
		)
		analyze_clicked = st.button("Analyze Candidates", type="primary", use_container_width=True)
		st.caption("No organizer files yet? The bundled demo uses 54 sample resumes and a synthetic JD based on the agreed requirements.")
		if st.button("Run bundled sample demo"):
			root = Path(__file__).resolve().parent
			class LocalUpload:
				type = "application/pdf"
				def __init__(self, path):
					self.path, self.name = path, path.name
				def getvalue(self):
					return self.path.read_bytes()
			jd_file = LocalUpload(root / "data/jd/Synthetic_Demo_JD.pdf")
			resume_files = [LocalUpload(path) for path in sorted((root / "data/resumes").glob("*.pdf"))]
			analyze_clicked = True

	return jd_file, resume_files, analyze_clicked


def main() -> None:
	st.set_page_config(page_title="InternLoom AI", page_icon="📄", layout="wide")
	initialize_session_state()

	st.title("InternLoom AI")
	st.subheader("Explainable Smart Shortlisting Engine")
	st.success("100% Local Processing — No External APIs")

	jd_file, resume_files, analyze_clicked = render_input_panel()

	if analyze_clicked:
		for key in STATE_DEFAULTS:
			default = STATE_DEFAULTS[key]
			st.session_state[key] = default.copy() if isinstance(default, list) else default
		validation_errors = validate_uploads(jd_file, resume_files)
		if validation_errors:
			for error in validation_errors:
				st.error(error)
		else:
			if len(resume_files) == 1:
				st.warning("Only one resume is uploaded. The shortlist will contain one candidate.")
			try:
				with st.status("Analyzing candidates locally...", expanded=True) as status:
					st.write("Parsing the job description and resumes")
					ranked, parsed_jd, team_result = run_analysis(jd_file, resume_files)
					st.session_state["parsed_jd"] = parsed_jd
					st.session_state["ranked_candidates"] = ranked
					st.session_state["team_result"] = team_result
					st.session_state["selected_candidates"] = []
					unreadable = [c["file_name"] for c in ranked if not c["clean_text"].strip()]
					if unreadable:
						st.warning("No readable text in these resumes; their scores are not a reliable assessment: " + ", ".join(unreadable))
					status.update(label="Analysis complete", state="complete")
			except Exception as error:
				st.error(f"Analysis could not be completed: {error}")

	ranking_tab, compare_tab, team_tab, jd_review_tab = st.tabs(
		["Ranking", "Compare", "Team Mode", "JD Review"]
	)

	with ranking_tab:
		render_ranking_tab()
		_render_top_three_explanations(st.session_state.get("ranked_candidates", []))
	with compare_tab:
		render_compare_tab()
	with team_tab:
		render_team_mode_tab()
	with jd_review_tab:
		render_jd_review_tab()


if __name__ == "__main__":
	main()
