FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md ./
COPY backend ./backend
RUN uv sync --frozen --no-dev
COPY --from=web /app/frontend/dist ./frontend/dist
# Public demo: state lives on the container's ephemeral disk (/data).
ENV LIGHTGRAVITY_TEAM_MODE=true \
    LIGHTGRAVITY_TEAM_COOKIE_SECURE=true \
    LIGHTGRAVITY_HOST=0.0.0.0 \
    PATH="/app/.venv/bin:$PATH"
RUN useradd -m app && mkdir /data && chown app /data
USER app
CMD exec lightgravity start --host 0.0.0.0 --port ${PORT:-8080} \
    --data-dir /data --workspace-root /data/workspaces --secret-store /data/secrets \
    --frontend-dist /app/frontend/dist
