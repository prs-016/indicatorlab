"""Start one loopback dashboard API that survives closing its launcher window."""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from src.hk.live_paths import dashboard_profile, local_quote_directory

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data/hk_dashboard"
APPLICATION = "indicatorlab"
START_TIMEOUT_SECONDS = 15
MAX_HEALTH_BYTES = 65_536


def _read_state() -> dict:
    try:
        value = json.loads((STATE / "dashboard.json").read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _health(port: int) -> dict | None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
            if response.headers.get_content_type() != "application/json":
                return None
            raw = response.read(MAX_HEALTH_BYTES + 1)
        if len(raw) > MAX_HEALTH_BYTES:
            return None
        value = json.loads(raw)
        return (
            value
            if isinstance(value, dict) and value.get("application") == APPLICATION
            else None
        )
    except (OSError, ValueError, URLError):
        return None


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _owned_pid(record: dict) -> int | None:
    """A saved PID alone is insufficient: also require this launch's unique ID."""
    pid, identity = record.get("pid"), record.get("instance_id")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    if (
        not isinstance(identity, str)
        or len(identity) != 32
        or not all(c in "0123456789abcdef" for c in identity)
    ):
        return None
    try:
        command = subprocess.check_output(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            text=True,
        )
        if "src.hk.dashboard" in command and "serve" in command and identity in command:
            return pid
    except (OSError, subprocess.CalledProcessError):
        pass
    return None


@contextlib.contextmanager
def _lock():
    # This Mac/Linux launcher uses an OS-released advisory lock, avoiding a
    # stale lock after a crash and duplicate processes from repeated clicks.
    import fcntl

    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "launcher.lock").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def _collector_state(checkout: Path, action: str) -> dict:
    if action == "status":
        command = [
            sys.executable,
            "-B",
            "-c",
            "import json; from src.hk.local_service import status; print(json.dumps(status()))",
        ]
    else:
        command = [sys.executable, "-B", "-m", "src.hk.local_service", "start"]
    result = subprocess.run(
        command, cwd=checkout, capture_output=True, text=True, timeout=15, check=True
    )
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or not isinstance(value.get("running"), bool):
        raise TypeError("Invalid collector status")
    return value


def _ensure_feed() -> dict:
    """Check every known collector before starting one; custom feeds stay external."""
    if os.getenv("INDICATORLAB_LIVE_SOURCE", "local").lower() != "local":
        return {"managed": False, "reason": "external_store"}
    directory = local_quote_directory(ROOT).resolve()
    checkouts = [
        p
        for p in (ROOT, ROOT.parent / "indicatorlab-clean")
        if (p / "src/hk/local_service.py").is_file()
    ]
    chosen = next(
        (p for p in checkouts if directory == (p / "data/live_hk/current").resolve()),
        None,
    )
    if chosen is None:
        return {"managed": False, "reason": "custom_quote_directory"}
    explicit = bool(os.getenv("INDICATORLAB_LIVE_HK_DIR", "").strip())
    try:
        for checkout in checkouts:
            value = _collector_state(checkout, "status")
            if value["running"]:
                if explicit and checkout != chosen:
                    return {
                        "managed": False,
                        "running": False,
                        "reason": "another_collector_running",
                    }
                return {
                    "managed": True,
                    "running": True,
                    "pid": value.get("pid"),
                    "reused": True,
                }
    except (OSError, TypeError, ValueError, subprocess.SubprocessError):
        # Uncertain process status must not produce another background worker.
        return {
            "managed": True,
            "running": False,
            "reason": "collector_status_unavailable",
        }
    try:
        value = _collector_state(chosen, "start")
        return {
            "managed": True,
            "running": value["running"],
            "pid": value.get("pid"),
            "reused": False,
        }
    except (OSError, TypeError, ValueError, subprocess.SubprocessError):
        return {"managed": True, "running": False, "reason": "collector_start_failed"}


def start(*, port: int = 8765, with_feed: bool = False) -> dict:
    """Start or reuse the local API, optionally ensuring the existing feed runs.

    Args:
        port: Loopback TCP port for the dashboard API and static page.
        with_feed: Start a stopped known local collector through its own controls.

    Returns:
        API URL, process identity and feed-start result.

    Raises:
        RuntimeError: Another service owns the port or API startup fails.
    """
    if not 1024 <= port <= 65535:
        raise ValueError("Dashboard port must be between 1024 and 65535")
    with _lock():
        existing = _health(port)
        url = f"http://127.0.0.1:{port}/live-markets/"
        record = _read_state()
        owned_pid = _owned_pid(record)
        if owned_pid and record.get("port") != port:
            raise RuntimeError(
                f"The dashboard already runs on port {record.get('port')}; stop it before choosing another port"
            )
        if owned_pid and not existing:
            # A previous launcher can exit while its detached child is still
            # importing. Keep that child under control instead of spawning two.
            deadline = time.monotonic() + START_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                existing = _health(port)
                if existing:
                    break
                owned_pid = _owned_pid(record)
                if owned_pid is None:
                    break
                time.sleep(0.2)
            if owned_pid and not existing:
                raise RuntimeError(
                    "The existing dashboard is still starting or not responding. Use Stop HK Dashboard.command before restarting it"
                )
        if existing and existing.get("dashboard_profile") != dashboard_profile(ROOT):
            raise RuntimeError(
                f"Port {port} belongs to a different dashboard checkout or configuration; no process was stopped"
            )
        if not existing and _listening(port):
            raise RuntimeError(
                f"Port {port} is used by another service; no process was stopped"
            )
        feed = _ensure_feed() if with_feed else {"managed": False}
        if existing:
            same = record.get("port") == port and existing.get(
                "dashboard_instance"
            ) == record.get("instance_id")
            return {
                "running": True,
                "reused": True,
                "url": url,
                "feed": feed,
                "pid": owned_pid if same else None,
            }
        identity = secrets.token_hex(16)
        with (STATE / "dashboard.log").open("a") as log:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "src.hk.dashboard",
                    "serve",
                    "--port",
                    str(port),
                    "--instance-id",
                    identity,
                ],
                cwd=ROOT,
                stdout=log,
                stderr=log,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"},
            )
        record = {"pid": child.pid, "instance_id": identity, "port": port}
        temporary = STATE / "dashboard.json.tmp"
        temporary.write_text(json.dumps(record) + "\n")
        temporary.replace(STATE / "dashboard.json")
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if child.poll() is not None:
                break
            value = _health(port)
            if value and value.get("dashboard_instance") == identity:
                return {
                    "running": True,
                    "reused": False,
                    "url": url,
                    "pid": child.pid,
                    "feed": feed,
                }
            time.sleep(0.2)
        if child.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                child.kill()
            child.wait(timeout=3)
        (STATE / "dashboard.json").unlink(missing_ok=True)
        raise RuntimeError(
            f"Dashboard API did not start. Details: {STATE / 'dashboard.log'}"
        )


def status(*, port: int = 8765) -> dict:
    """Return API reachability and the identity of this launcher's owned process."""
    value = _health(port)
    record = _read_state()
    same = (
        value
        and record.get("port") == port
        and value.get("dashboard_instance") == record.get("instance_id")
    )
    return {
        "running": value is not None,
        "pid": _owned_pid(record) if same else None,
        "url": f"http://127.0.0.1:{port}/live-markets/",
        "health": value,
    }


def stop() -> dict:
    """Stop only a verified dashboard process; leave the data collector running."""
    with _lock():
        record = _read_state()
        pid = _owned_pid(record)
        if pid is None:
            return {"stopped": False, "reason": "no_owned_dashboard_process"}
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            (STATE / "dashboard.json").unlink(missing_ok=True)
            return {"stopped": True}
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if _owned_pid(record) is None:
                (STATE / "dashboard.json").unlink(missing_ok=True)
                return {"stopped": True}
            time.sleep(0.1)
        return {"stopped": False, "reason": "shutdown_pending"}
