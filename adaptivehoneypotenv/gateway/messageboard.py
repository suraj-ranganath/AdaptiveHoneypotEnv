"""Append-only team messageboard.

Posts are tagged with the round that wrote them. A read returns posts from
earlier rounds only, so same-round callers cannot observe each other's writes.
Solo reads return the caller's own posts. The board stores text for attackers
who explicitly read it. It has no defender view.
"""

from __future__ import annotations

from dataclasses import dataclass

from adaptivehoneypotenv.contracts.limits import (
    MESSAGEBOARD_READ_MAX_BYTES,
    MESSAGEBOARD_READ_MAX_POSTS,
)


class MessageboardError(Exception):
    """A backend failed; never turn this into a successful empty board read."""


@dataclass(frozen=True)
class PostedMessage:
    post_id: int
    author_actor_id: str
    round_index: int
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class BoardPage:
    posts: tuple[PostedMessage, ...]
    clipped: bool


class Messageboard:
    def __init__(self, *, solo: bool) -> None:
        self._solo = solo
        self._posts: list[PostedMessage] = []
        self._next_id = 1

    def __len__(self) -> int:
        return len(self._posts)

    @property
    def posts(self) -> tuple[PostedMessage, ...]:
        return tuple(self._posts)

    def prepare(self, *, author_actor_id: str, round_index: int, text: str) -> PostedMessage:
        """Reserve a post id. The post is invisible until ``commit``."""

        post = PostedMessage(
            post_id=self._next_id,
            author_actor_id=author_actor_id,
            round_index=round_index,
            text=text,
        )
        self._next_id += 1
        return post

    def commit(self, post: PostedMessage) -> None:
        self._posts.append(post)

    def acknowledge_read(self, *, reader_actor_id: str, page: BoardPage) -> None:
        """Record optional backend receipts after the delivered page is journaled."""

    def close(self) -> None:
        """Release backend resources. The default board owns none."""

    def read(
        self,
        *,
        reader_actor_id: str,
        round_index: int,
        after_post_id: int,
    ) -> BoardPage:
        visible = [
            post
            for post in self._posts
            if post.post_id > after_post_id and post.round_index < round_index
        ]
        if self._solo:
            visible = [post for post in visible if post.author_actor_id == reader_actor_id]
        chosen: list[PostedMessage] = []
        used = 0
        for post in visible:
            size = len(post.text.encode("utf-8"))
            over_count = len(chosen) >= MESSAGEBOARD_READ_MAX_POSTS
            over_bytes = used + size > MESSAGEBOARD_READ_MAX_BYTES
            if over_count or over_bytes:
                return BoardPage(posts=tuple(chosen), clipped=True)
            chosen.append(post)
            used += size
        return BoardPage(posts=tuple(chosen), clipped=False)
