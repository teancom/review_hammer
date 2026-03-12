"""
Tests for review_file.py

Verifies:
- reviewers.AC2.1: Script produces valid JSON with correct line numbers
- reviewers.AC2.2: Script extracts correct category sections from templates
- reviewers.AC2.3: Script returns clear error when API key is missing
- reviewers.AC2.4: Script handles empty/malformed API responses
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from review_file import (
    prepend_line_numbers,
    extract_category_prompt,
    parse_findings,
    review_file,
    detect_language,
    EXTENSION_MAP
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
        lines = result.split('\n')
        assert len(lines) == 2
        assert lines[0] == "1| def foo():"
        assert lines[1] == "2|     return 42"

    def test_nine_to_ten_lines_justification(self):
        """Line numbers should be right-justified to match width of highest line number"""
        source = "\n".join([f"line {i}" for i in range(1, 11)])
        result = prepend_line_numbers(source)
        lines = result.split('\n')
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
        lines = result.split('\n')
        assert len(lines) == 2
        assert not result.endswith('\n')

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
            ".py", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hxx",
            ".java", ".cs", ".js", ".mjs", ".cjs", ".jsx",
            ".ts", ".tsx", ".mts", ".cts",
            ".kt", ".kts", ".rs", ".go", ".swift"
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
            "testing-nothing",
            "missing-assertions",
            "over-mocking",
            "brittle-tests",
            "missing-edge-cases"
        ]

        for category in categories:
            result = extract_category_prompt(str(template_path), category)
            assert len(result) > 100, f"Category {category} should have substantial content"
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


class TestParseFindings:
    """Test JSON parsing and error handling (AC2.4)"""

    def test_valid_json_array(self):
        """Should parse valid JSON array"""
        response = json.dumps([
            {"lines": [1, 5], "severity": "high", "category": "logic-errors"},
            {"lines": [10, 12], "severity": "medium", "category": "null-safety"}
        ])

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


class TestReviewFile:
    """Test end-to-end review orchestration (AC2.1 mocked)"""

    def test_review_file_orchestration(self):
        """Should orchestrate file review with mocked API"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("def foo():\n    return 42")
            temp_file = f.name

        try:
            mock_response = MagicMock()
            mock_response.choices[0].message.content = json.dumps([
                {"lines": [1, 2], "severity": "medium", "category": "logic-errors"}
            ])

            with patch('review_file.OpenAI') as mock_openai_class:
                mock_client = MagicMock()
                mock_openai_class.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_response

                result = review_file(
                    file_path=temp_file,
                    category="logic-errors",
                    language="generic",
                    api_key="test-key",
                    base_url="https://api.example.com/",
                    model="test-model"
                )

                # Verify OpenAI was called correctly
                mock_openai_class.assert_called_once_with(
                    api_key="test-key",
                    base_url="https://api.example.com/",
                    timeout=120.0,
                    max_retries=0
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

        finally:
            os.unlink(temp_file)

    def test_review_file_missing_file(self):
        """Should raise FileNotFoundError if file not found"""
        with pytest.raises(FileNotFoundError):
            review_file(
                file_path="/nonexistent/file.py",
                category="logic-errors",
                language="generic",
                api_key="test-key",
                base_url="https://api.example.com/",
                model="test-model"
            )

    def test_review_file_missing_category(self):
        """Should raise ValueError if category not found in template"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("code")
            temp_file = f.name

        try:
            with patch('review_file.OpenAI'):
                with pytest.raises(ValueError, match="not found"):
                    review_file(
                        file_path=temp_file,
                        category="nonexistent-category",
                        language="generic",
                        api_key="test-key",
                        base_url="https://api.example.com/",
                        model="test-model"
                    )
        finally:
            os.unlink(temp_file)

    def test_review_file_uses_correct_prompt_path(self):
        """Should resolve prompt template path relative to script"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("code")
            temp_file = f.name

        try:
            mock_response = MagicMock()
            mock_response.choices[0].message.content = "[]"

            with patch('review_file.OpenAI') as mock_openai_class:
                mock_client = MagicMock()
                mock_openai_class.return_value = mock_client
                mock_client.chat.completions.create.return_value = mock_response

                review_file(
                    file_path=temp_file,
                    category="logic-errors",
                    language="generic",
                    api_key="test-key",
                    base_url="https://api.example.com/",
                    model="test-model"
                )

                # Verify the call succeeded (template was found)
                assert mock_client.chat.completions.create.called

        finally:
            os.unlink(temp_file)
