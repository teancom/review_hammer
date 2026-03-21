# Smart Input Implementation Plan — Phase 6

**Goal:** The review-hammer skill dispatches agents with diff-base for diff modes and without for full-file modes, using the existing batch queue. test-hammer gains chunking awareness.

**Architecture:** Modify agent dispatch in review-hammer skill Phase 4 to include DIFF_BASE in agent prompts when in diff mode. Update test-hammer skill to note that large files may be chunked internally by the script.

**Tech Stack:** Markdown skill definitions (Claude Code plugin system)

**Scope:** 7 phases from original design (phase 6 of 7)

**Codebase verified:** 2026-03-20

---

## Acceptance Criteria Coverage

This phase implements:

### smart-input.AC1: Commit and branch review via natural language
- **smart-input.AC1.1 Success:** `/review-hammer this commit` reviews only files changed in HEAD, using diff + context
- **smart-input.AC1.2 Success:** `/review-hammer this branch` reviews cumulative diff from branch divergence point

### smart-input.AC2: File review with dirty/clean detection
- **smart-input.AC2.1 Success:** `/review-hammer <dirty-file>` reviews uncommitted changes as diff + context
- **smart-input.AC2.2 Success:** `/review-hammer <clean-file>` reviews the full file (current behavior)

### smart-input.AC3: Directory review
- **smart-input.AC3.1 Success:** `/review-hammer <directory>` classifies each file as dirty or clean and dispatches accordingly
- **smart-input.AC3.2 Success:** Mixed directory (some dirty, some clean) produces a unified report

### smart-input.AC7: test-hammer chunking
- **smart-input.AC7.1 Success:** test-hammer (full-file mode) chunks large files and produces merged suggestions
- **smart-input.AC7.2 Success:** Chunking in test-hammer uses the same code path as review-hammer chunking

---

<!-- START_TASK_1 -->
### Task 1: Update review-hammer agent dispatch to pass DIFF_BASE

**Files:**
- Modify: `skills/review-hammer/SKILL.md:139-200` (Phase 4: Agent Dispatch section)

**Implementation:**

Update the agent dispatch section to include `DIFF_BASE` in the prompt for both file-reviewer and test-suggester agents when in diff mode.

**For file-reviewer agents** (update the prompt template around line 178):

Current:
```
prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}"
```

New (conditional):
```
# For commit/branch modes (all files have the same DIFF_BASE):
prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}\nDIFF_BASE: {diff_base}"

# For file-diff mode (single file with DIFF_BASE=HEAD):
prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}\nDIFF_BASE: HEAD"

# For file-full mode or clean files in directory mode (no DIFF_BASE):
prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}"
```

**For test-suggester agents** (update the prompt template around line 185):

Current:
```
prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}\nTEST_FILES: {test_files_csv_or_none}"
```

New (conditional, same logic as file-reviewer):
```
# For diff modes:
prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}\nTEST_FILES: {test_files_csv_or_none}\nDIFF_BASE: {diff_base}"

# For full-file modes:
prompt: "FILE_PATH: {absolute_path}\nLANGUAGE: {detected_language}\nPLUGIN_ROOT: {plugin_root}\nTEST_FILES: {test_files_csv_or_none}"
```

**For directory mode:** Each file has its own `diff_base` value (from Phase 2 per-file classification). Files with uncommitted changes get `DIFF_BASE: HEAD`, clean files omit `DIFF_BASE`.

Add a note in the dispatch section:
```
**DIFF_BASE handling by input mode:**
- commit mode: all files get `DIFF_BASE: {resolved_ref}` (e.g., HEAD~1)
- branch mode: all files get `DIFF_BASE: {merge_base_hash}`
- file-diff mode: file gets `DIFF_BASE: HEAD`
- file-full mode: no DIFF_BASE (omit from prompt)
- directory mode: per-file — dirty files get `DIFF_BASE: HEAD`, clean files omit DIFF_BASE
```

**Verification:**
Read the modified skill and confirm:
- Commit/branch modes pass DIFF_BASE to all agents
- File-diff mode passes DIFF_BASE=HEAD
- File-full mode omits DIFF_BASE
- Directory mode handles per-file DIFF_BASE correctly
- test-suggester prompt includes DIFF_BASE when appropriate

**Commit:** `feat: update review-hammer agent dispatch to pass DIFF_BASE`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update test-hammer with chunking awareness note

**Files:**
- Modify: `skills/test-hammer/SKILL.md:105-134` (Phase 5: Agent Dispatch section)

**Implementation:**

test-hammer stays full-file only (no diff mode) but large files will now be chunked internally by `review_file.py`. Add a note to the agent dispatch section explaining this:

After the existing dispatch instructions (around line 134), add:

```markdown
6. **Large file handling:**
   - Large production files are automatically chunked internally by `review_file.py`
   - The agent does not need to do anything special — chunking, per-chunk API calls, and finding deduplication happen transparently within the script
   - This means files that previously timed out (e.g., 2900+ line files) will now complete successfully via automatic chunking
   - No `DIFF_BASE` is passed — test-hammer always reviews the full file
```

This satisfies AC7.1 (test-hammer chunks large files) and AC7.2 (same code path as review-hammer chunking) because the chunking logic lives in `review_file.py`, which both agents call.

**Verification:**
Read the modified skill and confirm:
- Chunking awareness note is present
- No DIFF_BASE is added to test-hammer dispatch
- Existing behavior is unchanged

**Commit:** `feat: add chunking awareness note to test-hammer skill`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update review-hammer report header for diff mode

**Files:**
- Modify: `skills/review-hammer/SKILL.md:256-340` (Phase 6: Report Formatting section)

**Implementation:**

Update the report formatting section to show the input mode in the report header. Currently the report shows:

```markdown
**Target:** {target_path}
**Files reviewed:** {total_file_count}
```

Update to conditionally show the diff context:

```markdown
# For commit mode:
**Target:** {target_path} (commit: HEAD)
**Mode:** Diff review (only changed code reviewed)
**Files reviewed:** {total_file_count}

# For branch mode:
**Target:** {target_path} (branch diff from {merge_base_short_hash})
**Mode:** Diff review (only changed code reviewed)
**Files reviewed:** {total_file_count}

# For file-diff mode:
**Target:** {target_path} (uncommitted changes)
**Mode:** Diff review (only changed code reviewed)
**Files reviewed:** 1

# For file-full mode or directory (existing):
**Target:** {target_path}
**Files reviewed:** {total_file_count}
```

**Verification:**
Read the modified report template and confirm mode-specific headers are present.

**Commit:** `feat: add input mode context to review-hammer report header`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: End-to-end verification of dispatch integration

**Files:**
- No new files — manual verification

**Verification:**

Manually test the full pipeline for each input mode:

1. `/review-hammer this commit` — verify agents receive DIFF_BASE, findings reference original line numbers
2. `/review-hammer this branch` — verify merge-base resolution and DIFF_BASE passthrough
3. `/review-hammer <dirty-file>` — verify DIFF_BASE=HEAD passed to agents
4. `/review-hammer <clean-file>` — verify no DIFF_BASE, full-file review
5. `/review-hammer <directory>` — verify mixed dispatch (some with DIFF_BASE, some without)
6. `/test-hammer <large-file>` — verify chunking works transparently

**Commit:** No commit — verification step.
<!-- END_TASK_4 -->
