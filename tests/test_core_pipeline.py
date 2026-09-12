"""Unit and integration test suite for the Teammate 1 Core Matching Pipeline.

Validates Test Cases A through E from TEAMMATE_1_CORE_MATCHING.md, schema compliance
with MASTER_CONTEXT.md, and offline JSON serializability.
"""

import json
import unittest
from src.evidence import score_evidence
from src.keyword_matcher import keyword_match
from src.pipeline import evaluate_candidate
from src.preprocessing import estimate_parse_quality, split_resume_sections
from src.ranker import rank_candidates
from src.requirement_extractor import detect_role_level, extract_requirements
from src.schemas import candidate_to_json, create_default_candidate, sanitize_for_json
from src.scorer import score_candidate
from src.semantic_matcher import get_semantic_model, semantic_match
from src.skill_extractor import normalize_skill


class TestCoreMatchingPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load local embedding model once for all tests
        cls.model = get_semantic_model()

    def setUp(self):
        self.sample_jd_text = """
        Job Title: Junior Full Stack Developer Intern
        Requirements:
        - Must have strong experience with React and Node.js.
        - Required: Proficient in MongoDB database design.
        - Should have experience to develop backend APIs.
        - Preferred: Familiarity with Docker and AWS.
        """
        self.requirements = extract_requirements(self.sample_jd_text)
        self.jd = {
            "title": "Junior Full Stack Developer Intern",
            "raw_text": self.sample_jd_text,
            "clean_text": self.sample_jd_text,
            "requirements": self.requirements,
            "role_level": detect_role_level(self.sample_jd_text),
            "bias_flags": [],
        }

    def test_schema_conformance(self):
        """Verify candidate object contains all required keys from MASTER_CONTEXT.md Section 7.2."""
        candidate = create_default_candidate("cand_1", "Test Candidate", "test.pdf")
        candidate = evaluate_candidate(candidate, self.jd, semantic_model=self.model)

        expected_keys = [
            "candidate_id", "name", "file_name", "raw_text", "clean_text",
            "sections", "parse_quality", "detected_skills", "requirement_matches",
            "scores", "matched_required_skills", "missing_required_skills",
            "matched_preferred_skills", "rank", "overqualification", "critique",
            "counterfactual", "interview_probes", "alternative_role"
        ]
        for key in expected_keys:
            self.assertIn(key, candidate, f"Missing required key in Candidate schema: {key}")

        # Check requirement_matches structure
        for m in candidate["requirement_matches"]:
            self.assertIn("requirement_id", m)
            self.assertIn("requirement_name", m)
            self.assertIn("keyword_match", m)
            self.assertIn("keyword_score", m)
            self.assertIn("semantic_score", m)
            self.assertIn("evidence_strength", m)
            self.assertIn("evidence_type", m)
            self.assertIn("evidence_text", m)
            self.assertIn("matched", m)

    def test_case_a_exact_skill_in_project(self):
        """Test A: Exact skill in project experience receives high keyword, semantic, and evidence scores."""
        resume_text = """
        TECHNICAL SKILLS
        JavaScript, HTML, CSS

        PROJECTS
        E-Commerce Platform
        - Built frontend using React.js and Redux for interactive UI components.
        - Deployed scalable web services on Docker containers.
        """
        sections = split_resume_sections(resume_text)
        cand = create_default_candidate("cand_a", "Alice", "alice.pdf", raw_text=resume_text, clean_text=resume_text, sections=sections)
        cand = evaluate_candidate(cand, self.jd, semantic_model=self.model)

        # Locate React requirement
        react_match = next((m for m in cand["requirement_matches"] if m["requirement_name"] == "react"), None)
        self.assertIsNotNone(react_match)
        self.assertTrue(react_match["keyword_match"], "React keyword should match via React.js alias")
        self.assertGreaterEqual(react_match["semantic_score"], 60.0, "Semantic score should be high")
        self.assertGreaterEqual(react_match["evidence_strength"], 0.85, "Demonstrated project evidence should be strong (>= 0.85)")
        self.assertEqual(react_match["evidence_type"], "project")
        self.assertIn("React.js", react_match["evidence_text"])

    def test_case_b_skills_list_only(self):
        """Test B: Skills listed in Skills section only receive lower authenticity than demonstrated projects."""
        resume_text = """
        SKILLS
        React, Node.js, MongoDB

        EXPERIENCE
        General Office Assistant
        - Maintained filing systems and coordinated meetings.
        """
        sections = split_resume_sections(resume_text)
        cand = create_default_candidate("cand_b", "Bob", "bob.pdf", raw_text=resume_text, clean_text=resume_text, sections=sections)
        cand = evaluate_candidate(cand, self.jd, semantic_model=self.model)

        react_match = next((m for m in cand["requirement_matches"] if m["requirement_name"] == "react"), None)
        self.assertIsNotNone(react_match)
        self.assertTrue(react_match["keyword_match"], "Keyword match should be True")
        self.assertEqual(react_match["evidence_strength"], 0.35, "Skills list only should yield 0.35 strength")
        self.assertEqual(react_match["evidence_type"], "skills_list")

    def test_case_c_semantic_related_experience(self):
        """Test C: Semantic matching captures relevant terminology even if exact wording varies."""
        # Create a JD requirement for backend APIs
        api_jd = {
            "title": "Backend Intern",
            "requirements": [
                {
                    "id": "req_api",
                    "name": "rest api",
                    "display_name": "REST API",
                    "category": "architecture",
                    "importance": "required",
                    "weight": 3.0,
                    "source_text": "Develop backend APIs and server logic",
                }
            ],
            "role_level": "intern",
            "bias_flags": [],
        }

        resume_text = """
        PROJECTS
        Microservices Platform
        - Created RESTful services using Express and handled routing logic.
        """
        sections = split_resume_sections(resume_text)
        cand = create_default_candidate("cand_c", "Charlie", "charlie.pdf", raw_text=resume_text, clean_text=resume_text, sections=sections)
        evaluated = evaluate_candidate(cand, api_jd, semantic_model=self.model)

        api_match = evaluated["requirement_matches"][0]
        self.assertGreaterEqual(api_match["semantic_score"], 60.0, "Semantic match should recognize RESTful services for backend APIs")

    def test_case_d_missing_requirement_penalty(self):
        """Test D: Missing critical required skills triggers transparent penalty and flags."""
        resume_text = """
        TECHNICAL SKILLS
        HTML, CSS, Graphic Design

        EXPERIENCE
        UI Designer
        - Designed wireframes and vector graphics.
        """
        sections = split_resume_sections(resume_text)
        cand = create_default_candidate("cand_d", "David", "david.pdf", raw_text=resume_text, clean_text=resume_text, sections=sections)
        cand = evaluate_candidate(cand, self.jd, semantic_model=self.model)

        self.assertIn("react", cand["missing_required_skills"])
        self.assertIn("node.js", cand["missing_required_skills"])
        self.assertIn("mongodb", cand["missing_required_skills"])

        # Final score should be lower than base score due to penalty
        self.assertLess(cand["scores"]["final_score"], cand["scores"]["base_score"])
        # Penalty is capped at 10.0
        self.assertLessEqual(cand["scores"]["base_score"] - cand["scores"]["final_score"], 10.01)

    def test_case_e_messy_resume_fallback(self):
        """Test E: Messy resume with non-standard formatting does not crash and populates warnings."""
        messy_text = "I am a programmer. I know python and javascript. I built websites."
        sections = split_resume_sections(messy_text)
        quality = estimate_parse_quality(messy_text, sections)

        self.assertEqual(sections["skills"], "")
        self.assertIn(messy_text, sections["other"])
        self.assertGreater(len(quality["warnings"]), 0)
        self.assertLess(quality["score"], 80.0)

        cand = create_default_candidate("cand_e", "Evan", "evan.pdf", raw_text=messy_text, clean_text=messy_text, sections=sections, parse_quality=quality)
        cand = evaluate_candidate(cand, self.jd, semantic_model=self.model)
        self.assertIsInstance(cand["scores"]["final_score"], float)

    def test_ranking_and_tie_breaking(self):
        """Test candidate ranking order, tie-breaking, and top-3 explanation payload."""
        cand_strong = create_default_candidate("c1", "Strong Cand", "c1.pdf", sections=split_resume_sections(
            "PROJECTS\n- Built fullstack app with React, Node.js and MongoDB."
        ))
        cand_weak = create_default_candidate("c2", "Weak Cand", "c2.pdf", sections=split_resume_sections(
            "SKILLS\nReact\nEXPERIENCE\n- Handled paperwork."
        ))

        e1 = evaluate_candidate(cand_strong, self.jd, semantic_model=self.model)
        e2 = evaluate_candidate(cand_weak, self.jd, semantic_model=self.model)

        ranked = rank_candidates([e2, e1])
        self.assertEqual(ranked[0]["candidate_id"], "c1", "Strong candidate should be ranked #1")
        self.assertEqual(ranked[0]["rank"], 1)
        self.assertEqual(ranked[1]["rank"], 2)

        # Check explanation data
        self.assertIn("explanation_data", ranked[0])
        exp = ranked[0]["explanation_data"]
        self.assertIn("strongest_matches", exp)
        self.assertIn("best_evidence", exp)
        self.assertIn("score_breakdown", exp)

    def test_json_serializability(self):
        """Verify candidate dictionary can be serialized to JSON without numpy/tensor errors."""
        cand = create_default_candidate("cand_json", "Json Test", "json.pdf", sections=split_resume_sections(
            "PROJECTS\n- Built REST APIs with Express and MongoDB."
        ))
        evaluated = evaluate_candidate(cand, self.jd, semantic_model=self.model)
        ranked = rank_candidates([evaluated])

        json_str = candidate_to_json(ranked[0])
        parsed = json.loads(json_str)
        self.assertEqual(parsed["candidate_id"], "cand_json")
        self.assertIsInstance(parsed["scores"]["final_score"], float)


if __name__ == "__main__":
    unittest.main()
