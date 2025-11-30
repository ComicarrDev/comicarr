SHELL := /bin/bash

ENV_FILE := $(wildcard .env)

.PHONY: help dev dev-back dev-front run test test-back test-front build-front build clean sync install cov-back cov-front type-check type-check-back type-check-front

help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

define load_env
set -a; \
if [ -n "$(ENV_FILE)" ]; then source "$(ENV_FILE)"; fi; \
set +a;
endef

sync: ## Sync dependencies (backend and frontend, including test and dev)
	@echo "Syncing backend dependencies..."
	uv sync --extra test --extra dev
	@echo "Syncing frontend dependencies..."
	npm install

install: sync ## Install dependencies (alias for sync)
	@echo "Dependencies installed"

dev-back: ## Start backend in development mode with reload
	@echo "Starting backend in development mode..."
	@$(load_env) \
	COMICARR_ENV=development uv run python -m comicarr.app

dev-front: ## Start frontend development server
	@echo "Starting frontend development server..."
	@$(load_env) \
	cd frontend && npm install && npm run dev

test-back: ## Run backend test suite with coverage
	@echo "Running backend test suite with coverage..."
	uv run pytest backend/tests/ --cov=comicarr --cov-report=term-missing --cov-report=html

test-front: ## Run frontend test suite (non-watch mode)
	@echo "Running frontend test suite..."
	@$(load_env) \
	cd frontend && npm install && npm run test -- run

test: test-back test-front ## Run all tests (backend and frontend)

cov-back: test-back ## Run backend tests with coverage and open HTML report
	@echo "Coverage report generated in htmlcov/index.html"
	@echo "Open with: open htmlcov/index.html"

cov-front: ## Run frontend test suite with coverage
	@echo "Running frontend test suite with coverage..."
	@$(load_env) \
	cd frontend && npm install && npm run test:coverage

coverage: cov-back cov-front ## Run all tests with coverage (backend and frontend)

type-check-back: ## Run backend type checking with pyrefly
	@echo "Running backend type checking with pyrefly..."
	uv run pyrefly check backend/comicarr

type-check-front: ## Run frontend type checking with TypeScript
	@echo "Running frontend type checking..."
	cd frontend && npx tsc --noEmit;

type-check: type-check-back type-check-front ## Run type checking (backend and frontend)

build-front: ## Build frontend assets
	@echo "Building frontend assets..."
	@$(load_env) \
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

run: ## Start backend in production mode
	@echo "Starting backend in production mode..."
	@$(load_env) \
	COMICARR_ENV=production uv run python -m comicarr.app
