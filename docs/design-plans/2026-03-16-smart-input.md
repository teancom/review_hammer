# Smart Input Design

## Summary

Review Hammer currently sends entire source files to the LLM API for review. For large files, this wastes API quota reviewing unchanged code and can exceed the API's input size limits entirely. This design adds diff-aware input assembly: when a user reviews "this commit", "this branch", or a dirty file, the plugin extracts only the changed hunks from the git diff, expands each hunk with surrounding context lines, and sends that focused payload to the LLM — reducing review input from thousands of lines to hundreds in typical cases.

The implementation spans three layers. The skill layer gains the ability to classify natural-language arguments into one of five input modes (commit, branch, dirty file, clean file, or directory) and resolve them to concrete git refs. The agent layer gains a passthrough field (`DIFF_BASE`) that carries the resolved ref down to the script. The script layer does the actual work: running `git diff`, parsing unified diff output, assembling a context-enriched message with original file line numbers preserved, and — when the assembled content is too large — automatically chunking it, reviewing each chunk independently, and merging the findings. All changes are additive and backward compatible.

## Definition of Done

1. `/review-hammer this commit` and `/review-hammer this branch` review only the diff (with file headers + context lines), with the skill interpreting natural language arguments to determine the right git ref
2. `/review-hammer <file>` reviews uncommitted changes as a diff if the file is dirty, or the full file if clean
3. `/review-hammer <directory>` applies the same per-file logic within the directory
4. Large inputs (diff or full file) are automatically chunked into reviewable segments
5. `review_file.py` gains a diff input mode that preserves original-file line numbers in findings
6. No prompt template changes — diff format instructions are injected at runtime by `review_file.py`
7. test-hammer stays full-file only but gains chunking for large files

## Acceptance Criteria

### smart-input.AC1: Commit and branch review via natural language
- **smart-input.AC1.1 Success:** `/review-hammer this commit` reviews only files changed in HEAD, using diff + context
- **smart-input.AC1.2 Success:** `/review-hammer this branch` reviews cumulative diff from branch divergence point
- **smart-input.AC1.3 Success:** Findings reference original file line numbers, not diff-relative positions
- **smart-input.AC1.4 Failure:** `/review-hammer this commit` in a non-git directory returns a clear error
- **smart-input.AC1.5 Edge:** `/review-hammer this commit` on a merge commit reviews the merge diff

### smart-input.AC2: File review with dirty/clean detection
- **smart-input.AC2.1 Success:** `/review-hammer <dirty-file>` reviews uncommitted changes as diff + context
- **smart-input.AC2.2 Success:** `/review-hammer <clean-file>` reviews the full file (current behavior)
- **smart-input.AC2.3 Edge:** `/review-hammer <untracked-file>` (not in git) falls back to full-file mode

### smart-input.AC3: Directory review
- **smart-input.AC3.1 Success:** `/review-hammer <directory>` classifies each file as dirty or clean and dispatches accordingly
- **smart-input.AC3.2 Success:** Mixed directory (some dirty, some clean) produces a unified report

### smart-input.AC4: Auto-chunking
- **smart-input.AC4.1 Success:** File exceeding chunk threshold is split, reviewed per-chunk, and findings merged into a single array
- **smart-input.AC4.2 Success:** Chunks include file header (imports/definitions) for context
- **smart-input.AC4.3 Success:** Overlapping chunk regions produce deduplicated findings
- **smart-input.AC4.4 Success:** Chunking works for both diff mode and full-file mode
- **smart-input.AC4.5 Edge:** File just under the threshold is NOT chunked (no unnecessary splitting)

### smart-input.AC5: Diff context assembly
- **smart-input.AC5.1 Success:** Diff hunks include file header plus surrounding context lines with original line numbers
- **smart-input.AC5.2 Success:** Adjacent hunks with overlapping context windows are merged into one continuous block
- **smart-input.AC5.3 Success:** When assembled content covers >=90% of the file, diff markers are preserved but full-file framing is used
- **smart-input.AC5.4 Success:** Runtime instruction block injected before content explains the format to the LLM

### smart-input.AC6: Backward compatibility
- **smart-input.AC6.1 Success:** Omitting `--diff-base` produces identical behavior to current implementation
- **smart-input.AC6.2 Success:** All existing unit tests and corpus tests pass without modification
- **smart-input.AC6.3 Success:** No prompt template files are modified

### smart-input.AC7: test-hammer chunking
- **smart-input.AC7.1 Success:** test-hammer (full-file mode) chunks large files and produces merged suggestions
- **smart-input.AC7.2 Success:** Chunking in test-hammer uses the same code path as review-hammer chunking

## Glossary

- **diff mode / full-file mode**: The two operating modes for `review_file.py`. Diff mode reviews only changed portions; full-file mode sends the entire file (current behavior, preserved when `--diff-base` is omitted).
- **unified diff**: Standard `git diff` output format with `+`/`-` prefixes for changed lines and `@@ -L,N +L,N @@` hunk headers identifying line positions.
- **hunk**: A contiguous block of changes within a unified diff, bounded by a `@@` header. A single file's diff may contain multiple hunks.
- **context assembly**: Expanding raw diff hunks by ±N surrounding lines, merging overlapping windows, and prepending the file header to produce a review-ready excerpt.
- **file header**: The top portion of a source file (imports, module-level declarations, type definitions) prepended to every diff hunk or chunk for LLM context.
- **coverage detector**: Logic comparing assembled diff content length against full file length. At ≥90% coverage, switches from "partial view" to full-file framing with diff markers.
- **chunking**: Splitting oversized input into overlapping segments, reviewing each separately, and merging findings. Handles files exceeding the API input limit.
- **chunk threshold**: Line-count constant at ~66% of the empirically determined API limit, below which no chunking occurs.
- **input mode detection**: Skill-layer logic classifying `$ARGUMENTS` into one of five modes: commit, branch, file-diff, file-full, or directory.
- **runtime instruction injection**: Prepending mode-specific LLM guidance at API call time rather than modifying stored prompt templates.
- **Opus judge pass**: Existing post-processing step that deduplicates, verifies line numbers, and filters false positives across findings from all agents.
- **PEP 723**: Python standard for inline script dependencies, used by `review_file.py` so `uv run` auto-manages requirements.

## Architecture

The plugin currently sends entire files to the LLM API for review. This design adds diff-aware input assembly so that reviews of commits, branches, and dirty files send only the changed code plus surrounding context — reducing API payload from thousands of lines to hundreds.

The change spans three layers:

**Skill layer** (`skills/review-hammer/SKILL.md`): Gains input mode detection. Classifies user arguments into five modes — commit, branch, file-diff, file-full, or directory — and resolves natural language ("this commit", "this branch") to git refs. Passes the resolved ref to agents.

**Agent layer** (`agents/file-reviewer.md`, `agents/test-suggester.md`): Gains a `DIFF_BASE` input field. Passes it through to `review_file.py` via `--diff-base`. No diff logic in agents.

**Script layer** (`scripts/review_file.py`): Gains `--diff-base` and `--context-lines` flags. When `--diff-base` is provided, the script runs `git diff`, parses unified diff output, extracts the file header (imports/definitions) and diff hunks with surrounding context, and assembles a review-ready message with original file line numbers. When the assembled content covers ≥90% of the file, it drops the "partial view" framing and sends as a full-file review with diff markers showing what changed. Chunking for oversized inputs (diff or full file) also lives here — the script splits, makes multiple API calls, and merges findings transparently.

Data flow for diff mode:

```
User: /review-hammer this commit
  → Skill: git diff HEAD~1..HEAD --name-only → [file1, file2]
  → Skill: dispatch agent per file with DIFF_BASE=HEAD~1
    → Agent: timeout 300 uv run review_file.py file1 --diff-base HEAD~1 --category X
      → Script: git diff HEAD~1 -- file1 → parse hunks → assemble context → API call → findings
    → Agent: returns JSON findings
  → Skill: Opus judge pass → final report
```

Data flow for full-file mode (unchanged from current behavior):

```
User: /review-hammer src/clean_file.rs
  → Skill: file is clean (no uncommitted changes)
  → Skill: dispatch agent without DIFF_BASE
    → Agent: timeout 300 uv run review_file.py src/clean_file.rs --category X
      → Script: reads full file → API call → findings (current behavior)
```

## Existing Patterns

The current `review_file.py` user message format uses a `# Source file: {path}` header followed by line-numbered content. The diff mode follows this pattern with `# Diff review: {path}` for partial coverage or `# Source file: {path}` (with diff markers) for full coverage.

The `--test-context` flag established the pattern for optional input modifiers — `--diff-base` follows the same approach: optional flag, `None` default, backward compatible.

The skill's Phase 1 input validation currently uses Glob to verify path existence. The new mode detection extends this with git commands, but Glob remains the fallback for non-git paths.

Chunking is a new pattern with no existing equivalent in the codebase.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Diff Extraction and Context Assembly in review_file.py

**Goal:** `review_file.py` can accept `--diff-base` and produce a context-assembled user message from a git diff, with original file line numbers.

**Components:**
- `--diff-base` and `--context-lines` CLI arguments in `scripts/review_file.py`
- Unified diff parser — extracts hunk ranges from `git diff` output
- File header extractor — captures imports/definitions from the top of the file (everything before first function/class/impl)
- Context assembler — expands each hunk by ±N lines, merges overlapping windows, prepends file header
- Coverage detector — compares assembled content against full file length, chooses full-file or partial framing
- Runtime instruction injection — prepends diff-specific or full-file-with-markers guidance to the user message
- Unit tests for diff parsing, context assembly, coverage detection, and instruction injection

**Dependencies:** None (first phase)

**Done when:** `review_file.py --diff-base HEAD~1 somefile.py --category logic-errors` produces a correctly assembled user message with original line numbers, and all unit tests pass.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Chunking

**Goal:** Oversized inputs (diff or full file) are automatically split into chunks, reviewed separately, and findings merged transparently.

**Components:**
- Line count threshold detection in `scripts/review_file.py` (threshold TBD via API calibration)
- Chunk splitter — splits at natural boundaries (blank lines between functions) with overlap
- File header prepended to each chunk
- Per-chunk API calls within the existing retry loop
- Finding merger — deduplicates findings from overlapping regions
- Unit tests for chunking, splitting at boundaries, overlap handling, and finding deduplication

**Dependencies:** Phase 1 (context assembly produces the content that gets chunked)

**Done when:** A file exceeding the threshold is automatically chunked, each chunk reviewed, and findings merged into a single deduplicated array. Unit tests pass.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: API Limit Calibration

**Goal:** Determine the actual line limit for the LLM API and set the chunk threshold.

**Components:**
- Calibration test script (or manual process) that sends progressively larger files to the API
- Chunk threshold constant in `scripts/review_file.py` set to ~66% of the discovered limit
- Default `--context-lines` value calibrated to fit comfortably within the limit

**Dependencies:** Phase 2 (chunking must work before we can set the threshold)

**Done when:** Chunk threshold is set based on empirical API testing, and a large file (e.g., the 2900-line file that triggered this design) reviews successfully via chunking.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Agent Definition Updates

**Goal:** `file-reviewer.md` and `test-suggester.md` accept and pass through `DIFF_BASE`.

**Components:**
- `DIFF_BASE` input field added to `agents/file-reviewer.md`
- `DIFF_BASE` input field added to `agents/test-suggester.md` (for future use — test-hammer currently stays full-file but the plumbing should exist)
- Command template updated to conditionally include `--diff-base`

**Dependencies:** Phase 1 (script must accept the flag)

**Done when:** Agents correctly pass `--diff-base` to `review_file.py` when provided, and omit it when not provided.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Skill Input Mode Detection

**Goal:** `skills/review-hammer/SKILL.md` classifies user arguments into five modes and resolves natural language to git refs.

**Components:**
- Input classifier in Phase 1 of the skill — determines mode from `$ARGUMENTS`:
  - Contains "commit" → commit mode, resolve to `HEAD~1` (or parse "last N commits")
  - Contains "branch" → branch mode, resolve via `git merge-base`
  - Is a file path (exists on disk) → check `git status` for dirty/clean → file-diff or file-full
  - Is a directory path → directory mode
- Git ref resolution — translates natural language to concrete refs via Bash
- Per-file dirty/clean classification for directory mode via `git status --porcelain`

**Dependencies:** Phase 4 (agents must accept DIFF_BASE)

**Done when:** All five input modes correctly identified and dispatched with appropriate DIFF_BASE values.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Skill Dispatch Integration

**Goal:** The review-hammer skill dispatches agents with diff-base for diff modes and without for full-file modes, using the existing batch queue.

**Components:**
- Modified agent dispatch in `skills/review-hammer/SKILL.md` Phase 4/5 — passes `DIFF_BASE` field to file-reviewer and test-suggester agents when in diff mode
- Directory mode dispatches mixed: some files with diff-base, some without
- test-hammer skill (`skills/test-hammer/SKILL.md`) gains chunking awareness (dispatches with awareness that large files may chunk internally) but stays full-file only

**Dependencies:** Phase 5 (mode detection must work)

**Done when:** `/review-hammer this commit`, `/review-hammer this branch`, `/review-hammer <file>`, and `/review-hammer <directory>` all produce correct review reports.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Edge Cases and Error Handling

**Goal:** Graceful handling of all edge cases identified during design.

**Components:**
- Untracked files (not in git) — fall back to full-file mode
- Binary files — skip with warning
- Deleted files in diff — skip with note
- Invalid git ref — clear error message
- Empty diff (no changes) — report "no changes to review"
- Version bump in plugin.json and marketplace.json

**Dependencies:** Phase 6 (core functionality must work first)

**Done when:** All edge cases handled gracefully with appropriate messages. No crashes or confusing output for any input.
<!-- END_PHASE_7 -->

## Additional Considerations

**Prompt template stability:** No prompt templates are modified in this design. The diff-specific instructions are injected at runtime by `review_file.py`, keeping the prompt templates focused on *what to look for* (language-specific) while the script handles *how the input is formatted* (mode-specific).

**Backward compatibility:** All changes are additive. Omitting `--diff-base` produces identical behavior to the current implementation. Existing corpus tests and unit tests should pass without modification.

**test-hammer and chunking:** test-hammer stays full-file because test gap analysis needs the complete file to identify what's missing. However, it benefits from chunking — a 2900-line file that currently times out will be chunked and reviewed successfully.
