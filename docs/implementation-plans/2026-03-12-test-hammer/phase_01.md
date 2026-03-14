# Test Hammer Implementation Plan — Phase 1: Prompt Templates and Script Extension

**Goal:** Add `test-suggestions` category to Rust and generic prompt templates and extend `review_file.py` to accept test context via `--test-context` flag.

**Architecture:** Extends the existing prompt template + `review_file.py` pipeline. New `## test-suggestions` sections follow the same extraction pattern as existing categories but use a different internal structure (WHAT TO SUGGEST / DO NOT SUGGEST instead of Look for / DO NOT REPORT) since this category suggests tests rather than finding bugs. The `--test-context` flag adds optional test file content to the user message sent to the LLM.

**Tech Stack:** Python 3.10+, OpenAI SDK, uv, pytest

**Scope:** 6 phases from original design (this is phase 1 of 6)

**Codebase verified:** 2026-03-13

---

## Acceptance Criteria Coverage

This phase implements and tests:

### test-hammer.AC3: Language-specific prompt templates
- **test-hammer.AC3.1 Success:** `prompts/rust.md` contains `## test-suggestions` section with Rust-specific WHAT TO SUGGEST and DO NOT SUGGEST lists
- **test-hammer.AC3.2 Success:** `prompts/generic.md` contains `## test-suggestions` section as fallback
- **test-hammer.AC3.3 Success:** DO NOT SUGGEST lists prevent suggestions for language-level trivia (e.g., Rust: testing Default/From/Into for newtypes; Python: testing `__init__` assignment)

### test-hammer.AC5: Cross-cutting behaviors
- **test-hammer.AC5.3 Edge:** Large test files exceeding 500 lines are truncated with a warning before being passed to the LLM

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add `## test-suggestions` section to `prompts/rust.md`

**Verifies:** test-hammer.AC3.1, test-hammer.AC3.3

**Files:**
- Modify: `prompts/rust.md` (append after line 269, the end of `## missing-edge-cases`)

**Implementation:**

Append a new `## test-suggestions` section at the end of the file. This section follows a different internal structure than existing categories because it suggests tests rather than reports bugs. The "Focus" is replaced with a prioritized "WHAT TO SUGGEST" list, and "DO NOT REPORT" is replaced with "DO NOT SUGGEST".

The hard cap of 3 suggestions must be stated in the section preamble.

Add the following content after the existing `## missing-edge-cases` section (after line 269):

```markdown

---

## test-suggestions

You are now a test-suggestion specialist. Given production source code and optionally existing test code, suggest up to **3** high-value tests that are missing.

**Output format:** Same JSON array as other categories. In the `description` field, explain WHAT to test and WHY it matters — not how to implement the test. The `category` field must be `"test-suggestions"`.

**IMPORTANT:** Return at most 3 suggestions. If fewer than 3 are warranted, return fewer. If nothing is worth suggesting, return `[]`.

**WHAT TO SUGGEST** (in priority order):

1. **State transition coverage** — Code with distinct states (enums, flags, mode fields) where transitions between states are not tested. Focus on transitions that change observable behavior.
2. **Error path coverage** — Error handling paths (`match` on `Result`/`Option`, `?` propagation, custom error types) with no corresponding error-case tests. Prioritize paths where the error transforms data or has side effects.
3. **Business logic boundaries** — Domain-specific boundary conditions where behavior changes (thresholds, limits, mode switches). The boundary must be in THIS code, not in a called function.
4. **Integration seam tests** — Boundaries between components where one side makes assumptions about the other's behavior (trait implementations, callback contracts, message formats). Focus on assumptions that could silently diverge.
5. **Property-based test opportunities** — Functions with clear invariants: roundtrip encode/decode, idempotency, commutativity. Only suggest when the invariant is non-trivial and not already covered.

**DO NOT SUGGEST:**

- Tests that validate Rust language semantics (`Option` can be `None`, `Vec` can be empty, `Result` can be `Err`)
- Tests that duplicate what the type system or borrow checker enforces (type conversions, ownership rules, lifetime correctness)
- Tests for trivial `Default`, `From`, `Into`, `Display`, or `Debug` implementations on newtypes or simple structs
- Tests for trivial getters/setters/accessors with no logic
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for `Clone`, `PartialEq`, `Hash`, or other derived trait implementations
- Tests for framework-provided behavior (`serde` serialization of simple structs, `clap` argument parsing)
- Tests for pure data structures with no logic (struct definitions, enum variants with no methods)
- Tests already covered in the existing test file(s) provided as context
- Tests for `#[cfg(test)]` module scaffolding or test helper functions
- Tests that only verify a function "doesn't panic" without checking the result
```

**Verification:**

Run: `.venv/bin/pytest tests/test_review_file.py::TestExtractCategoryPrompt -v`
Expected: Existing tests still pass (new section doesn't break extraction of other categories).

**Commit:** `feat: add test-suggestions prompt section to rust.md`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add `## test-suggestions` section to `prompts/generic.md`

**Verifies:** test-hammer.AC3.2

**Files:**
- Modify: `prompts/generic.md` (append after the last section, currently `## missing-edge-cases` ending at line 223)

**Implementation:**

Append a `## test-suggestions` section at the end of `prompts/generic.md`. This is the language-agnostic fallback. The structure mirrors the Rust version but the DO NOT SUGGEST list uses language-agnostic phrasing.

```markdown

---

## test-suggestions

You are now a test-suggestion specialist. Given production source code and optionally existing test code, suggest up to **3** high-value tests that are missing.

**Output format:** Same JSON array as other categories. In the `description` field, explain WHAT to test and WHY it matters — not how to implement the test. The `category` field must be `"test-suggestions"`.

**IMPORTANT:** Return at most 3 suggestions. If fewer than 3 are warranted, return fewer. If nothing is worth suggesting, return `[]`.

**WHAT TO SUGGEST** (in priority order):

1. **State transition coverage** — Code with distinct states where transitions between states are not tested. Focus on transitions that change observable behavior.
2. **Error path coverage** — Error handling paths (try/catch, error returns, exception handlers) with no corresponding error-case tests. Prioritize paths where the error transforms data or has side effects.
3. **Business logic boundaries** — Domain-specific boundary conditions where behavior changes (thresholds, limits, mode switches). The boundary must be in THIS code, not in a called function.
4. **Integration seam tests** — Boundaries between components where one side makes assumptions about the other's behavior (interface implementations, callback contracts, message formats). Focus on assumptions that could silently diverge.
5. **Property-based test opportunities** — Functions with clear invariants: roundtrip encode/decode, idempotency, commutativity. Only suggest when the invariant is non-trivial and not already covered.

**DO NOT SUGGEST:**

- Tests that validate language semantics (null can be null, empty collections can be empty)
- Tests that duplicate what the type system or compiler enforces
- Tests for trivial getters/setters/accessors with no logic
- Tests that merely exercise code for coverage without meaningful assertions
- Tests for framework-provided behavior (ORM basic CRUD, framework routing)
- Tests for pure data structures with no logic
- Tests already covered in the existing test file(s) provided as context
- Tests that only verify a function "doesn't throw/panic" without checking the result
```

**Verification:**

Run: `.venv/bin/pytest tests/test_review_file.py::TestExtractCategoryPrompt -v`
Expected: Existing tests still pass.

**Commit:** `feat: add test-suggestions prompt section to generic.md`

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Add `--test-context` CLI argument and plumbing to `review_file.py`

**Verifies:** test-hammer.AC5.3

**Files:**
- Modify: `scripts/review_file.py`
  - Lines 369-409: Add `--test-context` argument to argparse
  - Lines 249-257: Add `test_context_paths` parameter to `review_file()` function signature
  - Lines 287-312: Add test context reading and prompt assembly logic
  - Lines 434-443: Pass test context to `review_file()` call

**Implementation:**

Three changes to `review_file.py`:

**Change 1: Add `--test-context` CLI argument (after `--timeout` arg, around line 409)**

Add a new argument that can be specified multiple times (for multiple test files):

```python
parser.add_argument(
    "--test-context",
    action="append",
    default=None,
    dest="test_context",
    help="Path to existing test file(s) to include as context. Can be specified multiple times."
)
```

**Change 2: Add `test_context_paths` parameter to `review_file()` function**

Update the function signature at line 249 to add an optional parameter:

```python
def review_file(
    file_path: str,
    category: str,
    language: str,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float = 120.0,
    test_context_paths: list[str] | None = None
) -> list:
```

Update the docstring to document the new parameter.

**Change 3: Build user message with test context**

After `numbered_source = prepend_line_numbers(source)` (line 292), add logic to read test context files and build the user message. Insert before the client creation (line 302):

```python
# Build user message: source code + optional test context
user_message = f"# Source file: {file_path}\n\n{numbered_source}"

if test_context_paths:
    for test_path in test_context_paths:
        if not os.path.exists(test_path):
            print(f"Warning: Test context file not found: {test_path}", file=sys.stderr)
            continue
        with open(test_path, 'r') as f:
            test_lines = f.readlines()
        if len(test_lines) > 500:
            print(
                f"Warning: Test file {test_path} has {len(test_lines)} lines, "
                f"truncating to 500 lines",
                file=sys.stderr
            )
            test_content = ''.join(test_lines[:500])
            test_content += f"\n# ... truncated ({len(test_lines) - 500} lines omitted)"
        else:
            test_content = ''.join(test_lines)
        numbered_test = prepend_line_numbers(test_content)
        user_message += f"\n\n# Existing test file: {test_path}\n\n{numbered_test}"
else:
    if category == "test-suggestions":
        user_message += "\n\n# No existing test files found for this source file."
```

**Change 4: Use `user_message` instead of `numbered_source` in API call**

In the `messages` list at line 310-313, replace `numbered_source` with `user_message`:

```python
messages=[
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_message}
],
```

**Change 5: Pass test context from `main()` to `review_file()`**

In the `main()` function at the `review_file()` call (around line 435), add the new parameter:

```python
findings = review_file(
    file_path=args.file_path,
    category=args.category,
    language=language,
    api_key=api_key,
    base_url=base_url,
    model=model,
    timeout=args.timeout,
    test_context_paths=args.test_context
)
```

**Verification:**

Run: `.venv/bin/pytest tests/test_review_file.py -v`
Expected: All existing tests still pass (new parameter is optional with default None, so no existing calls break).

**Commit:** `feat: add --test-context flag to review_file.py`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Unit tests for `--test-context` flag

**Verifies:** test-hammer.AC3.1 (end-to-end with prompt), test-hammer.AC5.3 (truncation)

**Files:**
- Modify: `tests/test_review_file.py` (add new test class after existing classes)

**Testing:**

Add a new `TestTestContext` class to `tests/test_review_file.py` covering these scenarios:

- **test-hammer.AC3.1:** `review_file()` with `--test-context` includes test file content in the user message sent to the API. Mock the OpenAI client and verify the `messages[1]["content"]` contains both the source and test file content.
- **test-hammer.AC5.3:** When a test context file exceeds 500 lines, it is truncated and a warning is printed to stderr. Create a temp file with 600 lines, call `review_file()` with it as test context, verify the user message contains only 500 lines of test content plus the truncation notice.
- **No test file exists:** When `test_context_paths` contains a nonexistent path, a warning is printed to stderr and the review proceeds without that file's content.
- **Multiple test files:** When `test_context_paths` has 2 paths, both are included in the user message.
- **No test context with test-suggestions category:** When `test_context_paths` is None and category is `"test-suggestions"`, the user message includes the "No existing test files found" notice.
- **No test context with other category:** When `test_context_paths` is None and category is not `"test-suggestions"`, no extra notice is appended (backward compatible).

Follow the existing mocking patterns in `TestReviewFile`:
- Use `patch('review_file.OpenAI')` to mock the client
- Use `patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"})` for env vars
- Use the `temp_file_with_content` fixture for creating temp source and test files
- Capture the `messages` argument from `mock_client.chat.completions.create.call_args`

**Verification:**

Run: `.venv/bin/pytest tests/test_review_file.py::TestTestContext -v`
Expected: All new tests pass.

Run: `.venv/bin/pytest tests/test_review_file.py -v`
Expected: All tests pass (new + existing).

**Commit:** `test: add unit tests for --test-context flag`

<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
