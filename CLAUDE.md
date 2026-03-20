# Review Hammer

Last verified: 2026-03-20

## Tech Stack
- Python 3.10+ (scripts, tests)
- OpenAI Python SDK (>=1.0.0) — declared as PEP 723 inline dependency
- uv (runs review_file.py with auto-managed dependencies, no venv needed)
- pytest (>=7.0.0)
- Claude Code plugin system (hooks, agents, skills, marketplace)

## Commands
- `uv run scripts/review_file.py FILE --category CATEGORY` - Run a single review (add `--test-context TEST_FILE` for test-suggestions category, add `--diff-base REF` for diff-only review)
- `uv run scripts/test_corpus.py` - Run review calibration tests against corpus files
- `.venv/bin/pytest tests/` - Run unit tests (dev venv, not used by plugin)

## Project Structure
- `scripts/` - Python CLI backend (review_file.py, calibrate_chunk_threshold.py, ensure-venv.sh)
- `prompts/` - Language-specific prompt templates (12 languages + generic)
- `agents/` - Haiku agent definitions (file-reviewer, test-suggester)
- `skills/` - User-facing skill definitions (/review-hammer, /test-hammer orchestrators)
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
- `REVIEWERS_MAX_CONCURRENT` (optional, default: `2`) - Max parallel review agents per batch (shared by file-reviewer and test-suggester)

## Architecture
The plugin implements two multi-agent pipelines sharing the same backend:

### /review-hammer (code review)
1. User invokes `/review-hammer <target>` where target is a path, "this commit", or "this branch" (skill)
2. Skill classifies input into one of five modes: commit, branch, file-diff, file-full, or directory
3. For commit/branch modes, resolves DIFF_BASE via git and gets changed file list from `git diff --name-only`
4. For file/directory modes, enumerates files via Glob, detects languages, discovers test file pairings, classifies per-file dirty/clean status
5. Skill dispatches Haiku file-reviewer and test-suggester agents in batches (default 2, configurable via `REVIEWERS_MAX_CONCURRENT`), passing `DIFF_BASE` for dirty/changed files
6. Each file-reviewer agent runs 5-6 specialist categories via `uv run review_file.py` (with `--diff-base` when in diff mode)
7. Each test-suggester agent runs the test-suggestions category with `--test-context` for paired test files
8. `review_file.py` sends file + category prompt to external LLM API, returns JSON findings; large files (>500 lines) are automatically chunked with overlap and per-chunk deduplication
9. Retry logic: respects RFC 7231 Retry-After header (seconds or HTTP-date), falls back to jittered exponential backoff
10. Opus judge pass deduplicates, verifies line numbers, filters false positives
11. Final severity-ranked markdown report (with input mode context in header) presented to user

### /test-hammer (test suggestions only)
1. User invokes `/test-hammer <path>` (skill)
2. Same enumeration and language detection as review-hammer, but filters to production files only
3. Discovers and pairs existing test files with production files by convention
4. Dispatches test-suggester agents (not file-reviewer) with test context
5. Opus judge pass with hard cap of 3 suggestions per file
6. Severity-ranked test suggestion report

## Permission Prompt Minimization
- File enumeration uses Glob tool (built-in, no prompt)
- `review_file.py` calls auto-approved by PreToolUse hook in `hooks/hooks.json`
- Plugin root resolution auto-approved by hook (matches `review-hammer-marketplace`)
- Agent restricted to Bash-only tools, explicitly forbidden from running debug commands
- No venv needed — `uv run` handles dependencies via PEP 723 inline metadata

## Releasing Changes
When changing any plugin-facing file (scripts/, prompts/, agents/, skills/, hooks/), bump the version in both `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` (must match). A PreToolUse hook (`.claude/hooks/enforce-version-bump.sh`) enforces this at commit time — it will block if plugin-facing files are staged without a matching version bump.

## Conventions
- Prompt templates use `## category-name` headings for section extraction
- Findings JSON schema: `{lines, severity, category, description, impact, confidence}`
- Exit codes: 0=success, 1=config/input error, 2=retries exhausted
- Z.AI GLM-5 concurrency limit: configurable via `REVIEWERS_MAX_CONCURRENT` (default 2)
- Corpus metadata schema: `{type, category, language, description, expect_empty, test_file?}` where type is "clean"|"bug"|"adversarial"
- Optional `test_file` field in corpus metadata names a companion test file (same directory) passed via `--test-context`
- Corpus files live at `tests/corpus/{language}/` with paired `.ext` + `.json` files sharing the same stem

## Boundaries
- Safe to edit: `scripts/`, `prompts/`, `agents/`, `skills/`, `tests/`
- Coordinate edits: `hooks/hooks.json` (plugin hook registry)
- Sync together: `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` (version must match)
