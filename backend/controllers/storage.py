"""S3 log-removal routes."""

from api.runtime import (
    Depends,
    HTTPException,
    Query,
    app,
)
from api.security import (
    Depends,
    HTTPException,
    _verify_token,
)
from controllers.auth_dashboard import (
    Depends,
    HTTPException,
    _verify_token,
    app,
)

try:
    import s3_storage
except ImportError:
    s3_storage = None


@app.delete("/api/logs")
def api_delete_log(key: str = Query(..., description="S3 key of the log to delete"), user=Depends(_verify_token)):
    """Delete a specific log file from S3 by its key."""
    if not s3_storage:
        raise HTTPException(status_code=503, detail="S3 storage not available")
    s3_storage._init_s3()
    if not s3_storage.S3_AVAILABLE:
        raise HTTPException(status_code=503, detail="S3 storage not connected")

    success = s3_storage.delete_file(key)
    if success:
        return {"ok": True, "message": f"Log supprimé: {key}"}
    raise HTTPException(status_code=500, detail="Échec de la suppression du log")


@app.delete("/api/logs/machine/{machine_name}")
def api_delete_machine_logs(machine_name: str, user=Depends(_verify_token)):
    """Delete ALL log files for a given machine from S3."""
    if not s3_storage:
        raise HTTPException(status_code=503, detail="S3 storage not available")
    s3_storage._init_s3()
    if not s3_storage.S3_AVAILABLE:
        raise HTTPException(status_code=503, detail="S3 storage not connected")

    # Find all logs matching this machine
    all_files = s3_storage.list_files("logs/")
    machine_key = machine_name.replace(' ', '_')
    to_delete = [f for f in all_files if f"/{machine_key}/" in f["key"] or machine_key in f["key"]]

    deleted = 0
    for f in to_delete:
        if s3_storage.delete_file(f["key"]):
            deleted += 1

    return {"ok": True, "deleted": deleted, "message": f"{deleted} log(s) supprimé(s) pour {machine_name}"}




# ==========================================
# PDF REPORT GENERATION (server-side fpdf2)
# ==========================================

__all__ = [
    "api_delete_log",
    "api_delete_machine_logs",
    "s3_storage",
]

