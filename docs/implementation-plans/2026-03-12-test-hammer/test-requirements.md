# Test Requirements — test-hammer

Maps every acceptance criterion (AC1 through AC5) from the test-hammer design plan to either an automated test or a documented human verification procedure.

## Legend

| Column | Meaning |
|--------|---------|
| **AC** | Acceptance criterion identifier |
| **Description** | What the criterion requires |
| **Test Type** | `unit` (pytest, mocked), `calibration` (real API via test_corpus.py), `e2e` (full skill invocation), or `human` |
| **Test File / Approach** | Path for automated tests, or verification approach for human tests |
| **Phase** | Implementation phase that delivers the criterion |

---

## AC1: Standalone `/test-hammer <path>` skill

| AC | Description | Test Type | Test File / Approach |
|----|-------------|-----------|----------------------|
| AC1.1 | `/test-hammer <file>` analyzes a single production file and returns up to 3 test suggestions in a severity-ranked markdown report | human | **Justification:** The skill orchestrator runs as a Claude Code skill dispatching Haiku agents via the Agent tool. There is no programmatic interface to invoke a skill and inspect its output. **Verification:** (1) Run `/test-hammer scripts/review_file.py` on a known file. (2) Confirm the report contains at most 3 suggestions per file. (3) Confirm suggestions are sorted by severity (Critical > High > Medium). (4) Confirm the report includes file path, line numbers, confidence, description, impact, and code context sections. |
| AC1.2 | `/test-hammer <directory>` enumerates all production files, pairs each with test files, and produces a combined report | human | **Justification:** Directory enumeration, test file pairing, and multi-agent dispatch are orchestrated entirely within the skill markdown (Glob tool calls, Agent tool dispatches). No unit-testable code path exists. **Verification:** (1) Run `/test-hammer scripts/` on the scripts directory. (2) Confirm the report header shows "Files analyzed: N" matching the actual production file count. (3) Confirm test file pairing is reported (files with tests vs without). (4) Confirm suggestions span multiple files. |
| AC1.3 | Test-suggester agent invokes `review_file.py` with `--test-context` flag and returns JSON findings | unit | `tests/test_review_file.py::TestTestContext::test_test_context_included_in_user_message` -- Verifies that `review_file()` called with `test_context_paths` includes the test file content in the user message sent to the mocked OpenAI API. Also partially covered by calibration (see AC4.1). |
| AC1.4 | Opus judge pass deduplicates, verifies line numbers, and ranks suggestions before final report | human | **Justification:** The judge pass runs as inline Opus reasoning within the skill orchestrator. Its behavior (deduplication, line verification, false positive filtering) is not callable as a function. **Verification:** (1) Run `/test-hammer` on a directory with 3+ production files. (2) Confirm no duplicate suggestions appear across files for identical gap types. (3) Confirm line number references in the report match actual code when spot-checked with Read tool. (4) Confirm no suggestions violate the DO NOT SUGGEST lists. |
| AC1.5 | When no test file exists for a production file, agent is informed "no existing tests found" and suggestions focus on highest-value tests | unit | `tests/test_review_file.py::TestTestContext::test_no_test_context_test_suggestions_category` -- Verifies that when `test_context_paths` is None and category is `"test-suggestions"`, the user message includes the "No existing test files found" notice. Also verified by calibration corpus gap file (AC4.2) which has no companion test file. |

---

## AC2: Review-hammer integration

| AC | Description | Test Type | Test File / Approach |
|----|-------------|-----------|----------------------|
| AC2.1 | `/review-hammer <path>` dispatches both file-reviewer and test-suggester agents from the same batch queue | human | **Justification:** Agent dispatch is orchestrated within the review-hammer skill markdown. The interleaved batch queue is a skill-level instruction, not executable code. **Verification:** (1) Run `/review-hammer` on a small directory (2-3 files). (2) Observe that both file-reviewer and test-suggester agents are dispatched. (3) Confirm the total concurrent agents never exceeds `REVIEWERS_MAX_CONCURRENT`. |
| AC2.2 | Test suggestions appear in the final review-hammer report alongside other findings | human | **Justification:** Report formatting is performed by Opus within the skill orchestrator. **Verification:** (1) Run `/review-hammer` on a directory containing files with test gaps. (2) Confirm the final report contains a "Test Suggestions" section separate from bug findings. (3) Confirm the summary header includes test suggestion count. |
| AC2.3 | `missing-edge-cases` category no longer runs for production files | unit + calibration | `tests/test_review_file.py::TestExtractCategoryPrompt::test_extract_each_category` -- After Phase 5, this test's category list no longer includes `"missing-edge-cases"`. Verified by confirming `grep -c 'missing-edge-cases' prompts/*.md` returns 0 for all files. Additionally, `uv run scripts/test_corpus.py` must still pass all existing corpus cases after removal. |
| AC2.4 | Global `REVIEWERS_MAX_CONCURRENT` limit is respected across both agent types (2 total, not 2 per type) | human | **Justification:** Batch size enforcement is a skill-level instruction controlling how many Agent tool calls are made in parallel. There is no code-level mechanism to test this. **Verification:** (1) Set `REVIEWERS_MAX_CONCURRENT=1`. (2) Run `/review-hammer` on a 3-file directory. (3) Observe that agents are dispatched one at a time (file-reviewer and test-suggester interleaved, never more than 1 concurrent). |

---

## AC3: Language-specific prompt templates

| AC | Description | Test Type | Test File / Approach |
|----|-------------|-----------|----------------------|
| AC3.1 | `prompts/rust.md` contains `## test-suggestions` section with Rust-specific WHAT TO SUGGEST and DO NOT SUGGEST lists | unit | `tests/test_review_file.py::TestExtractCategoryPrompt` -- Existing extraction test confirms the `## test-suggestions` heading is parseable. New test `tests/test_review_file.py::TestTestContext::test_test_context_included_in_user_message` exercises the full path with the Rust prompt. |
| AC3.2 | `prompts/generic.md` contains `## test-suggestions` section as fallback | unit | `tests/test_review_file.py::TestExtractCategoryPrompt` -- Same extraction test validates that `generic.md` can extract the `test-suggestions` category. |
| AC3.3 | DO NOT SUGGEST lists prevent suggestions for language-level trivia (e.g., Rust: testing Default/From/Into for newtypes) | calibration | `uv run scripts/test_corpus.py` -- The adversarial corpus file `tests/corpus/rust/adversarial_test_suggestions_trivial_newtype.rs` is specifically designed to tempt suggestions for derived trait testing. It must produce zero suggestions (AC4.3 exercises this). |
| AC3.4 | All 12 language prompt files contain `## test-suggestions` sections with language-appropriate exclusion lists | unit | `tests/test_review_file.py::TestExtractCategoryPrompt::test_extract_each_category` -- After Phase 6, add `"test-suggestions"` to the category list in this test. The test iterates all categories and verifies extraction succeeds for each language template. Additionally, a simple grep verification: `grep -c '## test-suggestions' prompts/*.md` must show 1 for all 12 files. |

---

## AC4: Calibration corpus

| AC | Description | Test Type | Test File / Approach |
|----|-------------|-----------|----------------------|
| AC4.1 | Clean corpus files (well-tested code) produce zero test suggestions | calibration | `uv run scripts/test_corpus.py` -- Corpus file: `tests/corpus/rust/clean_test_suggestions_well_tested.rs` with companion `_tests.rs` file. Metadata has `expect_empty: true`. The test runner passes `--test-context` with the companion test file and asserts zero findings. |
| AC4.2 | Gap corpus files (untested code with genuine test gaps) produce suggestions targeting the right areas | calibration | `uv run scripts/test_corpus.py` -- Corpus file: `tests/corpus/rust/bug_test_suggestions_untested_parser.rs`. Metadata has `expect_empty: false`. No companion test file (simulates no existing tests). Asserts at least one finding with `category == "test-suggestions"`. |
| AC4.3 | Adversarial corpus files (trivial code that tempts garbage suggestions) produce zero suggestions | calibration | `uv run scripts/test_corpus.py` -- Corpus file: `tests/corpus/rust/adversarial_test_suggestions_trivial_newtype.rs`. Metadata has `expect_empty: true`. Asserts zero findings despite the code having no tests (trivial code should not warrant suggestions). |

---

## AC5: Cross-cutting behaviors

| AC | Description | Test Type | Test File / Approach |
|----|-------------|-----------|----------------------|
| AC5.1 | `hooks/auto-approve-review.sh` auto-approves test-suggester's `review_file.py` invocations with `--test-context` flag (no permission prompts) | unit | Verified by pattern match: `echo 'timeout 180 uv run /path/scripts/review_file.py foo.rs --category test-suggestions --language rust --test-context test_foo.rs' \| grep -q "review_file.py"` returns match. The hook's grep pattern is substring-based and already covers all flag combinations. No new test file needed; this is a static verification during Phase 3 implementation. |
| AC5.2 | Hard cap of 3 suggestions per file is enforced in the prompt template | unit + human | **Automated:** Verify all 12 prompt `## test-suggestions` sections contain the text "Return at most 3 suggestions" -- add an assertion to `tests/test_review_file.py::TestExtractCategoryPrompt` that checks the extracted prompt content includes the cap language. **Human:** The Opus judge pass (Phase 6c) also enforces the cap by discarding suggestions beyond 3 per file. This judge-level enforcement can only be verified by running the skill on a file complex enough to potentially generate >3 suggestions and confirming the report contains at most 3 per file. |
| AC5.3 | Large test files exceeding 500 lines are truncated with a warning before being passed to the LLM | unit | `tests/test_review_file.py::TestTestContext::test_large_test_file_truncated` -- Creates a temp file with 600 lines, calls `review_file()` with it as test context, verifies: (1) user message contains only 500 lines of test content, (2) truncation notice is appended ("... truncated (100 lines omitted)"), (3) warning is printed to stderr. |

---

## Summary

| Category | Total Criteria | Automated (unit) | Automated (calibration) | Human Verification |
|----------|---------------|-------------------|------------------------|--------------------|
| AC1 | 5 | 2 | 0 | 3 |
| AC2 | 4 | 1 | 0 | 3 |
| AC3 | 4 | 3 | 1 | 0 |
| AC4 | 3 | 0 | 3 | 0 |
| AC5 | 3 | 2 | 0 | 1 (partial) |
| **Total** | **19** | **8** | **4** | **7** |

### Automated Test Files

| File | Type | Runner |
|------|------|--------|
| `tests/test_review_file.py::TestTestContext` | unit | `.venv/bin/pytest tests/test_review_file.py::TestTestContext -v` |
| `tests/test_review_file.py::TestExtractCategoryPrompt` | unit | `.venv/bin/pytest tests/test_review_file.py::TestExtractCategoryPrompt -v` |
| `tests/corpus/rust/clean_test_suggestions_well_tested.*` | calibration | `uv run scripts/test_corpus.py` |
| `tests/corpus/rust/bug_test_suggestions_untested_parser.*` | calibration | `uv run scripts/test_corpus.py` |
| `tests/corpus/rust/adversarial_test_suggestions_trivial_newtype.*` | calibration | `uv run scripts/test_corpus.py` |

### Human Verification Criteria

The 7 criteria requiring human verification all share the same root cause: they test **skill orchestration behavior** (agent dispatch patterns, report formatting, judge pass reasoning, batch queue interleaving) that executes as Claude Code skill instructions rather than as callable Python functions. There is no API to programmatically invoke a skill, capture its intermediate state, and assert on outputs.

**Recommended verification approach:** After all 6 phases are implemented, run a manual acceptance pass:

1. `/test-hammer scripts/review_file.py` -- validates AC1.1, AC1.5, AC5.2
2. `/test-hammer scripts/` -- validates AC1.2, AC1.4
3. `/review-hammer scripts/` -- validates AC2.1, AC2.2, AC2.4
4. Set `REVIEWERS_MAX_CONCURRENT=1` and repeat step 3 -- validates AC2.4 specifically
