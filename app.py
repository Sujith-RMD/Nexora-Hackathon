"""Recruiter-facing Streamlit shell for InternLoom AI.

Pipeline integration (branch merge): the Analyze action calls
``src.analysis_runner.analyze_uploads``, which runs Teammate 1's core matching
and Teammate 2's trust layer and returns the shared-schema payload consumed by
the tabs below. This file holds presentation logic only — no scoring,
matching, or PDF parsing lives here.
"""

from pathlib import Path, PurePath

import streamlit as st

from src.analysis_runner import AnalysisError, STAGES, analyze_uploads
from src.semantic_matcher import get_semantic_model

BUNDLED_JD = "data/jd/Sample_JD.pdf"
BUNDLED_RESUMES = [
    "data/resumes/web_dev__aditya_kulkarni.pdf",
    "data/resumes/web_dev__priya_nair.pdf",
    "data/resumes/sde__arjun_desai.pdf",
    "data/resumes/ai_dev__rohan_mehta.pdf",
    "data/resumes/python_dev__karan_verma.pdf",
]
_APP_ROOT = Path(__file__).resolve().parent


def _resolve_bundled(rel_path: str) -> Path:
	"""Bundled demo assets resolve against the repo root, not the CWD."""
	return rel_path if Path(rel_path).is_absolute() else _APP_ROOT / rel_path


STATE_DEFAULTS = {
	"parsed_jd": None,
	"ranked_candidates": [],
	"team_result": None,
	"selected_candidates": [],
	"analysis_source": None,
	"last_error": None,
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
	"""Show structured requirement matches and any supplied evidence."""
	requirement_rows = []
	for item in _requirement_items(requirement_matches):
		if not isinstance(item, dict):
			continue
		requirement = item.get("requirement_name")
		if requirement is None:
			requirement = item.get("requirement")
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
		if item.get("graph_match") and item.get("graph_path"):
			path_text = " → ".join(str(step) for step in item["graph_path"])
			graph_note = f"related via {path_text} ({item.get('graph_score', 0)}%)"
		elif item.get("graph_match"):
			graph_note = "graph-supported"
		else:
			graph_note = "—"
		requirement_rows.append(
			{
				"Requirement / skill": _as_display_text(requirement),
				"Matched": _as_display_text(matched),
				"Evidence strength": _as_display_text(strength),
				"Evidence snippet": _as_display_text(evidence),
				"Skill-graph support": graph_note,
			}
		)

	if requirement_rows:
		st.dataframe(requirement_rows, use_container_width=True, hide_index=True)
	else:
		st.caption("Not available")


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
	missing = candidate.get("missing_required_skills")
	if missing is None:
		missing = candidate.get("missing_skills")
	st.write(_as_display_text(missing))

	critique = candidate.get("critique")
	st.markdown("#### Ranking confidence & self-critique")
	if isinstance(critique, dict):
		confidence = _candidate_confidence(candidate)
		badge = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(
			str(critique.get("confidence", "")).lower(), "⚪"
		)
		st.markdown(f"{badge} **Confidence: {confidence}**")
		st.caption(critique.get("summary") or "No summary supplied.")
		flags = critique.get("flags") or []
		if flags:
			for flag in flags:
				st.markdown(f"- {flag}")
		if critique.get("human_review_recommended"):
			st.warning("Human review recommended before finalizing this position.")
	else:
		st.caption("Not available")

	counterfactual = candidate.get("counterfactual")
	st.markdown("#### How this candidate could move up (coaching)")
	if isinstance(counterfactual, dict):
		st.write(counterfactual.get("message") or "")
		improvements = counterfactual.get("suggested_improvements") or []
		if improvements:
			st.dataframe(
				[
					{
						"Requirement": imp.get("requirement"),
						"Suggested change": imp.get("change"),
						"Type": imp.get("kind"),
						"Projected score gain": imp.get("estimated_gain"),
					}
					for imp in improvements
					if isinstance(imp, dict)
				],
				use_container_width=True,
				hide_index=True,
			)
		if counterfactual.get("disclaimer"):
			st.caption(counterfactual["disclaimer"])
	else:
		st.caption("Not available")

	probes = candidate.get("interview_probes") or []
	st.markdown("#### Suggested interview probes")
	if probes:
		for probe in probes:
			st.markdown(f"- ❓ {probe}")
	else:
		st.caption("No probes generated.")

	optional_details = [
		("Parse quality", candidate.get("parse_quality")),
		("Role-level mismatch", _role_level_mismatch(candidate)),
	]
	for label, value in optional_details:
		st.markdown(f"#### {label}")
		st.write(_as_display_text(value))
	overqualification = candidate.get("overqualification")
	if isinstance(overqualification, dict) and overqualification.get("reasons"):
		for reason in overqualification["reasons"]:
			st.caption(f"• {reason}")


def render_ranking_tab() -> None:
	"""Render supplied ranked candidates without modifying their ranking."""
	ranked_candidates = st.session_state.get("ranked_candidates", [])
	if not isinstance(ranked_candidates, list) or not ranked_candidates:
		render_empty_state(
			"No results yet. Choose a data source in the sidebar and click "
			"“Analyze Candidates”."
		)
		return

	candidates = _sort_candidates(ranked_candidates)
	if not candidates:
		render_empty_state("No valid candidate records were produced by the analysis.")
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
	"""Side-by-side comparison of two ranked candidates (read-only view)."""
	candidates = _sort_candidates(st.session_state.get("ranked_candidates", []))
	if len(candidates) < 2:
		render_empty_state("Analyze at least two candidates to compare them side by side.")
		return

	labels = [_candidate_label(candidate, index) for index, candidate in enumerate(candidates)]
	left_choice = st.selectbox("Candidate A", labels, index=0)
	right_choice = st.selectbox("Candidate B", labels, index=min(1, len(labels) - 1))
	cand_a = candidates[labels.index(left_choice)]
	cand_b = candidates[labels.index(right_choice)]

	def _sc(candidate, key):
		scores = candidate.get("scores") or {}
		return scores.get(key, "—")

	metric_rows = [
		{"Measure": "Final score", "A": _sc(cand_a, "final_score"), "B": _sc(cand_b, "final_score")},
		{"Measure": "Semantic relevance", "A": _sc(cand_a, "semantic"), "B": _sc(cand_b, "semantic")},
		{"Measure": "Requirement coverage", "A": _sc(cand_a, "keyword"), "B": _sc(cand_b, "keyword")},
		{"Measure": "Evidence authenticity", "A": _sc(cand_a, "evidence"), "B": _sc(cand_b, "evidence")},
		{"Measure": "Related-skill evidence", "A": _sc(cand_a, "graph"), "B": _sc(cand_b, "graph")},
		{"Measure": "Ranking confidence", "A": _candidate_confidence(cand_a), "B": _candidate_confidence(cand_b)},
		{"Measure": "Role-level mismatch", "A": _role_level_mismatch(cand_a), "B": _role_level_mismatch(cand_b)},
	]
	st.markdown("#### Head-to-head scores")
	st.dataframe(metric_rows, use_container_width=True, hide_index=True)

	st.markdown("#### Requirement match matrix")
	by_req: dict[str, dict] = {}
	for cand, side in ((cand_a, "A"), (cand_b, "B")):
		for item in _requirement_items(cand.get("requirement_matches")):
			if not isinstance(item, dict):
				continue
			name = item.get("requirement_name") or item.get("requirement") or item.get("name")
			if name is None:
				continue
			cell = by_req.setdefault(str(name), {"Requirement": str(name)})
			if item.get("graph_match") and item.get("graph_path"):
				cell[side] = f"related ({item.get('graph_score', 0)}%)"
			else:
				cell[side] = "matched" if item.get("matched") else "missing"
	if by_req:
		st.dataframe(list(by_req.values()), use_container_width=True, hide_index=True)

	for column, cand in zip(st.columns(2), (cand_a, cand_b)):
		with column:
			st.markdown("#### Suggested interview probes")
			for probe in (cand.get("interview_probes") or ["None generated."]):
				st.markdown(f"- ❓ {probe}")


def render_team_mode_tab() -> None:
	"""Render the balanced 3-person team recommendation (Teammate 2 team mode)."""
	team = st.session_state.get("team_result")
	if not isinstance(team, dict):
		render_empty_state("Run an analysis to see the recommended balanced team.")
		return

	candidates = {c.get("candidate_id"): c for c in st.session_state.get("ranked_candidates", [])}
	members = team.get("members") or []
	if not members:
		st.warning(team.get("note") or "Not enough candidates to form a team.")
		return

	head1, head2, head3 = st.columns(3)
	head1.metric("Team score", _as_display_text(team.get("team_score")))
	head2.metric("Required coverage", f"{team.get('required_skill_coverage', 0)}%")
	head3.metric("Teams evaluated", _as_display_text(team.get("teams_evaluated")))

	st.markdown("#### Recommended team")
	contributions = team.get("member_contributions") or {}
	rows = []
	for member_id in members:
		cand = candidates.get(member_id, {})
		contrib = contributions.get(member_id, [])
		if isinstance(contrib, dict):
			contrib = list(contrib.keys())
		rows.append({
			"Candidate": _as_display_text(cand.get("name"), member_id),
			"Individual rank": _as_display_text(cand.get("rank")),
			"Primary skills covered": _as_display_text(contrib, "—"),
		})
	st.dataframe(rows, use_container_width=True, hide_index=True)

	gaps = team.get("remaining_gaps") or []
	if gaps:
		st.warning("Still missing across the whole team: " + ", ".join(str(g) for g in gaps))
	else:
		st.success("The recommended team collectively covers every required skill.")

	runner_ups = team.get("runner_up_teams") or []
	if runner_ups:
		with st.expander("Runner-up team combinations"):
			for alt in runner_ups[:3]:
				names = alt.get("members") if isinstance(alt, dict) else alt
				score = alt.get("team_score") if isinstance(alt, dict) else None
				st.write(f"{_as_display_text(names, 'team')} — score {_as_display_text(score)}")


def render_jd_review_tab() -> None:
	"""Explain what the engine understood from the JD + phrasing hints."""
	jd = st.session_state.get("parsed_jd")
	if not isinstance(jd, dict):
		render_empty_state("Analyze a job description to review its extracted requirements.")
		return

	st.markdown("#### Understood requirements")
	requirement_rows = [
		{
			"Skill": _as_display_text(r.get("display_name") or r.get("name")),
			"Importance": _as_display_text(r.get("importance")),
			"Weight": _as_display_text(r.get("weight")),
		}
		for r in (jd.get("requirements") or [])
		if isinstance(r, dict)
	]
	if requirement_rows:
		st.dataframe(requirement_rows, use_container_width=True, hide_index=True)
	st.caption(f"Detected role level: **{_as_display_text(jd.get('role_level'))}**")

	st.markdown("#### Phrasing hints")
	bias_flags = jd.get("bias_flags") or []
	if bias_flags:
		for flag in bias_flags:
			if isinstance(flag, dict):
				st.markdown(
					f"- **“{flag.get('phrase')}”** — {flag.get('reason')} "
					f"*Suggestion: {flag.get('suggestion')}*"
				)
	else:
		st.success("No risky phrasing detected in this job description.")

	warnings = st.session_state.get("jd_warnings") or []
	if warnings:
		with st.expander("Parser warnings"):
			for warning in warnings:
				st.write(f"• {warning}")


def render_input_panel() -> tuple[str, object, list[object], bool]:
	"""Render data-source choice, file inputs, and return the analyze action.

	Returns ``(mode, jd_file, resume_files, analyze_clicked)`` where mode is
	``"sample"`` or ``"upload"``.
	"""
	with st.sidebar:
		st.header("Analysis inputs")
		mode = st.radio(
			"Data source",
			options=["upload", "sample"],
			format_func=lambda m: "Upload my own PDFs" if m == "upload" else "Use bundled sample batch",
			help="Sample runs the repo's demo JD + five resumes with zero uploading.",
		)
		if mode == "upload":
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
		else:
			jd_file, resume_files = None, []
			st.caption(f"Demo JD + {len(BUNDLED_RESUMES)} bundled resumes from data/resumes/.")
		analyze_clicked = st.button("Analyze Candidates", type="primary", use_container_width=True)

	return mode, jd_file, resume_files, analyze_clicked


def _load_bundled_batch() -> tuple[bytes, str, list[tuple[bytes, str]]]:
	"""Read the demo JD + resumes from disk (bundled with the repo)."""
	jd_path = _resolve_bundled(BUNDLED_JD)
	jd_bytes = jd_path.read_bytes()
	resumes: list[tuple[bytes, str]] = []
	for rel in BUNDLED_RESUMES:
		path = _resolve_bundled(rel)
		if path.exists():
			resumes.append((path.read_bytes(), path.name))
	return jd_bytes, jd_path.name, resumes


def run_analysis(mode: str, jd_file, resume_files) -> None:
	"""Execute the full pipeline and store results in session state."""
	st.session_state["last_error"] = None
	try:
		if mode == "sample":
			jd_bytes, jd_name, resumes = _load_bundled_batch()
			if not resumes:
				raise AnalysisError("Bundled sample resumes were not found on disk.")
		else:
			jd_bytes, jd_name = jd_file.getvalue(), jd_file.name
			resumes = [(f.getvalue(), f.name) for f in resume_files]

		progress = st.progress(0.0, text="Preparing…")

		def on_stage(label: str) -> None:
			try:
				idx = STAGES.index(label.split(" (")[0]) + 1
			except ValueError:
				idx = min(progress.value + 0.1, 1.0)
			progress.progress(min(idx / len(STAGES), 1.0), text=label)

		payload = analyze_uploads(jd_bytes, jd_name, resumes, on_stage=on_stage,
		                         model=get_semantic_model())
		progress.empty()

		st.session_state["parsed_jd"] = payload["jd"]
		st.session_state["ranked_candidates"] = payload["ranked_candidates"]
		st.session_state["team_result"] = payload["team_result"]
		st.session_state["jd_warnings"] = payload["jd_warnings"]
		st.session_state["analysis_source"] = mode
		st.success(
			f"Analysis complete — {len(payload['ranked_candidates'])} candidates ranked locally. "
			"Nothing left this machine."
		)
	except AnalysisError as exc:
		st.session_state["last_error"] = str(exc)
		st.error(str(exc))
	except Exception as exc:  # pragma: no cover - defensive UI guard
		st.session_state["last_error"] = str(exc)
		st.error("Analysis failed to complete. Check that every PDF contains real text.")


def main() -> None:
	st.set_page_config(page_title="InternLoom AI", page_icon="📄", layout="wide")
	initialize_session_state()

	st.title("InternLoom AI")
	st.subheader("Explainable Smart Shortlisting Engine")
	st.success("100% Local Processing — No External APIs")

	mode, jd_file, resume_files, analyze_clicked = render_input_panel()

	if analyze_clicked:
		if mode == "upload":
			validation_errors = validate_uploads(jd_file, resume_files)
			if validation_errors:
				for error in validation_errors:
					st.error(error)
			elif len(resume_files) == 1:
				st.warning(
					"Only one resume is uploaded. Add more resumes for a meaningful shortlist comparison."
				)
			else:
				run_analysis(mode, jd_file, resume_files)
		else:
			run_analysis(mode, jd_file, resume_files)

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
