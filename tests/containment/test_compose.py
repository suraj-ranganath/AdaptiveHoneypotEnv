"""Compose config must not hand any container the Docker socket."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_compose_config_has_no_docker_sock() -> None:
    completed = subprocess.run(
        ["docker", "compose", "--profile", "manual", "config", "--format", "json"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    rendered = json.loads(completed.stdout)
    blob = json.dumps(rendered)
    assert "docker.sock" not in blob
    assert "/var/run/docker.sock" not in blob

    services = rendered["services"]
    target = services["target"]
    bridge = services["bridge"]
    assert not target.get("ports")
    assert not bridge.get("ports")
    for service in (target, bridge):
        assert service["read_only"] is True
        assert "ALL" in service["cap_drop"]
        assert any("no-new-privileges" in item for item in service["security_opt"])
        assert not service.get("volumes")
        assert not service.get("privileged")
    assert rendered["networks"]["internal"]["internal"] is True
