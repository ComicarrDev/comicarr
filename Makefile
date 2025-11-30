SHELL := /bin/bash

ENV_FILE := $(firstword $(wildcard .env) $(wildcard .env.example))

.PHONY: help dev dev-back dev-front run test test-back test-front test-front-coverage build-front build clean sync install coverage type-check

help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

define load_env
set -a; \
if [ -n "$(ENV_FILE)" ]; then source "$(ENV_FILE)"; fi; \
set +a;
endef

define load_nvm
export NVM_DIR="$$HOME/.nvm"; \
[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && \. "/opt/homebrew/opt/nvm/nvm.sh"; \
nvm use stable;
endef

sync: ## Sync dependencies with uv (including test and dev dependencies)
	@echo "Syncing dependencies..."
	uv sync --extra test --extra dev

install: sync ## Install dependencies (alias for sync)
	@echo "Dependencies installed"

dev-back: ## Start backend in development mode with reload
	@echo "Starting backend in development mode..."
	@$(load_env) \
	COMICARR_ENV=development uv run python -m comicarr.app

dev-front: ## Start frontend development server
	@echo "Starting frontend development server..."
	@$(load_env) \
	$(load_nvm) \
	cd frontend && npm install && npm run dev

test-back: ## Run backend test suite with coverage
	@echo "Running backend test suite with coverage..."
	uv run pytest backend/tests/ --cov=comicarr --cov-report=term-missing --cov-report=html

test-front: ## Run frontend test suite (non-watch mode)
	@echo "Running frontend test suite..."
	@$(load_env) \
	$(load_nvm) \
	cd frontend && npm install && npm run test -- run

test-front-coverage: ## Run frontend test suite with coverage
	@echo "Running frontend test suite with coverage..."
	@$(load_env) \
	$(load_nvm) \
	cd frontend && npm install && npm run test:coverage

test: test-back test-front ## Run all tests (backend and frontend)

type-check: ## Run type checking with pyrefly
	@echo "Running type checking with pyrefly..."
	uv run pyrefly check backend/comicarr

build-front: ## Build frontend assets
	@echo "Building frontend assets..."
	@$(load_env) \
	$(load_nvm) \
	cd frontend && npm install && npm run build

build: build-front ## Build all assets

clean: ## Clean build artifacts and caches
	@echo "Cleaning build artifacts..."
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -r {} + 2>/dev/null || true
	find . -type f -name ".coverage*" -delete 2>/dev/null || true
	rm -rf htmlcov/ 2>/dev/null || true
	rm -rf backend/comicarr/static/frontend/* 2>/dev/null || true

coverage: test-back ## Run tests with coverage and open HTML report
	@echo "Coverage report generated in htmlcov/index.html"
	@echo "Open with: open htmlcov/index.html"

run: ## Start backend in production mode
	@echo "Starting backend in production mode..."
	@$(load_env) \
	COMICARR_ENV=production uv run python -m comicarr.app
