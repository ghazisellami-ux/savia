import json
import logging

from services.observability import (
    JsonLogFormatter,
    RequestMetrics,
    capacity_snapshot,
    render_prometheus_metrics,
    request_id_from_header,
    reset_request_id,
    set_request_id,
)


def test_request_id_is_generated_when_client_value_is_unsafe():
    assert request_id_from_header("../../bad") != "../../bad"
    assert request_id_from_header("safe-request_2026") == "safe-request_2026"


def test_json_logs_include_request_context_without_payload_data():
    token = set_request_id("request-test-2026")
    try:
        record = logging.LogRecord("savia-api", logging.INFO, __file__, 1, "HTTP request completed", (), None)
        record.event = "http_access"
        record.method = "GET"
        record.path = "/api/clients"
        record.status_code = 200
        encoded = JsonLogFormatter().format(record)
    finally:
        reset_request_id(token)

    log = json.loads(encoded)
    assert log["request_id"] == "request-test-2026"
    assert log["event"] == "http_access"
    assert "authorization" not in encoded.lower()


def test_request_metrics_count_statuses_and_duration():
    local_metrics = RequestMetrics()
    local_metrics.record(200, 0.125)
    local_metrics.record(500, 0.250)

    snapshot = local_metrics.snapshot()
    assert snapshot["requests_total"] == 2
    assert snapshot["status"] == {"200": 1, "500": 1}
    assert snapshot["duration_sum_seconds"] == 0.375


class _CapacityRow:
    def get(self, name):
        return 123456 if name == "database_bytes" else None


class _CapacityConnection:
    def execute(self, _query):
        return self

    def fetchone(self):
        return _CapacityRow()


def test_capacity_snapshot_contains_database_and_disk_values():
    snapshot = capacity_snapshot(_CapacityConnection())

    assert snapshot["database_bytes"] == 123456
    assert set(snapshot["disk"]) == {"total_bytes", "used_bytes", "free_bytes"}


def test_prometheus_metrics_expose_capacity_alert_series():
    payload = render_prometheus_metrics(_CapacityConnection())

    assert 'savia_capacity_alert{resource="disk"}' in payload
    assert 'savia_capacity_alert{resource="database"}' in payload
