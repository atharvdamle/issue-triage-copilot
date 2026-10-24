# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

`issue-triage-copilot`: an issue-triage agent. The repo is at its first commit and holds only a README, with no source, build, lint, or test setup yet. Update this file with commands and architecture once they exist.

`.env` exports `LANGSMITH_ENDPOINT` and `LANGSMITH_API_KEY`, so the agent will be traced with LangSmith. Load it with `source .env`.

## Working principles

These come from [andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills). They favor caution over speed; trivial changes like typo fixes can skip the full process.

### 1. Think before coding
- State your assumptions explicitly. If you're unsure, ask instead of guessing.
- If a request has more than one reasonable interpretation, present them instead of silently picking one.
- If a simpler approach exists, say so and push back when it's warranted.
- If something is unclear, stop, name what's confusing, and ask.

### 2. Simplicity first
- Write the minimum code that solves the problem. Add nothing speculative.
- Don't add features beyond the request, abstractions for single-use code, or flexibility and configurability nobody asked for.
- Don't add error handling for impossible scenarios.
- If a senior engineer would call it overcomplicated, simplify it.

### 3. Surgical changes
- Touch only what the request requires. Don't "improve," reformat, or refactor adjacent code.
- Match the existing style, even if you'd do it differently.
- Mention unrelated dead code instead of deleting it.
- Remove only the imports, variables, and functions that your own change orphaned.
- Every changed line should trace directly to the request.

### 4. Goal-driven execution
- Turn tasks into verifiable goals. For example, "fix the bug" becomes "write a test that reproduces it, then make it pass."
- For multi-step work, state a brief plan with a verification check for each step.
- Loop until the success criteria are verifiably met.
