# Repository Guidelines

## Project Structure & Module Organization

This repository currently contains a single planning document that defines the system architecture and data schemas.

- `roadmap.txt`: primary specification for the Multi-Campus Culture Intelligence Agent (flows, schemas, subagents, scoring, outputs).
- No source code or test directories are present yet; treat `roadmap.txt` as the source of truth until implementation lands.

If you add code, keep it aligned with the schemas and sections in `roadmap.txt` and mirror that organization (e.g., `campus_profiles/`, `subagents/`, `aggregator/`, `outputs/`).

## Build, Test, and Development Commands

There are no build or test scripts in this repository yet.

- Example future commands (add when available):
  - `python -m agent.run --campus usc_la` — run a weekly pipeline.
  - `pytest` — execute unit tests.

If you introduce commands, document them here and keep them minimal and reproducible.

## Coding Style & Naming Conventions

No code style is enforced yet. When adding implementation:

- Prefer consistent, readable naming that mirrors the schema keys in `roadmap.txt` (e.g., `candidate_item`, `final_pick`).
- Keep JSON field names exactly as specified (e.g., `posterability`, `freshness_days`).
- Use 2-space indentation for JSON artifacts and 4-space indentation for code unless the chosen language standard differs.

## Testing Guidelines

No testing framework is configured.

- When tests are added, include:
  - Schema validation tests for `CandidateItem` and `FinalPick`.
  - Deduplication and scoring logic tests based on the rules in `roadmap.txt`.
- Name tests to reflect the behavior (e.g., `test_scoring_weights_applied`).

## Commit & Pull Request Guidelines

There is no commit history to infer conventions. Until one is established:

- Use short, imperative commit messages (e.g., "Add campus profile loader").
- PRs should include:
  - A brief summary of changes.
  - Any new commands or configuration notes.
  - Examples of new outputs (e.g., sample `weekly_digest.json`).

## Security & Configuration Tips

- Treat `campus_profiles/*.json` as configuration, not code.
- Keep trusted domains up to date and aligned with campus policies.
- Avoid storing API keys in the repo; prefer environment variables or a `.env` file (not committed).

## Agent-Specific Notes

- The weekly flow, subagents, and scoring model must match `roadmap.txt`.
- Any deviation from the schema should be justified and documented here.

## How to run

Run commands (from repo root):

source .venv/bin/activate
export GEMINI_API_KEY=YOUR_KEY   # or keep it in .env
PYTHONPATH=src python -m auto_news_agent.cli --campus usc_la --print
