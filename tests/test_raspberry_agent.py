"""Tests for Raspberry Pi HHIP agent."""

from __future__ import annotations

import json

from agents.raspberry_pi.hhip_agent import RaspberryPiAgent


class TestRaspberryAgent:
    def test_device_discovery(self):
        lines: list[str] = []
        agent = RaspberryPiAgent(device_id="rpi4_test", simulate=True, writer=lines.append)
        agent.start()
        assert lines
        msg = json.loads(lines[0])
        assert msg["type"] == "EVENT"
        assert msg["payload"]["event"] == "DEVICE_DISCOVERY"
        assert msg["payload"]["board_type"] == "raspberry-pi-4"
        assert msg["payload"]["vendor"] == "Raspberry Pi Foundation"
        agent.stop()

    def test_gpio_write_and_state(self):
        lines: list[str] = []
        agent = RaspberryPiAgent(device_id="rpi4_gpio", simulate=True, writer=lines.append)
        agent.start()
        lines.clear()
        agent.handle_message(
            {
                "type": "EVENT",
                "payload": {"event": "GPIO_WRITE", "pin": "GPIO17", "value": 1},
            }
        )
        assert any(json.loads(line)["payload"].get("event") == "GPIO_STATE" for line in lines)
        assert agent._pins["GPIO17"]["state"] == 1  # noqa: SLF001

    def test_heartbeat(self):
        lines: list[str] = []
        agent = RaspberryPiAgent(device_id="rpi4_hb", simulate=True, writer=lines.append)
        agent.send_heartbeat()
        msg = json.loads(lines[-1])
        assert msg["type"] == "HEARTBEAT"

    def test_execute_command_simulated(self):
        lines: list[str] = []
        agent = RaspberryPiAgent(device_id="rpi4_cmd", simulate=True, writer=lines.append)
        agent.execute_command("hostname")
        msg = json.loads(lines[-1])
        assert msg["payload"]["event"] == "COMMAND_RESULT"
        assert msg["payload"]["ok"] is True
