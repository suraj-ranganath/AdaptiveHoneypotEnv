"""Controller-only SQLite maintenance helper.

Invoked by the trusted launcher through Docker's exec API with one fixed
argument: backup, restore, or stat. Paths are constants. There is no HTTP
server and no shell.

backup and restore use SQLite's online backup API. They do not restart the
application process, so the in-memory process salt stays in place. The caller
must already have stopped sending requests.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys

LIVE_DB = "/run/state/db.sqlite3"
SNAPSHOT_DB = "/run/state/episode-backup.sqlite3"
PID_PATH = "/run/state/app.pid"
OPERATIONS = {"backup", "restore", "stat"}


def _copy(source_path: str, destination_path: str) -> None:
    source = sqlite3.connect(source_path, timeout=5)
    destination = sqlite3.connect(destination_path, timeout=5)
    try:
        source.execute("PRAGMA busy_timeout=5000")
        destination.execute("PRAGMA busy_timeout=5000")
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def _pid() -> int:
    with open(PID_PATH, encoding="ascii") as handle:
        pid = int(handle.read().strip())
    os.kill(pid, 0)
    return pid


def backup() -> None:
    if not os.path.exists(LIVE_DB):
        raise SystemExit("live database is missing")
    _copy(LIVE_DB, SNAPSHOT_DB)


def restore() -> None:
    if not os.path.exists(SNAPSHOT_DB):
        raise SystemExit("snapshot is missing")
    if not os.path.exists(LIVE_DB):
        raise SystemExit("live database is missing")
    _copy(SNAPSHOT_DB, LIVE_DB)


def stat() -> None:
    pid = _pid()
    connection = sqlite3.connect(LIVE_DB, timeout=5)
    try:
        row = connection.execute("SELECT COUNT(*) FROM users").fetchone()
    finally:
        connection.close()
    if row is None:
        raise SystemExit("user count missing")
    print(json.dumps({"pid": pid, "user_count": int(row[0])}), flush=True)


def main(argv: list[str]) -> None:
    if len(argv) != 2 or argv[1] not in OPERATIONS:
        raise SystemExit("usage: maintenance.py backup|restore|stat")
    operation = argv[1]
    if operation == "backup":
        backup()
    elif operation == "restore":
        restore()
    else:
        stat()


if __name__ == "__main__":
    main(sys.argv)
