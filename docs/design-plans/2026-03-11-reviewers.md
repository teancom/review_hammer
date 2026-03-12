# Review Hammer Design

## Summary

Review Hammer is a Claude Code plugin that performs high-precision automated code review by combining a fleet of cheap, specialized LLM agents with a final Opus judge pass. The core insight is a division of labor: a cost-effective backend model (any OpenAI-compatible endpoint) handles volume by running one focused specialist per category per file, while Claude Opus acts as a senior reviewer who deduplicates findings, verifies line numbers against actual source, filters false positives, and groups systemic patterns before presenting a ranked final report.

The approach uses category isolation to improve signal quality — each specialist is given a narrow mandate (e.g., only resource leaks, or only race conditions) along with explicit DO NOT REPORT constraints tuned to the language. Production code and test code are treated as separate concerns with different specialist sets. The plugin is structured as a standard Claude Code plugin: a Python script handles the API calls, per-language prompt templates define specialist behavior, a Haiku collector agent fans out across categories for a single file, and a top-level Opus orchestrator skill handles file enumeration, agent dispatch, and the final judge pass for any target from a single function to an entire repo.

## Definition of Done

A Claude Code plugin (`teancom/review_hammer`) that dispatches category-specialized code review agents to any OpenAI-compatible LLM endpoint, then uses Opus as a judge layer to produce high-precision findings. The plugin:

1. **Provides a skill** that takes any code target (function, file, directory, repo) and dispatches category-specialized review agents — using the proven recipe: line-numbered source, tight per-category DO NOT REPORT constraints, language-aware prompts
2. **Is backend-agnostic** — works with any OpenAI-compatible API endpoint (z.ai/GLM-5, Ollama, OpenRouter, Together, Groq, etc.), configured via environment variables (`REVIEWERS_API_KEY`, `REVIEWERS_BASE_URL`, `REVIEWERS_MODEL`)
3. **Includes a Python script** that handles the API calls (one file + one specialist category per invocation, rate-limit-aware with configurable concurrency)
4. **Uses Opus as the judge layer** — deduplicates findings across specialists, filters remaining false positives, produces a final ranked report
5. **Is language-aware** — detects language from file extension, selects appropriate specialist prompts (coroutine patterns for Kotlin, async patterns for Python/JS, memory safety for Rust, etc.)
6. **Handles multi-file orchestration** — when given a directory or repo, enumerates files, chunks intelligently, manages the fleet across all targets
7. **Is installable** as a standard Claude Code plugin from GitHub

## Acceptance Criteria

### reviewers.AC1: Skill accepts any code target
- **reviewers.AC1.1 Success:** Skill accepts a single file path, reviews it, returns findings
- **reviewers.AC1.2 Success:** Skill accepts a directory, enumerates files, reviews each, returns consolidated findings
- **reviewers.AC1.3 Failure:** Skill given a non-existent path reports clear error
- **reviewers.AC1.4 Edge:** Skill given a directory with no supported-language files reports "nothing to review"

### reviewers.AC2: Python script produces correct findings
- **reviewers.AC2.1 Success:** Script sends line-numbered code to API and returns valid JSON with correct line numbers
- **reviewers.AC2.2 Success:** Script reads prompt template for correct language and extracts correct category section
- **reviewers.AC2.3 Failure:** Script returns clear error when API key is missing or invalid
- **reviewers.AC2.4 Edge:** Script handles API returning empty/malformed response without crashing

### reviewers.AC3: Language-aware prompts
- **reviewers.AC3.1 Success:** Each of 12 language prompt files contains language-specific specialist sections with appropriate DO NOT REPORT constraints
- **reviewers.AC3.2 Success:** File extension correctly maps to language (e.g., .kt->kotlin, .swift->swift, .rs->rust)
- **reviewers.AC3.3 Edge:** Unknown file extension falls back to generic.md

### reviewers.AC4: Collector agent dispatches specialists correctly
- **reviewers.AC4.1 Success:** Agent detects production file and runs 6 production specialist categories
- **reviewers.AC4.2 Success:** Agent detects test file and runs 5 test specialist categories
- **reviewers.AC4.3 Edge:** Agent handles specialist returning "No findings" without error

### reviewers.AC5: Opus judge pass produces high-precision output
- **reviewers.AC5.1 Success:** Duplicate findings from multiple specialists are merged into one
- **reviewers.AC5.2 Success:** High-severity findings have line numbers verified against actual code
- **reviewers.AC5.3 Success:** Systemic patterns across files are grouped rather than listed individually
- **reviewers.AC5.4 Success:** Final report is ranked by severity (critical -> high -> medium)

### reviewers.AC6: Robustness under real-world conditions
- **reviewers.AC6.1 Success:** 429 rate limit errors are retried with backoff
- **reviewers.AC6.2 Success:** Individual specialist timeout doesn't kill the whole review
- **reviewers.AC6.3 Success:** Large repo (100+ files) prompts user for confirmation before proceeding

### reviewers.AC7: Installable plugin
- **reviewers.AC7.1 Success:** `claude plugin install teancom/review_hammer` works
- **reviewers.AC7.2 Success:** Session-start hook warns when REVIEWERS_API_KEY is not set

## Glossary

- **Claude Code plugin**: A packaged extension for the Claude Code CLI, installable via `claude plugin install <owner>/<repo>`. Bundles skills, agents, hooks, and scripts.
- **Skill**: A user-invocable workflow defined as markdown (`SKILL.md`). Invoked with a slash command (e.g., `/fleet-review`).
- **Agent**: A subagent definition (markdown + YAML frontmatter) specifying model, role, and instructions. Dispatched programmatically by skills.
- **Opus / Haiku**: Claude model tiers. Opus is most capable (used for judgment); Haiku is cheaper (used for high-volume specialist dispatch).
- **Collector agent**: The Haiku agent that receives one file, detects test/production status, and calls `review_file.py` per specialist category.
- **Orchestrator skill**: The user-facing entry point that enumerates files, dispatches collector agents, and runs the Opus judge pass.
- **Specialist category**: A narrow review focus (e.g., `race-conditions`, `over-mocking`). One `review_file.py` invocation = one file, one category.
- **DO NOT REPORT constraints**: Per-language, per-category instructions telling the model what not to flag — suppresses known false-positive-prone patterns.
- **Judge pass**: The final Opus step: dedup, line verification, false positive filtering, cross-file pattern detection, severity-ranked report.
- **OpenAI-compatible API**: Any LLM endpoint using the OpenAI HTTP format. Lets the plugin work with Ollama, OpenRouter, Groq, Together, GLM-5, etc.
- **Line-numbered source**: Code preprocessed to prepend line numbers before sending to the LLM, enabling findings to reference exact locations.
- **Session-start hook**: Shell script that fires on Claude Code session start, warns if required env vars are missing.
- **Test file detection**: Heuristic identifying test files by name pattern (`*Test.*`, `test_*.*`) or directory (`test/`, `__tests__/`, `spec/`).

## Architecture

### Components

Four components with clear separation of concerns:

**1. Python Script (`scripts/review_file.py`)**

Single-file, single-category reviewer. Takes a file path, specialist category, and API configuration. Prepends line numbers to source code, loads the appropriate language prompt template, extracts the section for the requested category, assembles the final prompt, and calls the OpenAI-compatible API. Returns JSON findings. Handles 429 rate-limit retries internally with exponential backoff.

Does not enumerate files, pick categories, or judge quality.

**2. Specialist Prompt Templates (`prompts/*.md`)**

One markdown file per language. Each contains a preamble (language context, general rules) and 6 specialist sections for production code, plus test-specific specialist sections.

Production specialists (applied to non-test files):
- race-conditions / concurrency
- null-safety / memory-safety / type-safety (language-dependent naming)
- resource-leaks
- logic-errors
- error-handling
- state-management

Test specialists (applied to test files):
- testing-nothing (assertions that verify mocks or language semantics, not behavior)
- missing-assertions (code runs but nothing meaningful is checked)
- over-mocking (so much mocked that no real code is exercised)
- brittle-tests (testing implementation details instead of behavior)
- missing-edge-cases (happy path only)

Each specialist section includes tight DO NOT REPORT constraints tuned to the language. Adding a new language requires only a new markdown file — no code changes.

Supported languages (12 + generic fallback):
- Python, C, C++, Java, C#, JavaScript, TypeScript, Kotlin, Rust, Go, Swift, and a generic fallback

**3. Collector Agent (`agents/file-reviewer.md`, Haiku model)**

Receives one file path and its detected language. Determines whether the file is a test file (by filename pattern and directory convention). Calls `review_file.py` once per relevant specialist category (6 calls for production, 5 for tests). Manages sequencing with configurable delay between calls. Formats findings into consistent JSON structure. Returns all findings for that file tagged by category.

Test file detection: `*Test.*`, `*_test.*`, `test_*.*`, `*Spec.*`, `*Tests.*`, files under `test/`, `tests/`, `__tests__/`, `spec/` directories.

**4. Orchestrator Skill (`skills/fleet-review/SKILL.md`)**

User-facing entry point. Accepts any code target: file path, directory, or repo root. Enumerates files by walking the target path and matching extensions to supported languages. Filters out binaries, generated files, build artifacts, `node_modules/`, `.git/`, etc. Respects `.gitignore`.

For large repos: presents file count and estimated API calls to the user, asks whether to proceed or narrow scope.

Dispatches one Haiku collector agent per file (parallelized). Collects all findings across all files. Runs the Opus judge pass:

1. Deduplication — same bug found by multiple specialists merged, noting which categories flagged it
2. Line number verification — for high-severity findings, reads actual code at cited lines via Read tool
3. False positive filtering — applies Opus judgment to each finding
4. Cross-file pattern detection — systemic anti-patterns grouped rather than listed N times
5. Final ranked report presented to user

### Data Flow

```
User: /fleet-review ./src/
  │
  ▼
Skill (Opus): enumerate files, detect languages, filter
  │
  ├─► Haiku Agent: file_a.kt (kotlin, production)
  │     ├─► review_file.py --category race-conditions
  │     ├─► review_file.py --category null-safety
  │     ├─► review_file.py --category resource-leaks
  │     ├─► review_file.py --category logic-errors
  │     ├─► review_file.py --category error-handling
  │     └─► review_file.py --category state-management
  │     └── returns: [{lines, category, severity, description, impact, confidence}, ...]
  │
  ├─► Haiku Agent: file_b_test.kt (kotlin, test)
  │     ├─► review_file.py --category testing-nothing
  │     ├─► review_file.py --category missing-assertions
  │     ├─► review_file.py --category over-mocking
  │     ├─► review_file.py --category brittle-tests
  │     └─► review_file.py --category missing-edge-cases
  │     └── returns: [{lines, category, severity, description, impact, confidence}, ...]
  │
  ▼
Skill (Opus): dedup → verify → filter → rank → report
```

### Configuration

Environment variables:
- `REVIEWERS_API_KEY` — API key for the backend (required)
- `REVIEWERS_BASE_URL` — base URL, defaults to `https://api.z.ai/api/paas/v4/`
- `REVIEWERS_MODEL` — model ID, defaults to `glm-5`
- `REVIEWERS_MAX_CONCURRENT` — max parallel API calls, defaults to `3`

A session-start hook checks that `REVIEWERS_API_KEY` is set and warns if not.

### Finding Format

Standard JSON structure returned by `review_file.py` and consumed by the collector agent:

```json
{
  "lines": [574, 574],
  "severity": "critical",
  "category": "logic-error",
  "description": "list[index] without bounds check",
  "impact": "IndexOutOfBoundsException when player list shrinks",
  "confidence": 0.95
}
```

### File Chunking

- Files under ~3,000 lines: sent whole
- Files over ~3,000 lines: split by top-level declarations and reviewed per chunk (Python script accepts optional line range)

## Existing Patterns

This plugin follows the Claude Code plugin conventions established by ed3d-plugins:

- Skills as orchestrator markdown (`skills/<name>/SKILL.md`)
- Agents as markdown with YAML frontmatter (`agents/<name>.md`)
- Hooks via `hooks/hooks.json` with shell scripts
- Plugin metadata in `.claude-plugin/plugin.json`
- Supporting scripts in `scripts/` invoked via Bash tool

The orchestration pattern (skill dispatches subagents, subagents do work, results bubble up) follows the same pattern as `requesting-code-review` in ed3d-plan-and-execute.

New pattern introduced: external API calls from a Python script invoked by subagents. No existing plugin does this, but the mechanism is standard (Bash tool runs script, agent reads output).

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Plugin Scaffolding
**Goal:** Working plugin structure installable via `claude plugin install`

**Components:**
- `.claude-plugin/plugin.json` — plugin metadata (name, version, author, description)
- `hooks/hooks.json` + `hooks/session-start.sh` — env var validation on session start
- `README.md` — setup instructions (env vars, install command)

**Dependencies:** None

**Done when:** Plugin installs cleanly, session-start hook fires and reports env var status
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Python Script Core
**Goal:** `review_file.py` can send a single file + category to an OpenAI-compatible API and return structured JSON findings

**Components:**
- `scripts/review_file.py` — CLI script accepting file path, category, language, and API config args/env vars. Prepends line numbers, loads prompt template, calls API, parses response, outputs JSON.
- `scripts/requirements.txt` — `openai` dependency
- `prompts/generic.md` — generic language prompt with all 6 production specialist sections and 5 test specialist sections

**Dependencies:** Phase 1 (plugin exists)

**Done when:** Running `review_file.py` against a known file produces valid JSON findings with correct line numbers. Covers: reviewers.AC2.1, reviewers.AC2.2, reviewers.AC2.3, reviewers.AC2.4
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Language Prompt Templates
**Goal:** All 12 language-specific prompt files with tuned specialist categories

**Components:**
- `prompts/python.md`, `prompts/c.md`, `prompts/cpp.md`, `prompts/java.md`, `prompts/csharp.md`, `prompts/javascript.md`, `prompts/typescript.md`, `prompts/kotlin.md`, `prompts/rust.md`, `prompts/go.md`, `prompts/swift.md`
- Language detection logic in `review_file.py` (extension → language mapping)

**Dependencies:** Phase 2 (script works with generic prompts)

**Done when:** Each prompt file contains language-appropriate specialist sections with language-specific DO NOT REPORT constraints. Script correctly selects prompt file based on file extension. Covers: reviewers.AC3.1, reviewers.AC3.2
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Collector Agent
**Goal:** Haiku agent that reviews a single file by dispatching all specialist categories

**Components:**
- `agents/file-reviewer.md` — Haiku agent definition with instructions for calling `review_file.py` per category, detecting test files, formatting results

**Dependencies:** Phase 2 (script works), Phase 3 (prompts exist)

**Done when:** Agent receives a file path, detects language and test/production status, runs appropriate specialist categories, returns consolidated JSON findings. Covers: reviewers.AC4.1, reviewers.AC4.2
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Orchestrator Skill
**Goal:** User-facing skill that handles file enumeration, agent dispatch, and the Opus judge pass

**Components:**
- `skills/fleet-review/SKILL.md` — orchestrator instructions covering file enumeration, language detection, filtering, agent dispatch, judge pass workflow, and report formatting

**Dependencies:** Phase 4 (collector agent works)

**Done when:** User can invoke the skill with a file, directory, or repo path. Skill enumerates files, dispatches collector agents, collects findings, runs Opus judge pass, and presents final ranked report. Covers: reviewers.AC1.1, reviewers.AC1.2, reviewers.AC5.1, reviewers.AC5.2, reviewers.AC5.3, reviewers.AC5.4
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Rate Limiting and Robustness
**Goal:** Reliable operation under API rate limits and error conditions

**Components:**
- Rate limit handling in `scripts/review_file.py` — 429 retry with exponential backoff
- Configurable concurrency via `REVIEWERS_MAX_CONCURRENT`
- Timeout handling — individual specialist timeouts don't kill the whole review
- Large repo flow — file count/estimate prompt before proceeding

**Dependencies:** Phase 5 (full pipeline works)

**Done when:** Plugin handles 429 errors gracefully, respects concurrency limits, survives individual specialist timeouts, and prompts user before reviewing large repos. Covers: reviewers.AC6.1, reviewers.AC6.2, reviewers.AC6.3
<!-- END_PHASE_6 -->

## Additional Considerations

**Test file review is a first-class feature.** The test specialist categories are intentionally different from production categories. Test anti-patterns are a specific problem the user has encountered repeatedly with LLM-generated tests.

**Prompt template extensibility.** Adding a new language requires only a new markdown file in `prompts/`. The file naming convention matches the language key in the extension mapping. Community contributions can add languages without touching Python code.

**The Opus judge pass is where trust is built.** The external model (GLM-5 or whatever backend is configured) handles volume; Opus handles judgment. This separation is the core insight from the prototype experiment — specialist agents achieved 100% precision on a 1,623-line Kotlin file, and false positives that slip through are caught by Opus reading the actual code.
