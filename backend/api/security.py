"""Authentication dependencies and creation-permission policies."""

from api.runtime import (
    BaseModel,
    Depends,
    HTTPAuthorizationCredentials,
    HTTPException,
    JWT_ISSUER,
    JWT_SECRET,
    Optional,
    bcrypt,
    get_db,
    jwt,
    security,
)
from pydantic import Field

def _decode_token(token: str) -> dict:
    """Decode a JWT and return its authenticated user payload."""
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            options={"require": ["sub", "role", "iss", "iat", "nbf", "exp"]},
        )
        # Rétrocompatibilité : si Lecteur mais client absent du token, le récupérer en DB
        if payload.get("role") == "Lecteur" and not payload.get("client"):
            try:
                with get_db() as conn:
                    row = conn.execute(
                        "SELECT client FROM utilisateurs WHERE username = %s",
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


def _verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    """Require a valid Bearer JWT for every protected business route."""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentification requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token(credentials.credentials)


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
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

__all__ = [
    "_verify_token",
    "_verify_password",
    "_check_create_permission",
    "_check_create_demande_permission",
    "_check_create_piece_permission",
    "LoginRequest",
]
