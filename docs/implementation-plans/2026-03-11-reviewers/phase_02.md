# Review Hammer Implementation Plan — Phase 2: Python Script Core

**Goal:** `review_file.py` can send a single file + category to an OpenAI-compatible API and return structured JSON findings

**Architecture:** CLI script with three pure functions (line numbering, prompt extraction, response parsing) and one I/O function (API call). Uses the OpenAI Python SDK configured with custom base_url for backend-agnostic operation. Prompt templates are markdown files with H2 sections per specialist category.

**Tech Stack:** Python 3.9+, openai SDK v2.x, argparse

**Scope:** 6 phases from original design (this is phase 2 of 6)

**Descoped from this implementation round:**
- File chunking for files over ~3,000 lines (design section "File Chunking"). The script processes files whole. Large file support (line-range arguments, splitting by top-level declarations) will be added in a future iteration.

**Codebase verified:** 2026-03-11 — fresh `review_hammer` repo. `scripts/` directory will be created by Phase 1 (placeholder .gitkeep). No existing Python code. User convention: always use `.venv/` at repo root. System Python: 3.14.3.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### reviewers.AC2: Python script produces correct findings
- **reviewers.AC2.1 Success:** Script sends line-numbered code to API and returns valid JSON with correct line numbers
- **reviewers.AC2.2 Success:** Script reads prompt template for correct language and extracts correct category section
- **reviewers.AC2.3 Failure:** Script returns clear error when API key is missing or invalid
- **reviewers.AC2.4 Edge:** Script handles API returning empty/malformed response without crashing

---

<!-- START_TASK_1 -->
### Task 1: Set up Python virtual environment and dependencies

**Files:**
- Create: `scripts/requirements.txt`
- Create: `.venv/` (virtual environment, gitignored)

**Step 1: Create requirements.txt**

```
openai>=1.0.0
pytest>=7.0.0
```

**Step 2: Create virtual environment and install dependencies**

Run:
```bash
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
```
Expected: Installation completes without errors

**Step 3: Verify openai is importable**

Run: `.venv/bin/python3 -c "import openai; print(openai.__version__)"`
Expected: Prints version number (e.g., `2.26.0`)

**Step 4: Ensure .venv is gitignored**

Run:
```bash
for pattern in '.venv/' '__pycache__/' '*.pyc'; do
  grep -q "$pattern" .gitignore 2>/dev/null || echo "$pattern" >> .gitignore
done
```

**Commit:** `chore: add Python dependencies and virtual environment`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create generic prompt template

**Files:**
- Create: `prompts/generic.md`

**Step 1: Create the generic prompt template**

The template has a preamble, 6 production specialist sections (H2 headings), and 5 test specialist sections (H2 headings). Each section has a focused mandate and DO NOT REPORT constraints.

The script will extract sections by matching H2 headings (`## category-name`). The category name in the heading must match the CLI `--category` argument exactly.

```markdown
# Generic Code Review Specialist

You are a code review specialist. You will be given source code with line numbers prepended. Your job is to find bugs in ONE specific category. Report ONLY findings in your assigned category.

**Output format:** Return a JSON array of findings. Each finding must have:
- `lines`: array of two integers [start_line, end_line]
- `severity`: one of "critical", "high", "medium"
- `category`: your assigned category name
- `description`: one-sentence description of the bug
- `impact`: one-sentence description of the consequence
- `confidence`: float between 0.0 and 1.0

If you find nothing, return an empty array: `[]`

**IMPORTANT:** Return ONLY the JSON array. No markdown fences, no explanation, no preamble.

---

## race-conditions

**Focus:** Find race conditions, data races, TOCTOU bugs, and concurrency issues.

Look for:
- Shared mutable state accessed without synchronization
- Check-then-act patterns without atomicity
- Concurrent collection modification
- Callback/event handler ordering assumptions
- Async operations that assume sequential execution

**DO NOT REPORT:**
- Single-threaded code with no concurrency
- Immutable shared state
- Thread-local variables
- Properly synchronized access (locks, mutexes, atomic operations)
- Event-driven code where the framework guarantees single-threaded execution

---

## null-safety

**Focus:** Find null pointer dereferences, undefined access, and missing nil checks.

Look for:
- Dereferencing values that may be null/None/nil/undefined
- Optional chaining that silently swallows errors
- Missing null checks after fallible operations (map lookups, find, array access)
- Type narrowing gaps where null flows through unchecked

**DO NOT REPORT:**
- Values guaranteed non-null by language semantics or prior checks
- Constructor-initialized fields accessed after construction
- Guard clauses that already handle the null case
- Default parameter values that prevent null

---

## resource-leaks

**Focus:** Find unclosed resources: file handles, network connections, database connections, streams, locks.

Look for:
- Resources opened but never closed
- Resources closed only in the happy path (not in error/exception paths)
- Missing try-finally or equivalent cleanup patterns
- Resources stored in local variables that go out of scope

**DO NOT REPORT:**
- Resources managed by a framework or container (dependency injection, context managers)
- Resources with automatic cleanup (garbage collected handles in languages that support it)
- Resources closed in a finally block or equivalent
- Short-lived resources in scripts/CLI tools where process exit cleans up

---

## logic-errors

**Focus:** Find logic bugs: wrong conditions, off-by-one errors, incorrect operator usage, unreachable code.

Look for:
- Inverted boolean conditions (if x instead of if not x)
- Off-by-one in loops, array indexing, or range calculations
- Wrong comparison operator (< vs <=, == vs ===)
- Dead code after unconditional return/break/throw
- Switch/match fallthrough bugs
- Integer overflow/underflow in arithmetic

**DO NOT REPORT:**
- Stylistic preferences (ternary vs if-else)
- Performance optimizations that don't change correctness
- Missing features or incomplete implementations (unless they cause bugs in existing code)
- Code that is correct but could be written more clearly

---

## error-handling

**Focus:** Find swallowed errors, missing error handling, and incorrect error propagation.

Look for:
- Empty catch/except blocks that silently swallow errors
- Generic catch-all that hides specific failures
- Error codes ignored (unchecked return values)
- Errors logged but not propagated when callers need to know
- Cleanup code that runs but the error is still lost
- Incorrect error type thrown/returned

**DO NOT REPORT:**
- Intentional error suppression with a comment explaining why
- Top-level error handlers in main/entry points
- Errors that are logged AND re-raised/propagated
- Expected errors handled as part of normal flow (e.g., file not found -> create file)

---

## state-management

**Focus:** Find state corruption: invalid state transitions, stale state, inconsistent updates.

Look for:
- Partial updates that leave objects in inconsistent state
- State modified in one place but dependents not notified/updated
- Stale references to state that has been replaced
- Invalid state transitions (e.g., closing an already-closed resource)
- Mutable state shared across boundaries without copying

**DO NOT REPORT:**
- Immutable data structures
- State managed by a well-tested framework (Redux, MobX, etc.)
- Local mutable variables that don't escape their scope
- Builder/fluent patterns where partial state is intentional during construction

---

## testing-nothing

**Focus:** Find tests that assert trivially true things, verify mock behavior instead of real behavior, or test language semantics.

Look for:
- Assertions that verify a mock was configured correctly (asserting the mock returns what you told it to return)
- Tests that assert `true == true` or equivalent tautologies
- Tests that verify language built-in behavior (e.g., testing that list.append adds an element)
- Tests where all assertions are against mocked return values, not real computation

**DO NOT REPORT:**
- Tests that verify integration between real components
- Tests that use mocks for external dependencies but assert real logic
- Tests that verify error handling behavior
- Smoke tests that intentionally verify basic connectivity/setup

---

## missing-assertions

**Focus:** Find tests that execute code but don't meaningfully verify the results.

Look for:
- Test functions with no assert/expect statements
- Tests that only verify the code "doesn't throw" without checking return values
- Tests that call functions but discard the results
- Tests with assertions on unrelated values (asserting the wrong thing)

**DO NOT REPORT:**
- Tests that use framework-specific assertion patterns (e.g., shouldThrow, assertRaises)
- Property-based tests where the framework handles assertions
- Tests that verify side effects through mock verification (when the side effect IS the behavior)
- Benchmark or performance tests that intentionally measure rather than assert

---

## over-mocking

**Focus:** Find tests where so much is mocked that no real code is exercised.

Look for:
- Tests where the unit under test has ALL dependencies mocked
- Tests that mock internal methods of the class being tested
- Tests where the mock setup is longer than the actual test
- Tests that mock data access and business logic, leaving nothing real

**DO NOT REPORT:**
- Mocking external services (HTTP, databases, file systems) — that's correct
- Mocking time/clock for deterministic tests
- Mocking at integration boundaries where real calls would be flaky
- Test fixtures that set up realistic test data

---

## brittle-tests

**Focus:** Find tests that test implementation details instead of behavior, breaking when code is refactored.

Look for:
- Tests that assert on exact method call order when order doesn't matter
- Tests that verify private/internal method calls
- Tests that assert on exact string representations that could change
- Tests coupled to specific data structure shapes rather than behavior
- Tests that break when you rename an internal variable

**DO NOT REPORT:**
- Tests that verify public API contracts
- Tests that assert on documented behavior
- Tests for serialization/deserialization where exact format matters
- Snapshot tests (they're intentionally brittle — that's their purpose)

---

## missing-edge-cases

**Focus:** Find tests that only cover the happy path, missing boundary conditions and error cases.

Look for:
- No test for empty input (empty list, empty string, null)
- No test for boundary values (0, -1, MAX_INT, empty collection)
- No test for error/exception paths
- No test for concurrent/parallel execution (if the code is concurrent)
- Single test case where multiple distinct behaviors exist

**DO NOT REPORT:**
- Edge cases that are impossible given the type system (e.g., null in a non-nullable type)
- Edge cases handled by a called function that has its own tests
- Exploratory/example tests that aren't meant to be exhaustive
- Tests for trivial functions where edge cases don't meaningfully differ from happy path
```

**Step 2: Verify the template has all required sections**

Run:
```bash
grep '^## ' prompts/generic.md | sort
```
Expected output (11 sections):
```
## brittle-tests
## error-handling
## logic-errors
## missing-assertions
## missing-edge-cases
## null-safety
## over-mocking
## race-conditions
## resource-leaks
## state-management
## testing-nothing
```

**Commit:** `feat: add generic prompt template with all specialist categories`
<!-- END_TASK_2 -->

<!-- START_SUBCOMPONENT_A (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Create review_file.py

**Verifies:** reviewers.AC2.1, reviewers.AC2.2, reviewers.AC2.3, reviewers.AC2.4

**Files:**
- Create: `scripts/review_file.py`

**Implementation:**

The script has four main functions and a CLI entry point:

1. **`prepend_line_numbers(source: str) -> str`** — Takes raw source code, returns it with `{line_number}| ` prepended to each line. Line numbers are right-justified to the width of the highest line number.

2. **`extract_category_prompt(template_path: str, category: str) -> str`** — Reads a prompt template markdown file, extracts the preamble (everything before the first `## ` heading) and the section matching `## {category}` (from the heading through to the next `## ` heading or end of file). Returns the combined preamble + category section. **Raises ValueError if the category section is not found in the template** — this catches language-specific naming mismatches (e.g., passing `null-safety` to the Rust template which uses `memory-safety`).

3. **`parse_findings(raw_response: str) -> list[dict]`** — Takes the raw LLM response string, attempts to parse it as a JSON array. Handles: valid JSON array (returns it), empty string (returns `[]`), string that contains a JSON array within markdown fences (extracts and parses it), malformed JSON (returns empty array with a warning to stderr).

4. **`review_file(file_path: str, category: str, language: str, api_key: str, base_url: str, model: str) -> list[dict]`** — Orchestrates: reads the file, prepends line numbers, loads prompt template for the language, extracts category section, calls the OpenAI API, parses findings, returns them.

   **API call structure:**
   - System message: the extracted category prompt (preamble + specialist section)
   - User message: the line-numbered source code
   - Temperature: `0` (deterministic review output)
   - The call uses `client.chat.completions.create()` and extracts `response.choices[0].message.content`

5. **CLI entry point** — Uses argparse with:
   - `file_path` (positional) — path to the file to review
   - `--category` (required) — specialist category name
   - `--language` (required) — language key (maps to prompt file)
   - `--api-key` / `REVIEWERS_API_KEY` env var
   - `--base-url` / `REVIEWERS_BASE_URL` env var (default: `https://api.z.ai/api/paas/v4/`)
   - `--model` / `REVIEWERS_MODEL` env var (default: `glm-5`)

   Outputs: JSON array of findings to stdout. Errors to stderr.

**Error handling:**
- Missing API key: print error to stderr, exit code 1
- File not found: print error to stderr, exit code 1
- Category not found in template: print error to stderr, exit code 1
- API connection error: print error to stderr, exit code 2
- API rate limit (429): handled by SDK's built-in retry (`max_retries=3`)
- Malformed API response: return empty findings array, warn on stderr

**Key design decisions:**
- Args take precedence over env vars for API configuration
- `response_format={"type": "json_object"}` is NOT used because not all OpenAI-compatible endpoints support it — instead, the prompt instructs JSON output and `parse_findings` handles extraction
- Prompt template path is resolved as `{script_dir}/../prompts/{language}.md` — relative to the script location, not cwd
- The script does NOT handle rate-limit retries itself in Phase 2 — relies on SDK built-in retry. Phase 6 adds configurable retry behavior.

**Testing:**

Tests must verify each AC listed above:
- reviewers.AC2.1: Call script with a known file and verify output is valid JSON with line numbers matching the source file
- reviewers.AC2.2: Call `extract_category_prompt` with the generic template and each category name, verify it returns the correct section content
- reviewers.AC2.3: Run script without API key set, verify it exits with code 1 and prints an error message to stderr
- reviewers.AC2.4: Call `parse_findings` with empty string, malformed JSON, JSON wrapped in markdown fences, and valid JSON — verify correct handling of each

Since the API call is an external dependency, AC2.1 is verified operationally (manual run against real API). AC2.2, AC2.3, AC2.4 are verified with unit tests on the pure functions.

Test file: `tests/test_review_file.py`

**Verification:**
Run: `.venv/bin/python3 -m pytest tests/test_review_file.py -v`
Expected: All tests pass

**Commit:** `feat: add review_file.py with prompt extraction and JSON parsing`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify script end-to-end (operational)

**Verifies:** reviewers.AC2.1 (operational verification)

**Step 1: Create a small test fixture file**

Create `tests/fixtures/sample.py`:
```python
def greet(name):
    print("Hello, " + name)
    return name.upper()
```

**Step 2: Run review_file.py with a dry-run check (no API key needed)**

Run:
```bash
REVIEWERS_API_KEY="" .venv/bin/python3 scripts/review_file.py tests/fixtures/sample.py --category logic-errors --language generic 2>&1
```
Expected: Error message about missing API key, exit code 1

**Step 3: Verify line numbering output (add a `--dry-run` flag check or test the function directly)**

Run:
```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0, 'scripts')
from review_file import prepend_line_numbers
code = open('tests/fixtures/sample.py').read()
print(prepend_line_numbers(code))
"
```
Expected:
```
1| def greet(name):
2|     print("Hello, " + name)
3|     return name.upper()
```

**Step 4: Verify prompt extraction**

Run:
```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0, 'scripts')
from review_file import extract_category_prompt
prompt = extract_category_prompt('prompts/generic.md', 'logic-errors')
print('Contains preamble:', 'Output format' in prompt)
print('Contains category:', 'logic-errors' in prompt.lower() or 'Logic' in prompt)
print('Length:', len(prompt))
"
```
Expected: Both checks print `True`, length is > 100 characters

**Commit:** `test: add test fixture and verify review_file.py functions`
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->
