"""Knowledge document parsing and encoding services."""

import logging


logger = logging.getLogger("savia-api")


def _text(value, limit: int) -> str:
    """Convert an extracted value to bounded, clean text."""
    return " ".join(str(value or "").split())[:limit]


def _normalise_row(item, source_page=None, extraction_method="ai"):
    """Validate one model result and return the canonical import shape."""
    if not isinstance(item, dict):
        return None
    code = _text(item.get("code", item.get("Code", "")), 120)
    if not code:
        return None
    priority = _text(item.get("priorite", item.get("Priorite", "MOYENNE")), 20).upper()
    if priority not in {"HAUTE", "MOYENNE", "BASSE"}:
        priority = "MOYENNE"
    try:
        confidence = int(float(str(item.get("confidence", item.get("Confidence_Score", 70))).replace("%", "")))
        confidence = max(0, min(100, confidence))
    except (TypeError, ValueError):
        confidence = 70 if extraction_method == "ai" else 35
    row = {
        "code": code,
        "message": _text(item.get("message", item.get("Message", "")), 500),
        "type": _text(item.get("type", item.get("Type", "Hardware")), 80) or "Hardware",
        "cause": _text(item.get("cause", item.get("Cause", "")), 4000),
        "solution": _text(item.get("solution", item.get("Solution", "")), 8000),
        "priorite": priority,
        "confidence": confidence,
        "extraction_method": extraction_method,
    }
    if source_page is not None:
        row["source_page"] = source_page
    return row


def _text_chunks(text: str, max_chars: int = 100000):
    """Split on line boundaries so an error record is not cut mid-line."""
    chunks, current, size = [], [], 0
    for line in text.splitlines():
        # A single huge line still needs a bounded split.
        pieces = [line[i:i + max_chars] for i in range(0, len(line), max_chars)] or [""]
        for piece in pieces:
            if current and size + len(piece) + 1 > max_chars:
                chunks.append("\n".join(current))
                current, size = [], 0
            current.append(piece)
            size += len(piece) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def _code_aliases(code: str) -> set[str]:
    """Return stable aliases used to merge hex/decimal representations."""
    import re

    aliases = set()
    data_match = re.search(r"\bdata\s*=\s*([^\s\]\)]+)", str(code or ""), re.IGNORECASE)
    data_suffix = f":data={data_match.group(1).rstrip('*)').lower()}" if data_match else ""
    for match in re.finditer(r"\b(\d{2})-\s*([0-9a-f]{3,4})h\b", str(code or ""), re.IGNORECASE):
        aliases.add(f"hex:{match.group(1)}-{match.group(2)}{data_suffix}".lower())
    # A decimal value is only a safe identity when no hexadecimal identity is
    # present. Manuals can reuse a decimal value for different hex variants.
    if not aliases:
        for match in re.finditer(r"\b(\d{3,5})d\b", str(code or ""), re.IGNORECASE):
            aliases.add(f"dec:{match.group(1)}".lower())
    if not aliases and code:
        aliases.add(f"raw:{str(code).strip().casefold()}")
    return aliases


def _merge_row(rows_by_code: dict, row: dict) -> None:
    """Merge one row while treating hex and decimal code forms as one error."""
    aliases = _code_aliases(row.get("code", ""))
    existing_key = next(
        (key for key, existing in rows_by_code.items() if aliases & _code_aliases(existing.get("code", ""))),
        None,
    )
    if existing_key is None:
        rows_by_code[row["code"].casefold()] = row
        return

    existing = rows_by_code[existing_key]
    # Keep the table representation because it retains both identifiers.
    if row.get("extraction_method") == "table" and existing.get("extraction_method") != "table":
        existing["code"] = row["code"]
        existing["extraction_method"] = "ai+table" if existing.get("extraction_method") == "ai" else "table"
    for field in ("message", "type", "cause", "solution"):
        if not existing.get(field) and row.get(field):
            existing[field] = row[field]
    existing["confidence"] = max(existing.get("confidence", 0), row.get("confidence", 0))


def _extract_hex_decimal_table_rows(text: str, source_page=None) -> list:
    """Recover rows from manuals whose table has separate hex and decimal columns."""
    import re

    code_pattern = re.compile(r"\b(?P<family>\d{2})-\s*(?P<hex>[0-9a-f]{3,4})h\b", re.IGNORECASE)
    matches = list(code_pattern.finditer(text or ""))
    rows = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), match.end() + 12000)
        segment = text[match.start():next_start]
        # The decimal column and optional data marker occur immediately after
        # the hexadecimal code, before the message column starts.
        prefix = segment[:500]
        decimal_matches = list(re.finditer(r"\b(\d{3,5})d\b", prefix, re.IGNORECASE))
        decimal_values = [item.group(1) for item in decimal_matches]
        data_match = re.search(r"\bdata\s*=\s*([^\s\r\n]+)", prefix, re.IGNORECASE)
        hex_values = [match.group("hex").lower()]
        relative_hex_end = match.end() - match.start()
        after_hex = segment[relative_hex_end : min(len(segment), relative_hex_end + 180)]
        for alternate in re.findall(r"(?<![0-9a-f])([0-9a-f]{3,4})h\b", after_hex, re.IGNORECASE):
            if alternate.lower() not in hex_values:
                hex_values.append(alternate.lower())

        code = f"{match.group('family')}-{' / '.join(value + 'h' for value in hex_values)}"
        if decimal_values:
            code += f" ({' / '.join(value + 'd' for value in decimal_values[:len(hex_values)])})"
        if data_match:
            code += f" [data={data_match.group(1).rstrip('*)')}]"

        body = segment[decimal_matches[-1].end():] if decimal_matches else segment[match.end():]
        # Page headers/footers are outside the table and must not become part
        # of the last row on a page.
        body = re.split(r"\[PAGE\s+\d+\]", body, maxsplit=1, flags=re.IGNORECASE)[0]
        # Use the table's visual order as a lightweight fallback when the AI
        # does not return a row: message, numbered causes, then bullet actions.
        body = body.strip()
        cause_start = re.search(r"(?:^|\n)\s*1[.)]\s*", body)
        action_start = re.search(r"(?:^|\n)\s*[-•]\s+", body)
        message_end = min(
            [position for position in (cause_start.start() if cause_start else None, action_start.start() if action_start else None) if position is not None]
            or [len(body)]
        )
        message = body[:message_end].strip()
        cause = ""
        if cause_start:
            cause_end = action_start.start() if action_start and action_start.start() > cause_start.start() else len(body)
            cause = body[cause_start.start():cause_end].strip()
        if action_start:
            solution = body[action_start.start():].strip()
        else:
            no_action = re.search(r"\bNo action\.?", body, re.IGNORECASE)
            solution = no_action.group(0) if no_action else ""
        row = _normalise_row(
            {
                "code": code,
                "message": message,
                "cause": cause,
                "solution": solution,
                "type": "Hardware",
                "priorite": "MOYENNE",
                "confidence": 60,
            },
            source_page,
            "table",
        )
        if row:
            rows.append(row)
    return rows


def _structured_docx_row(code: str, message: str, cause: str, solution: str) -> dict | None:
    """Build one row from a DOCX alarm card, mapping Remedy to Solution."""
    import re

    match = re.search(r"\d{1,5}", str(code or ""))
    if not match:
        return None
    return _normalise_row(
        {
            "code": match.group(0),
            "message": message,
            "cause": cause,
            "solution": solution,
            "type": "Hardware",
            "priorite": "MOYENNE",
            "confidence": 85,
        },
        extraction_method="docx-structured",
    )


def extract_docx_structured_rows(data: bytes) -> list:
    """Extract alarm cards from DOCX tables and embedded text-box tables.

    Some Word manuals store the visible cards inside drawing text boxes. The
    python-docx paragraph API does not expose those nodes, which previously
    caused several alarm headings to be concatenated into one message.
    """
    import re
    import zipfile
    import xml.etree.ElementTree as ET

    rows = []
    try:
        from docx import Document

        import io

        document = Document(io.BytesIO(data))
        for table in document.tables:
            table_rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            if len(table_rows) < 3:
                continue
            header = " ".join(table_rows[0]).strip()
            if not re.search(r"\b(?:ALARM|ALLARME|ERROR|ERREUR|WARNING|FAULT|FAILURE)\b", header, re.IGNORECASE):
                continue
            cause_row = next((item for item in table_rows[1:] if re.search(r"\b(?:CAUSE|CAUSES|ORIGIN|ORIGINE)\b", " ".join(item), re.IGNORECASE)), None)
            remedy_row = next((item for item in table_rows[1:] if re.search(r"\b(?:REMEDY|SOLUTION|ACTION|FIX|CORRECTIVE ACTION)\b", " ".join(item), re.IGNORECASE)), None)
            if cause_row and remedy_row:
                alarm_match = re.search(r"\b(?:ALARM|ALLARME|ERROR|ERREUR|WARNING|FAULT|FAILURE)\s*\|?\s*(\d{1,5})\s*[:\-]\s*(.+)$", header, re.IGNORECASE)
                if alarm_match:
                    rows.append(
                        _structured_docx_row(
                            alarm_match.group(1),
                            alarm_match.group(2),
                            " ".join(cause_row[1:]),
                            " ".join(remedy_row[1:]),
                        )
                    )
    except Exception as exc:
        logger.warning("DOCX table extraction failed: %s", exc)

    try:
        import io

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml_data = archive.read("word/document.xml")
        root = ET.fromstring(xml_data)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        for textbox in root.findall(".//w:txbxContent", ns):
            paragraphs = []
            for paragraph in textbox.findall(".//w:p", ns):
                value = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns)).strip()
                if value:
                    paragraphs.append(value)
            content = " ".join(paragraphs)
            content = re.sub(r"\s+", " ", content).strip()
            if not re.search(r"\b(?:ALARM|ALLARME|ERROR|ERREUR|WARNING|FAULT|FAILURE)\s*\d{1,5}\s*[:\-]", content, re.IGNORECASE):
                continue
            match = re.search(
                r"\b(?:ALARM|ALLARME|ERROR|ERREUR|WARNING|FAULT|FAILURE)\s*(\d{1,5})\s*[:\-]\s*(.*?)\s*(?:\?\s*)?(?:CAUSE|CAUSES|ORIGIN|ORIGINE)\s+(.*?)\s+(?:REMEDY|SOLUTION|ACTION|FIX|CORRECTIVE ACTION)\s+(.*)$",
                content,
                re.IGNORECASE,
            )
            if not match:
                continue
            rows.append(_structured_docx_row(match.group(1), match.group(2), match.group(3), match.group(4)))
    except Exception as exc:
        logger.warning("DOCX embedded table extraction failed: %s", exc)

    unique = {}
    for row in rows:
        if row:
            unique[row["code"].casefold()] = row
    return list(unique.values())


def parse_text_to_rows(text: str, source_page=None, max_ai_chunks: int = 2) -> list:
    """Extract a document into structured error records using AI plus regex supplementation.

    The complete document is sent in one prompt whenever possible, matching the
    ChatGPT-style upload workflow.  Very large documents are split into a small
    number of large, line-preserving chunks so the synchronous request remains
    bounded; regex extraction still scans the complete document for error codes.
    """
    import re
    rows_by_code = {}
    chunks = _text_chunks(text)

    # Seed the result from explicit hex/decimal table rows. This guarantees
    # that a manual's complete error catalogue is retained even if the model
    # truncates its JSON response or omits a low-frequency code.
    table_rows = _extract_hex_decimal_table_rows(text, source_page)
    for table_row in table_rows:
        _merge_row(rows_by_code, table_row)

    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
        if AI_AVAILABLE and len(text.strip()) > 50:
            ai_chunks = max(0, int(max_ai_chunks))
            if len(chunks) > ai_chunks:
                logger.info(
                    "AI extraction limited to %s/%s chunks; regex will supplement the full text",
                    ai_chunks,
                    len(chunks),
                )
            invalid_chunks = 0
            for chunk_idx, text_chunk in enumerate(chunks[:ai_chunks]):
                if len(text_chunk.strip()) < 50:
                    continue
                document_label = "document complet" if len(chunks) == 1 else f"partie {chunk_idx + 1}/{len(chunks)}"
                prompt = f"""Tu es un analyste de documentation technique. Analyse la {document_label} ci-dessous et extrais toutes les fiches d'erreur réellement présentes.
Réponds uniquement avec un tableau JSON valide, sans markdown ni texte avant/après. Chaque objet doit contenir exactement ces champs:
code, message, type, cause, solution, priorite.
La valeur de priorite doit être exactement HAUTE, MOYENNE ou BASSE.
N'invente jamais une fiche ni une valeur absente. Si cause, solution ou une autre information est absente, utilise une chaîne vide.
Déduplique les entrées ayant le même code. Sois concis dans message, cause et solution pour que le tableau reste complet.

Texte:
{text_chunk}
"""
                raw = _call_ia(prompt, timeout=60, is_json=True)
                result = clean_json_response(raw) if raw else None
                if isinstance(result, dict):
                    result = [result]
                if not isinstance(result, list):
                    logger.warning("AI extraction chunk %s returned an invalid JSON shape", chunk_idx + 1)
                    invalid_chunks += 1
                    if invalid_chunks >= 2:
                        logger.warning("Stopping AI extraction after %s invalid chunks", invalid_chunks)
                        break
                    continue
                invalid_chunks = 0
                for item in result:
                    row = _normalise_row(item, source_page, "ai")
                    if not row:
                        continue
                    _merge_row(rows_by_code, row)
            if rows_by_code:
                logger.info("AI document extraction: %s unique codes from %s chunk(s)", len(rows_by_code), min(len(chunks), ai_chunks))
    except Exception as exc:
        logger.warning("AI extraction failed: %s", exc)

    # Generic regex supplements unstructured logs. For a table document, the
    # specialized parser above is more reliable and avoids false section codes.
    patterns = () if table_rows else (
        r"(?:Alarm|ERROR|ERR|FAULT|CODE)\s+(\d{1,5})",
        r"\b([EHSN]\d{2,4})\b",
        r"\b(0x[0-9A-Fa-f]{2,8})\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            code = match.group(1)
            start, end = max(0, match.start() - 30), min(len(text), match.end() + 150)
            row = _normalise_row({
                "code": code,
                "message": text[start:end].replace("\n", " "),
                "type": "Hardware",
                "priorite": "MOYENNE",
                "confidence": 35,
            }, source_page, "regex")
            if row:
                _merge_row(rows_by_code, row)

    return list(rows_by_code.values())



def detect_and_fix_encoding(data: bytes) -> str:
    """
    DÃ©tecte et corrige l'encodage universel des donnÃ©es binaires.
    Fonctionne pour tous les formats: CSV, DOCX, PDF texte, etc.
    """
    if not data:
        return ""

    import chardet

    # Essayer chardet pour dÃ©tecter l'encodage
    detected = chardet.detect(data)
    detected_encoding = detected.get('encoding') if detected and detected.get('confidence', 0) > 0.5 else None

    logger.info(f"ðŸ” Charset detection: {detected_encoding} (confidence: {detected.get('confidence', 0):.2f})")

    # Liste d'encodages Ã  essayer, avec le dÃ©tectÃ© en prioritÃ©
    encodings_to_try = []
    if detected_encoding:
        encodings_to_try.append(detected_encoding)

    # Ajouter les encodages courants dans l'ordre de probabilitÃ©
    # UTF-8 first (avec BOM), then Latin-1, then CP1252
    encodings_to_try.extend(['utf-8-sig', 'utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'cp1250', 'ascii'])

    # Essayer les encodages
    for encoding in encodings_to_try:
        try:
            text = data.decode(encoding)
            logger.info(f"âœ“ Successfully decoded with: {encoding}")
            return text
        except (UnicodeDecodeError, AttributeError, LookupError):
            continue

    # Fallback: dÃ©coder avec remplacement (ne jamais Ã©chouer)
    logger.warning("âš ï¸ All encoding attempts failed, using UTF-8 with replacement")
    return data.decode('utf-8', errors='replace')
