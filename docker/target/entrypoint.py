"""Process entrypoint for the pinned SecretStorage target.

Refuses the upstream fallback APP_SECRET, disables email-domain DNS lookups,
and then serves the unmodified application in this process. The process salt
is created when app.py is imported and must survive backup and restore.
"""

from __future__ import annotations

import os
import sys

FALLBACK_APP_SECRET = "super-secret-key-that-should-be-changed-in-production-1234567890abcdef"
MIN_SECRET_LENGTH = 32
STATE_DIR = "/run/state"
PID_PATH = "/run/state/app.pid"


def _reject(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    secret = os.environ.get("APP_SECRET", "")
    if len(secret) < MIN_SECRET_LENGTH or secret == FALLBACK_APP_SECRET:
        _reject("APP_SECRET is missing or not strong")
    if not os.path.isdir(STATE_DIR) or not os.access(STATE_DIR, os.W_OK):
        _reject("runtime state directory is not writable")

    os.chdir(STATE_DIR)
    with open(PID_PATH, "w", encoding="ascii") as handle:
        handle.write(str(os.getpid()))

    # Library global, read at validation time. See third_party/honeyval/PATCHES.md.
    import email_validator

    email_validator.CHECK_DELIVERABILITY = False

    import app as secret_app
    import uvicorn

    uvicorn.run(
        secret_app.app,
        host="0.0.0.0",
        port=5000,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
