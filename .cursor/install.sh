#!/usr/bin/env bash
# Idempotent bootstrap for Cursor cloud agents.
# Installs uv, syncs the lockfile, and installs Docker Engine plus Compose v2
# when they are missing. Docker is operator infrastructure for the trusted
# launcher. Do not expose the daemon to the target or the bridge.
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
if [[ -x "${HOME}/.local/bin/uv" ]]; then
  sudo ln -sfn "${HOME}/.local/bin/uv" /usr/local/bin/uv
  sudo ln -sfn "${HOME}/.local/bin/uvx" /usr/local/bin/uvx
fi

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi

uv sync --frozen --all-groups
