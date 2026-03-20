# Smart Input Implementation Plan — Phase 1

**Goal:** `review_file.py` can accept `--diff-base` and produce a context-assembled user message from a git diff, with original file line numbers.

**Architecture:** Add diff extraction and context assembly to `scripts/review_file.py`. When `--diff-base` is provided, the script runs `git diff`, parses unified diff output, extracts file header and diff hunks with surrounding context lines, and assembles a review-ready message preserving original file line numbers. A coverage detector switches framing when ≥90% of the file is covered.

**Tech Stack:** Python 3.10+, subprocess (git diff), OpenAI SDK (existing)

**Scope:** 7 phases from original design (phase 1 of 7)

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements and tests:

### smart-input.AC1: Commit and branch review via natural language
- **smart-input.AC1.3 Success:** Findings reference original file line numbers, not diff-relative positions

### smart-input.AC5: Diff context assembly
- **smart-input.AC5.1 Success:** Diff hunks include file header plus surrounding context lines with original line numbers
- **smart-input.AC5.2 Success:** Adjacent hunks with overlapping context windows are merged into one continuous block
- **smart-input.AC5.3 Success:** When assembled content covers >=90% of the file, diff markers are preserved but full-file framing is used
- **smart-input.AC5.4 Success:** Runtime instruction block injected before content explains the format to the LLM

### smart-input.AC6: Backward compatibility
- **smart-input.AC6.1 Success:** Omitting `--diff-base` produces identical behavior to current implementation
- **smart-input.AC6.2 Success:** All existing unit tests and corpus tests pass without modification
- **smart-input.AC6.3 Success:** No prompt template files are modified

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add `--diff-base` and `--context-lines` CLI arguments

**Verifies:** smart-input.AC6.1 (backward compatibility when omitted)

**Files:**
- Modify: `scripts/review_file.py:443-498` (argparse setup and config resolution)

**Implementation:**

Add two new optional arguments to the argparse setup in `main()`, following the existing `--test-context` pattern (optional flag, `None` default). Add after the `--test-context` argument block (after line 483):

```python
parser.add_argument(
    "--diff-base",
    default=None,
    help="Git ref to diff against (e.g., HEAD~1, main). When provided, reviews only changed hunks with context instead of the full file.",
)
parser.add_argument(
    "--context-lines",
    type=int,
    default=3,
    help="Number of context lines around each diff hunk (default: 3). Only used with --diff-base.",
)
```

Pass both new args through to `review_file()` in `main()` (around line 514):

```python
findings = review_file(
    file_path=args.file_path,
    category=args.category,
    language=language,
    api_key=api_key,
    base_url=base_url,
    model=model,
    timeout=args.timeout,
    test_context_paths=args.test_context,
    diff_base=args.diff_base,
    context_lines=args.context_lines,
)
```

Update `review_file()` signature (line 262) to accept the new parameters:

```python
def review_file(
    file_path: str,
    category: str,
    language: str,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float = 120.0,
    test_context_paths: list[str] | None = None,
    diff_base: str | None = None,
    context_lines: int = 3,
) -> list:
```

For now, the new parameters are accepted but not used — they will be wired in Tasks 3-6. This ensures backward compatibility: omitting `--diff-base` preserves identical behavior.

**Verification:**
Run: `.venv/bin/pytest tests/ -x`
Expected: All existing tests pass unchanged (new params have defaults)

**Commit:** `feat: add --diff-base and --context-lines CLI arguments to review_file.py`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Tests for CLI argument parsing

**Verifies:** smart-input.AC6.1

**Files:**
- Modify: `tests/test_review_file.py` (add to TestMainCLI class)

**Testing:**
Add tests to the existing `TestMainCLI` class that verify:
- smart-input.AC6.1: Running without `--diff-base` still works identically (existing tests already cover this, but add an explicit assertion that `diff_base` defaults to `None` in the argparse namespace)
- `--diff-base HEAD~1` is parsed correctly into `args.diff_base == "HEAD~1"`
- `--context-lines 5` is parsed correctly as integer
- `--context-lines` defaults to 3 when omitted
- `--diff-base` and `--context-lines` are passed through to `review_file()` call

Follow existing test patterns: use `patch("review_file.OpenAI")` and `patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"})` to isolate from API calls. Import from `review_file` module.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py::TestMainCLI -x -v`
Expected: All tests pass

**Commit:** `test: add CLI argument tests for --diff-base and --context-lines`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->
<!-- START_TASK_3 -->
### Task 3: Unified diff parser function

**Verifies:** smart-input.AC5.1, smart-input.AC1.3

**Files:**
- Modify: `scripts/review_file.py` (add new function after `prepend_line_numbers` at line 136)

**Implementation:**

Add a `parse_unified_diff()` function that takes raw `git diff` output for a single file and returns structured hunk data. Place it after `prepend_line_numbers()` (after line 136) in `review_file.py`.

The function should:
1. Parse `@@ -old_start,old_count +new_start,new_count @@` hunk headers
2. Extract the original-file line range for each hunk (the `-old_start,old_count` side)
3. Return a list of dicts, each with `{"start_line": int, "end_line": int}` representing the range of changed lines in the original file

Use `re.finditer` with pattern `r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@'` (with `re.MULTILINE`) to find hunk headers. For each match:
- `start_line = int(match.group(1))`
- `count = int(match.group(2) or '1')`
- `end_line = start_line + count - 1`

Then walk the diff lines within each hunk to find exactly which original-file lines were changed (lines starting with `-` or ` ` that have context). This gives the precise line ranges that the LLM needs to focus on.

```python
def parse_unified_diff(diff_output: str) -> list[dict]:
    """
    Parse unified diff output and extract hunk ranges.

    Args:
        diff_output: Raw output from `git diff` for a single file

    Returns:
        List of dicts with keys:
        - start_line: First line number in original file
        - end_line: Last line number in original file
        Each dict represents one hunk's range in the original file.
        Returns empty list if no hunks found.
    """
```

**Testing:**
Tests must verify each AC listed above:
- smart-input.AC5.1: Parse a multi-hunk diff and confirm each hunk's start_line/end_line matches the `@@` header
- smart-input.AC1.3: Line numbers in returned hunks are original-file line numbers (from the `-` side of the `@@` header), not diff-relative positions
- Edge case: single-line hunk (count omitted in `@@` header, e.g., `@@ -5 +5,2 @@` means count=1)
- Edge case: empty diff output returns empty list
- Edge case: diff with only additions (new file) — `@@ -0,0 +1,10 @@`

Create a new test class `TestParseUnifiedDiff` in `tests/test_review_file.py`. Import `parse_unified_diff` from `review_file`.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py::TestParseUnifiedDiff -x -v`
Expected: All tests pass

**Commit:** `feat: add unified diff parser for extracting hunk ranges`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: File header extractor function

**Verifies:** smart-input.AC5.1

**Files:**
- Modify: `scripts/review_file.py` (add new function after `parse_unified_diff`)

**Implementation:**

Add an `extract_file_header()` function that captures the top portion of a source file (imports, module-level declarations, type definitions) — everything before the first function/class definition. This header is prepended to every diff excerpt so the LLM has context about types and imports.

The function takes the full file content as a string and returns the header portion. Use a language-agnostic heuristic: scan lines top-to-bottom, and stop when encountering a line that starts a function or class definition. Common patterns across languages:
- Python: `def `, `class `, `async def `
- Rust: `fn `, `impl `, `pub fn `, `pub(crate) fn `
- JavaScript/TypeScript: `function `, `export function `, `export default function `
- Go: `func `
- Java/C#/Kotlin: lines containing `{` after a word that looks like a method/class (heuristic)
- C/C++: function definitions

A practical approach: stop at the first line matching `r'^\s*(def |class |fn |pub fn |pub\(|impl |func |function |export function |export default function |async def )'`. If no match, return the entire file (it might be a config/data file).

Also cap the header at a reasonable size (e.g., first 50 lines or 25% of total lines, whichever is smaller) to avoid sending excessive header content.

```python
# Regex pattern for function/class definition starts across common languages
_DEFINITION_START = re.compile(
    r'^\s*(?:pub(?:\(crate\))?\s+)?(?:async\s+)?(?:def |class |fn |impl |func |function |export\s+(?:default\s+)?function )',
)

# Maximum header lines (cap to avoid excessive context)
MAX_HEADER_LINES = 50


def extract_file_header(source: str) -> str:
    """
    Extract the file header (imports, type definitions, module-level declarations).

    Returns everything before the first function/class definition, capped at
    MAX_HEADER_LINES lines.

    Args:
        source: Full file content

    Returns:
        Header portion of the file, or empty string if file starts with a definition.
    """
```

**Testing:**
Tests must verify:
- smart-input.AC5.1: Python file with imports then `def` — returns only the imports section
- Rust file with `use` statements then `fn` — returns only the `use` section
- File with no function definitions (e.g., config file) — returns entire file (capped)
- Empty file returns empty string
- File that starts immediately with `def` — returns empty string
- Header exceeding MAX_HEADER_LINES is capped

Create a new test class `TestExtractFileHeader` in `tests/test_review_file.py`. Import `extract_file_header` and `MAX_HEADER_LINES` from `review_file`.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py::TestExtractFileHeader -x -v`
Expected: All tests pass

**Commit:** `feat: add file header extractor for diff context`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Context assembler function

**Verifies:** smart-input.AC5.1, smart-input.AC5.2, smart-input.AC1.3

**Files:**
- Modify: `scripts/review_file.py` (add new function after `extract_file_header`)

**Implementation:**

Add an `assemble_diff_context()` function that takes parsed hunk ranges, the full source file, and context_lines count, then produces the review-ready excerpt with original file line numbers.

The function should:
1. For each hunk range, expand by ±context_lines
2. Merge overlapping/adjacent expanded ranges into continuous blocks
3. For each merged block, extract those lines from the source file
4. Prepend line numbers using the same `{n}| {line}` format as `prepend_line_numbers()` (but only for the extracted line ranges, preserving original line numbers)
5. Add `...` separator between non-adjacent blocks
6. Prepend the file header (from `extract_file_header()`) before the hunk content, separated by a blank line and `--- (hunks below) ---` marker

```python
def assemble_diff_context(
    hunks: list[dict],
    source: str,
    context_lines: int = 3,
) -> str:
    """
    Assemble diff hunks with surrounding context and original line numbers.

    Args:
        hunks: List of {"start_line": int, "end_line": int} from parse_unified_diff()
        source: Full file content
        context_lines: Number of lines to include above and below each hunk

    Returns:
        Assembled content with file header, then numbered hunk excerpts
        with `...` separators between non-adjacent blocks.
        Line numbers match the original file (1-indexed).
    """
```

Key implementation details:
- Lines are 1-indexed (matching `prepend_line_numbers()` convention)
- Right-justify line numbers based on max line number in the file (consistent with existing format)
- When expanding ranges, clamp to `[1, total_lines]`
- Two ranges overlap if `range_a.end + 1 >= range_b.start` (after expansion)

**Testing:**
Tests must verify each AC listed above:
- smart-input.AC5.1: Single hunk with context_lines=3 includes 3 lines above and below, with file header prepended, all with original line numbers
- smart-input.AC5.2: Two hunks 2 lines apart with context_lines=3 are merged into one continuous block (3+2+3 > gap)
- smart-input.AC5.2: Two hunks far apart remain separate with `...` separator
- smart-input.AC1.3: Line numbers in output match original file positions (e.g., if hunk starts at line 50, first numbered line is 50)
- Edge case: hunk at start of file (no lines above to include)
- Edge case: hunk at end of file (no lines below to include)

Create a new test class `TestAssembleDiffContext` in `tests/test_review_file.py`. Import `assemble_diff_context` from `review_file`.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py::TestAssembleDiffContext -x -v`
Expected: All tests pass

**Commit:** `feat: add context assembler for diff hunk expansion and merging`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-8) -->
<!-- START_TASK_6 -->
### Task 6: Coverage detector function

**Verifies:** smart-input.AC5.3

**Files:**
- Modify: `scripts/review_file.py` (add new function after `assemble_diff_context`)

**Implementation:**

Add a `detect_coverage()` function that compares the assembled diff content lines against the total file lines. When ≥90% of the file is covered by the assembled hunks, the review should use full-file framing (with diff markers showing what changed) rather than partial-view framing.

```python
# Threshold for switching from partial to full-file framing
FULL_COVERAGE_THRESHOLD = 0.90


def detect_coverage(hunks: list[dict], total_lines: int, context_lines: int) -> bool:
    """
    Determine if assembled diff covers enough of the file for full-file framing.

    Args:
        hunks: List of {"start_line": int, "end_line": int} from parse_unified_diff()
        total_lines: Total lines in the original file
        context_lines: Context lines used for expansion

    Returns:
        True if coverage >= FULL_COVERAGE_THRESHOLD (90%), meaning full-file
        framing should be used instead of partial-view framing.
    """
```

The function should:
1. Expand each hunk range by ±context_lines (same expansion as `assemble_diff_context`)
2. Merge overlapping ranges
3. Count total covered lines
4. Return `covered_lines / total_lines >= FULL_COVERAGE_THRESHOLD`

**Testing:**
Tests must verify:
- smart-input.AC5.3: File with 100 lines, hunks covering 92 lines after expansion → returns True
- smart-input.AC5.3: File with 100 lines, hunks covering 50 lines after expansion → returns False
- Boundary: exactly 90% coverage → returns True
- Boundary: 89% coverage → returns False
- Edge case: empty hunks list → returns False
- Edge case: single hunk covering entire file → returns True

Create a new test class `TestDetectCoverage` in `tests/test_review_file.py`. Import `detect_coverage` and `FULL_COVERAGE_THRESHOLD` from `review_file`.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py::TestDetectCoverage -x -v`
Expected: All tests pass

**Commit:** `feat: add coverage detector for diff-to-full-file framing switch`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Runtime instruction injection

**Verifies:** smart-input.AC5.4, smart-input.AC6.3

**Files:**
- Modify: `scripts/review_file.py` (add constants and function after `detect_coverage`)

**Implementation:**

Add instruction text constants and a `build_diff_user_message()` function that constructs the complete user message for diff mode. This function injects mode-specific instructions at the top of the user message, before the code content, explaining the format to the LLM. No prompt template files are modified (AC6.3).

```python
DIFF_PARTIAL_INSTRUCTIONS = """## Review Input Format

You are reviewing a **partial view** of the file, showing only changed code with surrounding context.

- Line numbers are from the original file (use these in your findings)
- The file header (imports/declarations) is shown first for context
- `...` separates non-adjacent code sections
- Focus your review on the visible code — do not speculate about unseen sections
"""

DIFF_FULL_WITH_MARKERS_INSTRUCTIONS = """## Review Input Format

You are reviewing the **full file** with diff markers showing recent changes.

- Line numbers are from the original file (use these in your findings)
- Lines prefixed with `+` were added
- Lines prefixed with `-` were removed (shown for context, not in the current file)
- Review the entire file but pay special attention to changed lines and their interactions with surrounding code
"""


def build_diff_user_message(
    file_path: str,
    source: str,
    hunks: list[dict],
    context_lines: int,
    diff_output: str,
) -> str:
    """
    Build the user message for diff mode review.

    Chooses between partial-view and full-file-with-markers framing
    based on coverage detection.

    Args:
        file_path: Path to the file being reviewed
        source: Full file content
        hunks: Parsed hunk ranges from parse_unified_diff()
        context_lines: Number of context lines for expansion
        diff_output: Raw git diff output (used for full-file-with-markers mode)

    Returns:
        Complete user message string ready for API call
    """
```

For partial coverage (<90%):
- Header: `# Diff review: {file_path}\n\n{DIFF_PARTIAL_INSTRUCTIONS}\n\n{assembled_context}`

For full coverage (≥90%):
- Header: `# Source file: {file_path}\n\n{DIFF_FULL_WITH_MARKERS_INSTRUCTIONS}\n\n{full_file_with_diff_markers}`
- The full file content should use `prepend_line_numbers()` on the current file content, with `+`/`-` markers on changed lines

**Testing:**
Tests must verify:
- smart-input.AC5.4: Partial coverage message starts with `# Diff review:` and contains `DIFF_PARTIAL_INSTRUCTIONS` text
- smart-input.AC5.4: Full coverage message starts with `# Source file:` and contains `DIFF_FULL_WITH_MARKERS_INSTRUCTIONS` text
- smart-input.AC6.3: No prompt template files are read or modified by this function (it only builds the user message)
- Content includes file header and numbered lines for partial mode
- Content includes full numbered file for full-coverage mode

Create a new test class `TestBuildDiffUserMessage` in `tests/test_review_file.py`. Import `build_diff_user_message`, `DIFF_PARTIAL_INSTRUCTIONS`, and `DIFF_FULL_WITH_MARKERS_INSTRUCTIONS` from `review_file`.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py::TestBuildDiffUserMessage -x -v`
Expected: All tests pass

**Commit:** `feat: add runtime instruction injection for diff mode user messages`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Wire diff mode into `review_file()` function

**Verifies:** smart-input.AC5.1, smart-input.AC5.3, smart-input.AC5.4, smart-input.AC6.1

**Files:**
- Modify: `scripts/review_file.py:262-326` (the `review_file()` function, between file reading and API call)

**Implementation:**

In the `review_file()` function, after reading the file (line 312) and before building the user message (line 326), add a conditional branch for diff mode:

```python
    # Read the file
    with open(file_path, "r") as f:
        source = f.read()
    source_lines = source.count("\n") + 1

    # Build user message based on mode
    if diff_base is not None:
        # Diff mode: run git diff, parse, and assemble context
        diff_output = subprocess.run(
            ["git", "diff", diff_base, "--", file_path],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        hunks = parse_unified_diff(diff_output)
        if not hunks:
            # No changes found — skip review for this file
            print(
                f"[review] SKIP {category} for {file_path} (no diff hunks found)",
                file=sys.stderr,
            )
            return []

        user_message = build_diff_user_message(
            file_path=file_path,
            source=source,
            hunks=hunks,
            context_lines=context_lines,
            diff_output=diff_output,
        )
    else:
        # Full-file mode (existing behavior)
        numbered_source = prepend_line_numbers(source)
        user_message = f"# Source file: {file_path}\n\n{numbered_source}"
```

Add `import subprocess` to the stdlib imports (alphabetically, after `import re` on line 20).

The test context block (lines 328-354) remains unchanged and appends to `user_message` regardless of mode.

**Testing:**
Tests must verify:
- smart-input.AC6.1: `review_file()` called without `diff_base` still produces the exact same user message format (`# Source file: {path}\n\n{numbered}`)
- smart-input.AC5.1: `review_file()` called with `diff_base="HEAD~1"` runs `git diff`, parses hunks, and produces a diff-mode user message
- smart-input.AC5.3: With high-coverage diff, produces full-file-with-markers message
- smart-input.AC5.4: Diff-mode message contains runtime instructions
- Empty diff (no hunks) returns empty findings list `[]`

Add tests to a new class `TestReviewFileDiffMode` in `tests/test_review_file.py`. Mock `subprocess.run` to return fake diff output (don't depend on actual git state). Use existing `patch("review_file.OpenAI")` pattern for API isolation.

**Verification:**
Run: `.venv/bin/pytest tests/test_review_file.py -x -v`
Expected: All tests pass including new diff mode tests AND all existing tests

**Commit:** `feat: wire diff mode into review_file() with git diff integration`
<!-- END_TASK_8 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_TASK_9 -->
### Task 9: Run full test suite and verify backward compatibility

**Verifies:** smart-input.AC6.1, smart-input.AC6.2

**Files:**
- No new files — verification only

**Verification:**

Run: `.venv/bin/pytest tests/ -x -v`
Expected: All tests pass — both existing tests and new tests

Run: `ruff check scripts/review_file.py tests/test_review_file.py`
Expected: No lint errors

Run: `ruff format --check scripts/review_file.py tests/test_review_file.py`
Expected: No formatting issues

**Commit:** No commit needed — this is a verification step. If any issues are found, fix and amend the previous commit.
<!-- END_TASK_9 -->
