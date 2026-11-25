"""Write a Markdown stats report for data/raw/issues.jsonl to reports/raw_issue_stats.md.

Usage: uv run python -m issue_triage_copilot.issue_stats
"""

import statistics
from collections import Counter
from collections.abc import Iterable

from issue_triage_copilot.config import settings
from issue_triage_copilot.fetch_issues import ISSUES_FILE, MANIFEST_FILE
from issue_triage_copilot.models import FetchManifest, Issue

REPORT_FILE = "raw_issue_stats.md"
DUPLICATE_LABEL = "*duplicate"
TOP_LABELS = 30


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%"


def table(header: tuple[str, str], rows: Iterable[tuple[object, object]]) -> list[str]:
    lines = [f"| {header[0]} | {header[1]} |", "|---|---:|"]
    lines += [f"| {key} | {value} |" for key, value in rows]
    return lines


def build_report(issues: list[Issue], manifest: FetchManifest) -> str:
    total = len(issues)
    closed = [i for i in issues if i.state == "closed"]
    days_to_close = sorted(
        (i.closed_at - i.created_at).total_seconds() / 86400
        for i in closed
        if i.closed_at
    )
    label_counts = Counter(label for i in issues for label in i.labels)
    duplicates = sum(
        1
        for i in issues
        if i.state_reason == "duplicate" or DUPLICATE_LABEL in i.labels
    )
    body_lengths = [len(i.body or "") for i in issues]
    comments = [len(i.comments) for i in issues]
    comment_lengths = [len(c.body or "") for i in issues for c in i.comments]
    mismatched = sum(1 for i in issues if len(i.comments) != i.comment_count)
    created_by_month = Counter(i.created_at.strftime("%Y-%m") for i in issues)
    close_reasons = Counter(i.state_reason or "none" for i in closed)

    lines = [
        f"# Issue stats: {manifest.repo}",
        "",
        f"- Window: created since {manifest.since:%Y-%m-%d}, fetched {manifest.fetched_at:%Y-%m-%d %H:%M} UTC",
        f"- Issues kept: **{total}**, with **{manifest.comments}** comments",
        (
            f"- Skipped: {manifest.skipped_pull_requests} pull requests, "
            f"{manifest.skipped_invalid} labeled `invalid`, "
            f"{manifest.skipped_spam} labeled `spam`, "
            f"{manifest.skipped_unlabeled} unlabeled"
        ),
        "",
        "## State",
        "",
        *table(
            ("State", "Issues"),
            [
                ("open", f"{total - len(closed)} ({pct(total - len(closed), total)})"),
                ("closed", f"{len(closed)} ({pct(len(closed), total)})"),
            ],
        ),
        "",
        "### Close reasons",
        "",
        *table(("Reason", "Issues"), close_reasons.most_common()),
        "",
        (
            f"- Duplicates (`state_reason=duplicate` or `{DUPLICATE_LABEL}`): "
            f"{duplicates} ({pct(duplicates, total)})"
        ),
    ]
    if days_to_close:
        lines += [
            (
                f"- Days to close: median {statistics.median(days_to_close):.1f}, "
                f"p90 {days_to_close[int(0.9 * (len(days_to_close) - 1))]:.1f}"
            ),
        ]
    lines += [
        "",
        "## Labels",
        "",
        f"- Distinct labels: {len(label_counts)}",
        f"- Mean labels per issue: {sum(label_counts.values()) / total:.2f}",
        "",
        f"### Top {TOP_LABELS} labels",
        "",
        *table(
            ("Label", "Issues"),
            (
                (f"`{label}`", f"{n} ({pct(n, total)})")
                for label, n in label_counts.most_common(TOP_LABELS)
            ),
        ),
        "",
        "## Content",
        "",
        f"- Empty body: {body_lengths.count(0)} ({pct(body_lengths.count(0), total)})",
        (
            f"- Body length (chars): median {statistics.median(body_lengths):.0f}, "
            f"max {max(body_lengths)}"
        ),
        (
            f"- Comments per issue: median {statistics.median(comments):.0f}, "
            f"mean {statistics.mean(comments):.1f}, max {max(comments)}"
        ),
        (f"- Comment length (chars): median {statistics.median(comment_lengths):.0f}"),
        (
            f"- Issues whose fetched comments differ from GitHub's count: "
            f"{mismatched} ({pct(mismatched, total)})"
        ),
        "",
        "## Issues created per month",
        "",
        *table(("Month", "Issues"), sorted(created_by_month.items())),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    raw = settings.raw_data_dir
    with (raw / ISSUES_FILE).open() as f:
        issues = [Issue.model_validate_json(line) for line in f]
    manifest = FetchManifest.model_validate_json((raw / MANIFEST_FILE).read_text())

    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = settings.reports_dir / REPORT_FILE
    report_path.write_text(build_report(issues, manifest))
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
