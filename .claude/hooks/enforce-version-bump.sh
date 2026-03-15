#!/bin/bash
# PreToolUse hook: blocks git commit when plugin-facing files are staged
# but version hasn't been bumped in plugin.json + marketplace.json.
#
# "Plugin-facing" = files that ship with the plugin and affect its behavior:
#   scripts/, prompts/, agents/, skills/, hooks/
#
# Tests and docs are NOT plugin-facing (users don't install them).

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only care about git commit commands
if ! echo "$COMMAND" | grep -qE '^\s*git commit'; then
  exit 0
fi

# What's staged right now?
STAGED=$(git diff --cached --name-only 2>/dev/null || true)

if [ -z "$STAGED" ]; then
  exit 0  # Nothing staged, let git complain about it
fi

# Are any plugin-facing files staged?
PLUGIN_FACING=$(echo "$STAGED" | grep -E '^(scripts/|prompts/|agents/|skills/|hooks/)' || true)

if [ -z "$PLUGIN_FACING" ]; then
  exit 0  # Only tests/docs/config changed, no version bump needed
fi

# Plugin-facing files ARE staged. Check version files.
PLUGIN_JSON_STAGED=$(echo "$STAGED" | grep -c '^\.claude-plugin/plugin\.json$' || true)
MARKETPLACE_STAGED=$(echo "$STAGED" | grep -c '^\.claude-plugin/marketplace\.json$' || true)

if [ "$PLUGIN_JSON_STAGED" -eq 0 ] || [ "$MARKETPLACE_STAGED" -eq 0 ]; then
  echo "BLOCKED: Plugin-facing files are staged but version not bumped." >&2
  echo "" >&2
  echo "Staged plugin-facing files:" >&2
  echo "$PLUGIN_FACING" | sed 's/^/  /' >&2
  echo "" >&2
  echo "You must bump the version in BOTH:" >&2
  echo "  .claude-plugin/plugin.json" >&2
  echo "  .claude-plugin/marketplace.json" >&2
  echo "" >&2
  echo "Versions must match. See CLAUDE.md 'Releasing Changes'." >&2
  exit 2
fi

# Both version files are staged. Verify they match.
PLUGIN_VERSION=$(jq -r '.version' .claude-plugin/plugin.json 2>/dev/null)
MARKET_VERSION=$(jq -r '.plugins[0].version' .claude-plugin/marketplace.json 2>/dev/null)

if [ "$PLUGIN_VERSION" != "$MARKET_VERSION" ]; then
  echo "BLOCKED: Version mismatch between plugin.json ($PLUGIN_VERSION) and marketplace.json ($MARKET_VERSION)." >&2
  echo "They must be identical. See CLAUDE.md 'Releasing Changes'." >&2
  exit 2
fi

# All good — plugin-facing files staged with matching version bump
exit 0
