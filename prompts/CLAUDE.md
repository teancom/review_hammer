# Prompts - Language-Specific Review Templates

Last verified: 2026-03-11

## Purpose
Provides structured prompt templates that turn a generic LLM into a specialist
code reviewer for a specific language and bug category.

## Contracts
- **Exposes**: Markdown files named `{language}.md` matching EXTENSION_MAP values in review_file.py
- **Guarantees**:
  - Each template has a preamble (output format instructions) and `## category-name` sections
  - Preamble defines the JSON finding schema (lines, severity, category, description, impact, confidence)
  - Production categories: race-conditions, null-safety (or variant), resource-leaks, logic-errors, error-handling, state-management
  - Test categories: testing-nothing, missing-assertions, over-mocking, brittle-tests
- **Expects**: Called via `extract_category_prompt()` in review_file.py which splits on `## ` headings

## Dependencies
- **Used by**: `scripts/review_file.py` (loaded at review time)
- **Boundary**: Templates are read-only from the script's perspective

## Key Decisions
- Language-specific null-safety variants: c/cpp/rust use "memory-safety", go uses "nil-safety", js/ts use "type-safety"
- Generic template as fallback: Covers unknown file extensions with language-agnostic patterns

## Invariants
- Every language template must have all 11 category headings (6 production + 5 test)
- Heading format must be exactly `## category-name` (used for extraction)
- Template filenames must match language keys in EXTENSION_MAP + "generic"

## Gotchas
- Adding a new language requires: new prompt file, EXTENSION_MAP entry in review_file.py, and SKILL.md extension list update
