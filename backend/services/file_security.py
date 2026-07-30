"""Validation and naming rules for user-provided files.

The browser supplied MIME type and filename are never trusted.  This module
checks the binary signature, limits the amount of data accepted, and creates a
safe display name.  Object-storage keys are generated separately by
``s3_storage`` and never contain user input.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from fastapi import HTTPException, UploadFile


_MIB = 1024 * 1024
_EXTENSIONS = {
    "fiche": {"jpg", "jpeg", "png", "webp", "pdf"},
    "document_technique": {"jpg", "jpeg", "png", "webp", "pdf", "docx", "xlsx"},
    "clients_import": {"csv", "xlsx"},
    "knowledge_import": {"csv", "xlsx", "xls", "pdf", "docx", "doc"},
}
_MIME_BY_EXTENSION = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "xls": "application/x-ole-storage",
    "doc": "application/x-ole-storage",
}


@dataclass(frozen=True)
class ValidatedFile:
    data: bytes
    display_name: str
    extension: str
    content_type: str
    sha256: str


def _limit_for(category: str) -> int:
    defaults = {
        "fiche": 10,
        "document_technique": 20,
        "clients_import": 10,
        "knowledge_import": 20,
    }
    env_name = f"MAX_{category.upper()}_SIZE_MB"
    try:
        value = int(os.environ.get(env_name, defaults[category]))
    except ValueError:
        value = defaults[category]
    # A configuration typo must not make the API accept unbounded uploads.
    return max(1, min(value, 100)) * _MIB


def _safe_display_name(filename: str, extension: str) -> str:
    raw_name = unicodedata.normalize("NFKC", PurePath(filename or "").name)
    stem = raw_name.rsplit(".", 1)[0] if "." in raw_name else raw_name
    stem = re.sub(r"[\x00-\x1f\x7f]+", "", stem)
    stem = re.sub(r"[^\w.() -]+", "_", stem, flags=re.UNICODE).strip(" ._")
    return f"{(stem or 'document')[:100]}.{extension}"


def _detect_content_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"PK\x03\x04"):
        return _detect_office_type(data)
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "application/x-ole-storage"
    return None


def _detect_office_type(data: bytes) -> str | None:
    """Identify an OOXML office file without trusting its .zip extension."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 500 or sum(item.file_size for item in entries) > 50 * _MIB:
                return None
            names = {item.filename for item in entries}
    except (OSError, zipfile.BadZipFile):
        return None
    if "[Content_Types].xml" not in names:
        return None
    if any(name.startswith("word/") for name in names):
        return _MIME_BY_EXTENSION["docx"]
    if any(name.startswith("xl/") for name in names):
        return _MIME_BY_EXTENSION["xlsx"]
    return None


def validate_file_bytes(filename: str, data: bytes, category: str) -> ValidatedFile:
    if category not in _EXTENSIONS:
        raise ValueError(f"Unknown file category: {category}")
    if not data:
        raise HTTPException(status_code=400, detail="Le fichier est vide")
    limit = _limit_for(category)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"Le fichier ne doit pas dépasser {limit // _MIB} Mo")

    suffix = PurePath(filename or "").suffix.lower().lstrip(".")
    if suffix not in _EXTENSIONS[category]:
        allowed = ", ".join(sorted(_EXTENSIONS[category]))
        raise HTTPException(status_code=415, detail=f"Extension non autorisée. Formats acceptés : {allowed}")
    expected = _MIME_BY_EXTENSION[suffix]
    if expected == "text/csv":
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError:
            # CSV imports support legacy encodings in their parser, but NUL
            # bytes are never valid text data and often indicate a binary file.
            if b"\x00" in data:
                raise HTTPException(status_code=415, detail="Le fichier CSV doit être un fichier texte") from None
        detected = expected
    else:
        detected = _detect_content_type(data)
    # jpg and jpeg are equivalent extensions for one binary MIME type.
    if detected != expected:
        raise HTTPException(status_code=415, detail="Le contenu du fichier ne correspond pas à son extension")
    return ValidatedFile(
        data=data,
        display_name=_safe_display_name(filename, suffix),
        extension=suffix,
        content_type=detected,
        sha256=hashlib.sha256(data).hexdigest(),
    )


async def read_validated_upload(upload: UploadFile, category: str) -> ValidatedFile:
    """Read multipart data in bounded chunks so the declared size is irrelevant."""
    limit = _limit_for(category)
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(_MIB):
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=f"Le fichier ne doit pas dépasser {limit // _MIB} Mo")
        chunks.append(chunk)
    return validate_file_bytes(upload.filename or "document", b"".join(chunks), category)


def decode_and_validate_base64(filename: str, encoded: str, category: str) -> ValidatedFile:
    """Decode a legacy JSON/base64 upload after checking its transport size."""
    if encoded.startswith("data:"):
        _, separator, encoded = encoded.partition(",")
        if not separator:
            raise HTTPException(status_code=400, detail="Contenu base64 invalide")
    maximum_transport = (_limit_for(category) * 4 // 3) + 8_192
    if len(encoded) > maximum_transport:
        raise HTTPException(status_code=413, detail=f"Le fichier ne doit pas dépasser {_limit_for(category) // _MIB} Mo")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Contenu base64 invalide") from None
    return validate_file_bytes(filename, data, category)


def validate_log_upload(filename: str, content: str) -> tuple[str, str]:
    """Bound text logs before parsing or storing them in object storage."""
    if not isinstance(content, str) or not content:
        raise HTTPException(status_code=400, detail="Le contenu du journal est requis")
    try:
        limit_mb = max(1, min(int(os.environ.get("MAX_LOG_SIZE_MB", "10")), 100))
    except ValueError:
        limit_mb = 10
    if len(content.encode("utf-8")) > limit_mb * _MIB:
        raise HTTPException(status_code=413, detail=f"Le journal ne doit pas dépasser {limit_mb} Mo")
    extension = PurePath(filename or "").suffix.lower().lstrip(".")
    if extension not in {"log", "txt", "csv", "json"}:
        raise HTTPException(status_code=415, detail="Format de journal non autorisé")
    return _safe_display_name(filename, extension), content
