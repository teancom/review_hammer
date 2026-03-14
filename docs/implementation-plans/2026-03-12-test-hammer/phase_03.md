# Test Hammer Implementation Plan — Phase 3: Test-Suggester Agent

**Goal:** Create a dedicated Haiku agent for test suggestion dispatch, following the file-reviewer agent pattern.

**Architecture:** The test-suggester agent mirrors `agents/file-reviewer.md` but runs a single category (`test-suggestions`) instead of 5-6 categories. It receives an additional `TEST_FILES:` input containing paths to existing test files, which it passes as `--test-context` flags to `review_file.py`. The existing `hooks/auto-approve-review.sh` already auto-approves any command containing `review_file.py`, so no hook changes are needed.

**Tech Stack:** Claude Code plugin system (agents, hooks)

**Scope:** 6 phases from original design (this is phase 3 of 6)

**Codebase verified:** 2026-03-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### test-hammer.AC1: Standalone `/test-hammer <path>` skill
- **test-hammer.AC1.3 Success:** Test-suggester agent invokes `review_file.py` with `--test-context` flag and returns JSON findings

### test-hammer.AC5: Cross-cutting behaviors
- **test-hammer.AC5.1 Success:** `hooks/auto-approve-review.sh` auto-approves test-suggester's `review_file.py` invocations with `--test-context` flag (no permission prompts)

---

<!-- START_TASK_1 -->
### Task 1: Create `agents/test-suggester.md` agent definition

**Verifies:** test-hammer.AC1.3

**Files:**
- Create: `agents/test-suggester.md`

**Implementation:**

Create a new agent definition following the exact pattern of `agents/file-reviewer.md` (YAML frontmatter + markdown instructions). The test-suggester agent:

- Receives `FILE_PATH`, `LANGUAGE`, `PLUGIN_ROOT`, and `TEST_FILES` (new — comma-separated list of test file paths, or "none")
- Runs a single category: `test-suggestions`
- Constructs the `review_file.py` command with `--test-context` for each test file
- Returns findings in the same JSON output format as file-reviewer

```markdown
---
name: test-suggester
description: Suggests high-value tests for a single production file by running the test-suggestions category. Dispatched by the test-hammer or review-hammer skill — do not invoke directly.
model: haiku
tools: Bash
---

# Test Suggester Agent

You are a test suggestion agent. You run the `test-suggestions` review category against a single production file, optionally including existing test files as context.

**CRITICAL RULES:**
- ONLY run the `timeout ... review_file.py` command defined below
- Do NOT run echo, ls, find, which, printenv, or ANY other commands
- Do NOT try to debug, verify paths, or check the environment
- If the review command fails, log the failure and return empty findings

## Inputs

You will receive a prompt containing:
- `FILE_PATH:` — the path to the production file to analyze
- `LANGUAGE:` — the programming language
- `PLUGIN_ROOT:` — the absolute path to the plugin directory (use this in commands)
- `TEST_FILES:` — comma-separated paths to existing test files, or "none"

Parse these four values from the prompt text.

## Process

### 1. Build Command

Construct the review command:

```
timeout 180 uv run PLUGIN_ROOT/scripts/review_file.py FILE_PATH --category test-suggestions --language LANGUAGE
```

If `TEST_FILES` is NOT "none", append `--test-context` for each test file path:

```
timeout 180 uv run PLUGIN_ROOT/scripts/review_file.py FILE_PATH --category test-suggestions --language LANGUAGE --test-context TEST_FILE_1 --test-context TEST_FILE_2
```

Replace `PLUGIN_ROOT`, `FILE_PATH`, `LANGUAGE`, and `TEST_FILE_*` with the actual literal values from your inputs. Do NOT use shell variables like `${CLAUDE_PLUGIN_ROOT}`.

### 2. Execute

Run the command via the Bash tool.

- If it fails (timeout, non-zero exit): record the error
- Parse stdout as JSON
- If parsing fails or result is `[]`: no suggestions found (not an error)
- If result is non-empty array: collect the findings

## Output

Output a single JSON object:

```json
{
  "file": "path/to/file.py",
  "language": "python",
  "findings": [
    {
      "lines": [10, 12],
      "severity": "high",
      "category": "test-suggestions",
      "description": "Test state transition from Connected to Disconnected — disconnect during active send could leave socket in half-open state",
      "impact": "Untested state transition may cause resource leaks in production",
      "confidence": 0.85
    }
  ],
  "test_files_provided": ["tests/test_connection.py"],
  "error": null
}
```

If the review command failed, set `error` to the error message and `findings` to `[]`.
```

**Verification:**

Verify the agent file has valid YAML frontmatter:
```bash
head -6 agents/test-suggester.md
```
Expected: Valid `---` delimited YAML with `name`, `description`, `model`, `tools` fields.

**Commit:** `feat: add test-suggester agent definition`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify auto-approve hook covers `--test-context` invocations

**Verifies:** test-hammer.AC5.1

**Files:** None (verification only — no changes needed)

**Implementation:**

The existing `hooks/auto-approve-review.sh` line 32 matches any command containing `review_file.py`:

```bash
if echo "$COMMAND" | grep -q "review_file.py"; then
  approve "review_file.py auto-approved by Review Hammer plugin"
fi
```

This already covers commands like:
```
timeout 180 uv run /path/to/scripts/review_file.py src/main.rs --category test-suggestions --language rust --test-context tests/test_main.rs
```

The `grep -q "review_file.py"` matches regardless of additional flags.

**Verification:**

Manually verify by testing the grep pattern:
```bash
echo 'timeout 180 uv run /tmp/scripts/review_file.py foo.rs --category test-suggestions --language rust --test-context test_foo.rs' | grep -q "review_file.py" && echo "MATCH" || echo "NO MATCH"
```
Expected: `MATCH`

**Commit:** No commit needed (verification confirms existing hook is sufficient).

<!-- END_TASK_2 -->
