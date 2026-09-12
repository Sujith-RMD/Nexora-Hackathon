"""Offline PDF batch runner: same trust pipeline used by the recruiter app."""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.pdf_parser import parse_pdf_with_metadata
from src.pipeline import parse_candidate_from_pdf
from src.trust_pipeline import build_jd, run_trust_layer
from src.jd_bias import detect_jd_bias
from src.candidate_outcomes import route_alternative_role


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jd", required=True, type=Path)
    parser.add_argument("--resumes", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    paths = sorted(p for p in args.resumes.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    if not paths:
        parser.error("No resume PDFs found.")
    parsed = parse_pdf_with_metadata(str(args.jd))
    text = str(parsed["text"])
    jd = build_jd(text, title=text.splitlines()[0] if text else "")
    if not text.strip() or not jd["requirements"]:
        parser.error("The JD has no readable, recognized requirements.")
    jd["bias_flags"] = detect_jd_bias(text)
    candidates = [parse_candidate_from_pdf(str(p), candidate_id=f"C{i + 1:03d}") for i, p in enumerate(paths)]
    ranked, team = run_trust_layer(jd, candidates)
    for candidate in ranked:
        route_alternative_role(candidate)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "latest_results.json").write_text(json.dumps({"jd": jd, "ranked_candidates": ranked, "team": team}, indent=2, allow_nan=False), encoding="utf-8")
    fields = ["rank", "candidate_id", "name", "final_score", "semantic", "keyword", "evidence", "graph", "matched_required", "missing_required", "parse_quality"]
    with (args.output / "ranking.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for candidate in ranked:
            row = {key: candidate[key] for key in ("rank", "candidate_id", "name")}
            row.update({key: candidate["scores"][key] for key in ("final_score", "semantic", "keyword", "evidence", "graph")})
            row.update(matched_required="; ".join(candidate["matched_required_skills"]), missing_required="; ".join(candidate["missing_required_skills"]), parse_quality=candidate["parse_quality"]["score"])
            writer.writerow(row)
            print(f"{row['rank']:3} {row['final_score']:6.2f}  {row['name']}")
    print(f"Saved {len(ranked)} candidates to {args.output}")


if __name__ == "__main__":
    main()
