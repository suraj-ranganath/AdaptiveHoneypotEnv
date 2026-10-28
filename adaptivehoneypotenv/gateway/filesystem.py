"""Workspace reads. Paths stay inside the root. Symlinks are rejected, not followed.

Listing and search order is lexicographic by relative path, then line number.
Nothing in this module knows about decoys, so result order cannot favor traps.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from adaptivehoneypotenv.contracts.limits import (
    LISTING_MAX_ENTRIES,
    READ_MAX_RETURNED_BYTES,
    SEARCH_MAX_HITS,
    SEARCH_MAX_RETURNED_BYTES,
)
from adaptivehoneypotenv.contracts.tools import SYMLINK_POLICY, validate_workspace_path


class FilesystemRefusal(Exception):
    """Expected path failure. ``reason`` is a stable token, not a host path."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class FilesystemFailure(Exception):
    """Unexpected local IO. The message is a stable token."""

    def __init__(self, reason: str = "filesystem_error") -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class DirectoryEntry:
    name: str
    kind: str


@dataclass(frozen=True)
class DirectoryListing:
    entries: tuple[DirectoryEntry, ...]
    clipped: bool


@dataclass(frozen=True)
class SearchHit:
    path: str
    line: int
    text: str


@dataclass(frozen=True)
class SearchFindings:
    hits: tuple[SearchHit, ...]
    clipped: bool


@dataclass(frozen=True)
class FileSlice:
    lines: tuple[tuple[int, str], ...]
    clipped: bool


def resolve_workspace_path(root: Path, relative: str) -> Path:
    """Lexical path under ``root``. A symlink component raises ``FilesystemRefusal``."""

    if SYMLINK_POLICY != "reject":
        raise FilesystemFailure("symlink_policy")
    try:
        validate_workspace_path(relative)
    except ValueError as exc:
        reason = str(exc)
        if "traversal" in reason or "absolute" in reason:
            raise FilesystemRefusal("traversal") from exc
        raise FilesystemRefusal("invalid_path") from exc
    if root.is_symlink():
        raise FilesystemRefusal("symlink")
    if not root.is_dir():
        raise FilesystemFailure("filesystem_error")

    current = root
    if relative != ".":
        for part in relative.split("/"):
            current = current / part
            try:
                if current.is_symlink():
                    raise FilesystemRefusal("symlink")
            except OSError as exc:
                raise FilesystemFailure() from exc
            if not current.exists():
                raise FilesystemRefusal("not_found")
    if not _is_inside(root, current):
        raise FilesystemRefusal("traversal")
    return current


def list_directory(root: Path, relative: str) -> DirectoryListing:
    directory = resolve_workspace_path(root, relative)
    if directory.is_symlink():
        raise FilesystemRefusal("symlink")
    if not directory.is_dir():
        raise FilesystemRefusal("not_directory")
    try:
        names = sorted(os.listdir(directory))
    except OSError as exc:
        raise FilesystemFailure() from exc
    entries: list[DirectoryEntry] = []
    for name in names:
        child = directory / name
        entries.append(DirectoryEntry(name=name, kind=_kind(child)))
    clipped = len(entries) > LISTING_MAX_ENTRIES
    return DirectoryListing(entries=tuple(entries[:LISTING_MAX_ENTRIES]), clipped=clipped)


def search_files(root: Path, relative: str, query: str) -> SearchFindings:
    """Case-insensitive literal substring search. Order is path, then line."""

    if query == "":
        raise FilesystemRefusal("invalid_query")
    directory = resolve_workspace_path(root, relative)
    if not directory.is_dir() or directory.is_symlink():
        if directory.is_symlink():
            raise FilesystemRefusal("symlink")
        raise FilesystemRefusal("not_directory")
    needle = query.casefold()
    hits: list[SearchHit] = []
    used = 0
    clipped = False
    for file_path in _files_in_order(root, directory):
        relative_path = file_path.relative_to(root).as_posix()
        try:
            text = _read_text_no_follow(file_path)
        except FilesystemRefusal as exc:
            if exc.reason == "not_utf8":
                continue
            raise
        except FilesystemFailure:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if needle not in line.casefold():
                continue
            piece = line
            size = len(piece.encode("utf-8"))
            if len(hits) >= SEARCH_MAX_HITS or used + size > SEARCH_MAX_RETURNED_BYTES:
                if len(hits) < SEARCH_MAX_HITS and used < SEARCH_MAX_RETURNED_BYTES:
                    remaining = SEARCH_MAX_RETURNED_BYTES - used
                    prefix = _utf8_prefix(piece, remaining)
                    if prefix:
                        hits.append(SearchHit(path=relative_path, line=line_number, text=prefix))
                clipped = True
                ordered = tuple(sorted(hits, key=lambda hit: (hit.path, hit.line)))
                return SearchFindings(hits=ordered, clipped=True)
            hits.append(SearchHit(path=relative_path, line=line_number, text=piece))
            used += size
    ordered = tuple(sorted(hits, key=lambda hit: (hit.path, hit.line)))
    return SearchFindings(hits=ordered, clipped=clipped)


def read_file(root: Path, relative: str, start_line: int, max_lines: int) -> FileSlice:
    file_path = resolve_workspace_path(root, relative)
    if file_path.is_symlink():
        raise FilesystemRefusal("symlink")
    if file_path.is_dir():
        raise FilesystemRefusal("not_file")
    if not file_path.is_file():
        raise FilesystemRefusal("not_file")
    text = _read_text_no_follow(file_path)
    selected = text.splitlines()[start_line - 1 : start_line - 1 + max_lines]
    delivered: list[tuple[int, str]] = []
    used = 0
    clipped = False
    for offset, line in enumerate(selected):
        number = start_line + offset
        size = len(line.encode("utf-8"))
        if used + size > READ_MAX_RETURNED_BYTES:
            remaining = READ_MAX_RETURNED_BYTES - used
            prefix = _utf8_prefix(line, remaining)
            if prefix:
                delivered.append((number, prefix))
            clipped = True
            break
        delivered.append((number, line))
        used += size
    return FileSlice(lines=tuple(delivered), clipped=clipped)


def _files_in_order(root: Path, directory: Path) -> Iterator[Path]:
    found: list[Path] = []
    _collect(directory, found)
    found.sort(key=lambda path: path.relative_to(root).as_posix())
    yield from found


def _collect(directory: Path, found: list[Path]) -> None:
    try:
        names = sorted(os.listdir(directory))
    except OSError as exc:
        raise FilesystemFailure() from exc
    for name in names:
        child = directory / name
        try:
            if child.is_symlink():
                continue
            if child.is_dir():
                _collect(child, found)
            elif child.is_file():
                found.append(child)
        except OSError as exc:
            raise FilesystemFailure() from exc


def _read_text_no_follow(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if path.is_symlink():
            raise FilesystemRefusal("symlink") from exc
        raise FilesystemFailure() from exc
    try:
        chunks: list[bytes] = []
        while True:
            block = os.read(fd, 64 * 1024)
            if not block:
                break
            chunks.append(block)
            if sum(len(chunk) for chunk in chunks) > 8 * 1024 * 1024:
                raise FilesystemFailure("filesystem_error")
    except OSError as exc:
        raise FilesystemFailure() from exc
    finally:
        os.close(fd)
    try:
        return b"".join(chunks).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FilesystemRefusal("not_utf8") from exc


def _kind(path: Path) -> str:
    try:
        if path.is_symlink():
            return "symlink"
        if path.is_dir():
            return "dir"
        if path.is_file():
            return "file"
    except OSError:
        return "other"
    return "other"


def _is_inside(root: Path, candidate: Path) -> bool:
    root_abs = os.path.abspath(root)
    candidate_abs = os.path.abspath(candidate)
    try:
        common = os.path.commonpath([root_abs, candidate_abs])
    except ValueError:
        return False
    return common == root_abs


def _utf8_prefix(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    clipped = raw[:max_bytes]
    while clipped:
        try:
            return clipped.decode("utf-8")
        except UnicodeDecodeError:
            clipped = clipped[:-1]
    return ""
