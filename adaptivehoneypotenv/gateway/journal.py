"""In-memory event log with an optional fsynced JSONL sink.

Payload bytes stay off the envelope. A failed sink write leaves the in-memory
log unchanged so the caller can refuse to deliver the result.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from adaptivehoneypotenv.contracts.events import (
    Event,
    PayloadRef,
    validate_journal,
)


class JournalWriteError(OSError):
    """The durable sink did not accept the record."""


class EpisodeJournal:
    def __init__(self, episode_id: str, directory: Path | None = None) -> None:
        self.episode_id = episode_id
        self._events: list[Event] = []
        self._payloads: dict[str, bytes] = {}
        self._directory = directory
        self._payload_dir: Path | None = None
        self._jsonl: Path | None = None
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            payload_dir = directory / "payloads"
            payload_dir.mkdir(exist_ok=True)
            self._payload_dir = payload_dir
            self._jsonl = directory / "events.jsonl"

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def next_sequence(self) -> int:
        return len(self._events)

    def payload(self, ref_id: str) -> bytes:
        return self._payloads[ref_id]

    def iter_payloads(self) -> tuple[bytes, ...]:
        return tuple(self._payloads.values())

    def store(self, data: bytes) -> PayloadRef:
        if len(data) > 1_048_576:
            raise ValueError("payload exceeds the envelope limit")
        digest = hashlib.sha256(data).hexdigest()
        ref_id = "payload_" + digest[:32]
        if ref_id not in self._payloads:
            if self._payload_dir is not None:
                self._write_bytes(self._payload_dir / ref_id, data)
            self._payloads[ref_id] = data
        return PayloadRef(ref_id=ref_id, sha256=digest, byte_length=len(data))

    def append(self, event: Event) -> None:
        if event.episode_id != self.episode_id:
            raise ValueError("event episode_id does not match the journal")
        if event.sequence != len(self._events):
            raise ValueError("event sequence is not the next journal index")
        validate_journal((*self._events, event))
        if self._jsonl is not None:
            line = event.model_dump_json() + "\n"
            self._append_line(self._jsonl, line.encode("utf-8"))
        self._events.append(event)

    def _write_bytes(self, path: Path, data: bytes) -> None:
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            fd = os.open(path, flags, 0o600)
            try:
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise JournalWriteError(str(exc)) from exc

    def _append_line(self, path: Path, data: bytes) -> None:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError as exc:
            raise JournalWriteError(str(exc)) from exc
