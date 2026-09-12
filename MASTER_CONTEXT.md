# MASTER CONTEXT — InternLoom AI Hackathon
## Project: Explainable Offline Smart Shortlisting Engine

> This file is the single source of truth for all three teammates/agents.  
> Every module must obey the interfaces, constraints, naming, and integration rules defined here.

---

## 1. Problem We Are Solving

Build a system that accepts:

- **1 Job Description PDF**
- **A batch of 15–18 resume PDFs**

and produces:

1. A **ranked list of every candidate**, best fit to worst fit.
2. A **final score** for each candidate.
3. A genuinely hybrid ranking that uses both:
   - **Semantic matching** — meaning/context similarity.
   - **Keyword/explicit requirement matching** — exact or normalized technologies, skills, tools, and terms.
4. For the **top 3 candidates**, a short explanation containing:
   - Why they ranked highly.
   - Skills/requirements that matched.
   - Important required skills that appear to be missing.

The hackathon explicitly does **not** accept a solution that simply gives a resume + JD to an LLM and asks for a score. Our own pipeline must perform the matching and ranking.

---

## 2. Judging Priorities

Optimize engineering effort in this order:

| Criterion | Weight |
|---|---:|
| Effective semantic + keyword matching | 35% |
| Quality/sensibility of ranking | 20% |
| Accuracy/clarity of top-3 explanations | 20% |
| Working end-to-end demo | 15% |
| Bonus features | 10% |

The core ranking must remain the most reliable part of the product.

---

## 3. Hard Constraints

### 3.1 No External APIs

**No API calls are allowed.**

This means:

- No OpenAI API.
- No Gemini API.
- No Claude API.
- No hosted embedding API.
- No external inference API.
- No remote OCR/API service.
- No API-based email generation.
- No API-based chatbot.

Everything must run locally using Python libraries and locally downloaded models.

### 3.2 Runtime Must Be Offline-Capable

Allowed examples:

- `PyMuPDF` / `pdfplumber`
- `sentence-transformers`
- local `all-MiniLM-L6-v2`
- `scikit-learn`
- `numpy`
- `pandas`
- `networkx`
- `streamlit`
- `plotly` if already installed/downloadable
- Python `re`, `json`, `itertools`, etc.

**Important:** download/cache the local embedding model before the final demo. Runtime should not require internet access.

### 3.3 Explainability Is Mandatory

Every important ranking decision should be traceable to:

- JD requirement.
- Resume evidence.
- Semantic score.
- Keyword score.
- Evidence strength.
- Missing/uncertain requirements.
- Any penalty/adjustment.

Never show unexplained "AI score = 91".

---

# 4. Product Positioning

Our differentiator is not "we used AI."

Our pitch is:

> **A privacy-preserving, fully local hiring decision-support engine that does not merely count skills. It checks whether skills are demonstrated, challenges its own ranking, explains uncertainty, models related technologies, and shows what evidence would change the outcome.**

Core principles:

1. **Local-first**
2. **Explainable**
3. **Evidence-backed**
4. **Self-critical**
5. **Human-in-the-loop**
6. **Deterministic enough to defend before judges**

---

# 5. Final Feature Set

## 5.1 Mandatory Core

- PDF parsing.
- JD parsing.
- Resume parsing.
- Text normalization.
- Requirement extraction.
- Skill normalization/synonyms.
- Keyword matching.
- Local semantic embedding matching.
- Hybrid scoring.
- Full ranking.
- Top-3 explanations.

## 5.2 Official Bonus Features

Implement if stable:

- JD bias / overly narrow phrasing detector.
- Recruiter comparison / "Why X above Y?" interaction.
- Graceful handling of messy/inconsistent resume formatting.

## 5.3 Our Differentiators

### D1. Self-Critiquing / Red-Team Ranking

The system actively tests whether its own ranking may be unreliable.

Examples of critique triggers:

- Semantic score and keyword score strongly disagree.
- Candidate is high-ranked but important skills have weak evidence.
- Candidate's score is extremely close to the next candidate.
- Candidate's position changes significantly when reasonable weights change.
- Resume parsing quality is low.
- Critical skill is missing despite high semantic similarity.
- Candidate may be overqualified for an intern/junior role.

Output:

```python
{
    "confidence": "high|medium|low",
    "critique_flags": [...],
    "critique_summary": "...",
    "human_review_recommended": True
}
```

Important:
- The critic should **not invent new facts**.
- It should reason only from existing structured scores/evidence.
- Prefer transparent rules to complex heuristics.

---

### D2. Evidence Authenticity Scoring

Do not treat:

> `"React"` in a Skills list

as equivalent to:

> `"Built a React dashboard used in a project"`

For every matched requirement, assign evidence strength.

Recommended evidence levels:

| Evidence type | Strength |
|---|---:|
| Demonstrated in project/work experience with action/context | 1.00 |
| Mentioned in project/experience but weak context | 0.75 |
| Mentioned in multiple resume sections | 0.60 |
| Listed only in Skills section | 0.35 |
| Fuzzy/graph-related evidence only | 0.20–0.50 |
| No evidence | 0.00 |

Store exact supporting text snippets.

Example:

```python
{
    "skill": "react",
    "matched": True,
    "strength": 1.0,
    "evidence_type": "project",
    "evidence_text": "Built a responsive dashboard using React.js..."
}
```

This is a core trust layer, not decorative UI.

---

### D3. Counterfactual / Coaching Ranking

For a selected candidate:

> "What would need to change for this candidate to reach the Top 3?"

Procedure:

1. Find the current score required to reach rank 3.
2. Identify missing/weak high-value requirements.
3. Simulate improving one requirement at a time.
4. Recompute the score.
5. Find the smallest realistic set of improvements that crosses the threshold.

Output example:

> Candidate #7 could approximately reach the current Top-3 threshold by adding strong demonstrated evidence for **MongoDB** and **REST API development**.

Never present hypothetical additions as facts. Clearly label them as simulated.

---

### D4. Requirement / Skill Graph

Represent technology relationships instead of treating all skills as isolated strings.

Example relationships:

```text
JavaScript -> Node.js -> Express -> REST API
MongoDB -> NoSQL Database
React -> Frontend Development
Git -> Version Control
```

Edge types may include:

- `framework_of`
- `commonly_used_with`
- `implements`
- `related_to`
- `specialization_of`
- `database_type`
- `frontend_backend_relation`

Graph use cases:

1. Explain semantic/related matches.
2. Improve fuzzy skill coverage.
3. Show why a non-exact skill is still relevant.
4. Support alternative role routing.

Graph matches must **never completely replace explicit required skills**.

Example:

> JD asks for backend API development. Resume states Express + RESTful services. The graph supports this as related evidence even if the exact phrase "backend API development" is absent.

---

### D5. Team Composition Mode

Secondary mode only.

Do **not** replace individual ranking.

Question:

> "Which 3 candidates together cover the JD requirements best?"

For 18 candidates, brute-force all 3-person combinations is only:

`C(18,3) = 816`

which is trivial.

Recommended objective:

```text
team_score =
  0.60 * unique_required_skill_coverage
+ 0.20 * average_evidence_strength
+ 0.15 * average_semantic_relevance
+ 0.05 * complementary_skill_bonus
```

Return:

- Best trio.
- Combined coverage.
- Requirements uniquely contributed by each member.
- Remaining gaps.

---

### D6. Over-Qualification Flag

This should primarily be a **flag**, not an automatic large ranking penalty.

Why:

- The supplied role is a Junior Full Stack Developer Intern.
- A very senior candidate may dominate similarity scores while being a questionable fit for role level.

Possible signals:

- Multiple senior/lead/staff titles.
- Many years of experience relative to an intern role.
- Leadership-heavy resume with little junior-role alignment.
- Explicit advanced seniority language.

Output:

```python
{
    "overqualification_flag": True,
    "reasons": [
        "Multiple senior-level titles detected",
        "Experience level appears substantially above role level"
    ]
}
```

Avoid age-based or demographic assumptions.

---

### D7. Interview Probe Generator

Convert uncertainty into recruiter action.

Generate **targeted verification questions** based on:

- Weak evidence.
- Missing evidence.
- Skill listed only in Skills section.
- Semantic/keyword disagreement.
- Self-critique flags.

Examples:

- "You list MongoDB under Skills. Can you describe a project where you designed or queried a MongoDB schema?"
- "Your resume mentions REST APIs indirectly. What API endpoints did you personally implement?"
- "What part of the React application did you own?"

No LLM/API is required. Use templates.

---

### D8. Rejection Email + Alternative Role Routing

No external text-generation API.

Use deterministic templates.

For non-shortlisted candidates:

1. Generate a neutral rejection/deselection draft.
2. Suggest a **possible role direction**, not a real available vacancy.

Example role clusters:

- Frontend-focused
- Backend-focused
- Data/analytics
- DevOps/cloud
- General software engineering

Important wording:

> "Based on the resume's strongest demonstrated skills, the candidate may be better aligned with backend-focused opportunities."

Do **not** claim:
- that another opening exists;
- that a hiring decision is final unless the user explicitly decides;
- personal demographic inference.

---

# 6. Recommended Local Architecture

```text
JD PDF + Resume PDFs
        |
        v
PDF Extraction
        |
        v
Cleaning + Section Detection
        |
        +----------------------------+
        |                            |
        v                            v
Requirement Extraction         Resume Evidence Extraction
        |                            |
        +-----------+----------------+
                    |
        +-----------+-----------+
        |                       |
        v                       v
Keyword Matcher          Local Semantic Matcher
        |                       |
        +-----------+-----------+
                    |
                    v
          Evidence Authenticity Layer
                    |
                    v
            Requirement Skill Graph
                    |
                    v
             Hybrid Core Scorer
                    |
                    v
             Full Candidate Rank
                    |
     +--------------+---------------+
     |              |               |
     v              v               v
Self-Critique   Counterfactual   Team Composition
     |              |               |
     +--------------+---------------+
                    |
                    v
     Explanations / Interview Probes
                    |
                    v
              Streamlit UI
```

---

# 7. Shared Data Contracts — DO NOT BREAK THESE

All teammates should integrate through a common Python dictionary/dataclass structure.

## 7.1 JD Schema

```python
jd = {
    "title": str,
    "raw_text": str,
    "clean_text": str,

    "requirements": [
        {
            "id": str,                  # stable ID e.g. "req_react"
            "name": str,                # normalized name
            "display_name": str,
            "category": str,            # skill/tool/framework/experience/etc.
            "importance": "required|preferred|context",
            "weight": float,            # e.g. 3/2/1
            "source_text": str
        }
    ],

    "role_level": "intern|junior|mid|senior|unknown",

    "bias_flags": [
        {
            "phrase": str,
            "reason": str,
            "suggestion": str
        }
    ]
}
```

---

## 7.2 Candidate Schema

```python
candidate = {
    "candidate_id": str,
    "name": str,
    "file_name": str,

    "raw_text": str,
    "clean_text": str,

    "sections": {
        "skills": str,
        "experience": str,
        "projects": str,
        "education": str,
        "certifications": str,
        "other": str
    },

    "parse_quality": {
        "score": float,               # 0-100
        "warnings": list[str]
    },

    "detected_skills": list[str],

    "requirement_matches": [
        {
            "requirement_id": str,
            "requirement_name": str,

            "keyword_match": bool,
            "keyword_score": float,   # 0-100 or normalized internally

            "semantic_score": float,  # 0-100

            "graph_match": bool,
            "graph_path": list[str],
            "graph_score": float,     # 0-100

            "evidence_strength": float, # 0.0-1.0
            "evidence_type": str,
            "evidence_text": str,

            "matched": bool
        }
    ],

    "scores": {
        "semantic": float,
        "keyword": float,
        "evidence": float,
        "graph": float,
        "base_score": float,
        "final_score": float
    },

    "matched_required_skills": list[str],
    "missing_required_skills": list[str],
    "matched_preferred_skills": list[str],

    "rank": int,

    "overqualification": {
        "flag": bool,
        "reasons": list[str]
    },

    "critique": {
        "confidence": "high|medium|low",
        "flags": list[str],
        "summary": str,
        "human_review_recommended": bool
    },

    "counterfactual": {
        "target_rank": int,
        "target_score": float,
        "suggested_improvements": list[dict],
        "projected_score": float
    },

    "interview_probes": list[str],

    "alternative_role": {
        "cluster": str,
        "reason": str
    }
}
```

Do not casually rename keys after integration starts.

---

# 8. Baseline Core Scoring

The exact weights may be tuned after seeing real outputs, but start deterministic.

Recommended:

```text
semantic_component = 45%
keyword_component  = 35%
evidence_component = 15%
graph_component    =  5%
```

So:

```python
base_score = (
    0.45 * semantic_score +
    0.35 * keyword_score +
    0.15 * evidence_score +
    0.05 * graph_score
)
```

Then apply only transparent adjustments.

Example:

```python
final_score = base_score - critical_missing_penalty
```

Recommended penalty:
- Missing a high-weight **required** skill: small bounded penalty.
- Cap total penalty so one rule cannot destroy the ranking.

Suggested cap:

```text
0–10 points maximum total critical-missing penalty
```

### Important

- Semantic and keyword matching must both genuinely affect final ranking.
- Evidence authenticity improves trust but must not eliminate the mandatory hybrid engine.
- Graph score should remain small because related technology is not always equivalent to an explicit requirement.
- Overqualification should be shown primarily as a recruiter flag rather than silently crushing score.

---

# 9. Semantic Matching Strategy

Use a local sentence-transformer such as:

```text
sentence-transformers/all-MiniLM-L6-v2
```

Recommended approach:

1. Chunk or section the resume.
2. Embed each JD requirement or meaningful JD chunk.
3. Embed relevant resume sections/chunks.
4. For each requirement, take the strongest relevant resume match.
5. Aggregate requirement-level similarities with requirement weights.

Better than:

> one embedding for the entire JD vs one embedding for the entire resume.

Why:
- Evidence remains explainable.
- Relevant project text is not diluted.
- Requirement-level scores feed directly into explanations and red-team analysis.

---

# 10. Keyword Matching Strategy

Use normalization:

```text
ReactJS -> react
React.js -> react
node js -> node.js
NodeJS -> node.js
mongo -> mongodb
RESTful API -> rest api
JS -> javascript
```

Avoid dangerous short-token matches:
- `"C"` should not match every letter C.
- `"R"` should not be raw substring matched.
- Use token boundaries / regex.

Weighted keyword coverage:

```python
keyword_score =
100 * sum(weight of matched requirements) / sum(weight of all considered requirements)
```

Prefer:
- required + preferred requirements;
- separate breakdown for transparency.

---

# 11. Evidence Authenticity Logic

Suggested section priority:

```text
experience/projects > certifications > skills list > other
```

Evidence scoring can combine:

```text
section strength
+ action verb presence
+ contextual sentence length
+ repeated support
+ semantic similarity
```

Example simple rule:

```python
if match in experience or projects:
    strength = 1.0 if contextual else 0.75
elif match in certifications:
    strength = 0.65
elif match in skills:
    strength = 0.35
else:
    strength = 0.0
```

Do not overcomplicate before end-to-end pipeline works.

---

# 12. Self-Critique Rules

Recommended red-team checks:

## C1. Semantic–Keyword Disagreement

```text
abs(semantic_score - keyword_score) > 25
```

Flag:

> "High semantic relevance but low explicit requirement coverage."

or inverse.

## C2. Weak-Evidence High Rank

Candidate top-3 and evidence score below threshold.

## C3. Missing Critical Requirement

Top-ranked candidate missing a high-weight required skill.

## C4. Ranking Margin

If:

```text
score(rank N) - score(rank N+1) < 2 or 3 points
```

flag as close decision.

## C5. Weight Sensitivity

Re-run ranking under a few safe presets:

```text
semantic/keyword:
55/45
45/55
60/40
40/60
```

If rank changes significantly, confidence goes down.

## C6. Parse Quality

Low extracted-text quality means low confidence.

## C7. Evidence Concentration

If almost all matches are only from the Skills section, lower trust.

---

# 13. Counterfactual Algorithm

Target:

```python
target_score = score_of_current_rank_3 + epsilon
```

For each missing/weak required requirement:

1. Simulate an improved evidence state.
2. Recalculate relevant components.
3. Measure score gain.
4. Sort improvements by gain.
5. Add improvements until projected score reaches target.

Return:
- minimal number of improvements;
- projected score;
- caveat that this is simulation.

Never say:
> "Learn MongoDB and you will get hired."

Instead:
> "Within this ranking model, strong demonstrated MongoDB evidence would increase this candidate's score by approximately X."

---

# 14. Skill Graph Contract

Recommended representation:

```python
skill_graph = {
    "node.js": [
        {"target": "javascript", "relation": "runtime_for", "weight": 0.8},
        {"target": "express", "relation": "commonly_used_with", "weight": 0.8}
    ]
}
```

Or use `networkx`.

Graph outputs per requirement:

```python
{
    "graph_match": True,
    "graph_path": ["backend development", "node.js", "express", "rest api"],
    "graph_score": 72
}
```

Keep graph small and relevant to the supplied full-stack JD.

---

# 15. Team Composition Algorithm

Brute force:

```python
from itertools import combinations
teams = combinations(candidates, 3)
```

For each team:

- union of matched required requirements;
- strongest evidence per requirement across team;
- mean semantic relevance;
- complementary coverage.

Return best 3–5 teams, but UI only needs top recommendation.

---

# 16. Interview Probe Rules

Probe generator consumes `requirement_matches` + `critique`.

Examples:

### Skill listed but weak evidence

Template:

> "You list {skill}. Can you describe a project where you personally used it and what you implemented?"

### Related graph match only

> "Your resume shows {related_skill}, which is related to {required_skill}. How much direct experience do you have with {required_skill}?"

### Semantic high, keyword low

> "Your experience appears relevant to {requirement}, but the exact technology is unclear. Which tools did you use?"

Generate 3–5 probes maximum.

---

# 17. Alternative Role Routing

Use skill clusters, not an LLM.

Example:

```python
ROLE_CLUSTERS = {
    "frontend": ["react", "javascript", "html", "css", "ui", "frontend"],
    "backend": ["node.js", "express", "rest api", "mongodb", "sql", "backend"],
    "data": ["python", "pandas", "sql", "machine learning", "analytics"],
    "devops": ["docker", "aws", "ci/cd", "linux", "kubernetes"]
}
```

Score cluster evidence and choose strongest.

Output language:

> "Potential stronger direction: Backend-focused opportunities."

Not:

> "You are selected for Backend Engineer."

---

# 18. Official Bonus Features

## JD Bias / Narrow-Phrasing Detector

Rule-based list such as:

- "young and energetic"
- "native English speaker"
- "rockstar"
- "ninja"
- unnecessary degree restrictions
- unnecessary years-of-experience phrasing for intern roles

Provide:
- phrase;
- reason;
- neutral rewrite.

Do not infer protected characteristics from candidates.

## Recruiter Comparison Mode

Instead of a free-form chatbot, safest no-API version:

```text
Candidate A dropdown
Candidate B dropdown
[Compare]
```

Output:

- score difference;
- semantic difference;
- keyword difference;
- evidence difference;
- skills A has that B lacks;
- skills B has that A lacks;
- critique/confidence.

Optionally support a few predefined recruiter questions/buttons.

## Messy Resume Handling

- Normalize whitespace.
- Case-insensitive headings.
- Flexible date formats.
- Section aliases:
  - work experience / employment / professional experience.
  - projects / academic projects / personal projects.
- Missing-section fallback.
- Parser quality warning.

---

# 19. Shared File/Module Layout

```text
project/
|
|-- app.py
|-- requirements.txt
|
|-- config/
|   |-- skill_aliases.json
|   |-- skill_graph.json
|   |-- bias_rules.json
|   `-- role_clusters.json
|
|-- src/
|   |-- schemas.py
|   |-- pdf_parser.py
|   |-- preprocessing.py
|   |-- requirement_extractor.py
|   |-- skill_extractor.py
|   |-- keyword_matcher.py
|   |-- semantic_matcher.py
|   |-- evidence.py
|   |-- skill_graph.py
|   |-- scorer.py
|   |-- ranker.py
|   |-- critique.py
|   |-- counterfactual.py
|   |-- team_mode.py
|   |-- overqualification.py
|   |-- probes.py
|   |-- jd_bias.py
|   |-- compare.py
|   `-- candidate_outcomes.py
|
|-- ui/
|   `-- components.py
|
|-- data/
|   |-- jd/
|   `-- resumes/
|
`-- results/
    `-- latest_results.json
```

Keep module responsibilities narrow.

---

# 20. Public Function Interfaces

Prefer these signatures so integration is easy:

```python
# Parsing
parse_pdf(path: str) -> str
split_resume_sections(text: str) -> dict
estimate_parse_quality(raw_text: str, sections: dict) -> dict

# JD
extract_requirements(jd_text: str) -> list[dict]
detect_role_level(jd_text: str) -> str

# Matching
keyword_match(jd: dict, candidate: dict) -> dict
semantic_match(jd: dict, candidate: dict, model) -> dict
score_evidence(jd: dict, candidate: dict) -> dict
apply_skill_graph(jd: dict, candidate: dict, graph) -> dict

# Scoring
score_candidate(jd: dict, candidate: dict) -> dict
rank_candidates(candidates: list[dict]) -> list[dict]

# Differentiators
critique_ranking(jd: dict, ranked_candidates: list[dict]) -> list[dict]
generate_counterfactual(candidate: dict, ranked_candidates: list[dict], jd: dict) -> dict
find_best_team(jd: dict, ranked_candidates: list[dict], team_size: int = 3) -> dict
flag_overqualification(jd: dict, candidate: dict) -> dict
generate_interview_probes(jd: dict, candidate: dict) -> list[str]

# Bonus / UX
detect_jd_bias(jd_text: str) -> list[dict]
compare_candidates(a: dict, b: dict, jd: dict) -> dict
route_alternative_role(candidate: dict) -> dict
generate_rejection_draft(candidate: dict, jd: dict) -> str
```

If internal logic changes, keep the outward contract stable.

---

# 21. Integration Rules

## Rule 1 — Core First

Nothing matters until:

```text
PDFs -> scores -> ranking -> top-3 explanations
```

works.

## Rule 2 — One Owner Per Shared Module

Avoid two teammates editing the same core file simultaneously.

## Rule 3 — Features Consume Structured Results

Advanced features should consume the candidate schema rather than re-parsing resumes.

Bad:

```text
counterfactual.py parses PDF again
```

Good:

```text
counterfactual.py reads candidate["requirement_matches"]
```

## Rule 4 — No Network Calls

Search code for:
- `requests`
- remote SDKs
- API keys
- hosted URLs

before demo.

## Rule 5 — Deterministic Demo

- fixed weighting defaults;
- cache embeddings where possible;
- stable model;
- no random text generation;
- graceful errors.

## Rule 6 — Preserve Evidence Text

Exact snippets are needed for:
- explanations;
- authenticity;
- interview probes;
- self-critique;
- judge walkthrough.

---

# 22. Merge Order

Recommended merge/integration sequence:

1. Shared schemas/config.
2. Parser + preprocessing.
3. Requirement/skill extraction.
4. Keyword matcher.
5. Semantic matcher.
6. Evidence authenticity.
7. Skill graph.
8. Scorer/ranker.
9. Top-3 explanation.
10. Self-critique.
11. Counterfactual.
12. Overqualification.
13. Interview probes.
14. Team composition.
15. Bias detector.
16. Candidate comparison.
17. Alternative role + rejection draft.
18. Streamlit UI wiring.
19. Full regression test with all resumes.
20. Demo freeze.

---

# 23. Minimum Demo Flow

1. Open app.
2. Upload/select JD.
3. Upload/select all resumes.
4. Click **Analyze Candidates**.
5. Show complete ranking.
6. Open Rank #1:
   - final score;
   - semantic;
   - keyword;
   - evidence;
   - matched/missing requirements;
   - exact evidence.
7. Show **System Critique**:
   - confidence;
   - warnings;
   - close decision if applicable.
8. Show **Counterfactual** for a mid-ranked candidate.
9. Show **Compare Candidates**.
10. Show **Team Composition Mode** if stable.
11. Show JD bias analysis / recruiter bonus.
12. Emphasize:
   - no APIs;
   - local/private;
   - ranking is explainable.

---

# 24. UI Labels Worth Using

Use labels that make the technical innovation obvious:

- **Hybrid Match Score**
- **Semantic Relevance**
- **Explicit Requirement Coverage**
- **Evidence Authenticity**
- **Related-Skill Graph Evidence**
- **Ranking Confidence**
- **System Self-Critique**
- **What Would Change This Ranking?**
- **Interview Verification Questions**
- **Best Complementary 3-Person Team**
- **Potential Role Alignment**
- **100% Local Processing — No External APIs**

---

# 25. Guardrails

Do not:

- infer age, gender, religion, ethnicity, disability, or other protected traits;
- use names/photos as ranking signals;
- silently penalize someone based on personal attributes;
- claim a simulated counterfactual guarantees hiring;
- call alternative role suggestions real vacancies;
- let graph similarity fully satisfy a hard required technology;
- hide uncertainty.

The tool is a **decision-support system**, not an autonomous hiring authority.

---

# 26. Definition of Done

The project is demo-ready when:

- [ ] All resumes parse without crashing.
- [ ] Every candidate receives semantic and keyword scores.
- [ ] Both scores genuinely affect final score.
- [ ] Rankings show meaningful spread.
- [ ] Top 3 have matched + missing requirements.
- [ ] Evidence snippets are visible.
- [ ] Evidence authenticity score works.
- [ ] Self-critique produces useful flags.
- [ ] Counterfactual simulation works for at least one mid-ranked candidate.
- [ ] Skill graph produces explainable related-skill paths.
- [ ] Overqualification flag does not use protected attributes.
- [ ] Interview probes are generated locally.
- [ ] Team mode returns a valid trio.
- [ ] Rejection draft/role routing is clearly templated and non-deceptive.
- [ ] Official bonus features do not break core flow.
- [ ] App makes no external API/network request during demo.
- [ ] Fresh launch works end-to-end.

---

# 27. Final Pitch

> **Most resume ranking systems only ask whether the right words are present. Ours asks whether the candidate actually demonstrates those skills, understands related technology through an explainable skill graph, challenges its own ranking when evidence is weak, and shows recruiters exactly what evidence would change the outcome — all locally, without sending candidate data to an external API.**
