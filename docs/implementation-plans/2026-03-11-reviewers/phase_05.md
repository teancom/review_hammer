# Review Hammer Implementation Plan — Phase 5: Orchestrator Skill

**Goal:** User-facing skill that handles file enumeration, agent dispatch, and the Opus judge pass

**Architecture:** A Claude Code skill (`skills/fleet-review/SKILL.md`) that serves as the user entry point. When invoked via `/fleet-review <target>`, it enumerates source files, detects languages, dispatches Haiku `file-reviewer` agents in parallel, collects all findings, then performs the Opus judge pass (dedup, verify, filter, group, rank) before presenting the final report.

**Tech Stack:** Claude Code skill markdown, Agent tool dispatch, Read tool for verification

**Scope:** 6 phases from original design (this is phase 5 of 6)

**Codebase verified:** 2026-03-11 — `skills/fleet-review/` directory has `.gitkeep` from Phase 1. Skill format verified: YAML frontmatter with `name`, `description`, `user-invocable` fields; `$ARGUMENTS` for argument substitution; `${CLAUDE_SKILL_DIR}` for relative paths.

---

## Acceptance Criteria Coverage

This phase implements:

### reviewers.AC1: Skill accepts any code target
- **reviewers.AC1.1 Success:** Skill accepts a single file path, reviews it, returns findings
- **reviewers.AC1.2 Success:** Skill accepts a directory, enumerates files, reviews each, returns consolidated findings
- **reviewers.AC1.3 Failure:** Skill given a non-existent path reports clear error
- **reviewers.AC1.4 Edge:** Skill given a directory with no supported-language files reports "nothing to review"

### reviewers.AC5: Opus judge pass produces high-precision output
- **reviewers.AC5.1 Success:** Duplicate findings from multiple specialists are merged into one
- **reviewers.AC5.2 Success:** High-severity findings have line numbers verified against actual code
- **reviewers.AC5.3 Success:** Systemic patterns across files are grouped rather than listed individually
- **reviewers.AC5.4 Success:** Final report is ranked by severity (critical -> high -> medium)

**Verifies: None** — This is a skill definition (infrastructure/orchestration). Verification is operational: invoke `/fleet-review` on a target and confirm the full pipeline runs end-to-end producing a ranked report.

---

<!-- START_TASK_1 -->
### Task 1: Create the orchestrator skill SKILL.md

**Files:**
- Create: `skills/fleet-review/SKILL.md` (replaces `skills/fleet-review/.gitkeep`)

**Step 1: Create the skill definition**

The skill has YAML frontmatter and a detailed markdown body with instructions for Claude to follow when the skill is invoked.

**Frontmatter:**
```yaml
---
name: fleet-review
description: High-precision code review using specialized LLM agents. Use when user wants to review code for bugs across a file, directory, or repo. Dispatches category-specialized reviewers and presents a deduplicated, severity-ranked report.
user-invocable: true
disable-model-invocation: true
argument-hint: <file-or-directory-path>
---
```

`disable-model-invocation: true` because this skill has significant side effects (API calls, agent dispatch) and should only run when the user explicitly invokes it.

**Skill body — the full orchestration instructions:**

The skill body must instruct Claude through these phases:

**1. Input Validation**
- Parse `$ARGUMENTS` to get the target path
- If no arguments provided, ask the user what to review
- Verify the path exists (use Glob or Bash `test -e`)
- If path doesn't exist, report error and stop (AC1.3)
- If path is a single file, proceed to step 3 with a single-file list
- If path is a directory, proceed to step 2

**2. File Enumeration (directory targets)**
- Use Glob to find files with supported extensions in the target directory
- Supported extensions: `.py`, `.c`, `.h`, `.cpp`, `.cc`, `.cxx`, `.hpp`, `.hxx`, `.java`, `.cs`, `.js`, `.mjs`, `.cjs`, `.jsx`, `.ts`, `.tsx`, `.mts`, `.cts`, `.kt`, `.kts`, `.rs`, `.go`, `.swift`
- Filter out files in excluded directories: `node_modules/`, `.git/`, `build/`, `dist/`, `target/`, `.gradle/`, `__pycache__/`, `.tox/`, `vendor/`, `.venv/`, `venv/`
- Respect `.gitignore` by using `git ls-files` if in a git repo
- If no supported files found, report "nothing to review" and stop (AC1.4)
- For large repos (>100 files): present file count and estimated API calls (files × 6 for production or 5 for test), ask user to confirm or narrow scope (AC6.3 — implemented fully in Phase 6)

**3. Language Detection**
- For each file, detect language from extension using the same mapping as `review_file.py`:
  ```
  .py→python, .c/.h→c, .cpp/.cc/.cxx/.hpp/.hxx→cpp, .java→java,
  .cs→csharp, .js/.mjs/.cjs/.jsx→javascript, .ts/.tsx/.mts/.cts→typescript,
  .kt/.kts→kotlin, .rs→rust, .go→go, .swift→swift
  ```
- Unknown extensions fall back to `generic`

**4. Agent Dispatch**
- For each file, dispatch a `file-reviewer` agent (Haiku) using the Agent tool:
  ```
  Agent tool:
    subagent_type: "review-hammer:file-reviewer"
    description: "Review {filename}"
    prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}"
  ```
- Dispatch multiple agents in parallel (up to all files simultaneously — rate limiting handled by `review_file.py` and Phase 6)
- Collect the JSON output from each agent

**5. Opus Judge Pass**

After all agents complete, perform these steps as Opus (the current model):

**5a. Deduplication (AC5.1)**
- Compare findings across categories and files
- If two or more findings reference the same line range in the same file with similar descriptions, merge them into one finding
- Note which categories flagged it: `"flagged_by": ["logic-errors", "error-handling"]`

**5b. Line Number Verification (AC5.2)**
- For every finding with severity "critical" or "high":
  - Use the Read tool to read the actual file at the cited line range
  - Verify the finding description matches what's actually at those lines
  - If the line numbers are wrong or the described code isn't there, either correct the line numbers or discard the finding

**5c. False Positive Filtering (AC5.3 partial)**
- Review each remaining finding with your own judgment
- Consider: Is this actually a bug? Could the code be correct in context? Is there a framework/pattern that makes this safe?
- Remove findings that are clearly false positives

**5d. Cross-File Pattern Detection (AC5.3)**
- Look for systemic patterns: the same type of issue appearing in multiple files
- Group systemic findings: instead of listing "missing error check" 15 times, report it once as a systemic pattern with affected file list
- Keep unique per-file findings separate

**5e. Severity Ranking (AC5.4)**
- Sort findings: critical first, then high, then medium
- Within same severity, sort by confidence (highest first)

**6. Report Formatting**

Present the final report to the user in this format:

```markdown
# Code Review Report

**Target:** {path}
**Files reviewed:** {count}
**Findings:** {total_count} ({critical_count} critical, {high_count} high, {medium_count} medium)

## Critical

### [Finding title]
**File:** `path/to/file.py:123-125`
**Category:** logic-error (also flagged by: error-handling)
**Confidence:** 0.95

[Description of the bug]

**Impact:** [What goes wrong]

**Code:**
```python
[actual code at those lines]
```

---

## High

[... same format ...]

## Medium

[... same format ...]

## Systemic Patterns

### [Pattern name]
**Affected files:** `file1.py`, `file2.py`, `file3.py` (and N more)
**Category:** error-handling

[Description of the pattern]

---

*Reviewed by {count} specialists across {file_count} files. {filtered_count} false positives removed.*
```

**Step 2: Remove the .gitkeep placeholder**

Run: `rm skills/fleet-review/.gitkeep`

**Step 3: Verify skill frontmatter**

Run: `head -8 skills/fleet-review/SKILL.md`
Expected: Shows YAML frontmatter with `name: fleet-review`, `user-invocable: true`

**Commit:** `feat: add fleet-review orchestrator skill`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify skill definition completeness

**Step 1: Verify all workflow phases are documented in the skill**

Run:
```bash
echo "=== Key workflow sections ==="
grep -c 'Input Validation\|File Enumeration\|Language Detection\|Agent Dispatch\|Judge Pass\|Report' skills/fleet-review/SKILL.md

echo "=== AC coverage references ==="
grep -c 'AC1\.\|AC5\.' skills/fleet-review/SKILL.md

echo "=== Agent dispatch pattern ==="
grep -c 'file-reviewer' skills/fleet-review/SKILL.md

echo "=== Severity levels ==="
grep -c 'critical\|high\|medium' skills/fleet-review/SKILL.md
```
Expected: All counts ≥ 1

**Step 2: Verify the skill is properly structured**

Run:
```bash
# Check skill file exists and has content
wc -l skills/fleet-review/SKILL.md
```
Expected: Substantial line count (150+ lines for the orchestration instructions)

No commit for this task — it's a verification step only.
<!-- END_TASK_2 -->
