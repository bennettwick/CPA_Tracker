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
  "courses": [
    {
      "name": "<exact course name from transcript>",
      "credits": <number>,
      "grade": "<letter grade or null>",
      "year": <four-digit year or null>,
      "level": "undergrad" or "grad" or null,
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

If a course does not match any topic above, use one of these fallback categories:
- general_business — business courses not matching a specific topic above
- other — non-accounting, non-business courses (e.g., English, PE, electives)
- unclear — only if you genuinely cannot determine the subject area

For the "level" field:
- Use "grad" ONLY if the transcript explicitly marks the course as graduate-level (e.g., course number 5000+, "Graduate" section header, "G" prefix, or similar)
- Use "undergrad" for all other courses
- Use null only if the transcript gives no indication at all

Return ONLY valid JSON. No markdown. No code fences. No explanation. Start with {{ and end with }}.

Use this exact schema:
{COURSE_SCHEMA}

Rules:
- Include ALL courses on the transcript, not just accounting ones
- Use the exact course name as printed on the transcript
- credits must be a number (e.g., 3 or 3.0)
- grade must be the letter grade shown (e.g., "A", "B+", "C-") or null if not shown
- year must be the four-digit year the course was taken, or null if not shown
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
