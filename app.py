import json
import os
import traceback

from flask import Flask, jsonify, render_template, request

from gemini_extractor import GeminiParseError, call_gemini_with_retry
from requirements_checker import check_requirements

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB


def _load_state_keys() -> list:
    path = os.path.join(os.path.dirname(__file__), "state_requirements.json")
    with open(path, "r") as f:
        data = json.load(f)
    # Return display names in a consistent order
    return [v["state"] for v in data.values()]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/states", methods=["GET"])
def get_states():
    return jsonify({"states": _load_state_keys()})


@app.route("/check", methods=["POST"])
def check():
    if "transcript" not in request.files:
        return jsonify({"error": "No transcript file uploaded."}), 400

    file = request.files["transcript"]
    state = request.form.get("state", "").strip()

    if not file.filename:
        return jsonify({"error": "No transcript file selected."}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Please upload a PDF file."}), 400

    valid_states = [s.lower() for s in _load_state_keys()]
    if state.lower() not in valid_states:
        return jsonify({"error": "Please select a valid state."}), 400

    pdf_bytes = file.read()

    try:
        extraction = call_gemini_with_retry(pdf_bytes, state)
    except GeminiParseError as e:
        return jsonify({"error": str(e)}), 422
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred while analyzing your transcript. Please try again."}), 500

    courses = extraction.get("courses", [])
    graduation_status = extraction.get("graduation_status", "unknown")

    try:
        results = check_requirements(courses, state, graduation_status)
    except Exception:
        traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred while checking requirements. Please try again."}), 500

    return jsonify({"courses": courses, "results": results})


if __name__ == "__main__":
    app.run(debug=True)
