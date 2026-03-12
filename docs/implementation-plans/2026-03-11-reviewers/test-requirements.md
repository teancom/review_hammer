# Test Requirements: Review Hammer

Maps each acceptance criterion to specific tests, categorized as automated (pytest unit tests) or human verification (operational/manual checks).

## Summary

| AC Group | Total Criteria | Automated | Human Verification |
|----------|---------------|-----------|-------------------|
| AC1 | 4 | 0 | 4 |
| AC2 | 4 | 3 | 1 |
| AC3 | 3 | 2 | 1 |
| AC4 | 3 | 0 | 3 |
| AC5 | 4 | 0 | 4 |
| AC6 | 3 | 1 | 2 |
| AC7 | 2 | 0 | 2 |
| **Total** | **23** | **6** | **17** |

---

## AC1: Skill accepts any code target

### reviewers.AC1.1 — Skill accepts a single file path, reviews it, returns findings

- **Verification type:** Human
- **Why not automated:** This criterion exercises the full pipeline: skill invocation, agent dispatch, API calls, and Opus judge pass. It requires a running Claude Code session with the plugin installed and a live LLM backend.
- **Verification approach:** Invoke `/fleet-review tests/fixtures/sample.py` in a Claude Code session. Confirm the skill runs the file-reviewer agent, calls `review_file.py`, and produces a formatted report.

### reviewers.AC1.2 — Skill accepts a directory, enumerates files, reviews each, returns consolidated findings

- **Verification type:** Human
- **Why not automated:** Requires live skill execution with agent dispatch across multiple files.
- **Verification approach:** Invoke `/fleet-review tests/fixtures/` (with multiple fixture files in different languages). Confirm the skill enumerates all supported files, dispatches agents, and returns consolidated findings.

### reviewers.AC1.3 — Skill given a non-existent path reports clear error

- **Verification type:** Human
- **Why not automated:** Error handling happens inside the skill's orchestration logic (Opus reading markdown instructions), not in a testable function.
- **Verification approach:** Invoke `/fleet-review /nonexistent/path/here`. Confirm the skill reports a clear error message and does not dispatch any agents.

### reviewers.AC1.4 — Skill given a directory with no supported-language files reports "nothing to review"

- **Verification type:** Human
- **Why not automated:** Skill-level orchestration logic.
- **Verification approach:** Create a temp directory containing only `.txt` and `.md` files. Invoke `/fleet-review` on it. Confirm the skill reports "nothing to review" or equivalent.

---

## AC2: Python script produces correct findings

### reviewers.AC2.1 — Script sends line-numbered code to API and returns valid JSON with correct line numbers

- **Verification type:** Human (operational)
- **Why not automated:** Requires a live API call to an OpenAI-compatible endpoint.
- **Verification approach:** Run `review_file.py` against `tests/fixtures/sample.py` with a valid `REVIEWERS_API_KEY`. Verify stdout is valid JSON. Verify any reported line numbers correspond to actual lines in the source file.

### reviewers.AC2.2 — Script reads prompt template for correct language and extracts correct category section

- **Verification type:** Automated (unit test)
- **Test file:** `tests/test_review_file.py`
- **Test type:** Unit
- **Tests:**
  - `test_extract_category_prompt_returns_preamble_and_section` — Call `extract_category_prompt("prompts/generic.md", "logic-errors")`. Verify result contains the preamble ("Output format") and the logic-errors section content. Verify it does NOT contain other category sections.
  - `test_extract_category_prompt_all_production_categories` — For each of the 6 production categories, verify a non-empty result.
  - `test_extract_category_prompt_all_test_categories` — For each of the 5 test categories, verify a non-empty result.
  - `test_extract_category_prompt_invalid_category_raises` — Verify `ValueError` for `"nonexistent-category"`.

### reviewers.AC2.3 — Script returns clear error when API key is missing or invalid

- **Verification type:** Automated (unit test)
- **Test file:** `tests/test_review_file.py`
- **Test type:** Unit
- **Tests:**
  - `test_cli_exits_with_error_when_api_key_missing` — Run the script via subprocess with no `REVIEWERS_API_KEY`. Verify exit code 1 and stderr error message.

### reviewers.AC2.4 — Script handles API returning empty/malformed response without crashing

- **Verification type:** Automated (unit test)
- **Test file:** `tests/test_review_file.py`
- **Test type:** Unit
- **Tests:**
  - `test_parse_findings_valid_json_array` — Valid JSON array returns parsed list.
  - `test_parse_findings_empty_string` — Empty string returns `[]`.
  - `test_parse_findings_malformed_json` — Invalid JSON returns `[]` without raising.
  - `test_parse_findings_json_in_markdown_fences` — JSON in triple-backtick fences is extracted and parsed.
  - `test_parse_findings_json_object_not_array` — JSON object (not array) returns `[]`.

---

## AC3: Language-aware prompts

### reviewers.AC3.1 — Each of 12 language prompt files contains language-specific specialist sections with appropriate DO NOT REPORT constraints

- **Verification type:** Human
- **Why not automated:** Content quality of DO NOT REPORT constraints requires human judgment of domain-specific accuracy.
- **Verification approach:** Review each of the 12 prompt files. Verify: (1) 11 H2 sections (6 production + 5 test), (2) each section has a DO NOT REPORT block, (3) constraints are language-appropriate.

### reviewers.AC3.2 — File extension correctly maps to language

- **Verification type:** Automated (unit test)
- **Test file:** `tests/test_review_file.py`
- **Test type:** Unit
- **Tests:**
  - `test_detect_language_known_extensions` — Each extension maps to correct language key.
  - `test_detect_language_multi_extension_consistency` — `.cpp`/`.cc`/`.cxx`/`.hpp`/`.hxx` all map to `"cpp"`, etc.

### reviewers.AC3.3 — Unknown file extension falls back to generic.md

- **Verification type:** Automated (unit test)
- **Test file:** `tests/test_review_file.py`
- **Test type:** Unit
- **Tests:**
  - `test_detect_language_unknown_extensions_return_generic` — `.xyz`, `.rb`, `.lua`, `.php`, `.pl` all return `"generic"`.

---

## AC4: Collector agent dispatches specialists correctly

### reviewers.AC4.1 — Agent detects production file and runs 6 production specialist categories

- **Verification type:** Human
- **Why not automated:** Agent behavior is LLM-driven (Haiku interpreting markdown instructions).
- **Verification approach:** Dispatch file-reviewer agent with a production file. Verify `"is_test": false` and `"categories_run"` contains 6 production categories.

### reviewers.AC4.2 — Agent detects test file and runs 5 test specialist categories

- **Verification type:** Human
- **Why not automated:** Agent behavior is LLM-driven.
- **Verification approach:** Dispatch file-reviewer agent with a test file. Verify `"is_test": true` and `"categories_run"` contains 5 test categories.

### reviewers.AC4.3 — Agent handles specialist returning "No findings" without error

- **Verification type:** Human
- **Why not automated:** Agent behavior is LLM-driven.
- **Verification approach:** Dispatch agent with a trivially simple file. Verify completion with `"findings": []` and no errors.

---

## AC5: Opus judge pass produces high-precision output

### reviewers.AC5.1 — Duplicate findings from multiple specialists are merged into one

- **Verification type:** Human
- **Why not automated:** Deduplication is Opus judgment, not algorithmic code.
- **Verification approach:** Run `/fleet-review` on a file with an issue spanning categories. Verify merged finding with `"flagged_by"` listing multiple categories.

### reviewers.AC5.2 — High-severity findings have line numbers verified against actual code

- **Verification type:** Human
- **Why not automated:** Line verification is Opus using the Read tool.
- **Verification approach:** For every critical/high finding, manually check cited line numbers match described code.

### reviewers.AC5.3 — Systemic patterns across files are grouped rather than listed individually

- **Verification type:** Human
- **Why not automated:** Cross-file pattern detection is Opus judgment.
- **Verification approach:** Run `/fleet-review` on a directory with repeated anti-patterns. Verify "Systemic Patterns" section groups the issue.

### reviewers.AC5.4 — Final report is ranked by severity

- **Verification type:** Human
- **Why not automated:** Report formatting is Opus following skill instructions.
- **Verification approach:** Verify report sections appear in order: Critical, High, Medium.

---

## AC6: Robustness under real-world conditions

### reviewers.AC6.1 — 429 rate limit errors are retried with backoff

- **Verification type:** Automated (unit test) + Human
- **Test file:** `tests/test_review_file.py`
- **Test type:** Unit
- **Tests:**
  - `test_retry_constants_exist` — Verify `MAX_RETRIES == 5`, `INITIAL_BACKOFF == 1.0`, `MAX_BACKOFF == 60.0`.
- **Additional human verification:** Run against unreachable endpoint with `--timeout 5`. Verify retry attempts with increasing backoff in stderr, eventual `[]` output, exit code 2.

### reviewers.AC6.2 — Individual specialist timeout doesn't kill the whole review

- **Verification type:** Human
- **Why not automated:** Requires live agent dispatch with forced timeout.
- **Verification approach:** Force one specialist to timeout. Verify collector agent continues with remaining categories and reports `"failed_categories"`.

### reviewers.AC6.3 — Large repo (100+ files) prompts user for confirmation before proceeding

- **Verification type:** Human
- **Why not automated:** Requires live Claude Code session with skill invocation.
- **Verification approach:** Invoke `/fleet-review` on 100+ file directory. Verify file count, estimated API calls, and options are presented before dispatch.

---

## AC7: Installable plugin

### reviewers.AC7.1 — `claude plugin install teancom/review_hammer` works

- **Verification type:** Human
- **Why not automated:** Requires publishing to GitHub and running `claude plugin install`.
- **Verification approach:** After pushing to `teancom/review_hammer`, run `claude plugin install teancom/review_hammer`. Verify installation succeeds and `/fleet-review` appears in skill list.

### reviewers.AC7.2 — Session-start hook warns when REVIEWERS_API_KEY is not set

- **Verification type:** Human
- **Why not automated:** Session-start hooks fire within Claude Code runtime.
- **Verification approach:** Start session without `REVIEWERS_API_KEY`. Verify warning. Set variable, restart — verify confirmation with configured values.

---

## Automated Test File Summary

All automated tests live in a single file:

| Test File | Phase | Criteria Covered |
|-----------|-------|-----------------|
| `tests/test_review_file.py` | 2, 3, 6 | AC2.2, AC2.3, AC2.4, AC3.2, AC3.3, AC6.1 |

### Test function inventory

```
tests/test_review_file.py
    # AC2.2 - Prompt extraction
    test_extract_category_prompt_returns_preamble_and_section
    test_extract_category_prompt_all_production_categories
    test_extract_category_prompt_all_test_categories
    test_extract_category_prompt_invalid_category_raises

    # AC2.3 - Missing API key
    test_cli_exits_with_error_when_api_key_missing

    # AC2.4 - Response parsing
    test_parse_findings_valid_json_array
    test_parse_findings_empty_string
    test_parse_findings_malformed_json
    test_parse_findings_json_in_markdown_fences
    test_parse_findings_json_object_not_array

    # AC3.2 - Extension mapping
    test_detect_language_known_extensions
    test_detect_language_multi_extension_consistency

    # AC3.3 - Generic fallback
    test_detect_language_unknown_extensions_return_generic

    # AC6.1 - Retry constants
    test_retry_constants_exist
```

### Test fixture

| Fixture File | Purpose |
|-------------|---------|
| `tests/fixtures/sample.py` | Small Python file for operational verification |

---

## What is NOT tested automatically and why

| Category | Reason |
|----------|--------|
| AC1 (skill target handling) | Skill is markdown instructions interpreted by Opus |
| AC4 (agent dispatch) | Agent is markdown instructions interpreted by Haiku |
| AC5 (judge pass quality) | Deduplication, verification, ranking are Opus judgment |
| AC6.2-6.3 (timeout/large repo) | Requires live agent execution |
| AC7 (plugin installation) | Requires GitHub publishing and `claude plugin install` |
| AC3.1 (prompt quality) | Content quality requires human domain review |
