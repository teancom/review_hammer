#!/usr/bin/env bash
# Session start hook: validate environment and check for uv

# Check for uv (required for running review_file.py)
if ! command -v uv &>/dev/null; then
  echo "Review Hammer: WARNING - 'uv' not found. Install it: https://docs.astral.sh/uv/"
  echo "  The /fleet-review skill requires 'uv' to run review scripts."
  exit 0
fi

# Validate environment
missing=()

if [ -z "$REVIEWERS_API_KEY" ]; then
  missing+=("REVIEWERS_API_KEY")
fi

if [ ${#missing[@]} -eq 0 ]; then
  echo "Review Hammer: Ready."
  echo "  API Base URL: ${REVIEWERS_BASE_URL:-https://api.z.ai/api/paas/v4/}"
  echo "  Model: ${REVIEWERS_MODEL:-glm-5}"
  exit 0
else
  echo "Review Hammer: Missing required environment variables: ${missing[*]}"
  echo "  Set REVIEWERS_API_KEY to use the /fleet-review skill."
  exit 0
fi
