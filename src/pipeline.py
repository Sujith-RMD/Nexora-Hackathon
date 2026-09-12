"""End-to-end core matching pipeline orchestrator.

Provides convenient high-level functions to parse PDFs, run all matchers,
score, and rank candidates according to the Teammate 1 contract.
"""

import os
from typing import Any, Dict, List, Optional
from .evidence import score_evidence
from .keyword_matcher import keyword_match
from .pdf_parser import parse_pdf_with_metadata
from .preprocessing import estimate_parse_quality, split_resume_sections
from .ranker import rank_candidates
from .requirement_extractor import detect_role_level, extract_requirements
from .schemas import CandidateDict, JDDict, create_default_candidate
from .scorer import score_candidate
from .semantic_matcher import get_semantic_model, semantic_match
from .skill_extractor import extract_skills_from_text


def parse_candidate_from_pdf(pdf_path: str, candidate_id: Optional[str] = None) -> CandidateDict:
    """Parse a single resume PDF and create an initialized CandidateDict."""
    filename = os.path.basename(pdf_path)
    cid = candidate_id or os.path.splitext(filename)[0]

    # Derive human-friendly display name from filename (e.g. sde__ishaan_kapoor.pdf -> Ishaan Kapoor)
    base = os.path.splitext(filename)[0]
    if "__" in base:
        raw_name = base.split("__")[-1]
    else:
        raw_name = base
    display_name = " ".join([part.capitalize() for part in raw_name.replace("_", " ").split()])

    parsed = parse_pdf_with_metadata(pdf_path)
    clean_text = str(parsed["text"])
    raw_text = str(parsed["raw_text"])

    sections = split_resume_sections(clean_text)
    quality = estimate_parse_quality(clean_text, sections)

    # Append any PDF reading warnings to quality warnings
    pdf_warnings = parsed.get("warnings", [])
    if pdf_warnings:
        quality["warnings"] = list(quality["warnings"]) + list(pdf_warnings)

    candidate = create_default_candidate(
        candidate_id=cid,
        name=display_name,
        file_name=filename,
        raw_text=raw_text,
        clean_text=clean_text,
        sections=sections,
        parse_quality=quality,
    )

    candidate["detected_skills"] = extract_skills_from_text(clean_text)
    return candidate


def evaluate_candidate(
    candidate: Dict[str, Any],
    jd: Dict[str, Any],
    semantic_model: Optional[Any] = None,
    graph_score: float = 0.0,
    graph_matches: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Execute keyword matching, local semantic matching, evidence scoring, and hybrid scoring."""
    model = semantic_model or get_semantic_model()

    kw_res = keyword_match(jd, candidate)
    sem_res = semantic_match(jd, candidate, model=model)
    evi_res = score_evidence(jd, candidate)

    scored = score_candidate(
        jd=jd,
        candidate=candidate,
        keyword_result=kw_res,
        semantic_result=sem_res,
        evidence_result=evi_res,
        graph_score=graph_score,
        graph_matches=graph_matches,
    )
    return scored


def run_core_pipeline(
    jd_dict: Dict[str, Any],
    resume_paths: List[str],
    semantic_model: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Run full Teammate 1 pipeline on a list of resume PDFs against a structured JD."""
    model = semantic_model or get_semantic_model()
    candidates: List[Dict[str, Any]] = []

    for path in resume_paths:
        cand = parse_candidate_from_pdf(path)
        evaluated = evaluate_candidate(cand, jd_dict, semantic_model=model)
        candidates.append(evaluated)

    ranked = rank_candidates(candidates)
    return ranked
