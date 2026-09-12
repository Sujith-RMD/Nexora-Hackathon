"""Deterministic ranking confidence and self-critique rules."""


def critique_ranking(jd: dict, ranked_candidates: list[dict]) -> list[dict]:
    for index, candidate in enumerate(ranked_candidates or []):
        scores = candidate.get("scores") or {}
        flags = []
        semantic = scores.get("semantic")
        keyword = scores.get("keyword")
        if isinstance(semantic, (int, float)) and isinstance(keyword, (int, float)) and abs(semantic - keyword) > 25:
            flags.append("Semantic relevance and explicit requirement coverage disagree.")
        evidence = scores.get("evidence")
        if index < 3 and isinstance(evidence, (int, float)) and evidence < 60:
            flags.append("Top-three candidate has comparatively weak evidence authenticity.")
        if candidate.get("missing_required_skills"):
            flags.append("One or more required skills are missing from the explicit match results.")
        if index + 1 < len(ranked_candidates):
            next_score = (ranked_candidates[index + 1].get("scores") or {}).get("final_score")
            score = scores.get("final_score")
            if isinstance(score, (int, float)) and isinstance(next_score, (int, float)) and score - next_score < 2.5:
                flags.append("This is a close ranking decision.")
        quality = candidate.get("parse_quality") or {}
        if isinstance(quality, dict) and isinstance(quality.get("score"), (int, float)) and quality["score"] < 55:
            flags.append("Resume parse quality is low and merits human review.")
        confidence = "low" if len(flags) >= 2 else "medium" if flags else "high"
        candidate["critique"] = {
            "confidence": confidence,
            "flags": flags,
            "summary": " ".join(flags) if flags else "No material ranking concern was detected by the rule-based review.",
            "human_review_recommended": bool(flags),
        }
    return ranked_candidates
