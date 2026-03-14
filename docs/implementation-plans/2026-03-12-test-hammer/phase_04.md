# Test Hammer Implementation Plan — Phase 4: Standalone Skill

**Goal:** Create the `/test-hammer <path>` orchestrator skill that enumerates production files, pairs each with test files, dispatches test-suggester agents in batches, runs an Opus judge pass, and presents a severity-ranked report.

**Architecture:** Mirrors the `skills/review-hammer/SKILL.md` orchestrator pattern — same phases (input validation, file enumeration, language detection, agent dispatch, judge pass, report) — but runs a single category (`test-suggestions`) instead of 5-6 categories, and adds a test file discovery/pairing step. Uses the same `REVIEWERS_MAX_CONCURRENT` env var for batch size.

**Tech Stack:** Claude Code plugin system (skills, agents)

**Scope:** 6 phases from original design (this is phase 4 of 6)

**Codebase verified:** 2026-03-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### test-hammer.AC1: Standalone `/test-hammer <path>` skill
- **test-hammer.AC1.1 Success:** `/test-hammer <file>` analyzes a single production file and returns up to 3 test suggestions in severity-ranked markdown report
- **test-hammer.AC1.2 Success:** `/test-hammer <directory>` enumerates all production files, pairs each with test files, and produces a combined report
- **test-hammer.AC1.4 Success:** Opus judge pass deduplicates, verifies, and ranks suggestions before final report
- **test-hammer.AC1.5 Edge:** When no test file exists for a production file, agent is informed "no existing tests found" and suggestions focus on highest-value tests

### test-hammer.AC5: Cross-cutting behaviors
- **test-hammer.AC5.2 Success:** Hard cap of 3 suggestions per file is enforced in the prompt template

---

<!-- START_TASK_1 -->
### Task 1: Create `skills/test-hammer/SKILL.md`

**Verifies:** test-hammer.AC1.1, test-hammer.AC1.2, test-hammer.AC1.4, test-hammer.AC1.5, test-hammer.AC5.2

**Files:**
- Create: `skills/test-hammer/SKILL.md`

**Implementation:**

Create the skill file following the exact structure of `skills/review-hammer/SKILL.md`. The frontmatter and 6-phase orchestration pattern should mirror review-hammer, with these key differences:

1. **Test file discovery phase** (new — between language detection and agent dispatch)
2. **Single agent type** — `test-suggester` instead of `file-reviewer`
3. **Test file pairing** — convention-based test file discovery passed to agents
4. **Simpler judge pass** — no cross-file pattern detection (test suggestions are per-file)
5. **Different report format** — test suggestions instead of bug findings

The full skill content:

```markdown
---
name: test-hammer
description: Suggests high-value tests for production code by pairing it with existing test files and analyzing gaps. Use when user wants test suggestions for a file, directory, or repo.
user-invocable: true
disable-model-invocation: true
argument-hint: <file-or-directory-path>
---

# Test Hammer Orchestrator Skill

This skill orchestrates a test suggestion pipeline. When invoked, it enumerates production source files, detects languages, discovers and pairs existing test files, dispatches specialized Haiku `test-suggester` agents in parallel, collects suggestions, performs an Opus judge pass for deduplication and verification, and presents a final severity-ranked report.

## Phase 1: Input Validation

When this skill is invoked with `$ARGUMENTS`:

1. **Parse the target path:**
   - Extract the file or directory path from `$ARGUMENTS`
   - If no arguments provided, ask the user: "Which file or directory would you like me to analyze for test suggestions?"

2. **Verify path existence:**
   - Use the Glob tool to confirm the path exists (do NOT use Bash)
   - If the path does not exist, report clearly: "Error: Path does not exist: {path}"
   - Stop execution

3. **Determine target type:**
   - If the path is a single file, proceed to Phase 3 with a single-file list
   - If the path is a directory, proceed to Phase 2

## Phase 2: File Enumeration (for directory targets)

When the target is a directory:

1. **Enumerate supported files using Glob (no Bash):**
   - Use the **Glob tool** (NOT Bash, NOT `git ls-files`, NOT `find`) to find files
   - Call Glob multiple times in parallel with these patterns, scoped to the target directory:
     - `**/*.py`
     - `**/*.{c,h}`
     - `**/*.{cpp,cc,cxx,hpp,hxx}`
     - `**/*.java`
     - `**/*.cs`
     - `**/*.{js,mjs,cjs,jsx}`
     - `**/*.{ts,tsx,mts,cts}`
     - `**/*.{kt,kts}`
     - `**/*.rs`
     - `**/*.go`
     - `**/*.swift`

2. **Apply exclusions (filter results, no Bash):**
   - From the Glob results, discard any path containing these directory segments:
     - `node_modules/`, `.git/`, `build/`, `dist/`, `target/`, `.gradle/`
     - `__pycache__/`, `.tox/`, `vendor/`, `.venv/`, `venv/`
   - This filtering is done in-context on the Glob results — do NOT shell out

3. **Filter to production files only:**
   - Discard test files from the list. A file is a test file if:
     - Filename ends with `Test.*`, `_test.*`, `Spec.*`, `Tests.*`, or starts with `test_`
     - Path contains `/test/`, `/tests/`, `/__tests__/`, `/spec/`
   - Keep only production files — test-hammer suggests tests FOR production code

4. **Handle empty results:**
   - If no production files are found, report: "No production files found in {path}. Nothing to analyze."
   - Stop execution

5. **Confirm large targets (>50 files):**
   - If more than 50 production files are found:
     - Format message: "This target contains {file_count} production files, which will require {file_count} API calls."
     - Use AskUserQuestion with options: Proceed all / git diff / narrow scope / cancel
   - If 50 or fewer files, proceed directly

## Phase 3: Language Detection

For each enumerated production file:

1. **Map extension to language** using the same mapping as review-hammer:
   - `.py` → `python`, `.c`/`.h` → `c`, `.cpp`/`.cc`/`.cxx`/`.hpp`/`.hxx` → `cpp`
   - `.java` → `java`, `.cs` → `csharp`, `.js`/`.mjs`/`.cjs`/`.jsx` → `javascript`
   - `.ts`/`.tsx`/`.mts`/`.cts` → `typescript`, `.kt`/`.kts` → `kotlin`
   - `.rs` → `rust`, `.go` → `go`, `.swift` → `swift`
   - Unknown → `generic`

2. **Store the mapping:**
   - Create a list of tuples: `(absolute_path, detected_language, filename)`

## Phase 4: Test File Discovery and Pairing

For each production file, discover existing test files by convention. Check these patterns **in order, first match wins**:

| Language | Production File | Test File Pattern(s) |
|----------|----------------|---------------------|
| Rust | `src/foo.rs` | `tests/foo.rs`, `src/foo_test.rs` |
| Python | `foo.py` | `test_foo.py`, `tests/test_foo.py`, `foo_test.py` |
| Go | `foo.go` | `foo_test.go` (same directory) |
| TypeScript/JS | `foo.ts` | `foo.test.ts`, `foo.spec.ts`, `__tests__/foo.test.ts` |
| Java/Kotlin | `Foo.java` | `FooTest.java`, `FooSpec.java` (in test source tree) |
| Others | `foo.ext` | `test_foo.ext`, `foo_test.ext`, `foo.test.ext` |

**Use Glob tool** to check for test file existence (NOT Bash). For each production file, check the patterns in order:
- If a match is found, store the test file path(s) alongside the production file
- If multiple test files match, collect all of them
- If no match is found, record "none" — the agent will be informed no tests exist

**Store the complete mapping:**
- `(absolute_path, detected_language, filename, test_files_csv_or_none)`

## Phase 5: Agent Dispatch

Dispatch test-suggester agents with concurrency control:

1. **Read concurrency limit:**
   - Run via Bash: `printenv REVIEWERS_MAX_CONCURRENT`
   - If set, use that value as batch size (must be 1-10; ignore invalid values)
   - If not set or empty, default to **2**

2. **Prevent system sleep (macOS):**
   - Run via Bash: `caffeinate -i -w $$ &`

3. **Resolve the plugin root path:**
   - Run via Bash: `ls -d ~/.claude/plugins/cache/review-hammer-marketplace/review-hammer/*/ 2>/dev/null | sort -V | tail -1`
   - Strip trailing slash/newline, store as `plugin_root`
   - If no result, report error: "Review Hammer plugin not installed."

4. **For each production file, invoke the Agent tool:**
   ```
   subagent_type: "review-hammer:test-suggester"
   description: "Test suggestions for {filename}"
   prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}\nTEST_FILES: {test_files_csv_or_none}"
   ```
   - Always pass `PLUGIN_ROOT` with concrete absolute path
   - `TEST_FILES` is comma-separated paths or "none"

5. **Batch dispatch:**
   - Dispatch agents in batches using concurrency limit
   - Wait for all agents in a batch to complete before dispatching next batch
   - Collect JSON output from each agent

## Phase 6: Opus Judge Pass

After all agents complete, perform these steps as Opus to synthesize suggestions:

### 6a. Deduplication

- Compare suggestions across all files
- If two suggestions describe the same type of test gap in different files, keep both (they are different suggestions for different files)
- If an agent returned duplicate suggestions for the same file, merge them

### 6b. Verification

- For every suggestion with severity "critical" or "high":
  - Use the Read tool to verify the production file at the cited line range
  - Verify the suggestion makes sense given the actual code
  - If lines are incorrect, attempt to locate correct lines or discard

### 6c. False Positive Filtering

- Review each suggestion against the test-suggestions prompt's DO NOT SUGGEST list:
  - Remove suggestions for language-level trivia (testing derived traits, language semantics)
  - Remove suggestions that duplicate what the type system enforces
  - Remove suggestions for tests already present in the provided test file context
- Enforce the hard cap of 3 suggestions per file. If an agent returned more (it shouldn't), keep only the top 3 by severity then confidence.

### 6d. Severity Ranking

- Sort all suggestions by severity: Critical → High → Medium
- Within same severity, sort by confidence (highest first)

## Phase 7: Report Formatting

Present the final report:

```markdown
# Test Suggestion Report

**Target:** {target_path}
**Files analyzed:** {total_file_count}
**Suggestions:** {total_suggestion_count} ({critical_count} critical, {high_count} high, {medium_count} medium)

## Critical

### [Suggestion Title]
**File:** `path/to/file.py:123-125`
**Confidence:** 0.95

[Description of what to test and why it matters]

**Impact:** [What risk exists without this test]

**Code context:**
```{language}
[actual code at those lines from the file]
```

---

## High

### [Suggestion Title]
...

## Medium

### [Suggestion Title]
...

---

*Analyzed {file_count} production files. {files_with_tests} had existing tests, {files_without_tests} had no tests.*
```

If no suggestions remain after the judge pass, report: "No test suggestions for {target_path}. The existing test coverage appears adequate."

## Acceptance Criteria Coverage

- **AC1.1:** Single file analysis → Phase 1 directs to single-file flow
- **AC1.2:** Directory enumeration → Phase 2 enumerates, Phase 4 pairs
- **AC1.4:** Opus judge pass → Phase 6
- **AC1.5:** No test file handling → Phase 4 records "none", agent informed
- **AC5.2:** Hard cap of 3 → enforced in prompt template + Phase 6c verification
```

**Verification:**

Verify the skill file has valid YAML frontmatter:
```bash
head -7 skills/test-hammer/SKILL.md
```
Expected: Valid `---` delimited YAML with `name`, `description`, `user-invocable`, `disable-model-invocation`, `argument-hint`.

Verify directory was created:
```bash
ls skills/test-hammer/
```
Expected: `SKILL.md`

**Commit:** `feat: add standalone test-hammer orchestrator skill`

<!-- END_TASK_1 -->
