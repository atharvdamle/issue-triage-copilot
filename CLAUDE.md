# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`issue-triage-copilot` reads a new microsoft/vscode bug report and tells a maintainer three things:

1. **Duplicates:** which existing issues it duplicates, plus similar issues that were already resolved.
2. **Label:** which area label it belongs to.
3. **Summary:** a short triage summary of what's going on, with links to the evidence it cites.

The answer comes back as a structured `TriageReport`. The point of the project is **measured**
quality: every retrieval, prompt or agent change must earn a row in `results.md`.

## Never

- Never create or edit anything in `evals/golden/` or the dev/test splits in `evals/splits/`.
  If one looks wrong, say so.
- Never run the test split unless the owner asked for it.
- Never change an evaluation, metric or golden item to make a score go up.
- Never handle credentials: no keys in code, tests, logs, commits or chat. Read them through
  `config.py`. If one is missing, tell the owner which variable to set in `.env`.
- Never deploy, create cloud resources or spend money beyond eval runs without the owner's
  explicit go-ahead in the current conversation.

## Commands

- `make up` / `make down` (or `docker compose up -d`): Postgres 18 with pgvector on `localhost:5432` (user/password/db `triage`, overridable via `POSTGRES_*` env vars). `db/init/*.sql` runs on first start only; `docker compose down -v` wipes the data. Connect via `settings.database_url` (`DATABASE_URL`).
- `make fetch SINCE=YYYY-MM-DD` (`uv run python -m issue_triage_copilot.fetch_issues [--since YYYY-MM-DD]`): fetch microsoft/vscode issues created since the date (default: Jan 1 this year) into `data/raw/issues.jsonl` (one issue per line, full comment thread embedded) plus `issues_manifest.json`. Skips PRs, unlabeled issues, and issues labeled `invalid` or `spam`.
- `make stats` (`uv run python -m issue_triage_copilot.issue_stats`): write `reports/raw_issue_stats.md` from the raw data.
- `make test` (`uv run pytest`), `make lint` (`uv run ruff check`, `uv run ruff format --check`).

`.env` holds `LANGSMITH_ENDPOINT`, `LANGSMITH_API_KEY`, `GITHUB_TOKEN`, `ANTHROPIC_API_KEY` and `LANGSMITH_PROJECT`. All config is read in `src/issue_triage_copilot/config.py`.

## Stack

These choices are fixed. Don't swap them out mid-build. Ask before adding any other dependency.

- **uv** for packages and environments; Python 3.14 (`.python-version`).
- **Package layout:** everything under `src/issue_triage_copilot/` (subpackages `ingest`, `retrieval`, `api`, `agent`, `evals`, `mcp_server`, `db`). Tests in `tests/`.
- **Postgres 18 + pgvector** and Postgres full-text search, via Docker Compose.
- **psycopg with plain SQL** instead of an ORM, so retrieval queries stay visible and easy to explain.
- **pytest** for tests and **ruff** for lint and formatting.
- **FastAPI + Pydantic v2**; pydantic-settings for config.
- **LangChain** for the baseline, **LangGraph** for the agent, **LangSmith** for tracing.
- **MCP Python SDK** for the tracker tool server; `langchain-mcp-adapters` to load it.
- **Local sentence-transformers** models for embeddings and reranking.
- **LLM:** Anthropic `anthropic` SDK / `langchain-anthropic`. Default `claude-opus-5-5` for generation and the agent, `claude-sonnet-5-5` for the judge.

## LLM call rules

- No `temperature`/`top_p`/`top_k`; no assistant prefill; no forced `tool_choice` (`any`/`tool`)
  on Opus 5.5 / Sonnet 5.5. Use structured outputs (`output_config.format`) or `tool_choice: auto`
  with strict tools.
- Set `effort` explicitly (default `medium`). Check `stop_reason` before reading content; handle `refusal`.
- Cache stable system prompts. Log every LLM call with model, token counts, latency and estimated cost.
- Retrieval-only experiments make no LLM calls. Iterate with `--subset`; full runs use the Batch API.

## Conventions

- Follow standard Python conventions (PEP 8, enforced by ruff).
- Add sufficient logging so that code can be traced easily.
- Use type hints everywhere. Use Pydantic models for any data that crosses a boundary (API, DB, LLM input/output, files).
- Keep each prompt in its own file under `src/issue_triage_copilot/prompts/`, not inline in code.
- Read config in one place only.
- Every function in `retrieval/`, `evals/` and `agent/` has a test.
- Experiments are YAML configs in `experiments/`; one config per `results.md` row.
- Keep docstrings and comments short and precise. Code that needs many comments to be understood should be rewritten instead.

## Working principles

Adapted from [andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills). They favor caution over speed; trivial changes like typo fixes can skip the full process.

### 1. Think before coding
- State your assumptions explicitly. If you're unsure, ask instead of guessing.
- If a request has more than one reasonable interpretation, present them instead of silently picking one.
- If a simpler approach exists, say so and push back when it's warranted.
- If something is unclear, stop, name what's confusing, and ask.

### 2. Simplicity first
- Write the minimum code that solves the problem. Add nothing speculative.
- Don't add features beyond the request, abstractions for single-use code, or configurability nobody asked for.
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
