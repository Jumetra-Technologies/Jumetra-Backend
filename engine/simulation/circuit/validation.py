"""Circuit connection validation — voltage, protocol, direction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from engine.components.models import ComponentSpec
from engine.controllers.models import ControllerSpec

from .graph import CircuitGraph, Connection, ProtocolType


@dataclass
class ValidationIssue:
    connection_id: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"connection_id": self.connection_id, "severity": self.severity, "message": self.message}


@dataclass
class ValidationResult:
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "issues": [i.to_dict() for i in self.issues]}


class CircuitValidator:
    """Validate circuit connections against component and controller specs."""

    def validate(
        self,
        graph: CircuitGraph,
        *,
        controller: Optional[ControllerSpec] = None,
        components: Optional[dict[str, ComponentSpec]] = None,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        components = components or {}

        for conn in graph.connections.values():
            issues.extend(self._validate_connection(conn, controller, components, graph))

        return ValidationResult(valid=not any(i.severity == "error" for i in issues), issues=issues)

    def _validate_connection(
        self,
        conn: Connection,
        controller: Optional[ControllerSpec],
        components: dict[str, ComponentSpec],
        graph: CircuitGraph,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        target_node = graph.nodes.get(conn.target_node)
        if target_node is None:
            issues.append(ValidationIssue(conn.connection_id, "error", "Target node missing"))
            return issues

        comp = components.get(target_node.component_id)
        if comp is None:
            return issues

        if conn.protocol not in comp.interfaces and conn.protocol != ProtocolType.POWER.value:
            issues.append(
                ValidationIssue(
                    conn.connection_id,
                    "error",
                    f"Protocol {conn.protocol} not supported by {comp.name}",
                )
            )

        if controller and conn.voltage_v > controller.voltage_v + 0.5:
            issues.append(
                ValidationIssue(
                    conn.connection_id,
                    "warning",
                    f"Voltage {conn.voltage_v}V may exceed {controller.name} ({controller.voltage_v}V)",
                )
            )

        if conn.direction not in {"input", "output", "bidirectional"}:
            issues.append(
                ValidationIssue(conn.connection_id, "error", f"Invalid direction: {conn.direction}")
            )

        return issues
