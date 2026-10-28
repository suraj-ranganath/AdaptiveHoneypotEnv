"""Phase 0 skeleton: layout, compose, and the devcontainer contract."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

MODULE_FILES = (
    "adaptivehoneypotenv/__init__.py",
    "adaptivehoneypotenv/env.py",
    "adaptivehoneypotenv/scenario.py",
    "adaptivehoneypotenv/tools.py",
    "adaptivehoneypotenv/templates.py",
    "adaptivehoneypotenv/scoring.py",
    "adaptivehoneypotenv/events.py",
    "adaptivehoneypotenv/policies.py",
    "adaptivehoneypotenv/deployment.py",
    "adaptivehoneypotenv/server.py",
    "adaptivehoneypotenv/adapters/agentenv.py",
    "adaptivehoneypotenv/adapters/gymnasium.py",
    "adaptivehoneypotenv/contracts/actions.py",
    "adaptivehoneypotenv/contracts/observations.py",
    "adaptivehoneypotenv/contracts/events.py",
    "adaptivehoneypotenv/contracts/transition.py",
    "adaptivehoneypotenv/contracts/tools.py",
    "adaptivehoneypotenv/contracts/manifest.py",
    "adaptivehoneypotenv/scenarios/secret_store_ops_v1/scenario.yaml",
    "adaptivehoneypotenv/scenarios/secret_store_ops_v1/fixtures.py",
    "adaptivehoneypotenv/scenarios/secret_store_ops_v1/verifier.py",
    "web/README.md",
    "third_party/README.md",
    "docker-compose.yml",
    "Makefile",
    "pyproject.toml",
    ".devcontainer/devcontainer.json",
    ".github/workflows/ci.yml",
    ".cursor/environment.json",
)


def test_phase0_layout_files_exist() -> None:
    missing = [path for path in MODULE_FILES if not (ROOT / path).is_file()]
    assert missing == []


def test_compose_does_not_mount_docker_socket_or_publish_ports() -> None:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert "docker.sock" not in text
    services = data["services"]
    assert "target" in services
    assert "bridge" in services
    for name, service in services.items():
        assert "ports" not in service, name
        volumes = service.get("volumes") or []
        assert all("sock" not in str(volume) for volume in volumes)
    devcontainer = (ROOT / ".devcontainer/devcontainer.json").read_text(encoding="utf-8")
    assert "docker.sock" not in devcontainer
    assert "docker-in-docker" in devcontainer
