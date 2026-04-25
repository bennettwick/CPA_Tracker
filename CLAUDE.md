# CPA Transcript Analyzer — Project Brief

## What This App Does
Students upload a college transcript (PDF). The app uses Gemini 2.0 Flash 
to extract their courses and map them to CPA exam requirement categories 
for their state. A progress dashboard shows which requirements are met 
and what's still needed.

## Tech Stack
- **Backend:** Python, Flask
- **Frontend:** HTML, CSS, vanilla JavaScript (no React)
- **AI:** Google Gemini 2.0 Flash via google-generativeai Python SDK
- **Data transport:** JSON
- **No database** — stateless, process transcript fresh each time

## Project Structure to Follow
cpa-tracker/
├── app.py                  # Flask app, API routes
├── gemini_extractor.py     # Handles PDF → Gemini → structured JSON
├── requirements_checker.py # Compares extracted courses to state rules
├── CLAUDE.md
├── requirements.txt
├── .env
├── static/
│   ├── style.css
│   └── script.js
├── templates/
│   └── index.html          # Upload form + results dashboard
└── state_requirements.json

## AI Extraction Logic
- Send the transcript PDF directly to Gemini 2.0 Flash
- Prompt it to return ONLY valid JSON, no markdown, no explanation
- JSON schema for extracted courses:
  {
    "courses": [
      {
        "name": "Principles of Financial Accounting",
        "credits": 3,
        "grade": "A",
        "year": 2022,
        "cpa_category": "financial_accounting"
      }
    ]
  }
- Valid cpa_category values: financial_accounting, managerial_accounting,
  auditing, taxation, business_law, ethics, upper_division_accounting,
  general_business, other, unclear

## State Requirements JSON Schema
- Stored in state_requirements.json
- Each state has exam_eligibility only (v1 scope)
- Each required topic has an aliases array — pass these to Gemini so it
  can match course names across different schools
- Arkansas requires minimum grade of C in all required courses — flag 
  any required course where grade is below C

## Frontend Requirements
- Clean, modern design — progress bars for each category
- Color coding: green = met, yellow = in progress, red = not started
- Show: credits earned vs credits required per category
- Mobile friendly
- No frameworks — plain HTML/CSS/JS only

## Key Constraints
- Must remain FREE for all users (this is why we use Gemini free tier)
- No user accounts or login
- No storing transcripts or personal data after processing
- Keep it simple — this is a small tool, not an enterprise app
- I know Python well, minimal JavaScript experience, so keep JS simple

## Gemini API Setup
- API key stored in .env file as GEMINI_API_KEY
- Never hardcode the API key
- Use python-dotenv to load it

## Error Handling Priorities
1. If Gemini returns malformed JSON, retry once with a stricter prompt
2. If a course category is "unclear", flag it for the student to review manually
3. Show friendly error messages on the frontend, never raw stack traces