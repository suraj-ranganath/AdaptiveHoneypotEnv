#!/usr/bin/env bash
# Start the Docker daemon for the trusted launcher when it is installed.
# This does not create episode containers and does not publish target ports.
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is not installed" >&2
  exit 0
fi

if docker info >/dev/null 2>&1; then
  docker compose version
  exit 0
fi

if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl start docker || true
fi
if ! docker info >/dev/null 2>&1; then
  sudo service docker start || true
fi

if docker info >/dev/null 2>&1; then
  docker compose version
else
  echo "docker daemon is not running" >&2
  exit 1
fi
