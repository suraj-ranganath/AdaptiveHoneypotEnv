"""The vendored SecretStorage bytes stay on the reviewed Honeyval revision."""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP = (
    REPO_ROOT
    / "third_party"
    / "honeyval"
    / "data"
    / "baxbench-webapps"
    / "SecretStorage"
    / "sec"
    / "app.py"
)
PINNED_APP_SHA256 = "7e51814c21fa091435ef8a552ca4c2063bdfd59d250407abf5e4b74556573d7a"


def test_vendored_app_matches_pinned_hash() -> None:
    digest = hashlib.sha256(APP.read_bytes()).hexdigest()
    assert digest == PINNED_APP_SHA256
