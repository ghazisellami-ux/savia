"""Protected operational metrics and capacity endpoints."""

import hmac
import os

from fastapi import HTTPException, Request
from fastapi.responses import PlainTextResponse

from api.runtime import app, get_db
from services.observability import capacity_snapshot, render_prometheus_metrics


def _require_metrics_token(request: Request) -> None:
    expected = os.getenv("METRICS_TOKEN", "")
    supplied = request.headers.get("X-Metrics-Token", "")
    if not expected:
        raise HTTPException(status_code=503, detail="METRICS_TOKEN n'est pas configuré")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="Accès aux métriques refusé")


@app.get("/api/ops/metrics", include_in_schema=False)
def get_metrics(request: Request):
    _require_metrics_token(request)
    with get_db() as conn:
        return PlainTextResponse(render_prometheus_metrics(conn), media_type="text/plain; version=0.0.4")


@app.get("/api/ops/capacity", include_in_schema=False)
def get_capacity(request: Request):
    _require_metrics_token(request)
    with get_db() as conn:
        return capacity_snapshot(conn)


__all__ = ["get_metrics", "get_capacity"]
