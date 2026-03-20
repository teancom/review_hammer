#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "openai>=1.0.0",
# ]
# ///
"""
review_file.py - Code review specialist orchestrator.

Sends a single file + category to an OpenAI-compatible API and returns structured JSON findings.
"""

import argparse
import calendar
import email.utils
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from openai import (
    OpenAI,
    APIConnectionError,
    RateLimitError,
    APITimeoutError,
    AuthenticationError,
)


# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 60.0  # seconds

# Chunk threshold in lines — content exceeding this is split into chunks.
# Set to ~66% of empirically determined API input limit. Calibrated in Phase 3.
CHUNK_THRESHOLD = 500

# Overlap lines between adjacent chunks (ensures findings near boundaries aren't lost)
CHUNK_OVERLAP = 20


def parse_retry_after(value: str) -> Optional[float]:
    """
    Parse an RFC 7231 Retry-After header value.

    Supports both formats:
    - Delay in seconds: "5", "120"
    - HTTP-date: "Fri, 31 Dec 2021 23:59:59 GMT"

    Returns seconds to wait, or None if unparseable.
    """
    # Try as a number of seconds first
    try:
        return float(value)
    except (ValueError, TypeError):
        pass

    # Try as an HTTP-date (RFC 2822 / RFC 7231)
    try:
        parsed = email.utils.parsedate(value)
        if parsed is not None:
            target_utc = calendar.timegm(parsed)
            delay = target_utc - time.time()
            return max(0.0, delay)
    except (ValueError, TypeError, OverflowError):
        pass

    return None


EXTENSION_MAP = {
    ".py": "python",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".java": "java",
    ".cs": "csharp",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rs": "rust",
    ".go": "go",
    ".swift": "swift",
}


def detect_language(file_path: str) -> str:
    """
    Detect programming language from file extension.

    Args:
        file_path: Path to the file

    Returns:
        Language key (maps to prompts/{language}.md), or "generic" if unknown
    """
    path_obj = Path(file_path)
    extension = path_obj.suffix.lower()
    return EXTENSION_MAP.get(extension, "generic")


def prepend_line_numbers(source: str) -> str:
    """
    Prepend line numbers to source code.

    Args:
        source: Raw source code (may have trailing newline or not)

    Returns:
        Source code with line numbers prepended, right-justified.
        Format: "{line_number}| {line_content}"
    """
    lines = source.splitlines(keepends=False)
    if not lines:
        return ""

    # Determine width needed for line numbers
    max_line = len(lines)
    width = len(str(max_line))

    # Prepend line numbers
    numbered = []
    for i, line in enumerate(lines, start=1):
        numbered.append(f"{i:>{width}}| {line}")

    return "\n".join(numbered)


def _annotate_with_diff_markers(source: str, diff_output: str) -> str:
    """
    Prepend line numbers to source code and mark changed lines with +/- prefixes.

    Parses the diff output to determine which lines were added (+) or removed (-),
    then annotates the full source accordingly. Removed lines appear in the diff
    for context but don't exist in the current file, so this function marks them.

    Args:
        source: Full file content (current state, without diff markers)
        diff_output: Raw git diff output

    Returns:
        Source code with line numbers and diff markers prepended.
        Format: "{marker}{line_number}| {line_content}"
        where marker is "", "+", or "-"
    """
    source_lines = source.splitlines(keepends=False)
    if not source_lines:
        return ""

    # Parse diff to find which original-file lines were changed
    # We'll track added and removed lines based on the diff
    added_lines = set()
    removed_lines = set()

    # Track the current line number in the original file
    current_old_line = 0
    current_new_line = 0

    diff_lines = diff_output.split("\n")
    for diff_line in diff_lines:
        # Check for hunk header
        if diff_line.startswith("@@"):
            # Parse @@ -old_start,old_count +new_start,new_count @@
            match = re.match(
                r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@",
                diff_line,
            )
            if match:
                current_old_line = int(match.group(1))
                current_new_line = int(match.group(3))
            continue

        # Skip diff headers
        if diff_line.startswith("---") or diff_line.startswith("+++"):
            continue
        if diff_line.startswith("diff --git"):
            continue
        if diff_line.startswith("index "):
            continue

        # Process diff content lines
        if diff_line.startswith("-"):
            # Line was removed in original file
            removed_lines.add(current_old_line)
            current_old_line += 1
        elif diff_line.startswith("+"):
            # Line was added in current file
            added_lines.add(current_new_line)
            current_new_line += 1
        elif diff_line.startswith(" "):
            # Context line (unchanged)
            current_old_line += 1
            current_new_line += 1
        # else: ignore other diff lines

    # Determine width needed for line numbers
    max_line = len(source_lines)
    width = len(str(max_line))

    # Prepend line numbers and markers
    numbered = []
    for i, line in enumerate(source_lines, start=1):
        if i in added_lines:
            marker = "+"
        elif i in removed_lines:
            marker = "-"
        else:
            marker = " "
        numbered.append(f"{marker}{i:>{width}}| {line}")

    return "\n".join(numbered)


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
    hunks = []
    # Pattern: @@ -old_start,old_count +new_start,new_count @@
    pattern = r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"

    for match in re.finditer(pattern, diff_output, re.MULTILINE):
        start_line = int(match.group(1))
        # If count is omitted, it defaults to 1
        count = int(match.group(2) or "1")
        end_line = start_line + count - 1

        hunks.append({"start_line": start_line, "end_line": end_line})

    return hunks


# Regex pattern for function/class definition starts across common languages
_DEFINITION_START = re.compile(
    r"^\s*(?:pub(?:\(crate\))?\s+)?(?:async\s+)?(?:def |class |fn |impl |func |function |export\s+(?:default\s+)?function )",
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
    lines = source.splitlines(keepends=False)
    if not lines:
        return ""

    # Find the first line that starts a function or class definition
    for i, line in enumerate(lines):
        if _DEFINITION_START.match(line):
            # Found a definition, return lines up to here (capped)
            header_lines = lines[:i]
            if len(header_lines) > MAX_HEADER_LINES:
                header_lines = header_lines[:MAX_HEADER_LINES]
            return "\n".join(header_lines)

    # No definition found, return entire file (capped)
    if len(lines) > MAX_HEADER_LINES:
        return "\n".join(lines[:MAX_HEADER_LINES])
    return source


def split_into_chunks(
    content: str,
    file_header: str,
    chunk_threshold: int = CHUNK_THRESHOLD,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    Split content into overlapping chunks at natural boundaries.

    Each chunk gets the file header prepended for LLM context.
    Splits preferentially at blank lines between functions/classes.

    Args:
        content: The content to split (may be numbered lines from diff or full file)
        file_header: File header to prepend to each chunk
        chunk_threshold: Line count above which splitting occurs
        chunk_overlap: Number of overlapping lines between adjacent chunks

    Returns:
        List of chunk strings. If content is under threshold, returns [content]
        with file header prepended. Each chunk has file header prepended.
    """
    content_lines = content.splitlines(keepends=False)
    total_lines = len(content_lines)

    # If under threshold, return single chunk with header
    if total_lines <= chunk_threshold:
        return [f"{file_header}\n\n{content}"] if file_header else [content]

    # Calculate target chunk size accounting for header lines
    header_lines = len(file_header.splitlines(keepends=False)) if file_header else 0
    target_chunk_size = chunk_threshold - header_lines

    # Split content into chunks
    chunks = []
    chunk_start = 0

    while chunk_start < total_lines:
        # Calculate the end position for this chunk
        chunk_end = min(chunk_start + target_chunk_size, total_lines)

        # Try to find a blank line near the target end for a natural boundary
        # Search ±20 lines from the target
        search_window = 20
        best_split = chunk_end

        if chunk_end < total_lines:  # Don't search if at the end
            search_start = max(chunk_start, chunk_end - search_window)
            search_end = min(total_lines, chunk_end + search_window)

            for i in range(search_end - 1, search_start - 1, -1):
                if i < total_lines and content_lines[i].strip() == "":
                    best_split = i
                    break

        # Extract chunk lines
        chunk_content_lines = content_lines[chunk_start:best_split]
        chunk_content = "\n".join(chunk_content_lines)

        # Prepend file header
        if file_header:
            chunk = f"{file_header}\n\n{chunk_content}"
        else:
            chunk = chunk_content

        chunks.append(chunk)

        # For next chunk, start with overlap
        chunk_start = best_split - chunk_overlap
        if chunk_start < chunk_end:
            chunk_start = chunk_end

    return chunks


def deduplicate_findings(all_findings: list[list]) -> list:
    """
    Merge and deduplicate findings from multiple chunk reviews.

    Two findings are considered duplicates if they have the same category
    and overlapping line ranges (within 2 lines tolerance).

    Args:
        all_findings: List of finding lists, one per chunk

    Returns:
        Single deduplicated list of findings
    """
    if not all_findings:
        return []

    # Flatten all finding lists into one
    flattened = []
    for findings_list in all_findings:
        flattened.extend(findings_list)

    if not flattened:
        return []

    # Helper function to parse line ranges
    def parse_lines(lines_field):
        """Parse a lines field into (start, end) tuple."""
        if isinstance(lines_field, str):
            parts = lines_field.split("-")
            start = int(parts[0])
            end = int(parts[-1]) if len(parts) > 1 else start
            return (start, end)
        elif isinstance(lines_field, list) and lines_field:
            start = lines_field[0]
            end = lines_field[-1] if len(lines_field) > 1 else start
            return (start, end)
        return (1, 1)

    # Helper function to get line number for sorting
    def get_line_number(finding: dict) -> int:
        """Extract the first line number from a finding's lines field."""
        lines_field = finding.get("lines", "1")
        if isinstance(lines_field, str):
            # Handle "42" or "42-45" format
            parts = lines_field.split("-")
            return int(parts[0])
        elif isinstance(lines_field, list) and lines_field:
            return lines_field[0]
        return 1

    # Sort by line number for easier deduplication
    flattened.sort(key=get_line_number)

    # Deduplicate by building a new list
    deduplicated = []

    for finding in flattened:
        # Check if this finding is a duplicate of any already-kept finding
        is_duplicate = False
        duplicate_idx = None

        for j, kept in enumerate(deduplicated):
            # Check if same category and overlapping lines
            if finding.get("category") != kept.get("category"):
                continue

            finding_start, finding_end = parse_lines(finding.get("lines", "1"))
            kept_start, kept_end = parse_lines(kept.get("lines", "1"))

            # Check if line ranges overlap or are within 2 lines
            if (
                (
                    finding_start <= kept_end + 2
                    and finding_end >= kept_start - 2
                )
                or abs(finding_start - kept_start) <= 2
            ):
                # Found a duplicate
                is_duplicate = True
                duplicate_idx = j

                # Compare severity and potentially replace
                severity_order = {"critical": 3, "high": 2, "medium": 1}
                finding_severity = severity_order.get(
                    finding.get("severity", "medium"), 0
                )
                kept_severity = severity_order.get(
                    kept.get("severity", "medium"), 0
                )

                if finding_severity > kept_severity:
                    # Replace kept with finding
                    deduplicated[j] = finding
                # else: keep the already-kept finding

                break

        if not is_duplicate:
            deduplicated.append(finding)

    return deduplicated


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
    if not hunks:
        return ""

    source_lines = source.splitlines(keepends=False)
    total_lines = len(source_lines)

    merged = _expand_and_merge_ranges(hunks, total_lines, context_lines)

    # Determine line number width for proper alignment
    max_line_num = total_lines
    width = len(str(max_line_num))

    # Build output with header and hunks
    header = extract_file_header(source)
    output_parts = []

    if header:
        output_parts.append(header)
        output_parts.append("--- (hunks below) ---")

    # Process merged ranges
    for i, rng in enumerate(merged):
        if i > 0:
            output_parts.append("...")

        # Extract and number lines for this range
        hunk_lines = []
        for line_num in range(rng["start"], rng["end"] + 1):
            line_content = source_lines[line_num - 1]  # 0-indexed array
            hunk_lines.append(f"{line_num:>{width}}| {line_content}")

        output_parts.append("\n".join(hunk_lines))

    return "\n".join(output_parts)


# Threshold for switching from partial to full-file framing
FULL_COVERAGE_THRESHOLD = 0.90


def _expand_and_merge_ranges(
    hunks: list[dict], total_lines: int, context_lines: int
) -> list[dict]:
    """
    Expand hunk ranges by context_lines and merge overlapping/adjacent ranges.

    Args:
        hunks: List of {"start_line": int, "end_line": int} from parse_unified_diff()
        total_lines: Total lines in the original file
        context_lines: Number of lines to include above and below each hunk

    Returns:
        List of merged dicts with keys "start" and "end" representing continuous blocks
    """
    if not hunks:
        return []

    # Expand hunk ranges by context_lines
    expanded = []
    for hunk in hunks:
        start = max(1, hunk["start_line"] - context_lines)
        end = min(total_lines, hunk["end_line"] + context_lines)
        expanded.append({"start": start, "end": end})

    # Merge overlapping/adjacent ranges
    expanded.sort(key=lambda x: x["start"])
    merged = []
    for exp in expanded:
        if merged and exp["start"] <= merged[-1]["end"] + 1:
            # Overlapping or adjacent, merge
            merged[-1]["end"] = max(merged[-1]["end"], exp["end"])
        else:
            # Not overlapping, add new range
            merged.append(exp)

    return merged


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
    if not hunks or total_lines == 0:
        return False

    merged = _expand_and_merge_ranges(hunks, total_lines, context_lines)

    # Count total covered lines
    covered_lines = 0
    for rng in merged:
        covered_lines += rng["end"] - rng["start"] + 1

    # Check if coverage meets threshold
    coverage = covered_lines / total_lines
    return coverage >= FULL_COVERAGE_THRESHOLD


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
    total_lines = source.count("\n") + 1
    use_full_file = detect_coverage(hunks, total_lines, context_lines)

    if use_full_file:
        # Full-file mode: show entire file with numbered lines and diff markers
        # Annotate with +/- markers showing which lines were changed
        numbered_source = _annotate_with_diff_markers(source, diff_output)
        return (
            f"# Source file: {file_path}\n\n"
            f"{DIFF_FULL_WITH_MARKERS_INSTRUCTIONS}\n\n"
            f"{numbered_source}"
        )
    else:
        # Partial-view mode: show only hunks with context
        assembled = assemble_diff_context(hunks, source, context_lines)
        return (
            f"# Diff review: {file_path}\n\n{DIFF_PARTIAL_INSTRUCTIONS}\n\n{assembled}"
        )


def extract_category_prompt(template_path: str, category: str) -> str:
    """
    Extract preamble and category section from a prompt template.

    Args:
        template_path: Path to the prompt template markdown file
        category: Category name to extract (matches ## heading)

    Returns:
        Combined preamble + category section

    Raises:
        ValueError: If the category section is not found
        FileNotFoundError: If the template file does not exist
    """
    with open(template_path, "r") as f:
        content = f.read()

    # Find the first ## heading to know where preamble ends
    lines = content.split("\n")
    preamble_end = 0
    for i, line in enumerate(lines):
        if line.startswith("## "):
            preamble_end = i
            break

    # Extract preamble (everything before first ## heading)
    preamble = "\n".join(lines[:preamble_end]).rstrip()

    # Find the target category section
    target_heading = f"## {category}"
    category_start = None
    category_end = None

    for i, line in enumerate(lines[preamble_end:], start=preamble_end):
        if line.startswith("## "):
            if line == target_heading:
                category_start = i
            elif category_start is not None:
                # Found the next section
                category_end = i
                break

    if category_start is None:
        raise ValueError(f"Category '{category}' not found in template {template_path}")

    # If no next section found, go to end of file
    if category_end is None:
        category_end = len(lines)

    # Extract category section
    category_section = "\n".join(lines[category_start:category_end]).rstrip()

    # Combine preamble and category
    return f"{preamble}\n\n{category_section}"


def parse_findings(raw_response: str) -> list:
    """
    Parse findings from LLM response.

    Handles:
    - Valid JSON array (returns it)
    - Empty string (returns [])
    - JSON wrapped in markdown fences (extracts and parses)
    - Malformed JSON (warns to stderr, returns [])

    Args:
        raw_response: Raw response from LLM

    Returns:
        List of findings (dict objects) or empty list if parsing fails
    """
    if not raw_response or not raw_response.strip():
        return []

    response = raw_response.strip()

    # Try direct parsing first
    try:
        result = json.loads(response)
        if isinstance(result, list):
            return result
        else:
            # JSON is valid but not an array
            print(
                "Warning: LLM response is JSON but not an array, returning empty findings",
                file=sys.stderr,
            )
            return []
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown fences
    if "```json" in response or "```" in response:
        # Look for ```json...``` or ```...```
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", response, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                if isinstance(result, list):
                    return result
                else:
                    # JSON is valid but not an array
                    print(
                        "Warning: LLM response is JSON but not an array, returning empty findings",
                        file=sys.stderr,
                    )
                    return []
            except json.JSONDecodeError:
                pass

    # Failed to parse
    print("Warning: Could not parse LLM response as JSON", file=sys.stderr)
    return []


class RetryExhaustedError(Exception):
    """Raised when all retries are exhausted."""

    pass


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
    """
    Orchestrate code review for a single file.

    Steps:
    1. Read the file
    2. Prepend line numbers
    3. Load and extract category prompt
    4. Call OpenAI API with retry logic
    5. Parse findings
    6. Return findings

    Args:
        file_path: Path to the file to review
        category: Specialist category (e.g., "logic-errors")
        language: Language key (e.g., "generic")
        api_key: OpenAI API key
        base_url: OpenAI-compatible API base URL
        model: Model to use
        timeout: API call timeout in seconds (default 120)
        test_context_paths: Optional list of paths to test files to include as context
        diff_base: Optional git ref to diff against (e.g., HEAD~1, main). When provided, reviews only changed hunks with context instead of the full file.
        context_lines: Number of context lines around each diff hunk (default: 3). Only used with diff_base.

    Returns:
        List of findings (each is a dict with lines, severity, category, etc.)

    Raises:
        FileNotFoundError: If file not found
        ValueError: If category not found in template, or if git diff fails
        AuthenticationError: If API authentication fails (no retry)
        RetryExhaustedError: If all retries exhausted
    """
    # Log start for observability
    source_lines = 0
    start_time = time.time()
    print(
        f"[review] START {category} for {file_path} (timeout={timeout}s)",
        file=sys.stderr,
    )

    # Read the file
    with open(file_path, "r") as f:
        source = f.read()
    source_lines = source.count("\n") + 1

    # Determine prompt template path relative to script location
    script_dir = Path(__file__).parent
    template_path = script_dir.parent / "prompts" / f"{language}.md"

    # Extract category prompt
    system_prompt = extract_category_prompt(str(template_path), category)

    # Build user message based on mode
    if diff_base is not None:
        # Diff mode: run git diff, parse, and assemble context
        try:
            result = subprocess.run(
                ["git", "diff", diff_base, "--", file_path],
                capture_output=True,
                text=True,
                check=True,
            )
            diff_output = result.stdout
        except subprocess.CalledProcessError as e:
            raise ValueError(
                f"git diff failed for ref '{diff_base}': {e.stderr}"
            ) from e

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

    if test_context_paths:
        for test_path in test_context_paths:
            if not os.path.exists(test_path):
                print(
                    f"Warning: Test context file not found: {test_path}",
                    file=sys.stderr,
                )
                continue
            with open(test_path, "r") as f:
                test_lines = f.readlines()
            if len(test_lines) > 500:
                print(
                    f"Warning: Test file {test_path} has {len(test_lines)} lines, "
                    f"truncating to 500 lines",
                    file=sys.stderr,
                )
                test_content = "".join(test_lines[:500])
                test_content += (
                    f"\n# ... truncated ({len(test_lines) - 500} lines omitted)"
                )
            else:
                test_content = "".join(test_lines)
            numbered_test = prepend_line_numbers(test_content)
            user_message += f"\n\n# Existing test file: {test_path}\n\n{numbered_test}"
    else:
        if category == "test-suggestions":
            user_message += "\n\n# No existing test files found for this source file."

    # Create client with timeout and max_retries=0 (we handle retries ourselves)
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)

    # Retry loop with exponential backoff
    backoff = INITIAL_BACKOFF
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
            )

            # Extract response content
            raw_response = response.choices[0].message.content

            # Parse findings
            findings = parse_findings(raw_response)

            elapsed = time.time() - start_time
            print(
                f"[review] OK {category} for {file_path} "
                f"({source_lines} lines, {len(findings)} findings, "
                f"{elapsed:.1f}s, attempt {attempt + 1})",
                file=sys.stderr,
            )
            return findings

        except AuthenticationError:
            # Do not retry authentication errors
            raise

        except (RateLimitError, APITimeoutError, APIConnectionError) as e:
            # Retry on rate limit, timeout, or connection error
            error_name = type(e).__name__
            if attempt < MAX_RETRIES:
                # Check for Retry-After header (RateLimitError from openai SDK
                # exposes the response object)
                retry_after = None
                if (
                    isinstance(e, RateLimitError)
                    and hasattr(e, "response")
                    and e.response is not None
                ):
                    raw_header = e.response.headers.get("retry-after")
                    if raw_header is not None:
                        retry_after = parse_retry_after(raw_header)

                if retry_after is not None:
                    # Server told us exactly how long to wait
                    wait_time = retry_after
                    print(
                        f"{error_name} (attempt {attempt + 1}/{MAX_RETRIES + 1}). "
                        f"Retry-After: {wait_time:.1f}s",
                        file=sys.stderr,
                    )
                else:
                    # Exponential backoff with jitter (±25%)
                    jitter = backoff * random.uniform(-0.25, 0.25)
                    wait_time = backoff + jitter
                    print(
                        f"{error_name} (attempt {attempt + 1}/{MAX_RETRIES + 1}). "
                        f"Retrying in {wait_time:.1f}s...",
                        file=sys.stderr,
                    )
                    backoff = min(backoff * 2, MAX_BACKOFF)

                time.sleep(wait_time)
            else:
                elapsed = time.time() - start_time
                print(
                    f"[review] FAIL {category} for {file_path} "
                    f"({source_lines} lines, {elapsed:.1f}s total, "
                    f"{error_name} after {MAX_RETRIES} retries): {e}",
                    file=sys.stderr,
                )
                raise RetryExhaustedError(f"{error_name} after {MAX_RETRIES} retries")

    # This should not be reached, but raise if somehow loop exits normally
    raise RetryExhaustedError("Unexpected end of retry loop")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Review a code file for bugs in a specific category"
    )
    parser.add_argument("file_path", help="Path to the file to review")
    parser.add_argument(
        "--category",
        required=True,
        help="Specialist category (e.g., logic-errors, null-safety)",
    )
    parser.add_argument(
        "--language",
        required=False,
        default=None,
        help="Language key (maps to prompts/{language}.md). If not provided, auto-detected from file extension.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="OpenAI API key (or set REVIEWERS_API_KEY env var)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible API base URL (or set REVIEWERS_BASE_URL env var)",
    )
    parser.add_argument(
        "--model", default=None, help="Model to use (or set REVIEWERS_MODEL env var)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="API call timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--test-context",
        action="append",
        default=None,
        dest="test_context",
        help="Path to existing test file(s) to include as context. Can be specified multiple times.",
    )
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

    args = parser.parse_args()

    # Resolve language from args or auto-detect from file extension
    language = args.language
    if not language:
        language = detect_language(args.file_path)

    # Resolve configuration from args or env vars
    api_key = args.api_key or os.environ.get("REVIEWERS_API_KEY")
    base_url = args.base_url or os.environ.get(
        "REVIEWERS_BASE_URL", "https://api.z.ai/api/paas/v4/"
    )
    model = args.model or os.environ.get("REVIEWERS_MODEL", "glm-5")

    # Validate required parameters
    if not api_key:
        print(
            "Error: API key is required. Set --api-key or REVIEWERS_API_KEY environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        # Check file exists
        if not os.path.exists(args.file_path):
            print(f"Error: File not found: {args.file_path}", file=sys.stderr)
            sys.exit(1)

        # Run review
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

        # Output findings as JSON
        print(json.dumps(findings, indent=2))

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    except AuthenticationError as e:
        print(f"Error: Authentication failed: {e}", file=sys.stderr)
        sys.exit(1)

    except RetryExhaustedError:
        # All retries exhausted: output empty findings and exit with code 2
        print("[]")
        sys.exit(2)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
