UV ?= uv

.PHONY: setup test lint typecheck

setup:
	$(UV) sync --frozen --all-groups

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy
