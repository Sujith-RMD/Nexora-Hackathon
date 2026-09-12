"""Streamlit-facing analysis runner — integration glue (Teammate 2).

Bridges in-memory ``st.file_uploader`` objects to the file-path-based Teammate
1 parser and the Teammate 2 trust pipeline. The Streamlit app should be the
ONLY place this is called from; everything below is plain Python and testable
headlessly (see tests/test_teammate2_integration.py).

    payload = analyze_uploads(jd_bytes, jd_name, [(pdf_bytes, name), ...],
                              on_stage=callable)
    payload = {"jd", "ranked_candidates", "team_result", "jd_warnings",
               "resume_warnings"}

Flow (MASTER_CONTEXT #22 merge order, T1 core -> T2 trust layer -> T3-facing
summary): parse -> requirements -> keyword/semantic/evidence -> skill graph ->
rescore + rank -> critique/overqualification/probes/counterfactual -> team
mode -> JD review. No external APIs, no network.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple

from .jd_bias import review_jd
from .pdf_parser import parse_pdf_with_metadata
from .pipeline import parse_candidate_from_pdf
from .trust_pipeline import build_jd, run_trust_layer

STAGES: List[str] = [
    "Parsing job description",
    "Extracting requirements",
    "Parsing resumes",
    "Running keyword + semantic + evidence matching",
    "Applying skill graph and rescoring",
    "Ranking candidates",
    "Running self-critique, coaching and probes",
    "Composing team recommendation and JD review",
]


class AnalysisError(ValueError):
    """User-facing failure with a safe message (never a raw traceback)."""


def _with_temp_pdf(data: bytes, action: Callable[[str], Any]) -> Any:
    """Run a path-based Teammate 1 function on in-memory upload bytes."""
    fd, tmp_path = tempfile.mkstemp(suffix=".pdf", prefix="internloom_")
    try:
        os.write(fd, data)
        os.close(fd)
        return action(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def analyze_uploads(
    jd_bytes: bytes,
    jd_name: str,
    resumes: List[Tuple[bytes, str]],
    on_stage: Optional[Callable[[str], None]] = None,
    model: Optional[Any] = None,
    team_size: int = 3,
) -> Dict[str, Any]:
    """Run the complete integrated analysis on uploaded file bytes."""
    stage = on_stage or (lambda _label: None)

    # 1. JD -----------------------------------------------------------------
    stage(STAGES[0])
    jd_parse = _with_temp_pdf(jd_bytes, parse_pdf_with_metadata)

    jd_text = str(jd_parse.get("text") or "").strip()
    if not jd_text:
        warnings = "; ".join(jd_parse.get("warnings") or []) or "no text found"
        raise AnalysisError(
            "The job description PDF produced no readable text "
            f"({warnings}). Is it a scanned/image-only PDF?"
        )
    first_line = jd_text.splitlines()[0].strip() if jd_text.splitlines() else ""
    title = first_line[:120] if first_line.lower().startswith("job title") else ""

    stage(STAGES[1])
    jd = build_jd(jd_text, title=title or jd_name)
    jd["bias_flags"] = review_jd(jd)

    # 2. Resumes ------------------------------------------------------------
    stage(STAGES[2])
    candidates: List[Dict[str, Any]] = []
    resume_warnings: Dict[str, List[str]] = {}
    for index, (data, name) in enumerate(resumes, start=1):
        if len(resumes) >= 6 and index % 6 == 0:
            stage(f"{STAGES[2]} ({index - 1}/{len(resumes)})")
        candidate = _with_temp_pdf(data, lambda p: parse_candidate_from_pdf(p))
        # Uploaded filenames are already unique-ish; keep a readable id.
        candidate["candidate_id"] = f"c{index:02d}_{os.path.splitext(name)[0][:40]}"
        candidate["file_name"] = name
        if not str(candidate.get("clean_text") or "").strip():
            resume_warnings[name] = list(candidate.get("parse_quality", {})
                                         .get("warnings", [])) or ["empty text"]
        candidates.append(candidate)

    if not any(str(c.get("clean_text") or "").strip() for c in candidates):
        raise AnalysisError("None of the uploaded resume PDFs produced readable text.")

    # 3-7. Core scoring + trust layer (Teammate 1 + Teammate 2) ------------
    stage(STAGES[3])
    ranked, team_result = run_trust_layer(jd, candidates, model=model,
                                          team_size=team_size)
    stage(STAGES[4]); stage(STAGES[5]); stage(STAGES[6])

    # 8. JD review already attached; return payload --------------------------
    stage(STAGES[7])
    return {
        "jd": jd,
        "ranked_candidates": ranked,
        "team_result": team_result,
        "jd_warnings": list(jd_parse.get("warnings") or []),
        "resume_warnings": resume_warnings,
    }
