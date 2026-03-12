#!/usr/bin/env bash
# Ensures the plugin's Python venv exists and has dependencies installed.
# Called by the fleet-review skill before dispatching agents.
# Auto-approved by the PreToolUse hook.

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-.}"
VENV_PATH="${PLUGIN_ROOT}/.venv"
REQ_FILE="${PLUGIN_ROOT}/scripts/requirements.txt"

if [ ! -d "$VENV_PATH" ]; then
  echo "Creating Python virtual environment..."
  if ! python3 -m venv "$VENV_PATH" 2>&1; then
    echo "ERROR: Failed to create venv. Ensure python3 is installed."
    exit 1
  fi
  echo "Installing dependencies..."
  "$VENV_PATH/bin/pip" install -q -r "$REQ_FILE" 2>&1
  touch "$VENV_PATH/.deps_installed"
  echo "Ready."
elif [ "$REQ_FILE" -nt "$VENV_PATH/.deps_installed" ] 2>/dev/null; then
  echo "Updating dependencies..."
  "$VENV_PATH/bin/pip" install -q -r "$REQ_FILE" 2>&1
  touch "$VENV_PATH/.deps_installed"
  echo "Ready."
else
  echo "Ready."
fi
