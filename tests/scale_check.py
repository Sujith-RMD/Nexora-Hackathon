"""One-shot scale check: full trust layer over every real resume PDF.

Not part of the test suite (slow by design). Run from repo root:
    python tests/scale_check.py
"""
import json
import sys
import time
import socket
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.pipeline import parse_candidate_from_pdf
from src.schemas import candidate_to_json
from src.trust_pipeline import build_jd, run_trust_layer

JD_TEXT = """
Job Title: Junior Full Stack Developer Intern
Requirements:
- Must have strong programming knowledge in Python or JavaScript.
- Required: Hands-on experience developing web applications with React or Node.js.
- Must know database management with MongoDB or PostgreSQL.
- Preferred: REST API and Git.
- Docker is a bonus.
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
    assert pdfs, "No demo resume PDFs found"
    assert not failures, "Some demo PDFs failed to parse"

    jd = build_jd(JD_TEXT)
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Runtime network forbidden")), patch.object(socket, "create_connection", side_effect=AssertionError("Runtime network forbidden")):
        ranked, team = run_trust_layer(jd, candidates)
    assert len(ranked) == len(pdfs)
    assert len([r for r in jd["requirements"] if r["importance"] == "required"]) == 3
    for c in ranked:
        assert c["scores"]["keyword"] >= 0 and c["scores"]["semantic"] >= 0
        assert len(c["requirement_matches"]) == len(jd["requirements"])
        assert c["score_adjustments"]["critical_missing_penalty"] <= 10
        assert not any("[simulated]" in m["evidence_text"] for m in c["requirement_matches"])
    results_dir = ROOT / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "offline_scale_results.json").write_text(json.dumps({"jd": jd, "ranked_candidates": ranked, "team": team}, indent=2, allow_nan=False), encoding="utf-8")

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
