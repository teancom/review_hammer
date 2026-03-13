#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
test_corpus.py - Review calibration test runner.

Discovers test corpus files under tests/corpus/, invokes review_file.py
for each, and validates results against expected outcomes.

Usage:
    uv run scripts/test_corpus.py [--corpus-dir CORPUS_DIR]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REQUIRED_METADATA_FIELDS = {"type", "category", "language", "description", "expect_empty"}
REVIEW_TIMEOUT = 180  # seconds

# Subset of review_file.py's EXTENSION_MAP for language/extension validation
EXTENSION_TO_LANGUAGE = {
    ".py": "python", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp",
    ".java": "java", ".cs": "csharp", ".js": "javascript", ".ts": "typescript",
    ".kt": "kotlin", ".rs": "rust", ".go": "go", ".swift": "swift",
}


def discover_cases(corpus_dir: Path) -> list[dict]:
    """Discover all test cases by globbing for .json metadata files."""
    cases = []
    for meta_path in sorted(corpus_dir.glob("**/*.json")):
        cases.append({"meta_path": meta_path})
    return cases


def validate_metadata(meta_path: Path) -> tuple[dict | None, str | None]:
    """Load and validate a metadata JSON file. Returns (metadata, error)."""
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except json.JSONDecodeError as e:
        return None, f"Malformed JSON: {e}"

    missing = REQUIRED_METADATA_FIELDS - set(meta.keys())
    if missing:
        return None, f"Missing required fields: {', '.join(sorted(missing))}"

    if meta["type"] not in ("clean", "bug", "adversarial"):
        return None, f"Invalid type: {meta['type']} (expected clean, bug, or adversarial)"

    if not isinstance(meta["expect_empty"], bool):
        return None, f"expect_empty must be boolean, got {type(meta['expect_empty']).__name__}"

    return meta, None


def find_source_file(meta_path: Path) -> Path | None:
    """Find the companion source file matching the metadata file's stem."""
    stem = meta_path.stem
    parent = meta_path.parent
    for candidate in parent.iterdir():
        if candidate.stem == stem and candidate.suffix != ".json":
            return candidate
    return None


def run_review(source_path: Path, category: str, language: str, script_dir: Path) -> tuple[list | None, str | None]:
    """Run review_file.py and return (findings, error)."""
    cmd = [
        "uv", "run", str(script_dir / "review_file.py"),
        str(source_path),
        "--category", category,
        "--language", language,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=REVIEW_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return None, f"Review timed out after {REVIEW_TIMEOUT}s"

    if result.returncode == 1:
        return None, f"Config/input error (exit 1): {result.stderr.strip()}"

    # Exit code 2 means retries exhausted — review_file.py prints [] to stdout
    # Exit code 0 means success — findings in stdout
    try:
        findings = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, f"Failed to parse findings JSON: {result.stdout[:200]}"

    return findings, None


def apply_gate(meta: dict, findings: list) -> tuple[bool, str]:
    """Apply automated pass/fail gate. Returns (passed, reason)."""
    if meta["expect_empty"]:
        if len(findings) == 0:
            return True, "Clean file returned no findings (expected)"
        else:
            descs = [f["description"][:80] for f in findings[:3]]
            return False, f"Clean file returned {len(findings)} unexpected finding(s): {descs}"
    else:
        if len(findings) == 0:
            return False, "Bug/adversarial file returned no findings (expected non-empty)"

        expected_cat = meta["category"]
        matching = [f for f in findings if f.get("category") == expected_cat]
        if matching:
            return True, f"Found {len(matching)} finding(s) in expected category '{expected_cat}'"
        else:
            found_cats = list(set(f.get("category", "unknown") for f in findings))
            return False, f"Findings exist but none match category '{expected_cat}' (found: {found_cats})"


def main():
    parser = argparse.ArgumentParser(description="Review calibration test runner")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=None,
        help="Path to corpus directory (default: tests/corpus/ relative to repo root)",
    )
    args = parser.parse_args()

    # Resolve paths relative to this script's location
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    corpus_dir = args.corpus_dir or (repo_root / "tests" / "corpus")
    if not corpus_dir.exists():
        print(f"ERROR: Corpus directory not found: {corpus_dir}", file=sys.stderr)
        sys.exit(1)

    cases = discover_cases(corpus_dir)
    if not cases:
        print(f"No test cases found in {corpus_dir}")
        print("\nSummary: 0 passed, 0 failed, 0 errors (no cases found)")
        sys.exit(0)

    results = []
    for case in cases:
        meta_path = case["meta_path"]
        rel_path = meta_path.relative_to(corpus_dir)
        print(f"\n{'='*60}")
        print(f"Case: {rel_path}")

        # Validate metadata
        meta, error = validate_metadata(meta_path)
        if error:
            print(f"  ERROR: {error}")
            results.append({"case": str(rel_path), "status": "error", "reason": error})
            continue

        print(f"  Type: {meta['type']}, Category: {meta['category']}, Expect empty: {meta['expect_empty']}")

        # Find source file
        source_path = find_source_file(meta_path)
        if source_path is None:
            error = f"No companion source file found for {meta_path.name}"
            print(f"  ERROR: {error}")
            results.append({"case": str(rel_path), "status": "error", "reason": error})
            continue

        print(f"  Source: {source_path.name}")

        # Warn if metadata language doesn't match source file extension
        expected_lang = EXTENSION_TO_LANGUAGE.get(source_path.suffix)
        if expected_lang and expected_lang != meta["language"]:
            print(f"  WARNING: metadata language '{meta['language']}' does not match "
                  f"source extension '{source_path.suffix}' (expected '{expected_lang}')")

        # Run review
        findings, error = run_review(source_path, meta["category"], meta["language"], script_dir)
        if error:
            print(f"  ERROR: {error}")
            results.append({
                "case": str(rel_path),
                "status": "error",
                "reason": error,
            })
            continue

        # Apply gate
        passed, reason = apply_gate(meta, findings)
        status = "pass" if passed else "fail"
        print(f"  Result: {status.upper()} — {reason}")

        result_entry = {
            "case": str(rel_path),
            "status": status,
            "reason": reason,
            "type": meta["type"],
            "category": meta["category"],
        }
        if not passed:
            result_entry["findings"] = findings
        results.append(result_entry)

    # Summary
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    errors = sum(1 for r in results if r["status"] == "error")

    print(f"\n{'='*60}")
    print(f"Summary: {passed} passed, {failed} failed, {errors} errors out of {len(results)} cases")

    if failed > 0 or errors > 0:
        print("\nFailed/errored cases:")
        for r in results:
            if r["status"] in ("fail", "error"):
                print(f"  {r['status'].upper()}: {r['case']} — {r['reason']}")
                if "findings" in r:
                    print(f"    Raw findings: {json.dumps(r['findings'], indent=2)}")

    sys.exit(0 if (failed == 0 and errors == 0) else 1)


if __name__ == "__main__":
    main()
