# Node reconciliation — current-state spec

Status: reflects the code as of the `RECONCILIATION_DUMP.md` reviewed on this
date. Every claim below is cited to a specific file and function. Anything
not directly verifiable from the reviewed files is marked **NEEDS
CONFIRMATION** with the exact file that would close it out — it is not
guessed.

## 0. There are two independent systems, not one

| | Owns | Node type | Workspace-id space | Storage |
|---|---|---|---|---|
| **Discovery/Hybrid twin** | `WorkspaceSyncService` | `HardwareNode` | defaults to the literal string `"default"` (`WorkspaceSyncService.__init__`) | `data/lab_workspace/hardware_nodes/<id>.json` |
| **Canvas** | `LabWorkspaceService` | `CanvasNode` | `WS{uuid hex}` per `EngineeringWorkspace.create()` | `data/lab_workspace/sessions/<id>.json` |

**These two id spaces never intersect in any file reviewed.** A `HardwareNode`
created by auto-discovery lives under workspace id `"default"`; the canvas
the user has open is `WS7F3A2B91C0` or similar. `HardwareNode.to_canvas_node()`
exists (`engine/hardware_nodes/hardware_node.py`) specifically to project a
`HardwareNode` into `CanvasNode` shape, but it is not called from any of:
`workspace_sync.py`, `hardware_node_factory.py`, `discovery_listener.py`,
`api/services/workspace_hardware_service.py`.

**NEEDS CONFIRMATION**: whether `api/routes/engineering_workspace.py` (not
in the reviewed set) calls `to_canvas_node()` anywhere. If it doesn't, the
two systems are fully disjoint in production and a physical device added via
Hardware Discovery never appears on the canvas automatically — matching the
screenshot behavior seen earlier, where "Add physical board to canvas" is a
manual user action, not automatic.

## 1. HardwareNode status state machine (as implemented)

States (`HardwareNodeStatus`, `engine/hardware_nodes/hardware_node.py`):
`CONNECTING` (default) → `ONLINE` | `WAITING` | `OFFLINE` | `ERROR`

Transitions, cited to the exact call site:

| Trigger | Function | Resulting status | Notes |
|---|---|---|---|
| Device upserted (new or reconnect) | `HardwareNode.touch_heartbeat()`, called from `WorkspaceSyncService.upsert_from_device()` | `ONLINE` | Only flips from `CONNECTING`/`WAITING`; a no-op if already `ONLINE`/`OFFLINE`/`ERROR` |
| Device removed | `WorkspaceSyncService.remove_device()` | `WAITING` | **See Bug 1** — `mark_offline()` is called then immediately overwritten by `mark_waiting()` in the same function body |
| Hard delete | `WorkspaceSyncService.hard_remove()` | node deleted entirely | No status transition — node is popped from `self._nodes` |
| Reconnect pass, device found | `WorkspaceSyncService.reconnect()` | `ONLINE` | Matches by `device_id` first, `endpoint` second — **see Bug 2** |
| Reconnect pass, device not found | `WorkspaceSyncService.reconnect()` | `WAITING` | Via `HardwareNode.mark_waiting()` |
| Server restart, node was `ONLINE` at shutdown | `WorkspaceSyncService._load_default()` | `WAITING` | Explicit defensive downgrade — correct, persisted "online" is never trusted after a restart |

### Bug 1 — `HardwareNodeStatus.OFFLINE` is unreachable

`WorkspaceSyncService.remove_device()`:
```python
node.mark_offline()
# Keep node in waiting state for reconnect UX (persistence)
node.mark_waiting()
```
`mark_offline()` sets `status=OFFLINE, health="offline", available=False`.
The next line unconditionally overwrites it with `status=WAITING,
health="waiting", available=False`. `remove_device()` is the only production
disconnect path (called from `DiscoveryListener.handle_event()` on a
`DISCONNECT_EVENTS` match, and from the `/workspace/hardware/disconnect`
route via `disconnect_node()`). **No caller of `remove_device()` will ever
observe `OFFLINE`.** If any consumer branches on that status value, that
branch is dead code.

### Bug 2 — reconnect matching depends on device identity that isn't always stable

`reconnect()` matches incoming hybrid devices to existing `HardwareNode`s by:
```python
match = by_id.get(node.device_id) or by_endpoint.get(node.endpoint)
```
`device_id` stability depends entirely on firmware. From the firmware source
reviewed earlier in this project:
- `firmware/hhip_agent/esp32/hhip_agent.ino` derives it from
  `ESP.getEfuseMac()` — stable across reboots.
- `firmware/hhip_agent/arduino_uno/hhip_agent.ino` derives it from
  `simpleHash()` seeded by `analogRead(A0)` on an otherwise-unused floating
  pin — **not a stable identity**, it changes on every power cycle.

`endpoint` is the OS-assigned COM port, which Windows frequently reassigns
across USB replug/reboot. For the Uno firmware specifically, both match
strategies can fail simultaneously, and the device permanently orphans as a
new node in `WAITING` rather than reconnecting to its prior canvas position
and wiring. This is a firmware-level fix (persist a generated ID to EEPROM
on first boot and reuse it), not a `WorkspaceSyncService` fix — the
reconciliation logic here is doing the right thing with the identity it's
given.

## 2. Pin state on reconnect — carries over only where names match

`upsert_from_device()`:
```python
node = self.factory.from_hybrid_device(data, workspace_id=ws_id, position=position)
if existing:
    for name, pin in existing.pins.items():
        if name in node.pins:
            node.pins[name].state = pin.state
```
Live pin state survives a reconnect **only for pin names present in both the
old and new node's pin map.** If the newly-built pin map (from
`HardwareNodeFactory.from_hybrid_device()`, which falls back to
`get_pin_layout(board_type)` in `engine/hardware_nodes/board_renderer.py`
when the device doesn't report its own pins) differs from what was live
before — a firmware update that renames pins, or a discovery pass that
completes with a fuller pin list than an earlier partial one — the old
state for any dropped/renamed pin is silently lost, not migrated or logged.

**NEEDS CONFIRMATION**: exact conditions under which `get_pin_layout()`
returns a materially different pin set for the same `board_type` between two
calls. Not written up as a numbered bug or tested here, since testing it
without `board_renderer.py`'s real source would mean guessing its behavior —
exactly what this spec is trying to avoid.

## 3. What triggers reconciliation in the first place

`DiscoveryListener` (`engine/hardware_nodes/discovery_listener.py`) is an
`EventSubscriber` that calls `upsert_from_device()` / `remove_device()` in
response to exactly these EventBus event types:
- Connect: `HybridEventType.PHYSICAL_DEVICE_CONNECTED`, or the literal
  string `"BOARD_CONNECTED"`
- Disconnect: `HybridEventType.PHYSICAL_DEVICE_DISCONNECTED`, or the literal
  string `"BOARD_DISCONNECTED"`
- GPIO: `HybridEventType.GPIO_STATE`, `HybridEventType.GPIO_WRITE`

`HardwareDiscoveryService` (`engine/discovery/service.py`) — the plain
USB-serial scanner, the one behind the "Hardware Discovery" sidebar panel
fixed earlier — publishes via `DeviceLifecycleEvent.CONNECTED` /
`.DISCONNECTED` from `engine/devices/base/lifecycle.py`, a **different
module** than `engine.hybrid.events.HybridEventType`.

**NEEDS CONFIRMATION**: the literal string values of `DeviceLifecycleEvent`.
If they don't happen to equal `HybridEventType.PHYSICAL_DEVICE_CONNECTED`'s
value or the literal `"BOARD_CONNECTED"`, then plain USB discovery (no
hybrid-layer connection) **never** triggers `DiscoveryListener`, and a
`HardwareNode` digital twin is only ever created when a device goes through
the hybrid bridge specifically — not on ordinary serial discovery. This
would mean the two subsystems users likely perceive as the same thing
("a device got plugged in and shows up") are wired through non-overlapping
event pipelines. I'm not asserting this as fact — it depends on one file I
don't have (`engine/devices/base/lifecycle.py`).
