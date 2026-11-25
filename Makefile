.PHONY: up down test lint fetch stats

up:      ## Postgres 18 + pgvector
	docker compose up -d

down:
	docker compose down

test:
	uv run pytest

lint:
	uv run ruff check && uv run ruff format --check

fetch:   ## microsoft/vscode issues into data/raw/ (SINCE=YYYY-MM-DD)
	uv run python -m issue_triage_copilot.fetch_issues $(if $(SINCE),--since $(SINCE))

stats:   ## reports/raw_issue_stats.md
	uv run python -m issue_triage_copilot.issue_stats
