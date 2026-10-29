UV ?= uv

.PHONY: setup test lint typecheck smoke-live

setup:
	$(UV) sync --frozen --all-groups

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy

# One real OpenRouter call. CI must not set this flag. The module checks it again.
smoke-live:
	@if [ "$${ADAPTIVEHONEYPOT_SMOKE_LIVE}" != "1" ]; then \
		echo "refusing live call: set ADAPTIVEHONEYPOT_SMOKE_LIVE=1" >&2; \
		exit 2; \
	fi
	$(UV) run python -m adaptivehoneypotenv.models.smoke
