.DEFAULT_GOAL := help
PY ?= python

.PHONY: help install lint format typecheck test cov run migrate revision docker-build compose-up compose-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the package with dev extras
	$(PY) -m pip install -e ".[dev]"

lint: ## Run ruff
	ruff check app tests

format: ## Format with black + ruff --fix
	black app tests
	ruff check --fix app tests

typecheck: ## Run mypy
	mypy app

test: ## Run the test suite
	pytest -q

cov: ## Run tests with coverage gate (>=90%)
	pytest --cov=app --cov-report=term-missing --cov-fail-under=90

run: ## Run the dev server with reload
	$(PY) -m app serve --reload

migrate: ## Apply database migrations
	alembic upgrade head

revision: ## Autogenerate a migration: make revision m="message"
	alembic revision --autogenerate -m "$(m)"

docker-build: ## Build the Docker image
	docker build -t upgi:latest .

compose-up: ## Start the full stack
	docker compose up --build -d

compose-down: ## Stop the stack
	docker compose down
