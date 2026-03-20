# Smart Input Implementation Plan — Phase 4

**Goal:** `file-reviewer.md` and `test-suggester.md` accept and pass through `DIFF_BASE`.

**Architecture:** Add an optional `DIFF_BASE` input field to both agent definitions. When provided, the command templates include `--diff-base DIFF_BASE`. When not provided, commands are unchanged (backward compatible).

**Tech Stack:** Markdown agent definitions (Claude Code plugin system)

**Scope:** 7 phases from original design (phase 4 of 7)

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase is an **infrastructure phase** — agent definitions are markdown templates verified operationally.

**Verifies: None** — operational verification only. Agent passthrough is exercised in Phase 6 integration testing.

---

<!-- START_TASK_1 -->
### Task 1: Add DIFF_BASE input to file-reviewer agent

**Files:**
- Modify: `agents/file-reviewer.md:19-26` (Inputs section)
- Modify: `agents/file-reviewer.md:67-78` (command template and example)

**Implementation:**

**Update the Inputs section** (after line 24, add DIFF_BASE):

In the `## Inputs` section, add a new bullet after `PLUGIN_ROOT`:
```
- `DIFF_BASE:` — (optional) git ref to diff against. When provided, review_file.py reviews only changed hunks. When "none" or absent, full file is reviewed.
```

Update the "Parse these" instruction to include the new field:
```
Parse these values from the prompt text. DIFF_BASE may be absent — treat it as "none" if not found.
```

**Update the command template** in section `### 3. Run Each Category` (line 70):

Replace the single command template with a conditional:

```
For each category, run this exact command pattern via Bash:

**If DIFF_BASE is "none" or was not provided:**
```
timeout 300 uv run PLUGIN_ROOT/scripts/review_file.py FILE_PATH --category CATEGORY --language LANGUAGE --timeout 45
```

**If DIFF_BASE is provided (not "none"):**
```
timeout 300 uv run PLUGIN_ROOT/scripts/review_file.py FILE_PATH --category CATEGORY --language LANGUAGE --timeout 45 --diff-base DIFF_BASE
```
```

**Update the example** (around line 75) to show both variants.

**Verification:**
Read the modified file and confirm:
- DIFF_BASE is listed in Inputs
- Command template has conditional --diff-base
- Existing command format is preserved when DIFF_BASE is absent

**Commit:** `feat: add DIFF_BASE passthrough to file-reviewer agent`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add DIFF_BASE input to test-suggester agent

**Files:**
- Modify: `agents/test-suggester.md:19-25` (Inputs section)
- Modify: `agents/test-suggester.md:32-44` (command template)

**Implementation:**

**Update the Inputs section** (after line 24, add DIFF_BASE):

In the `## Inputs` section, add a new bullet after `TEST_FILES`:
```
- `DIFF_BASE:` — (optional) git ref to diff against. When provided, review_file.py reviews only changed hunks. When "none" or absent, full file is reviewed. Note: test-hammer currently always omits this, but the plumbing exists for future use.
```

Update the "Parse these" instruction:
```
Parse these five values from the prompt text. DIFF_BASE may be absent — treat it as "none" if not found.
```

**Update the command templates** in section `### 1. Build Command` (lines 32-44):

Add the conditional `--diff-base` to both command variants (with and without test files):

```
**If DIFF_BASE is "none" or was not provided:**

```
timeout 300 uv run PLUGIN_ROOT/scripts/review_file.py FILE_PATH --category test-suggestions --language LANGUAGE --timeout 45
```

**If DIFF_BASE is provided (not "none"):**

```
timeout 300 uv run PLUGIN_ROOT/scripts/review_file.py FILE_PATH --category test-suggestions --language LANGUAGE --timeout 45 --diff-base DIFF_BASE
```

If `TEST_FILES` is NOT "none", append `--test-context` for each test file path to whichever command variant above applies.
```

**Verification:**
Read the modified file and confirm:
- DIFF_BASE is listed in Inputs
- Command template has conditional --diff-base
- --test-context appending still works
- Existing behavior preserved when DIFF_BASE absent

**Commit:** `feat: add DIFF_BASE passthrough to test-suggester agent`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify backward compatibility

**Files:**
- No new files — verification only

**Verification:**

Visually inspect both agent files to confirm:
1. When DIFF_BASE is not in the prompt, agents produce the exact same commands as before
2. Input parsing handles missing DIFF_BASE gracefully (treats as "none")
3. No other sections of the agent definitions were inadvertently changed

Run: `ruff check agents/` — N/A (markdown files, not Python)

**Commit:** No commit — verification only.
<!-- END_TASK_3 -->
