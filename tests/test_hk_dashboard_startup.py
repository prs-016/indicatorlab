"""Regression checks for local app lifecycle, directory discovery and safe reuse."""

import json
import subprocess
from datetime import UTC, datetime, timedelta
from email.message import Message
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.api.live_data import LiveSettings, LiveStore
from src.hk import dashboard_runtime as runtime
from src.hk.live_paths import dashboard_profile, local_quote_directory


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    root = tmp_path / "jack"
    root.mkdir()
    monkeypatch.setattr(runtime, "ROOT", root)
    monkeypatch.setattr(runtime, "STATE", root / "data/hk_dashboard")
    for name in [
        "INDICATORLAB_LIVE_SOURCE",
        "INDICATORLAB_LIVE_HK_DIR",
        "INDICATORLAB_DASHBOARD_INSTANCE",
    ]:
        monkeypatch.delenv(name, raising=False)
    return root


def write_snapshot(directory, received):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "latest.json").write_text(
        json.dumps([{"ts_received": received.isoformat()}])
    )


def test_discovery_uses_newest_receipt_not_directory_order(tmp_path, monkeypatch):
    monkeypatch.delenv("INDICATORLAB_LIVE_HK_DIR", raising=False)
    root = tmp_path / "jack"
    week4 = root / "data/live_hk_week4"
    sibling = root.parent / "indicatorlab-clean/data/live_hk/current"
    now = datetime.now(UTC)
    write_snapshot(week4, now - timedelta(days=1))
    write_snapshot(sibling, now - timedelta(seconds=2))
    assert local_quote_directory(root) == sibling


def test_discovery_respects_explicit_path_and_has_fresh_install_default(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("INDICATORLAB_LIVE_HK_DIR", raising=False)
    assert local_quote_directory(tmp_path) == tmp_path / "data/live_hk/current"
    monkeypatch.setenv("INDICATORLAB_LIVE_HK_DIR", "data/chosen")
    assert local_quote_directory(tmp_path) == tmp_path / "data/chosen"


def test_discovery_rejects_far_future_but_allows_small_clock_skew(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("INDICATORLAB_LIVE_HK_DIR", raising=False)
    root = tmp_path / "jack"
    first, second = root / "data/live_hk_week4", root / "data/live_hk/current"
    now = datetime.now(UTC)
    write_snapshot(first, now - timedelta(days=1))
    write_snapshot(second, now + timedelta(seconds=1))
    assert local_quote_directory(root) == second
    write_snapshot(second, now + timedelta(seconds=30))
    assert local_quote_directory(root) == first


def test_reader_can_discover_collector_started_after_api(monkeypatch, tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    (new / "latest.json").write_text("[]")
    current = [old]
    monkeypatch.setattr("src.api.live_data.local_quote_directory", lambda: current[0])
    store = LiveStore(LiveSettings(directory=old, auto_discover=True))
    current[0] = new
    assert store.rows() == []


def test_profile_changes_with_checkout_or_public_configuration(tmp_path, monkeypatch):
    original = dashboard_profile(tmp_path)
    assert original != dashboard_profile(tmp_path / "other")
    monkeypatch.setenv("INDICATORLAB_LIVE_HK_DIR", "/tmp/other-quotes")
    assert original != dashboard_profile(tmp_path)
    same = dashboard_profile(tmp_path)
    monkeypatch.setenv("INDICATORLAB_DASHBOARD_INSTANCE", "another-process")
    assert dashboard_profile(tmp_path) == same


def health(root, identity=None):
    return {
        "application": "indicatorlab",
        "dashboard_profile": dashboard_profile(root),
        "dashboard_instance": identity,
    }


def test_repeated_start_reuses_healthy_same_checkout_without_spawning(
    isolated, monkeypatch
):
    monkeypatch.setattr(runtime, "_health", lambda port: health(isolated))
    monkeypatch.setattr(runtime, "_owned_pid", lambda record: None)
    spawn = Mock()
    monkeypatch.setattr(runtime.subprocess, "Popen", spawn)
    assert runtime.start()["reused"] is True
    spawn.assert_not_called()


def test_foreign_checkout_is_not_reused_or_stopped(isolated, monkeypatch):
    monkeypatch.setattr(runtime, "_health", lambda port: health(isolated / "foreign"))
    monkeypatch.setattr(runtime, "_owned_pid", lambda record: None)
    feed, kill = Mock(), Mock()
    monkeypatch.setattr(runtime, "_ensure_feed", feed)
    monkeypatch.setattr(runtime, "os", SimpleNamespace(kill=kill))
    with pytest.raises(RuntimeError, match="different dashboard"):
        runtime.start(with_feed=True)
    feed.assert_not_called()
    kill.assert_not_called()


def test_unrelated_port_does_not_start_feed_or_api(isolated, monkeypatch):
    monkeypatch.setattr(runtime, "_health", lambda port: None)
    monkeypatch.setattr(runtime, "_owned_pid", lambda record: None)
    monkeypatch.setattr(runtime, "_listening", lambda port: True)
    feed, spawn = Mock(), Mock()
    monkeypatch.setattr(runtime, "_ensure_feed", feed)
    monkeypatch.setattr(runtime.subprocess, "Popen", spawn)
    with pytest.raises(RuntimeError, match="another service"):
        runtime.start(with_feed=True)
    feed.assert_not_called()
    spawn.assert_not_called()


def test_background_start_records_identity_and_uses_detached_process(
    isolated, monkeypatch
):
    live = [None]
    child = Mock(pid=4321)
    child.poll.return_value = None

    def spawn(args, **kwargs):
        assert kwargs["start_new_session"] is True
        assert kwargs["stdin"] == subprocess.DEVNULL
        identity = args[args.index("--instance-id") + 1]
        live[0] = health(isolated, identity)
        return child

    monkeypatch.setattr(runtime, "_health", lambda port: live[0])
    monkeypatch.setattr(runtime, "_owned_pid", lambda record: None)
    monkeypatch.setattr(runtime, "_listening", lambda port: False)
    monkeypatch.setattr(runtime.subprocess, "Popen", spawn)
    result = runtime.start()
    assert result["running"] and result["pid"] == 4321
    record = runtime._read_state()
    assert len(record["instance_id"]) == 32 and record["port"] == 8765


def test_failed_child_is_reaped_and_does_not_leave_active_state(isolated, monkeypatch):
    child = Mock(pid=4321)
    child.poll.return_value = 1
    monkeypatch.setattr(runtime, "_health", lambda port: None)
    monkeypatch.setattr(runtime, "_owned_pid", lambda record: None)
    monkeypatch.setattr(runtime, "_listening", lambda port: False)
    monkeypatch.setattr(runtime.subprocess, "Popen", lambda *a, **k: child)
    with pytest.raises(RuntimeError, match="did not start"):
        runtime.start()
    child.wait.assert_called_once()
    assert not (runtime.STATE / "dashboard.json").exists()


def test_stop_never_signals_a_recycled_or_foreign_pid(isolated, monkeypatch):
    runtime.STATE.mkdir(parents=True)
    (runtime.STATE / "dashboard.json").write_text(
        json.dumps({"pid": 42, "instance_id": "a" * 32})
    )
    monkeypatch.setattr(
        runtime.subprocess, "check_output", lambda *a, **k: "python another-app.py"
    )
    kill = Mock()
    monkeypatch.setattr(runtime, "os", SimpleNamespace(kill=kill))
    assert runtime.stop()["stopped"] is False
    kill.assert_not_called()


def test_owned_pid_requires_unique_instance_in_command(isolated, monkeypatch):
    identity = "a" * 32
    monkeypatch.setattr(
        runtime.subprocess,
        "check_output",
        lambda *a, **k: f"python -m src.hk.dashboard serve --instance-id {identity}",
    )
    assert runtime._owned_pid({"pid": 42, "instance_id": identity}) == 42
    assert runtime._owned_pid({"pid": 42, "instance_id": "b" * 32}) is None
    assert runtime._owned_pid({"pid": True, "instance_id": identity}) is None


def known_checkout(root):
    p = root / "src/hk/local_service.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# fixture")


def test_auto_feed_reuses_active_sibling_even_if_older_snapshot(isolated, monkeypatch):
    sibling = isolated.parent / "indicatorlab-clean"
    known_checkout(isolated)
    known_checkout(sibling)
    monkeypatch.setattr(
        runtime, "local_quote_directory", lambda root: isolated / "data/live_hk/current"
    )
    calls = []

    def state(root, action):
        calls.append((root, action))
        return {"running": root == sibling, "pid": 123 if root == sibling else None}

    monkeypatch.setattr(runtime, "_collector_state", state)
    result = runtime._ensure_feed()
    assert result["running"] and result["reused"] and result["pid"] == 123
    assert all(action == "status" for root, action in calls)


def test_unknown_collector_status_does_not_start_another(isolated, monkeypatch):
    known_checkout(isolated)
    monkeypatch.setattr(
        runtime, "local_quote_directory", lambda root: isolated / "data/live_hk/current"
    )
    calls = []

    def state(root, action):
        calls.append(action)
        raise subprocess.TimeoutExpired("status", 15)

    monkeypatch.setattr(runtime, "_collector_state", state)
    assert runtime._ensure_feed()["reason"] == "collector_status_unavailable"
    assert calls == ["status"]


def test_custom_or_cloud_sources_do_not_start_local_workers(isolated, monkeypatch):
    monkeypatch.setattr(
        runtime, "local_quote_directory", lambda root: isolated / "custom"
    )
    state = Mock()
    monkeypatch.setattr(runtime, "_collector_state", state)
    assert runtime._ensure_feed()["reason"] == "custom_quote_directory"
    monkeypatch.setenv("INDICATORLAB_LIVE_SOURCE", "dynamodb")
    assert runtime._ensure_feed()["reason"] == "external_store"
    state.assert_not_called()


@pytest.mark.parametrize(
    "body,content_type",
    [(b"<html>page</html>", "text/html"), (b"x" * 65537, "application/json")],
)
def test_health_probe_rejects_html_and_oversized_responses(
    monkeypatch, body, content_type
):
    headers = Message()
    headers["Content-Type"] = content_type
    response = Mock(headers=headers)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = body
    monkeypatch.setattr(runtime, "urlopen", lambda *a, **k: response)
    assert runtime._health(8765) is None
    if content_type == "text/html":
        response.read.assert_not_called()
    else:
        response.read.assert_called_once_with(65537)


def test_feed_starts_once_only_after_all_known_collectors_are_inactive(
    isolated, monkeypatch
):
    sibling = isolated.parent / "indicatorlab-clean"
    known_checkout(isolated)
    known_checkout(sibling)
    monkeypatch.setattr(
        runtime, "local_quote_directory", lambda root: sibling / "data/live_hk/current"
    )
    calls = []

    def state(root, action):
        calls.append((root, action))
        return {"running": action == "start", "pid": 321 if action == "start" else None}

    monkeypatch.setattr(runtime, "_collector_state", state)
    assert runtime._ensure_feed()["pid"] == 321
    assert calls == [(isolated, "status"), (sibling, "status"), (sibling, "start")]


def test_explicit_known_directory_does_not_duplicate_a_running_sibling(
    isolated, monkeypatch
):
    sibling = isolated.parent / "indicatorlab-clean"
    known_checkout(isolated)
    known_checkout(sibling)
    monkeypatch.setenv(
        "INDICATORLAB_LIVE_HK_DIR", str(isolated / "data/live_hk/current")
    )
    monkeypatch.setattr(
        runtime, "local_quote_directory", lambda root: isolated / "data/live_hk/current"
    )
    calls = []

    def state(root, action):
        calls.append(action)
        return {"running": root == sibling, "pid": 123 if root == sibling else None}

    monkeypatch.setattr(runtime, "_collector_state", state)
    assert runtime._ensure_feed()["reason"] == "another_collector_running"
    assert "start" not in calls


def test_stop_handles_a_process_that_exits_after_identity_check(isolated, monkeypatch):
    runtime.STATE.mkdir(parents=True)
    record = runtime.STATE / "dashboard.json"
    record.write_text(json.dumps({"pid": 42, "instance_id": "a" * 32}))
    monkeypatch.setattr(runtime, "_owned_pid", lambda value: 42)

    def vanished(*args):
        raise ProcessLookupError("already stopped")

    monkeypatch.setattr(runtime, "os", SimpleNamespace(kill=vanished))
    assert runtime.stop()["stopped"] is True
    assert not record.exists()


def test_existing_child_before_port_bind_is_not_duplicated(isolated, monkeypatch):
    runtime.STATE.mkdir(parents=True)
    record = {"pid": 777, "instance_id": "a" * 32, "port": 8765}
    (runtime.STATE / "dashboard.json").write_text(json.dumps(record))
    monkeypatch.setattr(runtime, "_owned_pid", lambda value: 777)
    monkeypatch.setattr(runtime, "_health", lambda port: None)
    monkeypatch.setattr(runtime, "START_TIMEOUT_SECONDS", 0)
    spawn = Mock()
    monkeypatch.setattr(runtime.subprocess, "Popen", spawn)
    with pytest.raises(RuntimeError, match="still starting"):
        runtime.start()
    spawn.assert_not_called()
    assert runtime._read_state() == record


def test_start_waits_for_existing_child_instead_of_replacing_it(isolated, monkeypatch):
    runtime.STATE.mkdir(parents=True)
    identity = "a" * 32
    (runtime.STATE / "dashboard.json").write_text(
        json.dumps({"pid": 777, "instance_id": identity, "port": 8765})
    )
    monkeypatch.setattr(runtime, "_owned_pid", lambda value: 777)
    responses = [None, health(isolated, identity)]
    monkeypatch.setattr(runtime, "_health", lambda port: responses.pop(0))
    spawn = Mock()
    monkeypatch.setattr(runtime.subprocess, "Popen", spawn)
    assert runtime.start()["pid"] == 777
    spawn.assert_not_called()
