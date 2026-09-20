"""
Tests for the physical<->virtual node reconciliation layer.

These import the REAL modules. Run from the backend root:

    python -m pytest test_node_reconciliation.py -v

This is version 2 — after applying the OFFLINE-vs-WAITING fix
(hardware_node.py, workspace_sync.py). The two tests that documented
Bug 1 as-observed are now rewritten to assert the CORRECTED behavior;
they will only pass once the updated hardware_node.py and
workspace_sync.py are in place. test_hardware_sync_and_lab_workspace_do_not_share_nodes
is unchanged — Finding A wasn't touched by this fix and is still open.
"""

from __future__ import annotations

import pytest

from engine.hardware_nodes.hardware_node import HardwareNode, HardwareNodeStatus
from engine.hardware_nodes.workspace_sync import WorkspaceSyncService


# ---------------------------------------------------------------------------
# Bug 1 (fixed) — remove_device() now genuinely produces WAITING, and a new
# disable_device() genuinely produces OFFLINE, distinctly.
# ---------------------------------------------------------------------------

def test_mark_offline_is_no_longer_immediately_overwritten():
    """
    mark_offline() alone (no mark_waiting() called after it) now stays
    OFFLINE — the dead-code bug (calling mark_waiting() right after
    mark_offline() inside remove_device()) has been removed from
    remove_device() entirely; mark_offline() is only invoked from
    disable_device() now.
    """
    node = HardwareNode(device_id="esp32_test", board_type="esp32")
    node.mark_offline()
    assert node.status == HardwareNodeStatus.OFFLINE


def test_remove_device_produces_waiting_not_offline(tmp_path):
    """
    remove_device() — the auto-detected-loss path (DiscoveryListener on
    an unplug event) — still produces WAITING, unchanged from before.
    This is intentional: only a deliberate user action should produce
    OFFLINE now.
    """
    sync = WorkspaceSyncService(data_dir=tmp_path, default_workspace_id="default")
    sync.upsert_from_device(
        {"device_id": "esp32_test", "board_type": "esp32", "endpoint": "COM7", "connected": True}
    )

    removed = sync.remove_device("esp32_test")
    assert removed.status == HardwareNodeStatus.WAITING
    assert removed.manually_disabled is False


def test_disable_device_produces_offline_and_sets_manually_disabled(tmp_path):
    """
    disable_device() — the new user-initiated-disconnect path, used by
    disconnect_node() / the /workspace/hardware/disconnect route — now
    genuinely produces OFFLINE, and marks the node so background
    reconnect() sweeps leave it alone.
    """
    sync = WorkspaceSyncService(data_dir=tmp_path, default_workspace_id="default")
    sync.upsert_from_device(
        {"device_id": "esp32_test", "board_type": "esp32", "endpoint": "COM7", "connected": True}
    )

    disabled = sync.disable_device("esp32_test")
    assert disabled.status == HardwareNodeStatus.OFFLINE
    assert disabled.manually_disabled is True

    stored = sync.get_node("esp32_test")
    assert stored["status"] == "offline"
    assert stored["manually_disabled"] is True


def test_disconnect_node_uses_disable_device_path(tmp_path):
    """disconnect_node() (the API-facing method) now goes OFFLINE, not WAITING."""
    sync = WorkspaceSyncService(data_dir=tmp_path, default_workspace_id="default")
    sync.upsert_from_device(
        {"device_id": "esp32_test", "board_type": "esp32", "endpoint": "COM7", "connected": True}
    )

    result = sync.disconnect_node("esp32_test")
    assert result["ok"] is True
    assert result["node"]["status"] == "offline"
    assert result["node"]["manually_disabled"] is True


# ---------------------------------------------------------------------------
# manually_disabled excluded from bulk reconnect, but not from an explicit
# per-device reconnect request.
# ---------------------------------------------------------------------------

def test_bulk_reconnect_sweep_skips_manually_disabled_node(tmp_path):
    """
    A device the user deliberately disconnected must not silently come
    back online just because it happens to still be plugged in and the
    background reconnect sweep sees it.
    """
    sync = WorkspaceSyncService(data_dir=tmp_path, default_workspace_id="default")
    sync.upsert_from_device(
        {"device_id": "esp32_test", "board_type": "esp32", "endpoint": "COM7", "connected": True}
    )
    sync.disable_device("esp32_test")

    # Device is still physically present according to the hybrid layer...
    result = sync.reconnect(hybrid_devices=[{"device_id": "esp32_test", "endpoint": "COM7"}])

    # ...but the bulk sweep must not bring it back.
    assert "esp32_test" not in result["reconnected"]
    assert "esp32_test" in result["skipped_disabled"]
    assert sync.get_node("esp32_test")["status"] == "offline"


def test_explicit_reconnect_overrides_manually_disabled(tmp_path):
    """
    Asking to reconnect a specific disabled device_id is the user
    explicitly asking for it back — this should clear the disabled flag
    and actually reconnect it if the hardware is present.
    """
    sync = WorkspaceSyncService(data_dir=tmp_path, default_workspace_id="default")
    sync.upsert_from_device(
        {"device_id": "esp32_test", "board_type": "esp32", "endpoint": "COM7", "connected": True}
    )
    sync.disable_device("esp32_test")

    result = sync.reconnect(
        device_id="esp32_test",
        hybrid_devices=[{"device_id": "esp32_test", "endpoint": "COM7"}],
    )

    assert "esp32_test" in result["reconnected"]
    node = sync.get_node("esp32_test")
    assert node["status"] == "online"
    assert node["manually_disabled"] is False


def test_restart_preserves_manually_disabled_across_load(tmp_path):
    """
    A deliberately-disabled node must stay OFFLINE across a server
    restart, unlike an auto-WAITING node which is untouched either way
    since _load_default() only ever downgrades ONLINE, never OFFLINE.
    """
    sync1 = WorkspaceSyncService(data_dir=tmp_path, default_workspace_id="default")
    sync1.upsert_from_device(
        {"device_id": "esp32_test", "board_type": "esp32", "endpoint": "COM7", "connected": True}
    )
    sync1.disable_device("esp32_test")

    # Simulate a restart: a fresh service instance loading the same data_dir.
    sync2 = WorkspaceSyncService(data_dir=tmp_path, default_workspace_id="default")
    node = sync2.get_node("esp32_test")
    assert node["status"] == "offline"
    assert node["manually_disabled"] is True


# ---------------------------------------------------------------------------
# Finding A — unchanged by this fix, still open. Kept here so the full
# suite reflects the complete, current picture in one file.
# ---------------------------------------------------------------------------

def test_hardware_sync_and_lab_workspace_do_not_share_nodes(tmp_path):
    from engine.lab_workspace.service import LabWorkspaceService
    from engine.lab_workspace.storage import LabWorkspaceStorage

    hw_sync = WorkspaceSyncService(data_dir=tmp_path, default_workspace_id="default")
    lab = LabWorkspaceService(storage=LabWorkspaceStorage(base_dir=tmp_path))

    canvas_ws = lab.create(name="Test bench")
    canvas_ws_id = canvas_ws["workspace_id"]
    assert canvas_ws_id != "default"

    hw_sync.upsert_from_device(
        {"device_id": "esp32_test", "board_type": "esp32", "endpoint": "COM7", "connected": True}
    )
    assert hw_sync.get_node("esp32_test") is not None

    canvas_state = lab.get_state(canvas_ws_id)
    assert len(canvas_state["canvas"]["nodes"]) == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))