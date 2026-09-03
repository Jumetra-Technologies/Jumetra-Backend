import logging

from engine.main import HHIPEngine


def make_engine() -> HHIPEngine:
    # Port is never opened in these tests; _check_sequence is pure
    # in-memory bookkeeping and doesn't touch the serial adapter.
    return HHIPEngine(port="COM_TEST", persist_events=False)


class TestSequenceTracking:
    def test_first_sequence_from_device_is_accepted_silently(self, caplog):
        engine = make_engine()
        with caplog.at_level(logging.WARNING):
            engine._check_sequence("esp32_01", 1)
        assert engine._last_seen_sequence["esp32_01"] == 1
        assert not caplog.records

    def test_increasing_sequence_is_accepted_silently(self, caplog):
        engine = make_engine()
        engine._check_sequence("esp32_01", 1)
        with caplog.at_level(logging.WARNING):
            engine._check_sequence("esp32_01", 2)
        assert engine._last_seen_sequence["esp32_01"] == 2
        assert not caplog.records

    def test_duplicate_sequence_is_flagged(self, caplog):
        engine = make_engine()
        engine._check_sequence("esp32_01", 5)
        with caplog.at_level(logging.WARNING):
            engine._check_sequence("esp32_01", 5)
        assert any("Duplicate sequence" in r.message for r in caplog.records)

    def test_out_of_order_sequence_is_flagged(self, caplog):
        engine = make_engine()
        engine._check_sequence("esp32_01", 10)
        with caplog.at_level(logging.WARNING):
            engine._check_sequence("esp32_01", 3)
        assert any("Out-of-order" in r.message for r in caplog.records)

    def test_sequences_are_tracked_independently_per_device(self, caplog):
        engine = make_engine()
        engine._check_sequence("esp32_01", 100)
        with caplog.at_level(logging.WARNING):
            # A different device starting at 1 should not be treated
            # as out-of-order relative to esp32_01's sequence.
            engine._check_sequence("esp32_02", 1)
        assert not caplog.records
        assert engine._last_seen_sequence == {"esp32_01": 100, "esp32_02": 1}

    def test_engines_own_outgoing_sequence_increments(self):
        engine = make_engine()
        first = engine._next_sequence()
        second = engine._next_sequence()
        assert first == 1
        assert second == 2
