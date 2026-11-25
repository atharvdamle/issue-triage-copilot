import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from issue_triage_copilot.fetch_issues import (
    attach_comments,
    get_page,
    list_comments,
    month_windows,
    parse_issue,
)
from issue_triage_copilot.issue_stats import build_report
from issue_triage_copilot.models import FetchManifest

REPO_API = "https://api.github.com/repos/microsoft/vscode"


def github_item(
    number: int, labels: list[str], state: str = "open", **extra: object
) -> dict:
    return {
        "number": number,
        "title": f"Issue {number}",
        "body": "Steps to reproduce",
        "state": state,
        "state_reason": None,
        "labels": [{"name": name} for name in labels],
        "user": {"login": "someone"},
        "author_association": "NONE",
        "comments": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-05T00:00:00Z",
        "closed_at": None,
        "html_url": f"https://github.com/microsoft/vscode/issues/{number}",
        **extra,
    }


def github_comment(comment_id: int, issue_number: int, body: str = "Same here") -> dict:
    return {
        "id": comment_id,
        "issue_url": f"{REPO_API}/issues/{issue_number}",
        "user": {"login": "maintainer"},
        "author_association": "MEMBER",
        "body": body,
        "created_at": "2026-01-02T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "html_url": f"https://github.com/microsoft/vscode/issues/{issue_number}#c{comment_id}",
    }


def test_parse_issue_flattens_labels_and_author() -> None:
    issue = parse_issue(github_item(1, ["bug", "editor"], user=None))
    assert issue.labels == ["bug", "editor"]
    assert issue.author is None
    assert issue.comment_count == 1
    assert issue.comments == []


def test_attach_comments_skips_issues_not_kept() -> None:
    issues = {1: parse_issue(github_item(1, ["bug"]))}
    attach_comments(issues, [github_comment(10, 1), github_comment(11, 99)])
    assert [c.id for c in issues[1].comments] == [10]
    assert issues[1].comments[0].author == "maintainer"


def test_build_report_counts_state_duplicates_labels_and_comments() -> None:
    issues = {
        1: parse_issue(github_item(1, ["bug"])),
        2: parse_issue(
            github_item(
                2,
                ["*duplicate"],
                state="closed",
                state_reason="duplicate",
                closed_at="2026-01-03T00:00:00Z",
            )
        ),
    }
    attach_comments(issues, [github_comment(10, 1, body="Duplicate of #5")])
    manifest = FetchManifest(
        repo="microsoft/vscode",
        since=datetime(2026, 1, 1, tzinfo=UTC),
        fetched_at=datetime(2026, 2, 1, tzinfo=UTC),
        kept=2,
        skipped_pull_requests=5,
        skipped_invalid=3,
        skipped_spam=6,
        skipped_unlabeled=4,
        comments=1,
    )
    report = build_report(list(issues.values()), manifest)
    assert "Issues kept: **2**, with **1** comments" in report
    assert (
        "5 pull requests, 3 labeled `invalid`, 6 labeled `spam`, 4 unlabeled" in report
    )
    assert "| closed | 1 (50.0%) |" in report
    assert "or `*duplicate`): 1 (50.0%)" in report
    assert "Days to close: median 2.0" in report
    assert "| `bug` | 1 (50.0%) |" in report
    assert "Comment length (chars): median 15" in report
    assert "differ from GitHub's count: 1 (50.0%)" in report


def test_month_windows_split_at_month_starts() -> None:
    windows = month_windows(
        datetime(2025, 11, 15, tzinfo=UTC), datetime(2026, 1, 10, tzinfo=UTC)
    )
    assert [(start.date().isoformat(), end.year) for start, end in windows] == [
        ("2025-11-15", 2025),
        ("2025-12-01", 2026),
        ("2026-01-01", 9999),
    ]
    assert windows[0][1] == windows[1][0]


def test_list_comments_follows_pages_and_stops_at_window_end() -> None:
    pages = {
        "1": [
            github_comment(1, 7) | {"created_at": "2026-01-10T00:00:00Z"},
            github_comment(2, 7) | {"created_at": "2026-01-20T00:00:00Z"},
        ],
        "2": [
            github_comment(3, 7) | {"created_at": "2026-01-31T00:00:00Z"},
            github_comment(4, 7) | {"created_at": "2026-02-01T00:00:00Z"},
        ],
        "3": [github_comment(5, 7) | {"created_at": "2026-02-02T00:00:00Z"}],
    }
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        requested.append(page)
        headers = {
            "link": f'<{REPO_API}/issues/comments?page={int(page) + 1}>; rel="next"'
        }
        return httpx.Response(200, json=pages[page], headers=headers)

    async def run() -> list[dict]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await list_comments(
                client,
                REPO_API,
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 2, 1, tzinfo=UTC),
            )

    assert [c["id"] for c in asyncio.run(run())] == [1, 2, 3]
    assert requested == ["1", "2"]


def test_get_page_retries_server_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    statuses = iter([500, 502, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(next(statuses), json=[])

    async def no_sleep(seconds: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    async def run() -> int:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await get_page(client, f"{REPO_API}/issues", None)
            return response.status_code

    assert asyncio.run(run()) == 200
