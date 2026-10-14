# LightGravity Bot — unified check entry points (LG-002 skeleton).
#
# Requires: uv (0.12.x), GNU make, Node.js 22 LTS + npm 10.
# See README.md for version and platform requirements.

UV ?= uv
NPM ?= npm
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000

.PHONY: help lock sync type test check run frontend-install frontend-dev frontend-type frontend-test frontend-build frontend-check check-all clean

help:
	@echo "LightGravity Bot make targets:"
	@echo "  make lock             Lock Python dependencies (uv.lock)"
	@echo "  make sync             Create .venv and sync locked dependencies"
	@echo "  make type             Run mypy on backend/lightgravity"
	@echo "  make test             Run backend pytest suite"
	@echo "  make check            type + test (backend)"
	@echo "  make run              Start backend on loopback"
	@echo "  make frontend-install Install frontend dependencies from package-lock.json"
	@echo "  make frontend-dev     Start Vite dev server"
	@echo "  make frontend-type    Type-check the frontend"
	@echo "  make frontend-test    Run frontend unit tests (vitest run)"
	@echo "  make frontend-build   Build the frontend for production"
	@echo "  make frontend-check   frontend-type + frontend-test"
	@echo "  make check-all        backend check + frontend check"
	@echo "  make clean            Remove local caches and build output"

lock:
	$(UV) lock

sync:
	$(UV) sync

type:
	$(UV) run mypy

test:
	$(UV) run pytest

check: type test

run:
	$(UV) run uvicorn --factory lightgravity.api.app:create_app --host $(BACKEND_HOST) --port $(BACKEND_PORT)

frontend-install:
	$(NPM) --prefix frontend ci

frontend-dev:
	$(NPM) --prefix frontend run dev

frontend-type:
	$(NPM) --prefix frontend run typecheck

frontend-test:
	$(NPM) --prefix frontend run test:run

frontend-build:
	$(NPM) --prefix frontend run build

frontend-check: frontend-type frontend-test

check-all: check frontend-check

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf frontend/dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
