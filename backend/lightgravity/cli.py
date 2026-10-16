"""``lightgravity`` command line: single-command start / stop / status / init.

LG-020 local distribution entry point.  It is intentionally small and honest:

* ``start`` builds the real runtime (see :mod:`lightgravity.api.bootstrap`),
  writes a non-secret pid record, serves the API + static frontend on loopback,
  and reports which dependencies were actually wired;
* ``stop`` stops *that* process (SIGTERM, then SIGKILL) and removes the record,
  cleaning stale records instead of pretending;
* ``status`` reports the live pid + an optional HTTP health probe; ``--deep``
  also builds the runtime read-only and prints the execution readiness report;
* ``init`` is the only command that writes configuration, and only when the
  operator supplies an explicit connection (idempotent, revision-preserving).

No command prints the runtime token, a credential value or the contents of
``.env``.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .api.bootstrap import (
    ALLOWED_HOSTS_ENV,
    FRONTEND_DIST_ENV,
    RuntimeState,
    StartupOptions,
    build_runtime,
    default_frontend_dist,
)
from .config import Settings
from .runtime.minimal import AgentInit, ConnectionInit, initialize_minimal
from .runtime.pidfile import (
    ProcessRecord,
    process_alive,
    read_record,
    remove_record,
    stop_process_file,
    write_record,
)
from .runtime.token import resolve_runtime_token
from .settings import ConnectionService, FileSecretStore, PREFERRED_MODEL, DEFAULT_BASE_URL
from .store import FileStore
from .team import TeamAccounts, TeamAccountsError

DEFAULT_LOG_NAME = "lightgravity.log"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _settings_from_args(args: argparse.Namespace) -> Settings:
    env = Settings.from_env()
    data_dir = Path(args.data_dir) if args.data_dir else env.data_dir
    if args.workspace_root:
        workspace_root = Path(args.workspace_root)
    elif args.data_dir:
        workspace_root = data_dir / "workspaces"
    else:
        workspace_root = env.workspace_root
    secret_store = Path(args.secret_store) if args.secret_store else env.secret_store
    host = args.host or env.host
    port = args.port if args.port is not None else env.port
    return Settings(
        data_dir=data_dir,
        workspace_root=workspace_root,
        secret_store=secret_store,
        host=host,
        port=port,
        # LG-050: carry the resolved team-mode settings so the CLI never drops
        # them (the explicit path/port overrides must not reset team mode).
        team_mode=env.team_mode,
        team_accounts=env.team_accounts,
        team_session_ttl_seconds=env.team_session_ttl_seconds,
        team_cookie_secure=env.team_cookie_secure,
        team_bot_mention=env.team_bot_mention,
    )


def _add_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data-dir", help="runtime data root (default ./bot-data)")
    parser.add_argument("--workspace-root", help="authorized task workspace root")
    parser.add_argument("--secret-store", help="controlled secret store directory")
    parser.add_argument("--host", help="bind host (default 127.0.0.1)")
    parser.add_argument("--port", type=int, help="bind port (default 8000)")


def _add_start_options(parser: argparse.ArgumentParser) -> None:
    _add_paths(parser)
    parser.add_argument("--frontend-dist", help="frontend build directory")
    parser.add_argument(
        "--no-frontend", action="store_true", help="serve API only (no static frontend)"
    )
    parser.add_argument(
        "--allow-host",
        action="append",
        default=[],
        help="extra allowed Host value (repeatable)",
    )
    parser.add_argument(
        "--no-executor",
        action="store_true",
        help="do not wire the real executor (execution stays honestly unavailable)",
    )
    parser.add_argument(
        "--daemon", action="store_true", help="detach and log under <data-dir>/logs"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lightgravity", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    _add_start_options(sub.add_parser("start", help="start the local service"))

    stop = sub.add_parser("stop", help="stop the started local service")
    _add_paths(stop)
    stop.add_argument("--timeout", type=float, default=10.0)

    status = sub.add_parser("status", help="report process + health")
    _add_paths(status)
    status.add_argument(
        "--deep", action="store_true", help="also build the runtime and report execution readiness"
    )

    init = sub.add_parser("init", help="write explicit minimal resources (idempotent)")
    _add_paths(init)
    init.add_argument("--connection-id", required=True)
    init.add_argument("--connection-title")
    init.add_argument("--backend", default="openai-compat")
    init.add_argument("--model", default=PREFERRED_MODEL)
    init.add_argument("--base-url", default=DEFAULT_BASE_URL)
    init.add_argument("--credential-ref", required=True)
    init.add_argument("--agent-id")
    init.add_argument("--agent-title")
    init.add_argument("--agent-tools", default="view-file,edit-file,run-command")
    init.add_argument("--agent-skills", default="implementation,verification")
    init.add_argument("--set-worker-default", action="store_true")

    user = sub.add_parser("user", help="manage team accounts (LG-050)")
    user_sub = user.add_subparsers(dest="user_command")
    user_add = user_sub.add_parser("add", help="add a team account (password via getpass)")
    _add_paths(user_add)
    user_add.add_argument("--username", required=True)
    user_add.add_argument("--role", choices=["admin", "member"], default="member")
    user_list = user_sub.add_parser("list", help="list team accounts (no secrets)")
    _add_paths(user_list)
    return parser


def _run_foreground(state: RuntimeState, settings: Settings, token_source: str) -> int:
    import uvicorn

    record = ProcessRecord(
        pid=os.getpid(),
        host=settings.host,
        port=settings.port,
        started_at=_now(),
        token_source=token_source,
        frontend_served=state.frontend_served,
        data_dir=str(settings.data_dir),
    )
    write_record(settings.data_dir, record)
    try:
        uvicorn.run(state.app, host=settings.host, port=settings.port)
    finally:
        remove_record(settings.data_dir)
    return 0


def _daemonize(settings: Settings) -> bool:
    """Fork into the background; return ``True`` in the child, ``False`` in parent."""

    if not hasattr(os, "fork"):  # pragma: no cover - non-POSIX
        print("daemon mode is not supported on this platform", file=sys.stderr)
        return False
    pid = os.fork()
    if pid > 0:
        return False
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(log_dir / DEFAULT_LOG_NAME, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    return True


def cmd_start(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    token = resolve_runtime_token(os.environ)
    frontend_dist = Path(args.frontend_dist) if args.frontend_dist else None
    env_dist = os.environ.get(FRONTEND_DIST_ENV)
    if frontend_dist is None and env_dist:
        frontend_dist = Path(env_dist)
    if frontend_dist is None:
        frontend_dist = default_frontend_dist()

    allowed_hosts = tuple(args.allow_host or ()) + tuple(
        item.strip()
        for item in os.environ.get(ALLOWED_HOSTS_ENV, "").split(",")
        if item.strip()
    )

    started = _daemonize(settings) if args.daemon else True
    if args.daemon and not started:
        # Parent: wait for the detached child to publish its pid record.
        record = _wait_for_record(settings.data_dir, timeout=8.0)
        if record is None:
            print("daemon did not publish a pid record; check the log", file=sys.stderr)
            return 1
        print(json.dumps({"started": True, "pid": record.pid, "url": _url(settings)}))
        return 0

    state = build_runtime(
        StartupOptions(
            settings=settings,
            token=token,
            frontend_dist=frontend_dist,
            serve_frontend=not args.no_frontend,
            allowed_hosts=allowed_hosts,
            wire_real_executor=not args.no_executor,
            log=lambda message: print(f"[startup] {message}", flush=True),
        )
    )
    print(
        json.dumps(
            {
                "url": _url(settings),
                "data_dir": str(settings.data_dir),
                "secret_store": str(settings.secret_store),
                "workspace_root": str(settings.workspace_root),
                "frontend_served": state.frontend_served,
                "executor_wired": state.executor_wired,
                "execution": state.execution_report(),
            },
            indent=2,
        ),
        flush=True,
    )
    return _run_foreground(state, settings, token.source)


def _url(settings: Settings) -> str:
    return _url_for(settings.host, settings.port)


def _url_for(host: str, port: int) -> str:
    shown = host if ":" not in host else f"[{host}]"
    return f"http://{shown}:{port}"


def _wait_for_record(data_dir: Path, *, timeout: float) -> ProcessRecord | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = read_record(data_dir)
        if record is not None:
            return record
        time.sleep(0.05)
    return read_record(data_dir)


def cmd_stop(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    result = stop_process_file(settings.data_dir, timeout=args.timeout)
    print(
        json.dumps(
            {
                "stopped": result.stopped,
                "forced": result.forced,
                "pid": result.pid,
                "message": result.message,
            },
            indent=2,
        )
    )
    return 0 if result.stopped else 1


def cmd_status(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    record = read_record(settings.data_dir)
    alive = bool(record and process_alive(record.pid))
    host = record.host if record else settings.host
    port = record.port if record else settings.port
    payload: dict[str, object] = {
        "running": alive,
        "pid": record.pid if record else None,
        "url": _url_for(host, port),
        "frontend_served": record.frontend_served if record else False,
        "token_source": record.token_source if record else None,
    }
    if alive:
        payload["health"] = _fetch_health(_url_for(host, port))
    if args.deep:
        state = build_runtime(
            StartupOptions(
                settings=settings,
                serve_frontend=False,
                wire_real_executor=True,
                # ``status`` must stay read-only: never seed resources.
                seed_minimal_agent=False,
                seed_default_admin=False,
            )
        )
        payload["execution"] = state.execution_report()
    print(json.dumps(payload, indent=2))
    return 0


def _fetch_health(url: str) -> object:
    try:
        with urllib.request.urlopen(url + "/api/v1/health", timeout=2.0) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def cmd_init(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    settings.ensure_data_dir()
    store = FileStore(settings.data_dir, settings.workspace_root)
    secret_store = FileSecretStore(settings.secret_store)
    connections = ConnectionService(store, secret_store=secret_store)

    tools = tuple(item.strip() for item in args.agent_tools.split(",") if item.strip())
    skill_names = tuple(item.strip() for item in args.agent_skills.split(",") if item.strip())
    skills = {
        name: f"# {name}\n\nMinimal inline skill written by LG-020 init.\n"
        for name in skill_names
    }
    agent = None
    if args.agent_id:
        agent = AgentInit(
            id=args.agent_id,
            title=args.agent_title,
            connection_ref=args.connection_id,
            skill_refs=skill_names,
            tool_refs=tools,
        )
    report = initialize_minimal(
        store,
        connections,
        connection=ConnectionInit(
            id=args.connection_id,
            title=args.connection_title,
            backend=args.backend,
            model=args.model,
            base_url=args.base_url,
            credential_ref=args.credential_ref,
        ),
        agent=agent,
        tools=tools,
        skills=skills,
        set_worker_default=args.set_worker_default,
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0


def cmd_user_add(args: argparse.Namespace) -> int:
    """Add a team account; the password is read via getpass, never argv."""

    settings = _settings_from_args(args)
    settings.ensure_data_dir()
    accounts = TeamAccounts.from_settings(settings)
    username = args.username
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("passwords do not match", file=sys.stderr)
        return 1
    if not password:
        print("password must not be empty", file=sys.stderr)
        return 1
    try:
        account = accounts.add(username, password, args.role)
    except TeamAccountsError as exc:
        print(f"could not add account: {exc}", file=sys.stderr)
        return 1
    # Never print the password or hash.
    print(
        json.dumps(
            {
                "added": account.username,
                "role": account.role,
                "created_at": account.created_at,
                "accounts_file": str(accounts.path),
            },
            indent=2,
        )
    )
    return 0


def cmd_user_list(args: argparse.Namespace) -> int:
    """List accounts (username/role/created_at only; no hashes or passwords)."""

    settings = _settings_from_args(args)
    accounts_store = TeamAccounts.from_settings(settings)
    try:
        accounts = accounts_store.list_accounts()
    except TeamAccountsError as exc:
        print(f"could not read accounts: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "accounts": [
                    {
                        "username": account.username,
                        "role": account.role,
                        "created_at": account.created_at,
                    }
                    for account in accounts
                ],
                "accounts_file": str(accounts_store.path),
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    if args.command == "start":
        return cmd_start(args)
    if args.command == "stop":
        return cmd_stop(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "init":
        return cmd_init(args)
    if args.command == "user":
        if args.user_command == "add":
            return cmd_user_add(args)
        if args.user_command == "list":
            return cmd_user_list(args)
        parser.error("user requires a subcommand: add|list")
        return 2
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":  # pragma: no cover - module entry
    sys.exit(main())
