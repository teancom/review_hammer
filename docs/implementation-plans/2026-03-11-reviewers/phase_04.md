# Review Hammer Implementation Plan — Phase 4: Collector Agent

**Goal:** Haiku agent that reviews a single file by dispatching all specialist categories via `review_file.py`

**Architecture:** A Claude Code agent definition in markdown with YAML frontmatter. The agent receives a file path, detects whether it's a test or production file, then calls `review_file.py` once per relevant specialist category (6 for production, 5 for tests). Uses Bash tool to invoke the Python script and collects results into a consolidated JSON structure.

**Tech Stack:** Claude Code agent markdown, Haiku model, Bash tool

**Scope:** 6 phases from original design (this is phase 4 of 6)

**Codebase verified:** 2026-03-11 — `agents/` directory has `.gitkeep` from Phase 1. Agent format verified: YAML frontmatter with `name`, `description`, `model`, `tools` fields, followed by markdown instructions. Agents at plugin level go in `agents/filename.md`.

---

## Acceptance Criteria Coverage

This phase implements:

### reviewers.AC4: Collector agent dispatches specialists correctly
- **reviewers.AC4.1 Success:** Agent detects production file and runs 6 production specialist categories
- **reviewers.AC4.2 Success:** Agent detects test file and runs 5 test specialist categories
- **reviewers.AC4.3 Edge:** Agent handles specialist returning "No findings" without error

**Verifies: None** — This is an agent definition (infrastructure). Verification is operational: the agent is dispatched by the orchestrator skill in Phase 5 and produces correct output.

---

<!-- START_TASK_1 -->
### Task 1: Create file-reviewer agent definition

**Files:**
- Create: `agents/file-reviewer.md` (replaces `agents/.gitkeep`)

**Step 1: Create the agent definition**

The agent definition has YAML frontmatter specifying it runs on Haiku with access to Bash, Read, and Glob tools. The markdown body contains the agent's instructions.

Key behaviors:
1. **Receive inputs:** The agent is dispatched with a prompt containing `FILE_PATH` and `LANGUAGE` (pre-detected by orchestrator)
2. **Detect test vs production:** Check the filename and directory path against test patterns
3. **Run specialists sequentially:** Call `review_file.py` once per category using the Bash tool
4. **Collect results:** Parse JSON output from each invocation, merge into a single findings array
5. **Handle empty results:** If a specialist returns `[]`, skip it — no error
6. **Return consolidated JSON:** All findings tagged by category and file

**Agent frontmatter:**
```yaml
---
name: file-reviewer
description: Reviews a single file by running specialist code review categories. Dispatched by the fleet-review skill — do not invoke directly.
model: haiku
tools: Bash, Read, Glob
---
```

**Agent instructions (markdown body):**

The instructions must tell the agent:

1. **Parse the dispatch prompt** — expect `FILE_PATH:` and `LANGUAGE:` in the prompt from the orchestrator
2. **Detect test file** — check if the file matches any test pattern:
   - Filename patterns: `*Test.*`, `*_test.*`, `test_*.*`, `*Spec.*`, `*Tests.*`
   - Directory patterns: file path contains `/test/`, `/tests/`, `/__tests__/`, `/spec/`
3. **Select categories based on file type:**
   - Production (6): `race-conditions`, `null-safety`, `resource-leaks`, `logic-errors`, `error-handling`, `state-management`
   - Test (5): `testing-nothing`, `missing-assertions`, `over-mocking`, `brittle-tests`, `missing-edge-cases`
   - Note: For C, C++, and Rust, use `memory-safety` instead of `null-safety`. For Go, use `nil-safety`. For JavaScript and TypeScript, use `type-safety`.
4. **Run each category** — for each category, run:
   ```bash
   ${CLAUDE_PLUGIN_ROOT}/.venv/bin/python3 ${CLAUDE_PLUGIN_ROOT}/scripts/review_file.py FILE_PATH --category CATEGORY --language LANGUAGE
   ```
   - Parse the stdout as JSON
   - If parse fails or returns empty array, continue to next category
   - Collect all findings
5. **Output consolidated results** — print a single JSON object:
   ```json
   {
     "file": "path/to/file.py",
     "language": "python",
     "is_test": false,
     "findings": [
       {"lines": [10, 12], "severity": "high", "category": "logic-errors", "description": "...", "impact": "...", "confidence": 0.9}
     ],
     "categories_run": ["race-conditions", "null-safety", "resource-leaks", "logic-errors", "error-handling", "state-management"],
     "categories_with_findings": ["logic-errors"]
   }
   ```

**Category name mapping by language:**

The agent must know which category name to use based on language:

| Language | Default "null-safety" name |
|----------|---------------------------|
| c, cpp | memory-safety |
| rust | memory-safety |
| go | nil-safety |
| javascript, typescript | type-safety |
| All others | null-safety |

The prompt template files use these language-specific H2 heading names, so the `--category` argument must match.

**Step 2: Remove the .gitkeep placeholder**

Run: `rm agents/.gitkeep`

**Step 3: Verify agent frontmatter is valid**

Run:
```bash
head -6 agents/file-reviewer.md
```
Expected: Shows YAML frontmatter with `name: file-reviewer`, `model: haiku`, `tools: Bash, Read, Glob`

**Commit:** `feat: add file-reviewer agent for specialist dispatch`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify agent definition end-to-end

**Step 1: Verify all required elements are present in the agent**

Run:
```bash
echo "=== Frontmatter fields ==="
grep -E '^(name|description|model|tools):' agents/file-reviewer.md

echo "=== Production categories referenced ==="
grep -c 'race-conditions' agents/file-reviewer.md
grep -c 'null-safety\|memory-safety\|nil-safety\|type-safety' agents/file-reviewer.md
grep -c 'resource-leaks' agents/file-reviewer.md
grep -c 'logic-errors' agents/file-reviewer.md
grep -c 'error-handling' agents/file-reviewer.md
grep -c 'state-management' agents/file-reviewer.md

echo "=== Test categories referenced ==="
grep -c 'testing-nothing' agents/file-reviewer.md
grep -c 'missing-assertions' agents/file-reviewer.md
grep -c 'over-mocking' agents/file-reviewer.md
grep -c 'brittle-tests' agents/file-reviewer.md
grep -c 'missing-edge-cases' agents/file-reviewer.md

echo "=== Test detection patterns ==="
grep -c 'test_\|Test\.\|Spec\.\|Tests\.\|__tests__' agents/file-reviewer.md
```
Expected: All grep counts ≥ 1

**Step 2: Verify the review_file.py invocation pattern is correct**

Run:
```bash
grep 'review_file.py' agents/file-reviewer.md
```
Expected: Shows the Bash command pattern with `${CLAUDE_PLUGIN_ROOT}` prefix

No commit for this task — it's a verification step only.
<!-- END_TASK_2 -->
