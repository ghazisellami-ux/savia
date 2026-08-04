"""Idempotency support for retries caused by offline synchronization."""

import json

from fastapi import HTTPException, Request
from psycopg2.extras import Json

from db_engine import get_db

HEADER_NAME = "X-SAVIA-Operation-Id"
MAX_OPERATION_ID_LENGTH = 128


def operation_id_from_request(request: Request) -> str:
    value = (request.headers.get(HEADER_NAME) or "").strip()
    if len(value) > MAX_OPERATION_ID_LENGTH:
        raise HTTPException(status_code=400, detail="Identifiant d'opération invalide")
    return value


def get_idempotent_response(operation_id: str, username: str, endpoint: str):
    if not operation_id:
        return None
    with get_db() as conn:
        row = conn.execute(
            """SELECT username, response_body
               FROM api_idempotency_keys
               WHERE operation_id = %s AND endpoint = %s""",
            (operation_id, endpoint),
        ).fetchone()
    if not row:
        return None
    if row.get("username") != username:
        raise HTTPException(status_code=409, detail="Identifiant d'opération déjà utilisé")
    payload = row.get("response_body")
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def save_idempotent_response(operation_id: str, username: str, endpoint: str, response_body: dict):
    if not operation_id:
        return
    with get_db() as conn:
        conn.execute(
            "DELETE FROM api_idempotency_keys WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '30 days'"
        )
        conn.execute(
            """INSERT INTO api_idempotency_keys
                   (operation_id, username, endpoint, response_body)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (operation_id, endpoint) DO NOTHING""",
            (operation_id, username, endpoint, Json(response_body)),
        )
