.DEFAULT_GOAL := help
.PHONY: help install lint format test check clean

help: ## List available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Create the virtualenv from the lockfile
	uv sync --locked

lint: ## Run the linter and check formatting
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-fix lint issues and format the code
	uv run ruff check --fix .
	uv run ruff format .

test: ## Run the test suite
	uv run pytest

check: lint test ## Run everything CI runs

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache build dist
	find . -type d -name __pycache__ -not -path './.venv/*' -prune -exec rm -rf {} +
