"""One-shot scale check: full trust layer over every real resume PDF.

Not part of the test suite (slow by design). Run from repo root:
    python tests/scale_check.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline import parse_candidate_from_pdf
from src.schemas import candidate_to_json
from src.trust_pipeline import build_jd, run_trust_layer

JD_TEXT = """
Job Title: Junior Full Stack Developer Intern
Requirements:
- Must have strong experience with React and Node.js.
- Required: Proficient in MongoDB database design.
- Must be able to build and consume REST API services.
- Preferred: Familiarity with Docker and AWS.
"""

def main():
    t0 = time.time()
    pdfs = sorted((ROOT / "data" / "resumes").glob("*.pdf"))
    print(f"{len(pdfs)} PDFs found")

    candidates, failures = [], []
    for p in pdfs:
        c = parse_candidate_from_pdf(str(p))
        (candidates if c["clean_text"].strip() else failures).append(c)
    print(f"parse failures: {[c['file_name'] for c in failures] or 'none'}")

    jd = build_jd(JD_TEXT)
    ranked, team = run_trust_layer(jd, candidates)

    # Full serialization round trip over the entire batch
    json.loads(json.dumps({"ranked_candidates": ranked, "team_result": team}))
    for c in ranked[:1]:
        candidate_to_json(c)

    print(f"FULL PIPELINE OK: {len(ranked)} candidates enriched + serialized in {time.time()-t0:.1f}s")
    print("team:", team["members"], "| score:", round(team["team_score"], 1),
          "| gaps:", team["remaining_gaps"] or "none")
    print("top 5:")
    for c in ranked[:5]:
        print(f"  #{c['rank']} {c['name']:<28} final={c['scores']['final_score']:6.2f} "
              f"graph={c['scores']['graph']:5.1f} conf={c['critique']['confidence']}")
    print("bottom 3:")
    for c in ranked[-3:]:
        print(f"  #{c['rank']} {c['name']:<28} final={c['scores']['final_score']:6.2f} "
              f"conf={c['critique']['confidence']}")
    flagged = sum(1 for c in ranked if c["overqualification"]["flag"])
    needs_review = sum(1 for c in ranked if c["critique"]["human_review_recommended"])
    avg_probes = sum(len(c["interview_probes"]) for c in ranked) / max(1, len(ranked))
    print(f"overqualification flags: {flagged} | human-review recommended: {needs_review} "
          f"| avg probes/candidate: {avg_probes:.1f}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
