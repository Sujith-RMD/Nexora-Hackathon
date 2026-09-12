"""Shared data schemas and contracts as defined in MASTER_CONTEXT.md.

This module provides factory functions, TypedDict definitions, and JSON
serialization helpers ensuring clean inter-teammate data handoffs.
"""

from typing import Any, Dict, List, Optional, TypedDict
import json


class RequirementDict(TypedDict, total=False):
    id: str
    name: str
    display_name: str
    category: str
    importance: str  # "required" | "preferred" | "context"
    weight: float
    source_text: str
    alternative_group: Optional[str]
    group_operator: Optional[str]


class BiasFlagDict(TypedDict):
    phrase: str
    reason: str
    suggestion: str


class JDDict(TypedDict):
    title: str
    raw_text: str
    clean_text: str
    requirements: List[RequirementDict]
    role_level: str  # "intern" | "junior" | "mid" | "senior" | "unknown"
    bias_flags: List[BiasFlagDict]


class SectionsDict(TypedDict):
    skills: str
    experience: str
    projects: str
    education: str
    certifications: str
    other: str


class ParseQualityDict(TypedDict):
    score: float
    warnings: List[str]


class RequirementMatchDict(TypedDict):
    requirement_id: str
    requirement_name: str
    keyword_match: bool
    keyword_score: float
    semantic_score: float
    graph_match: bool
    graph_path: List[str]
    graph_score: float
    evidence_strength: float
    evidence_type: str
    evidence_text: str
    matched: bool


class ScoresDict(TypedDict):
    semantic: float
    keyword: float
    evidence: float
    graph: float
    base_score: float
    final_score: float


class OverqualificationDict(TypedDict):
    flag: bool
    reasons: List[str]


class CritiqueDict(TypedDict):
    confidence: str  # "high" | "medium" | "low"
    flags: List[str]
    summary: str
    human_review_recommended: bool


class CounterfactualDict(TypedDict):
    target_rank: int
    target_score: float
    suggested_improvements: List[Dict[str, Any]]
    projected_score: float


class AlternativeRoleDict(TypedDict):
    cluster: str
    reason: str


class ExplanationDataDict(TypedDict):
    strongest_matches: List[Dict[str, Any]]
    important_missing: List[str]
    best_evidence: List[Dict[str, Any]]
    score_breakdown: Dict[str, float]


class CandidateDict(TypedDict):
    candidate_id: str
    name: str
    file_name: str
    raw_text: str
    clean_text: str
    sections: SectionsDict
    parse_quality: ParseQualityDict
    detected_skills: List[str]
    requirement_matches: List[RequirementMatchDict]
    scores: ScoresDict
    matched_required_skills: List[str]
    missing_required_skills: List[str]
    matched_preferred_skills: List[str]
    rank: int
    overqualification: OverqualificationDict
    critique: Optional[CritiqueDict]
    counterfactual: Optional[CounterfactualDict]
    interview_probes: List[str]
    alternative_role: Optional[AlternativeRoleDict]
    explanation_data: Optional[ExplanationDataDict]


def create_empty_sections() -> SectionsDict:
    return {
        "skills": "",
        "experience": "",
        "projects": "",
        "education": "",
        "certifications": "",
        "other": "",
    }


def create_default_scores() -> ScoresDict:
    return {
        "semantic": 0.0,
        "keyword": 0.0,
        "evidence": 0.0,
        "graph": 0.0,
        "base_score": 0.0,
        "final_score": 0.0,
    }


def create_default_candidate(
    candidate_id: str,
    name: str,
    file_name: str,
    raw_text: str = "",
    clean_text: str = "",
    sections: Optional[SectionsDict] = None,
    parse_quality: Optional[ParseQualityDict] = None,
) -> CandidateDict:
    """Factory to produce an initialized Candidate dict matching MASTER_CONTEXT.md."""
    return {
        "candidate_id": candidate_id,
        "name": name,
        "file_name": file_name,
        "raw_text": raw_text,
        "clean_text": clean_text,
        "sections": sections or create_empty_sections(),
        "parse_quality": parse_quality or {"score": 100.0, "warnings": []},
        "detected_skills": [],
        "requirement_matches": [],
        "scores": create_default_scores(),
        "matched_required_skills": [],
        "missing_required_skills": [],
        "matched_preferred_skills": [],
        "rank": 0,
        "overqualification": {"flag": False, "reasons": []},
        "critique": None,
        "counterfactual": None,
        "interview_probes": [],
        "alternative_role": None,
        "explanation_data": None,
    }


def sanitize_for_json(data: Any) -> Any:
    """Recursively convert numpy types, floats, and non-serializable objects to pure Python types."""
    if isinstance(data, dict):
        return {str(k): sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple)):
        return [sanitize_for_json(x) for x in data]
    elif hasattr(data, "item"):  # numpy scalar or torch tensor scalar
        return data.item()
    elif hasattr(data, "tolist"):  # numpy array or torch tensor
        return sanitize_for_json(data.tolist())
    elif isinstance(data, float):
        if data != data:  # NaN
            return 0.0
        return float(data)
    elif isinstance(data, int):
        return int(data)
    elif isinstance(data, bool):
        return bool(data)
    return data


def candidate_to_json(candidate: Dict[str, Any], indent: Optional[int] = None) -> str:
    """Safely serialize candidate object to JSON string."""
    sanitized = sanitize_for_json(candidate)
    return json.dumps(sanitized, indent=indent)
