# Review Hammer

High-precision automated code review using specialized LLM agents with an Opus judge pass.

## How It Works

Review Hammer dispatches category-specialized code review agents to any OpenAI-compatible LLM endpoint, then uses Claude Opus as a judge layer to deduplicate, verify, and rank findings. Each specialist has a narrow mandate (e.g., only race conditions, or only resource leaks) with language-specific false-positive suppression.

## Installation

First, add the marketplace, then install the plugin:

```
/plugin marketplace add teancom/review_hammer
/plugin install review-hammer@review-hammer-marketplace
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
