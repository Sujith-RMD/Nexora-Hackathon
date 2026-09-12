# TEAMMATE 2 CONTEXT — Trust Layer, Skill Graph & Advanced Ranking Features

## Your Mission

You own the features that make this project feel **different from a normal resume scorer**.

You consume the core structured candidate results from Teammate 1 and add:

1. Requirement/Skill Graph.
2. Self-Critiquing / Red-Team Ranking.
3. Counterfactual / Coaching Ranking.
4. Team Composition Mode.
5. Over-Qualification Flag.
6. Interview Probe Generator.

Read `MASTER_CONTEXT.md` first. Do not re-parse PDFs unless absolutely necessary.

---

# 1. Your Primary Ownership

You own:

- `src/skill_graph.py`
- `src/critique.py`
- `src/counterfactual.py`
- `src/team_mode.py`
- `src/overqualification.py`
- `src/probes.py`
- `config/skill_graph.json`

Your modules should consume:

```python
jd
ranked_candidates
candidate["requirement_matches"]
candidate["scores"]
candidate["sections"]
candidate["parse_quality"]
```

and enrich candidate objects.

---

# 2. Critical Rule — Do Not Build a Second Ranking Engine

Teammate 1 owns the core score.

You may:

- add graph contribution through the shared scoring contract;
- run score simulations for counterfactuals;
- test weight sensitivity for critique.

You should **not** invent a separate hidden score that conflicts with the core ranking.

---

# 3. Requirement / Skill Graph

## Goal

Model relationships like:

```text
JavaScript
   |
 Node.js
   |
 Express
   |
 REST API
   |
 MongoDB
```

The point is not to create a huge ontology.

The point is to answer:

> "Why can this related experience count as partial evidence?"

and make that connection explainable.

---

# 4. Graph Scope

Keep graph focused on technologies likely relevant to the sample Junior Full Stack Developer Intern JD.

Possible nodes:

### Frontend

```text
javascript
typescript
react
html
css
frontend development
responsive design
```

### Backend

```text
node.js
express
rest api
backend development
server-side development
```

### Databases

```text
mongodb
nosql
sql
mysql
postgresql
database
```

### Tooling

```text
git
github
version control
```

### General

```text
full stack development
web development
api development
```

Add only useful relationships.

---

# 5. Graph Representation

Option A — JSON adjacency:

```json
{
  "node.js": [
    {
      "target": "javascript",
      "relation": "built_on",
      "weight": 0.85
    },
    {
      "target": "express",
      "relation": "commonly_used_with",
      "weight": 0.85
    }
  ]
}
```

Option B — `networkx`.

Simple JSON is easier to inspect and explain.

---

# 6. Graph Matching

Function:

```python
def apply_skill_graph(jd: dict, candidate: dict, graph) -> dict:
    ...
```

For each unmet/weak requirement:

1. Look at candidate's detected skills.
2. Search paths of length 1–2.
3. Compute a decayed relationship score.
4. Preserve the path.

Example:

```python
{
    "requirement_id": "req_rest_api",
    "graph_match": True,
    "graph_path": ["express", "rest api"],
    "graph_score": 78
}
```

Decay idea:

```text
direct graph neighbor = weight * 100
2-hop path = product(edge weights) * 100
```

Limit depth to prevent nonsense.

---

# 7. Graph Guardrails

A graph relation is **supporting evidence**, not proof.

Bad:

> JD requires MongoDB, candidate knows MySQL, therefore requirement fully satisfied.

Good:

> Candidate has database experience, but explicit MongoDB evidence is missing.

Graph component should remain small in final score.

Recommended global contribution:

```text
5%
```

---

# 8. Self-Critiquing / Red-Team Ranking

## Goal

Most systems output a ranking confidently.

Ours should ask:

> "What could make this ranking wrong?"

Function:

```python
def critique_ranking(
    jd: dict,
    ranked_candidates: list[dict]
) -> list[dict]:
    ...
```

Populate:

```python
candidate["critique"] = {
    "confidence": "high|medium|low",
    "flags": [...],
    "summary": "...",
    "human_review_recommended": bool
}
```

---

# 9. Red-Team Checks

Implement simple, transparent checks.

## R1. Semantic vs Keyword Disagreement

```python
gap = abs(
    candidate["scores"]["semantic"]
    - candidate["scores"]["keyword"]
)
```

Suggested:

```text
gap >= 25 -> flag
gap >= 35 -> stronger flag
```

Possible explanation:

> "High semantic relevance but relatively low explicit requirement coverage."

---

## R2. High Rank With Weak Evidence

If candidate is top 3 but:

```text
evidence score < 55–60
```

flag:

> "This candidate ranks highly, but much of the match is weakly demonstrated."

---

## R3. Missing Required Skill

If high rank and missing one or more high-weight required skills:

> "Strong overall similarity may be masking a missing explicit requirement."

---

## R4. Close Ranking Margin

If neighboring candidates differ by e.g. < 2.5 points:

> "Ranks #2 and #3 are effectively a close decision."

This is excellent for honesty.

---

## R5. Weight Sensitivity

Re-score candidates with safe variants.

Example presets:

```python
presets = [
    {"semantic": 0.55, "keyword": 0.45},
    {"semantic": 0.45, "keyword": 0.55},
    {"semantic": 0.60, "keyword": 0.40},
    {"semantic": 0.40, "keyword": 0.60}
]
```

When doing this, either:
- temporarily ignore evidence/graph for the sensitivity sub-test; or
- keep their weights fixed and vary only semantic/keyword portions proportionally.

Measure:

- rank range;
- number of rank changes;
- top-3 stability.

Example:

```python
{
    "rank_min": 1,
    "rank_max": 4,
    "stable_top3": False
}
```

Flag significant instability.

---

## R6. Parse Quality

If parser quality low:

> "Ranking confidence reduced because resume extraction quality is low."

Do not penalize hard unless team agrees.

---

## R7. Skills-List Concentration

If a candidate's matched skills are mostly "Skills section only":

> "Keyword coverage is high, but demonstrated project/work evidence is limited."

This supports the Evidence Authenticity differentiator.

---

# 10. Confidence Level Logic

Example:

```text
HIGH
- no major critique flags
- stable under weights
- strong evidence
- good parse quality

MEDIUM
- one meaningful warning
- close score margin
- moderate evidence

LOW
- multiple warnings
- unstable ranking
- poor parsing
- major semantic/keyword contradiction
```

Keep rules deterministic.

---

# 11. Counterfactual / Coaching Ranking

Function:

```python
def generate_counterfactual(
    candidate: dict,
    ranked_candidates: list[dict],
    jd: dict
) -> dict:
    ...
```

Target:

```python
target_score = ranked_candidates[2]["scores"]["final_score"] + 0.1
```

for Top 3.

If candidate already Top 3:
- target next rank if useful;
- or state they are already Top 3.

---

# 12. Counterfactual Candidate Improvements

Potential simulated improvements:

1. Missing high-weight required skill becomes strong demonstrated evidence.
2. Weak evidence skill becomes project/work evidence.
3. Related graph-only evidence becomes direct evidence.

Estimate component gains using the actual scorer.

Best architecture:

```python
simulate_candidate(candidate, change)
-> scorer.score_candidate(...)
```

Do not manually invent final score if scorer can be reused.

---

# 13. Counterfactual Search

Because feature space is tiny:

1. Build candidate improvements.
2. Evaluate each individually.
3. Sort by score gain.
4. Try combinations of 2 if necessary.
5. Stop when target crossed.

Output:

```python
candidate["counterfactual"] = {
    "target_rank": 3,
    "target_score": 82.7,
    "suggested_improvements": [
        {
            "requirement": "MongoDB",
            "change": "Add demonstrated project/work evidence",
            "estimated_gain": 3.6
        }
    ],
    "projected_score": 83.1
}
```

Important UI wording:

> "Model simulation — not a hiring guarantee."

---

# 14. Team Composition Mode

Function:

```python
def find_best_team(
    jd: dict,
    ranked_candidates: list[dict],
    team_size: int = 3
) -> dict:
    ...
```

Use:

```python
from itertools import combinations
```

For each trio:

### Coverage

Union of required skills with sufficient evidence.

### Evidence

For each requirement, take the strongest evidence among team members.

### Semantic Relevance

Average or median candidate semantic score.

### Complementarity

Reward when different team members uniquely contribute requirements.

Suggested:

```python
team_score = (
    0.60 * coverage_score +
    0.20 * evidence_score +
    0.15 * semantic_score +
    0.05 * complementarity_score
)
```

Return:

```python
{
    "members": ["C01", "C05", "C12"],
    "team_score": 91.4,
    "required_skill_coverage": 96.0,
    "member_contributions": {
        "C01": [...],
        "C05": [...],
        "C12": [...]
    },
    "remaining_gaps": [...]
}
```

This is a secondary mode only.

---

# 15. Over-Qualification Flag

Function:

```python
def flag_overqualification(jd: dict, candidate: dict) -> dict:
    ...
```

Use role-level cues.

If JD:

```text
intern / junior
```

then detect resume cues:

```text
senior
lead
staff engineer
principal
engineering manager
architect
X years of experience
```

Be cautious.

Output:

```python
{
    "flag": True,
    "reasons": [
        "Resume contains multiple senior-level titles"
    ]
}
```

Avoid:
- age inference;
- graduation-year age estimates;
- demographic assumptions.

### Important

Prefer flagging rather than heavy score penalty.

Let recruiter decide.

---

# 16. Interview Probe Generator

Function:

```python
def generate_interview_probes(
    jd: dict,
    candidate: dict
) -> list[str]:
    ...
```

Maximum:

```text
3–5 questions
```

Priority:

1. Required skill with weak evidence.
2. Skill only listed in Skills section.
3. Graph-only match.
4. Semantic-high/keyword-low ambiguity.
5. Critique flag.

---

# 17. Probe Templates

## Skills List Only

```python
"You list {skill} under Skills. Can you describe a project where you personally used it and what you implemented?"
```

## Graph Match

```python
"Your resume shows experience with {related_skill}, which is related to {required_skill}. How much direct experience do you have with {required_skill}?"
```

## Missing Explicit Tool

```python
"Your experience appears relevant to {requirement}, but the exact tool is unclear. Which technologies did you use?"
```

## Weak Project Evidence

```python
"Can you explain your specific contribution to the project involving {skill}?"
```

---

# 18. Integration Contract With Teammate 1

You expect:

```python
candidate["requirement_matches"]
candidate["scores"]
candidate["sections"]
candidate["parse_quality"]
candidate["matched_required_skills"]
candidate["missing_required_skills"]
candidate["rank"]
```

If a field is missing:
- coordinate;
- do not silently create incompatible alternatives.

Skill graph integration requires updating:

```python
candidate["requirement_matches"][i]["graph_*"]
candidate["scores"]["graph"]
```

Then scorer/ranker should be rerun.

---

# 19. Integration Contract With Teammate 3

Teammate 3 needs your outputs to display.

Expose:

```python
candidate["critique"]
candidate["counterfactual"]
candidate["overqualification"]
candidate["interview_probes"]
```

Team mode should return a separate serializable object.

Avoid raw networkx objects in UI output.

---

# 20. Suggested Development Order

Do in this order:

1. Skill graph JSON.
2. Graph matcher.
3. Feed graph score into scorer.
4. Red-team simple checks.
5. Ranking sensitivity check.
6. Counterfactual.
7. Overqualification.
8. Interview probes.
9. Team mode.

Why:
- graph needs core integration;
- critique/counterfactual create strongest differentiation;
- team mode is impressive but secondary.

---

# 21. Fast Test Scenarios

## Test A — High Keyword, Low Evidence

Candidate:
- lots of skills listed;
- no projects.

Expect:
- authenticity warning;
- lower confidence;
- interview probes.

## Test B — Hidden Semantic Match

Candidate:
- Express/REST project;
- no exact "backend development" phrase.

Expect:
- skill graph supports relation;
- semantic score strong;
- explanation gives graph path.

## Test C — Close Candidates

Scores:
- 84.2
- 83.6

Expect:
- self-critique says close decision.

## Test D — Weight Instability

Candidate #2 becomes #5 under keyword-heavy weighting.

Expect:
- confidence reduced.

## Test E — Counterfactual

Rank #6 lacks MongoDB and REST API.

Expect:
- simulated gain;
- minimal change set shown.

## Test F — Team Mode

One candidate frontend-heavy, one backend-heavy, one database-heavy.

Expect:
- trio scores highly due to complementary coverage.

---

# 22. What You Must NOT Build

Do not:
- create UI pages;
- rewrite PDF parsing;
- invent free-form LLM reasoning;
- call APIs;
- make graph paths longer than necessary;
- silently change core scoring weights without team agreement.

---

# 23. Definition of Done

- [ ] Skill graph returns explainable paths.
- [ ] Graph score is small and bounded.
- [ ] Red-team flags are deterministic and meaningful.
- [ ] Confidence levels are understandable.
- [ ] Ranking sensitivity works.
- [ ] Counterfactual Top-3 simulation works.
- [ ] Counterfactual uses core scorer.
- [ ] Team composition returns valid trio.
- [ ] Overqualification flag avoids protected attributes.
- [ ] Interview probes are tied to actual evidence gaps.
- [ ] All outputs are serializable.
- [ ] No API calls.
- [ ] Teammate 3 can render outputs without reading your internal code.

---

# 24. Handoff Message to Team

When done, tell the team:

> Trust/innovation modules consume the core candidate schema and enrich it in place. The key UI fields are `critique`, `counterfactual`, `overqualification`, `interview_probes`, plus the separate team-composition result. Skill-graph outputs are written into each requirement match and should be included before the final scoring/ranking pass.
