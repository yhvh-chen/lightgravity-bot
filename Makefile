# Local source installation and runtime commands.
UV ?= uv
NPM ?= npm
BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000
LG_DATA_DIR ?= bot-data
LG_WORKSPACE_ROOT ?= $(LG_DATA_DIR)/workspaces
LG_SECRET_STORE ?= secrets

.PHONY: sync run frontend-install frontend-dev frontend-type frontend-build serve lg-start lg-stop lg-status
sync:
	$(UV) sync --locked --no-dev
run:
	$(UV) run --no-dev uvicorn --factory lightgravity.api.app:create_app --host $(BACKEND_HOST) --port $(BACKEND_PORT)
frontend-install:
	$(NPM) --prefix frontend ci
frontend-dev:
	$(NPM) --prefix frontend run dev
frontend-type:
	$(NPM) --prefix frontend run typecheck
frontend-build:
	$(NPM) --prefix frontend run build
serve: frontend-build lg-start
lg-start:
	$(UV) run --no-dev lightgravity start --data-dir $(LG_DATA_DIR) --workspace-root $(LG_WORKSPACE_ROOT) --secret-store $(LG_SECRET_STORE) --host $(BACKEND_HOST) --port $(BACKEND_PORT)
lg-stop:
	$(UV) run --no-dev lightgravity stop --data-dir $(LG_DATA_DIR) --secret-store $(LG_SECRET_STORE)
lg-status:
	$(UV) run --no-dev lightgravity status --data-dir $(LG_DATA_DIR) --secret-store $(LG_SECRET_STORE)
