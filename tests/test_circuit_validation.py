"""Sprint 24 — circuit validation tests."""

from __future__ import annotations

from engine.components import default_registry
from engine.controllers import default_controller_registry
from engine.simulation.circuit.graph import CircuitGraph, Connection, CircuitNode, ProtocolType
from engine.simulation.circuit.validation import CircuitValidator


class TestCircuitValidation:
    def test_valid_digital_connection(self):
        graph = CircuitGraph(laboratory_id="LAB001")
        graph.add_node(CircuitNode("esp32", "controller", "ESP32"))
        graph.add_node(CircuitNode("inst1", "component", "DHT11", component_id="dht11"))
        graph.add_connection(
            Connection(
                connection_id="c1",
                source_node="esp32",
                source_pin="D2",
                target_node="inst1",
                target_pin="pin_0",
                protocol=ProtocolType.DIGITAL.value,
            )
        )
        components = {"dht11": default_registry().require("dht11")}
        controller = default_controller_registry().require("esp32")
        result = CircuitValidator().validate(graph, controller=controller, components=components)
        assert result.valid is True

    def test_unsupported_protocol_flagged(self):
        graph = CircuitGraph(laboratory_id="LAB001")
        graph.add_node(CircuitNode("esp32", "controller", "ESP32"))
        graph.add_node(CircuitNode("inst1", "component", "Soil", component_id="soil-moisture"))
        graph.add_connection(
            Connection(
                connection_id="c1",
                source_node="esp32",
                source_pin="D2",
                target_node="inst1",
                target_pin="pin_0",
                protocol=ProtocolType.UART.value,
            )
        )
        components = {"soil-moisture": default_registry().require("soil-moisture")}
        result = CircuitValidator().validate(graph, components=components)
        assert result.valid is False
        assert any(i.severity == "error" for i in result.issues)

    def test_voltage_warning(self):
        graph = CircuitGraph(laboratory_id="LAB001")
        graph.add_node(CircuitNode("esp32", "controller", "ESP32"))
        graph.add_node(CircuitNode("inst1", "component", "Relay", component_id="relay"))
        graph.add_connection(
            Connection(
                connection_id="c1",
                source_node="esp32",
                source_pin="D2",
                target_node="inst1",
                target_pin="pin_0",
                voltage_v=6.0,
            )
        )
        controller = default_controller_registry().require("esp32")
        components = {"relay": default_registry().require("relay")}
        result = CircuitValidator().validate(graph, controller=controller, components=components)
        assert any(i.severity == "warning" for i in result.issues)

    def test_from_legacy_circuit(self):
        circuit = {
            "nodes": [
                {"id": "esp32", "type": "controller", "label": "ESP32", "position": {"x": 0, "y": 0}},
                {
                    "id": "VCI1",
                    "type": "component",
                    "label": "LED",
                    "component_id": "led",
                    "position": {"x": 100, "y": 100},
                },
            ],
            "edges": [{"id": "e1", "source": "esp32", "target": "VCI1", "label": "D2→pin_0"}],
        }
        graph = CircuitGraph.from_legacy_circuit(circuit, laboratory_id="LAB001")
        assert len(graph.nodes) == 2
        assert len(graph.connections) == 1
        rf = graph.to_react_flow()
        assert len(rf["nodes"]) == 2
