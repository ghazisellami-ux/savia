import base64

import pytest
from fastapi import HTTPException

from services.file_security import decode_and_validate_base64, validate_file_bytes


PNG = b"\x89PNG\r\n\x1a\n" + b"safe-image"
PDF = b"%PDF-1.7\n% safe document"


def test_fiche_accepts_a_real_png_and_sanitizes_its_display_name():
    file = validate_file_bytes("../../Fiche signee.png", PNG, "fiche")

    assert file.content_type == "image/png"
    assert file.display_name == "Fiche signee.png"
    assert len(file.sha256) == 64


def test_fiche_rejects_a_mismatched_extension_and_binary_content():
    with pytest.raises(HTTPException) as exc:
        validate_file_bytes("pretend.pdf", PNG, "fiche")

    assert exc.value.status_code == 415


def test_technical_document_decodes_legacy_base64_only_after_validation():
    encoded = base64.b64encode(PDF).decode("ascii")
    file = decode_and_validate_base64("notice.pdf", encoded, "document_technique")

    assert file.content_type == "application/pdf"
    assert file.data == PDF


def test_executable_extension_is_rejected_before_storage():
    with pytest.raises(HTTPException) as exc:
        validate_file_bytes("invoice.exe", b"MZ\x00\x00", "document_technique")

    assert exc.value.status_code == 415
