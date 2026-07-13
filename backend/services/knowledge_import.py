"""Knowledge document parsing and encoding services."""

import logging


logger = logging.getLogger("savia-api")


def parse_text_to_rows(text: str) -> list:
    """Parse unstructured text (from PDF/Word) into error code rows using AI with chunking or regex."""
    import re
    import json
    rows = []

    # Try AI extraction FIRST with chunking
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
        if AI_AVAILABLE and len(text) > 50:
            # Split into chunks to avoid token limits
            chunk_size = 20000
            chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

            logger.info(f"ðŸ“¤ Sending {len(text)} chars to IA in {len(chunks)} chunk(s)")

            all_codes = {}  # Use dict to avoid duplicates

            for chunk_idx, text_chunk in enumerate(chunks):
                if len(text_chunk) < 50:
                    continue

                logger.info(f"ðŸ“¤ Chunk {chunk_idx+1}/{len(chunks)} ({len(text_chunk)} chars)")

                prompt = f"""Extrais TOUS les codes d'erreur du texte.
Pour chaque code: code, message, cause, solution.
RÃ©ponds UNIQUEMENT en JSON:
[{{"code":"105","message":"Error description","cause":"Root cause","solution":"How to fix"}}]

Texte:
{text_chunk}
"""

                raw = _call_ia(prompt, timeout=60, is_json=True)

                if raw:
                    raw_text = raw.strip()
                    raw_text = re.sub(r'```\w*\s*', '', raw_text)
                    raw_text = re.sub(r'```', '', raw_text)
                    raw_text = raw_text.strip()

                    try:
                        result = json.loads(raw_text)
                        if isinstance(result, list):
                            logger.info(f"âœ“ Chunk {chunk_idx+1}: {len(result)} codes")
                            for item in result:
                                if isinstance(item, dict) and 'code' in item:
                                    code = str(item['code'])
                                    if code not in all_codes:
                                        item['message'] = str(item.get('message', code))
                                        item['cause'] = str(item.get('cause', ''))
                                        item['solution'] = str(item.get('solution', ''))
                                        item['type'] = 'Hardware'
                                        item['priorite'] = 'MOYENNE'
                                        all_codes[code] = item
                    except json.JSONDecodeError:
                        logger.warning(f"âš ï¸ Chunk {chunk_idx+1}: Parse error")

            if all_codes:
                rows = list(all_codes.values())
                logger.info(f"âœ“ IA: {len(rows)} unique codes from {len(chunks)} chunks")
                if len(rows) >= 3:
                    return rows

            logger.warning(f"âš ï¸ IA found only {len(rows)} codes, using regex fallback")

    except Exception as e:
        logger.warning(f"âš ï¸ IA extraction failed: {e}")

    # Fallback: regex-based extraction
    logger.info("ðŸ“Œ Using regex fallback")

    found_codes = set()

    # Pattern 1: Number after Alarm/ERROR keywords
    pattern1 = r'(?:Alarm|ALARM|ERROR|ERR|FAULT|CODE|code)\s+(\d{1,5})'
    matches = list(re.finditer(pattern1, text, re.IGNORECASE))
    logger.info(f"ðŸ” Pattern 1: {len(matches)} matches")

    for match in matches:
        code_num = match.group(1)
        if code_num not in found_codes:
            found_codes.add(code_num)
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 150)
            context = text[start:end].replace('\n', ' ').strip()
            rows.append({
                "code": code_num,
                "message": context[:150],
                "type": "Hardware",
                "cause": "",
                "solution": "",
                "priorite": "MOYENNE",
            })

    # Pattern 2: Letter+number codes
    pattern2 = r'\b([EHSN]\d{2,4})\b'
    matches = list(re.finditer(pattern2, text, re.IGNORECASE))
    logger.info(f"ðŸ” Pattern 2: {len(matches)} matches")

    for match in matches:
        code_num = match.group(1)
        if code_num not in found_codes:
            found_codes.add(code_num)
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 150)
            context = text[start:end].replace('\n', ' ').strip()
            rows.append({
                "code": code_num,
                "message": context[:150],
                "type": "Hardware",
                "cause": "",
                "solution": "",
                "priorite": "MOYENNE",
            })

    # Pattern 3: Hex codes
    pattern3 = r'\b(0x[0-9A-Fa-f]{2,8})\b'
    matches = list(re.finditer(pattern3, text, re.IGNORECASE))
    logger.info(f"ðŸ” Pattern 3: {len(matches)} matches")

    for match in matches:
        code_num = match.group(1)
        if code_num not in found_codes:
            found_codes.add(code_num)
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 150)
            context = text[start:end].replace('\n', ' ').strip()
            rows.append({
                "code": code_num,
                "message": context[:150],
                "type": "Hardware",
                "cause": "",
                "solution": "",
                "priorite": "MOYENNE",
            })

    logger.info(f"ðŸ“Œ Regex: {len(rows)} codes")

    if not rows:
        lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 10]
        for i, line in enumerate(lines[:50]):
            rows.append({
                "code": f"DOC-{i+1:03d}",
                "message": line[:150],
                "type": "Documentation",
                "cause": "",
                "solution": "",
                "priorite": "BASSE",
            })

    return rows



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
