#!/usr/bin/env bash
# Operator environment only. Installs uv and the locked package.
# Docker-in-Docker belongs to the trusted launcher, not to the target or bridge.
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
if [[ -x "${HOME}/.local/bin/uv" ]]; then
  mkdir -p "${HOME}/.local/bin"
  export PATH="${HOME}/.local/bin:${PATH}"
fi
uv sync --frozen --all-groups
