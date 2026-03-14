# Human Test Plan — test-hammer

Generated: 2026-03-13

## Prerequisites
- Environment: macOS with `uv` installed, `REVIEWERS_API_KEY` set to a valid API key
- Unit tests passing: `.venv/bin/pytest tests/test_review_file.py -v` (all green)
- Calibration tests passing: `uv run scripts/test_corpus.py` (all cases pass)
- Claude Code with the review-hammer plugin installed and loaded

## Phase 1: Single File Test Suggestion (AC1.1)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `/test-hammer scripts/review_file.py` | Skill begins execution, dispatches test-suggester agent |
| 2 | Wait for the report to complete | A severity-ranked markdown report is presented |
| 3 | Count the number of test suggestions in the report | At most 3 suggestions appear for the file |
| 4 | Check suggestion ordering | Suggestions are sorted by severity: Critical before High before Medium |
| 5 | For each suggestion, verify it includes: file path, line numbers, confidence score, description, impact statement, and code context | All fields are present and populated |
| 6 | Spot-check one line number reference using the Read tool against `scripts/review_file.py` | The referenced lines match actual code in the file |

## Phase 2: Directory Enumeration and Pairing (AC1.2, AC1.4)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `/test-hammer scripts/` | Skill enumerates all production files in `scripts/` |
| 2 | Check the report header for "Files analyzed: N" | Count matches the actual number of production Python files in `scripts/` (verify with `ls scripts/*.py`) |
| 3 | Check for test file pairing information | Report indicates which files have companion tests and which do not |
| 4 | Verify suggestions span multiple files | Report contains suggestions for more than one file |
| 5 | Check for duplicate suggestions | No two suggestions across different files describe the identical gap type with identical wording |
| 6 | Spot-check 2-3 line number references from the report | Referenced lines match actual source code |
| 7 | Check that no suggestion appears in the DO NOT SUGGEST categories for the file's language | No trivial suggestions (e.g., testing getters/setters, testing default implementations) |

## Phase 3: Review-Hammer Integration (AC2.1, AC2.2)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `/review-hammer scripts/` on a directory with 2-3 production files | Both file-reviewer and test-suggester agents are dispatched |
| 2 | Observe the agent dispatch output | Both agent types appear in the dispatch log |
| 3 | Monitor concurrent agent count | Total concurrent agents never exceeds the `REVIEWERS_MAX_CONCURRENT` value (default 2) |
| 4 | Wait for the final report | Report completes successfully |
| 5 | Check the final report structure | A distinct "Test Suggestions" section appears separately from bug findings |
| 6 | Check the summary header | Summary includes both bug finding count and test suggestion count |

## Phase 4: Concurrency Limit Enforcement (AC2.4)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Set `REVIEWERS_MAX_CONCURRENT=1` in the environment | Variable is set |
| 2 | Run `/review-hammer scripts/` on a directory with 3+ production files | Agents begin dispatching |
| 3 | Observe the dispatch pattern | Agents are dispatched one at a time — file-reviewer and test-suggester interleaved, never more than 1 concurrent |
| 4 | Verify all agents complete | Final report includes results from all files |

## Phase 5: Opus Judge Cap Enforcement (AC5.2 manual portion)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `/test-hammer` on a file with significant complexity (e.g., `scripts/review_file.py` which has ~300 lines with multiple code paths) | Test-suggester runs and produces suggestions |
| 2 | Count the number of suggestions in the final report for that file | At most 3 suggestions appear, even if the underlying LLM may have generated more |

## Traceability

| Acceptance Criterion | Automated Test | Manual Step |
|----------------------|----------------|-------------|
| AC1.1 | -- | Phase 1 |
| AC1.2 | -- | Phase 2 |
| AC1.3 | `TestTestContext::test_test_context_included_in_user_message` | -- |
| AC1.4 | -- | Phase 2 (steps 5-7) |
| AC1.5 | `TestTestContext::test_no_test_context_with_test_suggestions_category` | -- |
| AC2.1 | -- | Phase 3 |
| AC2.2 | -- | Phase 3 (steps 5-6) |
| AC2.3 | `TestExtractCategoryPrompt::test_extract_each_category` | -- |
| AC2.4 | -- | Phase 4 |
| AC3.1 | `TestExtractCategoryPrompt` + `TestTestContext` | -- |
| AC3.2 | `TestExtractCategoryPrompt::test_extract_each_category` | -- |
| AC3.3 | Calibration: `adversarial_test_suggestions_trivial_newtype.rs` | -- |
| AC3.4 | `TestExtractCategoryPrompt::test_extract_each_category` + grep | -- |
| AC4.1 | Calibration: `clean_test_suggestions_well_tested.rs` | -- |
| AC4.2 | Calibration: `bug_test_suggestions_untested_parser.rs` | -- |
| AC4.3 | Calibration: `adversarial_test_suggestions_trivial_newtype.rs` | -- |
| AC5.1 | Static: hook grep pattern | -- |
| AC5.2 | `TestExtractCategoryPrompt::test_test_suggestions_category_contains_cap_language` | Phase 5 |
| AC5.3 | `TestTestContext::test_test_context_file_truncation` | -- |
