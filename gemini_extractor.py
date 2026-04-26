import json
import os
import re

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL_NAME = "gemini-2.5-flash"

FALLBACK_CATEGORIES = ["general_business", "other", "unclear"]

COURSE_SCHEMA = """{
  "graduation_status": "conferred" or "in_progress" or "unknown",
  "courses": [
    {
      "code": "<course code exactly as printed, e.g. ECON 400H3, or null>",
      "name": "<course name only, without the course code>",
      "credits": <number>,
      "grade": "<letter grade or null>",
      "year": <four-digit year or null>,
      "semester": "Fall" or "Spring" or "Summer" or "Winter" or null,
      "level": "undergrad" or "grad" or null,
      "is_upper_level": true or false or null,
      "cpa_category": "<category from the list above>"
    }
  ]
}"""


class GeminiParseError(Exception):
    pass


def load_state_requirements(state: str) -> dict:
    path = os.path.join(os.path.dirname(__file__), "state_requirements.json")
    with open(path, "r") as f:
        data = json.load(f)
    key = state.lower()
    if key not in data:
        raise ValueError(f"State '{state}' not found.")
    return data[key]


def _build_topic_lines(state_req: dict) -> str:
    lines = []
    elig = state_req["exam_eligibility"]

    for section_name in ("accounting", "business"):
        section = elig.get(section_name, {})
        for topic_key, topic_def in section.get("required_topics", {}).items():
            aliases = topic_def.get("aliases", [])
            alias_str = ", ".join(f'"{a}"' for a in aliases)
            lines.append(f'- {topic_key} (also called: {alias_str})')

    return "\n".join(lines)


def build_extraction_prompt(state_req: dict) -> str:
    state_name = state_req["state"]
    topic_lines = _build_topic_lines(state_req)

    return f"""You are a college transcript parser. Extract EVERY course from the transcript provided.

For each course, assign a cpa_category from this list of recognized {state_name} CPA exam topics:
{topic_lines}

Two rules that override name-based guessing:
- Department prefix: if the course prefix is clearly accounting-specific (e.g., ACCT, ACTG, ACCY, or a school-specific equivalent), assign an appropriate accounting category (financial_accounting, taxation, auditing, etc.) even if the course title is ambiguous
- Information systems: use accounting_information_systems ONLY when the course name contains both an accounting reference ("Accounting", "ACCT") AND a systems/technology reference ("Information Systems", "Systems", "Technology"). Courses named "Business Information Systems", "Management Information Systems", "Business Technology", or similar without "Accounting" in the title should be general_business

If a course does not match any topic above, use one of these fallback categories:
- general_business — business courses not matching a specific topic above
- other — anything that is clearly not business or accounting: humanities, sciences, PE, health, orientation, generic transfer credit placeholders (e.g., "199T", "ELEC 100", "TR CREDIT"), low-numbered courses (099–199) with no accounting/business connection, and any course whose name gives no indication it could be CPA-relevant
- unclear — ONLY when the course name genuinely suggests it might count toward CPA requirements but you cannot determine the specific category (e.g., "Business Applications", "Accounting Seminar", "Financial Topics"). If you cannot tell whether the course is even business-related, use "other" instead

For the "level" field:
- Use "grad" ONLY if the transcript explicitly marks the course as graduate-level (e.g., course number 5000+, "Graduate" section header, "G" prefix, or similar)
- Use "undergrad" for all other courses
- Use null only if the transcript gives no indication at all

For the "is_upper_level" field:
- Use true for upper-division undergraduate (course number 300-499 or 3000-4999) and all graduate courses
- Use false for lower-division courses (course number 100-299 or 1000-2999), including "Principles of Accounting I/II", "Introduction to Accounting", "Survey of Accounting", or any course clearly labeled as introductory
- Use null only if no course number is shown and the course name gives no clear indication of level
- When in doubt based on name: "Intermediate", "Advanced", "Cost", "Auditing", "Tax", "Federal" → true; "Principles of", "Introduction to", "Intro to", "Survey of" → false

For the "graduation_status" field (top-level, not per course):
- Use "conferred" if the transcript clearly shows a bachelor's degree has been awarded (e.g., degree award date, "Conferred", "Degree Awarded", graduation noted, degree title listed as completed)
- Use "in_progress" if the transcript shows the degree is not yet complete (e.g., "In Progress", "Expected Graduation", "Anticipated", "Current Student", "Enrolled", courses marked as currently registered or graded "IP")
- Use "unknown" if the transcript gives no clear indication of degree completion status

Return ONLY valid JSON. No markdown. No code fences. No explanation. Start with {{ and end with }}.

Use this exact schema:
{COURSE_SCHEMA}

Rules:
- Include ALL courses on the transcript, not just accounting ones
- A new course entry always begins with a course code (e.g., "ECON 400H3", "ACCT 3013"). If a course name wraps onto a second line in the PDF with no course code at the start of that line, that line is a continuation of the previous course name — join it with a space and do NOT create a new course entry for it. Example: if the PDF shows:
    ECON 400H3  HONORS ECON COLLOQUIUM         3  A
                FINANCIAL CRISES: ANALYSIS AND HISTORY
    ECON 47503  FORECASTING                    3  B
  the correct output is two courses: "HONORS ECON COLLOQUIUM FINANCIAL CRISES: ANALYSIS AND HISTORY" (ECON 400H3) and "FORECASTING" (ECON 47503). It would be wrong to create a third course named "FINANCIAL CRISES: ANALYSIS AND HISTORY"
- code must be the course code exactly as printed (e.g., "ECON 400H3", "ACCT 3013"), or null if no course code appears on the transcript
- name must be the course title only — do not include the course code in the name
- credits must be a number (e.g., 3 or 3.0)
- grade must be the letter grade shown (e.g., "A", "B+", "C-") or null if not shown
- year must be the four-digit year the course was taken, or null if not shown
- semester must be "Fall", "Spring", "Summer", or "Winter" — extract from the transcript's term label (e.g., "Fall 2025", "Spring Semester", "Autumn Quarter"). Use null if no term/semester label is shown
- Do not invent or estimate credits — use only what the transcript states"""


def parse_gemini_response(raw_text: str) -> dict:
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise GeminiParseError(f"JSON parse failed: {e}") from e


def _call_gemini_once(pdf_bytes: bytes, prompt: str) -> dict:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            prompt,
        ],
    )
    return parse_gemini_response(response.text)


def call_gemini_with_retry(pdf_bytes: bytes, state: str) -> dict:
    state_req = load_state_requirements(state)
    prompt = build_extraction_prompt(state_req)

    try:
        return _call_gemini_once(pdf_bytes, prompt)
    except GeminiParseError:
        strict_prefix = (
            "IMPORTANT: Your previous response could not be parsed as JSON. "
            "Return ONLY the raw JSON object. Start with { and end with }. "
            "Absolutely no markdown, no code fences, no explanation.\n\n"
        )
        try:
            return _call_gemini_once(pdf_bytes, strict_prefix + prompt)
        except GeminiParseError as e:
            raise GeminiParseError(
                "Could not extract a valid course list from your transcript after two attempts. "
                "Please try again or check that your PDF is a readable transcript."
            ) from e
