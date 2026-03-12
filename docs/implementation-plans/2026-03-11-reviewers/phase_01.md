# Review Hammer Implementation Plan — Phase 1: Plugin Scaffolding

**Goal:** Working Claude Code plugin structure installable via `claude plugin install`

**Architecture:** Standard Claude Code plugin with manifest, session-start hook for env var validation, and README for setup instructions. Plugin lives at repo root with `.claude-plugin/plugin.json` as the manifest entry point.

**Tech Stack:** Shell (bash), JSON

**Scope:** 6 phases from original design (this is phase 1 of 6)

**Codebase verified:** 2026-03-11 — fresh repo, no files exist yet.

---

## Acceptance Criteria Coverage

This phase is infrastructure — verified operationally, not by tests.

### reviewers.AC7: Installable plugin
- **reviewers.AC7.1 Success:** `claude plugin install teancom/review_hammer` works
- **reviewers.AC7.2 Success:** Session-start hook warns when REVIEWERS_API_KEY is not set

---

<!-- START_TASK_1 -->
### Task 1: Create plugin manifest

**Files:**
- Create: `.claude-plugin/plugin.json`

**Step 1: Create the manifest file**

```json
{
  "name": "review-hammer",
  "version": "0.1.0",
  "description": "High-precision automated code review using specialized LLM agents with an Opus judge pass",
  "author": {
    "name": "teancom",
    "url": "https://github.com/teancom"
  },
  "repository": "https://github.com/teancom/review_hammer",
  "license": "MIT",
  "keywords": ["code-review", "linting", "multi-agent"]
}
```

**Step 2: Verify the file is valid JSON**

Run: `python3 -m json.tool .claude-plugin/plugin.json`
Expected: Pretty-printed JSON output without errors

**Commit:** `chore: add plugin manifest for review-hammer`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create session-start hook for env var validation

**Files:**
- Create: `hooks/hooks.json`
- Create: `hooks/session-start.sh`

**Step 1: Create hooks configuration**

`hooks/hooks.json`:
```json
{
  "description": "Review Hammer hooks",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh",
            "statusMessage": "Checking Review Hammer configuration"
          }
        ]
      }
    ]
  }
}
```

**Step 2: Create session-start shell script**

`hooks/session-start.sh`:
```bash
#!/usr/bin/env bash

missing=()

if [ -z "$REVIEWERS_API_KEY" ]; then
  missing+=("REVIEWERS_API_KEY")
fi

if [ ${#missing[@]} -eq 0 ]; then
  echo "Review Hammer: All required environment variables are set."
  echo "  API Base URL: ${REVIEWERS_BASE_URL:-https://api.z.ai/api/paas/v4/}"
  echo "  Model: ${REVIEWERS_MODEL:-glm-5}"
  echo "  Max Concurrent: ${REVIEWERS_MAX_CONCURRENT:-3}"
  exit 0
else
  echo "Review Hammer: Missing required environment variables: ${missing[*]}"
  echo "  Set REVIEWERS_API_KEY to use the /fleet-review skill."
  echo "  Optional: REVIEWERS_BASE_URL (default: https://api.z.ai/api/paas/v4/)"
  echo "  Optional: REVIEWERS_MODEL (default: glm-5)"
  echo "  Optional: REVIEWERS_MAX_CONCURRENT (default: 3)"
  exit 0
fi
```

Note: Exit code 0 in both branches — missing env vars is a warning, not a blocking error. Exit code 2 would block the session from starting.

**Step 3: Make the script executable**

Run: `chmod +x hooks/session-start.sh`

**Step 4: Verify the hook config is valid JSON**

Run: `python3 -m json.tool hooks/hooks.json`
Expected: Pretty-printed JSON output without errors

**Step 5: Verify the script runs without errors**

Run: `bash hooks/session-start.sh`
Expected: Output about missing REVIEWERS_API_KEY (since it's not set in this shell)

**Commit:** `feat: add session-start hook for env var validation`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create README with setup instructions

**Files:**
- Create: `README.md`

**Step 1: Create the README**

```markdown
# Review Hammer

High-precision automated code review using specialized LLM agents with an Opus judge pass.

## How It Works

Review Hammer dispatches category-specialized code review agents to any OpenAI-compatible LLM endpoint, then uses Claude Opus as a judge layer to deduplicate, verify, and rank findings. Each specialist has a narrow mandate (e.g., only race conditions, or only resource leaks) with language-specific false-positive suppression.

## Installation

```bash
claude plugin install teancom/review_hammer
```

## Configuration

Set these environment variables before using:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REVIEWERS_API_KEY` | Yes | — | API key for the backend LLM |
| `REVIEWERS_BASE_URL` | No | `https://api.z.ai/api/paas/v4/` | Base URL for the OpenAI-compatible API |
| `REVIEWERS_MODEL` | No | `glm-5` | Model ID to use for specialist reviews |
| `REVIEWERS_MAX_CONCURRENT` | No | `3` | Maximum parallel API calls |

## Usage

```bash
# Review a single file
/fleet-review ./src/auth.py

# Review a directory
/fleet-review ./src/

# Review entire repo
/fleet-review .
```

## Supported Languages

Python, C, C++, Java, C#, JavaScript, TypeScript, Kotlin, Rust, Go, Swift, plus a generic fallback for other languages.

## License

MIT
```

**Step 2: Verify the README renders correctly**

Visually inspect `README.md` for correct markdown formatting.

**Commit:** `docs: add README with setup and usage instructions`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create placeholder directories for later phases

**Files:**
- Create: `scripts/.gitkeep`
- Create: `prompts/.gitkeep`
- Create: `agents/.gitkeep`
- Create: `skills/fleet-review/.gitkeep`

**Step 1: Create the directory structure**

Run:
```bash
mkdir -p scripts prompts agents skills/fleet-review
touch scripts/.gitkeep prompts/.gitkeep agents/.gitkeep skills/fleet-review/.gitkeep
```

**Step 2: Verify structure**

Run: `find . -name .gitkeep -type f | sort`
Expected:
```
./agents/.gitkeep
./prompts/.gitkeep
./scripts/.gitkeep
./skills/fleet-review/.gitkeep
```

**Commit:** `chore: create placeholder directories for plugin components`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Verify plugin structure end-to-end

**Step 1: Verify complete directory structure**

Run: `find .claude-plugin hooks scripts prompts agents skills -type f | sort`
Expected:
```
.claude-plugin/plugin.json
agents/.gitkeep
hooks/hooks.json
hooks/session-start.sh
prompts/.gitkeep
scripts/.gitkeep
skills/fleet-review/.gitkeep
```

**Step 2: Verify plugin.json is valid and has required fields**

Run: `python3 -c "import json; d=json.load(open('.claude-plugin/plugin.json')); assert 'name' in d; print('OK:', d['name'])"`
Expected: `OK: review-hammer`

**Step 3: Verify hooks.json references existing script**

Run: `python3 -c "import json; d=json.load(open('hooks/hooks.json')); cmd=d['hooks']['SessionStart'][0]['hooks'][0]['command']; print('Hook command:', cmd)"`
Expected: `Hook command: ${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh`

**Step 4: Verify session-start.sh is executable**

Run: `test -x hooks/session-start.sh && echo "executable" || echo "not executable"`
Expected: `executable`

No commit for this task — it's a verification step only.
<!-- END_TASK_5 -->
