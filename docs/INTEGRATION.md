# Branch integration and demo handoff

Integration date: 2026-09-12. Local branch: `codex/integrated-demo`.

## Branch audit

| Remote branch | Reviewed revision | Integration |
|---|---|---|
| main | 96e685b | Shared architecture and teammate contracts retained |
| teammate-1 | 0b957ab | Core parsing, requirement extraction, matching, evidence, scoring and ranking |
| teammate2 | d55d413 | Full graph, critique, counterfactual, probes, overqualification, team selection and tests |
| teammate-3 | 1825fe7 | Streamlit UI, comparison, bias rules, role routing, draft generation and tests |

All four tips are ancestors of the integration branch. Teammate 3 had already merged Teammate 1. Its simpler trust implementations conflicted with Teammate 2's fuller implementations; the latter were retained, and the UI now invokes `run_trust_layer`. The Desktop checkout, its environment, and remote branches were not modified. Nothing was pushed.

## Reconciled behavior

- OR requirements have additive `alternatives` and `match_mode: "any"` fields. Keyword and evidence layers take the best alternative once; semantic matching takes the strongest alternative query. Graph matching can explain paths to either alternative. AND clauses and separate mandatory occurrences remain independent.
- `must know` is mandatory. Explicit required/preferred headings, wrapped OR lines and comma-separated OR lists are supported. Missing-required penalties apply once per unsatisfied group, capped at 10 points.
- The original shared dictionary keys and the 45/35/15/5 blend remain intact. Additional fields expose matched alternatives, semantic passages and score adjustments.
- Evidence snippets come from the sentence used to assign strength and its actual section. Skills on inline headings retain their skills-list evidence tier. Semantic-only passages are presented separately from direct evidence.
- The actual SentenceTransformer is loaded locally only. The UI's silent hashed-token fallback was removed. Streamlit and Hugging Face telemetry are disabled.
- Upload display names and original filenames survive temporary staging. Each upload has a distinct deterministic ID, including duplicate filenames.
- Team contribution reporting now uses the selected team's coverage maps. UI team fields now match Teammate 2's ID/name-based output.
- Counterfactuals use final rescored values, including capped penalty relief. Small improvement sets are enumerated up to three changes, and originals remain untouched. The adapter matches the graph layer's required/preferred aggregation denominator.
- Zero parse quality now triggers critique. Comparison imports work in the user's Python 3.9 environment.
- UI required counts exclude preferred/context requirements. A failed analysis clears previous results. A sample-demo button and JSON download support demonstration; the batch runner exports JSON/CSV.

## Verification and scope

Tests use the real local embedding model, including a cold load with Python outbound connections blocked. Streamlit AppTest exercises populated tabs, candidate selection, comparison validation, the full 54-resume sample button and failed-analysis state clearing. The scale check verifies all 54 sample PDFs parse and all candidates are enriched and JSON serializable under blocked outbound sockets.

Recorded final validation: the standard suite passed 41/41 tests; the separate teammate suite passed 34/34 checks (some cross-team tests overlap). The all-54 blocked-network scale run completed in 4.7 seconds with no parse failures. JSON/CSV export succeeded for all 54 candidates. A fresh Streamlit server and browser run completed the sample analysis and showed the ranked candidates and evidence. Git whitespace/conflict checks passed. Non-failing dependency warnings remain for the system Python's LibreSSL and PyMuPDF SWIG metadata.

Official organizer JD/resumes have not been validated because they are not present. The synthetic JD encodes the planned three OR groups (Python/JavaScript, React/Node.js, MongoDB/PostgreSQL), preferred REST API/Git and bonus Docker. Its output is a regression demonstration, not a validated hiring outcome. Exact scores can differ with JD wording and library/model versions. No claim of correctness for every possible PDF or free-form JD is implied.
