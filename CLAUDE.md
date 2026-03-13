# Review Hammer

Last verified: 2026-03-12

## Tech Stack
- Python 3.10+ (scripts, tests)
- OpenAI Python SDK (>=1.0.0) — declared as PEP 723 inline dependency
- uv (runs review_file.py with auto-managed dependencies, no venv needed)
- pytest (>=7.0.0)
- Claude Code plugin system (hooks, agents, skills, marketplace)

## Commands
- `uv run scripts/review_file.py FILE --category CATEGORY` - Run a single review
- `uv run scripts/test_corpus.py` - Run review calibration tests against corpus files
- `.venv/bin/pytest tests/` - Run unit tests (dev venv, not used by plugin)

## Project Structure
- `scripts/` - Python CLI backend (review_file.py, ensure-venv.sh)
- `prompts/` - Language-specific prompt templates (12 languages + generic)
- `agents/` - Haiku agent definitions (file-reviewer)
- `skills/` - User-facing skill definitions (/review-hammer orchestrator)
- `hooks/` - Session-start validation + PreToolUse auto-approve hook
- `tests/` - Unit tests for review_file.py + calibration corpus (`tests/corpus/`)
- `docs/` - Design and implementation plans
- `.claude-plugin/` - Plugin manifest (plugin.json) and marketplace catalog (marketplace.json)

## Plugin Distribution
- Marketplace repo: `teancom/review_hammer` on GitHub
- Install: `/plugin marketplace add teancom/review_hammer` then `/plugin install review-hammer@review-hammer-marketplace`
- Versions synced across: `plugin.json`, `marketplace.json` (bump both together)

## Environment Variables
- `REVIEWERS_API_KEY` (required) - API key for OpenAI-compatible endpoint
- `REVIEWERS_BASE_URL` (optional, default: `https://api.z.ai/api/paas/v4/`)
- `REVIEWERS_MODEL` (optional, default: `glm-5`)

## Architecture
The plugin implements a multi-agent code review pipeline:
1. User invokes `/review-hammer <path>` (skill)
2. Skill enumerates files via Glob (no Bash), detects languages, resolves plugin root from cache directory
3. Skill dispatches Haiku file-reviewer agents in batches of 2
4. Each file-reviewer agent runs 5-6 specialist categories via `uv run review_file.py`
5. `review_file.py` sends file + category prompt to external LLM API, returns JSON findings
6. Retry logic: respects RFC 7231 Retry-After header (seconds or HTTP-date), falls back to jittered exponential backoff
7. Opus judge pass deduplicates, verifies line numbers, filters false positives
8. Final severity-ranked markdown report presented to user

## Permission Prompt Minimization
- File enumeration uses Glob tool (built-in, no prompt)
- `review_file.py` calls auto-approved by PreToolUse hook in `hooks/hooks.json`
- Plugin root resolution auto-approved by hook (matches `review-hammer-marketplace`)
- Agent restricted to Bash-only tools, explicitly forbidden from running debug commands
- No venv needed — `uv run` handles dependencies via PEP 723 inline metadata

## Releasing Changes
When changing any plugin-facing file (skills, agents, hooks, scripts), bump the version FIRST:
1. Bump `version` in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` (must match)
2. Make your changes
3. Commit everything together

Do the version bump before editing other files so examples and references stay consistent.

## Conventions
- Prompt templates use `## category-name` headings for section extraction
- Findings JSON schema: `{lines, severity, category, description, impact, confidence}`
- Exit codes: 0=success, 1=config/input error, 2=retries exhausted
- Z.AI GLM-5 concurrency limit: 2 (match agent batch size)
- Corpus metadata schema: `{type, category, language, description, expect_empty}` where type is "clean"|"bug"|"adversarial"
- Corpus files live at `tests/corpus/{language}/` with paired `.ext` + `.json` files sharing the same stem

## Boundaries
- Safe to edit: `scripts/`, `prompts/`, `agents/`, `skills/`, `tests/`
- Coordinate edits: `hooks/hooks.json` (plugin hook registry)
- Sync together: `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` (version must match)
