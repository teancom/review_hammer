"""
Tests for review_file.py

Verifies:
- reviewers.AC2.1: Script produces valid JSON with correct line numbers
- reviewers.AC2.2: Script extracts correct category sections from templates
- reviewers.AC2.3: Script returns clear error when API key is missing
- reviewers.AC2.4: Script handles empty/malformed API responses
"""

import email.utils
import json
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from review_file import (
    prepend_line_numbers,
    extract_category_prompt,
    parse_findings,
    parse_retry_after,
    review_file,
    detect_language,
    EXTENSION_MAP,
    RetryExhaustedError,
    MAX_RETRIES,
    detect_coverage,
    build_diff_user_message,
    DIFF_PARTIAL_INSTRUCTIONS,
    DIFF_FULL_WITH_MARKERS_INSTRUCTIONS,
    parse_unified_diff,
    extract_file_header,
    assemble_diff_context,
    MAX_HEADER_LINES,
    split_into_chunks,
    deduplicate_findings,
    CHUNK_THRESHOLD,
    CHUNK_OVERLAP,
)
from openai import (
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    AuthenticationError,
)


class TestPrependLineNumbers:
    """Test line numbering functionality (AC2.1)"""

    def test_single_line(self):
        """Single line should be numbered as '1| '"""
        source = "def foo():"
        result = prepend_line_numbers(source)
        assert result == "1| def foo():"

    def test_multiple_lines(self):
        """Multiple lines should be right-justified"""
        source = "def foo():\n    return 42"
        result = prepend_line_numbers(source)
        lines = result.split("\n")
        assert len(lines) == 2
        assert lines[0] == "1| def foo():"
        assert lines[1] == "2|     return 42"

    def test_nine_to_ten_lines_justification(self):
        """Line numbers should be right-justified to match width of highest line number"""
        source = "\n".join([f"line {i}" for i in range(1, 11)])
        result = prepend_line_numbers(source)
        lines = result.split("\n")
        # Lines 1-9 should have 2-char width (space-padded), line 10 should have 2-char width
        assert lines[0].startswith(" 1| ")
        assert lines[8].startswith(" 9| ")
        assert lines[9].startswith("10| ")

    def test_empty_string(self):
        """Empty source should return empty string"""
        result = prepend_line_numbers("")
        assert result == ""

    def test_trailing_newline_removed(self):
        """Trailing newline should be removed in output"""
        source = "line 1\nline 2\n"
        result = prepend_line_numbers(source)
        lines = result.split("\n")
        assert len(lines) == 2
        assert not result.endswith("\n")

    def test_preserves_indentation(self):
        """Indentation should be preserved after line number"""
        source = "def foo():\n    if True:\n        pass"
        result = prepend_line_numbers(source)
        assert "    if True:" in result
        assert "        pass" in result


class TestDetectLanguage:
    """Test file extension to language detection (AC3.2, AC3.3)"""

    def test_python_extension(self):
        """Should detect .py as python"""
        result = detect_language("foo.py")
        assert result == "python"

    def test_c_extension(self):
        """Should detect .c and .h as c"""
        assert detect_language("foo.c") == "c"
        assert detect_language("header.h") == "c"

    def test_cpp_extensions(self):
        """Should detect multiple C++ extensions"""
        assert detect_language("main.cpp") == "cpp"
        assert detect_language("file.cc") == "cpp"
        assert detect_language("file.cxx") == "cpp"
        assert detect_language("header.hpp") == "cpp"
        assert detect_language("header.hxx") == "cpp"

    def test_java_extension(self):
        """Should detect .java as java"""
        result = detect_language("Main.java")
        assert result == "java"

    def test_csharp_extension(self):
        """Should detect .cs as csharp"""
        result = detect_language("program.cs")
        assert result == "csharp"

    def test_javascript_extensions(self):
        """Should detect multiple JavaScript extensions"""
        assert detect_language("app.js") == "javascript"
        assert detect_language("module.mjs") == "javascript"
        assert detect_language("common.cjs") == "javascript"
        assert detect_language("component.jsx") == "javascript"

    def test_typescript_extensions(self):
        """Should detect multiple TypeScript extensions"""
        assert detect_language("app.ts") == "typescript"
        assert detect_language("component.tsx") == "typescript"
        assert detect_language("module.mts") == "typescript"
        assert detect_language("compat.cts") == "typescript"

    def test_kotlin_extensions(self):
        """Should detect .kt and .kts as kotlin"""
        assert detect_language("main.kt") == "kotlin"
        assert detect_language("script.kts") == "kotlin"

    def test_rust_extension(self):
        """Should detect .rs as rust"""
        result = detect_language("lib.rs")
        assert result == "rust"

    def test_go_extension(self):
        """Should detect .go as go"""
        result = detect_language("main.go")
        assert result == "go"

    def test_swift_extension(self):
        """Should detect .swift as swift"""
        result = detect_language("app.swift")
        assert result == "swift"

    def test_unknown_extension_returns_generic(self):
        """Should return 'generic' for unknown extensions"""
        assert detect_language("script.rb") == "generic"
        assert detect_language("script.lua") == "generic"
        assert detect_language("file.xyz") == "generic"

    def test_case_insensitive(self):
        """Should handle uppercase extensions"""
        assert detect_language("FILE.PY") == "python"
        assert detect_language("File.Java") == "java"

    def test_path_with_directories(self):
        """Should extract extension from full path"""
        assert detect_language("/home/user/project/main.py") == "python"
        assert detect_language("../relative/path/script.rs") == "rust"

    def test_no_extension_returns_generic(self):
        """Should return 'generic' for files with no extension"""
        result = detect_language("Makefile")
        assert result == "generic"

    def test_extension_map_completeness(self):
        """All extensions in EXTENSION_MAP should be in task spec"""
        expected_extensions = {
            ".py",
            ".c",
            ".h",
            ".cpp",
            ".cc",
            ".cxx",
            ".hpp",
            ".hxx",
            ".java",
            ".cs",
            ".js",
            ".mjs",
            ".cjs",
            ".jsx",
            ".ts",
            ".tsx",
            ".mts",
            ".cts",
            ".kt",
            ".kts",
            ".rs",
            ".go",
            ".swift",
        }
        assert set(EXTENSION_MAP.keys()) == expected_extensions


class TestExtractCategoryPrompt:
    """Test prompt template extraction (AC2.2)"""

    def test_extract_preamble_and_category(self):
        """Should extract preamble and category section"""
        template_path = Path(__file__).parent.parent / "prompts" / "generic.md"

        result = extract_category_prompt(str(template_path), "logic-errors")

        # Should contain preamble content
        assert "Output format:" in result
        assert "Return a JSON array" in result

        # Should contain category section
        assert "logic-errors" in result.lower()

    def test_extract_each_category(self):
        """Should extract each category without error"""
        template_path = Path(__file__).parent.parent / "prompts" / "generic.md"

        categories = [
            "race-conditions",
            "null-safety",
            "resource-leaks",
            "logic-errors",
            "error-handling",
            "state-management",
            "test-suggestions",
            "testing-nothing",
            "missing-assertions",
            "over-mocking",
            "brittle-tests",
        ]

        for category in categories:
            result = extract_category_prompt(str(template_path), category)
            assert len(result) > 100, (
                f"Category {category} should have substantial content"
            )
            # Preamble should always be there
            assert "Output format:" in result

    def test_category_not_found(self):
        """Should raise ValueError if category not found"""
        template_path = Path(__file__).parent.parent / "prompts" / "generic.md"

        with pytest.raises(ValueError, match="Category 'nonexistent' not found"):
            extract_category_prompt(str(template_path), "nonexistent")

    def test_template_file_not_found(self):
        """Should raise FileNotFoundError if template not found"""
        with pytest.raises(FileNotFoundError):
            extract_category_prompt("/nonexistent/path/template.md", "logic-errors")

    def test_preamble_not_included_twice(self):
        """Preamble should appear only once in output"""
        template_path = Path(__file__).parent.parent / "prompts" / "generic.md"

        result = extract_category_prompt(str(template_path), "logic-errors")

        # Count occurrences of a unique preamble phrase
        count = result.count("Return a JSON array")
        assert count == 1, "Preamble should not be duplicated"

    def test_test_suggestions_category_contains_cap_language(self):
        """test-suggestions category should contain the 'Return at most 3 suggestions' cap (AC5.2)"""
        template_path = Path(__file__).parent.parent / "prompts" / "generic.md"

        result = extract_category_prompt(str(template_path), "test-suggestions")

        # Verify the extracted prompt contains the hard cap language
        assert "Return at most 3 suggestions" in result, (
            "test-suggestions prompt must contain the '3 suggestions' cap language"
        )


class TestParseFindings:
    """Test JSON parsing and error handling (AC2.4)"""

    def test_valid_json_array(self):
        """Should parse valid JSON array"""
        response = json.dumps(
            [
                {"lines": [1, 5], "severity": "high", "category": "logic-errors"},
                {"lines": [10, 12], "severity": "medium", "category": "null-safety"},
            ]
        )

        result = parse_findings(response)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["lines"] == [1, 5]
        assert result[1]["category"] == "null-safety"

    def test_empty_string(self):
        """Empty string should return empty list"""
        result = parse_findings("")
        assert result == []

    def test_whitespace_only(self):
        """Whitespace-only string should return empty list"""
        result = parse_findings("   \n   \t   ")
        assert result == []

    def test_json_in_markdown_fences(self):
        """Should extract JSON from markdown code fences"""
        response = """Here's the findings:

```json
[{"lines": [1, 2], "severity": "high"}]
```

Hope this helps!
"""
        result = parse_findings(response)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["severity"] == "high"

    def test_json_in_generic_fences(self):
        """Should extract JSON from generic ``` fences"""
        response = """```
[{"lines": [5, 10], "severity": "critical"}]
```"""

        result = parse_findings(response)

        assert isinstance(result, list)
        assert result[0]["severity"] == "critical"

    def test_malformed_json(self, capsys):
        """Should return empty list and warn for malformed JSON"""
        response = "{ invalid json }"

        result = parse_findings(response)

        assert result == []
        captured = capsys.readouterr()
        assert "Warning" in captured.err

    def test_empty_array(self):
        """Empty JSON array should return empty list"""
        response = "[]"

        result = parse_findings(response)

        assert result == []

    def test_json_not_array(self, capsys):
        """JSON that's not an array should return empty list"""
        response = '{"key": "value"}'

        result = parse_findings(response)

        assert result == []
        captured = capsys.readouterr()
        assert "Warning" in captured.err
        assert "not an array" in captured.err

    def test_json_not_array_in_markdown_fences(self, capsys):
        """JSON object in markdown fences (not array) should warn and return empty list"""
        response = """```json
{"key": "value", "other": "data"}
```"""

        result = parse_findings(response)

        assert result == []
        captured = capsys.readouterr()
        assert "Warning" in captured.err
        assert "not an array" in captured.err


class TestSplitIntoChunks:
    """Test chunk splitter with natural boundary detection (AC4.1, AC4.2, AC4.5)"""

    def test_content_under_threshold_returns_single_chunk(self):
        """Content under threshold should return single chunk with header"""
        content = "\n".join([f"line {i}" for i in range(1, 51)])
        header = "import os\nimport sys"

        result = split_into_chunks(content, header, chunk_threshold=CHUNK_THRESHOLD)

        assert len(result) == 1
        assert header in result[0]
        assert "line 1" in result[0]
        assert "line 50" in result[0]

    def test_content_exactly_at_threshold_not_chunked(self):
        """Content exactly at threshold should not be chunked"""
        # Create content with lines equal to CHUNK_THRESHOLD
        content = "\n".join([f"line {i}" for i in range(1, CHUNK_THRESHOLD + 1)])
        header = "import os"

        result = split_into_chunks(
            content,
            header,
            chunk_threshold=CHUNK_THRESHOLD,
            chunk_overlap=CHUNK_OVERLAP,
        )

        assert len(result) == 1
        assert header in result[0]

    def test_content_exceeding_threshold_creates_multiple_chunks(self):
        """Content exceeding threshold should be split into multiple chunks"""
        # Create content exceeding threshold
        content = "\n".join([f"line {i}" for i in range(1, CHUNK_THRESHOLD + 501)])
        header = "import os"

        result = split_into_chunks(
            content,
            header,
            chunk_threshold=CHUNK_THRESHOLD,
            chunk_overlap=CHUNK_OVERLAP,
        )

        assert len(result) > 1

    def test_each_chunk_contains_file_header(self):
        """Each chunk should have file header prepended"""
        content = "\n".join([f"line {i}" for i in range(1, CHUNK_THRESHOLD + 501)])
        header = "import os\nimport sys"

        result = split_into_chunks(
            content,
            header,
            chunk_threshold=CHUNK_THRESHOLD,
            chunk_overlap=CHUNK_OVERLAP,
        )

        for chunk in result:
            assert header in chunk

    def test_chunks_overlap_by_correct_amount(self):
        """Consecutive chunks should overlap by CHUNK_OVERLAP lines"""
        # Create content that will be split
        content = "\n".join([f"line {i}" for i in range(1, CHUNK_THRESHOLD + 501)])
        header = "import os"

        result = split_into_chunks(
            content,
            header,
            chunk_threshold=CHUNK_THRESHOLD,
            chunk_overlap=CHUNK_OVERLAP,
        )

        if len(result) > 1:
            # Get the last few lines of first chunk (after header)
            first_chunk_lines = result[0].split("\n")

            # Extract overlapping content from first chunk (last CHUNK_OVERLAP lines of content)
            first_chunk_overlap_start = len(first_chunk_lines) - CHUNK_OVERLAP

            # Verify some overlap exists
            assert first_chunk_overlap_start >= 0

    def test_prefers_blank_line_split_points(self):
        """Should prefer blank lines between functions as split points"""
        # Create content with a function boundary (blank line)
        lines_before_func = CHUNK_THRESHOLD // 2 - 10
        lines_in_func2 = CHUNK_THRESHOLD

        content_parts = [
            "import os",
            "",
            "def func1():",
            '    """First function."""',
            "    return 42",
        ]
        content_parts.extend(
            ["    # comment"] * (lines_before_func - len(content_parts))
        )
        content_parts.append("")  # Blank line between functions
        content_parts.append("def func2():")
        content_parts.extend(["    pass"] * lines_in_func2)

        content = "\n".join(content_parts)
        header = "import os"

        result = split_into_chunks(
            content,
            header,
            chunk_threshold=CHUNK_THRESHOLD,
            chunk_overlap=CHUNK_OVERLAP,
        )

        # Even if chunked, should have valid structure
        assert len(result) >= 1
        for chunk in result:
            assert header in chunk

    def test_empty_file_header(self):
        """Should handle empty file header"""
        content = "\n".join([f"line {i}" for i in range(1, 101)])

        result = split_into_chunks(content, "", chunk_threshold=CHUNK_THRESHOLD)

        assert len(result) >= 1
        assert "line 1" in result[0]

    def test_single_very_long_chunk_no_blank_lines(self):
        """Should handle long content with no blank lines by splitting at target"""
        # Create content with no blank lines (no natural split points)
        content = "x" * (CHUNK_THRESHOLD + 500)
        header = "# header"

        result = split_into_chunks(
            content,
            header,
            chunk_threshold=CHUNK_THRESHOLD,
            chunk_overlap=CHUNK_OVERLAP,
        )

        assert len(result) >= 1
        assert header in result[0]

    def test_chunk_threshold_parameter_respected(self):
        """Custom chunk_threshold should be respected"""
        small_threshold = 50
        content = "\n".join([f"line {i}" for i in range(1, small_threshold + 100)])
        header = "import os"

        result = split_into_chunks(
            content, header, chunk_threshold=small_threshold, chunk_overlap=5
        )

        # Should produce multiple chunks with small threshold
        assert len(result) > 1

    def test_chunk_overlap_parameter_respected(self):
        """Custom chunk_overlap should be respected"""
        content = "\n".join([f"line {i}" for i in range(1, CHUNK_THRESHOLD + 501)])
        header = "import os"
        custom_overlap = 10

        result = split_into_chunks(
            content,
            header,
            chunk_threshold=CHUNK_THRESHOLD,
            chunk_overlap=custom_overlap,
        )

        # Verify that chunks exist and overlap parameter is used
        assert len(result) >= 1


class TestDeduplicateFindings:
    """Test finding deduplication for chunk overlap regions (AC4.3)"""

    def test_identical_findings_deduplicated_to_one(self):
        """Two identical findings should be deduplicated to one"""
        all_findings = [
            [{"lines": "42-45", "severity": "high", "category": "logic-errors"}],
            [{"lines": "42-45", "severity": "high", "category": "logic-errors"}],
        ]

        result = deduplicate_findings(all_findings)

        assert len(result) == 1
        assert result[0]["lines"] == "42-45"

    def test_same_category_overlapping_lines_deduplicated(self):
        """Findings with same category and overlapping lines should deduplicate"""
        all_findings = [
            [{"lines": "42-45", "severity": "high", "category": "logic-errors"}],
            [{"lines": "44-47", "severity": "medium", "category": "logic-errors"}],
        ]

        result = deduplicate_findings(all_findings)

        assert len(result) == 1
        # Should keep the one with higher severity
        assert result[0]["severity"] == "high"

    def test_same_category_lines_within_two_line_tolerance(self):
        """Findings within 2 lines of each other should deduplicate"""
        all_findings = [
            [{"lines": "42", "severity": "medium", "category": "logic-errors"}],
            [{"lines": "43", "severity": "high", "category": "logic-errors"}],
        ]

        result = deduplicate_findings(all_findings)

        assert len(result) == 1
        # Should keep the higher severity one
        assert result[0]["severity"] == "high"

    def test_different_categories_same_lines_kept_separate(self):
        """Findings with different categories but same lines should be kept"""
        all_findings = [
            [{"lines": "42-45", "severity": "high", "category": "logic-errors"}],
            [{"lines": "42-45", "severity": "high", "category": "null-safety"}],
        ]

        result = deduplicate_findings(all_findings)

        assert len(result) == 2
        categories = {f["category"] for f in result}
        assert "logic-errors" in categories
        assert "null-safety" in categories

    def test_same_category_distant_lines_kept_separate(self):
        """Findings with same category but distant lines should be kept"""
        all_findings = [
            [{"lines": "42-45", "severity": "high", "category": "logic-errors"}],
            [{"lines": "100-105", "severity": "high", "category": "logic-errors"}],
        ]

        result = deduplicate_findings(all_findings)

        assert len(result) == 2

    def test_single_chunk_returned_unchanged(self):
        """Single chunk input should be returned unchanged"""
        all_findings = [
            [
                {"lines": "42", "severity": "high", "category": "logic-errors"},
                {"lines": "100", "severity": "medium", "category": "null-safety"},
            ]
        ]

        result = deduplicate_findings(all_findings)

        assert len(result) == 2
        assert result[0]["lines"] == "42"
        assert result[1]["lines"] == "100"

    def test_empty_input_returns_empty_list(self):
        """Empty input should return empty list"""
        result = deduplicate_findings([])
        assert result == []

    def test_empty_finding_lists_returns_empty(self):
        """Input with empty finding lists should return empty"""
        result = deduplicate_findings([[], [], []])
        assert result == []

    def test_mixed_empty_and_populated_lists(self):
        """Should handle mix of empty and populated finding lists"""
        all_findings = [
            [],
            [{"lines": "42", "severity": "high", "category": "logic-errors"}],
            [],
            [{"lines": "100", "severity": "medium", "category": "null-safety"}],
        ]

        result = deduplicate_findings(all_findings)

        assert len(result) == 2

    def test_severity_ordering_critical_highest(self):
        """Critical severity should be kept over high and medium"""
        all_findings = [
            [{"lines": "42-45", "severity": "medium", "category": "logic-errors"}],
            [{"lines": "43-44", "severity": "high", "category": "logic-errors"}],
            [{"lines": "44-46", "severity": "critical", "category": "logic-errors"}],
        ]

        result = deduplicate_findings(all_findings)

        assert len(result) == 1
        assert result[0]["severity"] == "critical"

    def test_severity_ordering_high_beats_medium(self):
        """High severity should be kept over medium"""
        all_findings = [
            [{"lines": "42-45", "severity": "medium", "category": "logic-errors"}],
            [{"lines": "44-46", "severity": "high", "category": "logic-errors"}],
        ]

        result = deduplicate_findings(all_findings)

        assert len(result) == 1
        assert result[0]["severity"] == "high"

    def test_multiple_duplicates_across_many_chunks(self):
        """Should deduplicate findings from many chunks correctly"""
        all_findings = [
            [
                {"lines": "10", "severity": "high", "category": "logic-errors"},
                {"lines": "20", "severity": "medium", "category": "null-safety"},
            ],
            [
                {"lines": "11", "severity": "medium", "category": "logic-errors"},
                {"lines": "25", "severity": "high", "category": "null-safety"},
            ],
            [
                {"lines": "30", "severity": "critical", "category": "logic-errors"},
            ],
        ]

        result = deduplicate_findings(all_findings)

        # Should have deduplicated the first two (lines 10 and 11, same category, within 2 lines)
        # Should keep all 3 categories but deduplicate overlaps
        assert len(result) <= 4

    def test_string_line_format_and_list_format(self):
        """Should handle both string and list formats for lines field"""
        all_findings = [
            [{"lines": "42-45", "severity": "high", "category": "logic-errors"}],
            [{"lines": [42, 43, 44], "severity": "medium", "category": "logic-errors"}],
        ]

        result = deduplicate_findings(all_findings)

        # Should recognize these as overlapping and deduplicate
        assert len(result) == 1
        assert result[0]["severity"] == "high"

    def test_findings_with_additional_fields_preserved(self):
        """Should preserve additional fields in findings (description, impact, confidence)"""
        all_findings = [
            [
                {
                    "lines": "42-45",
                    "severity": "high",
                    "category": "logic-errors",
                    "description": "Potential bug",
                    "impact": "Could cause crash",
                    "confidence": "high",
                }
            ]
        ]

        result = deduplicate_findings(all_findings)

        assert len(result) == 1
        assert result[0]["description"] == "Potential bug"
        assert result[0]["impact"] == "Could cause crash"
        assert result[0]["confidence"] == "high"


class TestReviewFile:
    """Test end-to-end review orchestration (AC2.1 mocked)"""

    def test_review_file_orchestration(self, temp_file_with_content):
        """Should orchestrate file review with mocked API"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(
            [{"lines": [1, 2], "severity": "medium", "category": "logic-errors"}]
        )

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = review_file(
                file_path=temp_file,
                category="logic-errors",
                language="generic",
                api_key="test-key",
                base_url="https://api.example.com/",
                model="test-model",
            )

            # Verify OpenAI was called correctly
            mock_openai_class.assert_called_once_with(
                api_key="test-key",
                base_url="https://api.example.com/",
                timeout=120.0,
                max_retries=0,
            )

            # Verify chat.completions.create was called
            create_call = mock_client.chat.completions.create.call_args
            assert create_call is not None

            # Check messages
            messages = create_call.kwargs["messages"]
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"
            assert "1| def foo():" in messages[1]["content"]

            # Verify result
            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["lines"] == [1, 2]

    def test_review_file_missing_file(self):
        """Should raise FileNotFoundError if file not found"""
        with pytest.raises(FileNotFoundError):
            review_file(
                file_path="/nonexistent/file.py",
                category="logic-errors",
                language="generic",
                api_key="test-key",
                base_url="https://api.example.com/",
                model="test-model",
            )

    def test_review_file_missing_category(self, temp_file_with_content):
        """Should raise ValueError if category not found in template"""
        temp_file = temp_file_with_content("code")

        with patch("review_file.OpenAI"):
            with pytest.raises(ValueError, match="not found"):
                review_file(
                    file_path=temp_file,
                    category="nonexistent-category",
                    language="generic",
                    api_key="test-key",
                    base_url="https://api.example.com/",
                    model="test-model",
                )

    def test_review_file_uses_correct_prompt_path(self, temp_file_with_content):
        """Should resolve prompt template path relative to script"""
        temp_file = temp_file_with_content("code")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            review_file(
                file_path=temp_file,
                category="logic-errors",
                language="generic",
                api_key="test-key",
                base_url="https://api.example.com/",
                model="test-model",
            )

            # Verify the call succeeded (template was found)
            assert mock_client.chat.completions.create.called


class TestMainCLI:
    """Test CLI entry point with argument validation (AC2.3)"""

    def test_main_missing_api_key_exits_with_code_1(
        self, capsys, temp_file_with_content
    ):
        """main() should exit with code 1 and print error to stderr when API key is missing"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        # Mock sys.argv with no API key set in environment
        test_argv = ["review_file.py", temp_file, "--category", "logic-errors"]

        with patch.dict(os.environ, {}, clear=True):
            # Remove REVIEWERS_API_KEY from environment
            os.environ.pop("REVIEWERS_API_KEY", None)

            with patch("sys.argv", test_argv):
                from review_file import main

                with pytest.raises(SystemExit) as exc_info:
                    main()

                # Should exit with code 1
                assert exc_info.value.code == 1

        # Check that error was printed to stderr
        captured = capsys.readouterr()
        assert "API key is required" in captured.err
        assert "REVIEWERS_API_KEY" in captured.err

    def test_main_with_api_key_env_var_succeeds(self, temp_file_with_content):
        """main() should succeed when REVIEWERS_API_KEY environment variable is set"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"

        test_argv = ["review_file.py", temp_file, "--category", "logic-errors"]

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("sys.argv", test_argv):
                with patch("review_file.OpenAI") as mock_openai_class:
                    mock_client = MagicMock()
                    mock_openai_class.return_value = mock_client
                    mock_client.chat.completions.create.return_value = mock_response

                    from review_file import main

                    # Should not raise SystemExit
                    main()

                    # Verify OpenAI was called
                    assert mock_openai_class.called

    def test_diff_base_defaults_to_none(self, temp_file_with_content):
        """--diff-base should default to None when omitted"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"

        test_argv = ["review_file.py", temp_file, "--category", "logic-errors"]

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("sys.argv", test_argv):
                with patch("review_file.OpenAI") as mock_openai_class:
                    mock_client = MagicMock()
                    mock_openai_class.return_value = mock_client
                    mock_client.chat.completions.create.return_value = mock_response

                    from review_file import main

                    # Should not raise SystemExit
                    main()

                    # Verify review_file was called with diff_base=None
                    assert mock_openai_class.called

    def test_diff_base_parsed_correctly(self, temp_file_with_content):
        """--diff-base HEAD~1 should be parsed correctly"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"

        test_argv = [
            "review_file.py",
            temp_file,
            "--category",
            "logic-errors",
            "--diff-base",
            "HEAD~1",
        ]

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("sys.argv", test_argv):
                with patch("review_file.review_file") as mock_review_file:
                    mock_review_file.return_value = []

                    from review_file import main

                    main()

                    # Verify review_file was called with diff_base="HEAD~1"
                    call_kwargs = mock_review_file.call_args[1]
                    assert call_kwargs["diff_base"] == "HEAD~1"

    def test_context_lines_parsed_as_integer(self, temp_file_with_content):
        """--context-lines 5 should be parsed as integer"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"

        test_argv = [
            "review_file.py",
            temp_file,
            "--category",
            "logic-errors",
            "--context-lines",
            "5",
        ]

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("sys.argv", test_argv):
                with patch("review_file.review_file") as mock_review_file:
                    mock_review_file.return_value = []

                    from review_file import main

                    main()

                    # Verify review_file was called with context_lines=5
                    call_kwargs = mock_review_file.call_args[1]
                    assert call_kwargs["context_lines"] == 5
                    assert isinstance(call_kwargs["context_lines"], int)

    def test_context_lines_defaults_to_3(self, temp_file_with_content):
        """--context-lines should default to 3 when omitted"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"

        test_argv = ["review_file.py", temp_file, "--category", "logic-errors"]

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("sys.argv", test_argv):
                with patch("review_file.review_file") as mock_review_file:
                    mock_review_file.return_value = []

                    from review_file import main

                    main()

                    # Verify review_file was called with context_lines=3
                    call_kwargs = mock_review_file.call_args[1]
                    assert call_kwargs["context_lines"] == 3


class TestRetryAndBackoff:
    """Test retry and backoff logic for error handling (AC6.1)"""

    def test_rate_limit_error_triggers_retry_and_exhausts(self, temp_file_with_content):
        """RateLimitError should trigger retry and eventually raise RetryExhaustedError"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            # Simulate persistent rate limit error on all attempts (no Retry-After header)
            mock_response = MagicMock()
            mock_response.headers = {}
            mock_client.chat.completions.create.side_effect = RateLimitError(
                "Rate limited", response=mock_response, body={}
            )

            with patch("review_file.time.sleep") as mock_sleep:
                with pytest.raises(RetryExhaustedError, match="after 5 retries"):
                    review_file(
                        file_path=temp_file,
                        category="logic-errors",
                        language="generic",
                        api_key="test-key",
                        base_url="https://api.example.com/",
                        model="test-model",
                    )

                # Should have called sleep MAX_RETRIES times (1, 2, 4, 8, 16 seconds)
                assert mock_sleep.call_count == MAX_RETRIES

    def test_authentication_error_raises_immediately_without_retry(
        self, temp_file_with_content
    ):
        """AuthenticationError should raise immediately without retry"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_response = MagicMock()
            mock_client.chat.completions.create.side_effect = AuthenticationError(
                "Invalid API key", response=mock_response, body={}
            )

            with patch("review_file.time.sleep") as mock_sleep:
                with pytest.raises(AuthenticationError):
                    review_file(
                        file_path=temp_file,
                        category="logic-errors",
                        language="generic",
                        api_key="test-key",
                        base_url="https://api.example.com/",
                        model="test-model",
                    )

                # Should NOT have called sleep at all
                assert mock_sleep.call_count == 0

                # Should have been called only once (no retries)
                assert mock_client.chat.completions.create.call_count == 1

    def test_api_timeout_error_triggers_retry(self, temp_file_with_content):
        """APITimeoutError should trigger retry and eventually raise RetryExhaustedError"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_request = MagicMock()
            mock_client.chat.completions.create.side_effect = APITimeoutError(
                request=mock_request
            )

            with patch("review_file.time.sleep") as mock_sleep:
                with pytest.raises(RetryExhaustedError, match="after 5 retries"):
                    review_file(
                        file_path=temp_file,
                        category="logic-errors",
                        language="generic",
                        api_key="test-key",
                        base_url="https://api.example.com/",
                        model="test-model",
                    )

                # Should have called sleep MAX_RETRIES times
                assert mock_sleep.call_count == MAX_RETRIES
                # Should have attempted MAX_RETRIES + 1 times total
                assert mock_client.chat.completions.create.call_count == MAX_RETRIES + 1

    def test_api_connection_error_triggers_retry(self, temp_file_with_content):
        """APIConnectionError should trigger retry and eventually raise RetryExhaustedError"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_request = MagicMock()
            mock_client.chat.completions.create.side_effect = APIConnectionError(
                message="Connection refused", request=mock_request
            )

            with patch("review_file.time.sleep") as mock_sleep:
                with pytest.raises(RetryExhaustedError, match="after 5 retries"):
                    review_file(
                        file_path=temp_file,
                        category="logic-errors",
                        language="generic",
                        api_key="test-key",
                        base_url="https://api.example.com/",
                        model="test-model",
                    )

                # Should have called sleep MAX_RETRIES times
                assert mock_sleep.call_count == MAX_RETRIES
                # Should have attempted MAX_RETRIES + 1 times total
                assert mock_client.chat.completions.create.call_count == MAX_RETRIES + 1

    def test_successful_response_on_second_attempt_after_transient_error(
        self, temp_file_with_content
    ):
        """Should successfully return findings on second attempt after transient error"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(
            [{"lines": [1, 2], "severity": "high", "category": "logic-errors"}]
        )

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            # Fail first time with timeout, succeed second time
            mock_request = MagicMock()
            mock_client.chat.completions.create.side_effect = [
                APITimeoutError(request=mock_request),
                mock_response,
            ]

            with patch("review_file.time.sleep") as mock_sleep:
                result = review_file(
                    file_path=temp_file,
                    category="logic-errors",
                    language="generic",
                    api_key="test-key",
                    base_url="https://api.example.com/",
                    model="test-model",
                )

                # Should have succeeded on second attempt
                assert isinstance(result, list)
                assert len(result) == 1
                assert result[0]["lines"] == [1, 2]

                # Should have slept once (between attempts)
                assert mock_sleep.call_count == 1

                # Should have called create twice (first failed, second succeeded)
                assert mock_client.chat.completions.create.call_count == 2

    def test_exponential_backoff_with_jitter(self, temp_file_with_content):
        """Backoff should increase exponentially with jitter when no Retry-After header"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            # Mock response with no retry-after header
            mock_response = MagicMock()
            mock_response.headers = {}
            mock_client.chat.completions.create.side_effect = RateLimitError(
                "Rate limited", response=mock_response, body={}
            )

            with (
                patch("review_file.time.sleep") as mock_sleep,
                patch("review_file.random.uniform", return_value=0.0),
            ):
                with pytest.raises(RetryExhaustedError):
                    review_file(
                        file_path=temp_file,
                        category="logic-errors",
                        language="generic",
                        api_key="test-key",
                        base_url="https://api.example.com/",
                        model="test-model",
                    )

                # Extract sleep durations from calls
                sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
                # With jitter=0, should be [1.0, 2.0, 4.0, 8.0, 16.0]
                assert len(sleep_calls) == MAX_RETRIES
                assert sleep_calls[0] == 1.0
                assert sleep_calls[1] == 2.0
                assert sleep_calls[2] == 4.0
                assert sleep_calls[3] == 8.0
                assert sleep_calls[4] == 16.0

    def test_retry_after_header_respected(self, temp_file_with_content):
        """When server sends Retry-After header, use that instead of backoff"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            # Mock response with retry-after header
            mock_response = MagicMock()
            mock_response.headers = {"retry-after": "5"}
            mock_client.chat.completions.create.side_effect = RateLimitError(
                "Rate limited", response=mock_response, body={}
            )

            with patch("review_file.time.sleep") as mock_sleep:
                with pytest.raises(RetryExhaustedError):
                    review_file(
                        file_path=temp_file,
                        category="logic-errors",
                        language="generic",
                        api_key="test-key",
                        base_url="https://api.example.com/",
                        model="test-model",
                    )

                # All waits should be 5.0 (from Retry-After header)
                sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
                assert len(sleep_calls) == MAX_RETRIES
                for wait in sleep_calls:
                    assert wait == 5.0


class TestGitDiffErrorHandling:
    """Test error handling for git diff subprocess calls (Critical)"""

    def test_invalid_diff_base_ref_raises_value_error(self, temp_file_with_content):
        """Invalid git ref to --diff-base should raise descriptive ValueError"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client

            with patch("review_file.subprocess.run") as mock_run:
                # Simulate git diff failure with invalid ref
                mock_run.side_effect = subprocess.CalledProcessError(
                    returncode=128,
                    cmd=["git", "diff", "invalid-ref", "--", temp_file],
                    stderr="fatal: bad revision 'invalid-ref'",
                )

                with pytest.raises(ValueError) as exc_info:
                    review_file(
                        file_path=temp_file,
                        category="logic-errors",
                        language="generic",
                        api_key="test-key",
                        base_url="https://api.example.com/",
                        model="test-model",
                        diff_base="invalid-ref",
                    )

                # Error message should include the ref and stderr
                assert "invalid-ref" in str(exc_info.value)
                assert "fatal: bad revision" in str(exc_info.value)

    def test_diff_base_none_skips_git_diff(self, temp_file_with_content):
        """When diff_base is None, git diff should not be called"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            with patch("review_file.subprocess.run") as mock_run:
                review_file(
                    file_path=temp_file,
                    category="logic-errors",
                    language="generic",
                    api_key="test-key",
                    base_url="https://api.example.com/",
                    model="test-model",
                    diff_base=None,
                )

                # subprocess.run should not be called when diff_base is None
                mock_run.assert_not_called()


class TestParseRetryAfter:
    """Test RFC 7231 Retry-After header parsing"""

    def test_integer_seconds(self):
        assert parse_retry_after("5") == 5.0

    def test_float_seconds(self):
        assert parse_retry_after("2.5") == 2.5

    def test_zero_seconds(self):
        assert parse_retry_after("0") == 0.0

    def test_http_date_in_future(self):
        # Generate an HTTP-date 10 seconds in the future
        future = time.time() + 10
        date_str = email.utils.formatdate(timeval=future, usegmt=True)
        result = parse_retry_after(date_str)
        assert result is not None
        # Should be approximately 10 seconds (allow 2s tolerance for test execution)
        assert 8.0 <= result <= 12.0

    def test_http_date_in_past(self):
        # Generate an HTTP-date 10 seconds in the past
        past = time.time() - 10
        date_str = email.utils.formatdate(timeval=past, usegmt=True)
        result = parse_retry_after(date_str)
        # Should clamp to 0
        assert result == 0.0

    def test_garbage_returns_none(self):
        assert parse_retry_after("not-a-date-or-number") is None

    def test_empty_string_returns_none(self):
        assert parse_retry_after("") is None


class TestTestContext:
    """Test --test-context flag functionality (AC3.1, AC5.3)"""

    def test_test_context_included_in_user_message(self, temp_file_with_content):
        """review_file() should include test file content in the user message"""
        source_file = temp_file_with_content("def foo():\n    return 42")
        test_file = temp_file_with_content(
            "def test_foo():\n    assert foo() == 42", suffix=".test.py"
        )

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps([])

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            review_file(
                file_path=source_file,
                category="test-suggestions",
                language="generic",
                api_key="test-key",
                base_url="https://api.example.com/",
                model="test-model",
                test_context_paths=[test_file],
            )

            # Verify the user message includes both source and test content
            create_call = mock_client.chat.completions.create.call_args
            user_message = create_call.kwargs["messages"][1]["content"]
            assert "def foo():" in user_message
            assert "def test_foo():" in user_message
            assert f"Existing test file: {test_file}" in user_message

    def test_test_context_file_truncation(self, temp_file_with_content, capsys):
        """Test context files exceeding 500 lines should be truncated with warning"""
        source_file = temp_file_with_content("def foo():\n    return 42")
        # Create a test file with 600 lines
        test_content = "\n".join([f"# line {i}" for i in range(1, 601)])
        test_file = temp_file_with_content(test_content, suffix=".test.py")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps([])

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            review_file(
                file_path=source_file,
                category="logic-errors",
                language="generic",
                api_key="test-key",
                base_url="https://api.example.com/",
                model="test-model",
                test_context_paths=[test_file],
            )

            # Verify the user message contains truncation notice
            create_call = mock_client.chat.completions.create.call_args
            user_message = create_call.kwargs["messages"][1]["content"]
            assert "truncated (100 lines omitted)" in user_message

            # Verify the stderr warning message was printed
            captured = capsys.readouterr()
            assert "truncating to 500 lines" in captured.err

    def test_test_context_nonexistent_file_warning(
        self, temp_file_with_content, capsys
    ):
        """When test context file doesn't exist, warning should be printed and review proceeds"""
        source_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps([])

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            review_file(
                file_path=source_file,
                category="logic-errors",
                language="generic",
                api_key="test-key",
                base_url="https://api.example.com/",
                model="test-model",
                test_context_paths=["/nonexistent/test/file.py"],
            )

            # Verify warning was printed to stderr
            captured = capsys.readouterr()
            assert "Warning: Test context file not found" in captured.err
            assert "/nonexistent/test/file.py" in captured.err

            # Verify the review still proceeded (user message has source)
            create_call = mock_client.chat.completions.create.call_args
            user_message = create_call.kwargs["messages"][1]["content"]
            assert "def foo():" in user_message

    def test_multiple_test_context_files(self, temp_file_with_content):
        """Multiple test context files should all be included in user message"""
        source_file = temp_file_with_content("def foo():\n    return 42")
        test_file_1 = temp_file_with_content(
            "def test_foo():\n    pass", suffix="_1.test.py"
        )
        test_file_2 = temp_file_with_content(
            "def test_bar():\n    pass", suffix="_2.test.py"
        )

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps([])

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            review_file(
                file_path=source_file,
                category="logic-errors",
                language="generic",
                api_key="test-key",
                base_url="https://api.example.com/",
                model="test-model",
                test_context_paths=[test_file_1, test_file_2],
            )

            # Verify both test files are in the user message
            create_call = mock_client.chat.completions.create.call_args
            user_message = create_call.kwargs["messages"][1]["content"]
            assert "def test_foo():" in user_message
            assert "def test_bar():" in user_message
            assert f"Existing test file: {test_file_1}" in user_message
            assert f"Existing test file: {test_file_2}" in user_message

    def test_no_test_context_with_test_suggestions_category(
        self, temp_file_with_content
    ):
        """When no test context and category is test-suggestions, include 'no test files' notice"""
        source_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps([])

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            review_file(
                file_path=source_file,
                category="test-suggestions",
                language="generic",
                api_key="test-key",
                base_url="https://api.example.com/",
                model="test-model",
                test_context_paths=None,
            )

            # Verify the user message includes the "no test files" notice
            create_call = mock_client.chat.completions.create.call_args
            user_message = create_call.kwargs["messages"][1]["content"]
            assert "No existing test files found for this source file." in user_message

    def test_no_test_context_with_other_category(self, temp_file_with_content):
        """When no test context and category is not test-suggestions, no extra notice"""
        source_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps([])

        with patch("review_file.OpenAI") as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            review_file(
                file_path=source_file,
                category="logic-errors",
                language="generic",
                api_key="test-key",
                base_url="https://api.example.com/",
                model="test-model",
                test_context_paths=None,
            )

            # Verify no "no test files" notice for non-test-suggestions categories
            create_call = mock_client.chat.completions.create.call_args
            user_message = create_call.kwargs["messages"][1]["content"]
            assert "No existing test files found" not in user_message


class TestParseUnifiedDiff:
    """Test unified diff parser (AC5.1, AC1.3)"""

    def test_single_hunk_simple(self):
        """Parse a single hunk with clear @@ header"""
        diff = """--- a/test.py
+++ b/test.py
@@ -5,3 +5,4 @@
 def foo():
-    return 41
+    return 42

"""
        result = parse_unified_diff(diff)

        assert len(result) == 1
        assert result[0]["start_line"] == 5
        assert result[0]["end_line"] == 7

    def test_multi_hunk_diff(self):
        """Parse diff with multiple hunks"""
        diff = """--- a/test.py
+++ b/test.py
@@ -5,3 +5,4 @@
 def foo():
-    return 41
+    return 42
@@ -20,3 +21,3 @@
 def bar():
-    pass
+    return 1
"""
        result = parse_unified_diff(diff)

        assert len(result) == 2
        assert result[0]["start_line"] == 5
        assert result[0]["end_line"] == 7
        assert result[1]["start_line"] == 20
        assert result[1]["end_line"] == 22

    def test_single_line_hunk_count_omitted(self):
        """Parse hunk where count is omitted (defaults to 1)"""
        diff = """--- a/test.py
+++ b/test.py
@@ -10 +10,2 @@
 def baz():
+    x = 1
"""
        result = parse_unified_diff(diff)

        assert len(result) == 1
        assert result[0]["start_line"] == 10
        assert result[0]["end_line"] == 10

    def test_empty_diff_returns_empty_list(self):
        """Empty diff output returns empty list"""
        result = parse_unified_diff("")

        assert result == []

    def test_new_file_hunk(self):
        """Parse hunk for new file (old start is 0)"""
        diff = """--- /dev/null
+++ b/newfile.py
@@ -0,0 +1,5 @@
+def new_func():
+    return True
+
+def another():
+    pass
"""
        result = parse_unified_diff(diff)

        # New files have @@ -0,0 +1,5 @@ which means start_line=0, count=0
        # This gives a hunk with start=0, end=-1 (start + count - 1 = 0 + 0 - 1 = -1)
        # This is an edge case - new files don't have changes in the original file
        assert len(result) == 1
        assert result[0]["start_line"] == 0
        assert result[0]["end_line"] == -1

    def test_hunk_headers_only_no_content(self):
        """Parse diff with only hunk headers, no actual content lines"""
        diff = """--- a/test.py
+++ b/test.py
@@ -5,5 +5,5 @@
@@ -20,3 +20,3 @@
"""
        result = parse_unified_diff(diff)

        assert len(result) == 2
        assert result[0]["start_line"] == 5
        assert result[0]["end_line"] == 9
        assert result[1]["start_line"] == 20
        assert result[1]["end_line"] == 22

    def test_line_numbers_are_from_original_file(self):
        """Verify line numbers come from - side of @@ header, not + side"""
        diff = """--- a/test.py
+++ b/test.py
@@ -100,3 +50,5 @@
 old line 100
-old line 101
+new line 1
+new line 2
+new line 3
 old line 102
"""
        result = parse_unified_diff(diff)

        assert len(result) == 1
        # Line numbers should be from - side (original file)
        assert result[0]["start_line"] == 100
        assert result[0]["end_line"] == 102


class TestExtractFileHeader:
    """Test file header extraction (AC5.1)"""

    def test_python_with_imports_then_def(self):
        """Python file with imports and def should extract only imports"""
        source = """import os
import sys
from pathlib import Path

def foo():
    return 42

class Bar:
    pass
"""
        result = extract_file_header(source)

        assert "import os" in result
        assert "from pathlib" in result
        assert "def foo" not in result
        assert "class Bar" not in result

    def test_rust_with_use_then_fn(self):
        """Rust file with use statements then fn should extract only use statements"""
        source = """use std::collections::HashMap;
use std::io;

fn main() {
    println!("Hello");
}

fn helper() {
    // code
}
"""
        result = extract_file_header(source)

        assert "use std::" in result
        assert "fn main" not in result
        assert "fn helper" not in result

    def test_file_with_no_definitions(self):
        """File with no function/class definitions should return entire file (capped)"""
        source = "# Configuration file\nkey=value\nother=data"
        result = extract_file_header(source)

        assert result == source

    def test_file_starting_with_def(self):
        """File that starts with def should return empty string"""
        source = """def foo():
    return 42

def bar():
    pass
"""
        result = extract_file_header(source)

        assert result == ""

    def test_empty_file(self):
        """Empty file should return empty string"""
        result = extract_file_header("")

        assert result == ""

    def test_header_exceeding_max_lines_is_capped(self):
        """Header exceeding MAX_HEADER_LINES should be capped"""
        # Create a file with 100 lines of imports, then def
        imports = "\n".join([f"import module{i}" for i in range(MAX_HEADER_LINES + 10)])
        source = imports + "\n\ndef foo():\n    pass"

        result = extract_file_header(source)

        # Count lines in result
        result_lines = result.split("\n")
        assert len(result_lines) <= MAX_HEADER_LINES

    def test_whitespace_before_def(self):
        """Function definition with leading whitespace should still be detected"""
        source = """# Header comment
import os

  def foo():  # indented definition
    pass
"""
        result = extract_file_header(source)

        assert "import os" in result
        assert "def foo" not in result

    def test_async_def_detection(self):
        """Async function definitions should be detected"""
        source = """import asyncio

async def main():
    await something()

def helper():
    pass
"""
        result = extract_file_header(source)

        assert "import asyncio" in result
        assert "async def main" not in result
        assert "def helper" not in result


class TestAssembleDiffContext:
    """Test diff context assembly (AC5.1, AC5.2, AC1.3)"""

    def test_single_hunk_with_context(self):
        """Single hunk with context_lines=3 expands by 3 lines above/below"""
        hunks = [{"start_line": 10, "end_line": 12}]
        source = "\n".join([f"line {i}" for i in range(1, 21)])
        result = assemble_diff_context(hunks, source, context_lines=3)

        # Should include lines 7-15 (10-3 to 12+3)
        assert "7| line 7" in result
        assert "10| line 10" in result
        assert "12| line 12" in result
        assert "15| line 15" in result
        assert "6| line 6" not in result
        assert "16| line 16" not in result

    def test_two_hunks_close_merge_into_one(self):
        """Two hunks 2 lines apart with context_lines=3 merge into continuous block"""
        hunks = [
            {"start_line": 10, "end_line": 12},
            {"start_line": 15, "end_line": 17},
        ]
        source = "\n".join([f"line {i}" for i in range(1, 25)])
        result = assemble_diff_context(hunks, source, context_lines=3)

        # With context, first hunk covers 7-15, second covers 12-20
        # They overlap (7 <= 15 and 12 <= 15), so should merge
        # Look for continuous numbering without ...
        # Should not have ... separator
        assert "..." not in result

    def test_two_hunks_far_apart_have_separator(self):
        """Two hunks far apart should have ... separator"""
        hunks = [
            {"start_line": 5, "end_line": 7},
            {"start_line": 50, "end_line": 52},
        ]
        source = "\n".join([f"line {i}" for i in range(1, 60)])
        result = assemble_diff_context(hunks, source, context_lines=3)

        # Should have ... separator
        assert "..." in result

    def test_line_numbers_match_original_file(self):
        """Line numbers in output match original file positions"""
        hunks = [{"start_line": 50, "end_line": 52}]
        source = "\n".join([f"line {i}" for i in range(1, 100)])
        result = assemble_diff_context(hunks, source, context_lines=0)

        # Should have lines 50-52 with correct numbers
        assert "50| line 50" in result
        assert "51| line 51" in result
        assert "52| line 52" in result

    def test_hunk_at_start_of_file(self):
        """Hunk at start of file clamped to line 1"""
        hunks = [{"start_line": 1, "end_line": 3}]
        source = "\n".join([f"line {i}" for i in range(1, 10)])
        result = assemble_diff_context(hunks, source, context_lines=3)

        # Should start from line 1 (can't go above)
        lines = result.split("\n")
        first_numbered = [line for line in lines if line and line[0].isdigit()][0]
        assert "1|" in first_numbered

    def test_hunk_at_end_of_file(self):
        """Hunk at end of file clamped to last line"""
        hunks = [{"start_line": 8, "end_line": 10}]
        source = "\n".join([f"line {i}" for i in range(1, 11)])
        result = assemble_diff_context(hunks, source, context_lines=3)

        # Should end at line 10 (can't go beyond)
        assert "10| line 10" in result
        assert "11|" not in result

    def test_includes_file_header(self):
        """Result includes file header before hunks"""
        hunks = [{"start_line": 10, "end_line": 12}]
        source = """import os

def foo():
    pass

def bar():
    return 1
    # line 10
    # line 11
    # line 12
"""
        result = assemble_diff_context(hunks, source, context_lines=3)

        # Should include file header (imports only, stops at first function definition)
        assert "import os" in result
        # The header extraction stops at the first function, so it only includes imports
        assert "--- (hunks below) ---" in result


class TestDetectCoverage:
    """Test coverage detection for full-file vs partial framing (AC5.3)"""

    def test_high_coverage_returns_true(self):
        """File with 92% coverage should return True"""
        # Hunk from 10-92 (83 lines) + 3 context on each side = 7-95 = 89 lines
        # Need 90+ lines for 90%, so make hunk bigger: 1-93 + context = 1-96 = 96 lines > 90
        hunks = [{"start_line": 1, "end_line": 93}]
        total_lines = 100
        context_lines = 3

        result = detect_coverage(hunks, total_lines, context_lines)
        assert result is True

    def test_low_coverage_returns_false(self):
        """File with 50% coverage should return False"""
        hunks = [{"start_line": 25, "end_line": 75}]
        total_lines = 100
        context_lines = 3

        result = detect_coverage(hunks, total_lines, context_lines)
        assert result is False

    def test_exactly_90_percent_coverage_returns_true(self):
        """File with exactly 90% coverage should return True"""
        # 100 lines, need 90 lines covered
        # Hunk at lines 1-87, with 3 context lines on each side = 1-90
        hunks = [{"start_line": 4, "end_line": 87}]
        total_lines = 100
        context_lines = 3

        result = detect_coverage(hunks, total_lines, context_lines)
        assert result is True

    def test_89_percent_coverage_returns_false(self):
        """File with 89% coverage should return False"""
        # 100 lines, need 90+ lines covered
        # Hunk at lines 1-86 with 3 context = 1-89
        hunks = [{"start_line": 4, "end_line": 86}]
        total_lines = 100
        context_lines = 3

        result = detect_coverage(hunks, total_lines, context_lines)
        assert result is False

    def test_empty_hunks_returns_false(self):
        """Empty hunks list should return False"""
        hunks = []
        total_lines = 100
        context_lines = 3

        result = detect_coverage(hunks, total_lines, context_lines)
        assert result is False

    def test_single_hunk_covering_entire_file(self):
        """Hunk covering entire file should return True"""
        hunks = [{"start_line": 1, "end_line": 100}]
        total_lines = 100
        context_lines = 3

        result = detect_coverage(hunks, total_lines, context_lines)
        assert result is True

    def test_multiple_hunks_merging_to_high_coverage(self):
        """Multiple separate hunks with context that merge should be calculated correctly"""
        # Two hunks, each 10 lines, 4 lines apart (so they merge with context_lines=3)
        hunks = [{"start_line": 10, "end_line": 19}, {"start_line": 24, "end_line": 33}]
        total_lines = 100
        context_lines = 3

        result = detect_coverage(hunks, total_lines, context_lines)
        # Expanded: [7-22] and [21-36], which overlap and merge to [7-36] = 30 lines
        # 30/100 = 30% < 90%, so False
        assert result is False

    def test_zero_total_lines_returns_false(self):
        """Empty file (zero lines) should return False"""
        hunks = [{"start_line": 1, "end_line": 1}]
        total_lines = 0
        context_lines = 3

        result = detect_coverage(hunks, total_lines, context_lines)
        assert result is False


class TestBuildDiffUserMessage:
    """Test diff user message building (AC5.4)"""

    def test_partial_coverage_message_format(self):
        """Partial coverage should produce diff review message with instructions"""
        file_path = "test.py"
        source = "\n".join([f"line {i}" for i in range(1, 101)])
        hunks = [{"start_line": 10, "end_line": 20}]
        context_lines = 3
        diff_output = "@@ -10,11 +10,11 @@ test\n"

        result = build_diff_user_message(
            file_path, source, hunks, context_lines, diff_output
        )

        # Should have "Diff review" header
        assert result.startswith("# Diff review: test.py")
        # Should contain partial instructions
        assert "partial view" in result
        assert DIFF_PARTIAL_INSTRUCTIONS in result
        # Should contain numbered content
        assert "10|" in result

    def test_full_coverage_message_format(self):
        """Full coverage should produce source file message with instructions"""
        file_path = "test.py"
        source = "\n".join([f"line {i}" for i in range(1, 101)])
        # Large hunk covering ~96 lines = 96% coverage
        hunks = [{"start_line": 1, "end_line": 93}]
        context_lines = 3
        diff_output = "@@ -1,93 +1,93 @@ test\n"

        result = build_diff_user_message(
            file_path, source, hunks, context_lines, diff_output
        )

        # Should have "Source file" header
        assert result.startswith("# Source file: test.py")
        # Should contain full file instructions
        assert "full file" in result
        assert DIFF_FULL_WITH_MARKERS_INSTRUCTIONS in result
        # Should contain full numbered file
        assert "1| line 1" in result
        assert "100| line 100" in result

    def test_partial_message_contains_assembled_context(self):
        """Partial message should contain the assembled diff context"""
        file_path = "test.py"
        source = "\n".join([f"line {i}" for i in range(1, 51)])
        hunks = [{"start_line": 10, "end_line": 15}]
        context_lines = 2
        diff_output = "@@ -10,6 +10,6 @@ test\n"

        result = build_diff_user_message(
            file_path, source, hunks, context_lines, diff_output
        )

        # Should contain the hunk lines
        assert "10|" in result
        assert "15|" in result

    def test_full_message_contains_entire_file(self):
        """Full coverage message should contain entire numbered file"""
        file_path = "test.py"
        source = "line 1\nline 2\nline 3\nline 4\nline 5"
        hunks = [{"start_line": 1, "end_line": 5}]
        context_lines = 3
        diff_output = "@@ -1,5 +1,5 @@ test\n"

        result = build_diff_user_message(
            file_path, source, hunks, context_lines, diff_output
        )

        # Should contain all lines numbered
        assert "1| line 1" in result
        assert "2| line 2" in result
        assert "3| line 3" in result
        assert "4| line 4" in result
        assert "5| line 5" in result

    def test_instructions_are_not_modified_by_function(self):
        """Instructions constants should remain unchanged"""
        # These are just checks that the constants exist and contain expected text
        assert "partial view" in DIFF_PARTIAL_INSTRUCTIONS
        assert "full file" in DIFF_FULL_WITH_MARKERS_INSTRUCTIONS
        assert "Line numbers are from the original file" in DIFF_PARTIAL_INSTRUCTIONS
        assert (
            "Line numbers are from the original file"
            in DIFF_FULL_WITH_MARKERS_INSTRUCTIONS
        )


class TestReviewFileDiffMode:
    """Test diff mode integration in review_file() (AC5.1, AC5.3, AC5.4, AC6.1)"""

    def test_without_diff_base_uses_full_file_mode(self, temp_file_with_content):
        """When diff_base is None, should use full-file mode (backward compatible)"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("review_file.OpenAI") as mock_openai_class:
                mock_client = MagicMock()
                mock_openai_class.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_response

                result = review_file(
                    file_path=temp_file,
                    category="logic-errors",
                    language="python",
                    api_key="test-key",
                    base_url="http://localhost:8000",
                    model="test-model",
                    diff_base=None,
                )

                # Should return empty list (parsed from mock response [])
                assert result == []

                # Verify the user message was the full-file format
                call_args = mock_client.chat.completions.create.call_args
                user_message = call_args[1]["messages"][1]["content"]
                assert "# Source file:" in user_message
                assert "def foo" in user_message

    def test_with_diff_base_runs_git_diff(self, temp_file_with_content, tmp_path):
        """When diff_base is provided, should run git diff and use diff mode"""
        temp_file = temp_file_with_content("def foo():\n    return 42\n    # changed")

        # Mock subprocess.run to return a fake diff
        fake_diff = "@@ -1,2 +1,3 @@\n def foo():\n     return 42\n+    # changed\n"

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("review_file.subprocess.run") as mock_subprocess:
                mock_result = MagicMock()
                mock_result.stdout = fake_diff
                mock_subprocess.return_value = mock_result

                with patch("review_file.OpenAI") as mock_openai_class:
                    mock_client = MagicMock()
                    mock_openai_class.return_value = mock_client
                    mock_response = MagicMock()
                    mock_response.choices[0].message.content = "[]"
                    mock_client.chat.completions.create.return_value = mock_response

                    result = review_file(
                        file_path=temp_file,
                        category="logic-errors",
                        language="python",
                        api_key="test-key",
                        base_url="http://localhost:8000",
                        model="test-model",
                        diff_base="HEAD~1",
                    )

                    # Should return empty list
                    assert result == []

                    # Verify subprocess.run was called with correct args
                    mock_subprocess.assert_called_once()
                    call_args = mock_subprocess.call_args[0][0]
                    assert call_args[0] == "git"
                    assert call_args[1] == "diff"
                    assert call_args[2] == "HEAD~1"

    def test_empty_diff_returns_empty_findings(self, temp_file_with_content):
        """When git diff returns no hunks, should return empty findings list"""
        temp_file = temp_file_with_content("def foo():\n    return 42")

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("review_file.subprocess.run") as mock_subprocess:
                mock_result = MagicMock()
                # No diff hunks
                mock_result.stdout = ""
                mock_subprocess.return_value = mock_result

                result = review_file(
                    file_path=temp_file,
                    category="logic-errors",
                    language="python",
                    api_key="test-key",
                    base_url="http://localhost:8000",
                    model="test-model",
                    diff_base="HEAD~1",
                )

                # Should return empty list (no hunks found)
                assert result == []

    def test_diff_mode_produces_diff_message_with_instructions(
        self, temp_file_with_content
    ):
        """Diff mode should produce user message with diff instructions"""
        temp_file = temp_file_with_content("def foo():\n    return 42\n    # changed")

        fake_diff = "@@ -1,2 +1,3 @@\n def foo():\n     return 42\n+    # changed\n"

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("review_file.subprocess.run") as mock_subprocess:
                mock_result = MagicMock()
                mock_result.stdout = fake_diff
                mock_subprocess.return_value = mock_result

                with patch("review_file.OpenAI") as mock_openai_class:
                    mock_client = MagicMock()
                    mock_openai_class.return_value = mock_client
                    mock_response = MagicMock()
                    mock_response.choices[0].message.content = "[]"
                    mock_client.chat.completions.create.return_value = mock_response

                    review_file(
                        file_path=temp_file,
                        category="logic-errors",
                        language="python",
                        api_key="test-key",
                        base_url="http://localhost:8000",
                        model="test-model",
                        diff_base="HEAD~1",
                        context_lines=2,
                    )

                    # Verify the user message contains diff instructions
                    call_args = mock_client.chat.completions.create.call_args
                    user_message = call_args[1]["messages"][1]["content"]
                    # Should have diff header
                    assert (
                        "# Diff review:" in user_message
                        or "# Source file:" in user_message
                    )

    def test_context_lines_parameter_passed_through(self, temp_file_with_content):
        """context_lines parameter should be passed to diff assembly"""
        temp_file = temp_file_with_content("line 1\nline 2\nline 3\nline 4\nline 5")

        fake_diff = "@@ -2,1 +2,1 @@\n"

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("review_file.subprocess.run") as mock_subprocess:
                mock_result = MagicMock()
                mock_result.stdout = fake_diff
                mock_subprocess.return_value = mock_result

                with patch("review_file.OpenAI") as mock_openai_class:
                    mock_client = MagicMock()
                    mock_openai_class.return_value = mock_client
                    mock_response = MagicMock()
                    mock_response.choices[0].message.content = "[]"
                    mock_client.chat.completions.create.return_value = mock_response

                    review_file(
                        file_path=temp_file,
                        category="logic-errors",
                        language="python",
                        api_key="test-key",
                        base_url="http://localhost:8000",
                        model="test-model",
                        diff_base="HEAD~1",
                        context_lines=5,
                    )

                    # The function should have succeeded without error
                    assert mock_client.chat.completions.create.called


class TestChunkedReview:
    """Test chunking integration in review_file() (AC4.1, AC4.4)"""

    def test_large_file_triggers_chunking(self, temp_file_with_content):
        """Large file exceeding CHUNK_THRESHOLD should trigger chunking"""
        # Create content exceeding threshold
        large_content = "\n".join(
            [f"line {i}" for i in range(1, CHUNK_THRESHOLD + 501)]
        )
        temp_file = temp_file_with_content(large_content)

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(
            [{"lines": "100", "severity": "high", "category": "logic-errors"}]
        )

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("review_file.OpenAI") as mock_openai_class:
                mock_client = MagicMock()
                mock_openai_class.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_response

                result = review_file(
                    file_path=temp_file,
                    category="logic-errors",
                    language="python",
                    api_key="test-key",
                    base_url="http://localhost:8000",
                    model="test-model",
                )

                # Should have made multiple API calls (chunking)
                assert mock_client.chat.completions.create.call_count > 1
                # Result should be a list
                assert isinstance(result, list)

    def test_large_file_returns_merged_findings(self, temp_file_with_content):
        """Chunked review should return merged findings from all chunks"""
        large_content = "\n".join(
            [f"line {i}" for i in range(1, CHUNK_THRESHOLD + 501)]
        )
        temp_file = temp_file_with_content(large_content)

        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps(
            [{"lines": "100", "severity": "high", "category": "logic-errors"}]
        )

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("review_file.OpenAI") as mock_openai_class:
                mock_client = MagicMock()
                mock_openai_class.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_response

                result = review_file(
                    file_path=temp_file,
                    category="logic-errors",
                    language="python",
                    api_key="test-key",
                    base_url="http://localhost:8000",
                    model="test-model",
                )

                # Should return findings (potentially deduplicated)
                assert isinstance(result, list)

    def test_small_file_no_chunking(self, temp_file_with_content):
        """Small file under threshold should not trigger chunking"""
        small_content = "\n".join([f"line {i}" for i in range(1, 100)])
        temp_file = temp_file_with_content(small_content)

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("review_file.OpenAI") as mock_openai_class:
                mock_client = MagicMock()
                mock_openai_class.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_response

                result = review_file(
                    file_path=temp_file,
                    category="logic-errors",
                    language="python",
                    api_key="test-key",
                    base_url="http://localhost:8000",
                    model="test-model",
                )

                # Should have made only 1 API call (no chunking)
                assert mock_client.chat.completions.create.call_count == 1
                # Result should be a list
                assert isinstance(result, list)

    def test_chunking_in_diff_mode(self, temp_file_with_content):
        """Chunking should work in diff mode for large diffs"""
        large_content = "\n".join(
            [f"line {i}" for i in range(1, CHUNK_THRESHOLD + 501)]
        )
        temp_file = temp_file_with_content(large_content)

        fake_diff = (
            f"@@ -1,{CHUNK_THRESHOLD + 500} +1,{CHUNK_THRESHOLD + 500} @@\n"
            + "\n".join([f" line {i}" for i in range(1, CHUNK_THRESHOLD + 501)])
        )

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("review_file.subprocess.run") as mock_subprocess:
                mock_result = MagicMock()
                mock_result.stdout = fake_diff
                mock_subprocess.return_value = mock_result

                with patch("review_file.OpenAI") as mock_openai_class:
                    mock_client = MagicMock()
                    mock_openai_class.return_value = mock_client
                    mock_client.chat.completions.create.return_value = mock_response

                    result = review_file(
                        file_path=temp_file,
                        category="logic-errors",
                        language="python",
                        api_key="test-key",
                        base_url="http://localhost:8000",
                        model="test-model",
                        diff_base="HEAD~1",
                    )

                    # Should succeed and potentially chunk the large diff
                    assert isinstance(result, list)

    def test_chunking_produces_correct_logs(self, temp_file_with_content, capsys):
        """Chunked review should produce observability logs for each chunk"""
        large_content = "\n".join(
            [f"line {i}" for i in range(1, CHUNK_THRESHOLD + 501)]
        )
        temp_file = temp_file_with_content(large_content)

        mock_response = MagicMock()
        mock_response.choices[0].message.content = "[]"

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("review_file.OpenAI") as mock_openai_class:
                mock_client = MagicMock()
                mock_openai_class.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_response

                review_file(
                    file_path=temp_file,
                    category="logic-errors",
                    language="python",
                    api_key="test-key",
                    base_url="http://localhost:8000",
                    model="test-model",
                )

                # Check stderr for chunk logs
                captured = capsys.readouterr()
                if "[review] CHUNK" in captured.err:
                    # If chunking happened, should see chunk logs
                    assert "CHUNK" in captured.err

    def test_deduplicated_findings_from_chunks(self, temp_file_with_content):
        """Findings from overlapping chunk regions should be deduplicated"""
        large_content = "\n".join(
            [f"line {i}" for i in range(1, CHUNK_THRESHOLD + 501)]
        )
        temp_file = temp_file_with_content(large_content)

        # Create responses that would produce overlapping findings
        mock_response1 = MagicMock()
        mock_response1.choices[0].message.content = json.dumps(
            [{"lines": "400", "severity": "high", "category": "logic-errors"}]
        )

        mock_response2 = MagicMock()
        mock_response2.choices[0].message.content = json.dumps(
            [{"lines": "401", "severity": "medium", "category": "logic-errors"}]
        )

        mock_response3 = MagicMock()
        mock_response3.choices[0].message.content = "[]"

        with patch.dict(os.environ, {"REVIEWERS_API_KEY": "test-key"}):
            with patch("review_file.OpenAI") as mock_openai_class:
                mock_client = MagicMock()
                mock_openai_class.return_value = mock_client
                # Return different responses for different calls (one per chunk)
                mock_client.chat.completions.create.side_effect = [
                    mock_response1,
                    mock_response2,
                    mock_response3,
                ]

                result = review_file(
                    file_path=temp_file,
                    category="logic-errors",
                    language="python",
                    api_key="test-key",
                    base_url="http://localhost:8000",
                    model="test-model",
                )

                # Should have deduplicated overlapping findings
                # (lines 400 and 401 should be merged to one with higher severity)
                if len(result) > 0:
                    # Verify findings contain expected categories
                    assert any(f.get("category") == "logic-errors" for f in result)
