# TEAMMATE 2 — HANDOFF & ASSUMPTIONS LOG

> Status: **all six owned modules complete** (29/29 tests green, stdlib-only,
> no APIs). This file records the handoff message (TEAMMATE_2 #24), every
> assumption made while the core pipeline was unavailable, and the exact
> integration checklist. **Delete/merge this file after the team review.**

---

## 1. Handoff message to the team

Trust/innovation modules consume the core candidate schema
(`requirement_matches`, `scores`, `sections`, `parse_quality`,
`detected_skills`) and enrich it **in place**. The key UI fields are
`critique`, `counterfactual`, `overqualification`, `interview_probes`, plus
the separate team-composition result object. Skill-graph outputs are written
into each requirement match (`graph_*`) and into `scores.graph`, and should be
included **before** the final scoring/ranking pass.

## 2. Public interfaces delivered

| Function | File | Notes |
|---|---|---|
| `load_skill_graph(path=None)` | `src/skill_graph.py` | Loads `config/skill_graph.json`, symmetrizes (edges authored once, used undirected). |
| `apply_skill_graph(jd, candidate, graph=None)` | `src/skill_graph.py` | Writes `graph_match/graph_path/graph_score` per requirement + `scores.graph`. Idempotent. |
| `critique_ranking(jd, ranked_candidates)` | `src/critique.py` | Checks R1–R7 incl. local weight sensitivity. Sets `candidate["critique"]`. |
| `generate_counterfactual(candidate, ranked_candidates, jd, scorer=None)` | `src/counterfactual.py` | Sets `candidate["counterfactual"]`. **`scorer=` is the integration seam.** |
| `flag_overqualification(jd, candidate)` | `src/overqualification.py` | Sets `candidate["overqualification"]` = `{"flag", "reasons"}`. |
| `generate_interview_probes(jd, candidate)` | `src/probes.py` | Sets/returns `candidate["interview_probes"]` (≤5). |
| `find_best_team(jd, ranked_candidates, team_size=3)` | `src/team_mode.py` | Returns a separate serializable result (never mutates ranking). |

Run tests: `python tests/run_all.py` (no pytest, no third-party deps).

## 3. Assumptions & judgment calls (need one-time team sign-off)

Docs left ranges open; these are the values chosen, all constants at module top:

1. **Graph aggregation**: `scores.graph` counts a *directly keyword-matched*
   requirement as 100, others by capped indirect path score (cap **85**, depth
   **2 hops**). Direct matches do not get `graph_match: True` (that flag means
   "supported only by relation").
2. **R5 weight sensitivity**: computed locally from stored components with the
   pinned 0.45/0.35/0.15/0.05 blend; semantic/keyword presets renormalized
   across a fixed 0.80 share (evidence/graph untouched). Major instability =
   rank moves ≥ **2** positions or top-3 membership change.
3. **Critique thresholds**: sem/kw gap 25 minor / 35 major; weak evidence for
   top-3 at **< 60**; close margin **< 2.5 pts**; parse quality low **< 55**;
   skills-list concentration ≥ 60% of ≥ 3 matches (strength ≤ 0.35).
4. **Confidence rules**: LOW = 2+ major, or 1 major + 2 minor, or 4+ minor;
   MEDIUM = any major or minor; HIGH = none. `human_review_recommended` =
   confidence LOW or any major flag.
5. **Overqualification**: only runs when `role_level ∈ {intern, junior}`;
   years thresholds **5y (intern) / 7y (junior)**; compound title patterns
   only; leadership cues ≥ 3; education section **never** scanned. Flag only —
   no score impact anywhere.
6. **Team coverage**: a required requirement is "covered" only by an explicit
   `matched` with `evidence_strength ≥ 0.60`. Graph-only support never counts
   (tested guardrail). Scores use the documented 0.60/0.20/0.15/0.05 objective.
7. **Counterfactual conservatism**: semantic component held constant (can't
   re-embed offline), penalty held constant, gains capped at **3**
   improvements. Per-requirement gains are independent → greedy set is the
   exact minimal set. All simulated evidence text is prefixed
   `[simulated]` and never written back into the real candidate.
8. **Additive output keys**: beyond the contract's required keys, critique
   output is exactly the 4 schema keys, but `counterfactual` and the team
   result include extra display-friendly fields (`current_score`,
   `reached_target`, `message`, `disclaimer`, `member_scores`,
   `runner_up_teams`, ...). Nothing was renamed.

## 4. Integration checklist (when Teammate 1's core lands)

1. Pipeline order: `parse → requirements → keyword/semantic/evidence →
   **apply_skill_graph** → `score_candidate` → `rank_candidates` →
   `critique_ranking` → per-candidate `flag_overqualification`,
   `generate_interview_probes`, `generate_counterfactual`.
2. **Rerun the scorer after graph enrichment** (TEAMMATE_2 #18) so
   `scores.graph` feeds the 5% component before ranking.
3. One-line swap for full fidelity:
   `generate_counterfactual(cand, ranked, jd, scorer=score_candidate)`.
4. Verify conventions against real parser output:
   - `evidence_type` vocabulary (we accept `skills|skills_section|skills-list`,
     `project(s)`, `experience`, `certification(s)`, `other`, `none`)
   - `detected_skills` values match `config/skill_aliases.json` canonical names
     used in `config/skill_graph.json` keys (all lowercase, e.g. `node.js`)
   - `rank` is 1-based and `ranked_candidates` is rank-ordered (critique R4
     relies on both).
5. Confirm no double-counting complaint from Teammate 1: graph contribution
   stays at the agreed 5%.

## 5. Known limitations (honest list)

- Everything is validated against **fixtures**, not real PDFs, until T1 merges.
- Overqualification regexes are heuristic; unusual resume formatting may miss
  cues (acceptable: flag-only feature, recruiter decides).
- Counterfactual gains slightly conservative vs. the real scorer's penalty
  behavior until the `scorer=` seam is used.
- If Teammate 1 aggregates keyword/evidence differently than MASTER_CONTEXT
  #10/#11 describe, the counterfactual *deltas* remain correct (they are
  self-consistent recomputations) but swap to the injected scorer before demo.

## 6. Definition of Done — Teammate 2 tracker

- [x] Skill graph returns explainable paths (tests B, depth/cap)
- [x] Graph score small and bounded (85 cap; 5% weight untouched here)
- [x] Red-team flags deterministic and meaningful (R1–R7)
- [x] Confidence levels understandable (rule table, tested)
- [x] Ranking sensitivity works (presets, rank range, top-3 stability)
- [x] Counterfactual Top-3 simulation works (scenario E exact-gain tests)
- [x] Counterfactual can use core scorer (`scorer=` seam, tested with injected fake)
- [x] Team composition returns valid trio (complementarity beats generalist, tested)
- [x] Overqualification avoids protected attributes (no education scan, tested)
- [x] Interview probes tied to actual evidence gaps (5 priority passes, tested)
- [x] All outputs serializable (round-trip test in e2e pipeline test)
- [x] No API calls (automated source audit test)
- [x] Teammate 3 can render outputs from schema alone (field shapes asserted in tests)
- [ ] Integration pass with real core (blocked until Teammate 1 merges — see #4)
