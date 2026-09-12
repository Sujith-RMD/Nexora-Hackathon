"""Resume preprocessing, section detection, and parse quality assessment.

Extracts normalized resume sections and evaluates the textual quality and completeness
of the extracted document.
"""

import re
import string
from typing import Dict, List, Tuple


SECTION_PATTERNS = {
    "skills": [
        r"^(?:technical\s+)?skills(?:\s+and\s+(?:abilities|competencies))?",
        r"^tools\s*(?:&|and)\s*technologies",
        r"^tech\s+stack",
        r"^technologies(?:\s+used)?",
        r"^core\s+competencies",
        r"^programming\s+languages",
        r"^technical\s+proficiencies",
        r"^competencies",
    ],
    "experience": [
        r"^(?:work|professional|employment)\s+experience",
        r"^experience",
        r"^employment(?:\s+history)?",
        r"^work\s+history",
        r"^internships?(?:\s+experience)?",
        r"^industry\s+experience",
        r"^relevant\s+experience",
    ],
    "projects": [
        r"^(?:academic|personal|key|technical|selected|featured)\s+projects",
        r"^projects",
        r"^project\s+experience",
        r"^portfolio(?:\s+projects)?",
    ],
    "education": [
        r"^education(?:al\s+background)?",
        r"^academic\s+(?:background|history|credentials)",
        r"^qualifications",
        r"^degrees?(?:\s+and\s+diplomas)?",
    ],
    "certifications": [
        r"^certifications?(?:\s*&|\s+and|\s*\/)?(?:\s*licenses)?",
        r"^certificates?",
        r"^licenses(?:\s+and\s+certifications)?",
        r"^accreditations",
        r"^courses(?:\s+and\s+certifications)?",
    ],
}


def _identify_header(line: str) -> Tuple[str, bool]:
    """Test if a line is likely a resume section header.

    Returns (section_name, is_header).
    """
    clean_line = line.strip()
    # Headers are usually short (< 50 chars) and not sentences
    if not clean_line or len(clean_line) > 55 or clean_line.endswith((".", ",", ";")):
        return "", False

    # Strip markdown headers, bullets, colons, numbers (e.g. "1. SKILLS:", "## EXPERIENCE")
    normalized_line = re.sub(r"^[#\*\-•\d\.\s]+", "", clean_line).strip()
    normalized_line = re.sub(r"[:\-_|]+$", "", normalized_line).strip().lower()

    for sec_name, patterns in SECTION_PATTERNS.items():
        for pat in patterns:
            if re.match(pat + r"$", normalized_line, re.IGNORECASE):
                return sec_name, True

    return "", False


def split_resume_sections(text: str) -> Dict[str, str]:
    """Split resume text into normalized sections.

    Returns dict matching MASTER_CONTEXT.md:
      {"skills": str, "experience": str, "projects": str,
       "education": str, "certifications": str, "other": str}
    """
    sections: Dict[str, List[str]] = {
        "skills": [],
        "experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
        "other": [],
    }

    if not text or not text.strip():
        return {k: "" for k in sections}

    lines = text.split("\n")
    current_section = "other"

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        sec_name, is_header = _identify_header(stripped)
        if is_header:
            current_section = sec_name
        else:
            sections[current_section].append(stripped)

    # Format each section as joined string
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def estimate_parse_quality(raw_text: str, sections: Dict[str, str]) -> Dict[str, object]:
    """Estimate parse quality score (0-100) and identify warning flags.

    Considers character count, section count, noise symbols, line lengths, etc.
    """
    warnings: List[str] = []
    score = 100.0

    if not raw_text or not raw_text.strip():
        return {
            "score": 0.0,
            "warnings": ["Document text is completely empty."],
        }

    char_count = len(raw_text.strip())
    if char_count < 200:
        score -= 50.0
        warnings.append(f"Extremely low text length ({char_count} characters). Possible scanned PDF.")
    elif char_count < 500:
        score -= 25.0
        warnings.append(f"Low text length ({char_count} characters). Resume appears unusually brief.")

    # Printable character ratio
    printable_chars = sum(1 for c in raw_text if c in string.printable)
    printable_ratio = printable_chars / max(1, len(raw_text))
    if printable_ratio < 0.85:
        score -= 30.0
        warnings.append(f"Low printable text ratio ({printable_ratio:.1%}). Possible binary/font encoding distortion.")

    # Check detected standard sections
    standard_sections = ["skills", "experience", "projects", "education"]
    detected_count = sum(1 for s in standard_sections if len(sections.get(s, "").strip()) > 30)

    if detected_count == 0:
        score -= 35.0
        warnings.append("No standard resume sections detected (Skills, Experience, Projects, Education). Fallback to unstructured content.")
    elif detected_count == 1:
        score -= 20.0
        warnings.append("Only 1 standard section detected. Headings may have non-standard formatting.")
    elif detected_count == 2:
        score -= 10.0
        warnings.append("Only 2 standard sections detected.")

    # Check for excessive unprintable or symbol noise
    noise_symbols = sum(1 for c in raw_text if c in "^~`\\|§±")
    if noise_symbols > 50:
        score -= 15.0
        warnings.append("High symbol noise detected. PDF extraction may contain formatting artifacts.")

    # Check duplicated consecutive lines
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    if lines:
        dup_count = sum(1 for i in range(1, len(lines)) if lines[i] == lines[i - 1])
        dup_ratio = dup_count / len(lines)
        if dup_ratio > 0.15:
            score -= 15.0
            warnings.append(f"High repeated lines detected ({dup_ratio:.1%}). Possible header/footer repetition.")

    # Clamping
    final_score = max(0.0, min(100.0, round(score, 1)))
    return {
        "score": final_score,
        "warnings": warnings,
    }
