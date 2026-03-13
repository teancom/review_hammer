# Review Calibration Design

## Summary

Review Hammer's prompt templates encode explicit exclusions for patterns that are safe in context — fire-and-forget channel sends, `#[repr(transparent)]` construction in tests, `unsafe impl Send + Sync` on MTA COM objects — but there is currently no automated way to verify that those exclusions are correctly scoped. A prompt change could accidentally suppress real bugs that merely resemble excluded patterns, or re-introduce false positives on the clean patterns. This design builds a calibration system that catches both failure modes.

The approach is a three-tier test corpus paired with a standalone runner. The corpus organizes known-good code (extracted from real codebases), synthetic buggy code, and adversarial code into file pairs: a source file and a companion metadata file declaring what the reviewer is expected to find. The runner invokes `review_file.py` against each corpus file via the real Z.AI API, applies an automated pass/fail gate based on whether findings were expected, and produces a structured report for an Opus judge pass to verify semantic correctness. The Rust corpus seeds the system with the documented false positives that motivated this work, and the file-based structure makes adding patterns for new languages or new false positive reports a one-step operation.

## Definition of Done

Build a test corpus and runner that validates prompt accuracy for both false positives (clean code incorrectly flagged) and false negatives (real bugs missed, especially near exclusion boundaries). The system uses real extracted code for clean patterns, synthetic code for planted bugs, and adversarial cases that resemble exclusion patterns but contain real issues. A standalone runner executes reviews against the corpus via the real API and validates results with an automated gate plus an always-on Opus judge pass for semantic verification.

**Deliverables:**
1. `tests/corpus/` directory with per-language subdirectories containing clean-pattern, planted-bug, and adversarial source files with companion metadata
2. `scripts/test_corpus.py` standalone runner with two-layer validation (automated gate + Opus judge)
3. Rust corpus seeded from ~15 documented false positives plus synthetic bugs and adversarial cases
4. Structure that makes adding new patterns trivial: add source file + metadata, done

## Acceptance Criteria

### review-calibration.AC1: Corpus structure supports all file types
- **review-calibration.AC1.1 Success:** Clean, bug, and adversarial files each have a source file and companion `.json` metadata file in `tests/corpus/{language}/`
- **review-calibration.AC1.2 Success:** Metadata JSON contains `type`, `category`, `language`, `description`, and `expect_empty` fields
- **review-calibration.AC1.3 Failure:** Runner reports clear error when metadata JSON is malformed or missing required fields
- **review-calibration.AC1.4 Edge:** Runner handles empty corpus directory gracefully (no cases found, reports zero results)

### review-calibration.AC2: Runner executes reviews and applies automated gate
- **review-calibration.AC2.1 Success:** Runner discovers all `.json` files under `tests/corpus/`, invokes `review_file.py` for each, and reports pass/fail
- **review-calibration.AC2.2 Success:** Clean files (`expect_empty: true`) pass when reviewer returns `[]`, fail when reviewer returns findings
- **review-calibration.AC2.3 Success:** Bug/adversarial files (`expect_empty: false`) pass when reviewer returns non-empty findings with matching `category`, fail when empty or wrong category
- **review-calibration.AC2.4 Failure:** Runner reports structured failure output including the raw findings JSON for Opus judge review
- **review-calibration.AC2.5 Success:** Runner prints summary line with total pass/fail counts and exits with code 0 (all pass) or 1 (any fail)

### review-calibration.AC3: Rust corpus validates prompt exclusions
- **review-calibration.AC3.1 Success:** Clean pattern files extracted from real code produce zero findings for their category
- **review-calibration.AC3.2 Success:** At least 3 clean pattern files covering distinct exclusions (fire-and-forget channel, repr-transparent construction, MTA COM Send+Sync)
- **review-calibration.AC3.3 Success:** Bug files with planted issues produce findings in the expected category
- **review-calibration.AC3.4 Success:** Adversarial files resembling exclusion patterns but containing real bugs produce findings

### review-calibration.AC4: Adversarial cases prove exclusions are scoped
- **review-calibration.AC4.1 Success:** Each adversarial file has a corresponding clean file testing the same exclusion pattern — the clean version passes, the adversarial version gets flagged
- **review-calibration.AC4.2 Success:** Opus judge confirms adversarial findings semantically match the planted bug description, not a false detection of something else

### review-calibration.AC5: Runner respects Z.AI concurrency limits
- **review-calibration.AC5.1 Success:** Runner executes reviews sequentially (one at a time) by default to stay well within the GLM-5 concurrency limit of 3
- **review-calibration.AC5.2 Edge:** Runner does not hang or fail if a single review times out — reports the timeout and continues to next case

### review-calibration.AC6: Adding new test cases requires no code changes
- **review-calibration.AC6.1 Success:** Adding a new corpus file is: create source file + metadata JSON in the appropriate language directory. No runner modifications needed.

## Glossary

- **Prompt exclusion**: A rule in a category prompt template telling the reviewer to ignore a specific safe pattern. Must be narrowly scoped to avoid hiding real bugs.
- **False positive**: A finding reported for code that is actually safe. Documented Rust false positives are the primary motivation for this system.
- **False negative**: A real bug the reviewer fails to report. Adversarial corpus files catch false negatives caused by over-broad exclusions.
- **Adversarial file**: A synthetic corpus file that superficially resembles an excluded pattern but contains a real bug. Proves exclusions are tightly scoped.
- **Automated gate**: First validation layer. Clean files must return zero findings; bug/adversarial files must return findings with the correct category. No LLM involved.
- **Opus judge pass**: Second validation layer. Claude Opus evaluates whether findings semantically match planted bugs. Runs in-session after the human executes the runner.
- **Corpus**: The collection of source files and companion metadata under `tests/corpus/`, organized by language with three file types: clean, bug, adversarial.
- **`review_file.py`**: Python CLI that sends a source file and specialist category to the Z.AI API and returns a JSON array of findings.
- **PEP 723**: Python standard for inline dependency declarations inside script files, used with `uv run` for automatic dependency management.
- **Z.AI / GLM-5**: External LLM API used for code review. Concurrency limit of 3; runner stays under this by executing sequentially.
- **MTA COM object**: A Windows COM object initialized on a Multi-Threaded Apartment. `unsafe impl Send + Sync` on such types is safe by design but resembles a thread-safety violation.
- **`#[repr(transparent)]`**: Rust attribute guaranteeing a struct has the same memory layout as its single field. Direct construction in tests is the public API, not an implementation detail.
- **Fire-and-forget channel send**: `let _ = tx.send(...)` in a spawned task, deliberately discarding the result. Safe when the receiver may have dropped.

## Architecture

Three-tier test corpus with a standalone runner that exercises `review_file.py` against known-outcome files and reports results for in-session Opus judgment.

**Corpus files** live in `tests/corpus/{language}/` as flat file pairs: a source file (`.rs`, `.py`, `.js`, etc.) and a companion `.json` metadata file. Three file types:

- **Clean** (`clean_*.{ext}`): Extracted from real codebases. Code that exercises a specific prompt exclusion (e.g., fire-and-forget channel send). Must produce zero findings for its category.
- **Bug** (`bug_*.{ext}`): Synthetic files with a planted bug. Must produce at least one finding in the expected category.
- **Adversarial** (`adversarial_*.{ext}`): Synthetic files that resemble an exclusion pattern but contain a real bug (e.g., `let _ =` discarding critical data, not fire-and-forget). Must produce findings — proves exclusions don't over-suppress.

**Metadata JSON** per file:
```json
{
  "type": "clean",
  "category": "error-handling",
  "language": "rust",
  "description": "Fire-and-forget channel send in spawned background task",
  "expect_empty": true
}
```

**Runner** (`scripts/test_corpus.py`): Standalone script invoked via `uv run`. Discovers test cases by globbing `tests/corpus/**/*.json`, executes `review_file.py` for each, applies automated gate, and outputs a structured pass/fail report. The Opus judge pass happens in-session — the human runs the script, then Claude Code reads the output and evaluates semantic correctness of findings.

**Data flow:**
```
scripts/test_corpus.py
  ├── glob tests/corpus/**/*.json → discover cases
  ├── for each case:
  │   ├── uv run scripts/review_file.py {source} --category {cat} --language {lang}
  │   ├── parse findings JSON
  │   └── automated gate: expect_empty? → check empty/non-empty + category match
  └── output: structured report (pass/fail per case, raw findings for failures)
```

**Corpus files must be syntactically valid** in their language — correct types, proper signatures, matching braces. Not full compilable programs (no imports/main), but well-formed excerpts that wouldn't trigger "syntax error" findings from the reviewer.

## Existing Patterns

Investigation found existing test infrastructure in `tests/test_review_file.py` using pytest with `unittest.mock`. The corpus runner does NOT integrate with pytest — it's a standalone script because it hits the real Z.AI API and costs money. This follows the existing pattern of `scripts/review_file.py` as a standalone `uv run` script with PEP 723 inline dependencies.

The runner reuses `review_file.py` directly via subprocess rather than importing it, matching how the plugin's file-reviewer agent invokes it.

No existing corpus or golden-file infrastructure exists in the codebase. This is a new pattern.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Corpus Structure and Runner

**Goal:** Create the corpus directory structure, metadata schema, and test runner script.

**Components:**
- `tests/corpus/` directory with `rust/` subdirectory
- `scripts/test_corpus.py` — standalone runner with discovery, execution, automated gate, and reporting
- PEP 723 inline dependencies (no external deps beyond stdlib needed — just subprocess + json + glob)

**Dependencies:** None

**Done when:** Runner can discover `.json` metadata files, invoke `review_file.py` for each, apply automated gate (empty/non-empty + category match), and output a structured pass/fail report. Verified with a trivial placeholder corpus file.

Covers: review-calibration.AC1.1, review-calibration.AC1.2, review-calibration.AC2.1, review-calibration.AC2.2, review-calibration.AC2.3, review-calibration.AC5.1, review-calibration.AC5.2
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Rust Clean Pattern Files

**Goal:** Extract clean-pattern corpus files from real codebases (sendspin-rs, desktop-app) covering documented false positives.

**Components:**
- `tests/corpus/rust/clean_fire_and_forget_channel.rs` + `.json` — `let _ = tx.send()` in spawned task (error-handling)
- `tests/corpus/rust/clean_repr_transparent.rs` + `.json` — `#[repr(transparent)]` tuple struct construction in tests (brittle-tests)
- `tests/corpus/rust/clean_mta_com_send_sync.rs` + `.json` — `unsafe impl Send + Sync` for MTA COM object (race-conditions)

**Dependencies:** Phase 1 (runner exists to validate)

**Done when:** All 3 clean files pass the automated gate (return `[]` for their category). Runner confirms no false positives.

Covers: review-calibration.AC3.1, review-calibration.AC3.2
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Rust Bug and Adversarial Files

**Goal:** Create synthetic bug files and adversarial files that test exclusion boundaries.

**Components:**
- `tests/corpus/rust/bug_unwrap_user_input.rs` + `.json` — `unwrap()` on network input in production handler (error-handling)
- `tests/corpus/rust/bug_unguarded_static_mut.rs` + `.json` — mutable static accessed from threads without sync (race-conditions)
- `tests/corpus/rust/adversarial_let_ignore_result.rs` + `.json` — `let _ = file.write()` in request handler where data loss occurs (error-handling)
- `tests/corpus/rust/adversarial_unsafe_send_sync.rs` + `.json` — `unsafe impl Send + Sync` on non-COM type without synchronization (race-conditions)
- `tests/corpus/rust/adversarial_private_struct_construction.rs` + `.json` — direct construction of non-repr-transparent struct with invariants (brittle-tests)

**Dependencies:** Phase 1 (runner exists), Phase 2 (clean counterparts exist for comparison)

**Done when:** All 5 files pass automated gate (return non-empty findings with correct category). Opus judge confirms findings semantically match the planted bugs.

Covers: review-calibration.AC3.3, review-calibration.AC3.4, review-calibration.AC4.1, review-calibration.AC4.2
<!-- END_PHASE_3 -->

## Additional Considerations

**Adding new languages:** Create `tests/corpus/{language}/` directory and add file pairs. No runner changes needed — it discovers by globbing. Start with Rust, expand to Python and Swift based on real false positive feedback from fleet reviews.

**API cost:** Each corpus file-category pair is one Z.AI API call. Full Rust seed (8 files) costs 8 calls. Keep corpus small (2-3 files per type per language) to control cost.

**Non-determinism:** LLM output varies between runs. A clean file might occasionally produce a finding, or a bug file might miss. If flakiness becomes a problem, consider running each case 2-3 times and using majority vote. Not needed initially — temperature=0 provides reasonable consistency.
