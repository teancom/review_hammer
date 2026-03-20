# Smart Input — Test Requirements

Maps each acceptance criterion (smart-input.AC1.1 through smart-input.AC7.2) to automated tests and/or human verification steps. Every criterion has at least one verification method.

**Conventions:**
- Test file: `tests/test_review_file.py` (all automated tests live here)
- Imports: Tests import functions and constants from `review_file` (the script module)
- Constants: Tests MUST use imported constants (e.g., `CHUNK_THRESHOLD`, `FULL_COVERAGE_THRESHOLD`), never hardcoded values
- Mocking: `subprocess.run` for git commands, `OpenAI` for API calls

---

## smart-input.AC1: Commit and branch review via natural language

### smart-input.AC1.1 — `/review-hammer this commit` reviews only files changed in HEAD, using diff + context

| Aspect | Detail |
|--------|--------|
| **Automated** | No — this is an end-to-end skill invocation. The skill is a markdown template interpreted by Claude Code, not executable Python. |
| **Human verification** | Invoke `/review-hammer this commit` in a repo with a recent commit. Verify: (1) skill resolves `DIFF_BASE=HEAD~1`, (2) only files from `git diff HEAD~1..HEAD --name-only` are dispatched, (3) agents receive `DIFF_BASE` in their prompt, (4) findings only reference changed code. |
| **Phase** | Phase 5 (mode detection), Phase 6 (dispatch integration) |
| **Justification** | The skill layer is declarative markdown — no unit-testable Python code. Input mode detection, git ref resolution, and agent dispatch all happen within the Claude Code skill runtime, which has no test harness. |

### smart-input.AC1.2 — `/review-hammer this branch` reviews cumulative diff from branch divergence point

| Aspect | Detail |
|--------|--------|
| **Automated** | No — same reasoning as AC1.1 (skill-layer logic). |
| **Human verification** | On a feature branch diverged from main, invoke `/review-hammer this branch`. Verify: (1) skill runs `git merge-base HEAD origin/main`, (2) `DIFF_BASE` is set to the merge-base hash, (3) files from `git diff {merge-base}..HEAD --name-only` are dispatched, (4) review covers cumulative branch changes. |
| **Phase** | Phase 5 (mode detection), Phase 6 (dispatch integration) |
| **Justification** | Same as AC1.1 — skill-layer orchestration with no Python test surface. |

### smart-input.AC1.3 — Findings reference original file line numbers, not diff-relative positions

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestParseUnifiedDiff` |
| Test methods | `test_hunk_ranges_use_original_line_numbers` — verifies that parsed hunk `start_line`/`end_line` come from the `-` side of `@@` headers (original file positions, not `+` side) |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 3 |
| | |
| Test class | `TestAssembleDiffContext` |
| Test methods | `test_line_numbers_match_original_file` — verifies that assembled output line numbers (e.g., `50| code`) correspond to the original file's line positions, not sequential positions within the excerpt |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 5 |

### smart-input.AC1.4 — `/review-hammer this commit` in a non-git directory returns a clear error

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestReviewFileDiffMode` |
| Test methods | `test_invalid_git_ref_exits_with_error` — mocks `subprocess.run` to raise `CalledProcessError`, verifies exit code 1 and error message on stderr |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 7, Task 3 |
| | |
| **Human verification** | Invoke `/review-hammer this commit` from a non-git directory (e.g., `/tmp`). Verify the skill reports "Error: Not a git repository or no commits yet." and stops. |
| **Phase (skill layer)** | Phase 5, Task 1 (skill-level `git rev-parse --verify HEAD` check) |
| **Justification for both** | Defense-in-depth: Phase 5 handles at the skill layer (markdown, human-verified), Phase 7 handles at the script layer (Python, automated). Both layers must produce clear errors. |

### smart-input.AC1.5 — `/review-hammer this commit` on a merge commit reviews the merge diff

| Aspect | Detail |
|--------|--------|
| **Automated** | No — merge commit detection happens in the skill layer (`git rev-list --parents -n 1 HEAD`). |
| **Human verification** | Create a merge commit, then invoke `/review-hammer this commit`. Verify: (1) skill detects merge commit (3+ fields in `git rev-list --parents`), (2) `DIFF_BASE` is set to `HEAD~1`, (3) merge diff is reviewed. |
| **Phase** | Phase 5, Task 1 |
| **Justification** | Merge commit detection is skill-layer logic with no Python test surface. The script receives the same `--diff-base HEAD~1` regardless of whether the commit is a merge — so the script behavior is already covered by other diff mode tests. |

---

## smart-input.AC2: File review with dirty/clean detection

### smart-input.AC2.1 — `/review-hammer <dirty-file>` reviews uncommitted changes as diff + context

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestReviewFileDiffMode` |
| Test methods | `test_diff_mode_runs_git_diff_and_assembles_context` — mocks `subprocess.run` returning diff output, verifies `review_file()` with `diff_base="HEAD"` produces a diff-mode user message |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 8 |
| | |
| **Human verification** | Modify a tracked file without committing, invoke `/review-hammer <that-file>`. Verify: (1) skill detects dirty status via `git status --porcelain`, (2) passes `DIFF_BASE=HEAD` to agent, (3) review covers only uncommitted changes. |
| **Phase (skill layer)** | Phase 5 (dirty detection), Phase 6 (dispatch) |

### smart-input.AC2.2 — `/review-hammer <clean-file>` reviews the full file (current behavior)

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestReviewFileDiffMode` |
| Test methods | `test_no_diff_base_produces_full_file_message` — calls `review_file()` without `diff_base`, verifies user message starts with `# Source file:` and contains full numbered content (identical to pre-smart-input behavior) |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 8 |
| | |
| **Existing tests** | All pre-existing tests in `TestReviewFile` class already exercise full-file mode and must continue passing (AC6.2). |
| **Human verification** | Invoke `/review-hammer <clean-file>` on a committed, unmodified file. Verify full-file review with no diff framing. |
| **Phase (skill layer)** | Phase 5 (clean detection), Phase 6 (dispatch without DIFF_BASE) |

### smart-input.AC2.3 — `/review-hammer <untracked-file>` falls back to full-file mode

| Aspect | Detail |
|--------|--------|
| **Automated** | No direct test for the skill-layer fallback. At the script layer, untracked files never receive `--diff-base` (the skill omits it), so existing full-file tests cover the script path. |
| **Human verification** | Create a new file not tracked by git, invoke `/review-hammer <that-file>`. Verify: (1) skill's `git status --porcelain` fails or shows `??`, (2) mode = file-full, (3) no `DIFF_BASE` passed, (4) full-file review completes normally. |
| **Phase** | Phase 5, Task 1 (skill-layer fallback logic); Phase 7, Task 2 (defense-in-depth script-layer check) |
| **Justification** | The fallback decision is made in skill-layer markdown. The script never sees `--diff-base` for untracked files, so the script path is already tested by full-file mode tests. |

---

## smart-input.AC3: Directory review

### smart-input.AC3.1 — `/review-hammer <directory>` classifies each file as dirty or clean and dispatches accordingly

| Aspect | Detail |
|--------|--------|
| **Automated** | No — directory enumeration, per-file classification, and mixed dispatch are all skill-layer logic. |
| **Human verification** | In a directory with mixed dirty/clean files, invoke `/review-hammer <directory>`. Verify: (1) skill runs `git status --porcelain -- <dir>`, (2) dirty files dispatched with `DIFF_BASE=HEAD`, (3) clean files dispatched without `DIFF_BASE`, (4) all files reviewed. |
| **Phase** | Phase 5, Task 2 (per-file classification); Phase 6, Task 1 (dispatch) |
| **Justification** | Entirely skill-layer orchestration. The per-file script invocations are individually covered by AC2.1/AC2.2 automated tests. |

### smart-input.AC3.2 — Mixed directory produces a unified report

| Aspect | Detail |
|--------|--------|
| **Automated** | No — report assembly is skill-layer logic (Opus judge pass). |
| **Human verification** | Same test as AC3.1. Additionally verify: (1) final report combines findings from all files, (2) report header shows directory path and file count, (3) no files are missing from the report. |
| **Phase** | Phase 6, Task 3 (report header); existing report formatting |
| **Justification** | The Opus judge pass and report formatting are markdown instructions executed by Claude Code. No Python code to unit test. |

---

## smart-input.AC4: Auto-chunking

### smart-input.AC4.1 — File exceeding chunk threshold is split, reviewed per-chunk, and findings merged

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestSplitIntoChunks` |
| Test methods | `test_content_exceeding_threshold_produces_multiple_chunks` — creates content of `CHUNK_THRESHOLD + 500` lines, verifies `split_into_chunks()` returns 2+ chunks |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 2, Task 1 |
| | |
| Test class | `TestChunkedReview` |
| Test methods | `test_large_file_triggers_chunking_with_multiple_api_calls` — creates a temp file exceeding `CHUNK_THRESHOLD`, mocks API to return findings per chunk, verifies `review_file()` makes multiple API calls and returns merged findings |
| Test type | Integration (mocked API) |
| File | `tests/test_review_file.py` |
| Phase | Phase 2, Task 3 |

### smart-input.AC4.2 — Chunks include file header (imports/definitions) for context

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestSplitIntoChunks` |
| Test methods | `test_each_chunk_starts_with_file_header` — provides a file header string, verifies every chunk returned by `split_into_chunks()` begins with that header |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 2, Task 1 |

### smart-input.AC4.3 — Overlapping chunk regions produce deduplicated findings

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestDeduplicateFindings` |
| Test methods | `test_identical_findings_from_different_chunks_deduplicated` — two findings with same category and lines from different chunks reduced to one |
| | `test_near_duplicate_findings_within_tolerance_deduplicated` — two findings with same category and lines within 2-line tolerance, higher severity kept |
| | `test_different_category_same_lines_both_kept` — findings with different categories but same lines are NOT deduplicated |
| | `test_same_category_distant_lines_both_kept` — findings with same category but far-apart lines are NOT deduplicated |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 2, Task 2 |

### smart-input.AC4.4 — Chunking works for both diff mode and full-file mode

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestChunkedReview` |
| Test methods | `test_large_diff_content_triggers_chunking` — provides `diff_base` with large diff output, verifies chunking activates in diff mode |
| | `test_large_full_file_triggers_chunking` — provides large file without `diff_base`, verifies chunking activates in full-file mode |
| Test type | Integration (mocked API, mocked subprocess) |
| File | `tests/test_review_file.py` |
| Phase | Phase 2, Task 3 |

### smart-input.AC4.5 — File just under the threshold is NOT chunked

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestSplitIntoChunks` |
| Test methods | `test_content_under_threshold_returns_single_chunk` — content of `CHUNK_THRESHOLD - 1` lines returns exactly one chunk (the original content with header prepended) |
| | `test_content_exactly_at_threshold_returns_single_chunk` — content of exactly `CHUNK_THRESHOLD` lines returns one chunk |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 2, Task 1 |

---

## smart-input.AC5: Diff context assembly

### smart-input.AC5.1 — Diff hunks include file header plus surrounding context lines with original line numbers

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestParseUnifiedDiff` |
| Test methods | `test_multi_hunk_diff_extracts_correct_ranges` — parse a diff with 3 hunks, verify each hunk's `start_line`/`end_line` matches the `@@` header |
| | `test_single_line_hunk_count_omitted` — `@@ -5 +5,2 @@` parsed as count=1 |
| | `test_empty_diff_returns_empty_list` |
| | `test_new_file_diff` — `@@ -0,0 +1,10 @@` handled correctly |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 3 |
| | |
| Test class | `TestExtractFileHeader` |
| Test methods | `test_python_file_returns_imports_before_def` — Python file with imports then `def` returns only imports |
| | `test_rust_file_returns_use_before_fn` — Rust file with `use` then `fn` returns `use` section |
| | `test_no_definitions_returns_capped_content` — config file returns entire content (capped at `MAX_HEADER_LINES`) |
| | `test_empty_file_returns_empty_string` |
| | `test_file_starting_with_def_returns_empty` |
| | `test_header_exceeding_max_lines_is_capped` |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 4 |
| | |
| Test class | `TestAssembleDiffContext` |
| Test methods | `test_single_hunk_with_context_includes_header_and_surrounding_lines` — single hunk with `context_lines=3` verifies header prepended, 3 lines above/below, original line numbers |
| | `test_hunk_at_start_of_file` — no lines above to include |
| | `test_hunk_at_end_of_file` — no lines below to include |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 5 |

### smart-input.AC5.2 — Adjacent hunks with overlapping context windows are merged into one continuous block

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestAssembleDiffContext` |
| Test methods | `test_adjacent_hunks_with_overlapping_context_merged` — two hunks 2 lines apart with `context_lines=3` produce one continuous block (no `...` separator) |
| | `test_distant_hunks_remain_separate_with_separator` — two hunks far apart produce separate blocks with `...` separator |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 5 |

### smart-input.AC5.3 — When assembled content covers >=90% of the file, full-file framing is used

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestDetectCoverage` |
| Test methods | `test_high_coverage_returns_true` — 100-line file, hunks covering 92 lines after expansion -> True |
| | `test_low_coverage_returns_false` — 100-line file, hunks covering 50 lines -> False |
| | `test_exactly_90_percent_returns_true` — boundary: exactly 90% -> True |
| | `test_just_under_90_percent_returns_false` — boundary: 89% -> False |
| | `test_empty_hunks_returns_false` |
| | `test_single_hunk_covering_entire_file_returns_true` |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 6 |
| | |
| Test class | `TestBuildDiffUserMessage` |
| Test methods | `test_full_coverage_uses_source_file_header_and_markers_instructions` — high-coverage hunks produce message with `# Source file:` and `DIFF_FULL_WITH_MARKERS_INSTRUCTIONS` |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 7 |

### smart-input.AC5.4 — Runtime instruction block injected before content explains the format to the LLM

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestBuildDiffUserMessage` |
| Test methods | `test_partial_coverage_includes_partial_instructions` — low-coverage hunks produce message starting with `# Diff review:` and containing `DIFF_PARTIAL_INSTRUCTIONS` text |
| | `test_full_coverage_includes_markers_instructions` — high-coverage hunks produce message containing `DIFF_FULL_WITH_MARKERS_INSTRUCTIONS` text |
| | `test_no_prompt_template_files_read` — function only builds a string; verify no file I/O occurs (satisfies AC6.3 at this function level) |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 7 |
| | |
| Test class | `TestReviewFileDiffMode` |
| Test methods | `test_diff_mode_user_message_contains_instructions` — end-to-end through `review_file()`, verify the user message passed to OpenAI contains runtime instructions |
| Test type | Integration (mocked API, mocked subprocess) |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 8 |

---

## smart-input.AC6: Backward compatibility

### smart-input.AC6.1 — Omitting `--diff-base` produces identical behavior to current implementation

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestMainCLI` |
| Test methods | `test_diff_base_defaults_to_none` — parse args without `--diff-base`, verify `args.diff_base is None` |
| | `test_context_lines_defaults_to_3` — parse args without `--context-lines`, verify `args.context_lines == 3` |
| | `test_diff_base_and_context_lines_passed_to_review_file` — verify both new params are forwarded in the `review_file()` call |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Tasks 1-2 |
| | |
| Test class | `TestReviewFileDiffMode` |
| Test methods | `test_no_diff_base_produces_full_file_message` — calls `review_file()` without `diff_base`, verifies identical user message format to pre-smart-input behavior |
| Test type | Unit |
| File | `tests/test_review_file.py` |
| Phase | Phase 1, Task 8 |
| | |
| **Existing tests** | ALL pre-existing tests in `TestPrependLineNumbers`, `TestExtractCategoryPrompt`, `TestParseFindings`, `TestDetectLanguage`, `TestReviewFile`, `TestMainCLI`, `TestRetryBehavior`, `TestParseRetryAfter` must pass without modification. |
| **Phase** | Phase 1, Task 9 (verification); Phase 7, Task 4 (final verification) |

### smart-input.AC6.2 — All existing unit tests and corpus tests pass without modification

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test command | `.venv/bin/pytest tests/ -x -v` |
| Test type | Full suite run |
| Phase | Phase 1, Task 9; Phase 2, Task 4; Phase 7, Task 4 |
| | |
| **Corpus tests** | |
| Test command | `REVIEWERS_API_KEY=... uv run scripts/test_corpus.py` |
| Test type | Integration (live API) |
| Phase | Phase 7, Task 4 |
| | |
| **Justification** | This is verified by running the existing test suite at the end of each phase. No test modifications should be needed. If any existing test fails, it indicates a backward compatibility regression that must be fixed before proceeding. |

### smart-input.AC6.3 — No prompt template files are modified

| Aspect | Detail |
|--------|--------|
| **Automated** | Partially. `TestBuildDiffUserMessage.test_no_prompt_template_files_read` verifies the diff message builder does not perform file I/O. |
| **Human verification** | After all phases are complete, run `git diff main -- prompts/` and verify zero changes to any file in `prompts/`. |
| **Phase** | Verified across all phases |
| **Justification** | The design explicitly states instructions are injected at runtime by the script, not by modifying prompt templates. A simple `git diff` on the `prompts/` directory is the definitive check. |

---

## smart-input.AC7: test-hammer chunking

### smart-input.AC7.1 — test-hammer (full-file mode) chunks large files and produces merged suggestions

| Aspect | Detail |
|--------|--------|
| **Automated tests** | |
| Test class | `TestChunkedReview` |
| Test methods | `test_large_full_file_triggers_chunking` — this test (from AC4.4) covers the same code path. `review_file()` is called without `diff_base` (full-file mode, as test-hammer uses) with a file exceeding `CHUNK_THRESHOLD`. Verifies chunking activates, multiple API calls made, findings merged. |
| Test type | Integration (mocked API) |
| File | `tests/test_review_file.py` |
| Phase | Phase 2, Task 3 |
| | |
| **Human verification** | Invoke `/test-hammer <large-file>` on a file with 2900+ lines. Verify: (1) chunking activates (stderr shows `[review] CHUNK 1/N...` messages), (2) test suggestions from all chunks are merged, (3) review completes without timeout. |
| **Phase** | Phase 6, Task 2 (chunking awareness note); Phase 2 (chunking implementation) |

### smart-input.AC7.2 — Chunking in test-hammer uses the same code path as review-hammer chunking

| Aspect | Detail |
|--------|--------|
| **Automated** | Implicitly verified. Both test-hammer and review-hammer call `review_file()` in `scripts/review_file.py`. Chunking logic (`split_into_chunks`, `deduplicate_findings`, `_call_api` loop) lives inside `review_file()`, not in the skill or agent layers. Any test of `review_file()` chunking validates the shared code path. |
| **Explicit tests** | `TestChunkedReview.test_large_full_file_triggers_chunking` (full-file mode = test-hammer path) and `TestChunkedReview.test_large_diff_content_triggers_chunking` (diff mode = review-hammer path) both exercise the same `split_into_chunks` and `deduplicate_findings` functions. |
| **Human verification** | Optional confirmation: review the code after implementation and verify there is exactly one chunking code path in `review_file()`, not separate paths for review-hammer vs test-hammer. |
| **Phase** | Phase 2 (implementation); Phase 6, Task 2 (documentation) |
| **Justification** | This is an architectural constraint, not a behavioral test. The single code path is enforced by design — both agents call the same script. The automated tests prove the code path works; the architectural verification is a code review check. |

---

## Summary Matrix

| AC | Automated Test Class(es) | Human Verification | Phase(s) |
|----|--------------------------|-------------------|----------|
| AC1.1 | -- | Skill invocation: commit mode | 5, 6 |
| AC1.2 | -- | Skill invocation: branch mode | 5, 6 |
| AC1.3 | `TestParseUnifiedDiff`, `TestAssembleDiffContext` | -- | 1 |
| AC1.4 | `TestReviewFileDiffMode` | Skill invocation: non-git dir | 5, 7 |
| AC1.5 | -- | Skill invocation: merge commit | 5 |
| AC2.1 | `TestReviewFileDiffMode` | Skill invocation: dirty file | 1, 5, 6 |
| AC2.2 | `TestReviewFileDiffMode`, existing tests | Skill invocation: clean file | 1, 5, 6 |
| AC2.3 | -- | Skill invocation: untracked file | 5, 7 |
| AC3.1 | -- | Skill invocation: directory | 5, 6 |
| AC3.2 | -- | Skill invocation: mixed directory | 6 |
| AC4.1 | `TestSplitIntoChunks`, `TestChunkedReview` | -- | 2 |
| AC4.2 | `TestSplitIntoChunks` | -- | 2 |
| AC4.3 | `TestDeduplicateFindings` | -- | 2 |
| AC4.4 | `TestChunkedReview` | -- | 2 |
| AC4.5 | `TestSplitIntoChunks` | -- | 2 |
| AC5.1 | `TestParseUnifiedDiff`, `TestExtractFileHeader`, `TestAssembleDiffContext` | -- | 1 |
| AC5.2 | `TestAssembleDiffContext` | -- | 1 |
| AC5.3 | `TestDetectCoverage`, `TestBuildDiffUserMessage` | -- | 1 |
| AC5.4 | `TestBuildDiffUserMessage`, `TestReviewFileDiffMode` | -- | 1 |
| AC6.1 | `TestMainCLI`, `TestReviewFileDiffMode`, all existing tests | -- | 1, 7 |
| AC6.2 | Full suite run (`pytest tests/`), corpus tests | -- | 1, 2, 7 |
| AC6.3 | `TestBuildDiffUserMessage` (partial) | `git diff main -- prompts/` | All |
| AC7.1 | `TestChunkedReview` | `/test-hammer <large-file>` invocation | 2, 6 |
| AC7.2 | `TestChunkedReview` (implicit) | Code review of single code path | 2, 6 |

---

## Test Classes Summary

All new test classes reside in `tests/test_review_file.py`:

| Test Class | Phase | Tests For | Type |
|------------|-------|-----------|------|
| `TestParseUnifiedDiff` | 1 | Unified diff parsing, hunk range extraction | Unit |
| `TestExtractFileHeader` | 1 | File header extraction across languages | Unit |
| `TestAssembleDiffContext` | 1 | Context expansion, hunk merging, line numbering | Unit |
| `TestDetectCoverage` | 1 | Coverage threshold detection | Unit |
| `TestBuildDiffUserMessage` | 1 | Runtime instruction injection, message framing | Unit |
| `TestReviewFileDiffMode` | 1, 7 | End-to-end diff mode through `review_file()`, edge cases (binary, deleted, invalid ref) | Integration (mocked) |
| `TestSplitIntoChunks` | 2 | Chunk splitting, boundary detection, header prepending | Unit |
| `TestDeduplicateFindings` | 2 | Finding deduplication across chunks | Unit |
| `TestChunkedReview` | 2 | Full chunking pipeline through `review_file()` | Integration (mocked) |

Existing test classes (`TestMainCLI`, `TestPrependLineNumbers`, `TestExtractCategoryPrompt`, `TestParseFindings`, `TestDetectLanguage`, `TestReviewFile`, `TestRetryBehavior`, `TestParseRetryAfter`) receive additional tests in `TestMainCLI` only (Phase 1, Task 2). All others must pass unmodified.

---

## Human Verification Checklist

The following criteria require manual testing because they involve skill-layer orchestration (markdown templates interpreted by Claude Code) with no Python test harness:

- [ ] AC1.1: `/review-hammer this commit` -- commit mode, diff review
- [ ] AC1.2: `/review-hammer this branch` -- branch mode, merge-base resolution
- [ ] AC1.4: `/review-hammer this commit` in non-git directory -- error message
- [ ] AC1.5: `/review-hammer this commit` on merge commit -- merge diff
- [ ] AC2.1: `/review-hammer <dirty-file>` -- dirty detection, diff dispatch
- [ ] AC2.2: `/review-hammer <clean-file>` -- clean detection, full-file dispatch
- [ ] AC2.3: `/review-hammer <untracked-file>` -- fallback to full-file
- [ ] AC3.1: `/review-hammer <directory>` -- per-file classification
- [ ] AC3.2: `/review-hammer <directory>` with mixed files -- unified report
- [ ] AC6.3: `git diff main -- prompts/` shows zero changes
- [ ] AC7.1: `/test-hammer <large-file>` -- chunking completes
