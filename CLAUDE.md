# CPA Transcript Analyzer — Project Brief

## What This App Does
Students upload a college transcript (PDF). The app uses Gemini 2.5 Flash
to extract every course and map it to CPA exam requirement categories for
their state. A results dashboard shows which requirements are met, credit
totals, grade warnings, and a full extracted course list grouped by semester.

## Tech Stack
- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, vanilla JavaScript (no React, no build step)
- **AI:** Google Gemini 2.5 Flash via `google-generativeai` Python SDK
- **Runner:** `uv` — start with `uv run python app.py`
- **Data transport:** JSON
- **No database** — stateless, transcript is processed fresh each time and never stored

## Project Structure
```
CPA_Tracker/
├── app.py                  # Flask app, /check and /states API routes
├── gemini_extractor.py     # PDF → Gemini → structured JSON
├── requirements_checker.py # Compares extracted courses to state rules
├── state_requirements.json # Per-state CPA eligibility rules
├── CLAUDE.md
├── .env                    # GEMINI_API_KEY (never commit)
├── static/
│   ├── style.css
│   └── script.js           # All frontend logic — vanilla JS only
└── templates/
    └── index.html          # Upload form + results dashboard
```

## Gemini Extraction — Current JSON Schema

`gemini_extractor.py` sends the PDF directly to Gemini and asks for this schema:

```json
{
  "graduation_status": "conferred" | "in_progress" | "unknown",
  "courses": [
    {
      "code": "ACCT 3013",
      "name": "Intermediate Accounting I",
      "credits": 3,
      "grade": "A",
      "year": 2023,
      "semester": "Fall" | "Spring" | "Summer" | "Winter" | null,
      "level": "undergrad" | "grad" | null,
      "is_upper_level": true | false | null,
      "cpa_category": "<see categories below>"
    }
  ]
}
```

**Field notes:**
- `code` — course code exactly as printed (e.g. "ECON 400H3"). Kept separate from `name` so the UI can display them independently.
- `name` — course title only, no course code included.
- `semester` — extracted from the transcript's term label. null if not shown.
- `level` — "grad" only if transcript explicitly marks it as graduate-level (5000+ course number, "Graduate" header, etc.). "undergrad" otherwise.
- `is_upper_level` — true for 300-499 / 3000-4999 course numbers and all grad courses; false for 100-299 / 1000-2999 and intro courses; null if unclear.
- `graduation_status` — top-level field, not per-course.

## CPA Category Values

Used in both the Gemini prompt and `requirements_checker.py`:

**Accounting categories** (counted toward accounting hour totals):
- `financial_accounting`, `management_accounting`, `governmental_nonprofit`
- `taxation`, `auditing`, `accounting_information_systems`
- `accounting_elective`, `upper_division_accounting`

**Business categories** (counted toward business hour totals):
- `general_business`, `business_law`, `ethics`

**Fallback categories** (not counted toward any hour total):
- `other` — clearly not business/accounting (humanities, PE, sciences, generic transfer placeholders)
- `unclear` — name suggests CPA relevance but category can't be determined; flagged for student review

**AIS classification rule:** Use `accounting_information_systems` ONLY when the course name contains both an accounting reference ("Accounting", "ACCT") AND a systems/technology reference. "Business Information Systems" or "MIS" without "Accounting" → `general_business`.

**Department prefix rule:** If the course prefix is clearly accounting-specific (ACCT, ACTG, ACCY, or school equivalent), assign an accounting category even if the title is ambiguous.

## Critical Prompt Design Decision — Multi-Line Course Names

Gemini sometimes misreads transcripts where a course name wraps onto a second line in the PDF. Without a fix, it treats the continuation line as a separate course, and assigns that leftover text as the name of the *next* course code.

The prompt explicitly instructs Gemini:
> A new course entry always begins with a course code. If a course name wraps onto a second line with no course code at the start of that line, join it with a space — do NOT create a new entry for it.

A concrete example is included in the prompt showing exactly this pattern (ECON 400H3 with a two-line name). **Do not remove or weaken this rule when editing the prompt.**

## Requirements Checker Logic (`requirements_checker.py`)

Pipeline run after extraction:

1. **Deduplication** — same course name appearing twice is only collapsed as a retake if the earlier grade was D+ or below. Otherwise treated as separate enrollments (repeatable courses).
2. **Topic requirements** — per-topic credit thresholds from `state_requirements.json`. Some states require upper-level only.
3. **Hour totals** — total accounting and business credits vs. state minimums. Some states (Louisiana) do not allow mixing undergrad and grad credits.
4. **Grade thresholds** — some states (Arkansas) require minimum C in required courses. Flags any required course below the threshold.
5. **Degree conferred** — checks `graduation_status` from Gemini. If "unknown", infers from credit count (120+) and whether all requirements are met.
6. **Unclear courses** — any course with `cpa_category: "unclear"` is surfaced for manual review.
7. **Manual checks** — requirements that can't be verified from a transcript (e.g., Louisiana age and residency requirements).

## State Requirements JSON Schema

```json
{
  "state_key": {
    "state": "Display Name",
    "exam_eligibility": {
      "degree_required": true,
      "accounting": {
        "undergraduate_hours_required": 27,
        "graduate_hours_required": 18,
        "combination_allowed": true,
        "upper_level_only": true,
        "min_grade": "C",
        "required_topics": {
          "topic_key": {
            "credits_required": 3,
            "graduate_credits_required": 3,
            "aliases": ["course name variant", ...]
          }
        }
      },
      "business": { ... }
    }
  }
}
```

`graduate_credits_required` is optional — only present when the grad threshold differs from undergrad (e.g. Louisiana `financial_accounting`).

## Frontend Behavior (`script.js` + `index.html`)

**Results dashboard sections (in order):**
1. Summary banner — eligible / needs review / not eligible
2. Results grid (2-col): Required Course Topics card + Requirements Summary card (hour progress bars + degree conferred toggle)
3. Grade warnings card (hidden if none)
4. Unclear courses card (hidden if none)
5. Manual verification card (hidden if none)
6. Level detection warning card (Louisiana only, hidden if none)
7. Collapsible courses table (hidden by default, toggled by button)

**Courses table:**
- Columns: Course Name, Credits, Grade, Level, Category (no separate Year column)
- Course name displayed as `"FINN 30103: FINANCIAL ANALYSIS"` (code + colon + name)
- Rows are grouped by semester with styled header rows (e.g. "FALL 2023")
- Groups sorted chronologically: Spring < Summer < Fall < Winter within a year; year-only entries after named semesters; "Unknown" last
- Semester label logic: if both semester and year → "Fall 2023"; year only → "2023"; neither → "Unknown"

**Degree conferred toggle:**
- Shown only when the state requires a degree
- Lets the student manually override the AI's inference
- Changing it recalculates the summary banner in real time

## Key Constraints
- Must remain **free** for all users — Gemini free tier only, no paid APIs
- No user accounts, no login
- No storing transcripts or personal data after the request completes
- No JavaScript frameworks — plain HTML/CSS/JS only
- Keep JS simple — owner knows Python well, minimal JS experience

## Gemini API Setup
- API key in `.env` as `GEMINI_API_KEY`, loaded via `python-dotenv`
- Never hardcode the key
- Retry logic: if Gemini returns malformed JSON, retry once with a stricter prompt prefix before raising `GeminiParseError`

## Error Handling
1. Malformed Gemini JSON → retry once with stricter prompt; show friendly error if still fails
2. `unclear` courses → surfaced in a warning card for manual review
3. Grade below threshold → flagged in a separate warnings card
4. Never show raw stack traces on the frontend
