.PHONY: setup up down migrate seed test lint e2e dagster-dev

setup:
	uv sync --extra dev

up:
	docker compose up -d

down:
	docker compose down

migrate:
	uv run alembic -c alembic.ini upgrade head

seed:
	uv run python dataset/scripts/load_all.py

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy backend pipelines

e2e:
	uv run pytest tests/integration

dagster-dev:
	uv run dagster dev -w pipelines/workspace.yaml
