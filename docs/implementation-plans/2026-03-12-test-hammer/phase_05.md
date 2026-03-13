# Test Hammer Implementation Plan — Phase 5: Review-Hammer Integration

**Goal:** Integrate test-hammer into the review-hammer pipeline so that `/review-hammer` dispatches both file-reviewer and test-suggester agents from the same batch queue, with test suggestions appearing in the final report. Retire the `missing-edge-cases` category.

**Architecture:** Modifies the review-hammer orchestrator (`skills/review-hammer/SKILL.md`) to: (1) discover and pair test files with production files (same logic as test-hammer standalone), (2) dispatch test-suggester agents alongside file-reviewer agents in a single interleaved batch queue sharing the `REVIEWERS_MAX_CONCURRENT` limit, (3) include test suggestions in the Opus judge pass and final report. The `missing-edge-cases` category is removed from `agents/file-reviewer.md` and all prompt templates.

**Tech Stack:** Claude Code plugin system (skills, agents, prompts)

**Scope:** 6 phases from original design (this is phase 5 of 6)

**Codebase verified:** 2026-03-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### test-hammer.AC2: Review-hammer integration
- **test-hammer.AC2.1 Success:** `/review-hammer <path>` dispatches both file-reviewer and test-suggester agents from the same batch queue
- **test-hammer.AC2.2 Success:** Test suggestions appear in the final review-hammer report alongside other findings
- **test-hammer.AC2.3 Success:** `missing-edge-cases` category no longer runs for production files
- **test-hammer.AC2.4 Success:** Global `REVIEWERS_MAX_CONCURRENT` limit is respected across both agent types (2 means 2 total, not 2 per type)

### test-hammer.AC5: Cross-cutting behaviors
- **test-hammer.AC5.3 Edge:** Large test files exceeding 500 lines are truncated with a warning before being passed to the LLM

---

<!-- START_TASK_1 -->
### Task 1: Remove `missing-edge-cases` from `agents/file-reviewer.md`

**Verifies:** test-hammer.AC2.3

**Files:**
- Modify: `agents/file-reviewer.md` line 53

**Implementation:**

In `agents/file-reviewer.md`, the test file categories list (lines 49-53) currently reads:

```markdown
**Test files (5 categories):**
1. `testing-nothing`
2. `missing-assertions`
3. `over-mocking`
4. `brittle-tests`
5. `missing-edge-cases`
```

Remove line 53 (`5. \`missing-edge-cases\``) and update the count to "4 categories":

```markdown
**Test files (4 categories):**
1. `testing-nothing`
2. `missing-assertions`
3. `over-mocking`
4. `brittle-tests`
```

**Verification:**

Read the modified file and confirm `missing-edge-cases` no longer appears:
```bash
grep -c 'missing-edge-cases' agents/file-reviewer.md
```
Expected: `0`

**Commit:** `refactor: remove missing-edge-cases from file-reviewer agent`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Remove `## missing-edge-cases` sections from all 12 prompt files

**Verifies:** test-hammer.AC2.3

**Files:**
- Modify: `prompts/rust.md` (remove lines 250-269, the `## missing-edge-cases` section)
- Modify: `prompts/generic.md` (remove the `## missing-edge-cases` section starting at line 207)
- Modify: `prompts/python.md` (line 219), `prompts/go.md` (line 237), `prompts/typescript.md` (line 229), `prompts/javascript.md` (line 227), `prompts/java.md` (line 244), `prompts/kotlin.md` (line 232), `prompts/swift.md` (line 240), `prompts/cpp.md` (line 220), `prompts/c.md` (line 222), `prompts/csharp.md` (line 260)

**Implementation:**

For each of the 12 prompt files, remove the entire `## missing-edge-cases` section. Each section starts with `## missing-edge-cases` and extends to the next `## ` heading or end of file.

Since `## missing-edge-cases` is the last test category in each file (but `## test-suggestions` was added after it in Phase 1 for rust.md and generic.md), be careful to only remove the `## missing-edge-cases` section, not the `## test-suggestions` section that follows it in rust.md and generic.md.

Also update `prompts/CLAUDE.md` line 15 to remove `missing-edge-cases` from the test categories list:
```
  - Test categories: testing-nothing, missing-assertions, over-mocking, brittle-tests
```

**Verification:**

Confirm no prompt files still contain `missing-edge-cases`:
```bash
grep -rl 'missing-edge-cases' prompts/
```
Expected: No output (no files match).

Confirm `## test-suggestions` still exists in rust.md and generic.md (the `## missing-edge-cases` section was between `## brittle-tests` and `## test-suggestions` — removing it must not affect the `## test-suggestions` section):
```bash
grep -c '## test-suggestions' prompts/rust.md prompts/generic.md
```
Expected: Both show `1`.

**Required test update:** `tests/test_review_file.py` line 212 lists `"missing-edge-cases"` in the `test_extract_each_category` test's category list. Remove this entry from the list (lines 201-213 of the test file). The updated list should be:

```python
categories = [
    "race-conditions",
    "null-safety",
    "resource-leaks",
    "logic-errors",
    "error-handling",
    "state-management",
    "testing-nothing",
    "missing-assertions",
    "over-mocking",
    "brittle-tests"
]
```

Run existing tests to confirm nothing breaks:
```bash
.venv/bin/pytest tests/test_review_file.py -v
```
Expected: All tests pass.

**Commit:** `refactor: remove missing-edge-cases sections from all prompt templates`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add test file discovery and test-suggester dispatch to review-hammer SKILL.md

**Verifies:** test-hammer.AC2.1, test-hammer.AC2.4

**Files:**
- Modify: `skills/review-hammer/SKILL.md`
  - Phase 3 (Language Detection): Add note about test file pairing
  - Between Phase 3 and Phase 4: Insert new "Phase 3.5: Test File Discovery" section
  - Phase 4 (Agent Dispatch): Modify to interleave test-suggester agents in the same batch queue

**Implementation:**

**Change 1: Add test file discovery phase after Phase 3 (Language Detection)**

Insert a new section between the existing Phase 3 and Phase 4. This uses the same convention-based pairing logic as the standalone test-hammer skill (Phase 4 of this implementation plan, Task 1). The key addition:

For each **production file** (not test files), discover companion test files using the convention table from the test-hammer design:

| Language | Production File | Test File Pattern(s) |
|----------|----------------|---------------------|
| Rust | `src/foo.rs` | `tests/foo.rs`, `src/foo_test.rs` |
| Python | `foo.py` | `test_foo.py`, `tests/test_foo.py`, `foo_test.py` |
| Go | `foo.go` | `foo_test.go` (same directory) |
| TypeScript/JS | `foo.ts` | `foo.test.ts`, `foo.spec.ts`, `__tests__/foo.test.ts` |
| Java/Kotlin | `Foo.java` | `FooTest.java`, `FooSpec.java` (in test source tree) |
| Others | `foo.ext` | `test_foo.ext`, `foo_test.ext`, `foo.test.ext` |

Use Glob tool for discovery (not Bash). Store results as `(absolute_path, language, filename, test_files_csv_or_none)`.

**Change 2: Modify Phase 4 (Agent Dispatch) for interleaved batch queue**

The current Phase 4 dispatches only file-reviewer agents. Modify it to build a combined work queue:

1. For each file (production or test), add a file-reviewer agent to the queue
2. For each **production** file, also add a test-suggester agent to the queue
3. Dispatch from the combined queue in batches of `REVIEWERS_MAX_CONCURRENT`

The queue should interleave agent types. Example with 2 production files and batch size 2:
```
Batch 1: [file-reviewer(prod1), test-suggester(prod1)]
Batch 2: [file-reviewer(prod2), test-suggester(prod2)]
```

This ensures `REVIEWERS_MAX_CONCURRENT=2` means 2 total agents hitting the API, not 2 per type.

The test-suggester agent invocation:
```
subagent_type: "review-hammer:test-suggester"
description: "Test suggestions for {filename}"
prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}\nTEST_FILES: {test_files_csv_or_none}"
```

**Change 3: Update estimated API calls for large repo confirmation**

In the existing Phase 2 large repo confirmation, update the estimate. Previously: `file_count × 6`. Now: `(file_count × 6) + production_file_count` (add 1 per production file for test-suggestions). Or simplify to `file_count × 7` as an upper bound estimate.

**Verification:**

Read the modified SKILL.md and verify:
1. Test file discovery section exists between Phase 3 and Phase 4
2. Phase 4 builds a combined queue with both agent types
3. Batch dispatch uses a single queue (not separate queues per agent type)

**Commit:** `feat: integrate test-suggester dispatch into review-hammer skill`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Include test suggestions in Opus judge pass and report

**Verifies:** test-hammer.AC2.2

**Files:**
- Modify: `skills/review-hammer/SKILL.md`
  - Phase 5 (Opus Judge Pass): Add handling for test-suggestion findings
  - Phase 6 (Report Formatting): Add "Test Suggestions" section to report template

**Implementation:**

**Change 1: Update Phase 5 (Opus Judge Pass)**

The judge pass currently processes findings from file-reviewer agents. Extend it to also process findings from test-suggester agents:

- In step 5a (Deduplication): Test suggestions have `category: "test-suggestions"` and should not be deduplicated against bug findings from other categories. Only deduplicate test suggestions against each other (same file, similar description).
- In step 5b (Line Number Verification): Verify test suggestion line references the same way as bug findings.
- In step 5c (False Positive Filtering): Apply the DO NOT SUGGEST criteria from the prompt template. Remove suggestions for language-level trivia.
- In step 5e (Severity Ranking): Include test suggestions in the overall ranking, but present them in a separate report section (see Change 2).

**Change 2: Update Phase 6 (Report Formatting)**

Add a "Test Suggestions" section after the main findings sections (Critical/High/Medium) and before "Systemic Patterns":

```markdown
## Test Suggestions

### [Suggestion Title]
**File:** `path/to/file.py:123-125`
**Severity:** high
**Confidence:** 0.85

[Description of what to test and why it matters]

**Impact:** [What risk exists without this test]

**Code context:**
```{language}
[actual code at those lines]
```

---
```

Update the summary header to include suggestion count:
```
**Findings:** {finding_count} ({critical} critical, {high} high, {medium} medium) + {suggestion_count} test suggestions
```

Update the footer:
```
*Reviewed by {agent_count} specialists across {file_count} files. {false_positive_count} false positives removed. {suggestion_count} test suggestions generated.*
```

**Verification:**

Read the modified SKILL.md and verify:
1. Phase 5 handles test-suggestion findings separately from bug findings
2. Phase 6 report template includes a "Test Suggestions" section
3. Summary counts include test suggestions

**Commit:** `feat: include test suggestions in review-hammer report`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update `prompts/CLAUDE.md` invariant and version bump

**Verifies:** None (infrastructure)

**Files:**
- Modify: `prompts/CLAUDE.md` line 20: Update the invariant about category count
- Modify: `.claude-plugin/plugin.json` — bump version
- Modify: `.claude-plugin/marketplace.json` — bump version (must match plugin.json)

**Implementation:**

**Change 1:** Update `prompts/CLAUDE.md` line 20 from:
```
- Every language template must have all 11 category headings (6 production + 5 test)
```
to:
```
- Every language template must have all 11 category headings (6 production + 4 test + 1 test-suggestions)
```

**Note:** At this point, only `rust.md` and `generic.md` have `## test-suggestions` (added in Phase 1). The remaining 10 languages get it in Phase 6. This invariant will be temporarily violated for those 10 files between Phase 5 and Phase 6 completion. This is acceptable since both phases are part of the same implementation plan and Phase 6 is the next phase.

**Change 2:** Bump the version in both `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`. The current version is `0.15.0`. Bump to `0.16.0` (minor version bump for new feature). Both files must have the same version.

**Verification:**

```bash
grep '"version"' .claude-plugin/plugin.json .claude-plugin/marketplace.json
```
Expected: Both show `"0.16.0"`.

**Commit:** `chore: bump version to 0.16.0 for test-hammer integration`

<!-- END_TASK_5 -->
