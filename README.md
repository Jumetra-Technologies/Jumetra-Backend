# HHIP — Hybrid Hardware Integration Platform

HHIP lets developers and students build IoT systems out of a mix of
**physical hardware** and **virtual/simulated hardware**, so that
missing components don't block prototyping or learning.

```text
Physical ESP32
Physical DHT11
        +
Virtual Soil Moisture Sensor
Virtual Relay
Virtual LCD
        ↓
      HHIP
        ↓
Hybrid IoT System
```

The core engine is simulator-agnostic. Wokwi is a planned future
simulation backend, plugged in as an adapter — never a hard
dependency of the core.

## Current phase: Sprint 26 — HHIP Engineering Workspace

Commercial laboratory environment (VS Code + Figma + Wokwi + Proteus in one app).
The **Laboratory Workspace** is the primary product surface; the research dashboard is secondary.
**Sync algorithms, correction engine, analytics engine, communication protocol, and Event Bus architecture unchanged.**

```text
LabWorkspaceService (engine/lab_workspace/)
  → Extended explorer catalog (MCUs, sensors, displays, actuators, comms, power)
  → Infinite React Flow canvas (zoom, pan, snap, minimap, undo/redo, multi-select)
  → Wire validation (voltage, protocol, duplicate pins) + auto-route
  → Device modes: physical | virtual | simulator | hybrid
  → Simulation controls: run / pause / step / reset / speed 1x–100x
  → Dockable monitors: Console, Serial, Events, Logic Analyzer, Oscilloscope
  → Zustand stores: workspace, simulation, selection, device, UI
  → FastAPI /engineering/workspace/* + WebSocket /ws/workspace/{id}
  → Next.js /laboratory/workspace (primary IDE shell)
```

### Engineering workspace folder structure

```text
engine/lab_workspace/
├── models.py          # EngineeringWorkspace, CanvasNode, CanvasWire
├── catalog.py         # Explorer catalog (40+ components)
├── wire.py            # Validation + auto-routing
├── history.py         # Undo/redo stack
├── service.py         # LabWorkspaceService orchestrator
└── storage.py         # data/lab_workspace/sessions/

dashboard/
├── app/laboratory/workspace/   # Primary product page
├── components/workspace/       # Canvas, Explorer, Inspector, Toolbar, Monitors
└── stores/                     # Zustand: workspace, simulation, selection, device, ui
```

### Workspace API (Sprint 26)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/engineering/workspace/catalog` | Component explorer catalog |
| POST | `/engineering/workspace` | Create workspace session |
| GET | `/engineering/workspace/{id}/state` | Full live state |
| POST | `/engineering/workspace/{id}/connect` | Connect runtime |
| POST | `/engineering/workspace/{id}/run` | Start simulation |
| POST | `/engineering/workspace/{id}/pause` | Pause |
| POST | `/engineering/workspace/{id}/reset` | Reset clocks/state |
| POST | `/engineering/workspace/{id}/step` | Advance simulation |
| WS | `/ws/workspace/{id}` | Realtime workspace stream |

Research project routes remain at `/workspace/projects` (unchanged).

### Limitations (Sprint 26)

- Code editor panel is reserved (structure ready; full Monaco IDE in a later sprint)
- MQTT / WebSocket message tabs are adapter hooks (not live brokers yet)
- Physical device connect uses availability flags; real serial attach uses existing HybridSerialAdapter
- Workspace reload from disk into a live session not yet implemented
- Cloud collaboration / multi-user cursors are extension points only

### Future extension points

- Plugin architecture for custom components and panels
- Wokwi / Proteus / FPGA simulator backends via HybridSimulatorAdapter
- AI circuit assistant subscribed to workspace Event Bus stream
- Cloud collaboration on `LabWorkspaceStorage` + CRDT canvas sync

---

## Sprint 25 — Hybrid Hardware Bridge (completed)

### Hybrid bridge folder structure

```text
engine/hybrid/
├── device.py              # HybridDevice, HybridDeviceMode
├── adapters/              # serial, wifi, mqtt, virtual, simulator
├── physical/esp32.py      # PhysicalESP32 bridge
├── simulators/            # WokwiAdapter, ProteusAdapter stubs
├── experiment/session.py  # HybridExperimentSession
├── bridge.py              # HybridBridgeService orchestrator
├── storage/               # HybridStorage (data/hybrid/)
└── events.py              # HYBRID_* Event Bus types
```

### Limitations (Sprint 25)

- WiFi and MQTT adapters are stubs (no real network stack yet)
- Wokwi and Proteus adapters are stubs (no external API integration)
- Physical bridge uses in-memory transport in tests; real serial requires hardware
- Hybrid experiment reload from disk into running session not yet implemented
- Sync observations are recorded only — sync/correction algorithms are not modified

---

## Sprint 24 — Virtual Hardware Behavior Engine (completed)

### Supported virtual devices (Sprint 24)

| Type | Component IDs | Capabilities |
|------|---------------|--------------|
| Sensors | `dht11`, `dht22`, `hc-sr04`, `pir`, `soil-moisture` | Generate readings, publish `SENSOR_DATA` |
| Actuators | `led`, `relay`, `servo` | Receive commands, publish `ACTUATOR_UPDATE` |
| Controllers | `esp32`, `arduino-uno`, `stm32` | GPIO, ADC, PWM, UART, I2C |

### Simulation engine folder structure

```text
engine/simulation/
├── behaviors/           # VirtualSensor, VirtualActuator + device implementations
├── virtual_controllers/ # VirtualESP32, VirtualArduinoUno, VirtualSTM32
├── circuit/             # CircuitGraph, Connection, CircuitValidator
├── runtime/             # SimulationEngine, SimulationClock, SimulationScheduler
├── storage/             # LaboratoryStorage (data/laboratory/)
├── events.py            # Event Bus integration
└── laboratory.py        # VirtualLaboratoryService orchestration
```

### Simulation example (Python)

```python
from engine.components import default_registry
from engine.controllers import default_controller_registry
from engine.simulation import VirtualLaboratoryService

service = VirtualLaboratoryService(default_registry(), default_controller_registry())
lab = service.create(
    name="Greenhouse",
    controller_id="esp32",
    component_ids=["dht22", "soil-moisture", "relay", "led"],
)
service.start(lab["laboratory_id"])
step = service.advance_simulation(lab["laboratory_id"], delta_ms=500)
print(step["state"]["behaviors"])  # live sensor/actuator state
service.send_command(lab["laboratory_id"], step["state"]["behaviors"][0]["instance_id"], "on")
service.stop_simulation(lab["laboratory_id"])
```

### Limitations (Sprint 24)

- Behaviors use deterministic math models, not physics-accurate SPICE-level simulation
- No firmware upload or binary execution on virtual MCUs
- Circuit validation is rule-based (protocol/voltage/direction), not full netlist analysis
- Wokwi/Proteus remain pluggable adapters — in-process runtime is the default
- Laboratory reload from disk into a running engine is not yet implemented

## Deploying to Render

This repository includes a Render Blueprint in `render.yaml`. Create a new
Blueprint from the repository in Render and set `HHIP_CORS_ORIGINS` to the
comma-separated origin(s) of the deployed frontend, for example
`https://app.example.com`.

The Blueprint uses `/var/data` for SQLite and application data and attaches a
1 GB persistent disk. The service health check is `/health`.

## Repository structure

```text
hhip/
├── api/
│   ├── routes/components.py, controllers.py, laboratory.py
│   └── services/component_service.py, laboratory_service.py
├── engine/
│   ├── components/          # Sprint 23 component catalog + search
│   ├── controllers/         # Microcontroller specs + compatibility
│   └── simulation/          # Virtual lab, behaviors, runtime, circuit, storage
│   └── hybrid/              # Sprint 25 hybrid hardware bridge
├── dashboard/
│   ├── app/components/      # Component search UI
│   ├── app/laboratory/      # Virtual lab creation + React Flow
│   ├── app/laboratory/[id]/simulation/  # Live simulation dashboard
│   └── app/hybrid/          # Hybrid bridge dashboard
│   ├── main.py                 # entry point
│   ├── protocol/
│   │   ├── messages.py           # HHIP Protocol Version 1 (+ SYNC_CORRECTION_*)
│   │   ├── correction.py         # Sprint 16 correction messages
│   │   ├── correction_wire.py    # Wire envelope helpers
│   │   └── reliability.py        # Sprint 17 timeout/retry/backoff
│   ├── events/
│   │   ├── sync_bridge.py        # SYNC_REQUEST → wire
│   │   └── correction_bridge.py  # SYNC_CORRECTION_REQUEST → wire
│   ├── communication/          # Transport adapters (serial, in-memory)
│   ├── devices/
│   │   ├── base/                 # Device ABC, capabilities, Physical/Simulator
│   │   ├── virtual/              # VirtualLED, VirtualButton
│   │   ├── device_manager.py
│   │   ├── registry.py
│   │   └── simulated_device.py   # in-process fake ESP32 (protocol)
│   ├── virtual/                 # compat re-exports → devices.virtual
│   ├── routing/                 # Router + RouterSubscriber
│   ├── state/                   # StateManager
│   ├── events/                  # Event, EventQueue, EventBus, EventSubscriber
│   ├── analytics/               # Sprint 20 research analytics
│   │   ├── models.py                # ExperimentAnalytics, DeviceMetrics, …
│   │   ├── engine.py                # AnalyticsEngine, ResearchReport
│   │   ├── comparison.py            # ExperimentComparison (fixed vs adaptive)
│   │   ├── reliability.py           # DeviceReliabilityScore
│   │   └── export.py                # JSON / CSV / research summary
│   ├── synchronization/         # SyncManager, Cristian engine, physical bridge
│   │   ├── control_loop/            # Sprint 19 autonomous control loop
│   │   │   ├── loop.py
│   │   │   ├── experiment.py
│   │   │   └── result.py
│   │   ├── intelligence/            # Sprint 18 adaptive sync
│   │   │   ├── interval_strategy.py
│   │   │   ├── correction_policy.py
│   │   │   ├── profile.py
│   │   │   ├── decision_engine.py
│   │   │   └── comparison.py
│   │   ├── physical_bridge.py       # PhysicalCorrectionBridge
│   │   ├── health_monitor.py        # CorrectionHealthMonitor (Sprint 17)
│   │   └── adjuster/physical_limits.py
│   ├── network/                 # NetworkConditionModel (virtual impairments)
│   ├── time/                    # Clock, ClockDomain, TimestampService
│   ├── experiments/             # ExperimentSession exports
│   ├── metrics/                 # MetricsCollector
│   └── storage/                 # StorageManager (JSONL / snapshots)
├── data/                     # Runtime events / metrics / snapshots
├── firmware/esp32/
│   ├── hhip_device/             # Full device firmware
│   └── sync_agent/              # Measurement + software correction (Sprint 16)
├── tests/                    # pytest suite
├── examples/                 # No-hardware demo scripts
├── docs/                     # Phase documentation
└── requirements.txt
```

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python engine/main.py COM8         # Windows example
python engine/main.py /dev/ttyUSB0 # Linux/macOS example
```

Flash `firmware/esp32/hhip_device/hhip_device.ino` to an ESP32 first
(see [`docs/poc-01.md`](docs/poc-01.md) for details).

### Research dashboard (Sprint 21–22)

```bash
# Terminal 1 — seed sample data (optional) and start API
cd hhip
python -m api.seed

# Recommended — works from hhip/ or repo root (fixes "No module named 'api'")
python run_api.py

# Or uvicorn — must run from hhip/ (not the parent folder)
uvicorn api.main:app --reload --port 8000

# Terminal 2 — start Next.js dashboard
cd dashboard
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL + WS
npm install
npm run dev                        # http://localhost:3000
```

**Platform API (Sprint 22):**

| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/ws/events` | Real-time platform event stream |
| POST | `/experiments/start` | Start a research experiment |
| POST | `/experiments/{id}/pause` | Pause running experiment |
| POST | `/experiments/{id}/stop` | Stop and export experiment |
| GET | `/experiments/{id}/status` | Live experiment status |
| GET | `/workspace/projects` | List research projects |
| GET | `/workspace/projects/{id}` | Project detail (experiments, datasets, reports) |
| GET | `/components/search` | Search hardware component catalog |
| GET | `/components/{id}` | Component specs + compatibility matrix |
| GET | `/controllers` | List supported microcontrollers |
| POST | `/laboratory/create` | Create virtual laboratory |
| POST | `/laboratory/{id}/start` | Start simulation engine |
| GET | `/laboratory/{id}/simulation` | Live simulation state |
| POST | `/laboratory/{id}/simulation/pause` | Pause simulation |
| POST | `/laboratory/{id}/simulation/stop` | Stop and persist run |
| POST | `/laboratory/{id}/simulation/advance` | Advance simulated time |
| POST | `/laboratory/{id}/simulation/command` | Send actuator command |
| POST | `/hybrid/create` | Create hybrid experiment |
| GET | `/hybrid/{id}` | Hybrid experiment state |
| POST | `/hybrid/{id}/start` | Start hybrid experiment |
| POST | `/hybrid/{id}/advance` | Advance hybrid simulation |
| POST | `/hybrid/{id}/stop` | Stop hybrid experiment |

Run tests:

```bash
pytest tests/                      # Python engine + platform
cd dashboard && npm test           # Dashboard component tests
```

## Roadmap

```text
1.1 Requirements → 1.2 Architecture → 1.3 Communication Protocol + ESP32 PoC
  → 1.4 Physical ↔ Virtual LED/Button → 1.4.1 Event Architecture
  → 1.4.1A Event Bus + Lifecycle → 1.4.2 Virtual Device Framework
  → Sprint 6 Device Abstraction → Sprint 7 Sync Measurement
  → Sprint 8 Sync Protocol (here) → 1.5 Synchronization Algorithms
  → 1.6 First IoT Use Case → 1.7 Wokwi/Simulator Adapter → 1.8 Visual Dashboard
  → 2. Education/STEM Platform → 3. Commercial Platform
```

## License

Licensing model (open-source core + commercial layer) to be decided
in a later phase — not settled during PoC-01.
