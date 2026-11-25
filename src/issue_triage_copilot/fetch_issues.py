"""Fetch labeled GitHub issues with comments (no PRs, `invalid`, `spam`) into data/raw/issues.jsonl.

Usage: uv run python -m issue_triage_copilot.fetch_issues [--since YYYY-MM-DD]
"""

import argparse
import asyncio
import logging
import time
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime
from typing import Any

import httpx

from issue_triage_copilot.config import settings
from issue_triage_copilot.models import Comment, FetchManifest, Issue

log = logging.getLogger(__name__)

API_URL = "https://api.github.com"
INVALID_LABEL = "invalid"
SPAM_LABEL = "spam"
ISSUES_FILE = "issues.jsonl"
MANIFEST_FILE = "issues_manifest.json"
MAX_CONCURRENT_REQUESTS = 8  # Well under GitHub's secondary rate limit.
MAX_RETRIES = 5  # For timeouts and 5xx errors, with exponential backoff.

_request_slots = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


def parse_issue(item: dict[str, Any]) -> Issue:
    return Issue(
        number=item["number"],
        title=item["title"],
        body=item["body"],
        state=item["state"],
        state_reason=item.get("state_reason"),
        labels=[label["name"] for label in item["labels"]],
        author=item["user"]["login"] if item["user"] else None,
        author_association=item["author_association"],
        comment_count=item["comments"],
        created_at=item["created_at"],
        updated_at=item["updated_at"],
        closed_at=item["closed_at"],
        html_url=item["html_url"],
    )


def parse_comment(item: dict[str, Any]) -> Comment:
    return Comment(
        id=item["id"],
        author=item["user"]["login"] if item["user"] else None,
        author_association=item["author_association"],
        body=item["body"],
        created_at=item["created_at"],
        updated_at=item["updated_at"],
        html_url=item["html_url"],
    )


def attach_comments(issues: dict[int, Issue], items: Iterable[dict[str, Any]]) -> None:
    """Attach repo-wide comments to their issues, ignoring PRs and dropped issues."""
    for item in items:
        number = int(item["issue_url"].rsplit("/", 1)[1])
        if number in issues:
            issues[number].comments.append(parse_comment(item))


def month_windows(since: datetime, until: datetime) -> list[tuple[datetime, datetime]]:
    """Split [since, until) at month starts; the last window is open-ended."""
    starts = [since]
    while True:
        year, month = divmod(starts[-1].year * 12 + starts[-1].month, 12)
        start = datetime(year, month + 1, 1, tzinfo=UTC)
        if start >= until:
            break
        starts.append(start)
    ends = starts[1:] + [datetime.max.replace(tzinfo=UTC)]
    return list(zip(starts, ends))


async def get_page(
    client: httpx.AsyncClient, url: str, params: dict[str, str] | None
) -> httpx.Response:
    """GET a page, retrying timeouts and 5xx errors and waiting out rate limits."""
    failures = 0
    while True:
        try:
            async with _request_slots:
                response = await client.get(url, params=params)
            error = f"HTTP {response.status_code}" if response.is_server_error else None
        except httpx.TimeoutException:
            error = "timeout"
        if error:
            failures += 1
            if failures > MAX_RETRIES:
                raise httpx.HTTPError(f"{error} after {MAX_RETRIES} retries: {url}")
            wait = 2**failures
            log.warning("%s on %s; retry %d in %ds", error, url, failures, wait)
            await asyncio.sleep(wait)
            continue
        if response.status_code in (403, 429):
            if response.headers.get("x-ratelimit-remaining") == "0":
                wait = int(response.headers["x-ratelimit-reset"]) - int(time.time()) + 5
                log.warning("Rate limit exhausted; sleeping %ds", wait)
                await asyncio.sleep(max(wait, 0))
                continue
            if "retry-after" in response.headers:
                wait = int(response.headers["retry-after"])
                log.warning("Secondary rate limit; sleeping %ds", wait)
                await asyncio.sleep(wait)
                continue
        response.raise_for_status()
        return response


async def paginate(
    client: httpx.AsyncClient, url: str, params: dict[str, str], label: str
) -> AsyncIterator[dict[str, Any]]:
    next_url: str | None = url
    next_params: dict[str, str] | None = {**params, "per_page": "100"}
    page = 0
    while next_url:
        response = await get_page(client, next_url, next_params)
        page += 1
        log.info(
            "%s: page %d (rate limit remaining: %s)",
            label,
            page,
            response.headers.get("x-ratelimit-remaining"),
        )
        for item in response.json():
            yield item
        next_url = response.links.get("next", {}).get("url")
        next_params = None  # The next link already carries the query string.


async def list_issues(
    client: httpx.AsyncClient, repo_url: str, state: str, since: datetime
) -> list[dict[str, Any]]:
    """Issues and PRs in `state` created on or after `since`, newest first."""
    params = {"state": state, "sort": "created", "direction": "desc"}
    items = []
    async for item in paginate(client, f"{repo_url}/issues", params, f"{state} issues"):
        if datetime.fromisoformat(item["created_at"]) < since:
            break
        items.append(item)
    return items


async def list_comments(
    client: httpx.AsyncClient, repo_url: str, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    """Comments created before `end`, from a listing that starts at `start`.

    GitHub caps page-number pagination, so each window must stay short.
    """
    params = {"since": start.isoformat(), "sort": "created", "direction": "asc"}
    label = f"comments from {start:%Y-%m-%d}"
    items = []
    async for item in paginate(client, f"{repo_url}/issues/comments", params, label):
        if datetime.fromisoformat(item["created_at"]) >= end:
            break
        items.append(item)
    return items


async def list_issue_comments(
    client: httpx.AsyncClient, repo_url: str, number: int
) -> list[Comment]:
    url = f"{repo_url}/issues/{number}/comments"
    return [parse_comment(c) async for c in paginate(client, url, {}, f"#{number}")]


async def fetch(since: datetime) -> FetchManifest:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    else:
        log.warning("GITHUB_TOKEN not set; unauthenticated limit is 60 requests/hour")

    repo_url = f"{API_URL}/repos/{settings.github_repo}"
    windows = month_windows(since, datetime.now(UTC))
    async with httpx.AsyncClient(headers=headers, timeout=120) as client:
        # Every comment on an issue created after `since` was also updated after it.
        results = await asyncio.gather(
            list_issues(client, repo_url, "open", since),
            list_issues(client, repo_url, "closed", since),
            *(list_comments(client, repo_url, start, end) for start, end in windows),
        )
        issue_items = results[0] + results[1]
        # Windows overlap for comments edited after creation; dedupe by id.
        comment_items = {c["id"]: c for chunk in results[2:] for c in chunk}.values()

        issues: dict[int, Issue] = {}
        skipped_prs = skipped_invalid = skipped_spam = skipped_unlabeled = 0
        for item in issue_items:
            if "pull_request" in item:
                skipped_prs += 1
                continue
            issue = parse_issue(item)
            if INVALID_LABEL in issue.labels:
                skipped_invalid += 1
            elif SPAM_LABEL in issue.labels:
                skipped_spam += 1
            elif not issue.labels:
                skipped_unlabeled += 1
            else:
                issues[issue.number] = issue
        log.info(
            "Issues: kept=%d prs=%d invalid=%d spam=%d unlabeled=%d",
            len(issues),
            skipped_prs,
            skipped_invalid,
            skipped_spam,
            skipped_unlabeled,
        )

        attach_comments(issues, comment_items)
        log.info(
            "Comments in window: %d", sum(len(i.comments) for i in issues.values())
        )

        incomplete = [i for i in issues.values() if len(i.comments) < i.comment_count]
        log.info(
            "Backfilling comments for %d issues with fewer than GitHub's count",
            len(incomplete),
        )
        backfilled = await asyncio.gather(
            *(list_issue_comments(client, repo_url, i.number) for i in incomplete)
        )
        for issue, comments in zip(incomplete, backfilled):
            issue.comments = comments

    settings.raw_data_dir.mkdir(parents=True, exist_ok=True)
    out_path = settings.raw_data_dir / ISSUES_FILE
    partial_path = out_path.with_suffix(".jsonl.partial")
    with partial_path.open("w") as out:
        for issue in sorted(issues.values(), key=lambda i: i.number, reverse=True):
            issue.comments.sort(key=lambda c: c.created_at)
            out.write(issue.model_dump_json() + "\n")
    partial_path.rename(out_path)

    manifest = FetchManifest(
        repo=settings.github_repo,
        since=since,
        fetched_at=datetime.now(UTC),
        kept=len(issues),
        skipped_pull_requests=skipped_prs,
        skipped_invalid=skipped_invalid,
        skipped_spam=skipped_spam,
        skipped_unlabeled=skipped_unlabeled,
        comments=sum(len(i.comments) for i in issues.values()),
    )
    (settings.raw_data_dir / MANIFEST_FILE).write_text(
        manifest.model_dump_json(indent=2)
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=UTC),
        default=datetime(datetime.now(UTC).year, 1, 1, tzinfo=UTC),
        help="Only issues created on or after this date (default: Jan 1 this year).",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    manifest = asyncio.run(fetch(args.since))
    log.info("Done: %s", manifest.model_dump_json())


if __name__ == "__main__":
    main()
