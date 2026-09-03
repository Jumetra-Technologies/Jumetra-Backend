# Phase 1.4 — Physical ↔ Virtual Hybrid Interaction

## Research question

> Can a physical hardware component and a virtual hardware component
> operate together as one synchronized embedded system?

## Updated project structure

```text
hhip/
├── engine/
│   ├── devices/
│   │   ├── manager.py          # NEW — unifies physical + virtual device lookup
│   │   ├── registry.py         # unchanged (physical devices)
│   │   └── simulated_device.py # extended — now handles/ACKs STATE_UPDATE
│   ├── routing/                # NEW package
│   │   ├── __init__.py
│   │   └── router.py           # generic STATE_UPDATE routing, both directions
│   ├── state/                  # NEW package
│   │   ├── __init__.py
│   │   └── state_manager.py    # previous/current/source/timestamp per device
│   ├── virtual/                # NEW package
│   │   ├── __init__.py
│   │   ├── base_device.py      # VirtualDevice ABC
│   │   ├── virtual_led.py
│   │   └── virtual_button.py
│   └── main.py                 # extended — STATE_UPDATE dispatch, --interactive
├── firmware/esp32/hhip_device/hhip_device.ino  # extended — button + LED
├── tests/
│   ├── test_virtual_led.py       # NEW
│   ├── test_virtual_button.py    # NEW
│   ├── test_state_manager.py     # NEW
│   ├── test_device_manager.py    # NEW
│   ├── test_router.py            # NEW
│   └── (test_protocol.py, test_registry.py, test_sequence.py unchanged)
└── examples/
    └── demo_phase_1_4.py        # NEW — executable proof of both demonstrations
```

Nothing from Phase 1.3 was deleted, redesigned, or had its behavior
changed. `engine.registry` (physical devices) still works exactly as
it did; `HHIPEngine`'s constructor signature only gained an optional
`physical_device_id` parameter.

## Modules created

| Module | Responsibility |
|---|---|
| `engine/virtual/base_device.py` | `VirtualDevice` ABC: id, type, state, `last_updated`, `receive_event()`, `report_state()`. |
| `engine/virtual/virtual_led.py` | `VirtualLED`: `turn_on/turn_off/toggle/get_state`, plus `receive_event({"state": "ON"/"OFF"})`. |
| `engine/virtual/virtual_button.py` | `VirtualButton`: `press/release`, plus an `on_change(button, previous, new)` callback so it can *emit* events without importing the Router. |
| `engine/routing/router.py` | `Router`: `route_incoming(message)` (protocol → virtual device) and `route_outgoing(target, payload, source_device, previous_state)` (virtual device → protocol). No device-type branching — enforced by a test that inspects the module's AST. |
| `engine/state/state_manager.py` | `StateManager`: one `StateRecord` (previous, current, source, timestamp) per device_id. |
| `engine/devices/manager.py` | `DeviceManager`: wraps the existing physical `DeviceRegistry` + a new virtual device dict, giving `Router` a single `get(device_id)` regardless of device kind. |

## Design decisions worth flagging

1. **DeviceManager wraps, doesn't replace, DeviceRegistry.** `HHIPEngine.registry` is still a plain `DeviceRegistry`, unchanged. `DeviceManager.physical` *is* that same object — `HHIPEngine.device_manager.physical is HHIPEngine.registry`. This was a deliberate choice to satisfy "do not redesign existing components."

2. **VirtualButton emits via callback, not by importing Router.** Keeping `engine/virtual/` free of any import from `engine/routing/` means virtual devices stay testable in total isolation (see `test_virtual_button.py`) and the dependency direction stays one-way: `routing` depends on `virtual`, never the reverse.

3. **One ESP32, one button, one LED — hardcoded target routing.** `HHIPEngine.physical_device_id` (default `"esp32_01"`) is where outgoing STATE_UPDATEs from the virtual button get sent. This is a real simplification, not a general addressing scheme — multi-device/multi-component routing is out of scope for this phase. Flagged in code comments at the constant's definition in `main.py`.

4. **HHIP ACKs every STATE_UPDATE it routes, even if routing fails.** `_handle_state_update()` always sends an `ACK` back to the sender, regardless of whether `Router.route_incoming()` found the target device. This mirrors the existing HEARTBEAT→ACK pattern from Phase 1.3 for consistency, but it means the ACK confirms *transport receipt*, not *successful routing*. A future phase should probably split these (e.g. ACK vs. ERROR/UNKNOWN_DEVICE) — noted below under limitations.

5. **`--interactive` terminal commands, not a GUI.** Since Demonstration B needs *something* to trigger the virtual button, and the spec explicitly forbids a GUI, `engine/main.py --interactive` starts a background thread reading `press` / `release` / `status` / `quit` from stdin. This is plain text I/O, not a graphical interface — but it is a new interaction surface, so it's flagged rather than silently added. `quit` only stops the command reader, not the engine itself (Ctrl+C still stops the program) — a known rough edge, not a bug.

6. **`SimulatedDevice`'s default id changed from `sim_esp32_01` to `esp32_01`.** Caught by actually running `--simulate --interactive` end-to-end before shipping this: the mismatch meant a pressed virtual button had nowhere to route to. Now the simulated device's id matches the real firmware's `DEVICE_ID`, and `SimulatedDevice` gained `_handle_state_update()` so it ACKs and logs a simulated LED change, mirroring what the real firmware now does.

## Manual test procedure

### 1. No hardware required — automated

```bash
pytest tests/ -v
```
**Status: executed.** 79/79 pass (38 from Phase 1.3 unchanged + 41 new).

### 2. No hardware required — executable end-to-end proof

```bash
python examples/demo_phase_1_4.py
```

This runs the real `HHIPEngine` (not a mock) against an `InMemoryAdapter`
standing in for a physical ESP32, and asserts both demonstrations
actually happen: an inbound `STATE_UPDATE` turns the virtual LED on,
and a virtual button press produces an outbound `STATE_UPDATE`
targeting the physical device.

**Status: executed.** Actual output:

```text
======================================================================
Setup: fake ESP32 sends HELLO (needed before either demonstration)
======================================================================
Fake ESP32 registered. HELLO_ACK received.

======================================================================
Demonstration A: Physical Button -> ESP32 -> HHIP -> Virtual LED
======================================================================
Before: virtual_led_01 state = OFF
Fake ESP32 sent STATE_UPDATE (simulating physical button press) -> virtual_led_01: ON
HHIP acknowledged the STATE_UPDATE.
After:  virtual_led_01 state = ON
Demonstration A: PASSED — physical button press turned the virtual LED ON.
StateManager record: {'device_id': 'virtual_led_01', 'previous_state': 'OFF', 'current_state': 'ON', 'source': 'esp32_01', 'timestamp': 1786620144624}

======================================================================
Demonstration B: Virtual Button -> HHIP -> ESP32 -> Physical LED
======================================================================
Before: virtual_button_01 state = RELEASED
Called engine.press_virtual_button() (simulating a virtual button activation)
Fake ESP32 received STATE_UPDATE targeting it: {'state': 'ON'}
Demonstration B: PASSED — virtual button press produced an outgoing STATE_UPDATE to the physical device, requesting LED = ON.
StateManager record: {'device_id': 'virtual_button_01', 'previous_state': 'RELEASED', 'current_state': 'PRESSED', 'source': 'hhip'}

======================================================================
Both demonstrations verified end-to-end against the real HHIPEngine.
======================================================================
```

### 3. No hardware required — interactive CLI

```bash
python engine/main.py --simulate --interactive --heartbeat-interval 100
```
Then type `status`, `press`, `status`, `quit`.

**Status: executed.** Actual (abbreviated) output confirms the full
loop: virtual button press → Router → `STATE_UPDATE` sent to
`esp32_01` → simulated device applies it and ACKs → engine logs the
`ACK` back:

```text
[HHIP] --- Status ---
[HHIP] virtual  virtual_led_01       OFF
[HHIP] virtual  virtual_button_01    RELEASED
[VIRTUAL BUTTON] virtual_button_01 state changed: RELEASED -> PRESSED
[TX] STATE_UPDATE
[SIM] received STATE_UPDATE; simulated physical LED -> ON
[ROUTER] virtual_button_01 -> esp32_01: {'state': 'ON'}
[STATE] virtual_button_01: RELEASED -> PRESSED (source=hhip)
[HHIP] --- Status ---
[HHIP] virtual  virtual_button_01    PRESSED
[RX] ACK from esp32_01
```

(Log lines from the interactive-command thread and the engine's
receive loop can interleave slightly — cosmetic, not a correctness
issue; noted under limitations.)

### 4. Requires physical hardware — NOT executed in this session

1. Flash the extended firmware (Arduino IDE: Verify only was run in this session — see below).
2. Wire a push button to `BUTTON_PIN` (GPIO4, `INPUT_PULLUP`, active LOW — button to GND) and confirm an LED on `LED_PIN` (GPIO2, or your board's built-in LED).
3. Run `python engine/main.py <PORT>`.
4. **Demonstration A:** press the physical button. Expect:
   ```text
   [RX] STATE_UPDATE from esp32_01
   [ROUTER] esp32_01 -> virtual_led_01: OFF -> ON
   [VIRTUAL LED] virtual_led_01 state changed: OFF -> ON
   [STATE] virtual_led_01: OFF -> ON (source=esp32_01)
   [TX] ACK
   ```
5. **Demonstration B:** run with `--interactive` and type `press`. Expect the physical LED to turn on, and:
   ```text
   [TX] STATE_UPDATE
   [RX] ACK from esp32_01
   ```

## What could NOT be tested this session

- **Firmware compilation.** No Arduino toolchain is available in this
  sandbox (network access is restricted to a fixed allowlist that
  doesn't include Arduino's package servers). The `.ino` file was
  written and reviewed carefully, following the same structure as the
  Phase 1.3 firmware (which *did* compile clean in the user's own
  Arduino IDE), but **this has not been compiled**. Run Verify in the
  Arduino IDE before trusting it, the same way Phase 1.3's firmware was checked.
- **Real button/LED wiring and debounce behavior** on actual GPIO hardware.
- **Concurrent send()/receive() on a real serial port** from the
  `--interactive` stdin thread and the engine's main receive loop —
  exercised successfully against `InMemoryAdapter`, but that's an
  in-process queue, not a real OS serial driver.

## Limitations

- STATE_UPDATE ACKs confirm transport receipt, not routing success (see decision #4 above).
- One physical device, one button, one LED — no multi-device addressing.
- `StateManager` keeps one record per device (latest transition only), not a full history — adequate for this phase, explicitly noted as the seam for later event-replay work.
- `quit` in `--interactive` mode stops the command reader thread but not the engine's main loop; Ctrl+C is still required to fully exit.
- No debounce/robustness testing possible without real hardware.

## Suggestions for refactoring before Phase 1.5

- If STATE_UPDATE gains more producers/consumers, split the "always ACK" behavior in `_handle_state_update()` so ACK vs. ERROR reflects actual routing outcome.
- `StateManager` should grow from "latest record per device" to an append-only log once Phase 1.5 needs event replay — the `StateRecord` shape (previous/current/source/timestamp) was chosen so that change doesn't require a redesign, just a different storage container.
- The one-ESP32 `physical_device_id` assumption in `HHIPEngine` will need to become a real addressing/topology concept once more than one physical device exists.
- `checkButton()`'s debounce is time-based and simple; fine for a single button, but a library-based debounce (e.g. Bounce2) would scale better if more physical inputs are added.
