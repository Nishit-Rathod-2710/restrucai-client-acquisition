# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Flask web app that turns plain-English requests (e.g. "Find 10 plumbers in Austin Texas")
into Google Maps lead lists. It parses intent with an LLM, scrapes businesses via Apify,
stores results in Supabase (PostgreSQL), and can enrich leads with contact emails by crawling each
business's own website. Single-user local tool — no auth, runs on `127.0.0.1:5000`.

## Commands

```bash
# Setup (Windows; use source venv/bin/activate on Mac/Linux)
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Run (serves UI + API on http://127.0.0.1:5000, debug mode on)
python app.py

# Reinitialize / inspect the SQLite schema
python db.py
```

There is no test suite, linter, or build step configured.

## Required environment (.env)

The app reads these via `python-dotenv` at startup. Without `APIFY_API_TOKEN`,
scraping raises immediately; without an LLM key, query parsing silently falls back to regex.

- `APIFY_API_TOKEN` — required for scraping (Apify Google Maps actor).
- `OPENROUTER_API_KEY` — preferred LLM provider for intent parsing.
- `OPENAI_API_KEY` — fallback LLM provider (used only if OpenRouter key is absent/fails).
- `FLASK_SECRET_KEY` — optional; defaults to a dev value.
- `SUPABASE_URL` — Supabase project URL (required for DB).
- `SUPABASE_KEY` — Supabase publishable/anon key (required for DB).
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — optional; enable the Notes modal's
  "Inform Team" button (`POST /api/leads/<id>/inform-team`). Without both, the endpoint
  returns a "not configured" error and the button shows it.

## Architecture

The request flow is the key thing to understand — work is split across background threads
and the frontend discovers completion by polling, not by waiting on the original request.

**Campaign creation** (`POST /api/campaigns` in [app.py](app.py)):
1. `parse_requirement()` ([query_builder.py](query_builder.py)) extracts `search_query`,
   `location`, `max_results`. Provider priority: **OpenRouter → OpenAI → regex heuristics**.
   The endpoint returns *immediately* with `campaign_id`; scraping has not finished yet.
2. A daemon thread runs `run_scraper()` ([apify_service.py](apify_service.py)), which calls
   the `compass~crawler-google-places` Apify actor, normalizes each dataset item into a lead
   dict, and inserts rows. Campaign status moves `running` → `completed`/`failed`.
3. The browser ([static/js/app.js](static/js/app.js)) polls `/status` every 5s to detect
   when scraping finishes and to pick up newly-inserted leads mid-run.

**Email enrichment** (`POST /api/campaigns/<id>/enrich`):
- A separate daemon thread runs `enrich_campaign()` ([email_enricher.py](email_enricher.py))
  over leads that have a website but no email. For each, it fetches the homepage plus common
  contact paths, extracts `mailto:`/regex emails, and filters blacklisted addresses.
- Progress lives in the module-level `enrichment_jobs` dict in [app.py](app.py), keyed by
  campaign id. The frontend polls `/enrich/status` every 2s. A `409` guard prevents
  concurrent enrichment of the same campaign.

**Persistence** ([db.py](db.py)): Supabase (PostgreSQL). Two tables — `campaigns` and
`leads` (FK to campaign). All queries use the `supabase-py` client; no raw SQL in app code.
Schema is in [supabase_schema.sql](supabase_schema.sql) — run it once in the Supabase SQL
Editor to create tables. `leads.raw_json` stores the full Apify item as a JSON string.

**AI Email Drafting** (`POST /api/leads/<id>/draft-email` in [app.py](app.py)):
- Synchronous endpoint (no background thread) that calls OpenRouter with the
  `anthropic/claude-sonnet-4.6` model to draft a personalized outreach/follow-up email.
- Prompt templates live in [email_prompts.py](email_prompts.py) — `_generate_system_prompt()`
  branches on `call_status` (Interested / Follow-Up / other) and `_generate_user_prompt()`
  injects lead details plus Notes Q&A items and free-form notes.
- Sender is hardcoded as **Nishit Rathod**; signature must include website
  `www.restrucai.com`, phone `+91 90825 87107`, and LinkedIn
  `https://www.linkedin.com/in/nishit-rathod/` (enforced in the system prompt).
- Response is JSON `{subject, body}`; em-dashes are stripped post-hoc as a fallback.
- The drafted email is then sent via the n8n webhook at `N8N_SEND_URL`.

## Things to know

- **Thread state is in-process and ephemeral.** Both `enrichment_jobs` and the background
  threads live in the single Flask process. Restarting the server loses in-flight job
  progress, and a campaign stuck in `running` (e.g. crash mid-scrape) stays that way in
  Supabase. Campaign data itself persists across restarts (it's in the cloud DB).
- **CSV export is hand-built** (`/export` streams rows in [app.py](app.py)), not a library.
  It strips commas from fields and URL-encodes commas in `google_url`; preserve that escaping
  if you touch it.
- **LLM models are hardcoded** in [query_builder.py](query_builder.py)
  (`openai/gpt-4o-mini` for OpenRouter, `gpt-4o-mini` for OpenAI), using
  `response_format={"type": "json_object"}`.
- **Apify input is deliberately minimal** ([apify_service.py](apify_service.py)): only
  well-documented, non-deprecated actor fields are sent to avoid schema validation errors.
  `scrapeContacts: True` is what lets Apify return emails directly (separate from the free
  website-crawl enrichment path).
- The frontend is vanilla JS with a single global `app` object — no framework, no bundler.
  HTML is rendered via template strings; email inline-editing escapes single quotes manually.
