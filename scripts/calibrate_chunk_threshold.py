#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Calibration script for determining API input size limits.

Sends progressively larger synthetic files to the review API and reports outcomes.
Used to set CHUNK_THRESHOLD in review_file.py.

Usage:
    REVIEWERS_API_KEY=... uv run scripts/calibrate_chunk_threshold.py
"""

import json
import subprocess
import tempfile
import time
from pathlib import Path


# Target line counts for synthetic files
TARGET_LINE_COUNTS = [500, 1000, 1500, 2000, 2500, 3000, 3500, 4000]

# Timeout for each review (seconds)
REVIEW_TIMEOUT = 180


def generate_synthetic_file(line_count: int) -> str:
    """
    Generate a realistic synthetic Python file with the target line count.

    Args:
        line_count: Target number of lines

    Returns:
        Source code string
    """
    lines = [
        '"""',
        "Synthetic module for API calibration testing.",
        '"""',
        "",
    ]

    # Generate repeating function definitions to reach target line count
    function_count = max(1, line_count // 20)  # ~20 lines per function
    lines_per_func = line_count // function_count

    for func_idx in range(function_count):
        func_name = f"func_{func_idx:04d}"
        lines.append(f"def {func_name}(a, b, c=None):")
        lines.append('    """')
        lines.append(f"    Synthetic function {func_idx} for calibration testing.")
        lines.append("    ")
        lines.append("    This function performs arithmetic operations on inputs.")
        lines.append('    """')
        lines.append("    if c is None:")
        lines.append("        c = 42")
        lines.append("    result = a + b + c")
        lines.append("    if result > 100:")
        lines.append("        return result * 2")
        lines.append("    elif result > 50:")
        lines.append("        return result + 10")
        lines.append("    else:")
        lines.append("        return result - 5")
        lines.append("")

        # Pad with additional lines if needed
        current_lines = len(lines)
        if current_lines < func_idx * lines_per_func + lines_per_func:
            pad_lines = (func_idx * lines_per_func + lines_per_func) - current_lines
            for _ in range(pad_lines):
                lines.append("    # padding line")

    return "\n".join(lines)


def run_review(
    source_code: str,
    language: str = "python",
    script_dir: Path = None,
) -> tuple[bool, float, dict]:
    """
    Send source code to review API via review_file.py.

    Args:
        source_code: The source code to review
        language: Programming language
        script_dir: Path to scripts directory

    Returns:
        Tuple of (success, response_time, findings_or_error)
        - success: True if review completed
        - response_time: Seconds elapsed
        - findings_or_error: Parsed findings dict or error dict
    """
    if script_dir is None:
        script_dir = Path(__file__).resolve().parent

    # Write source code to a temporary file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, dir="/tmp"
    ) as f:
        f.write(source_code)
        temp_path = f.name

    try:
        # Build review_file.py command
        cmd = [
            "uv",
            "run",
            str(script_dir / "review_file.py"),
            temp_path,
            "--category",
            "logic-errors",
            "--language",
            language,
        ]

        # Run the review
        start_time = time.time()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=REVIEW_TIMEOUT,
        )
        elapsed = time.time() - start_time

        # Parse result
        if result.returncode == 0:
            # Success: parse findings
            try:
                findings = json.loads(result.stdout)
                return True, elapsed, {"findings_count": len(findings)}
            except json.JSONDecodeError:
                return False, elapsed, {"error": "Malformed findings JSON"}
        elif result.returncode == 2:
            # Retries exhausted
            return False, elapsed, {"error": "Retries exhausted"}
        else:
            # Config/input error
            return False, elapsed, {"error": f"Exit code {result.returncode}"}

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        return False, elapsed, {"error": f"Timeout after {REVIEW_TIMEOUT}s"}
    except Exception as e:
        elapsed = time.time() - start_time
        return False, elapsed, {"error": str(e)}
    finally:
        # Clean up temp file
        Path(temp_path).unlink(missing_ok=True)


def main():
    """Run calibration across target line counts."""
    script_dir = Path(__file__).resolve().parent

    print("=" * 70)
    print("API Input Size Calibration")
    print("=" * 70)
    print()

    results = []

    for line_count in TARGET_LINE_COUNTS:
        print(f"Testing {line_count:5d} lines...", end=" ", flush=True)

        # Generate synthetic file
        source_code = generate_synthetic_file(line_count)
        actual_lines = len(source_code.splitlines())

        # Run review
        success, elapsed, data = run_review(source_code, "python", script_dir)

        result_entry = {
            "line_count": line_count,
            "actual_lines": actual_lines,
            "success": success,
            "elapsed_sec": round(elapsed, 2),
        }
        result_entry.update(data)
        results.append(result_entry)

        status = "OK" if success else "FAIL"
        print(f"{status:4s} ({actual_lines:4d} actual lines, {elapsed:6.2f}s)")

    # Print summary table
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print()
    print(
        f"{'Lines':>8}  {'Actual':>8}  {'Status':>10}  {'Time (s)':>10}  {'Notes':20}"
    )
    print("-" * 70)

    for result in results:
        status = "SUCCESS" if result["success"] else "FAILED"
        findings = (
            f"({result.get('findings_count', 0)} findings)"
            if "findings_count" in result
            else ""
        )
        error = result.get("error", "")
        notes = findings or error

        print(
            f"{result['line_count']:>8}  {result['actual_lines']:>8}  {status:>10}  "
            f"{result['elapsed_sec']:>10.2f}  {notes:20}"
        )

    print()
    print("Note: Review with 'logic-errors' category.")
    print("      Successful tests are candidates for CHUNK_THRESHOLD.")
    print("      Set threshold to ~66% of the largest successful size.")


if __name__ == "__main__":
    main()
