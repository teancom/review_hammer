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
