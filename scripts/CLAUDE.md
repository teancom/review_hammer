# Scripts - Review File Backend

Last verified: 2026-03-20

## Purpose
Provides the Python CLI that sends a single file + specialist category to an
OpenAI-compatible API and returns structured JSON findings. This is the only
component that talks to the external LLM.

## Contracts
- **Exposes**: `review_file()` function and CLI entry point
- **Guarantees**:
  - Output is always a JSON array of findings (or `[]` on failure)
  - Retries transient errors (rate-limit, timeout, connection) up to 5 times
  - Respects RFC 7231 Retry-After header (seconds or HTTP-date), falls back to jittered exponential backoff
  - Never retries authentication errors
  - Exit code 2 + empty JSON `[]` on exhausted retries
  - Line numbers prepended as `{n}| {line}` format before sending to API
  - In diff mode (`--diff-base`): Gracefully skips binary files and deleted files with stderr logging
- **Expects**:
  - `REVIEWERS_API_KEY` env var or `--api-key` flag
  - Prompt template at `../prompts/{language}.md` relative to script
  - Category must exist as `## {category}` heading in the template

## Dependencies
- **Uses**: `prompts/{language}.md` templates (sibling directory), OpenAI SDK
- **Runtime**: `uv run` with PEP 723 inline script metadata (no venv required)
- **Used by**: `agents/file-reviewer.md` (invoked via `uv run` in Bash)
- **Boundary**: Does not know about orchestration, batching, or deduplication

## Key Decisions
- Manual retry loop (not SDK retries): Gives control over backoff, Retry-After, and error classification
- PEP 723 inline deps: Eliminates venv bootstrap, `uv` caches the environment automatically
- Temperature 0: Deterministic reviews for consistency
- Markdown fence extraction: Handles LLMs that wrap JSON in code fences

## Invariants
- Finding schema is fixed: `{lines, severity, category, description, impact, confidence}`
- Severity values: "critical", "high", "medium" only
- Language detection uses EXTENSION_MAP; unknown extensions fall back to "generic"

## Key Files
- `review_file.py` - All logic (detection, prompting, API calls, retry, parsing)
- `test_corpus.py` - Calibration test runner; discovers `tests/corpus/` cases and validates review results against expected outcomes
- `ensure-venv.sh` - Legacy venv bootstrap (unused since v0.7.0, kept for dev)
- `requirements.txt` - Python dependencies for dev venv (openai, pytest)
