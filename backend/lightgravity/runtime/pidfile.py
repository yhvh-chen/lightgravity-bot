"""Runtime pid record and real process stop/cleanup (LG-020).

A started server writes a small JSON record under ``<data_dir>/runtime/`` so a
later ``lightgravity stop`` can find and stop *this* instance without guessing
pids.  Stopping is honest:

* SIGTERM first, then a bounded wait, then SIGKILL;
* the whole process group is signalled when possible so assistant/adapter child
  processes started by the server are cleaned up too;
* a stale record whose pid is gone is reported as stale and removed instead of
  being treated as a live server.

The record contains no secret material (never the runtime token value).
"""

from __future__ import annotations

import json
import os
import signal
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

RECORD_NAME = "lightgravity.json"


@dataclass(frozen=True, slots=True)
class ProcessRecord:
    """Non-secret runtime identity of a started server."""

    pid: int
    host: str
    port: int
    started_at: str
    token_source: str
    frontend_served: bool
    data_dir: str
    version: str = "0.1.0"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StopResult:
    """Outcome of a stop request against a pid record."""

    stopped: bool
    forced: bool
    pid: int | None
    message: str


def runtime_dir(data_dir: Path | str) -> Path:
    return Path(data_dir) / "runtime"


def record_path(data_dir: Path | str) -> Path:
    return runtime_dir(data_dir) / RECORD_NAME


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_record(data_dir: Path | str, record: ProcessRecord) -> Path:
    directory = runtime_dir(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = record_path(data_dir)
    tmp = directory / f".{RECORD_NAME}.tmp-{uuid.uuid4().hex}"
    payload = json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_record(data_dir: Path | str) -> ProcessRecord | None:
    path = record_path(data_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return ProcessRecord(
            pid=int(data["pid"]),
            host=str(data.get("host", "127.0.0.1")),
            port=int(data.get("port", 0)),
            started_at=str(data.get("started_at", "")),
            token_source=str(data.get("token_source", "unknown")),
            frontend_served=bool(data.get("frontend_served", False)),
            data_dir=str(data.get("data_dir", "")),
            version=str(data.get("version", "0.1.0")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def remove_record(data_dir: Path | str) -> None:
    record_path(data_dir).unlink(missing_ok=True)


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return not _is_zombie(pid)


def _is_zombie(pid: int) -> bool:
    """A not-yet-reaped child answers ``kill(pid, 0)`` but is already dead."""

    try:
        stat = Path(f"/proc/{pid}/stat").read_text("utf-8")
    except OSError:
        return False
    # ``<pid> (<comm>) <state> ...``; comm may contain spaces/parentheses.
    _, _, rest = stat.partition(") ")
    return rest[:1] == "Z"


def _signal_pid(pid: int, sig: int) -> None:
    """Signal the process; signal its group only when it is the group leader.

    A foreground server launched from a shell usually shares that shell's
    process group, so blindly calling ``killpg`` could stop unrelated
    processes.  We only escalate to the group when ``pgid == pid`` (the daemon
    path, which calls ``setsid``); otherwise we signal exactly one pid.
    """

    pgid: int | None
    try:
        pgid = os.getpgid(pid)
    except (ProcessLookupError, PermissionError, OSError):
        pgid = None
    if pgid == pid:
        try:
            os.killpg(pgid, sig)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _wait_gone(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + max(timeout, 0.0)
    while time.monotonic() < deadline:
        if not process_alive(pid):
            return True
        time.sleep(0.05)
    return not process_alive(pid)


def stop_process_file(data_dir: Path | str, *, timeout: float = 10.0) -> StopResult:
    """Stop the instance described by the pid record; report honestly."""

    record = read_record(data_dir)
    if record is None:
        return StopResult(False, False, None, "no runtime pid record found")
    pid = record.pid
    if not process_alive(pid):
        remove_record(data_dir)
        return StopResult(True, False, pid, f"process {pid} is not running; removed stale record")

    _signal_pid(pid, signal.SIGTERM)
    if _wait_gone(pid, timeout):
        remove_record(data_dir)
        return StopResult(True, False, pid, f"process {pid} stopped after SIGTERM")

    _signal_pid(pid, signal.SIGKILL)
    if _wait_gone(pid, 2.0):
        remove_record(data_dir)
        return StopResult(True, True, pid, f"process {pid} required SIGKILL")
    return StopResult(
        False, False, pid, f"process {pid} did not stop; inspect it manually"
    )


__all__ = [
    "RECORD_NAME",
    "ProcessRecord",
    "StopResult",
    "process_alive",
    "read_record",
    "record_path",
    "remove_record",
    "runtime_dir",
    "stop_process_file",
    "write_record",
]
