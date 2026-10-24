# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project goal: the three things the copilot does for a new issue:

- Find duplicates and similar resolved issues.
- Predict the label or component.
- Write a short triage summary with citations.

## Stack: the tools we already picked, with fixed choices where you’d otherwise have to decide mid-build:

uv for packages;
plain SQL through psycopg instead of an ORM, so retrieval queries stay visible and easy to explain;
pytest and ruff for tests and lint.

## Conventions: how code should look, so it stays consistent across days

- Type hints everywhere, with Pydantic models for anything crossing a boundary;
- Prompts kept in their own files;
- Config read in one place;
- Each LLM call logged with its tokens and latency.

## Frozen eval paths: the files that define how you measure the system:

- The golden set (evals/golden/);
- The metric code (evals/metrics.py);
- The dev/test split (data/splits/).

## Project status

Only basic skeleton is currently present. Update this file with commands and architecture once they exist.

`.env` exports `LANGSMITH_ENDPOINT` and `LANGSMITH_API_KEY`, so the agent will be traced with LangSmith. Load it with `source .env`.

## Working principles

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