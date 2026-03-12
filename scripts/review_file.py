#!/usr/bin/env python3
"""
review_file.py - Code review specialist orchestrator.

Sends a single file + category to an OpenAI-compatible API and returns structured JSON findings.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from openai import OpenAI, APIConnectionError, RateLimitError, APITimeoutError, AuthenticationError


# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 60.0  # seconds


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
    with open(template_path, 'r') as f:
        content = f.read()

    # Find the first ## heading to know where preamble ends
    lines = content.split('\n')
    preamble_end = 0
    for i, line in enumerate(lines):
        if line.startswith('## '):
            preamble_end = i
            break

    # Extract preamble (everything before first ## heading)
    preamble = '\n'.join(lines[:preamble_end]).rstrip()

    # Find the target category section
    target_heading = f"## {category}"
    category_start = None
    category_end = None

    for i, line in enumerate(lines[preamble_end:], start=preamble_end):
        if line.startswith('## '):
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
    category_section = '\n'.join(lines[category_start:category_end]).rstrip()

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
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown fences
    if "```json" in response or "```" in response:
        import re
        # Look for ```json...``` or ```...```
        match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(1))
                if isinstance(result, list):
                    return result
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
    timeout: float = 120.0
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

    Returns:
        List of findings (each is a dict with lines, severity, category, etc.)

    Raises:
        FileNotFoundError: If file not found
        ValueError: If category not found in template
        AuthenticationError: If API authentication fails (no retry)
        RetryExhaustedError: If all retries exhausted
    """
    # Read the file
    with open(file_path, 'r') as f:
        source = f.read()

    # Prepend line numbers
    numbered_source = prepend_line_numbers(source)

    # Determine prompt template path relative to script location
    script_dir = Path(__file__).parent
    template_path = script_dir.parent / "prompts" / f"{language}.md"

    # Extract category prompt
    system_prompt = extract_category_prompt(str(template_path), category)

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
                    {"role": "user", "content": numbered_source}
                ],
                temperature=0
            )

            # Extract response content
            raw_response = response.choices[0].message.content

            # Parse findings
            findings = parse_findings(raw_response)

            return findings

        except AuthenticationError as e:
            # Do not retry authentication errors
            raise

        except (RateLimitError, APITimeoutError, APIConnectionError) as e:
            # Retry on rate limit, timeout, or connection error
            error_name = type(e).__name__
            if attempt < MAX_RETRIES:
                print(
                    f"{error_name} (attempt {attempt + 1}/{MAX_RETRIES + 1}). "
                    f"Retrying in {backoff:.1f}s...",
                    file=sys.stderr
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)
            else:
                print(f"Error: {error_name} after {MAX_RETRIES} retries: {e}", file=sys.stderr)
                raise RetryExhaustedError(f"{error_name} after {MAX_RETRIES} retries")

    # This should not be reached, but raise if somehow loop exits normally
    raise RetryExhaustedError("Unexpected end of retry loop")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Review a code file for bugs in a specific category"
    )
    parser.add_argument(
        "file_path",
        help="Path to the file to review"
    )
    parser.add_argument(
        "--category",
        required=True,
        help="Specialist category (e.g., logic-errors, null-safety)"
    )
    parser.add_argument(
        "--language",
        required=False,
        default=None,
        help="Language key (maps to prompts/{language}.md). If not provided, auto-detected from file extension."
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="OpenAI API key (or set REVIEWERS_API_KEY env var)"
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible API base URL (or set REVIEWERS_BASE_URL env var)"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model to use (or set REVIEWERS_MODEL env var)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="API call timeout in seconds (default: 120)"
    )

    args = parser.parse_args()

    # Resolve language from args or auto-detect from file extension
    language = args.language
    if not language:
        language = detect_language(args.file_path)

    # Resolve configuration from args or env vars
    api_key = args.api_key or os.environ.get("REVIEWERS_API_KEY")
    base_url = args.base_url or os.environ.get("REVIEWERS_BASE_URL", "https://api.z.ai/api/paas/v4/")
    model = args.model or os.environ.get("REVIEWERS_MODEL", "glm-5")

    # Validate required parameters
    if not api_key:
        print("Error: API key is required. Set --api-key or REVIEWERS_API_KEY environment variable.", file=sys.stderr)
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
            timeout=args.timeout
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

    except RetryExhaustedError as e:
        # All retries exhausted: output empty findings and exit with code 2
        print("[]")
        sys.exit(2)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
