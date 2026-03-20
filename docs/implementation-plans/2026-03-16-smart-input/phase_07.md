# Smart Input Implementation Plan — Phase 7

**Goal:** Graceful handling of all edge cases identified during design, plus version bump.

**Architecture:** Add edge case handling to `scripts/review_file.py` (binary files, deleted files, empty diffs, invalid git refs) and to `skills/review-hammer/SKILL.md` (untracked files). Bump version in plugin manifests.

**Tech Stack:** Python 3.10+, Markdown skill definitions, JSON manifests

**Scope:** 7 phases from original design (phase 7 of 7)

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### smart-input.AC1: Commit and branch review via natural language
- **smart-input.AC1.4 Failure:** `/review-hammer this commit` in a non-git directory returns a clear error *(defense-in-depth: Phase 5 handles this at the skill layer for non-git directories; this phase handles it at the script layer for invalid git refs)*

### smart-input.AC2: File review with dirty/clean detection
- **smart-input.AC2.3 Edge:** `/review-hammer <untracked-file>` (not in git) falls back to full-file mode *(defense-in-depth: Phase 5 handles this at the skill layer; this phase provides script-layer fallback)*

### smart-input.AC6: Backward compatibility
- **smart-input.AC6.1 Success:** Omitting `--diff-base` produces identical behavior to current implementation
- **smart-input.AC6.2 Success:** All existing unit tests and corpus tests pass without modification

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Handle binary files in diff mode

**Verifies:** (edge case robustness, not a specific AC)

**Files:**
- Modify: `scripts/review_file.py` (in the diff mode branch of `review_file()`)

**Implementation:**

When `--diff-base` is provided and `git diff` output contains `Binary files ... differ`, skip the file with a warning instead of attempting to parse non-existent hunks.

In the diff mode branch of `review_file()` (added in Phase 1, Task 8), after getting `diff_output`, add:

```python
if "Binary files" in diff_output and "differ" in diff_output:
    print(
        f"[review] SKIP {category} for {file_path} (binary file)",
        file=sys.stderr,
    )
    return []
```

This check should come before `parse_unified_diff(diff_output)`.

**Testing:**
- Binary file in diff output → returns empty findings with skip log
- Non-binary diff output → proceeds normally (no regression)

Add tests to `TestReviewFileDiffMode` class. Mock `subprocess.run` to return binary diff output.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py::TestReviewFileDiffMode -x -v`
Expected: All tests pass

**Commit:** `fix: skip binary files in diff mode`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Handle deleted files in diff mode

**Verifies:** (edge case robustness)

**Files:**
- Modify: `scripts/review_file.py` (in `review_file()` diff mode branch)

**Implementation:**

When `--diff-base` is provided but the file doesn't exist on disk (it was deleted), skip with a note. The file read (`open(file_path)`) will raise `FileNotFoundError`. However, `review_file()` is called after `main()` checks `os.path.exists()`, so we need to handle the case where the file exists in the diff but was deleted between the `git diff --name-only` and the review.

In the diff mode branch, before reading the file, add:

```python
if diff_base is not None and not os.path.exists(file_path):
    print(
        f"[review] SKIP {category} for {file_path} (file deleted)",
        file=sys.stderr,
    )
    return []
```

Also update the skill-level dispatch (Phase 5/6): When using `git diff --name-only --diff-filter=ACMR`, the `--diff-filter=ACMR` flag already excludes deleted files (D). This was specified in Phase 5 Task 1. Verify this filter is present.

**Testing:**
- Diff mode with non-existent file → returns empty findings with skip log
- Diff mode with existing file → proceeds normally

Add test to `TestReviewFileDiffMode`.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py::TestReviewFileDiffMode -x -v`
Expected: All tests pass

**Commit:** `fix: handle deleted files gracefully in diff mode`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Handle invalid git ref and empty diff

**Verifies:** smart-input.AC1.4

**Files:**
- Modify: `scripts/review_file.py` (in `review_file()` diff mode branch)

**Implementation:**

When `subprocess.run(["git", "diff", ...])` fails (invalid ref, not a git repo), catch the `subprocess.CalledProcessError` and return a clear error:

```python
try:
    diff_output = subprocess.run(
        ["git", "diff", diff_base, "--", file_path],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
except subprocess.CalledProcessError as e:
    print(
        f"Error: git diff failed for {file_path} with ref '{diff_base}': {e.stderr.strip()}",
        file=sys.stderr,
    )
    sys.exit(1)
```

Empty diff (no changes) is already handled in Phase 1, Task 8: `if not hunks: return []`.

**Testing:**
- Invalid git ref (e.g., `--diff-base nonexistent-ref`) → exits with code 1 and clear error
- Valid git ref but no changes for this file → returns empty list (already tested)

Add test to `TestReviewFileDiffMode`.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py::TestReviewFileDiffMode -x -v`
Expected: All tests pass

**Commit:** `fix: handle invalid git ref with clear error message`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Full backward compatibility verification

**Verifies:** smart-input.AC6.1, smart-input.AC6.2

**Files:**
- No new files — verification only

**Verification:**

Run the full test suite to ensure all existing tests pass:

Run: `.venv/bin/pytest tests/ -x -v`
Expected: ALL tests pass — both existing and new

Run the corpus calibration tests:

Run: `REVIEWERS_API_KEY=... uv run scripts/test_corpus.py`
Expected: All corpus tests pass (unchanged behavior for full-file mode)

Run: `ruff check scripts/review_file.py tests/test_review_file.py`
Expected: No lint errors

Run: `ruff format --check scripts/review_file.py tests/test_review_file.py`
Expected: No formatting issues

**Commit:** No commit — verification step.
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Version bump

**Files:**
- Modify: `.claude-plugin/plugin.json:3` (version field)
- Modify: `.claude-plugin/marketplace.json:17` (version field in plugins array)

**Implementation:**

Bump the version from `0.16.4` to `0.17.0` in both files (minor version bump for new feature). Both files must have the same version — the PreToolUse hook at `.claude/hooks/enforce-version-bump.sh` enforces this.

**Note:** Verify current version before bumping — the target of `0.17.0` assumes no intervening version changes on `main`. If the version has already been bumped past `0.16.4`, adjust accordingly.

In `.claude-plugin/plugin.json`:
```json
"version": "0.17.0",
```

In `.claude-plugin/marketplace.json`:
```json
"version": "0.17.0",
```

**Verification:**
Confirm both files have the same version:
```bash
grep '"version"' .claude-plugin/plugin.json .claude-plugin/marketplace.json
```
Expected: Both show `0.17.0`

**Commit:** `chore: bump version to 0.17.0 for smart-input feature`
<!-- END_TASK_5 -->
