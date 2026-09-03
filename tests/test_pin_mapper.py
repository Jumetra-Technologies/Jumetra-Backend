"""Tests for PinMapper."""

from __future__ import annotations

from engine.hybrid.pin_mapper import PinMapper


class TestPinMapper:
    def test_create_connection(self, tmp_path):
        mapper = PinMapper(storage_path=tmp_path / "pins.json")
        conn = mapper.create_connection(
            virtual_node_id="NLED001",
            virtual_pin_id="in",
            physical_device_id="esp32_abc",
            physical_pin_id="D13",
            workspace_id="WS001",
        )
        assert conn["connection_id"].startswith("HC")
        assert conn["valid"] is True
        assert len(mapper.list_connections()) == 1

    def test_persist_and_reload(self, tmp_path):
        path = tmp_path / "pins.json"
        m1 = PinMapper(storage_path=path)
        m1.create_connection(
            virtual_node_id="N1",
            virtual_pin_id="gpio",
            physical_device_id="dev1",
            physical_pin_id="D2",
        )
        m2 = PinMapper(storage_path=path)
        assert len(m2.list_connections()) == 1

    def test_validate_incompatible(self):
        issues = PinMapper.validate(
            virtual_pin_id="rx",
            physical_pin_id="A0",
            virtual_interfaces=["uart"],
            physical_interfaces=["adc"],
        )
        assert issues

    def test_connections_for_device(self, tmp_path):
        mapper = PinMapper(storage_path=tmp_path / "p.json")
        mapper.create_connection(
            virtual_node_id="N1",
            virtual_pin_id="in",
            physical_device_id="esp32_1",
            physical_pin_id="D2",
        )
        assert len(mapper.connections_for_device("esp32_1")) == 1
