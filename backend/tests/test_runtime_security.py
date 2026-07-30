import api.runtime as runtime
import pytest


def test_production_cors_accepts_only_configured_origins(monkeypatch):
    monkeypatch.setattr(runtime, "IS_PRODUCTION", True)
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://app.client.tn/, https://site.client.tn, https://app.client.tn",
    )

    assert runtime._cors_origins() == [
        "https://app.client.tn",
        "https://site.client.tn",
    ]


def test_production_cors_rejects_wildcard(monkeypatch):
    monkeypatch.setattr(runtime, "IS_PRODUCTION", True)
    monkeypatch.setenv("CORS_ORIGINS", "https://app.client.tn,*")

    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        runtime._cors_origins()


def test_development_cors_keeps_local_origins(monkeypatch):
    monkeypatch.setattr(runtime, "IS_PRODUCTION", False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    assert runtime._cors_origins() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
