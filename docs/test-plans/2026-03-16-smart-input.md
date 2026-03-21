# Smart Input — Human Test Plan

Generated from test-requirements.md after automated coverage validation (16/16 automated criteria PASS, 141 tests passing).

## Prerequisites

- Local clone of `review_hammer` on the `smart-input` branch
- `REVIEWERS_API_KEY` environment variable set with a valid API key
- Claude Code installed with the `review-hammer` plugin active
- `.venv/bin/pytest tests/ -x -v` passing (141 tests, 0 failures)
- A git repository with at least one commit (for commit/branch mode tests)

## Phase 1: Commit and Branch Mode (AC1.1, AC1.2, AC1.5)

| Step | Action | Expected |
|------|--------|----------|
| 1 | In a repo with a recent commit that changes 2-3 files, invoke `/review-hammer this commit`. | Skill resolves `DIFF_BASE=HEAD~1`. Only files from `git diff HEAD~1..HEAD --name-only` are dispatched. |
| 2 | Observe agent prompts (stderr or debug output). | Each agent receives `DIFF_BASE` in its prompt. Findings only reference lines in the changed code. |
| 3 | On a feature branch diverged from `main` with 3+ commits, invoke `/review-hammer this branch`. | Skill runs `git merge-base HEAD origin/main` and sets `DIFF_BASE` to that hash. Files from `git diff {merge-base}..HEAD --name-only` are dispatched. |
| 4 | Create a merge commit, then invoke `/review-hammer this commit`. | Skill detects merge commit (3+ fields in `git rev-list --parents -n 1 HEAD`). `DIFF_BASE=HEAD~1`. Merge diff reviewed. |

## Phase 2: File Mode — Dirty/Clean/Untracked (AC2.1, AC2.2, AC2.3)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Modify a tracked file without committing. Invoke `/review-hammer <that-file>`. | Skill detects dirty status via `git status --porcelain`. Agent receives `DIFF_BASE=HEAD`. Review covers only uncommitted changes. |
| 2 | Revert the modification so the file is clean. Invoke `/review-hammer <that-file>`. | Skill detects clean status. No `DIFF_BASE` passed. Full-file review occurs. |
| 3 | Create a new file not `git add`ed. Invoke `/review-hammer <that-file>`. | Skill's `git status --porcelain` shows `??`. Mode = file-full. No `DIFF_BASE` passed. Full-file review completes. |

## Phase 3: Directory Mode (AC3.1, AC3.2)

| Step | Action | Expected |
|------|--------|----------|
| 1 | In a directory with 2 modified and 2 clean files, invoke `/review-hammer <directory>`. | Dirty files dispatched with `DIFF_BASE=HEAD`. Clean files dispatched without `DIFF_BASE`. |
| 2 | Wait for completion. | Unified report combines findings from all files. Report header shows directory path and file count. |

## Phase 4: Error Handling (AC1.4)

| Step | Action | Expected |
|------|--------|----------|
| 1 | From a non-git directory (e.g., `/tmp`), invoke `/review-hammer this commit`. | Skill reports "Error: Not a git repository or no commits yet." and stops cleanly. |
| 2 | From the repo, run `uv run scripts/review_file.py somefile.py --category logic-errors --diff-base nonexistent-ref`. | Script exits with error. Message includes the ref name and git's stderr. |

## Phase 5: Prompt Template Integrity (AC6.3)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `git diff main -- prompts/` from the repo root. | Zero changes. No prompt template files modified. |

## Phase 6: test-hammer Chunking (AC7.1)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Invoke `/test-hammer <large-file>` on a file with 2900+ lines. | Stderr shows `[review] CHUNK 1/N...` messages. |
| 2 | Wait for completion. | Test suggestions merged. Review completes without timeout. |

## End-to-End: Full Commit Review Pipeline

1. Make a small intentional change (e.g., introduce a deliberate logic error).
2. Commit the change.
3. Invoke `/review-hammer this commit`.
4. Verify: (a) only changed file reviewed, (b) findings reference lines within the change, (c) deliberate error flagged, (d) report formatted with severity ranking.
5. Revert the commit after testing.

## End-to-End: Mixed Directory with Large File Chunking

1. In a directory, place one small dirty file (20 lines, modified), one clean file (50 lines), and one large clean file (3000+ lines).
2. Invoke `/review-hammer <directory>`.
3. Verify: (a) dirty file in diff mode, (b) clean 50-line file in full-file mode without chunking, (c) large file in full-file mode WITH chunking (check stderr for `CHUNK` logs), (d) unified report includes all three files.

## Traceability

| AC | Automated Test | Manual Step |
|----|----------------|-------------|
| AC1.1 | -- | Phase 1, Step 1-2 |
| AC1.2 | -- | Phase 1, Step 3 |
| AC1.3 | `TestParseUnifiedDiff`, `TestAssembleDiffContext` | -- |
| AC1.4 | `TestGitDiffErrorHandling` | Phase 4, Step 1-2 |
| AC1.5 | -- | Phase 1, Step 4 |
| AC2.1 | `TestReviewFileDiffMode` | Phase 2, Step 1 |
| AC2.2 | `TestReviewFileDiffMode`, existing tests | Phase 2, Step 2 |
| AC2.3 | -- | Phase 2, Step 3 |
| AC3.1 | -- | Phase 3, Step 1 |
| AC3.2 | -- | Phase 3, Step 2 |
| AC4.1 | `TestSplitIntoChunks`, `TestChunkedReview` | -- |
| AC4.2 | `TestSplitIntoChunks` | -- |
| AC4.3 | `TestDeduplicateFindings` (12 tests) | -- |
| AC4.4 | `TestChunkedReview` | -- |
| AC4.5 | `TestSplitIntoChunks` | -- |
| AC5.1 | `TestParseUnifiedDiff`, `TestExtractFileHeader`, `TestAssembleDiffContext` | -- |
| AC5.2 | `TestAssembleDiffContext` | -- |
| AC5.3 | `TestDetectCoverage`, `TestBuildDiffUserMessage` | -- |
| AC5.4 | `TestBuildDiffUserMessage`, `TestReviewFileDiffMode` | -- |
| AC6.1 | `TestMainCLI`, `TestReviewFileDiffMode`, all existing tests | -- |
| AC6.2 | Full suite (141 passed) | -- |
| AC6.3 | `TestBuildDiffUserMessage` (partial) | Phase 5, Step 1 |
| AC7.1 | `TestChunkedReview` | Phase 6, Step 1-2 |
| AC7.2 | `TestChunkedReview` (implicit shared path) | -- |
