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


def render_ranking_tab() -> None:
	"""Render the ranking workspace without manufacturing candidate results."""
	if st.session_state["ranked_candidates"]:
		st.info("Ranked candidates will appear here when the analysis pipeline is connected.")
	else:
		render_empty_state(
			"Ranked candidates will appear here after the analysis pipeline is connected."
		)


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
