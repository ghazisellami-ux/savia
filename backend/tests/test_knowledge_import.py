from services.knowledge_import import _normalise_row, parse_text_to_rows, _structured_docx_row


def test_text_extraction_returns_unique_structured_error_rows(monkeypatch):
    import ai_engine

    monkeypatch.setattr(ai_engine, "AI_AVAILABLE", False)
    rows = parse_text_to_rows("ERROR 105 Tube overheating.\nERROR 105 repeated.\nE201 Detector fault.")

    assert {row["code"] for row in rows} == {"105", "E201"}
    assert all(set(("code", "message", "cause", "solution", "type", "priorite", "confidence")) <= row.keys() for row in rows)
    assert not any(row["code"].startswith("DOC-") for row in rows)


def test_extracted_row_normalizes_priority_and_confidence():
    row = _normalise_row(
        {"code": " E105 ", "message": "Fault", "priorite": "invalid", "confidence": 140},
        source_page=4,
        extraction_method="ai",
    )

    assert row["code"] == "E105"
    assert row["priorite"] == "MOYENNE"
    assert row["confidence"] == 100
    assert row["source_page"] == 4


def test_text_extraction_bounds_ai_calls_for_large_documents(monkeypatch):
    import ai_engine

    calls = []

    def fake_call(prompt, **kwargs):
        calls.append(prompt)
        return '[{"code": "AI-%s", "message": "Found"}]' % len(calls)

    monkeypatch.setattr(ai_engine, "AI_AVAILABLE", True)
    monkeypatch.setattr(ai_engine, "_call_ia", fake_call)
    monkeypatch.setattr(ai_engine, "clean_json_response", lambda raw: [{"code": raw.split('AI-')[1].split('"')[0], "message": "Found"}])

    text = "\n".join(f"ERROR {i} " + ("x" * 49900) for i in range(3))
    parse_text_to_rows(text)

    assert len(calls) == 2


def test_text_extraction_keeps_hex_and_decimal_table_codes(monkeypatch):
    import ai_engine

    monkeypatch.setattr(ai_engine, "AI_AVAILABLE", False)
    rows = parse_text_to_rows(
        """Error code (hex)\nError code (dec)\n30-\n0305h\n773d\nFPGA problem\n1. External cause\n- Check cabling\n"""
    )

    assert len(rows) == 1
    assert rows[0]["code"] == "30-0305h (773d)"
    assert rows[0]["cause"] == "1. External cause"
    assert rows[0]["solution"] == "- Check cabling"
    assert rows[0]["confidence"] == 60


def test_docx_remedy_is_mapped_to_solution():
    row = _structured_docx_row("ALARM 158", "Missing HV", "HV supply absent", "Reset the alarm")

    assert row["code"] == "158"
    assert row["message"] == "Missing HV"
    assert row["cause"] == "HV supply absent"
    assert row["solution"] == "Reset the alarm"
    assert row["extraction_method"] == "docx-structured"
