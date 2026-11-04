.DEFAULT_GOAL := help
.PHONY: help install lint format test check up down logs collect clean

# Every component's extras, so tests can import all of them.
UV_RUN := uv run --all-extras

# Containers write to ./data as the host user, so the files stay editable/removable.
export HOST_UID := $(shell id -u)
export HOST_GID := $(shell id -g)

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Create the virtualenv from the lockfile
	uv sync --locked --all-extras

lint: ## Run the linter and check formatting
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .

format: ## Auto-fix lint issues and format the code
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .

test: ## Run the test suite
	$(UV_RUN) pytest

check: lint test ## Run everything CI runs

up: ## Build and start the stack in the background
	mkdir -p data/raw
	docker compose up --detach --build

down: ## Stop the stack
	docker compose down

logs: ## Follow the stack logs
	docker compose logs --follow

collect: ## Run the collector on the host, in the foreground
	$(UV_RUN) python -m collector

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache build dist
	find . -type d -name __pycache__ -not -path './.venv/*' -prune -exec rm -rf {} +
