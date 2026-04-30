import re
import logging

logger = logging.getLogger(__name__)

# Max lines to keep to avoid Gemini context limits (200K tokens is large, but 500 lines is safe)
MAX_LINES_TO_KEEP = 300

# Patterns for sensitive/useless data
PATTERNS_TO_REMOVE = [
    (r"\b([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})\b", "[MAC_ADDR]"), # MAC Addresses
    (r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", "[IP_ADDR]"), # IP Addresses
    (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "[UUID]"), # UUIDs
    (r"(?i)Serial\s*(?:Number|No)[:\s-]*[A-Z0-9]{8,}", "[SERIAL]"), # Serial numbers like Serial Number: ABC12345678
]

# Patterns for lines we want to KEEP explicitly
# e.g., Dates (2024-04-19, 19/04/2024), Times (16:38:21)
DATE_TIME_PATTERN = re.compile(r"\b(20\d{2}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]20\d{2}|\d{2}:\d{2}:\d{2})\b")
LEVEL_PATTERN = re.compile(r"(?i)\b(INFO|WARN|WARNING|ERROR|ERR|FATAL|CRITICAL|FAIL|DEBUG)\b")
ERROR_CODE_PATTERN = re.compile(r"\b(0x[0-9A-Fa-f]+|Err(?:or)?\s*\d+|Code\s*\d+)\b", re.IGNORECASE)

def clean_log_line(line: str) -> str:
    """Removes proprietary/sensitive data from a single line."""
    cleaned = line
    for pattern, replacement in PATTERNS_TO_REMOVE:
        cleaned = re.sub(pattern, replacement, cleaned)
    return cleaned

def is_line_useful(line: str) -> bool:
    """Determine if a log line is useful for diagnostic (has timestamp, severity or error code)."""
    if not line.strip():
        return False
        
    has_date_time = DATE_TIME_PATTERN.search(line)
    has_level = LEVEL_PATTERN.search(line)
    has_error_code = ERROR_CODE_PATTERN.search(line)
    
    # We consider a line useful if it looks like a standard log statement
    # or if it explicitly mentions an error.
    if has_error_code or (has_date_time and has_level):
        return True
        
    # Also keep lines that look like a stack trace or exception
    if "Exception" in line or "Traceback" in line:
        return True
        
    return False

def clean_log(content: str, max_lines: int = MAX_LINES_TO_KEEP) -> str:
    """
    Cleans a raw log string by removing noise and keeping only the most important lines,
    then truncating to max_lines to prevent API token limits.
    """
    if not content or not content.strip():
        return ""
        
    lines = content.split('\n')
    cleaned_lines = []
    
    for line in lines:
        if is_line_useful(line):
            cleaned_line = clean_log_line(line)
            cleaned_lines.append(cleaned_line)
            
    # If the user passed a log with huge amount of info, we just keep the LAST lines
    # because usually the context *leading up* to an error is at the end of the provided snippet
    if len(cleaned_lines) > max_lines:
        logger.info(f"Log pre-processor: truncating {len(cleaned_lines)} lines to {max_lines}")
        cleaned_lines = cleaned_lines[-max_lines:]
        
    return '\n'.join(cleaned_lines)
