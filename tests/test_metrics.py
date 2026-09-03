from engine.metrics import MetricsCollector


class TestMetricsCollector:
    def test_record_event_and_processed(self):
        metrics = MetricsCollector()
        metrics.record_event()
        metrics.mark_processed()
        metrics.record_event()
        metrics.mark_processed()

        snapshot = metrics.get_metrics()
        assert snapshot["events_received"] == 2
        assert snapshot["events_processed"] == 2
        assert snapshot["errors"] == 0

    def test_record_processing_time(self):
        metrics = MetricsCollector()
        metrics.record_processing_time(2.0)
        metrics.record_processing_time(4.0)

        snapshot = metrics.get_metrics()
        assert snapshot["processing_time"] == [2.0, 4.0]
        assert snapshot["processing_time_count"] == 2
        assert snapshot["processing_time_total_ms"] == 6.0
        assert snapshot["processing_time_avg_ms"] == 3.0

    def test_errors_and_reset(self):
        metrics = MetricsCollector()
        metrics.record_event(error=True)
        metrics.record_error()
        assert metrics.get_metrics()["errors"] == 2

        metrics.reset()
        snapshot = metrics.get_metrics()
        assert snapshot["events_received"] == 0
        assert snapshot["events_processed"] == 0
        assert snapshot["errors"] == 0
        assert snapshot["processing_time"] == []

    def test_negative_processing_time_rejected(self):
        metrics = MetricsCollector()
        try:
            metrics.record_processing_time(-1)
            assert False, "expected ValueError"
        except ValueError:
            pass
