import json
import os
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

from gemini_extractor import GeminiParseError, GeminiServerError, call_gemini_with_retry
from requirements_checker import check_requirements

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

RATE_LIMIT_ANALYSES_PER_HOUR = int(os.environ.get("RATE_LIMIT_ANALYSES_PER_HOUR", "6"))
_analysis_requests_by_ip = defaultdict(deque)


def _load_state_keys() -> list:
    path = os.path.join(os.path.dirname(__file__), "state_requirements.json")
    with open(path, "r") as f:
        data = json.load(f)
    # Return display names in a consistent order
    return [v["state"] for v in data.values()]


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _rate_limit_ok(ip: str) -> bool:
    if RATE_LIMIT_ANALYSES_PER_HOUR <= 0:
        return True

    now = time.time()
    window_start = now - 3600
    requests_for_ip = _analysis_requests_by_ip[ip]

    while requests_for_ip and requests_for_ip[0] < window_start:
        requests_for_ip.popleft()

    if len(requests_for_ip) >= RATE_LIMIT_ANALYSES_PER_HOUR:
        return False

    requests_for_ip.append(now)
    return True


@app.after_request
def add_privacy_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.endpoint in {"check", "recalculate"}:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(RequestEntityTooLarge)
def file_too_large(_error):
    return jsonify({"error": "Please upload a PDF smaller than 10 MB."}), 413


def _looks_like_pdf(pdf_bytes: bytes) -> bool:
    return pdf_bytes.startswith(b"%PDF-")


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
    if not _looks_like_pdf(pdf_bytes):
        return jsonify({"error": "Please upload a valid PDF transcript."}), 400

    if not _rate_limit_ok(_client_ip()):
        return jsonify({
            "error": "Too many transcript analyses from this connection. Please wait a bit and try again."
        }), 429

    try:
        extraction = call_gemini_with_retry(pdf_bytes, state)
    except GeminiParseError as e:
        return jsonify({"error": str(e)}), 422
    except GeminiServerError:
        return jsonify({"error": "Gemini is temporarily unavailable due to high demand. Please wait a moment and try again."}), 503
    except Exception:
        app.logger.error("Unexpected transcript analysis error.")
        return jsonify({"error": "An unexpected error occurred while analyzing your transcript. Please try again."}), 500

    courses = extraction.get("courses", [])
    graduation_status = extraction.get("graduation_status", "unknown")

    try:
        results = check_requirements(courses, state, graduation_status)
    except Exception:
        app.logger.error("Unexpected requirements checking error.")
        return jsonify({"error": "An unexpected error occurred while checking requirements. Please try again."}), 500

    return jsonify({"courses": courses, "results": results, "graduation_status": graduation_status})


@app.route("/recalculate", methods=["POST"])
def recalculate():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided."}), 400

    courses = data.get("courses", [])
    state = data.get("state", "").strip()
    graduation_status = data.get("graduation_status", "unknown")

    valid_states = [s.lower() for s in _load_state_keys()]
    if state.lower() not in valid_states:
        return jsonify({"error": "Invalid state."}), 400

    try:
        results = check_requirements(courses, state, graduation_status)
    except Exception:
        app.logger.error("Unexpected recalculation error.")
        return jsonify({"error": "An unexpected error occurred."}), 500

    return jsonify({"results": results})


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)
