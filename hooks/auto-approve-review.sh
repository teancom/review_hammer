#!/bin/bash
# PreToolUse hook: auto-approve Bash calls used by the fleet-review pipeline.
# This eliminates permission prompts during fleet-review runs.

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

approve() {
  cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "$1"
  }
}
EOF
  exit 0
}

# Auto-approve caffeinate (prevents idle sleep during long reviews)
if echo "$COMMAND" | grep -qE '^caffeinate '; then
  approve "caffeinate auto-approved by Review Hammer plugin"
fi

# Auto-approve printenv for reading configuration env vars
if echo "$COMMAND" | grep -qE '^printenv REVIEWERS_'; then
  approve "printenv auto-approved by Review Hammer plugin"
fi

# Auto-approve review_file.py invocations (via uv run or direct)
if echo "$COMMAND" | grep -q "review_file.py"; then
  approve "review_file.py auto-approved by Review Hammer plugin"
fi

# Auto-approve plugin cache directory lookups (for resolving plugin root)
if echo "$COMMAND" | grep -q "review-hammer-marketplace"; then
  approve "plugin path lookup auto-approved by Review Hammer plugin"
fi

# Auto-approve read-only git commands used by smart-input mode detection.
# These may be prefixed with "cd /path &&" when reviewing external repos,
# so we match on the git subcommand rather than anchoring to line start.
if echo "$COMMAND" | grep -qE '(^|&& )git (diff|rev-parse|merge-base|status --porcelain|log --oneline)( |$)'; then
  approve "read-only git command auto-approved by Review Hammer plugin"
fi

exit 0
