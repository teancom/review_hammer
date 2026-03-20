---
name: review-hammer
description: High-precision code review using specialized LLM agents. Use when user wants to review code for bugs across a file, directory, or repo. Dispatches category-specialized reviewers and presents a deduplicated, severity-ranked report.
user-invocable: true
argument-hint: <file-or-directory-path>
---

# Review Hammer Orchestrator Skill

This skill orchestrates a high-precision code review pipeline. When invoked, it enumerates source files, detects languages, dispatches specialized Haiku `file-reviewer` agents in parallel, collects findings, performs an Opus judge pass for deduplication and verification, and presents a final severity-ranked report.

## Phase 1: Input Mode Detection

When this skill is invoked with `$ARGUMENTS`:

1. **Classify the input mode:**

   Examine `$ARGUMENTS` and classify into one of five modes:

   | Pattern | Mode | DIFF_BASE | File List Source |
   |---------|------|-----------|------------------|
   | Contains "commit" (e.g., "this commit", "last commit") | commit | Resolved via git | `git diff --name-only` |
   | Contains "branch" (e.g., "this branch") | branch | Resolved via git merge-base | `git diff --name-only` |
   | Is a file path AND file has uncommitted changes | file-diff | HEAD | Single file |
   | Is a file path AND file is clean (no uncommitted changes) | file-full | (none) | Single file |
   | Is a directory path | directory | Per-file (see Phase 2) | Directory enumeration |
   | No arguments provided | (prompt) | — | Ask user |

   If no arguments provided, ask the user: "Which file or directory would you like me to review? You can also say 'this commit' or 'this branch'."

2. **For commit mode:**
   - Run via Bash: `git rev-parse --verify HEAD 2>/dev/null`
   - If fails: report "Error: Not a git repository or no commits yet." and stop
   - Set `DIFF_BASE` to `HEAD~1`
   - For merge commits (detected via `git rev-list --parents -n 1 HEAD` having 3+ fields): `DIFF_BASE` is `HEAD~1` (reviews the merge diff, AC1.5)
   - Get changed files: `git diff HEAD~1..HEAD --name-only --diff-filter=ACMR`
   - Filter to supported extensions only (same extensions as Phase 2 Glob patterns)
   - If no supported files changed: report "No supported language files changed in this commit." and stop

3. **For branch mode:**
   - Run via Bash: `git rev-parse --verify HEAD 2>/dev/null`
   - If fails: report "Error: Not a git repository or no commits yet." and stop
   - Detect main branch: try `git rev-parse --verify origin/main` then `origin/master`
   - Find divergence point: `git merge-base HEAD origin/main` (or origin/master)
   - Set `DIFF_BASE` to the merge-base commit hash
   - Get changed files: `git diff {DIFF_BASE}..HEAD --name-only --diff-filter=ACMR`
   - Filter to supported extensions only
   - If no supported files changed: report "No supported language files changed on this branch." and stop

4. **For file path (single file):**
   - Use Glob tool to confirm the file exists
   - If not found: report "Error: Path does not exist: {path}" and stop
   - Check dirty status via Bash: `git status --porcelain -- {path} 2>/dev/null`
   - If output is non-empty (file has uncommitted changes): mode = file-diff, `DIFF_BASE` = `HEAD`
   - If output is empty (file is clean): mode = file-full, `DIFF_BASE` = none
   - If `git status` fails (not a git repo): mode = file-full, `DIFF_BASE` = none (AC2.3 fallback)

5. **For directory path:**
   - Use Glob tool to confirm the directory exists
   - If not found: report "Error: Path does not exist: {path}" and stop
   - Proceed to Phase 2 (file enumeration) — per-file dirty/clean classification happens there

6. **Store results for subsequent phases:**
   - `input_mode`: one of "commit", "branch", "file-diff", "file-full", "directory"
   - `diff_base`: the resolved git ref (or none for file-full mode)
   - `file_list`: list of files to review (for commit/branch modes, already resolved; for file modes, single file; for directory, resolved in Phase 2)

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
   - This filtering is done in-context on the Glob results — do NOT shell out to grep or any Bash command

3. **Per-file dirty/clean classification (directory mode only):**
   - Run via Bash: `git status --porcelain -- {directory_path} 2>/dev/null`
   - Parse output to identify dirty files (lines starting with ` M`, `M `, `MM`, `A `, `??`, etc.)
   - For each enumerated file:
     - If file appears in git status output → mark as dirty, assign `DIFF_BASE` = `HEAD`
     - If file does NOT appear → mark as clean, assign `DIFF_BASE` = none
     - If git status failed (not a git repo) → all files are clean (full-file mode)
   - Store per-file `diff_base` values for Phase 4 dispatch

4. **Handle empty results:**
   - If no supported files are found, report: "No supported language files found in {path}. Nothing to review." (AC1.4)
   - Stop execution

5. **Confirm large repos (AC6.3):**
   - If more than 100 files are found, present a confirmation flow to the user:
     - Calculate estimated API calls: `(file_count × 6) + production_file_count` (6 categories per file for file-reviewer agents, plus 1 test-suggester per production file), or simplify to `file_count × 7` as upper bound
     - Format message:
       ```
       This target contains {file_count} reviewable files, which will require approximately {api_calls} API calls.

       Options:
       - Proceed with all {file_count} files
       - Review only files changed in git (git diff)
       - Narrow scope - specify a subdirectory or file pattern
       - Cancel
       ```
     - Use the AskUserQuestion tool to get the user's decision
   - **If "Proceed with all":** Continue to Phase 3 with the full file list
   - **If "Review only files changed in git":**
     - Run `git diff --name-only` to get changed files
     - Filter to supported extensions only
     - Re-enumerate the file list with these changes
     - Proceed to Phase 3 with the filtered list
   - **If "Narrow scope":**
     - Ask the user: "Enter a subdirectory path or file pattern to review:"
     - Re-enumerate files matching the user's scope
     - If no files found, report and stop
     - Proceed to Phase 3 with the narrowed file list
   - **If "Cancel":** Stop execution and do not proceed
   - If 100 or fewer files are found initially, skip this confirmation and proceed directly to Phase 3

## Phase 3: Language Detection

For each enumerated file:

1. **Map extension to language:**
   - Use this mapping from `review_file.py`:
     - `.py` → `python`
     - `.c`, `.h` → `c`
     - `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx` → `cpp`
     - `.java` → `java`
     - `.cs` → `csharp`
     - `.js`, `.mjs`, `.cjs`, `.jsx` → `javascript`
     - `.ts`, `.tsx`, `.mts`, `.cts` → `typescript`
     - `.kt`, `.kts` → `kotlin`
     - `.rs` → `rust`
     - `.go` → `go`
     - `.swift` → `swift`

2. **Fallback:**
   - If a file extension is not recognized, default to `generic`

3. **Store the mapping:**
   - Create a list of tuples: `(absolute_path, detected_language, filename)`

## Phase 3.5: Test File Discovery

For each production file discovered in Phase 3, discover companion test files using convention-based pairing:

1. **Test file discovery rules by language:**

   | Language | Production File | Test File Pattern(s) |
   |----------|----------------|---------------------|
   | Rust | `src/foo.rs` | `tests/foo.rs`, `src/foo_test.rs` |
   | Python | `foo.py` | `test_foo.py`, `tests/test_foo.py`, `foo_test.py` |
   | Go | `foo.go` | `foo_test.go` (same directory) |
   | TypeScript/JS | `foo.ts` | `foo.test.ts`, `foo.spec.ts`, `__tests__/foo.test.ts` |
   | Java/Kotlin | `Foo.java` | `FooTest.java`, `FooSpec.java` (in test source tree) |
   | Others | `foo.ext` | `test_foo.ext`, `foo_test.ext`, `foo.test.ext` |

2. **For each production file, use the Glob tool (not Bash) to search for test files:**
   - Extract the base filename without extension
   - Search the repository root and common test directories
   - Collect all matching test file paths
   - Store the result as `(absolute_path, detected_language, filename, test_files_csv_or_none)`
   - For production files with no companion test files, set `test_files_csv_or_none` to `None`
   - For production files with companion test files, set to a comma-separated list of absolute paths

3. **Exclude test files from the file-reviewer queue:**
   - Separate files into two categories:
     - **Production files:** Files that are not test files (proceed to Phase 4 for agent dispatch)
     - **Test files:** Files discovered as companions to production files (these are analyzed only by test-suggester agents, not file-reviewer agents)
   - Note: Any test files that exist in the initial enumeration but are NOT companions of a production file (orphan test files) may be reviewed by file-reviewer agents

## Phase 4: Agent Dispatch

Dispatch specialized reviewer agents with concurrency control:

1. **Read concurrency limit:**
   - Run via Bash: `printenv REVIEWERS_MAX_CONCURRENT`
   - If set, use that value as the batch size (must be 1-10; ignore invalid values)
   - If not set or empty, default to **2**

2. **Prevent system sleep (macOS):**
   - Run via Bash: `caffeinate -i -w $$ &`
   - This prevents idle sleep for the duration of the current process
   - Without this, macOS will suspend processes when the display sleeps, causing reviews to stall for hours

3. **Resolve the plugin root path:**
   - Use the Bash tool to run: `ls -d ~/.claude/plugins/cache/review-hammer-marketplace/review-hammer/*/ 2>/dev/null | sort -V | tail -1`
   - This finds the highest-versioned installed plugin directory
   - Strip any trailing slash/newline and store as `plugin_root`
   - If no result, report error: "Review Hammer plugin not installed. Run: /plugin install review-hammer@review-hammer-marketplace"

4. **Build combined work queue:**
   - Create a queue of agent tasks from Phase 3.5 results
   - For each **production file** from Phase 3.5:
     - Add a file-reviewer agent task to the queue
     - Also add a test-suggester agent task to the queue
   - For each **test file** (orphan test files not paired to a production file):
     - Add a file-reviewer agent task to the queue
   - Queue should interleave agent types to maximize concurrency. Example with 2 production files and batch size 2:
     ```
     Batch 1: [file-reviewer(prod1), test-suggester(prod1)]
     Batch 2: [file-reviewer(prod2), test-suggester(prod2)]
     ```

5. **Invoke agents from combined queue:**

   **For file-reviewer agents:**

   When in diff mode (commit, branch, or file-diff), include `DIFF_BASE`:
   ```
   subagent_type: "review-hammer:file-reviewer"
   description: "Review {filename}"
   prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}\nDIFF_BASE: {diff_base}"
   ```

   When in full-file mode (file-full or clean files in directory), omit `DIFF_BASE`:
   ```
   subagent_type: "review-hammer:file-reviewer"
   description: "Review {filename}"
   prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}"
   ```

   **For test-suggester agents (production files only):**

   When in diff mode, include `DIFF_BASE`:
   ```
   subagent_type: "review-hammer:test-suggester"
   description: "Test suggestions for {filename}"
   prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}\nTEST_FILES: {test_files_csv_or_none}\nDIFF_BASE: {diff_base}"
   ```

   When in full-file mode, omit `DIFF_BASE`:
   ```
   subagent_type: "review-hammer:test-suggester"
   description: "Test suggestions for {filename}"
   prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}\nTEST_FILES: {test_files_csv_or_none}"
   ```

   - Always pass `PLUGIN_ROOT` with the concrete absolute path (never a shell variable)
   - For test-suggester, pass `TEST_FILES` as a comma-separated list of absolute paths, or empty/None if no test files found

   **DIFF_BASE handling by input mode:**
   - **commit mode:** all files get `DIFF_BASE: HEAD~1`
   - **branch mode:** all files get `DIFF_BASE: {merge_base_hash}`
   - **file-diff mode:** file gets `DIFF_BASE: HEAD`
   - **file-full mode:** no DIFF_BASE (omit from prompt)
   - **directory mode:** per-file — dirty files get `DIFF_BASE: HEAD`, clean files omit DIFF_BASE

6. **Batch dispatch with concurrency control:**
   - Dispatch agents from the combined queue in batches using the concurrency limit from step 1
   - Each batch contains the next N agents from the queue (where N is the concurrency limit)
   - Wait for all agents in a batch to complete before dispatching the next batch
   - Collect the JSON output from each agent as it completes

7. **Expected output from each agent:**
   - **file-reviewer output:** JSON structure with fields like `findings`, `file`, `language`, `is_test`, `categories_run`, `categories_with_findings`
   - **test-suggester output:** JSON structure with findings where `category: "test-suggestions"` (same schema as file-reviewer)
   - Each finding includes: `lines` (array of [start_line, end_line]), `severity`, `category`, `description`, `impact`, `confidence`
   - Per-specialist error handling: If a specialist times out or fails for a file, that file's review is noted as incomplete but other files continue processing

## Phase 5: Opus Judge Pass

After all agents complete, perform these steps as Opus to synthesize findings:

### 5a. Deduplication (AC5.1)

- Compare findings across all agents and files
- If two or more findings reference the same line range in the same file with similar descriptions, merge them
- **Important:** Test suggestions have `category: "test-suggestions"` and should not be deduplicated against bug findings from other categories. Only deduplicate test suggestions against each other (same file, similar description).
- For merged findings, create a `flagged_by` array listing which categories detected it:
  ```
  "flagged_by": ["logic-errors", "error-handling"]
  ```
- Keep only one instance of the merged finding

### 5b. Line Number Verification (AC5.2)

- For every finding with severity "critical" or "high":
  - Use the Read tool to open the actual file at the cited line range
  - Verify that the line numbers and code snippet match the finding description
  - If line numbers are incorrect or the described code is not present:
    - Attempt to locate the correct line numbers
    - If correction is possible, update the finding
    - If correction is impossible, discard the finding
- For test suggestions: Verify test suggestion line references the same way as bug findings.

### 5c. False Positive Filtering (AC5.3 partial)

- Review each remaining finding with expert judgment
- Consider:
  - Is this truly a bug, or could the code be correct in its context?
  - Are there framework/library patterns that make this code safe?
  - Is the issue only theoretical or does it have real impact?
- Remove findings that are clearly false positives
- For test suggestions: Apply the DO NOT SUGGEST criteria from the prompt template. Remove suggestions for language-level trivia.

### 5d. Cross-File Pattern Detection (AC5.3)

- Analyze findings across all files to identify systemic patterns
- Look for: the same type of issue appearing in multiple files (e.g., missing error checks in 15 files)
- **Systemic patterns:** Report once with an affected file list instead of individually
  - Example: "Missing null checks in list iteration" → affected files: `service1.py`, `service2.py`, `handler.py`, ...
- **Unique per-file findings:** Keep separate and report individually
- **Test suggestions:** Treat separately from bug findings (do not group with systemic patterns from bug categories)

### 5e. Severity Ranking (AC5.4)

- Sort all findings by severity:
  - **Critical** (highest priority)
  - **High**
  - **Medium**
- Within the same severity level, sort by confidence (highest first)
- Include test suggestions in the overall ranking, but present them in a separate report section (see Phase 6, Change 2)

## Phase 6: Report Formatting

Present the final report using this markdown template:

```markdown
# Code Review Report

**Target:** {target_path}
**Files reviewed:** {total_file_count}
**Findings:** {total_finding_count} ({critical_count} critical, {high_count} high, {medium_count} medium) + {suggestion_count} test suggestions

## Critical

### [Finding Title]
**File:** `path/to/file.py:123-125`
**Category:** logic-error (also flagged by: error-handling)
**Confidence:** 0.95

[Description of the bug]

**Impact:** [What goes wrong if this bug is present]

**Code:**
```{language}
[actual code at those lines from the file]
```

---

### [Next Critical Finding]
...

## High

### [Finding Title]
**File:** `path/to/file.py:456-460`
**Category:** performance-issue
**Confidence:** 0.88

[Description]

**Impact:** [Impact]

**Code:**
```{language}
[code]
```

---

## Medium

### [Finding Title]
...

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

## Systemic Patterns

### [Pattern Name]
**Affected files:** `file1.py`, `file2.py`, `file3.py` (and {N} more)
**Category:** error-handling

[Description of the pattern and its occurrences across files]

---

*Reviewed by {agent_count} specialists across {file_count} files. {false_positive_count} false positives removed. {suggestion_count} test suggestions generated.*
```

## Acceptance Criteria Coverage

- **AC1.1:** Single file paths accepted → handled in Phase 1
- **AC1.2:** Directory enumeration → Phase 2
- **AC1.3:** Non-existent paths → Phase 1 validation
- **AC1.4:** Empty directory handling → Phase 2
- **AC5.1:** Deduplication → Phase 5a
- **AC5.2:** Line verification → Phase 5b
- **AC5.3:** False positive filtering and pattern detection → Phase 5c & 5d
- **AC5.4:** Severity ranking → Phase 5e
