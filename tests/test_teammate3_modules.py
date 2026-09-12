import unittest

from src.candidate_outcomes import generate_rejection_draft, route_alternative_role
from src.jd_bias import detect_jd_bias


class Teammate3ModuleTests(unittest.TestCase):
    def test_jd_bias_is_rule_based_and_neutral(self):
        flags = detect_jd_bias("Seeking a young and energetic rockstar who is a native English speaker.")
        phrases = {flag["phrase"] for flag in flags}
        self.assertEqual(phrases, {"young and energetic", "rockstar", "native english speaker"})
        self.assertTrue(all(flag.get("reason") and flag.get("suggestion") for flag in flags))

    def test_jd_bias_empty_text(self):
        self.assertEqual(detect_jd_bias(""), [])

    def test_role_routing_uses_structured_skills(self):
        candidate = {"detected_skills": ["node.js", "express", "mongodb"]}
        result = route_alternative_role(candidate)
        self.assertEqual(result["cluster"], "backend")
        self.assertIn("node.js", result["reason"])
        self.assertEqual(candidate["alternative_role"], result)

    def test_rejection_draft_uses_supplied_strengths_and_gaps(self):
        candidate = {
            "name": "Sam",
            "matched_required_skills": ["python"],
            "missing_required_skills": ["react", "mongodb"],
            "alternative_role": {"cluster": "data"},
        }
        draft = generate_rejection_draft(candidate, {"title": "Software Intern"})
        self.assertIn("Sam", draft)
        self.assertIn("Software Intern", draft)
        self.assertIn("python", draft)
        self.assertIn("react, mongodb", draft)
        self.assertIn("data-focused", draft)
        self.assertIn("Recruiter-review draft", draft)


if __name__ == "__main__":
    unittest.main()
