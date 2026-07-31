"""Structured logging, request correlation, and lightweight Prometheus metrics."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any


_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def request_id_from_header(value: str | None) -> str:
    """Accept only a bounded, safe client correlation id or generate one."""
    if value and _SAFE_REQUEST_ID.fullmatch(value):
        return value
    return uuid.uuid4().hex


def set_request_id(value: str):
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def current_request_id() -> str:
    return _request_id.get()


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line, suitable for Docker, Coolify and log shippers."""

    _extra_fields = (
        "event",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "username",
        "role",
        "client_ip",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = current_request_id()
        if request_id:
            payload["request_id"] = request_id
        for field in self._extra_fields:
            value = getattr(record, field, None)
            if value not in (None, ""):
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Configure JSON stdout logs once the application runtime has loaded."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    # Uvicorn keeps its own handlers by default; let its diagnostics participate
    # in the same JSON stream. API access events are logged by our middleware.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    # The application middleware emits the canonical access record with a
    # request_id. Disable Uvicorn's duplicate record, which has no context.
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.handlers.clear()
    uvicorn_access_logger.disabled = True


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.monotonic()
        self._requests = Counter()
        self._status = Counter()
        self._duration_sum_seconds = 0.0

    def record(self, status_code: int, duration_seconds: float) -> None:
        with self._lock:
            self._requests["total"] += 1
            self._status[str(status_code)] += 1
            self._duration_sum_seconds += max(0.0, duration_seconds)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "requests_total": self._requests["total"],
                "status": dict(self._status),
                "duration_sum_seconds": self._duration_sum_seconds,
                "uptime_seconds": time.monotonic() - self._started_at,
            }


metrics = RequestMetrics()


def _disk_capacity() -> dict[str, int]:
    path = os.getenv("OBS_DATA_PATH", "/app/data")
    try:
        usage = shutil.disk_usage(path)
        return {"total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free}
    except OSError:
        return {"total_bytes": 0, "used_bytes": 0, "free_bytes": 0}


def capacity_snapshot(conn) -> dict[str, Any]:
    """Return capacity values without raising if PostgreSQL is temporarily down."""
    disk = _disk_capacity()
    database_bytes = 0
    try:
        row = conn.execute("SELECT pg_database_size(current_database()) AS database_bytes").fetchone()
        database_bytes = int(row.get("database_bytes") or 0) if row else 0
    except Exception:
        database_bytes = 0
    return {"disk": disk, "database_bytes": database_bytes}


def _alert_thresholds(capacity: dict[str, Any]) -> dict[str, int]:
    """Expose alert states; notification delivery belongs to the monitor."""
    try:
        disk_percent_limit = max(1, min(int(os.getenv("OBS_DISK_ALERT_PERCENT", "85")), 99))
    except ValueError:
        disk_percent_limit = 85
    try:
        database_limit = max(0, int(os.getenv("OBS_DB_ALERT_BYTES", "0")))
    except ValueError:
        database_limit = 0
    disk = capacity["disk"]
    used_percent = (disk["used_bytes"] * 100 / disk["total_bytes"]) if disk["total_bytes"] else 0
    return {
        "disk_used_percent": round(used_percent, 2),
        "disk_alert": int(used_percent >= disk_percent_limit),
        "database_alert": int(database_limit > 0 and capacity["database_bytes"] >= database_limit),
    }


def render_prometheus_metrics(conn) -> str:
    snapshot = metrics.snapshot()
    capacity = capacity_snapshot(conn)
    disk = capacity["disk"]
    alerts = _alert_thresholds(capacity)
    lines = [
        "# HELP savia_http_requests_total Total HTTP requests handled by this backend instance.",
        "# TYPE savia_http_requests_total counter",
        f"savia_http_requests_total {snapshot['requests_total']}",
        "# HELP savia_http_request_duration_seconds_sum Sum of request durations.",
        "# TYPE savia_http_request_duration_seconds_sum counter",
        f"savia_http_request_duration_seconds_sum {snapshot['duration_sum_seconds']:.6f}",
        "# HELP savia_process_uptime_seconds Backend process uptime.",
        "# TYPE savia_process_uptime_seconds gauge",
        f"savia_process_uptime_seconds {snapshot['uptime_seconds']:.3f}",
    ]
    for code, count in sorted(snapshot["status"].items()):
        lines.append(f'savia_http_responses_total{{status_code="{code}"}} {count}')
    lines.extend((
        "# HELP savia_disk_bytes Disk capacity of the backend data volume.",
        "# TYPE savia_disk_bytes gauge",
        f'savia_disk_bytes{{state="total"}} {disk["total_bytes"]}',
        f'savia_disk_bytes{{state="used"}} {disk["used_bytes"]}',
        f'savia_disk_bytes{{state="free"}} {disk["free_bytes"]}',
        "# HELP savia_disk_used_percent Percentage of the backend data volume in use.",
        "# TYPE savia_disk_used_percent gauge",
        f"savia_disk_used_percent {alerts['disk_used_percent']}",
        "# HELP savia_postgres_database_bytes Size of the connected PostgreSQL database.",
        "# TYPE savia_postgres_database_bytes gauge",
        f"savia_postgres_database_bytes {capacity['database_bytes']}",
        "# HELP savia_capacity_alert Alert state: 1 means the configured threshold is reached.",
        "# TYPE savia_capacity_alert gauge",
        f'savia_capacity_alert{{resource="disk"}} {alerts["disk_alert"]}',
        f'savia_capacity_alert{{resource="database"}} {alerts["database_alert"]}',
    ))
    return "\n".join(lines) + "\n"
