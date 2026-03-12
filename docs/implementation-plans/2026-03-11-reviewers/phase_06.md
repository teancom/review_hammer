# Review Hammer Implementation Plan — Phase 6: Rate Limiting and Robustness

**Goal:** Reliable operation under API rate limits and error conditions

**Architecture:** Enhances `review_file.py` with explicit retry logic beyond the SDK's built-in retry, configurable timeout per API call, and a concurrency semaphore. Enhances the orchestrator skill with large-repo confirmation flow. Enhances the collector agent with per-specialist timeout handling so one failing specialist doesn't block the whole file review.

**Tech Stack:** Python (review_file.py enhancements), Claude Code skill/agent markdown updates

**Scope:** 6 phases from original design (this is phase 6 of 6)

**Codebase verified:** 2026-03-11 — `review_file.py` exists from Phase 2 with basic OpenAI SDK usage. SDK provides built-in `max_retries` parameter (default 2) which handles 429 retries with exponential backoff. Phase 6 adds explicit retry logic on top for more control and logging.

---

## Acceptance Criteria Coverage

This phase implements:

### reviewers.AC6: Robustness under real-world conditions
- **reviewers.AC6.1 Success:** 429 rate limit errors are retried with backoff
- **reviewers.AC6.2 Success:** Individual specialist timeout doesn't kill the whole review
- **reviewers.AC6.3 Success:** Large repo (100+ files) prompts user for confirmation before proceeding

**Verifies: None** — This is robustness hardening. Verification is operational: trigger rate limits, timeouts, and large repo flows to confirm correct behavior.

---

<!-- START_TASK_1 -->
### Task 1: Add explicit retry and timeout to review_file.py

**Files:**
- Modify: `scripts/review_file.py`

**Implementation:**

Add the following enhancements to `review_file.py`:

**1. Configurable retry with exponential backoff (AC6.1)**

Replace or augment the SDK's built-in retry with explicit retry logic that provides visibility:

```python
import time
import sys

MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 60.0  # seconds
```

In the `review_file` function, wrap the API call in a retry loop:
- On `RateLimitError`: log to stderr with retry count and backoff duration, sleep with exponential backoff (1s, 2s, 4s, 8s, 16s capped at 60s), retry
- On `APITimeoutError`: log to stderr, retry up to MAX_RETRIES
- On `APIConnectionError`: log to stderr, retry up to MAX_RETRIES
- On `AuthenticationError`: log to stderr, do NOT retry, exit with code 1
- After MAX_RETRIES exhausted: log final error to stderr, return empty findings array (don't crash — let other specialists continue)

Also set `max_retries=0` on the OpenAI client to disable SDK-level retry (we handle it ourselves for better logging).

**2. Configurable timeout per API call (AC6.2)**

Add a `--timeout` CLI argument (default: 120 seconds) and pass it to the OpenAI client:

```python
client = OpenAI(
    base_url=base_url,
    api_key=api_key,
    timeout=timeout,
    max_retries=0,  # We handle retries ourselves
)
```

**3. Exit code conventions**

- Exit 0: findings returned (even if empty array)
- Exit 1: configuration error (missing API key, file not found, category not found)
- Exit 2: all retries exhausted (network/rate-limit failure) — but still outputs `[]` to stdout so the collector can continue

**Step 1: Modify review_file.py with retry and timeout logic**

Apply the changes described above to the existing `review_file.py`.

**Step 2: Verify retry behavior (no API key needed)**

Run:
```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0, 'scripts')
# Verify the retry constants exist
from review_file import MAX_RETRIES, INITIAL_BACKOFF, MAX_BACKOFF
print(f'MAX_RETRIES={MAX_RETRIES}, INITIAL_BACKOFF={INITIAL_BACKOFF}, MAX_BACKOFF={MAX_BACKOFF}')
assert MAX_RETRIES == 5
assert INITIAL_BACKOFF == 1.0
assert MAX_BACKOFF == 60.0
print('OK')
"
```
Expected: Constants verified

**Step 3: Verify timeout CLI argument**

Run:
```bash
.venv/bin/python3 scripts/review_file.py --help 2>&1 | grep -i timeout
```
Expected: Shows `--timeout` argument in help output

**Commit:** `feat: add explicit retry with backoff and configurable timeout`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update collector agent with per-specialist timeout handling

**Files:**
- Modify: `agents/file-reviewer.md`

**Implementation:**

Update the file-reviewer agent instructions to handle per-specialist failures gracefully (AC6.2):

1. When calling `review_file.py` for each category, set a timeout on the Bash invocation (e.g., 180 seconds per specialist)
2. If a specialist call times out or returns a non-zero exit code:
   - Log which specialist failed and why (to the agent's output)
   - Continue to the next specialist — do NOT abort the entire file review
   - Mark the failed specialist in the output: `"failed_categories": ["race-conditions"]`
3. If ALL specialists fail, still return a valid JSON structure with empty findings and all categories in `failed_categories`

Add to the agent instructions a section like:

```markdown
## Error Handling

If a specialist invocation fails (non-zero exit, timeout, or unparseable output):
1. Note the failure in your output under `failed_categories`
2. Continue to the next specialist
3. NEVER abort the entire review because one specialist failed

The consolidated output should include:
- `"failed_categories"`: array of category names that failed
- `"error_details"`: object mapping failed category to error description
```

**Step 1: Modify agents/file-reviewer.md**

Add the error handling section to the agent's markdown body.

**Step 2: Verify the error handling instructions are present**

Run:
```bash
grep -c 'failed_categories\|Error Handling\|Continue to the next' agents/file-reviewer.md
```
Expected: Count ≥ 3

**Commit:** `feat: add per-specialist timeout handling to collector agent`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update orchestrator skill with large-repo confirmation flow

**Files:**
- Modify: `skills/fleet-review/SKILL.md`

**Implementation:**

Update the file enumeration section of the skill to handle large repos (AC6.3):

After enumerating files, if the count exceeds 100:

1. Calculate estimated API calls: `file_count × avg_categories_per_file` (assume 6 for estimation)
2. Present to the user:
   ```
   This target contains {file_count} reviewable files, which will require approximately {api_calls} API calls.

   Options:
   - Proceed with all {file_count} files
   - Review only files changed in git (git diff)
   - Narrow scope - specify a subdirectory or file pattern
   - Cancel
   ```
3. Use AskUserQuestion tool to get user decision
4. If "git diff" selected: use `git diff --name-only` to get changed files only, then filter to supported extensions
5. If "narrow scope": ask user for path or pattern, re-enumerate
6. If "cancel": stop

Also add concurrency guidance in the agent dispatch section:
- Read `REVIEWERS_MAX_CONCURRENT` env var (default 3)
- Note in skill instructions: "Dispatch agents in batches, waiting for each batch to complete before starting the next. Batch size = REVIEWERS_MAX_CONCURRENT value."

**Step 1: Modify skills/fleet-review/SKILL.md**

Add the large-repo flow and concurrency guidance sections.

**Step 2: Verify the large-repo flow is documented**

Run:
```bash
grep -c '100\|large repo\|confirmation\|REVIEWERS_MAX_CONCURRENT\|concurrency' skills/fleet-review/SKILL.md
```
Expected: Count ≥ 3

**Commit:** `feat: add large-repo confirmation and concurrency control`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: End-to-end robustness verification

**Step 1: Verify review_file.py handles missing API key gracefully**

Run:
```bash
REVIEWERS_API_KEY="" .venv/bin/python3 scripts/review_file.py scripts/review_file.py --category logic-errors --language python 2>&1
echo "Exit code: $?"
```
Expected: Error message about missing API key, exit code 1

**Step 2: Verify review_file.py handles connection failure gracefully**

Run:
```bash
REVIEWERS_API_KEY="fake-key" REVIEWERS_BASE_URL="http://localhost:1" .venv/bin/python3 scripts/review_file.py scripts/review_file.py --category logic-errors --language python --timeout 5 2>&1
echo "Exit code: $?"
```
Expected: Connection error with retry attempts logged to stderr, eventually outputs `[]` to stdout, exit code 2

**Step 3: Verify all tests still pass**

Run: `.venv/bin/python3 -m pytest tests/ -v`
Expected: All tests pass

**Step 4: Verify complete plugin structure**

Run:
```bash
echo "=== Plugin structure ==="
find .claude-plugin hooks scripts prompts agents skills tests -type f | grep -v __pycache__ | sort

echo "=== Prompt file count ==="
ls prompts/*.md | wc -l

echo "=== All JSON configs valid ==="
python3 -m json.tool .claude-plugin/plugin.json > /dev/null && echo "plugin.json: OK"
python3 -m json.tool hooks/hooks.json > /dev/null && echo "hooks.json: OK"
```
Expected: Complete file listing, 12 prompt files, both JSON files valid

No commit for this task — it's a verification step only.
<!-- END_TASK_4 -->
