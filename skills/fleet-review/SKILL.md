---
name: fleet-review
description: High-precision code review using specialized LLM agents. Use when user wants to review code for bugs across a file, directory, or repo. Dispatches category-specialized reviewers and presents a deduplicated, severity-ranked report.
user-invocable: true
disable-model-invocation: true
argument-hint: <file-or-directory-path>
---

# Fleet Review Orchestrator Skill

This skill orchestrates a high-precision code review pipeline. When invoked, it enumerates source files, detects languages, dispatches specialized Haiku `file-reviewer` agents in parallel, collects findings, performs an Opus judge pass for deduplication and verification, and presents a final severity-ranked report.

## Phase 1: Input Validation

When this skill is invoked with `$ARGUMENTS`:

1. **Parse the target path:**
   - Extract the file or directory path from `$ARGUMENTS`
   - If no arguments provided, ask the user: "Which file or directory would you like me to review?"

2. **Verify path existence:**
   - Use the Glob or Bash tool to confirm the path exists
   - If the path does not exist, report clearly: "Error: Path does not exist: {path}" (AC1.3)
   - Stop execution

3. **Determine target type:**
   - If the path is a single file, proceed to Phase 3 with a single-file list
   - If the path is a directory, proceed to Phase 2

## Phase 2: File Enumeration (for directory targets)

When the target is a directory:

1. **Enumerate supported files:**
   - Use Glob to recursively find all files with these extensions:
     - **Python:** `.py`
     - **C:** `.c`, `.h`
     - **C++:** `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx`
     - **Java:** `.java`
     - **C#:** `.cs`
     - **JavaScript/JSX:** `.js`, `.mjs`, `.cjs`, `.jsx`
     - **TypeScript/TSX:** `.ts`, `.tsx`, `.mts`, `.cts`
     - **Kotlin:** `.kt`, `.kts`
     - **Rust:** `.rs`
     - **Go:** `.go`
     - **Swift:** `.swift`

2. **Apply exclusions:**
   - Filter out files in these directories:
     - `node_modules/`, `.git/`, `build/`, `dist/`, `target/`, `.gradle/`
     - `__pycache__/`, `.tox/`, `vendor/`, `.venv/`, `venv/`

3. **Respect .gitignore (if in git repo):**
   - If the directory is part of a git repository, use `git ls-files` to respect `.gitignore` rules
   - Only enumerate files that would be tracked by git

4. **Handle empty results:**
   - If no supported files are found, report: "No supported language files found in {path}. Nothing to review." (AC1.4)
   - Stop execution

5. **Confirm large repos:**
   - If more than 100 files are found, calculate estimated API calls:
     - **Production mode:** files × 6 (one file-reviewer agent + potential re-reviews)
     - **Test mode:** files × 5
   - Present the file count and estimated API calls to the user
   - Ask: "This would require approximately {count} API calls. Continue? (yes/no)"
   - If the user declines, suggest narrowing the scope (AC6.3)
   - If confirmed, proceed to Phase 3

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

## Phase 4: Agent Dispatch

Dispatch specialized reviewer agents in parallel:

1. **For each file, invoke the Agent tool:**
   ```
   subagent_type: "review-hammer:file-reviewer"
   description: "Review {filename}"
   prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}"
   ```

2. **Parallel execution:**
   - Dispatch multiple agents simultaneously (up to all files at once)
   - Rate limiting is handled by the `review_file.py` backend and Phase 6 safeguards
   - Collect the JSON output from each agent as it completes

3. **Expected output from each agent:**
   - JSON structure with fields like `findings`, `category`, `file`, `language`
   - Each finding includes: `description`, `severity`, `confidence`, `line_start`, `line_end`

## Phase 5: Opus Judge Pass

After all agents complete, perform these steps as Opus to synthesize findings:

### 5a. Deduplication (AC5.1)

- Compare findings across all agents and files
- If two or more findings reference the same line range in the same file with similar descriptions, merge them
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

### 5c. False Positive Filtering (AC5.3 partial)

- Review each remaining finding with expert judgment
- Consider:
  - Is this truly a bug, or could the code be correct in its context?
  - Are there framework/library patterns that make this code safe?
  - Is the issue only theoretical or does it have real impact?
- Remove findings that are clearly false positives

### 5d. Cross-File Pattern Detection (AC5.3)

- Analyze findings across all files to identify systemic patterns
- Look for: the same type of issue appearing in multiple files (e.g., missing error checks in 15 files)
- **Systemic patterns:** Report once with an affected file list instead of individually
  - Example: "Missing null checks in list iteration" → affected files: `service1.py`, `service2.py`, `handler.py`, ...
- **Unique per-file findings:** Keep separate and report individually

### 5e. Severity Ranking (AC5.4)

- Sort all findings by severity:
  - **Critical** (highest priority)
  - **High**
  - **Medium**
- Within the same severity level, sort by confidence (highest first)

## Phase 6: Report Formatting

Present the final report using this markdown template:

```markdown
# Code Review Report

**Target:** {target_path}
**Files reviewed:** {total_file_count}
**Findings:** {total_finding_count} ({critical_count} critical, {high_count} high, {medium_count} medium)

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

## Systemic Patterns

### [Pattern Name]
**Affected files:** `file1.py`, `file2.py`, `file3.py` (and {N} more)
**Category:** error-handling

[Description of the pattern and its occurrences across files]

---

*Reviewed by {agent_count} specialists across {file_count} files. {false_positive_count} false positives removed.*
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
