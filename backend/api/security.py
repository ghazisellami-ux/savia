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
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")


def _authenticated_user(credentials: Optional[HTTPAuthorizationCredentials]) -> dict:
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentification requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_token(credentials.credentials)
    with get_db() as conn:
        row = conn.execute(
            """SELECT username, role, nom_complet, client, pages_autorisees, actif,
                      password_version, must_change_password
               FROM utilisateurs WHERE username = %s""",
            (payload.get("sub", ""),),
        ).fetchone()
    if not row or not row["actif"]:
        raise HTTPException(status_code=401, detail="Compte indisponible")
    if payload.get("pv") != row["password_version"]:
        raise HTTPException(status_code=401, detail="Session révoquée : reconnectez-vous")

    payload.update({
        "role": row["role"],
        "nom": row["nom_complet"] or "",
        "client": row["client"] or "",
        "pages_autorisees": row["pages_autorisees"] or "",
        "password_change_required": bool(row["must_change_password"]),
    })
    return payload


def _verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    """Require a valid Bearer JWT for every protected business route."""
    payload = _authenticated_user(credentials)
    if payload["password_change_required"]:
        raise HTTPException(
            status_code=403,
            detail="Changement de mot de passe obligatoire avant de continuer",
        )
    return payload


def _verify_password_change_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    """Allow only the password-change flow for a session requiring rotation."""
    return _authenticated_user(credentials)


def validate_password_policy(password: str, username: str = "") -> None:
    if not isinstance(password, str) or len(password) < 12 or len(password.encode("utf-8")) > 72:
        raise ValueError("Le mot de passe doit contenir au moins 12 caractères")
    if not all((any(c.islower() for c in password), any(c.isupper() for c in password), any(c.isdigit() for c in password))):
        raise ValueError("Le mot de passe doit contenir une minuscule, une majuscule et un chiffre")
    if username and username.casefold() in password.casefold():
        raise ValueError("Le mot de passe ne doit pas contenir le nom d'utilisateur")


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


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=72)

__all__ = [
    "_verify_token",
    "_verify_password_change_token",
    "_verify_password",
    "validate_password_policy",
    "_check_create_permission",
    "_check_create_demande_permission",
    "_check_create_piece_permission",
    "LoginRequest",
    "ChangePasswordRequest",
]
