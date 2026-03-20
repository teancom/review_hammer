# Smart Input Implementation Plan — Phase 2

**Goal:** Oversized inputs (diff or full file) are automatically split into chunks, reviewed separately, and findings merged transparently.

**Architecture:** Add chunking to `scripts/review_file.py` that detects when content exceeds a line-count threshold, splits at natural boundaries (blank lines between functions), prepends file header to each chunk, makes per-chunk API calls reusing the existing retry loop, and deduplicates findings from overlapping regions.

**Tech Stack:** Python 3.10+, OpenAI SDK (existing)

**Scope:** 7 phases from original design (phase 2 of 7)

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### smart-input.AC4: Auto-chunking
- **smart-input.AC4.1 Success:** File exceeding chunk threshold is split, reviewed per-chunk, and findings merged into a single array
- **smart-input.AC4.2 Success:** Chunks include file header (imports/definitions) for context
- **smart-input.AC4.3 Success:** Overlapping chunk regions produce deduplicated findings
- **smart-input.AC4.4 Success:** Chunking works for both diff mode and full-file mode
- **smart-input.AC4.5 Edge:** File just under the threshold is NOT chunked (no unnecessary splitting)

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Chunk splitter function

**Verifies:** smart-input.AC4.1, smart-input.AC4.2, smart-input.AC4.5

**Files:**
- Modify: `scripts/review_file.py` (add new function and constants)

**Implementation:**

Add a `CHUNK_THRESHOLD` constant (placeholder value of 500 lines — will be calibrated in Phase 3) and a `split_into_chunks()` function.

```python
# Chunk threshold in lines — content exceeding this is split into chunks.
# Set to ~66% of empirically determined API input limit. Calibrated in Phase 3.
CHUNK_THRESHOLD = 500

# Overlap lines between adjacent chunks (ensures findings near boundaries aren't lost)
CHUNK_OVERLAP = 20


def split_into_chunks(
    content: str,
    file_header: str,
    chunk_threshold: int = CHUNK_THRESHOLD,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    Split content into overlapping chunks at natural boundaries.

    Each chunk gets the file header prepended for LLM context.
    Splits preferentially at blank lines between functions/classes.

    Args:
        content: The content to split (may be numbered lines from diff or full file)
        file_header: File header to prepend to each chunk
        chunk_threshold: Line count above which splitting occurs
        chunk_overlap: Number of overlapping lines between adjacent chunks

    Returns:
        List of chunk strings. If content is under threshold, returns [content]
        with file header prepended. Each chunk has file header prepended.
    """
```

The function should:
1. Count lines in `content`. If ≤ `chunk_threshold`, return `[file_header + "\n\n" + content]` (no splitting needed)
2. Calculate target chunk size: `chunk_threshold - len(file_header.splitlines())` (reserve space for header)
3. Split `content` into lines
4. Walk lines to find split points: prefer blank lines (natural function/class boundaries). Use a sliding window: from the target split point, search ±20 lines for a blank line. If found, split there. If not, split at exact target point.
5. Each chunk: `file_header + "\n\n" + chunk_lines` with `chunk_overlap` lines of overlap with the previous chunk
6. Return list of chunks

**Testing:**
Tests must verify each AC listed above:
- smart-input.AC4.1: Content of 1000 lines with threshold 500 produces 2+ chunks
- smart-input.AC4.2: Each chunk starts with the file header
- smart-input.AC4.5: Content of 499 lines with threshold 500 returns single chunk (no split)
- Chunks overlap by `CHUNK_OVERLAP` lines
- Split prefers blank lines between functions over arbitrary mid-code splits
- Edge: content exactly at threshold — not chunked

Create a new test class `TestSplitIntoChunks` in `tests/test_review_file.py`. Import `split_into_chunks`, `CHUNK_THRESHOLD`, and `CHUNK_OVERLAP` from `review_file`.

**IMPORTANT:** Tests MUST use `CHUNK_THRESHOLD` and `CHUNK_OVERLAP` constants, not hard-coded numeric values, so that Phase 3 threshold calibration does not break tests. For example, use `CHUNK_THRESHOLD + 500` for "exceeds threshold" cases, not a literal like `1000`.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py::TestSplitIntoChunks -x -v`
Expected: All tests pass

**Commit:** `feat: add chunk splitter with natural boundary detection`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Finding deduplicator function

**Verifies:** smart-input.AC4.3

**Files:**
- Modify: `scripts/review_file.py` (add new function after `split_into_chunks`)

**Implementation:**

Add a `deduplicate_findings()` function that merges finding lists from multiple chunks, removing duplicates that occur in overlapping regions.

```python
def deduplicate_findings(all_findings: list[list]) -> list:
    """
    Merge and deduplicate findings from multiple chunk reviews.

    Two findings are considered duplicates if they have the same category
    and overlapping line ranges (within 2 lines tolerance).

    Args:
        all_findings: List of finding lists, one per chunk

    Returns:
        Single deduplicated list of findings
    """
```

Deduplication logic:
1. Flatten all finding lists into one
2. Sort by line number (the `lines` field, which is a string like `"42-45"` or `"42"`)
3. For each pair of findings with the same `category`: if their line ranges overlap or are within 2 lines of each other, keep the one with higher severity (or the first if equal)
4. Return the deduplicated list

Severity ordering for comparison: `"critical" > "high" > "medium"`

**Testing:**
Tests must verify:
- smart-input.AC4.3: Two identical findings (same category, same lines) from different chunks → deduplicated to one
- smart-input.AC4.3: Two findings with same category and lines within 2-line tolerance → deduplicated to the higher-severity one
- Findings with different categories but same lines → both kept (not duplicates)
- Findings with same category but distant lines → both kept
- Single chunk input → returned unchanged
- Empty input → returns empty list

Create a new test class `TestDeduplicateFindings` in `tests/test_review_file.py`. Import `deduplicate_findings` from `review_file`.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py::TestDeduplicateFindings -x -v`
Expected: All tests pass

**Commit:** `feat: add finding deduplicator for chunk overlap regions`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Wire chunking into `review_file()` with per-chunk API calls

**Verifies:** smart-input.AC4.1, smart-input.AC4.4

**Files:**
- Modify: `scripts/review_file.py:262-438` (the `review_file()` function)

**Implementation:**

Refactor `review_file()` to support chunking. After building `user_message` (both diff mode and full-file mode), check if chunking is needed:

1. Extract a helper function `_call_api()` that encapsulates the existing client creation, retry loop, and response parsing (lines 357-438). This function takes `system_prompt` and `user_message` and returns a findings list.

   **IMPORTANT: After extracting `_call_api()` but before adding any chunking logic, run `.venv/bin/pytest tests/ -x` to verify the extraction is a pure refactor with no behavior change.** This catches subtle bugs in the extraction before they are masked by chunking changes.

2. After building `user_message`, check line count:
   ```python
   message_lines = user_message.count("\n") + 1
   if message_lines > CHUNK_THRESHOLD:
       # Extract file header for chunk context
       header = extract_file_header(source)
       chunks = split_into_chunks(user_message, header)

       all_findings = []
       for i, chunk in enumerate(chunks):
           print(
               f"[review] CHUNK {i+1}/{len(chunks)} {category} for {file_path}",
               file=sys.stderr,
           )
           chunk_findings = _call_api(client, system_prompt, chunk, ...)
           all_findings.append(chunk_findings)

       findings = deduplicate_findings(all_findings)
   else:
       findings = _call_api(client, system_prompt, user_message, ...)
   ```

3. The `_call_api()` helper reuses the existing retry loop verbatim — just extracted into a function.

This approach ensures chunking works for both diff mode (AC4.4 — diff content that's still large after assembly) and full-file mode (AC4.4 — large files reviewed without `--diff-base`).

**Testing:**
Tests must verify:
- smart-input.AC4.1: A very large file triggers chunking, produces multiple API calls, and returns merged findings
- smart-input.AC4.4 (diff mode): Large diff content triggers chunking
- smart-input.AC4.4 (full-file mode): Large file without `--diff-base` triggers chunking
- Chunking produces correct observability logs (`[review] CHUNK 1/3...`)
- Non-chunked file still works via `_call_api()` (no regression)

Add tests to a new class `TestChunkedReview` in `tests/test_review_file.py`. Mock `subprocess.run` for diff mode, mock `OpenAI` for API calls. Use `temp_file_with_content` fixture to create files exceeding `CHUNK_THRESHOLD`.

**Verification:**
Run: `.venv/bin/pytest tests/ -x -v`
Expected: All tests pass including new chunking tests AND all existing tests

**Commit:** `feat: wire chunking into review_file() with per-chunk API calls and deduplication`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Full test suite and lint verification

**Verifies:** smart-input.AC4.1, smart-input.AC4.2, smart-input.AC4.3, smart-input.AC4.4, smart-input.AC4.5

**Files:**
- No new files — verification only

**Verification:**

Run: `.venv/bin/pytest tests/ -x -v`
Expected: All tests pass

Run: `ruff check scripts/review_file.py tests/test_review_file.py`
Expected: No lint errors

Run: `ruff format --check scripts/review_file.py tests/test_review_file.py`
Expected: No formatting issues

**Commit:** No commit needed — verification step. Fix any issues and amend previous commit if needed.
<!-- END_TASK_4 -->
