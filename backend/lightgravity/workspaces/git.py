"""Bounded, hook-free git subprocess helpers (LG-018).

Every git call in :mod:`lightgravity.workspaces` goes through :func:`run_git`
so the boundary rules are enforced in one place:

* ``GIT_CONFIG_NOSYSTEM=1`` and a private ``HOME``/``GIT_CONFIG_GLOBAL`` isolate
  the invocation from the host's global/system git configuration (including a
  user-level ``core.hooksPath`` or credential helper).
* ``core.hooksPath`` points at an empty throw-away directory so no repository,
  template or inherited hook can execute.
* The child environment is an explicit allow-list; inherited secret variables
  (API keys, tokens) are not forwarded.
* Only absolute ``-C <dir>`` invocations with a fixed safe subset of commands
  are used by callers; arguments are passed as a list (never a shell string).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: Environment variables that are safe (and useful) to forward to git.
_ENV_ALLOWLIST = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TERM",
    "GIT_AUTHOR_NAME",
    "GIT_AUTHOR_EMAIL",
    "GIT_COMMITTER_NAME",
    "GIT_COMMITTER_EMAIL",
)


class GitUnavailable(RuntimeError):
    """The git executable itself is not available on this host."""


@dataclass(frozen=True, slots=True)
class GitResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def git_executable() -> str:
    exe = shutil.which("git")
    if not exe:
        raise GitUnavailable("git executable not found on PATH")
    return exe


def _child_env(home: Path, hooks_dir: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for name in _ENV_ALLOWLIST:
        value = os.environ.get(name)
        if value is not None:
            env[name] = value
    env["HOME"] = str(home)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = str(home / "gitconfig")
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = "true"
    env["GIT_HOOKS_PATH_UNUSED"] = str(hooks_dir)
    return env


class GitRunner:
    """Runs git with the boundary configuration; reusable across calls."""

    def __init__(self, scratch: Path, *, timeout: float = 60.0) -> None:
        self._scratch = scratch
        self._scratch.mkdir(parents=True, exist_ok=True)
        self._home = self._scratch / "home"
        self._home.mkdir(exist_ok=True)
        # An empty directory used as ``core.hooksPath``: no hook can fire.
        self._hooks = self._scratch / "empty-hooks"
        self._hooks.mkdir(exist_ok=True)
        self._timeout = timeout

    @property
    def hooks_dir(self) -> Path:
        return self._hooks

    def run(self, args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
            timeout: float | None = None) -> GitResult:
        exe = git_executable()
        command = [
            exe,
            "--no-optional-locks",
            "-c", f"core.hooksPath={self._hooks}",
            "-c", "core.fsmonitor=false",
            "-c", "advice.detachedHead=false",
            # Deterministic, non-secret identity for product-side operational
            # commits (e.g. the integration merge).  It never depends on the
            # host's global git config, which we deliberately isolate away.
            "-c", "user.name=LightGravity Bot",
            "-c", "user.email=bot@lightgravity.invalid",
        ]
        if cwd is not None:
            command += ["-C", str(cwd)]
        command += args
        child_env = _child_env(self._home, self._hooks)
        if env:
            child_env.update(env)
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                env=child_env,
                timeout=timeout or self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - host dependent
            raise GitUnavailable(
                f"git {' '.join(args)} timed out after {timeout or self._timeout}s"
            ) from exc
        return GitResult(proc.returncode, proc.stdout, proc.stderr)

    def ok(self, args: list[str], *, cwd: Path | None = None) -> str:
        result = self.run(args, cwd=cwd)
        if not result.ok:
            raise GitUnavailable(
                f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout


__all__ = ["GitResult", "GitRunner", "GitUnavailable", "git_executable"]
