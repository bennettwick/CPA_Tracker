# CPA Tracker

Flask app for checking uploaded transcript PDFs against state CPA exam eligibility requirements. The app is stateless: PDFs are read into memory for the request, sent to Gemini, checked against `state_requirements.json`, and not stored by the app.

## Local Development

1. Copy `.env.example` to `.env`.
2. Set `GEMINI_API_KEY` in `.env`.
3. Install dependencies.
4. Run:

```bash
uv run python app.py
```

## Deploy On Render Free

This repository includes `render.yaml` for Render Blueprint deploys.

1. Push this repo to GitHub.
2. In Render, create a new Blueprint from the repo.
3. Use the free web service plan.
4. Add the `GEMINI_API_KEY` environment variable when Render asks for it.
5. Keep `FLASK_DEBUG=0`.

The Render start command is:

```bash
gunicorn app:app --workers 2 --threads 4 --timeout 180 --bind 0.0.0.0:$PORT
```

## Public Use Notes

- Upload limit is 10 MB.
- `RATE_LIMIT_ANALYSES_PER_HOUR` defaults to 6 analyses per IP address per hour. Set it to `0` to disable the in-memory limit.
- Render Free services sleep after inactivity, so the first visitor after idle time may see a short cold start delay.
- The Gemini API key stays server-side. Do not commit `.env`.
