"""Interview probe generator — Differentiator D7 (Teammate 2).

Contract: MASTER_CONTEXT.md #5.3-D7, #16, #20 and
TEAMMATE_2_TRUST_AND_INNOVATION.md #16-#17.

    generate_interview_probes(jd: dict, candidate: dict) -> list[str]

Converts *uncertainty already present in the structured results* into concrete
recruiter verification actions. Template-based only — no LLM, no APIs, fully
deterministic. Output is capped at ``MAX_PROBES`` (docs: 3-5 questions).

Priority order (TEAMMATE_2 #16):
  1. Required/preferred skill with weak demonstrated evidence.
  2. Skill that appears to be only a Skills-section listing.
  3. Graph-only (related-tech) match.
  4. Semantic-high / keyword-low ambiguity about the exact tool.
  5. Missing high-weight required skill (no usable evidence at all).
"""

from __future__ import annotations

MAX_PROBES = 5
WEAK_EVIDENCE_RANGE = (0.35, 0.75)   # "mentioned" but not clearly demonstrated
LISTED_ONLY_MAX = 0.35               # skills-list-only band from MASTER_CONTEXT #5.3-D2
SEM_KW_DISAGREEMENT_GAP = 25.0
SEMANTIC_STRONG_FLOOR = 60.0
SKILLS_ONLY_TYPES = {"skills", "skills_section", "skills-list", "skills_list"}

# ---------------------------------------------------------------------------
# Templates (MASTER_CONTEXT #16 / TEAMMATE_2 #17)
# ---------------------------------------------------------------------------
T_WEAK_PROJECT = (
    "Can you explain your specific contribution to the work involving {skill}?"
)
T_LISTED_ONLY = (
    "You list {skill} under Skills. Can you describe a project where you "
    "personally used it and what you implemented?"
)
T_GRAPH_ONLY = (
    "Your resume shows experience with {related_skill}, which is related to "
    "{required_skill}. How much direct experience do you have with {required_skill}?"
)
T_SEM_KW_AMBIGUITY = (
    "Your experience appears relevant to {requirement}, but the exact tool is "
    "unclear. Which technologies did you use?"
)
T_MISSING_CRITICAL = (
    "This position requires {skill}. Do you have any hands-on experience with "
    "it — coursework, projects, or otherwise — that you can walk us through?"
)


def _display(entry: dict, req: dict, fallback: str = "") -> str:
    return str(
        req.get("display_name")
        or entry.get("requirement_name")
        or req.get("name")
        or entry.get("requirement_id")
        or fallback
    )


def _pretty_skill(name: str) -> str:
    """Readable form for a normalized skill pulled from a graph path."""
    pretty = str(name).title()
    return pretty.replace(".Js", ".js").replace("Node.Js", "Node.js")


def _score(candidate: dict, key: str) -> float:
    try:
        return float((candidate.get("scores") or {}).get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def generate_interview_probes(jd: dict, candidate: dict) -> list[str]:
    """Generate 3-5 targeted verification questions for one candidate.

    Consumes only ``requirement_matches`` + aggregate ``scores`` (Rule 3 of
    MASTER_CONTEXT #21 — no re-parsing). Attaches the result to
    ``candidate["interview_probes"]`` and returns it.
    """
    reqs: dict = {}
    for req in jd.get("requirements") or []:
        if isinstance(req, dict):
            reqs[req.get("id")] = req

    # Highest requirement weight first; ties broken by id for determinism.
    entries = [e for e in (candidate.get("requirement_matches") or []) if isinstance(e, dict)]
    def entry_weight(e: dict) -> float:
        return float((reqs.get(e.get("requirement_id")) or {}).get("weight") or 0.0)
    entries = sorted(entries, key=lambda e: (-entry_weight(e), str(e.get("requirement_id"))))

    probes: list[str] = []
    covered_skills: set[str] = set()

    def push(probe: str, dedupe_key: str) -> bool:
        if dedupe_key in covered_skills or len(probes) >= MAX_PROBES:
            return False
        covered_skills.add(dedupe_key)
        probes.append(probe)
        return len(probes) >= MAX_PROBES

    # Pass 1 — required/preferred skill with weak demonstrated evidence.
    low, high = WEAK_EVIDENCE_RANGE
    stop = False
    for e in entries:
        strength = float(e.get("evidence_strength") or 0.0)
        if e.get("keyword_match") and low < strength < high:
            skill = _display(e, reqs.get(e.get("requirement_id")) or {})
            if push(T_WEAK_PROJECT.format(skill=skill), skill.lower()):
                stop = True
                break
    # Pass 2 — listed-only in Skills section.
    if not stop:
        for e in entries:
            strength = float(e.get("evidence_strength") or 0.0)
            etype = str(e.get("evidence_type") or "").lower()
            if e.get("keyword_match") and (etype in SKILLS_ONLY_TYPES or strength <= LISTED_ONLY_MAX):
                skill = _display(e, reqs.get(e.get("requirement_id")) or {})
                if push(T_LISTED_ONLY.format(skill=skill), skill.lower()):
                    stop = True
                    break
    # Pass 3 — graph-only (related technology) match.
    if not stop:
        for e in entries:
            if e.get("graph_match") and not e.get("keyword_match"):
                path = e.get("graph_path") or []
                related = _pretty_skill(path[0]) if path else "related experience"
                req = reqs.get(e.get("requirement_id")) or {}
                required = _display(e, req)
                if push(
                    T_GRAPH_ONLY.format(related_skill=related, required_skill=required),
                    "graph:" + str(e.get("requirement_id")),
                ):
                    break
    # Pass 4 — semantic-high / keyword-low ambiguity on strong-but-unnamed matches.
    semantic = _score(candidate, "semantic")
    keyword = _score(candidate, "keyword")
    if not stop and semantic - keyword >= SEM_KW_DISAGREEMENT_GAP:
        for e in entries:
            req = reqs.get(e.get("requirement_id")) or {}
            if (req.get("importance") in {"required", "preferred"}
                    and not e.get("keyword_match")
                    and float(e.get("semantic_score") or 0.0) >= SEMANTIC_STRONG_FLOOR):
                requirement = _display(e, req)
                if push(T_SEM_KW_AMBIGUITY.format(requirement=requirement),
                        "semkw:" + requirement.lower()):
                    break
    # Pass 5 — missing high-weight required skill (no direct evidence at all;
    # graph-supported requirements were already probed by pass 3).
    if not stop:
        for e in entries:
            req = reqs.get(e.get("requirement_id")) or {}
            if (req.get("importance") == "required"
                    and float(req.get("weight") or 3.0) >= 3.0
                    and not e.get("keyword_match")
                    and not e.get("graph_match")
                    and not e.get("matched")):
                skill = _display(e, req)
                if push(T_MISSING_CRITICAL.format(skill=skill), "missing:" + skill.lower()):
                    break

    candidate["interview_probes"] = probes
    return probes
