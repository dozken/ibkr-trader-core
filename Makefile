.PHONY: venv test lint

# Host-side dev environment. The interpreter is pinned to 3.11 via .python-version
# (honored by uv, pyenv, mise and CI). `make venv` bootstraps a uv venv with the
# dev extra (pytest/pytest-asyncio/ruff); `make test` mirrors the CI invocation.
venv:
	uv venv
	uv pip install -e '.[dev]'

test:
	PYTHONPATH=. .venv/bin/pytest ibkr_core/ -q --tb=short

lint:
	.venv/bin/ruff check ibkr_core/
