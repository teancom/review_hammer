# Test Hammer Implementation Plan — Phase 2: Calibration Corpus for Test Suggestions

**Goal:** Build test corpus files and extend `test_corpus.py` to validate prompt accuracy for the `test-suggestions` category.

**Architecture:** Extends the existing calibration corpus pattern in `tests/corpus/rust/` with new paired source+metadata files targeting `test-suggestions`. The `test_corpus.py` runner is extended with an optional `test_file` metadata field to pass `--test-context` to `review_file.py` when present. Three corpus types validate the prompt: clean (well-tested code, expect zero suggestions), gap (untested code, expect suggestions), adversarial (trivial code, expect zero suggestions).

**Tech Stack:** Python 3.10+, uv, Rust (corpus source files)

**Scope:** 6 phases from original design (this is phase 2 of 6)

**Codebase verified:** 2026-03-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### test-hammer.AC4: Calibration corpus
- **test-hammer.AC4.1 Success:** Clean corpus files (well-tested code) produce zero test suggestions
- **test-hammer.AC4.2 Success:** Gap corpus files (untested code with genuine test gaps) produce suggestions targeting the right areas
- **test-hammer.AC4.3 Success:** Adversarial corpus files (trivial code that tempts garbage suggestions) produce zero suggestions

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Extend `test_corpus.py` to support `--test-context`

**Verifies:** None (infrastructure for AC4 validation)

**Files:**
- Modify: `scripts/test_corpus.py`
  - Line 22: Add `test_file` as optional metadata field
  - Lines 72-100: Update `run_review()` to accept and pass `--test-context` flag

**Implementation:**

**Change 1: Update `run_review()` signature and command construction (lines 72-86)**

Add an optional `test_file_path` parameter to `run_review()`:

```python
def run_review(source_path: Path, category: str, language: str, script_dir: Path,
               test_file_path: Path | None = None) -> tuple[list | None, str | None]:
    """Run review_file.py and return (findings, error)."""
    cmd = [
        "uv", "run", str(script_dir / "review_file.py"),
        str(source_path),
        "--category", category,
        "--language", language,
    ]
    if test_file_path is not None:
        cmd.extend(["--test-context", str(test_file_path)])
    # ... rest unchanged
```

**Change 2: Resolve `test_file` from metadata in `main()` (around line 173, after source file discovery)**

After `find_source_file()` returns, check for `test_file` in metadata and resolve it relative to the metadata file's directory:

```python
        # Resolve optional test file for test-context
        test_file_path = None
        if "test_file" in meta:
            test_file_path = meta_path.parent / meta["test_file"]
            if not test_file_path.exists():
                error = f"Test file not found: {meta['test_file']}"
                print(f"  ERROR: {error}")
                results.append({"case": str(rel_path), "status": "error", "reason": error})
                continue
            print(f"  Test context: {meta['test_file']}")
```

**Change 3: Pass `test_file_path` to `run_review()` (line 182)**

```python
        findings, error = run_review(source_path, meta["category"], meta["language"], script_dir,
                                     test_file_path=test_file_path)
```

**Verification:**

Run existing corpus tests to confirm nothing breaks:
```bash
uv run scripts/test_corpus.py
```
Expected: All existing 9 cases still pass (no metadata uses `test_file` yet).

**Note on gating logic:** The existing `apply_gate()` function (lines 103-122 of `test_corpus.py`) is category-agnostic and already handles `test-suggestions` correctly:
- `expect_empty: true` → pass if `len(findings) == 0`
- `expect_empty: false` → pass if any finding has `category == "test-suggestions"`
No changes to `apply_gate()` are needed.

**Commit:** `feat: extend test_corpus.py to pass --test-context from metadata`

<!-- END_TASK_1 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 2-4) -->
<!-- START_TASK_2 -->
### Task 2: Create clean corpus file (well-tested code)

**Verifies:** test-hammer.AC4.1

**Files:**
- Create: `tests/corpus/rust/clean_test_suggestions_well_tested.rs`
- Create: `tests/corpus/rust/clean_test_suggestions_well_tested_tests.rs`
- Create: `tests/corpus/rust/clean_test_suggestions_well_tested.json`

**Implementation:**

This corpus case validates that well-tested code produces zero test suggestions. The source file must have meaningful logic with comprehensive tests covering state transitions, error paths, and boundaries.

**Source file** (`clean_test_suggestions_well_tested.rs`):

Create a Rust module with a small state machine (e.g., a `ConnectionState` enum with `Idle`, `Connecting`, `Connected`, `Disconnected` states and `connect()`, `disconnect()`, `send()` methods that return `Result`). Include error paths (send while disconnected), state transitions, and a boundary condition (max reconnection attempts).

The code should be complex enough that test suggestions would be tempting, but the companion test file should cover everything.

**Test file** (`clean_test_suggestions_well_tested_tests.rs`):

Create a comprehensive test file for the above module that covers:
- Each state transition (Idle→Connecting, Connecting→Connected, Connected→Disconnected, etc.)
- Error paths (send while disconnected, connect while already connected)
- Boundary condition (max reconnection attempts reached)
- Property: disconnect then connect is idempotent in terms of final state

**Metadata** (`clean_test_suggestions_well_tested.json`):

```json
{
    "type": "clean",
    "category": "test-suggestions",
    "language": "rust",
    "description": "State machine with comprehensive test coverage — all transitions, error paths, and boundaries tested",
    "expect_empty": true,
    "test_file": "clean_test_suggestions_well_tested_tests.rs"
}
```

**Verification:**

Run: `uv run scripts/test_corpus.py --corpus-dir tests/corpus/rust/`
Expected: The new clean case passes (zero suggestions returned).

**Commit:** `test: add clean corpus file for test-suggestions calibration`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create gap corpus file (untested code with test gaps)

**Verifies:** test-hammer.AC4.2

**Files:**
- Create: `tests/corpus/rust/bug_test_suggestions_untested_parser.rs`
- Create: `tests/corpus/rust/bug_test_suggestions_untested_parser.json`

**Implementation:**

This corpus case validates that code with genuine test gaps produces suggestions targeting the right areas. The source file should have complex logic with obvious test gaps — no companion test file is provided (simulating no existing tests).

**Source file** (`bug_test_suggestions_untested_parser.rs`):

Create a Rust module implementing a configuration file parser with:
- A `parse_config(input: &str) -> Result<Config, ParseError>` function that handles multiple sections
- Custom error type `ParseError` with variants for different failure modes (missing section, invalid value, duplicate key)
- State transitions: parsing header vs parsing body vs parsing values
- Boundary conditions: empty input, section with no values, deeply nested values
- No `#[cfg(test)]` module — no tests exist at all

The code should have clear test gaps: error paths not tested, state transitions not tested, boundary conditions not tested.

**Metadata** (`bug_test_suggestions_untested_parser.json`):

```json
{
    "type": "bug",
    "category": "test-suggestions",
    "language": "rust",
    "description": "Config parser with error types, state transitions, and boundaries — zero tests exist",
    "expect_empty": false
}
```

Note: No `test_file` field — this simulates the "no existing tests" case. The LLM should be told "no existing tests found" and suggest high-value tests.

**Verification:**

Run: `uv run scripts/test_corpus.py --corpus-dir tests/corpus/rust/`
Expected: The gap case passes (suggestions returned with category `test-suggestions`).

**Commit:** `test: add gap corpus file for test-suggestions calibration`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create adversarial corpus file (trivial code, expect zero suggestions)

**Verifies:** test-hammer.AC4.3

**Files:**
- Create: `tests/corpus/rust/adversarial_test_suggestions_trivial_newtype.rs`
- Create: `tests/corpus/rust/adversarial_test_suggestions_trivial_newtype.json`

**Implementation:**

This corpus case validates that trivial code resists garbage suggestions. The source file must be the kind of code that tempts LLMs into suggesting useless tests (testing derived traits, language semantics, trivial accessors).

**Source file** (`adversarial_test_suggestions_trivial_newtype.rs`):

Create a Rust file with:
- A newtype wrapper: `struct UserId(u64)` with `#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]`
- A `From<u64>` impl and `Display` impl
- A second newtype: `struct Email(String)` with derived traits and a trivial `as_str(&self) -> &str` accessor
- A pure data struct `UserRecord { id: UserId, email: Email, created_at: u64 }` with no methods
- No logic, no state transitions, no error handling, no boundaries

This is designed to tempt suggestions like "test Default impl", "test From conversion", "test Display output", "test accessor returns correct value" — all of which should be suppressed by the DO NOT SUGGEST list.

**Metadata** (`adversarial_test_suggestions_trivial_newtype.json`):

```json
{
    "type": "adversarial",
    "category": "test-suggestions",
    "language": "rust",
    "description": "Newtype wrappers with derived traits and trivial accessors — tempts suggestions for testing Default/From/Display but all should be suppressed",
    "expect_empty": true
}
```

Note: No `test_file` field. Despite no tests existing, the code is too trivial for any meaningful test suggestions.

**Verification:**

Run: `uv run scripts/test_corpus.py --corpus-dir tests/corpus/rust/`
Expected: The adversarial case passes (zero suggestions returned).

**Commit:** `test: add adversarial corpus file for test-suggestions calibration`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_TASK_5 -->
### Task 5: Run full corpus validation

**Verifies:** test-hammer.AC4.1, test-hammer.AC4.2, test-hammer.AC4.3

**Files:** None (verification only)

**Verification:**

Run the full corpus suite to confirm all cases pass (existing + new):

```bash
uv run scripts/test_corpus.py
```

Expected output:
- All 9 existing cases: PASS
- `clean_test_suggestions_well_tested`: PASS (zero suggestions)
- `bug_test_suggestions_untested_parser`: PASS (suggestions in `test-suggestions` category)
- `adversarial_test_suggestions_trivial_newtype`: PASS (zero suggestions)
- Summary: 12 passed, 0 failed, 0 errors

If any new case fails, iterate on the corpus file content or prompt section. The goal is prompt calibration — the corpus validates that the prompt template produces correct behavior.

**Commit:** No commit needed (verification only).

<!-- END_TASK_5 -->
