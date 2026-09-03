"""Circuit graph and connection models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class PinDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"


class ProtocolType(str, Enum):
    DIGITAL = "digital"
    ANALOG = "analog"
    I2C = "i2c"
    SPI = "spi"
    UART = "uart"
    PWM = "pwm"
    POWER = "power"


@dataclass
class Connection:
    """Wire between controller pin and component pin."""

    connection_id: str
    source_node: str
    source_pin: str
    target_node: str
    target_pin: str
    protocol: str = ProtocolType.DIGITAL.value
    direction: str = PinDirection.OUTPUT.value
    voltage_v: float = 3.3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CircuitNode:
    node_id: str
    node_type: str
    label: str
    component_id: str = ""
    position: dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0})
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CircuitGraph:
    """Graph of nodes and connections for a virtual laboratory."""

    def __init__(self, *, laboratory_id: str = "") -> None:
        self.laboratory_id = laboratory_id
        self.nodes: dict[str, CircuitNode] = {}
        self.connections: dict[str, Connection] = {}

    def add_node(self, node: CircuitNode) -> None:
        self.nodes[node.node_id] = node

    def add_connection(self, connection: Connection) -> None:
        self.connections[connection.connection_id] = connection

    def to_dict(self) -> dict[str, Any]:
        return {
            "laboratory_id": self.laboratory_id,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "connections": [c.to_dict() for c in self.connections.values()],
            "react_flow": self.to_react_flow(),
        }

    def to_react_flow(self) -> dict[str, Any]:
        nodes = []
        for n in self.nodes.values():
            nodes.append(
                {
                    "id": n.node_id,
                    "type": n.node_type,
                    "label": n.label,
                    "component_id": n.component_id,
                    "position": dict(n.position),
                }
            )
        edges = []
        for c in self.connections.values():
            edges.append(
                {
                    "id": c.connection_id,
                    "source": c.source_node,
                    "target": c.target_node,
                    "label": f"{c.source_pin}→{c.target_pin} ({c.protocol})",
                }
            )
        return {"nodes": nodes, "edges": edges}

    @classmethod
    def from_legacy_circuit(cls, circuit: dict[str, Any], *, laboratory_id: str = "") -> "CircuitGraph":
        graph = cls(laboratory_id=laboratory_id)
        for raw in circuit.get("nodes") or []:
            graph.add_node(
                CircuitNode(
                    node_id=str(raw["id"]),
                    node_type=str(raw.get("type", "component")),
                    label=str(raw.get("label", "")),
                    component_id=str(raw.get("component_id", "")),
                    position=dict(raw.get("position") or {"x": 0, "y": 0}),
                    metadata={"pin_map": raw.get("pin_map") or {}},
                )
            )
        for raw in circuit.get("edges") or []:
            pins = str(raw.get("label", "D2→pin_0")).split("→")
            src_pin = pins[0].split(",")[0].strip() if pins else "D2"
            tgt_pin = pins[1].strip() if len(pins) > 1 else "pin_0"
            graph.add_connection(
                Connection(
                    connection_id=str(raw["id"]),
                    source_node=str(raw["source"]),
                    source_pin=src_pin,
                    target_node=str(raw["target"]),
                    target_pin=tgt_pin,
                )
            )
        return graph
