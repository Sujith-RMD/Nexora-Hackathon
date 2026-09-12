"""Skill normalization and extraction utilities.

Provides boundary-safe skill matching (avoiding false positives on single-letter
languages like C or R) and canonical alias resolution.
"""

import json
import os
import re
from typing import Dict, List, Optional, Set, Tuple


_DEFAULT_ALIASES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "skill_aliases.json"
)

_CACHED_ALIASES: Optional[Dict[str, str]] = None


def load_skill_aliases(path: Optional[str] = None) -> Dict[str, str]:
    """Load skill alias mappings from JSON."""
    global _CACHED_ALIASES
    if _CACHED_ALIASES is not None and path is None:
        return _CACHED_ALIASES

    target_path = path or _DEFAULT_ALIASES_PATH
    if os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if path is None:
                    _CACHED_ALIASES = data
                return data
        except Exception:
            pass
    return {}


def normalize_skill(term: str, aliases: Optional[Dict[str, str]] = None) -> str:
    """Normalize skill string to its canonical form using the alias dictionary."""
    if not term:
        return ""
    alias_dict = aliases if aliases is not None else load_skill_aliases()
    raw = term.strip().lower()
    # Direct alias lookup
    if raw in alias_dict:
        return alias_dict[raw]
    # Strip dots/dashes for fallback check (e.g., "react-js" -> "react js")
    alt = re.sub(r"[\-_]+", " ", raw).strip()
    if alt in alias_dict:
        return alias_dict[alt]
    return raw


def get_skill_pattern(term: str) -> re.Pattern:
    """Create a boundary-safe regular expression pattern for a skill term.

    Handles symbols like '+', '#', '.', and single letter languages ('c', 'r')
    safely without greedy substring collisions.
    """
    escaped = re.escape(term.strip())
    # Boundary: must not be preceded or followed by alphanumeric, +, or #
    # For 'js', must also not be preceded by a dot (e.g. node.js, vue.js)
    if term.strip().lower() == "js":
        pattern = rf"(?<![a-zA-Z0-9\+#\.]){escaped}(?![a-zA-Z0-9\+#])"
    else:
        pattern = rf"(?<![a-zA-Z0-9\+#]){escaped}(?![a-zA-Z0-9\+#])"
    return re.compile(pattern, re.IGNORECASE)


def find_skill_matches(
    canonical_skill: str,
    text: str,
    aliases: Optional[Dict[str, str]] = None,
) -> Tuple[bool, Optional[str]]:
    """Check whether a skill or any of its known aliases appears in the text.

    Returns (matched: bool, matched_variant: str).
    """
    if not text or not canonical_skill:
        return False, None

    alias_dict = aliases if aliases is not None else load_skill_aliases()
    canon_norm = normalize_skill(canonical_skill, alias_dict)

    # Gather all variants that map to this canonical skill
    variants: Set[str] = {canon_norm, canonical_skill.strip().lower()}
    for alias, canonical in alias_dict.items():
        if canonical == canon_norm:
            variants.add(alias.lower())

    # Sort variants longest first to match more specific variants first
    sorted_variants = sorted(variants, key=len, reverse=True)

    for variant in sorted_variants:
        pat = get_skill_pattern(variant)
        match = pat.search(text)
        if match:
            return True, match.group(0)

    return False, None


def extract_skills_from_text(
    text: str,
    skill_catalog: Optional[List[str]] = None,
    aliases: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Scan text against a catalog and alias dictionary to detect canonical skills."""
    if not text:
        return []

    alias_dict = aliases if aliases is not None else load_skill_aliases()
    all_targets: Set[str] = set()

    if skill_catalog:
        for s in skill_catalog:
            all_targets.add(normalize_skill(s, alias_dict))

    # Also check all canonical targets present in aliases
    for can in alias_dict.values():
        all_targets.add(can)

    detected: Set[str] = set()
    for target in all_targets:
        matched, _ = find_skill_matches(target, text, alias_dict)
        if matched:
            detected.add(target)

    return sorted(list(detected))
