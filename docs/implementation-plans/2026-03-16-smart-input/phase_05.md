# Smart Input Implementation Plan — Phase 5

**Goal:** `skills/review-hammer/SKILL.md` classifies user arguments into five modes and resolves natural language to git refs.

**Architecture:** Replace the existing Phase 1 (Input Validation) in the review-hammer skill with an extended version that classifies `$ARGUMENTS` into five input modes — commit, branch, file-diff, file-full, or directory — and resolves natural language arguments ("this commit", "this branch") to concrete git refs. The resolved mode and git ref flow into subsequent phases.

**Tech Stack:** Markdown skill definition (Claude Code plugin system), git CLI

**Scope:** 7 phases from original design (phase 5 of 7)

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements:

### smart-input.AC1: Commit and branch review via natural language
- **smart-input.AC1.1 Success:** `/review-hammer this commit` reviews only files changed in HEAD, using diff + context
- **smart-input.AC1.2 Success:** `/review-hammer this branch` reviews cumulative diff from branch divergence point
- **smart-input.AC1.4 Failure:** `/review-hammer this commit` in a non-git directory returns a clear error
- **smart-input.AC1.5 Edge:** `/review-hammer this commit` on a merge commit reviews the merge diff

### smart-input.AC2: File review with dirty/clean detection
- **smart-input.AC2.1 Success:** `/review-hammer <dirty-file>` reviews uncommitted changes as diff + context
- **smart-input.AC2.2 Success:** `/review-hammer <clean-file>` reviews the full file (current behavior)
- **smart-input.AC2.3 Edge:** `/review-hammer <untracked-file>` (not in git) falls back to full-file mode

### smart-input.AC3: Directory review
- **smart-input.AC3.1 Success:** `/review-hammer <directory>` classifies each file as dirty or clean and dispatches accordingly

---

<!-- START_TASK_1 -->
### Task 1: Replace Phase 1 with input mode classifier

**Files:**
- Modify: `skills/review-hammer/SKILL.md:12-28` (replace entire Phase 1 section)

**Implementation:**

Replace the existing `## Phase 1: Input Validation` section (lines 12-28) with a new `## Phase 1: Input Mode Detection` section. The new section classifies `$ARGUMENTS` into one of five modes and resolves git refs.

The new Phase 1 should contain these steps:

```markdown
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
```

**Verification:**
Read the modified file and confirm:
- All five input modes are documented with clear classification rules
- Git ref resolution is explicit (not left to the agent to figure out)
- Error handling for non-git directories is specified (AC1.4)
- Merge commit handling is specified (AC1.5)
- Untracked file fallback is specified (AC2.3)

**Commit:** `feat: add input mode detection to review-hammer skill Phase 1`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update Phase 2 for per-file dirty/clean classification

**Files:**
- Modify: `skills/review-hammer/SKILL.md:29-84` (Phase 2: File Enumeration section)

**Implementation:**

Update the existing Phase 2 to add per-file dirty/clean classification when `input_mode` is "directory". After file enumeration (step 1-2) and before the "Handle empty results" step, add:

```markdown
3. **Per-file dirty/clean classification (directory mode only):**
   - Run via Bash: `git status --porcelain -- {directory_path} 2>/dev/null`
   - Parse output to identify dirty files (lines starting with ` M`, `M `, `MM`, `A `, `??`, etc.)
   - For each enumerated file:
     - If file appears in git status output → mark as dirty, assign `DIFF_BASE` = `HEAD`
     - If file does NOT appear → mark as clean, assign `DIFF_BASE` = none
     - If git status failed (not a git repo) → all files are clean (full-file mode)
   - Store per-file `diff_base` values for Phase 4 dispatch
```

For commit and branch modes, Phase 2 is skipped entirely — the file list is already resolved in Phase 1.

**Verification:**
Read the modified file and confirm:
- Directory mode adds per-file dirty/clean classification
- Commit/branch modes skip Phase 2
- Per-file diff_base values are stored for Phase 4

**Commit:** `feat: add per-file dirty/clean classification to review-hammer Phase 2`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify all modes work end-to-end (manual testing)

**Files:**
- No new files — manual verification only

**Verification:**

After the skill changes are deployed, test each mode manually:

1. **Commit mode:** `/review-hammer this commit` — verify it resolves HEAD~1 and lists changed files
2. **Branch mode:** `/review-hammer this branch` — verify merge-base resolution
3. **File-diff:** `/review-hammer <dirty-file>` — verify dirty detection
4. **File-full:** `/review-hammer <clean-file>` — verify clean detection
5. **Directory:** `/review-hammer <directory>` — verify per-file classification
6. **Error:** `/review-hammer this commit` in non-git directory — verify error message (AC1.4)

**Commit:** No commit — verification step.
<!-- END_TASK_3 -->
