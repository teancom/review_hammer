# Test Hammer Design

## Summary

Test Hammer extends the existing review-hammer code review pipeline with a dedicated test-suggestion capability. Where review-hammer identifies problems in production code, test-hammer pairs each production file with its corresponding test files (discovered by naming convention), sends both to an external LLM, and returns up to three high-value test suggestions per file. It is designed to work both as a standalone `/test-hammer <path>` skill and as an integrated component within `/review-hammer`, where it replaces the existing `missing-edge-cases` category.

The implementation reuses review-hammer's infrastructure — the same `review_file.py` script, the same prompt template pattern, the same Haiku agent dispatch model, and the same Opus judge pass for deduplication and ranking — with one meaningful extension: a `--test-context` flag that feeds existing test file content into the prompt alongside the production source. Language-specific `## test-suggestions` sections in each prompt file define both what to suggest (state transitions, error paths, business logic boundaries, integration seams) and explicit exclusion lists to prevent the LLM from recommending tests that merely validate language semantics or repeat what the type system already guarantees.

## Definition of Done

1. **A standalone `/test-hammer <path>` skill** that analyzes production code, reads corresponding test files, and suggests up to 3 high-value tests per file — focusing on what matters (state transitions, error paths, integration seams, business logic boundaries) while aggressively excluding language-level trivia.

2. **Integration with review-hammer** where test-hammer replaces the `missing-edge-cases` category for production files, running within the existing batch/concurrency framework.

3. **Language-specific prompt templates** (same pattern as review-hammer) with explicit DO NOT SUGGEST exclusion lists to prevent garbage suggestions.

4. **Calibration corpus** (same pattern as review-calibration) to validate prompt accuracy — clean files that should produce zero suggestions, and files with genuine test gaps that should produce targeted suggestions.

## Acceptance Criteria

### test-hammer.AC1: Standalone `/test-hammer <path>` skill
- **test-hammer.AC1.1 Success:** `/test-hammer <file>` analyzes a single production file and returns up to 3 test suggestions in severity-ranked markdown report
- **test-hammer.AC1.2 Success:** `/test-hammer <directory>` enumerates all production files, pairs each with test files, and produces a combined report
- **test-hammer.AC1.3 Success:** Test-suggester agent invokes `review_file.py` with `--test-context` flag and returns JSON findings
- **test-hammer.AC1.4 Success:** Opus judge pass deduplicates, verifies, and ranks suggestions before final report
- **test-hammer.AC1.5 Edge:** When no test file exists for a production file, agent is informed "no existing tests found" and suggestions focus on highest-value tests

### test-hammer.AC2: Review-hammer integration
- **test-hammer.AC2.1 Success:** `/review-hammer <path>` dispatches both file-reviewer and test-suggester agents from the same batch queue
- **test-hammer.AC2.2 Success:** Test suggestions appear in the final review-hammer report alongside other findings
- **test-hammer.AC2.3 Success:** `missing-edge-cases` category no longer runs for production files
- **test-hammer.AC2.4 Success:** Global `REVIEWERS_MAX_CONCURRENT` limit is respected across both agent types (2 means 2 total, not 2 per type)

### test-hammer.AC3: Language-specific prompt templates
- **test-hammer.AC3.1 Success:** `prompts/rust.md` contains `## test-suggestions` section with Rust-specific WHAT TO SUGGEST and DO NOT SUGGEST lists
- **test-hammer.AC3.2 Success:** `prompts/generic.md` contains `## test-suggestions` section as fallback
- **test-hammer.AC3.3 Success:** DO NOT SUGGEST lists prevent suggestions for language-level trivia (e.g., Rust: testing Default/From/Into for newtypes; Python: testing `__init__` assignment)
- **test-hammer.AC3.4 Success:** All 12 language prompt files contain `## test-suggestions` sections with language-appropriate exclusion lists

### test-hammer.AC4: Calibration corpus
- **test-hammer.AC4.1 Success:** Clean corpus files (well-tested code) produce zero test suggestions
- **test-hammer.AC4.2 Success:** Gap corpus files (untested code with genuine test gaps) produce suggestions targeting the right areas
- **test-hammer.AC4.3 Success:** Adversarial corpus files (trivial code that tempts garbage suggestions) produce zero suggestions

### test-hammer.AC5: Cross-cutting behaviors
- **test-hammer.AC5.1 Success:** `hooks/auto-approve-review.sh` auto-approves test-suggester's `review_file.py` invocations with `--test-context` flag (no permission prompts)
- **test-hammer.AC5.2 Success:** Hard cap of 3 suggestions per file is enforced in the prompt template
- **test-hammer.AC5.3 Edge:** Large test files exceeding 500 lines are truncated with a warning before being passed to the LLM

## Glossary

- **review-hammer**: The existing Claude Code plugin that performs multi-category LLM-powered code review. Test-hammer is built as a parallel pipeline within the same plugin.
- **test-hammer**: The new capability being designed — a pipeline that suggests high-value tests for production code by pairing it with existing test files and sending both to an LLM.
- **Haiku agent**: A Claude Haiku subagent defined by a markdown file in `agents/`. Each agent handles one production file and runs one or more review categories. Haiku is used for per-file work; Opus is used for the final judge pass.
- **Opus judge pass**: A final step where Claude Opus reviews all collected findings to deduplicate, verify line numbers, filter false positives, and rank by severity before the report is presented.
- **GLM-5**: The external LLM used for analysis, accessed via a Z.AI OpenAI-compatible API endpoint. Subject to a concurrency limit managed by `REVIEWERS_MAX_CONCURRENT`.
- **`review_file.py`**: The Python script that extracts a category-specific section from a language prompt template, builds a prompt with the source file content, sends it to GLM-5, and returns findings as JSON.
- **`--test-context`**: A new CLI flag being added to `review_file.py` that includes the content of an existing test file in the prompt, giving the LLM visibility into what is already tested.
- **`REVIEWERS_MAX_CONCURRENT`**: Environment variable that caps the number of simultaneous agent invocations across the entire pipeline. Applies globally — shared between file-reviewer and test-suggester agents, not per agent type.
- **`uv run`**: A Python tool runner that installs and manages dependencies declared via PEP 723 inline metadata directly in the script file, with no separate virtual environment required.
- **PEP 723**: A Python standard for declaring script dependencies as inline metadata comments. Allows `uv run` to resolve and install dependencies on first run without a separate `requirements.txt` or `pyproject.toml`.
- **calibration corpus**: A set of test fixture files (clean, gap, and adversarial) used to validate prompt quality. Clean files should produce zero findings; gap files should produce findings in the right areas; adversarial files should resist generating garbage suggestions.
- **adversarial corpus file**: A source file designed to tempt the LLM into making low-value suggestions (e.g., trivial code with obvious type guarantees). Used to verify the DO NOT SUGGEST exclusion lists in prompts are working.
- **integration seam**: A boundary between two components where untested assumptions are especially likely to cause runtime failures.
- **property-based test**: A test that verifies a general invariant (e.g., roundtrip encode/decode, idempotency) rather than a specific input/output pair.
- **PreToolUse hook / auto-approve hook**: A Claude Code hook that intercepts tool calls before they are made and auto-approves ones matching a pattern, preventing repetitive permission prompts during batch reviews.
- **`missing-edge-cases`**: The existing review-hammer category for production files that test-hammer replaces. Once integration is complete, this category is retired.
- **convention-based test file pairing**: The orchestrator's logic for finding test files by checking a prioritized list of naming conventions (e.g., `foo.py` → `test_foo.py`, `tests/test_foo.py`) rather than requiring explicit configuration.

## Architecture

Test-hammer is a parallel pipeline to review-hammer sharing the same infrastructure (`review_file.py`, prompt templates, concurrency controls) but serving a different purpose: suggesting high-value tests for production code.

**Components:**
- `skills/test-hammer/SKILL.md` — standalone orchestrator skill, mirrors review-hammer's structure
- `agents/test-suggester.md` — Haiku agent that runs `test-suggestions` category against a single production file plus its test files
- `prompts/{language}.md` — extended with `## test-suggestions` section per language (lives in existing prompt files)
- `scripts/review_file.py` — extended with `--test-context <path>` flag to include existing test file content in the prompt

**Data flow:**
1. Orchestrator enumerates production files, pairs each with test files via convention-based discovery
2. Dispatches test-suggester agents in batches (respecting global `REVIEWERS_MAX_CONCURRENT`)
3. Each agent runs `uv run review_file.py <source> --category test-suggestions --language <lang> --test-context <test_file>`
4. `review_file.py` reads both source and test file, builds combined prompt, sends to GLM-5
5. GLM-5 returns up to 3 suggestions (hard cap enforced in prompt)
6. Orchestrator collects all suggestions, runs Opus judge pass for dedup, verification, and ranking
7. Final severity-ranked report presented

**Integration with review-hammer:**
When running from review-hammer, test-suggester agents replace the `missing-edge-cases` category for production files. Both file-reviewer and test-suggester agents draw from the same global batch queue — `REVIEWERS_MAX_CONCURRENT=2` means 2 total agents hitting the API, not 2 per type. The orchestrator interleaves both agent types into the same batched queue.

**Standalone mode (`/test-hammer <path>`):**
Stripped-down review-hammer that runs one category instead of six. Same phases: enumerate files, detect languages, pair with tests, dispatch agents, collect results, Opus judge pass, present report.

**Test file discovery (orchestrator-managed):**
Convention-based pairing checked in order, first match wins:

| Language | Production File | Test File Pattern(s) |
|----------|----------------|---------------------|
| Rust | `src/foo.rs` | `tests/foo.rs`, `src/foo_test.rs` (inline `#[cfg(test)]` detected by agent) |
| Python | `foo.py` | `test_foo.py`, `tests/test_foo.py`, `foo_test.py` |
| Go | `foo.go` | `foo_test.go` (same directory) |
| TS/JS | `foo.ts` | `foo.test.ts`, `foo.spec.ts`, `__tests__/foo.test.ts` |
| Java/Kotlin | `Foo.java` | `FooTest.java`, `FooSpec.java` (in test source tree) |
| Others | `foo.ext` | `test_foo.ext`, `foo_test.ext`, `foo.test.ext` |

If no test file found, the agent is told "no existing tests found" — strong signal that suggestions should focus on highest-value tests. If multiple test files match, all are passed.

**Prompt structure per language:**
Each language's `## test-suggestions` section contains:

- **WHAT TO SUGGEST** (prioritized):
  1. State transition coverage — code with distinct states where transitions aren't tested
  2. Error path coverage — error handling paths with no corresponding error-case tests
  3. Business logic boundaries — domain-specific boundary conditions where behavior changes
  4. Integration seam tests — boundaries between components where assumptions could diverge
  5. Property-based test opportunities — functions with clear invariants (roundtrip, commutativity, idempotency)

- **DO NOT SUGGEST** (language-specific exclusion lists):
  - Tests that validate language semantics (Option can be None, Vec can be empty)
  - Tests that duplicate what the type system/compiler enforces
  - Tests for trivial getters/setters/accessors with no logic
  - Tests that merely exercise code for coverage without meaningful assertions
  - Tests for framework-provided behavior
  - Tests for pure data structures with no logic
  - Tests already covered in the existing test file(s) provided
  - Language-specific additions (e.g., Rust: don't suggest testing Default/From/Into for newtypes; Python: don't suggest testing __init__ assignment, dataclass defaults; Go: don't suggest testing errors.Is/errors.As, interface satisfaction)

- **Output format:** Same JSON schema as review-hammer findings (`{lines, severity, category, description, impact, confidence}`) where `description` explains what to test and why it matters, not how to implement it

## Existing Patterns

This design follows established patterns from the existing review-hammer pipeline:

- **Prompt templates** in `prompts/{language}.md` with `## category-name` sections extracted by `review_file.py`'s `extract_category_prompt()` function
- **Agent dispatch** via orchestrator skill dispatching Haiku agents in batches with `REVIEWERS_MAX_CONCURRENT` concurrency control
- **Script invocation** via `uv run scripts/review_file.py` with PEP 723 inline metadata (no venv needed)
- **Auto-approve hook** in `hooks/auto-approve-review.sh` matching command patterns to eliminate permission prompts
- **Calibration corpus** in `tests/corpus/{language}/` with paired source + `.json` metadata files validated by `scripts/test_corpus.py`

New pattern introduced: `--test-context` flag on `review_file.py` to include additional file content in the prompt. This diverges from the current single-file-in, findings-out model but is the minimal extension needed — the script already reads the source file, now it optionally reads a second file.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Prompt Templates and Script Extension

**Goal:** Add `test-suggestions` category to language prompt templates and extend `review_file.py` to accept test context

**Components:**
- `prompts/rust.md` — add `## test-suggestions` section with Rust-specific WHAT TO SUGGEST and DO NOT SUGGEST lists
- `prompts/generic.md` — add `## test-suggestions` section as fallback for unsupported languages
- `scripts/review_file.py` — add `--test-context` CLI argument, read test file content, include in prompt
- `tests/test_review_file.py` — unit tests for `--test-context` flag handling

**Verifies:** test-hammer.AC3.1, test-hammer.AC3.2, test-hammer.AC3.3

**Dependencies:** None

**Done when:** `uv run scripts/review_file.py <source> --category test-suggestions --language rust --test-context <test_file>` returns JSON suggestions. Unit tests pass for the new flag.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Calibration Corpus for Test Suggestions

**Goal:** Build test corpus validating prompt accuracy for test suggestions

**Components:**
- `tests/corpus/rust/` — clean files (well-tested code, expect zero suggestions), gap files (untested code, expect suggestions), adversarial files (trivial code that tempts garbage suggestions, expect zero)
- `scripts/test_corpus.py` — extend or create parallel runner for test-suggestions category with adapted gating logic
- Corpus metadata `.json` files with `category: "test-suggestions"` and appropriate `expect_empty` values

**Verifies:** test-hammer.AC4.1, test-hammer.AC4.2, test-hammer.AC4.3

**Dependencies:** Phase 1

**Done when:** Corpus runner passes all test-suggestion cases. Clean files produce zero suggestions. Gap files produce suggestions in the right areas. Adversarial files resist garbage suggestions.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Test-Suggester Agent

**Goal:** Create dedicated Haiku agent for test suggestion dispatch

**Components:**
- `agents/test-suggester.md` — agent definition following `agents/file-reviewer.md` pattern, restricted to Bash tool, receives FILE_PATH + LANGUAGE + PLUGIN_ROOT + TEST_FILES
- `hooks/auto-approve-review.sh` — extend to auto-approve test-suggester's `review_file.py` invocations with `--test-context`

**Verifies:** test-hammer.AC1.3, test-hammer.AC5.1

**Dependencies:** Phase 1

**Done when:** Agent can be dispatched manually and returns JSON test suggestions for a production file with test context.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Standalone Skill

**Goal:** Create `/test-hammer <path>` orchestrator skill with file enumeration, test file pairing, agent dispatch, and Opus judge pass

**Components:**
- `skills/test-hammer/SKILL.md` — orchestrator skill with phases: input validation, file enumeration, language detection, test file discovery and pairing, agent dispatch with concurrency control, Opus judge pass, report presentation
- Test file discovery logic (convention-based pairing rules documented in Architecture)

**Verifies:** test-hammer.AC1.1, test-hammer.AC1.2, test-hammer.AC1.4, test-hammer.AC1.5, test-hammer.AC2.1, test-hammer.AC2.2, test-hammer.AC5.2

**Dependencies:** Phase 3

**Done when:** `/test-hammer <file-or-directory>` produces a severity-ranked report of test suggestions with Opus judge filtering. Respects `REVIEWERS_MAX_CONCURRENT`.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Review-Hammer Integration

**Goal:** Integrate test-hammer into review-hammer pipeline, replacing `missing-edge-cases` for production files

**Components:**
- `skills/review-hammer/SKILL.md` — modify production file category dispatch to drop `missing-edge-cases`, add test-suggester agent dispatch alongside file-reviewer agents in same batch queue
- `agents/file-reviewer.md` — remove `missing-edge-cases` from production file category list
- `prompts/{language}.md` — remove `## missing-edge-cases` sections (replaced by `## test-suggestions`)

**Verifies:** test-hammer.AC2.3, test-hammer.AC2.4, test-hammer.AC5.3

**Dependencies:** Phase 4

**Done when:** `/review-hammer <path>` dispatches both file-reviewer and test-suggester agents from the same batch queue, with test suggestions appearing in the final report alongside other findings. `missing-edge-cases` no longer runs for production files. Global concurrency limit is respected across both agent types.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Additional Language Prompts

**Goal:** Add `## test-suggestions` sections to remaining language prompt templates

**Components:**
- `prompts/python.md`, `prompts/go.md`, `prompts/typescript.md`, `prompts/javascript.md`, `prompts/java.md`, `prompts/kotlin.md`, `prompts/swift.md`, `prompts/cpp.md`, `prompts/c.md`, `prompts/csharp.md` — each gets language-specific WHAT TO SUGGEST and DO NOT SUGGEST lists

**Verifies:** test-hammer.AC3.4

**Dependencies:** Phase 2 (calibration patterns established)

**Done when:** All 12 language prompt files contain `## test-suggestions` sections with language-appropriate exclusion lists.
<!-- END_PHASE_6 -->

## Additional Considerations

**Concurrency is global.** The single most important implementation constraint. `REVIEWERS_MAX_CONCURRENT` applies across all agent types — file-reviewer and test-suggester share the same pool. The orchestrator must interleave both agent types into one batch queue. This applies both when review-hammer dispatches test-hammer internally and when test-hammer runs standalone (it still reads the same env var).

**Test file size.** Large test files may push the combined prompt (source + test file) past GLM-5's context window. `review_file.py` should truncate test file content with a warning if it exceeds a reasonable limit (e.g., 500 lines). The prompt should instruct the LLM to work with what it has.

**No test file is valid signal.** When no test file is found for a production file, the agent should know this. "No existing tests" means every suggestion is potentially valuable — but the hard cap of 3 still applies, forcing prioritization of the highest-value tests.
