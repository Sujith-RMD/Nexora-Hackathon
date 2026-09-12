"""Deterministic interview verification question generator."""


def generate_interview_probes(jd: dict, candidate: dict) -> list[str]:
    probes = []
    for match in candidate.get("requirement_matches", []) or []:
        if not isinstance(match, dict):
            continue
        name = match.get("requirement_name", "this requirement")
        if match.get("graph_match") and not match.get("keyword_match"):
            probes.append(f"Your resume shows related experience for {name}. How much direct experience do you have with {name}?")
        elif match.get("keyword_match") and float(match.get("evidence_strength", 0) or 0) < 0.6:
            probes.append(f"You list {name}. Can you describe a project where you personally used it and what you implemented?")
        elif match.get("matched") is False:
            probes.append(f"Can you describe any experience you have with {name}?")
        if len(probes) >= 5:
            break
    candidate["interview_probes"] = probes
    return probes
