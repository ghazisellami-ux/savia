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


# A Lecteur represents a customer-facing account. Internal roles are deliberately
# not client-bound because they operate SAVIA on behalf of every customer.
CLIENT_BOUND_ROLES = frozenset({"Lecteur"})
INTERNAL_WRITE_ROLES = frozenset({"Admin", "Manager", "Responsable Technique"})


def _normalise_client(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def get_client_scope(user: dict) -> str | None:
    """Return the enforced customer scope, or ``None`` for internal users.

    Client-facing accounts without an assigned client are rejected instead of
    silently receiving access to every client (the previous unsafe fallback).
    """
    if user.get("role") not in CLIENT_BOUND_ROLES:
        return None
    client = str(user.get("client") or "").strip()
    if not client:
        raise HTTPException(
            status_code=403,
            detail="Ce compte client n'est associé à aucun client actif",
        )
    return client


def resolve_client_scope(user: dict, requested_client: str | None = None) -> str | None:
    """Resolve a client filter without allowing a client account to override it."""
    scoped_client = get_client_scope(user)
    if scoped_client is None:
        return requested_client
    if requested_client and _normalise_client(requested_client) != _normalise_client(scoped_client):
        raise HTTPException(status_code=403, detail="Accès à un autre client interdit")
    return scoped_client


def assert_client_access(user: dict, resource_client: str | None) -> None:
    """Deny access when a client-bound account targets another customer's data."""
    scoped_client = get_client_scope(user)
    if scoped_client is None:
        return
    if _normalise_client(resource_client) != _normalise_client(scoped_client):
        raise HTTPException(status_code=403, detail="Accès à cette ressource interdit")


_RESOURCE_CLIENT_QUERIES = {
    "equipement": "SELECT client FROM equipements WHERE id = %s",
    "intervention": """SELECT COALESCE(NULLIF(i.client, ''), e.client, '') AS client
                         FROM interventions i
                         LEFT JOIN equipements e ON LOWER(e.nom) = LOWER(i.machine)
                         WHERE i.id = %s""",
    "contrat": "SELECT client FROM contrats WHERE id = %s",
    "demande": "SELECT client FROM demandes_intervention WHERE id = %s",
    "conformite": "SELECT client FROM conformite WHERE id = %s",
    "document_technique": """SELECT e.client FROM documents_techniques d
                              JOIN equipements e ON e.id = d.equipement_id
                              WHERE d.id = %s""",
}


def assert_resource_client_access(conn, resource_type: str, resource_id: int, user: dict) -> None:
    """Load the owning client from a fixed query and enforce customer isolation."""
    query = _RESOURCE_CLIENT_QUERIES[resource_type]
    row = conn.execute(query, (resource_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Ressource introuvable")
    assert_client_access(user, row["client"])


def assert_intervention_write_access(conn, intervention_id: int, user: dict) -> None:
    """Restrict technicians to interventions to which they are assigned."""
    assert_resource_client_access(conn, "intervention", intervention_id, user)
    if user.get("role") != "Technicien":
        return
    identities = [
        value.strip().casefold()
        for value in (user.get("nom"), user.get("sub"))
        if str(value or "").strip()
    ]
    if not identities:
        raise HTTPException(status_code=403, detail="Technicien non identifiable")
    row = conn.execute(
        """SELECT 1
           FROM interventions_techniciens it
           WHERE it.intervention_id = %s
             AND LOWER(BTRIM(it.technicien_nom)) = ANY(%s)
           UNION ALL
           SELECT 1
           FROM interventions i
           CROSS JOIN LATERAL regexp_split_to_table(COALESCE(i.technicien, ''), '\\s*,\\s*') AS assigned_name
           WHERE i.id = %s
             AND LOWER(BTRIM(assigned_name)) = ANY(%s)
           LIMIT 1""",
        (intervention_id, identities, intervention_id, identities),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Cette intervention ne vous est pas assignée")


def require_roles(user: dict, *allowed_roles: str) -> None:
    """Enforce server-side RBAC; UI visibility is never an authorization check."""
    if user.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Votre rôle n'autorise pas cette action")

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
    # Fail closed for customer-facing accounts that were created without a
    # client assignment. This applies to every business route using this
    # dependency, including routes added in the future.
    get_client_scope(payload)
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
    return role in INTERNAL_WRITE_ROLES


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
    "CLIENT_BOUND_ROLES",
    "INTERNAL_WRITE_ROLES",
    "get_client_scope",
    "resolve_client_scope",
    "assert_client_access",
    "assert_resource_client_access",
    "assert_intervention_write_access",
    "require_roles",
    "LoginRequest",
    "ChangePasswordRequest",
]
