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

# Auto-approve review_file.py invocations (the core review pipeline)
if echo "$COMMAND" | grep -q "review_file.py"; then
  approve "review_file.py auto-approved by Review Hammer plugin"
fi

# Auto-approve any command referencing the plugin cache path
if echo "$COMMAND" | grep -q "review-hammer"; then
  approve "review-hammer path auto-approved by Review Hammer plugin"
fi

# Auto-approve git diff commands (used for large-repo scoping)
if echo "$COMMAND" | grep -qE '^git diff( |$)'; then
  approve "git diff auto-approved by Review Hammer plugin"
fi

exit 0
