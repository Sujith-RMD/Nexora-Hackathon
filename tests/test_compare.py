import copy
import unittest

from src.compare import compare_candidates


class CompareCandidatesTests(unittest.TestCase):
	def candidate(self, name="Candidate"):
		return {
			"name": name,
			"scores": {
				"final_score": 80,
				"semantic": 70,
				"keyword": 60,
				"evidence": 50,
			},
			"requirement_matches": [],
		}

	def test_required_output_keys_exist(self):
		result = compare_candidates(self.candidate("A"), self.candidate("B"), {})

		self.assertEqual(
			set(result),
			{
				"score_difference",
				"semantic_difference",
				"keyword_difference",
				"evidence_difference",
				"a_unique_matches",
				"b_unique_matches",
				"a_missing",
				"b_missing",
				"explanation",
			},
		)

	def test_numeric_differences_are_a_minus_b(self):
		a = self.candidate("A")
		b = self.candidate("B")
		b["scores"] = {
			"final_score": 75,
			"semantic": 80,
			"keyword": 55,
			"evidence": 65,
		}

		result = compare_candidates(a, b, {})

		self.assertEqual(result["score_difference"], 5)
		self.assertEqual(result["semantic_difference"], -10)
		self.assertEqual(result["keyword_difference"], 5)
		self.assertEqual(result["evidence_difference"], -15)

	def test_missing_and_non_numeric_scores_return_none(self):
		a = self.candidate("A")
		b = self.candidate("B")
		del a["scores"]["semantic"]
		b["scores"]["keyword"] = "not-a-score"

		result = compare_candidates(a, b, {})

		self.assertIsNone(result["semantic_difference"])
		self.assertIsNone(result["keyword_difference"])
		self.assertIsNone(compare_candidates({}, {}, {})["score_difference"])

	def test_list_requirement_matches_and_unique_missing_requirements(self):
		a = self.candidate("A")
		b = self.candidate("B")
		a["requirement_matches"] = [
			{"requirement": "Python", "matched": True},
			{"skill": "SQL", "is_matched": False},
			{"name": "Docker", "matched": True},
		]
		b["requirement_matches"] = [
			{"requirement": "Python", "matched": True},
			{"skill": "SQL", "matched": True},
			{"name": "Cloud", "matched": False},
		]

		result = compare_candidates(a, b, {})

		self.assertEqual(result["a_unique_matches"], ["Docker"])
		self.assertEqual(result["b_unique_matches"], ["SQL"])
		self.assertEqual(result["a_missing"], ["SQL"])
		self.assertEqual(result["b_missing"], ["Cloud"])

	def test_dictionary_keyed_requirement_matches(self):
		a = self.candidate("A")
		b = self.candidate("B")
		a["requirement_matches"] = {
			"Python": {"matched": True},
			"SQL": {"matched": False},
		}
		b["requirement_matches"] = {
			"Python": {"matched": False},
			"Java": {"is_matched": True},
		}

		result = compare_candidates(a, b, {})

		self.assertEqual(result["a_unique_matches"], ["Python"])
		self.assertEqual(result["b_unique_matches"], ["Java"])
		self.assertEqual(result["a_missing"], ["SQL"])
		self.assertEqual(result["b_missing"], ["Python"])

	def test_only_literal_boolean_statuses_count(self):
		a = self.candidate("A")
		a["requirement_matches"] = [
			{"requirement": "TrueValue", "matched": True},
			{"requirement": "FalseValue", "matched": False},
			{"requirement": "One", "matched": 1},
			{"requirement": "Zero", "matched": 0},
			{"requirement": "TextTrue", "matched": "True"},
			{"requirement": "GraphOnly", "graph_match": True},
		]

		result = compare_candidates(a, self.candidate("B"), {})

		self.assertEqual(result["a_unique_matches"], ["TrueValue"])
		self.assertEqual(result["a_missing"], ["FalseValue"])

	def test_detected_skills_are_not_requirement_matches(self):
		a = self.candidate("A")
		a["detected_skills"] = ["Python", "SQL"]
		a.pop("requirement_matches")

		result = compare_candidates(a, self.candidate("B"), {})

		self.assertEqual(result["a_unique_matches"], [])
		self.assertEqual(result["a_missing"], [])

	def test_requirement_name_priority_is_requirement_skill_then_name(self):
		a = self.candidate("A")
		a["requirement_matches"] = [
			{"requirement": "Requirement name", "skill": "Skill name", "name": "Name", "matched": True},
			{"skill": "Skill only", "name": "Name", "matched": True},
			{"name": "Name only", "matched": True},
		]

		result = compare_candidates(a, self.candidate("B"), {})

		self.assertEqual(
			result["a_unique_matches"],
			["Requirement name", "Skill only", "Name only"],
		)

	def test_candidate_names_appear_and_missing_names_do_not_crash(self):
		named_result = compare_candidates(self.candidate("Alice"), self.candidate("Bob"), {})
		unnamed_result = compare_candidates(self.candidate(None), self.candidate(None), {})

		self.assertIn("Alice", named_result["explanation"])
		self.assertIn("Bob", named_result["explanation"])
		self.assertIsInstance(unnamed_result["explanation"], str)

	def test_does_not_mutate_candidates_and_accepts_empty_jd(self):
		a = self.candidate("A")
		b = self.candidate("B")
		a["requirement_matches"] = {"Python": {"matched": True}}
		before_a = copy.deepcopy(a)
		before_b = copy.deepcopy(b)

		compare_candidates(a, b, {})

		self.assertEqual(a, before_a)
		self.assertEqual(b, before_b)


if __name__ == "__main__":
	unittest.main()
