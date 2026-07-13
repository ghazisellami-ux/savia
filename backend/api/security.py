"""Authentication dependencies and creation-permission policies."""

from api.runtime import (
    BaseModel,
    Depends,
    HTTPAuthorizationCredentials,
    HTTPException,
    JWT_SECRET,
    Optional,
    bcrypt,
    get_db,
    jwt,
    security,
)

def _verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT and return user payload. Returns guest user if no token (allows public read)."""
    if not credentials:
        return {"sub": "guest", "role": "Lecteur", "nom": "Visiteur"}
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        # Rétrocompatibilité : si Lecteur mais client absent du token, le récupérer en DB
        if payload.get("role") == "Lecteur" and not payload.get("client"):
            try:
                with get_db() as conn:
                    row = conn.execute(
                        "SELECT client FROM utilisateurs WHERE username = ?",
                        (payload.get("sub", ""),)
                    ).fetchone()
                    if row and row["client"]:
                        payload["client"] = row["client"]
            except Exception:
                pass
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")



def _optional_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[dict]:
    """Verify JWT if present, return None if missing (allows public read access)."""
    if not credentials:
        return None
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _check_create_permission(user: dict) -> bool:
    """
    Vérifier si l'utilisateur a le droit de créer des clients, équipements, ou demandes (sauf Lecteur).
    Autorisé pour: Admin, Manager, Responsable Technique
    """
    role = user.get("role", "")
    allowed_roles = ["Admin", "Manager", "Responsable Technique"]
    return role in allowed_roles


def _check_create_demande_permission(user: dict) -> bool:
    """
    Vérifier si l'utilisateur a le droit de créer une demande d'intervention.
    Autorisé pour: Admin, Manager, Responsable Technique, Lecteur (clients)
    """
    role = user.get("role", "")
    allowed_roles = ["Admin", "Manager", "Responsable Technique", "Lecteur"]
    return role in allowed_roles


def _check_create_piece_permission(user: dict) -> bool:
    """
    Vérifier si l'utilisateur a le droit de créer des pièces de rechange.
    Autorisé pour: Admin, Manager, Responsable Technique, Gestionnaire de stock, Gestionnaire
    """
    role = user.get("role", "")
    allowed_roles = ["Admin", "Manager", "Responsable Technique", "Gestionnaire de stock", "Gestionnaire"]
    return role in allowed_roles


# ==========================================
# AUTH
# ==========================================

class LoginRequest(BaseModel):
    username: str
    password: str

__all__ = [
    "_verify_token",
    "_optional_token",
    "_verify_password",
    "_check_create_permission",
    "_check_create_demande_permission",
    "_check_create_piece_permission",
    "LoginRequest",
]

