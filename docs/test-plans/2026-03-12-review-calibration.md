# Human Test Plan: Review Calibration

**Generated:** 2026-03-12
**Branch:** review-calibration
**Corpus runner:** `uv run scripts/test_corpus.py`

## Prerequisites

- `REVIEWERS_API_KEY` environment variable set with a valid Z.AI API key
- `REVIEWERS_BASE_URL` set if using a non-default endpoint
- Working `uv` installation
- Repository checked out at commit `09b2dc2` or later on branch `review-calibration`
- Full automated corpus run passing:
  ```bash
  uv run scripts/test_corpus.py
  ```
  Expected: "Summary: 10 passed, 0 failed, 0 errors out of 10 cases", exit code 0

## Phase 1: Structured Failure Output (AC2.4)

Purpose: Verify that failure output includes case path, reason string, and raw findings JSON formatted for human diagnosis.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open `tests/corpus/rust/bug_unwrap_user_input.json` and change `"expect_empty": false` to `"expect_empty": true` | File saved |
| 2 | Run `uv run scripts/test_corpus.py` | Runner executes all cases |
| 3 | Locate the output for `rust/bug_unwrap_user_input.json` | Shows `FAIL` with reason "Clean file returned N unexpected finding(s): [descriptions]" |
| 4 | Scroll to the "Failed/errored cases:" section at the bottom | Line reads `FAIL: rust/bug_unwrap_user_input.json -- Clean file returned ...` |
| 5 | Verify "Raw findings:" block appears below the FAIL line | JSON array of finding objects indented under "Raw findings:", each containing `lines`, `severity`, `category`, `description`, `impact`, `confidence` fields |
| 6 | Confirm the raw JSON is sufficient to understand what the reviewer found | Finding descriptions should reference unwrap calls on user input, not be empty or truncated |
| 7 | Revert `bug_unwrap_user_input.json` to `"expect_empty": false` | File restored to original |

## Phase 2: Adversarial/Clean Pairing (AC4.1)

Purpose: Confirm each adversarial file has a corresponding clean counterpart exercising the same prompt exclusion, and both behave correctly in the same run.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `uv run scripts/test_corpus.py` and capture full output | All cases execute |
| 2 | Find `clean_fire_and_forget_channel` result | PASS -- clean file returned no findings for error-handling |
| 3 | Find `adversarial_let_ignore_result` result | PASS -- found findings in error-handling category |
| 4 | Verify the pairing: both target error-handling exclusion (fire-and-forget channel sends). Open both `.json` files and confirm the adversarial description references the same pattern as the clean counterpart | Descriptions reference the same exclusion |
| 5 | Find `clean_mta_com_send_sync` result | PASS -- clean file returned no findings for race-conditions |
| 6 | Find `adversarial_unsafe_send_sync` result | PASS -- found findings in race-conditions category |
| 7 | Verify the pairing: both target race-conditions exclusion (MTA COM Send+Sync) | Descriptions reference the same exclusion pattern |
| 8 | Find `clean_repr_transparent` result | PASS -- clean file returned no findings for brittle-tests |
| 9 | Find `adversarial_private_struct_construction` result | PASS -- found findings in brittle-tests category |
| 10 | Verify the pairing: both target brittle-tests exclusion (repr-transparent struct construction) | Descriptions reference the same exclusion pattern |

## Phase 3: Semantic Match via Opus Judge (AC4.2)

Purpose: Confirm findings describe the specific planted bug, not unrelated issues.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Run `uv run scripts/test_corpus.py` and save full output: `uv run scripts/test_corpus.py 2>&1 | tee /tmp/corpus_output.txt` | Output saved |
| 2 | For `adversarial_let_ignore_result`: temporarily flip `expect_empty` to `true` to force a FAIL with raw findings JSON, capture output, then revert | Raw findings JSON captured |
| 3 | Feed the adversarial source file and findings to Claude Code. Ask: "Do these findings describe the specific bug of silently discarding I/O errors via `let _ = file.write()`, or are they generic style complaints?" | Findings should specifically mention discarded write errors / silent I/O failure |
| 4 | Repeat for `adversarial_unsafe_send_sync`: findings should describe unsafe Send+Sync on a non-COM type with raw pointers and no synchronization | Findings reference the specific data race risk from unsynchronized raw pointer sharing |
| 5 | Repeat for `adversarial_private_struct_construction`: findings should describe tests bypassing constructor invariants by directly constructing structs with private fields | Findings reference private field access or constructor bypass. This case is the highest risk for semantic mismatch. |

## Phase 4: Timeout Handling (AC5.2)

Purpose: Verify the runner handles review timeouts gracefully without crashing or hanging.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Open `scripts/test_corpus.py` and change `REVIEW_TIMEOUT = 180` to `REVIEW_TIMEOUT = 1` | File saved |
| 2 | Run `uv run scripts/test_corpus.py` | Runner begins executing cases |
| 3 | Observe that timed-out cases report `ERROR: Review timed out after 1s` | ERROR message includes timeout duration |
| 4 | Confirm the runner continues to the next case after a timeout (does not crash or hang) | Subsequent cases are attempted |
| 5 | Check the summary line | Timeouts counted as errors: "N passed, M failed, K errors" where K > 0 |
| 6 | Check exit code: `echo $?` | Exit code is 1 (non-zero due to errors) |
| 7 | Revert `REVIEW_TIMEOUT` to `180` in `scripts/test_corpus.py` | File restored |

## Phase 5: Error Message Clarity (AC1.3 Extended)

Purpose: Verify error messages are clear enough to diagnose problems without reading source code.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Create temp corpus dir: `mkdir -p /tmp/test_corpus && echo '{bad' > /tmp/test_corpus/malformed_test.json && echo 'fn main() {}' > /tmp/test_corpus/malformed_test.rs` | Files created |
| 2 | Run `uv run scripts/test_corpus.py --corpus-dir /tmp/test_corpus` | `ERROR: Malformed JSON:` followed by parse error detail |
| 3 | Replace with missing fields: `echo '{"type":"clean"}' > /tmp/test_corpus/malformed_test.json` | File saved |
| 4 | Run `uv run scripts/test_corpus.py --corpus-dir /tmp/test_corpus` | `ERROR: Missing required fields: category, description, expect_empty, language` |
| 5 | Replace with invalid type: `echo '{"type":"unknown","category":"x","language":"rust","description":"test","expect_empty":true}' > /tmp/test_corpus/malformed_test.json` | File saved |
| 6 | Run `uv run scripts/test_corpus.py --corpus-dir /tmp/test_corpus` | `ERROR: Invalid type: unknown (expected clean, bug, or adversarial)` |
| 7 | Assess: can you diagnose each problem from the error message alone? | All three messages should be self-explanatory |
| 8 | Clean up: `rm -rf /tmp/test_corpus` | Temp directory removed |

## End-to-End: Full Calibration Cycle

1. Ensure no local modifications to corpus files or `test_corpus.py`
2. Run `uv run scripts/test_corpus.py` and record wall-clock time
3. Verify all 10 cases appear in output (4 clean, 2 bug, 3 adversarial, 1 clean placeholder)
4. Verify cases execute sequentially (each Case block appears after the previous one's Result line, with API latency gaps visible)
5. Verify the summary reads "10 passed, 0 failed, 0 errors out of 10 cases"
6. Verify exit code is 0
7. Add a new corpus file pair without modifying `test_corpus.py`: create `tests/corpus/rust/clean_newtest.json` with valid metadata and `tests/corpus/rust/clean_newtest.rs` with trivial clean Rust code
8. Run `uv run scripts/test_corpus.py` again
9. Verify 11 cases now appear, including the new file, confirming AC6.1 (no code changes required)
10. Remove the test files: `rm tests/corpus/rust/clean_newtest.{json,rs}`

## Traceability

| Acceptance Criterion | Automated Test | Manual Step |
|----------------------|----------------|-------------|
| AC1.1 | Corpus runner discovery (every run) | -- |
| AC1.2 | `REQUIRED_METADATA_FIELDS` validation (every run) | -- |
| AC1.3 | `validate_metadata` error paths | Phase 5 (extended clarity check) |
| AC1.4 | `--corpus-dir` with empty directory | -- |
| AC2.1 | Corpus runner main loop (every run) | -- |
| AC2.2 | `apply_gate` with 4 clean corpus files | -- |
| AC2.3 | `apply_gate` with 5 bug/adversarial corpus files | -- |
| AC2.4 | -- | Phase 1 (structured failure output) |
| AC2.5 | Summary line and exit code (every run) | -- |
| AC3.1 | 3 clean pattern files against prompt exclusions | -- |
| AC3.2 | 3 clean files covering distinct exclusions | -- |
| AC3.3 | 2 bug files producing expected-category findings | -- |
| AC3.4 | 3 adversarial files producing expected-category findings | -- |
| AC4.1 | -- | Phase 2 (adversarial/clean pairing) |
| AC4.2 | -- | Phase 3 (Opus judge semantic match) |
| AC5.1 | Sequential `subprocess.run` loop (every run) | -- |
| AC5.2 | -- | Phase 4 (timeout with reduced value) |
| AC6.1 | Glob-based discovery, no hardcoded lists | End-to-End step 7-9 |
