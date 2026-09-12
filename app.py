"""Recruiter-facing Streamlit shell for InternLoom AI.

The parsing and ranking pipeline will be connected here once the shared
pipeline modules are available. This file intentionally contains no scoring,
matching, or PDF parsing logic.
"""

from pathlib import PurePath

import streamlit as st


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
				"Required Matched": _as_display_text(_count_structured_requirements(candidate, True)),
				"Required Missing": _as_display_text(_count_structured_requirements(candidate, False)),
				"Role-level mismatch": _role_level_mismatch(candidate),
			}
		)
	return rows


def _render_evidence(requirement_matches) -> None:
	"""Show available evidence snippets without creating or inferring evidence."""
	evidence_rows = []
	for item in _requirement_items(requirement_matches):
		if not isinstance(item, dict):
			continue
		evidence = item.get("evidence_text") or item.get("evidence") or item.get("snippet")
		if evidence:
			requirement = item.get("requirement") or item.get("skill") or "Requirement"
			evidence_rows.append({"Requirement": requirement, "Evidence": evidence})

	if evidence_rows:
		st.dataframe(evidence_rows, use_container_width=True, hide_index=True)
	else:
		st.caption("Evidence not available.")


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

	st.markdown("#### Matched requirements")
	matched_requirements = candidate.get("requirement_matches") or candidate.get("matched_skills")
	st.write(_as_display_text(matched_requirements))
	st.markdown("#### Evidence snippets")
	_render_evidence(candidate.get("requirement_matches"))
	st.markdown("#### Missing requirements")
	st.write(_as_display_text(candidate.get("missing_skills")))

	optional_details = [
		("Parse quality", candidate.get("parse_quality")),
		("Ranking confidence", _candidate_confidence(candidate)),
		("Self-critique", candidate.get("critique")),
		("Role-level mismatch", _role_level_mismatch(candidate)),
	]
	for label, value in optional_details:
		st.markdown(f"#### {label}")
		st.write(_as_display_text(value))


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
	labels = [_candidate_label(candidate, index) for index, candidate in enumerate(candidates)]
	selected_label = st.selectbox("Select a candidate for details", labels)
	selected_index = labels.index(selected_label)
	selected_candidate = candidates[selected_index]
	st.session_state["selected_candidates"] = [selected_candidate]
	st.markdown("### Candidate details")
	render_candidate_detail(selected_candidate)


def render_compare_tab() -> None:
	render_empty_state("Candidate comparisons will appear here after ranking is available.")


def render_team_mode_tab() -> None:
	render_empty_state("Team recommendations will appear here after team analysis is connected.")


def render_jd_review_tab() -> None:
	render_empty_state("Job description insights will appear here after JD analysis is connected.")


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

	return jd_file, resume_files, analyze_clicked


def main() -> None:
	st.set_page_config(page_title="InternLoom AI", page_icon="📄", layout="wide")
	initialize_session_state()

	st.title("InternLoom AI")
	st.subheader("Explainable Smart Shortlisting Engine")
	st.success("100% Local Processing — No External APIs")

	jd_file, resume_files, analyze_clicked = render_input_panel()

	if analyze_clicked:
		validation_errors = validate_uploads(jd_file, resume_files)
		if validation_errors:
			for error in validation_errors:
				st.error(error)
		elif len(resume_files) == 1:
			st.warning(
				"Only one resume is uploaded. Add more resumes for a meaningful shortlist comparison."
			)
		else:
			st.info(
				"The analysis pipeline is not connected yet. Your uploaded files are ready for integration."
			)

	ranking_tab, compare_tab, team_tab, jd_review_tab = st.tabs(
		["Ranking", "Compare", "Team Mode", "JD Review"]
	)

	with ranking_tab:
		render_ranking_tab()
	with compare_tab:
		render_compare_tab()
	with team_tab:
		render_team_mode_tab()
	with jd_review_tab:
		render_jd_review_tab()


if __name__ == "__main__":
	main()
