"""Data models that cross file and API boundaries."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Comment(BaseModel):
    id: int
    author: str | None
    author_association: str
    body: str | None
    created_at: datetime
    updated_at: datetime
    html_url: str


class Issue(BaseModel):
    number: int
    title: str
    body: str | None
    state: Literal["open", "closed"]
    state_reason: str | None
    labels: list[str]
    author: str | None
    author_association: str
    comment_count: int
    comments: list[Comment] = []
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    html_url: str


class FetchManifest(BaseModel):
    repo: str
    since: datetime
    fetched_at: datetime
    kept: int
    skipped_pull_requests: int
    skipped_invalid: int
    skipped_spam: int
    skipped_unlabeled: int
    comments: int
