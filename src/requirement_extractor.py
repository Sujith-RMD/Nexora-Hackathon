"""Deterministic JD requirement extractor and role level detector.

Extracts structured JD requirements tagged with importance ('required', 'preferred', 'context')
and weights (3.0, 2.0, 1.0) without calling external APIs.
"""

import re
from typing import Dict, List, Optional, Set
from .skill_extractor import (
    extract_skills_from_text,
    find_skill_matches,
    load_skill_aliases,
    normalize_skill,
)


SKILL_CATEGORIES = {
    # Languages
    "javascript": "language",
    "typescript": "language",
    "python": "language",
    "java": "language",
    "c++": "language",
    "c#": "language",
    "go": "language",
    "php": "language",
    "ruby": "language",
    "sql": "language",
    "html": "language",
    "css": "language",
    # Frameworks & Libraries
    "react": "framework",
    "react native": "framework",
    "node.js": "framework",
    "express": "framework",
    "next.js": "framework",
    "vue": "framework",
    "angular": "framework",
    "fastapi": "framework",
    "flask": "framework",
    "django": "framework",
    "spring boot": "framework",
    "tailwindcss": "framework",
    "bootstrap": "framework",
    "redux": "framework",
    "pandas": "library",
    "numpy": "library",
    "scikit-learn": "library",
    "pytorch": "library",
    "tensorflow": "library",
    # Databases
    "mongodb": "database",
    "postgresql": "database",
    "mysql": "database",
    "sqlite": "database",
    "redis": "database",
    # APIs & Architecture
    "rest api": "architecture",
    "graphql": "architecture",
    "websockets": "architecture",
    # Tools & DevOps
    "git": "tool",
    "github": "tool",
    "gitlab": "tool",
    "docker": "tool",
    "kubernetes": "tool",
    "aws": "cloud",
    "azure": "cloud",
    "gcp": "cloud",
    "linux": "os",
    "ci/cd": "tool",
    # Testing
    "pytest": "testing",
    "jest": "testing",
    "mocha": "testing",
}

IMPORTANCE_WEIGHTS = {
    "required": 3.0,
    "preferred": 2.0,
    "context": 1.0,
}

REQUIRED_CUES = [
    r"\bmust\s+(?:have|be|demonstrate)\b",
    r"\brequired\b",
    r"\brequirements?\b",
    r"\bessential\b",
    r"\bneeds?\s+to\s+have\b",
    r"\bshould\s+have\b",
    r"\bproficient\s+(?:in|with)\b",
    r"\bstrong\s+(?:knowledge|experience|understanding)\b",
    r"\bmandatory\b",
]

PREFERRED_CUES = [
    r"\bpreferred\b",
    r"\bnice\s+to\s+have\b",
    r"\bplus\b",
    r"\bbonus\b",
    r"\bdesirable\b",
    r"\bgood\s+to\s+have\b",
    r"\bideal\b",
]


def detect_role_level(jd_text: str) -> str:
    """Classify role level from JD text ('intern' | 'junior' | 'mid' | 'senior' | 'unknown')."""
    if not jd_text:
        return "unknown"

    lower = jd_text.lower()
    # Check for intern
    if re.search(r"\b(?:intern|internship|trainee|freshers?|co-op)\b", lower):
        return "intern"
    # Check for senior / lead
    if re.search(r"\b(?:senior|lead|principal|staff|architect|manager)\b", lower):
        return "senior"
    # Check for junior / associate
    if re.search(r"\b(?:junior|entry[\s\-]level|associate|jr\.?)\b", lower):
        return "junior"
    # Check for mid
    if re.search(r"\b(?:mid[\s\-]level|intermediate|experienced)\b", lower):
        return "mid"

    return "unknown"


def _determine_importance(sentence: str, full_text: str) -> str:
    """Determine requirement importance based on surrounding sentence cues."""
    s_lower = sentence.lower()
    for cue in PREFERRED_CUES:
        if re.search(cue, s_lower):
            return "preferred"

    for cue in REQUIRED_CUES:
        if re.search(cue, s_lower):
            return "required"

    return "context"


def extract_requirements(
    jd_text: str,
    skill_catalog: Optional[List[str]] = None,
    aliases: Optional[Dict[str, str]] = None,
) -> List[Dict[str, object]]:
    """Extract structured requirements from JD text.

    Returns a list of dicts:
      [
        {
          "id": "req_react",
          "name": "react",
          "display_name": "React",
          "category": "framework",
          "importance": "required|preferred|context",
          "weight": 3.0|2.0|1.0,
          "source_text": "..."
        }
      ]
    """
    if not jd_text or not jd_text.strip():
        return []

    alias_dict = aliases if aliases is not None else load_skill_aliases()
    detected_skills = extract_skills_from_text(jd_text, skill_catalog, alias_dict)

    raw_sentences = re.split(r"\n+|[•;]|\s+[-*]\s+|\.\s+(?=[A-Z0-9\"'(\[])", jd_text)
    sentences = [s.strip() for s in raw_sentences if s.strip()]

    requirements: List[Dict[str, object]] = []
    seen_names: Set[str] = set()

    for skill in detected_skills:
        canonical = normalize_skill(skill, alias_dict)
        if canonical in seen_names:
            continue
        seen_names.add(canonical)

        # Locate sentence containing this skill
        matching_sentences: List[str] = []
        for s in sentences:
            m, _ = find_skill_matches(canonical, s, alias_dict)
            if m:
                matching_sentences.append(s)

        source_text = matching_sentences[0] if matching_sentences else canonical
        importance = "context"
        for s in matching_sentences:
            imp = _determine_importance(s, jd_text)
            if imp == "required":
                importance = "required"
                break
            elif imp == "preferred" and importance != "required":
                importance = "preferred"

        weight = IMPORTANCE_WEIGHTS[importance]
        category = SKILL_CATEGORIES.get(canonical, "technical")

        # Format display name nicely
        display_name = canonical.capitalize()
        if canonical in ["node.js", "next.js", "vue.js"]:
            parts = canonical.split(".")
            display_name = parts[0].capitalize() + "." + parts[1]
        elif canonical in ["html", "css", "sql", "api", "rest api", "ci/cd", "aws", "gcp"]:
            display_name = canonical.upper()
        elif canonical in ["c++", "c#"]:
            display_name = canonical.upper()

        req_id = f"req_{re.sub(r'[^a-z0-9]+', '_', canonical).strip('_')}"

        requirements.append(
            {
                "id": req_id,
                "name": canonical,
                "display_name": display_name,
                "category": category,
                "importance": importance,
                "weight": weight,
                "source_text": source_text,
            }
        )

    # Sort requirements: required first (by weight desc), then alphabetically
    requirements.sort(key=lambda r: (-float(r["weight"]), str(r["name"])))
    return requirements
