"""HHIP Engine — Hybrid Hardware Integration Platform core engine.

This package intentionally contains no simulator-specific (e.g. Wokwi)
or transport-specific logic. It only knows about:

- the HHIP wire protocol (engine.protocol)
- generic communication adapters (engine.communication)
- a device registry (engine.devices)
- a lightweight event queue abstraction (engine.events)

Physical adapters, simulation adapters, and future communication
backends (MQTT, WebSocket, BLE, ...) are expected to plug into these
boundaries rather than being embedded in the core.
"""

__version__ = "0.1.0"
