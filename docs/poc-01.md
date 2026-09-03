# PoC-01 — Communication Protocol (Phase 1.3)

## Objective

Prove reliable communication between one physical ESP32 and the HHIP
Python engine, using only:

```text
HELLO → HELLO_ACK → HEARTBEAT → ACK
```

Nothing else is in scope for this phase: no GUI, no database, no
authentication, no simulation backend, no multi-device support.

## What was implemented

| Component | Path | Purpose |
|---|---|---|
| Protocol | `engine/protocol/messages.py` | Message shape: create / encode / decode / validate. Stdlib only. |
| Serial adapter | `engine/communication/serial_adapter.py` | Wraps PySerial behind `connect()/disconnect()/send()/receive()`. |
| Device registry | `engine/devices/registry.py` | In-memory record of connected devices. |
| Event queue | `engine/events/queue.py` | Thread-safe FIFO; establishes the boundary for the future State Manager / Message Router. Nothing consumes it yet. |
| Engine | `engine/main.py` | CLI entry point; connects, listens, handles HELLO/HEARTBEAT, sends HELLO_ACK/ACK. |
| Firmware | `firmware/esp32/hhip_device/hhip_device.ino` | ESP32 side of the same protocol. |

## Protocol summary

Newline-delimited JSON, HHIP Protocol Version 1. Every message:

```json
{
  "version": 1,
  "message_id": "unique-id",
  "type": "HELLO",
  "source": "esp32_01",
  "target": "hhip",
  "sequence": 1,
  "timestamp": 1723456789123,
  "payload": {}
}
```

All ten message types (`HELLO`, `HELLO_ACK`, `HEARTBEAT`, `READ`,
`WRITE`, `STATE_UPDATE`, `EVENT`, `ACK`, `ERROR`, `DISCONNECT`) are
declared in `MessageType` and accepted by `validate_message()`, but
`engine/main.py` only has handlers for `HELLO` and `HEARTBEAT` in
this phase. Anything else is logged and ignored, not rejected —
that keeps the wire format stable for later phases without requiring
this phase to implement every handler.

## `--simulate` mode (no hardware required)

For development before an ESP32 is available:

```bash
python engine/main.py --simulate
python engine/main.py --simulate --heartbeat-interval 2   # faster cycle for demoing
```

This runs the real `HHIPEngine` against `engine/devices/simulated_device.py`,
an in-process fake device wired through `engine/communication/memory_adapter.py`
instead of a real serial port. Behavior mirrors the firmware (HELLO on
start, periodic HEARTBEAT), and the log output is identical in shape
to a real hardware run. Stop it with Ctrl+C.

This is explicitly a **PoC-01 testing aid**, not the "Virtual Device
Adapter" concept Phase 1.4 will build — see the module docstring in
`simulated_device.py` for why the two are kept separate.

## Engineering decisions worth flagging

1. **No Pydantic** — validation is a plain `validate_message(dict) -> list[str]` function, per the phase constraint to prefer the standard library. Easy to swap for a schema library later if message shapes grow more complex.
2. **ArduinoJson on the firmware side** — the one dependency introduced outside the Python stdlib. Hand-rolled JSON construction/parsing on a microcontroller is a well-known source of bugs (escaping, buffer sizing); ArduinoJson is small and standard for this exact job. Flagged in the firmware file header too.
3. **Sequence checking is log-only** — `HHIPEngine._check_sequence()` detects duplicate and out-of-order sequence numbers per device and logs a warning, but does not yet reject, request retransmission, or raise a `SEQUENCE_ERROR`. Reliability semantics (what should happen on a gap) are a Phase 1.5 concern once synchronization is being designed.
4. **Firmware timestamps are `millis()`, not epoch time** — the ESP32 has no wall clock. `timestamp` in outgoing device messages is device uptime in milliseconds. This is fine for PoC-01 (proving the message flow) but will need a time-sync mechanism before latency measurements in Phase 1.5 are meaningful.
5. **`python main.py PORT` works without `-m`** — `engine/main.py` inserts the project root onto `sys.path` at import time so absolute `engine.*` imports resolve whether it's run as `python engine/main.py`, from inside `engine/` as `python main.py`, or as `python -m engine.main`.

## Running it

### 1. Set up the Python environment

```bash
cd hhip
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Flash the ESP32

1. Open `firmware/esp32/hhip_device/hhip_device.ino` in the Arduino IDE (or PlatformIO).
2. Install the **ArduinoJson** library (v6.x) via Library Manager if not already installed.
3. Select your ESP32 board and port, then upload.
4. Close the Arduino Serial Monitor afterward — only one program can hold the port at a time, and the HHIP engine needs it next.

### 3. Run the engine

```bash
python engine/main.py COM8            # Windows
python engine/main.py /dev/ttyUSB0    # Linux
python engine/main.py /dev/cu.usbserial-XXXX  # macOS
```

Add `--verbose` for debug-level logging, `--baudrate` if you've changed it on the firmware side (default 115200 both sides).

### Expected output

```text
[HHIP] Connecting to COM8...
[HHIP] Connected.

[RX] HELLO from esp32_01
[HHIP] Device registered: esp32_01
[TX] HELLO_ACK
[RX] HEARTBEAT from esp32_01
[TX] ACK
```

A `HEARTBEAT`/`ACK` pair should repeat roughly every 5 seconds
thereafter, matching the firmware's `HEARTBEAT_INTERVAL_MS`.

## Testing

### Automated (no hardware required)

```bash
pip install pytest
pytest tests/ -v
```

Covers:
- **Protocol** (`tests/test_protocol.py`) — message creation, encode/decode round-tripping, validation of well-formed and malformed messages.
- **Registry** (`tests/test_registry.py`) — register (including re-registration on reconnect), get, remove, touch.
- **Sequence** (`tests/test_sequence.py`) — duplicate and out-of-order detection, per-device isolation, the engine's own outgoing counter.

**Status: executed.** All 38 tests pass as of this writing (`pytest tests/ -v`).

### No-hardware end-to-end check

`examples/simulate_esp32_pty.py` runs the *real* `HHIPEngine` against
a simulated device over a Linux pty pair (no ESP32 required) and
asserts the full `HELLO → HELLO_ACK → HEARTBEAT → ACK` exchange
happens correctly, including device registration.

```bash
python examples/simulate_esp32_pty.py
```

**Status: executed.** This was run during implementation and produced
a full, correct handshake — see the "Definition of done" section
below for what that confirms and what it doesn't.

This script is Linux-only (uses the `pty` module) and is a
development aid, not a substitute for the hardware test below.

### Hardware integration test (manual)

Documented, not automated, since physical hardware may not always be
attached to whatever machine runs this repo:

1. Flash the firmware (see "Flash the ESP32" above).
2. Run `python engine/main.py <PORT>`.
3. Confirm the console shows the log sequence in "Expected output" above within a few seconds of connecting.
4. Leave it running for at least 30 seconds and confirm `HEARTBEAT`/`ACK` pairs repeat roughly every 5 seconds.
5. Unplug and replug the ESP32 (or press its reset button); confirm the engine logs a fresh `HELLO`/`HELLO_ACK`/`device registered` sequence without needing to be restarted.

## What could NOT be tested without physical hardware

- The actual USB-serial link to a real ESP32 (driver behavior, cable quality, board-specific reset-on-connect quirks).
- Firmware compilation/upload via the Arduino IDE or PlatformIO toolchain.
- Real heartbeat timing drift over longer runs (minutes/hours) on physical hardware.
- Behavior when the ESP32 is reset mid-session (covered only as a manual test step above, not executed here).

Everything else — protocol correctness, engine message handling,
registry behavior, sequence detection — was executed against real
code in this sandbox (pytest suite + pty-based simulation), not just
written and assumed correct.

## Definition of done

PoC-01 is complete once the hardware integration test above has
actually been run against a physical ESP32 and produces the expected
log sequence. That step has **not** been performed in this session
(no hardware is attached to this environment) — everything else
(protocol, engine logic, tests, pty-simulated end-to-end flow) has
been implemented and verified. Do not proceed to Phase 1.4 until
that hardware run has been done and confirmed.
