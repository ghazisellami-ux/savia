"""S3/MinIO storage helpers for SAVIA."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from urllib.parse import quote
from uuid import uuid4

logger = logging.getLogger("s3_storage")

S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "")
S3_BUCKET = os.environ.get("S3_BUCKET", "savia-logs")
S3_REGION = os.environ.get("S3_REGION", "us-east-1")

_client = None
S3_AVAILABLE = False


def _init_s3():
    """Initialize the S3-compatible client and ensure its bucket exists."""
    global _client, S3_AVAILABLE
    if _client is not None:
        return _client
    if not S3_ACCESS_KEY or not S3_SECRET_KEY:
        logger.warning("S3/MinIO is not configured")
        return None
    try:
        import boto3
        from botocore.config import Config

        kwargs = {
            "aws_access_key_id": S3_ACCESS_KEY,
            "aws_secret_access_key": S3_SECRET_KEY,
            "region_name": S3_REGION,
            "config": Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "adaptive"}),
        }
        if S3_ENDPOINT:
            kwargs["endpoint_url"] = S3_ENDPOINT
        _client = boto3.client("s3", **kwargs)
        try:
            _client.head_bucket(Bucket=S3_BUCKET)
        except Exception:
            _client.create_bucket(Bucket=S3_BUCKET)
        S3_AVAILABLE = True
        logger.info("S3 storage initialized for bucket %s", S3_BUCKET)
        return _client
    except Exception as exc:
        logger.error("S3 initialization failed: %s", exc)
        _client = None
        return None


def _safe_log_component(value: str, fallback: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in "-_ ." else "_" for char in value)
    return sanitized.strip(" .")[:100] or fallback


def _ascii_metadata(metadata: dict) -> dict[str, str]:
    """Encode S3 user-metadata keys and values into their ASCII wire form.

    Object metadata is sent as HTTP headers.  S3-compatible services reject
    non-ASCII header values, while filenames and usernames legitimately may
    contain accents.  The database remains the source of the original display
    name; percent-encoding only affects the optional object metadata copy.
    """
    return {
        quote(str(key), safe="-_.~"): quote(str(value), safe="-_.~")
        for key, value in metadata.items()
    }


def upload_file(content: str, filename: str, equipement: str, metadata: dict | None = None) -> dict | None:
    """Upload a log body. Its object key cannot be controlled by the caller."""
    client = _init_s3()
    if not client:
        return None
    content_bytes = content.encode("utf-8")
    content_hash = hashlib.sha256(content_bytes).hexdigest()
    now = datetime.utcnow()
    safe_filename = _safe_log_component(os.path.basename(filename or "log.txt"), "log.txt")
    safe_equipment = _safe_log_component(equipement, "unknown")
    s3_key = f"logs/{now.strftime('%Y/%m/%d')}/{safe_equipment}/{content_hash[:8]}_{safe_filename}"
    object_metadata = {
        "equipement": equipement,
        "original-filename": safe_filename,
        "content-hash-sha256": content_hash,
        "upload-timestamp": now.isoformat(),
    }
    object_metadata = _ascii_metadata(object_metadata)
    if metadata:
        object_metadata.update(_ascii_metadata(metadata))
    try:
        client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=content_bytes,
            ContentType="text/plain; charset=utf-8",
            Metadata=object_metadata,
        )
        return {"s3_key": s3_key, "content_hash": content_hash, "size_bytes": len(content_bytes)}
    except Exception as exc:
        logger.error("S3 log upload failed: %s", exc)
        return None


def download_file(s3_key: str) -> str | None:
    """Download a UTF-8 log body."""
    client = _init_s3()
    if not client:
        return None
    try:
        return client.get_object(Bucket=S3_BUCKET, Key=s3_key)["Body"].read().decode("utf-8")
    except Exception as exc:
        logger.error("S3 log download failed (%s): %s", s3_key, exc)
        return None


def upload_private_file(content: bytes, *, category: str, extension: str, content_type: str,
                        original_name: str, content_hash: str, metadata: dict | None = None) -> dict | None:
    """Store a user file with a generated key; it is served only through the API."""
    client = _init_s3()
    if not client:
        return None
    now = datetime.utcnow()
    key = f"private/{category}/{now.strftime('%Y/%m/%d')}/{uuid4().hex}.{extension}"
    object_metadata = {
        "original-filename": original_name,
        "content-hash-sha256": content_hash,
        "upload-timestamp": now.isoformat(),
        "category": category,
    }
    object_metadata = _ascii_metadata(object_metadata)
    if metadata:
        object_metadata.update(_ascii_metadata(metadata))
    try:
        client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=content,
            ContentType=content_type,
            Metadata=object_metadata,
        )
        logger.info("Private file uploaded: category=%s size=%s", category, len(content))
        return {"s3_key": key, "size_bytes": len(content)}
    except Exception as exc:
        logger.error("Private file upload failed: %s", exc)
        return None


def download_private_file(s3_key: str) -> tuple[bytes, str] | None:
    """Read a private object after the controller has authorized the caller."""
    client = _init_s3()
    if not client:
        return None
    try:
        response = client.get_object(Bucket=S3_BUCKET, Key=s3_key)
        return response["Body"].read(), response.get("ContentType") or "application/octet-stream"
    except Exception as exc:
        logger.error("Private file download failed: %s", exc)
        return None


def delete_file(s3_key: str) -> bool:
    client = _init_s3()
    if not client:
        return False
    try:
        client.delete_object(Bucket=S3_BUCKET, Key=s3_key)
        return True
    except Exception as exc:
        logger.error("S3 file deletion failed (%s): %s", s3_key, exc)
        return False


def list_files(prefix: str = "logs/") -> list:
    client = _init_s3()
    if not client:
        return []
    try:
        response = client.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
        return [
            {"key": item["Key"], "size": item["Size"], "last_modified": item["LastModified"].isoformat()}
            for item in response.get("Contents", [])
        ]
    except Exception as exc:
        logger.error("S3 listing failed: %s", exc)
        return []
