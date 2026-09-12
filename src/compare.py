"""Deterministic recruiter comparison helper for ranked candidates.

This module compares existing candidate data without changing the ranking or
calculating any new candidate scores.
"""


def _numeric_score(scores: object, key: str):
	"""Return a numeric score value, or None when it is unavailable."""
	if not isinstance(scores, dict):
		return None
	value = scores.get(key)
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return None
	return value


def _score_difference(a: dict, b: dict, key: str):
	"""Calculate A minus B when both source scores are numeric."""
	a_score = _numeric_score(a.get("scores"), key)
	b_score = _numeric_score(b.get("scores"), key)
	if a_score is None or b_score is None:
		return None
	return a_score - b_score


def _requirement_records(value) -> list[dict]:
	"""Normalize supported requirement-match shapes into records."""
	if isinstance(value, dict):
		records = []
		for requirement, details in value.items():
			if isinstance(details, dict):
				record = dict(details)
				record.setdefault("requirement", requirement)
				records.append(record)
			else:
				records.append({"requirement": requirement, "matched": details})
		return records
	if isinstance(value, list):
		return [record for record in value if isinstance(record, dict)]
	return []


def _requirement_name(record: dict):
	"""Return the supplied requirement name using the shared field priority."""
	for key in ("requirement", "skill", "name"):
		value = record.get(key)
		if value is not None and value != "":
			return value
	return None


def _requirement_key(name) -> str | None:
	"""Create a stable comparison key without changing the returned name."""
	if name is None:
		return None
	return " ".join(str(name).split()).casefold()


def _explicit_requirements(candidate: dict) -> tuple[dict[str, object], dict[str, object]]:
	"""Collect explicitly true and false requirements from one candidate."""
	matched = {}
	missing = {}
	for record in _requirement_records(candidate.get("requirement_matches")):
		name = _requirement_name(record)
		key = _requirement_key(name)
		if key is None:
			continue
		status = record.get("matched")
		if status is None:
			status = record.get("is_matched")
		if status is True:
			matched.setdefault(key, name)
		elif status is False:
			missing.setdefault(key, name)
	return matched, missing


def _unique_names(first: dict[str, object], second: dict[str, object]) -> list:
	"""Return names present in the first map but explicitly matched by neither second map."""
	return [name for key, name in first.items() if key not in second]


def _candidate_name(candidate: dict, fallback: str) -> str:
	name = candidate.get("name")
	return str(name) if name is not None and name != "" else fallback


def _format_difference(value) -> str:
	if value is None:
		return "Not available"
	return f"{value:g}"


def _comparison_explanation(
	a: dict,
	b: dict,
	score_difference,
	a_unique_matches: list,
	b_unique_matches: list,
) -> str:
	"""Build a concise explanation from supplied comparison values."""
	a_name = _candidate_name(a, "Candidate A")
	b_name = _candidate_name(b, "Candidate B")
	if score_difference is None:
		summary = f"Final score difference between {a_name} and {b_name}: Not available."
	elif score_difference == 0:
		summary = f"{a_name} and {b_name} have the same final score."
	else:
		leading_name = a_name if score_difference > 0 else b_name
		summary = (
			f"{leading_name} has the higher supplied final score by "
			f"{_format_difference(abs(score_difference))}."
		)

	details = []
	if a_unique_matches:
		details.append(f"{a_name} uniquely matches: {', '.join(map(str, a_unique_matches))}.")
	if b_unique_matches:
		details.append(f"{b_name} uniquely matches: {', '.join(map(str, b_unique_matches))}.")
	return " ".join([summary, *details])


def compare_candidates(a: dict, b: dict, jd: dict) -> dict:
	"""Compare two existing candidates without altering ranking data.

	The JD argument is accepted for compatibility with the application and is
	not required for this deterministic candidate-to-candidate comparison.
	"""
	if not isinstance(a, dict):
		a = {}
	if not isinstance(b, dict):
		b = {}
	_a_matches, _a_missing = _explicit_requirements(a)
	_b_matches, _b_missing = _explicit_requirements(b)

	a_unique_matches = _unique_names(_a_matches, _b_matches)
	b_unique_matches = _unique_names(_b_matches, _a_matches)
	return {
		"score_difference": _score_difference(a, b, "final_score"),
		"semantic_difference": _score_difference(a, b, "semantic"),
		"keyword_difference": _score_difference(a, b, "keyword"),
		"evidence_difference": _score_difference(a, b, "evidence"),
		"a_unique_matches": a_unique_matches,
		"b_unique_matches": b_unique_matches,
		"a_missing": list(_a_missing.values()),
		"b_missing": list(_b_missing.values()),
		"explanation": _comparison_explanation(
			a,
			b,
			_score_difference(a, b, "final_score"),
			a_unique_matches,
			b_unique_matches,
		),
	}
