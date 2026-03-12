# Review Hammer

Last verified: 2026-03-11

## Tech Stack
- Python 3.x (scripts, tests)
- OpenAI Python SDK (>=1.0.0)
- pytest (>=7.0.0)
- Claude Code plugin system (hooks, agents, skills)

## Commands
- `source .venv/bin/activate` - Activate Python venv (always use this)
- `.venv/bin/pytest tests/` - Run unit tests
- `.venv/bin/python scripts/review_file.py FILE --category CATEGORY` - Run a single review

## Project Structure
- `scripts/` - Python CLI backend (review_file.py)
- `prompts/` - Language-specific prompt templates (12 languages + generic)
- `agents/` - Haiku agent definitions (file-reviewer)
- `skills/` - User-facing skill definitions (/fleet-review orchestrator)
- `hooks/` - Session-start hook for env var validation
- `tests/` - Unit tests for review_file.py
- `docs/` - Design and implementation plans
- `.claude-plugin/` - Plugin manifest (plugin.json)

## Environment Variables
- `REVIEWERS_API_KEY` (required) - API key for OpenAI-compatible endpoint
- `REVIEWERS_BASE_URL` (optional, default: `https://api.z.ai/api/paas/v4/`)
- `REVIEWERS_MODEL` (optional, default: `glm-5`)
- `REVIEWERS_MAX_CONCURRENT` (optional, default: `3`)

## Architecture
The plugin implements a multi-agent code review pipeline:
1. User invokes `/fleet-review <path>` (skill)
2. Skill enumerates files, detects languages, dispatches Haiku file-reviewer agents in batches
3. Each file-reviewer agent runs 5-6 specialist categories via `review_file.py`
4. `review_file.py` sends file + category prompt to external LLM API, returns JSON findings
5. Opus judge pass deduplicates, verifies line numbers, filters false positives
6. Final severity-ranked markdown report presented to user

## Conventions
- Python virtual environment at `.venv/` -- always use it
- Prompt templates use `## category-name` headings for section extraction
- Findings JSON schema: `{lines, severity, category, description, impact, confidence}`
- Exit codes: 0=success, 1=config/input error, 2=retries exhausted

## Boundaries
- Safe to edit: `scripts/`, `prompts/`, `agents/`, `skills/`, `tests/`
- Coordinate edits: `hooks/hooks.json` (plugin hook registry)
- Never touch: `.claude-plugin/plugin.json` without intent to change plugin identity
