"""Sprint 24 — laboratory persistence tests."""

from __future__ import annotations

from engine.components import default_registry
from engine.controllers import default_controller_registry
from engine.simulation import LaboratoryStorage, VirtualLaboratoryService


class TestLaboratoryPersistence:
    def test_project_circuit_and_run_saved(self, tmp_path):
        storage = LaboratoryStorage(tmp_path)
        service = VirtualLaboratoryService(
            default_registry(),
            default_controller_registry(),
            storage=storage,
        )
        lab = service.create(
            name="Persist Lab",
            controller_id="esp32",
            component_ids=["dht11", "led"],
        )
        lab_id = lab["laboratory_id"]
        assert storage.load_project(lab_id) is not None
        assert storage.load_circuit(lab_id) is not None

        service.start(lab_id)
        service.advance_simulation(lab_id, 100)
        service.stop_simulation(lab_id)
        assert storage.list_runs(lab_id)
