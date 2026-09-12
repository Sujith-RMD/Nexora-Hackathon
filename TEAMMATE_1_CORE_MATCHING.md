# TEAMMATE 1 CONTEXT — Core Matching, Parsing & Evidence Authenticity

## Your Mission

You own the **foundation that every other feature depends on**.

Your job is to produce a clean, deterministic, explainable pipeline:

```text
PDFs
 -> parsed text
 -> normalized JD requirements
 -> resume sections
 -> keyword matches
 -> semantic matches
 -> evidence authenticity
 -> core candidate scores
 -> ranked candidates
```

Other teammates should be able to consume your structured output without reading PDFs again.

Read `MASTER_CONTEXT.md` first. Its schemas and interfaces are authoritative.

---

# 1. Your Primary Ownership

You own:

- `src/pdf_parser.py`
- `src/preprocessing.py`
- `src/requirement_extractor.py`
- `src/skill_extractor.py`
- `src/keyword_matcher.py`
- `src/semantic_matcher.py`
- `src/evidence.py`
- `src/scorer.py`
- `src/ranker.py`
- optionally the initial `src/schemas.py`
- `config/skill_aliases.json`

You are primarily responsible for:

1. Robust PDF text extraction.
2. Resume section detection.
3. JD requirement extraction.
4. Skill normalization.
5. Explicit keyword matching.
6. Local semantic matching.
7. Evidence Authenticity Scoring.
8. Core hybrid scoring.
9. Ranking all candidates.
10. Producing the structured candidate objects consumed by Teammates 2 and 3.

---

# 2. Non-Negotiable Constraints

- **No external APIs.**
- Use local libraries/models only.
- Ranking must genuinely use both semantic and keyword matching.
- Do not ask an LLM to score.
- Preserve exact evidence snippets.
- Avoid brittle assumptions about resume formatting.
- Do not use names or demographic information as ranking features.

---

# 3. Required Input

You receive:

```text
1 JD PDF
15–18 resume PDFs
```

Expected local paths might look like:

```text
data/jd/Sample_JD.pdf
data/resumes/*.pdf
```

Do not hard-code exact filenames unless needed for the demo.

---

# 4. PDF Parsing

Recommended:

```python
import fitz  # PyMuPDF
```

Function:

```python
def parse_pdf(path: str) -> str:
    ...
```

Requirements:

- Read all pages.
- Join page text in order.
- Normalize obvious repeated whitespace.
- Never fail the entire batch because one file is odd.
- Return warning/error metadata separately if useful.

Keep original/raw text available.

---

# 5. Resume Section Detection

Function:

```python
def split_resume_sections(text: str) -> dict:
    ...
```

Normalize headings such as:

```text
SKILLS
TECHNICAL SKILLS
TOOLS & TECHNOLOGIES

EXPERIENCE
WORK EXPERIENCE
PROFESSIONAL EXPERIENCE
EMPLOYMENT

PROJECTS
ACADEMIC PROJECTS
PERSONAL PROJECTS

EDUCATION
ACADEMIC BACKGROUND

CERTIFICATIONS
CERTIFICATES
```

Return exactly:

```python
{
    "skills": str,
    "experience": str,
    "projects": str,
    "education": str,
    "certifications": str,
    "other": str
}
```

If headings are not detected:
- keep content in `other`;
- do not crash;
- lower parser confidence.

---

# 6. Parse Quality

Implement:

```python
def estimate_parse_quality(raw_text: str, sections: dict) -> dict:
    ...
```

Suggested signals:

- character count;
- printable-text ratio;
- number of detected sections;
- whether text is suspiciously empty;
- excessive symbol noise;
- duplicated lines;
- average line length.

Return:

```python
{
    "score": 0-100,
    "warnings": [...]
}
```

This feeds the self-critique module later.

---

# 7. JD Requirement Extraction

Because time is limited and no API is allowed, prefer a deterministic extraction strategy.

Combine:

1. known skills dictionary;
2. regex/token matching;
3. sentence cues such as:
   - required
   - must have
   - should know
   - preferred
   - nice to have
   - familiarity with
   - experience with

Output:

```python
[
    {
        "id": "req_react",
        "name": "react",
        "display_name": "React",
        "category": "framework",
        "importance": "required",
        "weight": 3.0,
        "source_text": "..."
    }
]
```

Suggested importance weights:

```text
required = 3
preferred = 2
context = 1
```

If classification is uncertain:
- default to `context` or `preferred`;
- avoid falsely declaring something mandatory.

---

# 8. Skill Normalization

Create `config/skill_aliases.json`.

Example:

```json
{
  "reactjs": "react",
  "react.js": "react",
  "nodejs": "node.js",
  "node js": "node.js",
  "mongo": "mongodb",
  "restful api": "rest api",
  "restful services": "rest api",
  "js": "javascript"
}
```

Important:

- Use word/token boundaries.
- Avoid substring matching.
- `C` and `R` need special handling.
- Preserve canonical names.

Provide:

```python
def normalize_skill(term: str) -> str:
    ...
```

---

# 9. Keyword Matching

Function:

```python
def keyword_match(jd: dict, candidate: dict) -> dict:
    ...
```

For every JD requirement:

- exact canonical match;
- alias match;
- safe phrase match;
- section where it appeared.

Generate requirement-level data.

Example:

```python
{
    "requirement_id": "req_react",
    "keyword_match": True,
    "keyword_score": 100,
    "matched_variant": "React.js",
    "section": "projects"
}
```

Aggregate:

```python
keyword_score = (
    100
    * matched_requirement_weight
    / total_requirement_weight
)
```

Keep required/preferred breakdown if possible.

---

# 10. Semantic Matching

Use local:

```text
sentence-transformers/all-MiniLM-L6-v2
```

Load once:

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2")
```

Do not reload per resume.

Function:

```python
def semantic_match(jd: dict, candidate: dict, model) -> dict:
    ...
```

Preferred design:

## Requirement-Level Semantic Matching

For each JD requirement:

1. Build requirement text from `source_text` + canonical name.
2. Compare it against candidate chunks/sections.
3. Save the best matching chunk.
4. Keep raw cosine similarity.
5. Convert to 0–100 carefully.

Store:

```python
{
    "requirement_id": "...",
    "semantic_score": 83.2,
    "best_chunk": "...",
    "best_section": "projects"
}
```

Aggregate using requirement weights.

This is much more useful than one whole-document similarity score.

---

# 11. Chunking

Keep it simple.

Possible approach:

- split by section;
- split long sections into paragraphs/sentences;
- or fixed character chunks around 500–1000 chars.

Avoid excessive tiny chunks.

Store chunk source section so evidence is explainable.

---

# 12. Evidence Authenticity Scoring — Major Differentiator

This is one of the most important features.

Goal:

> A skill should receive more trust when it is demonstrated in project/work context than when it is merely listed.

Function:

```python
def score_evidence(jd: dict, candidate: dict) -> dict:
    ...
```

For each requirement, search for its direct/alias/semantic evidence.

Recommended strength:

```text
1.00 = clear project/work evidence with context
0.75 = project/work mention but weak context
0.65 = certification evidence
0.60 = repeated across multiple sections
0.35 = Skills section only
0.20–0.50 = related graph evidence later
0.00 = no evidence
```

Useful context cues:

Action verbs:

```text
built
developed
implemented
designed
created
deployed
integrated
optimized
maintained
tested
```

Project/work section occurrence should matter most.

Output per requirement:

```python
{
    "requirement_id": "req_mongodb",
    "evidence_strength": 1.0,
    "evidence_type": "project",
    "evidence_text": "Built a REST API with Express and MongoDB..."
}
```

Aggregate evidence score:

```python
evidence_score =
100 * weighted_average(evidence_strength)
```

---

# 13. Core Hybrid Score

Implement in `src/scorer.py`.

Start with:

```python
base_score = (
    0.45 * semantic_score +
    0.35 * keyword_score +
    0.15 * evidence_score +
    0.05 * graph_score
)
```

At first, before teammate 2's graph is integrated:

```python
graph_score = 0
```

or temporarily redistribute weights only during development.

**Important:** once final integration happens, use the shared agreed weighting in `MASTER_CONTEXT.md`.

Critical-missing penalty:

- only for requirements marked `required`;
- bounded total, e.g. max 10 points;
- expose the reason.

Example:

```python
scores = {
    "semantic": 84.2,
    "keyword": 76.0,
    "evidence": 70.0,
    "graph": 0.0,
    "base_score": 78.49,
    "final_score": 74.49
}
```

Never round early.

Round only for display.

---

# 14. Ranking

Function:

```python
def rank_candidates(candidates: list[dict]) -> list[dict]:
    ranked = sorted(
        candidates,
        key=lambda c: c["scores"]["final_score"],
        reverse=True
    )

    for i, c in enumerate(ranked, start=1):
        c["rank"] = i

    return ranked
```

For ties:
- use evidence authenticity as tie-breaker;
- then required skill coverage;
- then semantic score.

Keep tie-break logic explicit.

---

# 15. Top-3 Explanation Data

You do not need to own final UI prose, but you must expose enough data.

Each top candidate must provide:

```python
matched_required_skills
missing_required_skills
matched_preferred_skills
requirement_matches[].evidence_text
scores
```

Recommended structured explanation object:

```python
candidate["explanation_data"] = {
    "strongest_matches": [...],
    "important_missing": [...],
    "best_evidence": [...],
    "score_breakdown": {...}
}
```

---

# 16. Data Contract You Must Hand Off

For each candidate, Teammate 2/3 expect:

```python
{
    "candidate_id": ...,
    "name": ...,
    "file_name": ...,
    "raw_text": ...,
    "clean_text": ...,
    "sections": ...,
    "parse_quality": ...,
    "detected_skills": ...,
    "requirement_matches": ...,
    "scores": ...,
    "matched_required_skills": ...,
    "missing_required_skills": ...,
    "matched_preferred_skills": ...,
    "rank": ...
}
```

Do not rename these after handoff.

---

# 17. Your Integration Touchpoints With Teammate 2

Teammate 2 will add:

- skill graph fields;
- self-critique;
- counterfactual;
- overqualification;
- team composition;
- interview probes.

Your scorer should make it easy to inject:

```python
graph_score
```

Do not import their modules deeply into parsing.

Maintain one-way flow:

```text
your structured result -> teammate 2 features
```

---

# 18. Your Integration Touchpoints With Teammate 3

Teammate 3 needs:

- clean candidate names;
- final rank;
- score breakdown;
- evidence text;
- matched/missing skills;
- parse warnings.

Prefer plain serializable dictionaries.

Make sure:

```python
json.dumps(candidate)
```

works after removing non-serializable model objects.

Do not store embedding tensors inside candidate output.

---

# 19. Performance Guidance

Only 18 resumes.

Do not over-engineer.

Good optimizations:

- load embedding model once;
- batch encode chunks;
- cache candidate embeddings;
- cache normalized text;
- avoid recomputing on every Streamlit rerender.

Potential Streamlit caching will be handled by UI teammate if needed.

---

# 20. Failure Handling

Never crash whole analysis because:

- one resume has no Projects section;
- candidate name cannot be extracted;
- one PDF is sparse;
- a skill cannot be categorized.

Fallbacks:

```text
name -> filename
unknown section -> other
missing role level -> unknown
missing evidence -> strength 0
```

Add warning.

---

# 21. What You Must NOT Build

Do not spend your time on:

- UI.
- free-form chatbot.
- email generation.
- team mode.
- red-team critique.
- fancy visualization.

Your job is the core engine.

---

# 22. Fast Test Cases

Before handoff, manually validate:

## Test A — Exact Skill

JD requires `React`.

Resume project contains:

> "Built frontend using React.js."

Expect:
- keyword match true;
- semantic high;
- evidence strong;
- alias normalized.

## Test B — Skills List Only

Resume:

> "Skills: React, Node.js, MongoDB"

Expect:
- keyword high;
- evidence much lower than demonstrated project.

## Test C — Semantic Related Experience

JD says:

> "Develop backend APIs"

Resume says:

> "Created RESTful services using Express."

Expect:
- semantic meaningful even if exact phrase differs.

## Test D — Missing Requirement

JD explicitly requires MongoDB.

Resume never mentions related DB evidence.

Expect:
- missing required skill;
- penalty transparent.

## Test E — Messy Resume

No clear headings.

Expect:
- no crash;
- parse quality warning.

---

# 23. Definition of Done for Your Module

- [ ] All PDFs parse.
- [ ] JD requirements are structured.
- [ ] Resume sections are extracted/fallback works.
- [ ] Skills are normalized.
- [ ] Keyword score is explainable.
- [ ] Local semantic score works.
- [ ] Evidence authenticity distinguishes "listed" from "demonstrated."
- [ ] All candidates get full score objects.
- [ ] All candidates are ranked.
- [ ] Top-3 explanation data exists.
- [ ] Outputs are JSON-serializable.
- [ ] No API/network dependency at runtime.
- [ ] Teammates can call your functions without reading your internals.

---

# 24. Handoff Message to Team

When ready, tell the team:

> Core pipeline is stable. Call the parser -> matchers -> evidence scorer -> scorer -> ranker. Candidate output follows the shared schema. Do not re-parse PDFs in downstream modules; use `requirement_matches`, `scores`, `sections`, and evidence snippets directly.
