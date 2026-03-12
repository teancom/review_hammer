# Scripts - Review File Backend

Last verified: 2026-03-11

## Purpose
Provides the Python CLI that sends a single file + specialist category to an
OpenAI-compatible API and returns structured JSON findings. This is the only
component that talks to the external LLM.

## Contracts
- **Exposes**: `review_file()` function and CLI entry point
- **Guarantees**:
  - Output is always a JSON array of findings (or `[]` on failure)
  - Retries transient errors (rate-limit, timeout, connection) up to 5 times with exponential backoff
  - Never retries authentication errors
  - Exit code 2 + empty JSON `[]` on exhausted retries
  - Line numbers prepended as `{n}| {line}` format before sending to API
- **Expects**:
  - `REVIEWERS_API_KEY` env var or `--api-key` flag
  - Prompt template at `../prompts/{language}.md` relative to script
  - Category must exist as `## {category}` heading in the template

## Dependencies
- **Uses**: `prompts/{language}.md` templates (sibling directory), OpenAI SDK
- **Used by**: `agents/file-reviewer.md` (invoked via Bash)
- **Boundary**: Does not know about orchestration, batching, or deduplication

## Key Decisions
- Manual retry loop (not SDK retries): Gives control over backoff and error classification
- Temperature 0: Deterministic reviews for consistency
- Markdown fence extraction: Handles LLMs that wrap JSON in code fences

## Invariants
- Finding schema is fixed: `{lines, severity, category, description, impact, confidence}`
- Severity values: "critical", "high", "medium" only
- Language detection uses EXTENSION_MAP; unknown extensions fall back to "generic"

## Key Files
- `review_file.py` - All logic (detection, prompting, API calls, parsing)
- `requirements.txt` - Python dependencies (openai, pytest)
