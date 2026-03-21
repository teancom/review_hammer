# Smart Input Implementation Plan — Phase 3

**Goal:** Determine the actual line limit for the LLM API and set the chunk threshold.

**Architecture:** Empirical calibration of the `CHUNK_THRESHOLD` constant using progressively larger files against the Z.AI GLM-5 API. The constant is updated in `scripts/review_file.py` once the practical limit is known.

**Tech Stack:** Python 3.10+, Z.AI GLM-5 API (200K token context window)

**Scope:** 7 phases from original design (phase 3 of 7)

**Codebase verified:** 2026-03-20

**External dependency research:** GLM-5 has a 200K token context window (~10,000-20,000 lines of code theoretically). However, the design references a 2900-line file as problematic, suggesting practical quality limits are much lower than the theoretical token maximum. Calibration must be empirical.

---

## Acceptance Criteria Coverage

This phase is an **infrastructure/calibration phase**. It operationally verifies:

**Verifies: None** — this phase sets constants based on empirical observation. Functional ACs are covered by Phases 1 and 2.

---

<!-- START_TASK_1 -->
### Task 1: Create calibration test script

**Files:**
- Create: `scripts/calibrate_chunk_threshold.py`

**Implementation:**

Create a standalone calibration script that sends progressively larger files to the API and records which sizes succeed, which degrade in quality, and which fail. This is a manual/semi-automated tool, not part of the test suite.

The script should:
1. Generate synthetic Python files of increasing line counts: 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000 lines
2. Each synthetic file should be realistic code (not just `pass` repeated) — use repeating function definitions with docstrings and logic
3. Send each file to the API via `review_file.py` (subprocess call, same pattern as `test_corpus.py`)
4. Record: success/failure, response time, whether findings are coherent
5. Print a summary table showing size → outcome

Use PEP 723 inline dependencies (same pattern as `test_corpus.py`). Requires `REVIEWERS_API_KEY` env var.

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Calibration script for determining API input size limits.

Sends progressively larger files to the review API and reports outcomes.
Used to set CHUNK_THRESHOLD in review_file.py.

Usage:
    REVIEWERS_API_KEY=... uv run scripts/calibrate_chunk_threshold.py
"""
```

**Verification:**
Run: `REVIEWERS_API_KEY=... uv run scripts/calibrate_chunk_threshold.py`
Expected: Prints a table showing success/failure per file size

**Commit:** `feat: add API calibration script for chunk threshold`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Run calibration and update CHUNK_THRESHOLD

**Files:**
- Modify: `scripts/review_file.py` (update `CHUNK_THRESHOLD` constant)

**Implementation:**

1. Run the calibration script from Task 1 against the live API
2. Identify the largest file size that consistently produces good-quality results
3. Set `CHUNK_THRESHOLD` to ~66% of that limit (leaving headroom for prompt template + system message overhead)
4. Update the `--context-lines` default if needed (currently 3; may need adjustment based on how much context fits)

For example, if 2000 lines is the reliable limit:
- `CHUNK_THRESHOLD = 1300` (66% of 2000)
- `--context-lines` default stays at 3

Update the constant and its comment in `scripts/review_file.py`:

```python
# Chunk threshold in lines — content exceeding this is split into chunks.
# Calibrated at ~66% of empirically determined API quality limit (~XXXX lines).
# See scripts/calibrate_chunk_threshold.py for calibration methodology.
CHUNK_THRESHOLD = XXXX  # Set based on calibration results
```

**Verification:**

Run: `uv run scripts/review_file.py <2900-line-file> --category logic-errors`
Expected: File is chunked and reviewed successfully via chunking, producing valid findings

Run: `.venv/bin/pytest tests/ -x`
Expected: All existing tests pass (threshold change doesn't affect tests that use explicit values)

**Commit:** `feat: calibrate CHUNK_THRESHOLD based on empirical API testing`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Verify calibration with real-world file

**Files:**
- No new files — operational verification only

**Implementation:**

Test with a real large file (the 2900-line file referenced in the design, or another large file from a real codebase) to confirm:
1. Chunking activates at the right threshold
2. Each chunk review succeeds
3. Findings are coherent and reference correct line numbers
4. Deduplication removes findings from overlapping regions
5. Total review completes within a reasonable time

**Verification:**

Run the review against a real large file:
```bash
REVIEWERS_API_KEY=... uv run scripts/review_file.py <large-file> --category logic-errors
```
Expected: Successful review with chunked output and valid line-numbered findings

Run: `ruff check scripts/calibrate_chunk_threshold.py`
Expected: No lint errors

Run: `ruff format --check scripts/calibrate_chunk_threshold.py`
Expected: No formatting issues

**Commit:** No commit needed — verification step.
<!-- END_TASK_3 -->
