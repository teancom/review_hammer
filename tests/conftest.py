"""
Shared pytest configuration and fixtures.

Provides:
- Path setup for importing modules from scripts directory
- Temporary file fixtures for tests
"""

import sys
from pathlib import Path

import pytest


# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


@pytest.fixture
def temp_python_file(tmp_path):
    """Fixture that creates a temporary Python file.

    Args:
        tmp_path: pytest's built-in tmp_path fixture

    Returns:
        Path object to a temporary .py file
    """
    temp_file = tmp_path / "temp_script.py"
    temp_file.write_text("# Temporary file for testing\n")
    return str(temp_file)


@pytest.fixture
def temp_file_with_content(tmp_path):
    """Fixture that creates a temporary file with custom content.

    Args:
        tmp_path: pytest's built-in tmp_path fixture

    Returns:
        A function that creates a temp file with the given content
    """
    def _create(content: str, suffix: str = ".py") -> str:
        temp_file = tmp_path / f"temp_file{suffix}"
        temp_file.write_text(content)
        return str(temp_file)

    return _create
