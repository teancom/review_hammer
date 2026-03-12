# Human Test Plan: Review Hammer

Maps each acceptance criterion to manual verification steps for behaviors that cannot be automated (LLM-driven orchestration, live API calls, plugin installation).

## Prerequisites

- Clone `teancom/review_hammer` and install the plugin: `claude plugin install teancom/review_hammer`
- Set environment variable `REVIEWERS_API_KEY` to a valid OpenAI-compatible API key
- Set `REVIEWERS_BASE_URL` and `REVIEWERS_MODEL` if using a non-default endpoint
- Automated tests passing: `.venv/bin/python3 -m pytest tests/test_review_file.py` (48 tests, all green)
- Have a directory with 100+ source files available (or create one with a script)

## Phase 1: Skill Target Handling (AC1)

| Step | Action | Expected |
|------|--------|----------|
| 1.1 | In a Claude Code session, run `/fleet-review tests/fixtures/sample.py` | Skill dispatches file-reviewer agent, calls `review_file.py` per category, returns a formatted report with findings or "no issues found" |
| 1.2 | Create a directory `tests/fixtures/multi/` with at least 3 files in different languages (e.g., `app.py`, `main.go`, `utils.js`). Run `/fleet-review tests/fixtures/multi/` | Skill enumerates all files, dispatches agents for each, returns a consolidated report covering all files |
| 1.3 | Run `/fleet-review /nonexistent/path/here` | Skill reports a clear error message (e.g., "Path does not exist") and does not dispatch any agents |
| 1.4 | Create a temp directory containing only `readme.txt` and `notes.md`. Run `/fleet-review` on that directory | Skill reports "nothing to review" or equivalent; no agents dispatched |

## Phase 2: Live API Integration (AC2.1)

| Step | Action | Expected |
|------|--------|----------|
| 2.1 | Run `scripts/review_file.py tests/fixtures/sample.py --category logic-errors` with a valid `REVIEWERS_API_KEY` | stdout is valid JSON (parseable with `python3 -c "import json,sys; json.load(sys.stdin)"`). Exit code 0 |
| 2.2 | Pipe the output to `python3 -c "import json,sys; d=json.load(sys.stdin); [print(f['lines']) for f in d]"` | Any reported line numbers correspond to actual lines in `tests/fixtures/sample.py` (verify by opening the file) |
| 2.3 | Run with `--category null-safety`, then `--category error-handling` | Each invocation returns valid JSON; findings (if any) are relevant to the requested category |

## Phase 3: Prompt Quality Review (AC3.1)

| Step | Action | Expected |
|------|--------|----------|
| 3.1 | List prompt files: `ls prompts/` | 12 language-specific files plus `generic.md` (python.md, c.md, cpp.md, java.md, csharp.md, javascript.md, typescript.md, kotlin.md, rust.md, go.md, swift.md, generic.md) |
| 3.2 | For each prompt file, count H2 (`##`) sections | Each file has exactly 11 H2 sections: 6 production + 5 test |
| 3.3 | For each H2 section in each file, look for "DO NOT REPORT" block | Every section has a DO NOT REPORT block with language-appropriate constraints |

## Phase 4: Agent Dispatch (AC4)

| Step | Action | Expected |
|------|--------|----------|
| 4.1 | Dispatch file-reviewer agent with a production file (e.g., `scripts/review_file.py`) | Agent output includes `"is_test": false` and `"categories_run"` lists exactly 6 production categories |
| 4.2 | Dispatch file-reviewer agent with a test file (e.g., `tests/test_review_file.py`) | Agent output includes `"is_test": true` and `"categories_run"` lists exactly 5 test categories |
| 4.3 | Dispatch agent with a trivially simple file (e.g., a file containing only `x = 1`) | Agent completes without errors, `"findings": []`, no error messages in output |

## Phase 5: Opus Judge Pass (AC5)

| Step | Action | Expected |
|------|--------|----------|
| 5.1 | Run `/fleet-review` on a file where the same issue would be flagged by multiple categories | Report contains merged finding with `"flagged_by"` listing multiple categories |
| 5.2 | For every critical or high severity finding in the report, open the cited file and go to the cited line numbers | Line numbers match the described code; no off-by-one errors |
| 5.3 | Run `/fleet-review` on a directory containing 5+ files that all have the same anti-pattern | Report includes a "Systemic Patterns" section that groups the repeated issue |
| 5.4 | Check the final report section ordering | Findings appear in severity order: Critical first, then High, then Medium |

## Phase 6: Robustness (AC6.2, AC6.3)

| Step | Action | Expected |
|------|--------|----------|
| 6.1 | Run `scripts/review_file.py` against an unreachable endpoint (`REVIEWERS_BASE_URL=http://localhost:1` with `--timeout 5`) | stderr shows retry attempts with increasing backoff. After 5 retries, outputs `[]` to stdout, exits with code 2 |
| 6.2 | Force one specialist category to timeout during full agent dispatch | Agent continues with remaining categories; report includes `"failed_categories"` |
| 6.3 | Run `/fleet-review` on a directory with 100+ source files | Skill presents file count, estimated API calls, and asks for confirmation before dispatching |

## Phase 7: Plugin Installation (AC7)

| Step | Action | Expected |
|------|--------|----------|
| 7.1 | From a fresh Claude Code session, run `claude plugin install teancom/review_hammer` | Installation succeeds. `/fleet-review` appears in available skills |
| 7.2 | Start a new Claude Code session without `REVIEWERS_API_KEY` set | Session-start hook displays a warning about missing API key |
| 7.3 | Set `REVIEWERS_API_KEY`, restart Claude Code session | Session-start hook displays confirmation with configured values |

## End-to-End: Full Single-File Review

1. Ensure `REVIEWERS_API_KEY` is set and plugin is installed
2. Run `/fleet-review scripts/review_file.py`
3. Verify the skill detects the file as Python, selects `prompts/python.md`
4. Verify the agent identifies it as a production file and runs 6 specialist categories
5. Verify the Opus judge pass produces a severity-ordered report with verified line numbers
6. Total wall-clock time should be under 3 minutes for a single file

## Traceability

| Acceptance Criterion | Automated Test | Manual Step |
|----------------------|----------------|-------------|
| AC1.1 | -- | 1.1 |
| AC1.2 | -- | 1.2 |
| AC1.3 | -- | 1.3 |
| AC1.4 | -- | 1.4 |
| AC2.1 | -- | 2.1-2.3 |
| AC2.2 | `TestExtractCategoryPrompt` (4 tests) | -- |
| AC2.3 | `TestMainCLI` (1 test) | -- |
| AC2.4 | `TestParseFindings` (9 tests) | -- |
| AC3.1 | -- | 3.1-3.3 |
| AC3.2 | `TestDetectLanguage` (11 tests) | -- |
| AC3.3 | `TestDetectLanguage` (2 tests) | -- |
| AC4.1 | -- | 4.1 |
| AC4.2 | -- | 4.2 |
| AC4.3 | -- | 4.3 |
| AC5.1 | -- | 5.1 |
| AC5.2 | -- | 5.2 |
| AC5.3 | -- | 5.3 |
| AC5.4 | -- | 5.4 |
| AC6.1 | `TestRetryAndBackoff` (6 tests) | 6.1 |
| AC6.2 | -- | 6.2 |
| AC6.3 | -- | 6.3 |
| AC7.1 | -- | 7.1 |
| AC7.2 | -- | 7.2-7.3 |
