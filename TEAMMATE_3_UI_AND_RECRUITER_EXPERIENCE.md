# TEAMMATE 3 CONTEXT — Streamlit UI, Official Bonus Features & Candidate Outcomes

## Your Mission

You own the **end-to-end recruiter experience and final integration surface**.

The application should make the technical depth visible without becoming complicated.

You are responsible for:

1. Streamlit application.
2. Ranking dashboard.
3. Candidate detail/explanation UI.
4. Official recruiter comparison bonus.
5. JD bias / narrow-phrasing detector.
6. Candidate rejection draft.
7. Alternative role routing.
8. Integrating self-critique, counterfactual, interview probes, and team mode into a coherent demo.
9. Final demo reliability.

Read `MASTER_CONTEXT.md` first.

---

# 1. Primary Ownership

You own:

- `app.py`
- `ui/components.py`
- `src/jd_bias.py`
- `src/compare.py`
- `src/candidate_outcomes.py`
- `config/bias_rules.json`
- `config/role_clusters.json`

You may make small integration edits elsewhere only after coordinating with module owners.

---

# 2. UI Philosophy

The app should feel like:

> **Recruiter decision-support dashboard**

not:

> "random AI chatbot."

Prioritize:

- clear ranking;
- evidence;
- confidence;
- comparison;
- action.

Do not hide technical scoring behind vague language.

---

# 3. Proposed Main UI Flow

## Screen 1 — Input

```text
Smart Shortlisting Engine

[ Upload Job Description ]
[ Upload Resume PDFs      ]

[ Analyze Candidates ]
```

Include badge:

```text
100% Local Processing — No External APIs
```

Optional small text:

> Candidate files remain on the local machine during analysis.

Only claim this if implementation actually behaves that way.

---

# 4. Processing State

When user clicks Analyze:

Show simple stages:

```text
✓ Parsing JD
✓ Parsing resumes
✓ Extracting requirements
✓ Running keyword matching
✓ Running semantic matching
✓ Evaluating evidence authenticity
✓ Ranking candidates
✓ Running self-critique
```

Do not add artificial delays.

---

# 5. Main Ranking Dashboard

Use a table:

| Rank | Candidate | Final | Semantic | Keyword | Evidence | Confidence |
|---:|---|---:|---:|---:|---:|---|
| 1 | Candidate A | 88.4 | 90 | 84 | 92 | High |
| 2 | Candidate B | 86.1 | 88 | 87 | 81 | Medium |

Useful visual markers:

```text
🟢 High confidence
🟡 Medium confidence
🔴 Low confidence
```

Do not use color as the only signal; also show text.

Add:

- matched required count;
- missing required count;
- overqualification badge if flagged.

---

# 6. Candidate Detail Panel

For a selected candidate, display in this order:

## A. Summary

```text
Rank #2
Final Score: 86.1
Confidence: Medium
```

## B. Score Breakdown

```text
Semantic Relevance           88
Keyword Requirement Coverage 87
Evidence Authenticity        81
Related-Skill Graph          72
```

## C. Matched Requirements

Show:
- requirement;
- evidence strength;
- evidence snippet.

Example:

```text
React — Strong evidence
"Built a React dashboard for..."
```

## D. Missing Required Skills

Clearly separate.

## E. System Self-Critique

Example:

```text
⚠ Close ranking decision
⚠ Candidate has high semantic relevance but weaker explicit MongoDB evidence
```

## F. Interview Probes

3–5 questions.

## G. Counterfactual

```text
What would move this candidate into the Top 3?
```

Show simulated improvements.

Use strong label:

> **Simulation — not a hiring guarantee**

---

# 7. Top-3 Explanations

The official requirement expects short explanations.

Generate them deterministically from structured data.

Template:

```text
{candidate_name} ranks #{rank} with a score of {final_score}.

Strongest matches:
- {skill}: {evidence_summary}
- {skill}: {evidence_summary}

Missing/weak requirements:
- {skill}
- {skill}

Why the ranking is credible:
- Semantic relevance: {semantic}
- Explicit requirement coverage: {keyword}
- Evidence authenticity: {evidence}
```

Keep concise.

Never invent evidence.

---

# 8. Candidate Comparison — Official Bonus

Build a structured comparison mode.

UI:

```text
Compare Candidates

Candidate A [dropdown]
Candidate B [dropdown]

[ Compare ]
```

Function from `src/compare.py`:

```python
def compare_candidates(a: dict, b: dict, jd: dict) -> dict:
    ...
```

Return:

```python
{
    "score_difference": ...,
    "semantic_difference": ...,
    "keyword_difference": ...,
    "evidence_difference": ...,
    "a_unique_matches": [...],
    "b_unique_matches": [...],
    "a_missing": [...],
    "b_missing": [...],
    "explanation": "..."
}
```

Suggested explanation:

> Candidate A ranks above Candidate B mainly because A has stronger demonstrated evidence for Node.js and MongoDB, while both have similar semantic relevance.

No LLM/API needed.

---

# 9. Optional "Recruiter Questions" Without a Chatbot

Since APIs are disallowed, use buttons such as:

```text
[ Why is A above B? ]
[ What is A missing? ]
[ Is this ranking reliable? ]
[ What should I verify in interview? ]
```

These produce structured answers from existing data.

This gives a chat-like experience without pretending to support unrestricted natural language.

---

# 10. JD Bias / Overly Narrow Phrasing Detector

Function:

```python
def detect_jd_bias(jd_text: str) -> list[dict]:
    ...
```

Use rule-based phrase detection.

Example `config/bias_rules.json`:

```json
[
  {
    "pattern": "young and energetic",
    "reason": "Age-coded phrasing may unnecessarily narrow the applicant pool.",
    "suggestion": "Use 'motivated and proactive' or describe the actual work requirement."
  },
  {
    "pattern": "native english speaker",
    "reason": "Native-language status may be narrower than the communication requirement.",
    "suggestion": "Specify the required written/verbal English proficiency."
  },
  {
    "pattern": "rockstar",
    "reason": "Vague cultural language does not describe a measurable job requirement.",
    "suggestion": "Describe the actual technical or performance expectation."
  }
]
```

Avoid aggressive claims.

Use phrasing:

> "Potentially narrow phrasing"

instead of:

> "This JD is discriminatory."

---

# 11. Alternative Role Routing

Implement locally.

Function:

```python
def route_alternative_role(candidate: dict) -> dict:
    ...
```

Read strongest skills/evidence.

Possible clusters:

```text
Frontend-focused
Backend-focused
Data/analytics
DevOps/cloud
General software engineering
```

Output:

```python
{
    "cluster": "Backend-focused",
    "reason": "Strongest demonstrated evidence is in Node.js, REST APIs, and databases."
}
```

Do not claim a vacancy exists.

UI wording:

> **Potential stronger role direction**

---

# 12. Rejection / Non-Shortlist Draft

Function:

```python
def generate_rejection_draft(candidate: dict, jd: dict) -> str:
    ...
```

Because APIs are disallowed, use a professional template.

Example:

```text
Subject: Update on your application for {role}

Hi {candidate_name},

Thank you for your interest in the {role} opportunity. After reviewing the current role requirements, we will not be progressing your application for this specific position at this stage.

Your profile showed strengths in {strongest_area}. For this role, the main gaps were in {important_gaps}.

Based on the skills demonstrated in your resume, you may be better aligned with {alternative_role_direction} opportunities.

Thank you for your time and interest.

Regards,
Recruitment Team
```

Important:

- This is a **draft**.
- Recruiter should review before use.
- Avoid definitive claims if candidate name is uncertain.
- Never include sensitive/protected-trait reasoning.

UI button:

```text
[ Generate Candidate Communication Draft ]
```

---

# 13. Team Composition Mode UI

Use Teammate 2's result.

Separate tab:

```text
Individual Ranking | Compare | Team Composition | JD Review
```

Team Composition should show:

```text
Recommended 3-Person Team

Candidate A
- React
- Frontend
- UI

Candidate B
- Node.js
- Express
- REST APIs

Candidate C
- MongoDB
- Git
- Backend projects

Combined required-skill coverage: 96%
Remaining gap: Docker
```

Make it clear:

> This is an additional collaboration view; it does not replace the required individual ranking.

---

# 14. Overqualification UI

If teammate 2 flags:

```text
⚠ Role-level mismatch to review
```

Show reasons.

Do not display:

> "Reject: overqualified"

Use recruiter-support language.

---

# 15. Requirement Coverage Matrix

Strong optional visual if time allows.

Rows:
- candidates.

Columns:
- major JD requirements.

Cell states:

```text
Strong evidence
Weak/listed evidence
Related evidence
Missing
```

This can be simple dataframe styling.

It makes the system visually understandable in seconds.

---

# 16. Evidence Heatmap / Resume Snippets

If time allows:

Display top evidence snippets with strength bars.

Example:

```text
React                  ██████████  Strong
MongoDB                ███████░░░  Moderate
Git                    ███░░░░░░░  Listed only
Docker                 ░░░░░░░░░░ Missing
```

This makes Evidence Authenticity visible.

---

# 17. Streamlit State

Important: Streamlit reruns the script.

Use:

```python
st.session_state
```

to keep:

- parsed JD;
- ranked candidates;
- team result;
- selected candidates.

Use:

```python
@st.cache_resource
```

for local embedding model if model loading lives in app layer.

Use:

```python
@st.cache_data
```

for safe deterministic preprocessing where useful.

Do not cache unhashable large objects blindly.

---

# 18. Error Handling

UI should handle:

- no JD uploaded;
- no resumes uploaded;
- only one resume;
- invalid PDF;
- sparse resume;
- missing candidate name;
- parser warning.

Never show Python traceback in demo if avoidable.

Use:

```python
st.error(...)
st.warning(...)
```

---

# 19. Demo Reliability

Before final video:

1. Restart app fresh.
2. Upload all files.
3. Verify ranking loads.
4. Click Rank #1.
5. Click Rank #5 counterfactual.
6. Compare 2 candidates.
7. Open Team Composition.
8. Open JD Review.
9. Generate one interview probe set.
10. Generate one communication draft.

If any secondary feature is unstable:
- hide it before the demo;
- do not risk the core.

---

# 20. Suggested Navigation

Fastest:

```text
Sidebar:
- Overview
- Candidate Ranking
- Compare Candidates
- Team Composition
- JD Review
```

Or tabs:

```text
[ Ranking ] [ Compare ] [ Team Mode ] [ JD Review ]
```

Avoid multi-page complexity if time is short.

---

# 21. Landing Page Messaging

Recommended:

```text
Explainable Smart Shortlisting Engine

Hybrid semantic + keyword matching
Evidence-backed candidate scoring
Self-critiquing ranking confidence
100% local processing
```

Do not overuse "AI" everywhere.

---

# 22. Judge-Friendly Labels

Use technical terms judges can ask about:

```text
Semantic Relevance
Explicit Requirement Coverage
Evidence Authenticity
Skill-Graph Evidence
Critical Missing Requirements
Ranking Confidence
Counterfactual Simulation
```

This makes the architecture obvious from the UI.

---

# 23. Integration Contract With Teammate 1

Expect:

```python
candidate["name"]
candidate["rank"]
candidate["scores"]
candidate["requirement_matches"]
candidate["matched_required_skills"]
candidate["missing_required_skills"]
candidate["matched_preferred_skills"]
candidate["parse_quality"]
```

Do not duplicate their scoring logic in UI.

UI reads results.

---

# 24. Integration Contract With Teammate 2

Expect:

```python
candidate["critique"]
candidate["counterfactual"]
candidate["overqualification"]
candidate["interview_probes"]
```

Plus a separate:

```python
team_result
```

Gracefully handle missing fields during parallel development:

```python
candidate.get("critique", {})
```

so UI can be built before final merge.

---

# 25. Candidate Outcome Logic

For alternative role routing:

Use evidence-weighted skill clusters.

Example:

```python
cluster_score =
sum(
    evidence_strength
    for skill in cluster_skills
    if matched
)
```

Pick strongest cluster.

Rejection draft should use:

- candidate name;
- JD role title;
- top demonstrated strengths;
- 1–3 important role gaps;
- alternative role cluster.

---

# 26. What You Must NOT Do

Do not:

- call a text-generation API;
- change ranking scores for presentation;
- invent candidate evidence;
- hide missing requirements;
- infer protected characteristics;
- make role routing sound like a real job offer;
- spend hours on CSS;
- break working core logic to add animation.

---

# 27. Minimum Styling

Use Streamlit defaults plus:

- columns;
- metrics;
- expanders;
- progress bars;
- dataframe;
- tabs.

Polish should come from information hierarchy, not fancy CSS.

---

# 28. Recommended Demo Story

## 1. Problem

> Keyword-only screening misses semantically relevant candidates, while pure semantic systems can overlook hard skill requirements.

## 2. Core

Show:

```text
semantic + keyword + evidence authenticity + graph
```

## 3. Ranking

Show all candidates.

## 4. Trust

Open Rank #1:

- evidence;
- missing skill;
- self-critique.

## 5. Differentiation

Open mid-rank candidate:

> "What would move them into Top 3?"

## 6. Recruiter Action

Show interview probes.

## 7. Broader Intelligence

Show team composition.

## 8. Responsibility

Show JD narrow-phrasing detector.

## 9. Privacy

Finish:

> "Everything runs locally; no resume data is sent to an external API."

---

# 29. Definition of Done

- [ ] App accepts JD + resumes.
- [ ] Full ranking table renders.
- [ ] Score breakdown renders.
- [ ] Top-3 explanations are clear.
- [ ] Evidence snippets visible.
- [ ] Missing requirements visible.
- [ ] Self-critique visible.
- [ ] Counterfactual visible.
- [ ] Candidate comparison works.
- [ ] JD bias/narrow phrasing detector works.
- [ ] Team composition is integrated if stable.
- [ ] Overqualification flag visible.
- [ ] Interview probes visible.
- [ ] Alternative role routing works.
- [ ] Rejection draft is templated locally.
- [ ] No API/network call at runtime.
- [ ] App survives a fresh restart.
- [ ] No raw traceback in final demo.

---

# 30. Handoff Message to Team

When integration is complete, tell the team:

> UI consumes the shared candidate schema and does not modify ranking logic. All major differentiators are surfaced as recruiter actions: inspect evidence, review system critique, simulate Top-3 improvements, compare candidates, generate interview probes, inspect team composition, and review JD phrasing. Candidate communication is generated locally from templates.
