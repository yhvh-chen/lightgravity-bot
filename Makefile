# LightGravity Bot — unified check entry points (LG-002 skeleton).
#
# Requires: uv (0.12.x), GNU make, Node.js 22 LTS + npm 10.
# See README.md for version and platform requirements.

UV ?= uv
NPM ?= npm
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
LG_DATA_DIR ?= bot-data
LG_WORKSPACE_ROOT ?= $(LG_DATA_DIR)/workspaces
LG_SECRET_STORE ?= secrets

.PHONY: help lock sync type test check run frontend-install frontend-dev frontend-type frontend-test frontend-build frontend-check check-all clean lg-start lg-stop lg-status lg-init serve

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
	@echo "  make serve            build the frontend then start the one-process local service"
	@echo "  make lg-start         Start the one-process local service on loopback (foreground)"
	@echo "  make lg-start-daemon  Start the service detached (logs under <data-dir>/logs)"
	@echo "  make lg-status        Show process + HTTP health"
	@echo "  make lg-stop          Stop the started service and clean its pid record"
	@echo "  make lg-init          Write explicit minimal resources (requires LG_CONNECTION_*)"
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

# One-process local distribution (LG-020): API + static frontend on loopback.
# Override LG_DATA_DIR / LG_WORKSPACE_ROOT / LG_SECRET_STORE for isolation.
serve: frontend-build
	$(UV) run lightgravity start --data-dir $(LG_DATA_DIR) --workspace-root $(LG_WORKSPACE_ROOT) --secret-store $(LG_SECRET_STORE) --host $(BACKEND_HOST) --port $(BACKEND_PORT)

lg-start:
	$(UV) run lightgravity start --data-dir $(LG_DATA_DIR) --workspace-root $(LG_WORKSPACE_ROOT) --secret-store $(LG_SECRET_STORE) --host $(BACKEND_HOST) --port $(BACKEND_PORT)

lg-start-daemon:
	$(UV) run lightgravity start --daemon --data-dir $(LG_DATA_DIR) --workspace-root $(LG_WORKSPACE_ROOT) --secret-store $(LG_SECRET_STORE) --host $(BACKEND_HOST) --port $(BACKEND_PORT)

lg-status:
	$(UV) run lightgravity status --data-dir $(LG_DATA_DIR) --secret-store $(LG_SECRET_STORE)

lg-stop:
	$(UV) run lightgravity stop --data-dir $(LG_DATA_DIR) --secret-store $(LG_SECRET_STORE)

# Explicit, non-interactive minimal init. Set LG_CONNECTION_ID/CREDENTIAL_REF
# (and optionally LG_MODEL/LG_BASE_URL/LG_AGENT_ID/LG_SET_WORKER_DEFAULT) first.
lg-init:
	$(UV) run lightgravity init --data-dir $(LG_DATA_DIR) --workspace-root $(LG_WORKSPACE_ROOT) --secret-store $(LG_SECRET_STORE) --connection-id $(LG_CONNECTION_ID) --credential-ref $(LG_CREDENTIAL_REF) $(if $(LG_MODEL),--model $(LG_MODEL),) $(if $(LG_BASE_URL),--base-url $(LG_BASE_URL),) $(if $(LG_AGENT_ID),--agent-id $(LG_AGENT_ID),) $(if $(LG_SET_WORKER_DEFAULT),--set-worker-default,)

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
