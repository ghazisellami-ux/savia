"""Automatic equipment status transitions driven by intervention lifecycle."""

from typing import Any


EQUIPMENT_OPERATIONAL = "Opérationnel"
EQUIPMENT_MAINTENANCE = "En maintenance"
EQUIPMENT_WORKSHOP = "En atelier"
EQUIPMENT_OUT_OF_SERVICE = "Hors Service"

WORKSHOP_TRANSFER_STATUS = "Transfert vers l'atelier"

# An intervention waiting for a part is still active from the equipment's
# point of view: it must not become operational before the intervention is
# actually closed.
ACTIVE_INTERVENTION_STATUSES = (
    "En cours",
    WORKSHOP_TRANSFER_STATUS,
    "En attente de piece",
    "En attente de pièce",
    "En attente de piÃ¨ce",
)


CLOSED_INTERVENTION_STATUSES = (
    "Cloturee",
    "ClÃ´turÃ©e",
    "ClÃƒÂ´turÃƒÂ©e",
    "TerminÃ©e",
    "TerminÃƒÂ©e",
)


def _is_out_of_service(status: Any) -> bool:
    """Return True for all historical spellings of the manual status."""
    value = str(status or "").strip().casefold()
    return value in {"hors service", "hors-service"}


def _equipment_rows(conn, machine: str, client: str):
    """Find the equipment targeted by an intervention.

    Equipment names are not globally unique, so a client is used whenever it
    is available. If a legacy intervention has no client and the name is
    duplicated, no automatic update is performed rather than risking a
    cross-client status change.
    """
    rows = conn.execute(
        """
        SELECT id, statut, client
        FROM equipements
        WHERE LOWER(nom) = LOWER(%s)
          AND (%s = '' OR LOWER(COALESCE(client, '')) = LOWER(%s))
        ORDER BY id
        FOR UPDATE
        """,
        (machine, client, client),
    ).fetchall()
    if not client and len(rows) != 1:
        return []
    return rows


def _has_other_active_intervention(conn, intervention_id: int, machine: str, equipment_id: int, client: str) -> bool:
    placeholders = ", ".join(["%s"] * len(ACTIVE_INTERVENTION_STATUSES))
    row = conn.execute(
        f"""
        SELECT 1
        FROM interventions i
        LEFT JOIN equipements e ON e.id = %s
        WHERE i.id <> %s
          AND LOWER(i.machine) = LOWER(%s)
          AND i.statut IN ({placeholders})
          AND (
                %s <> ''
                AND LOWER(COALESCE(NULLIF(i.client, ''), e.client, '')) = LOWER(%s)
              OR %s = ''
          )
        LIMIT 1
        """,
        (equipment_id, intervention_id, machine, *ACTIVE_INTERVENTION_STATUSES, client, client, client),
    ).fetchone()
    return bool(row)


def calculer_nouveau_statut_equipement(
    current_status: Any,
    intervention_status: str,
    has_other_active_intervention: bool = False,
) -> str:
    """Pure transition rule used by the database synchronizer and tests."""
    if _is_out_of_service(current_status):
        return str(current_status or EQUIPMENT_OUT_OF_SERVICE)
    if intervention_status == WORKSHOP_TRANSFER_STATUS:
        return EQUIPMENT_WORKSHOP
    if intervention_status in ACTIVE_INTERVENTION_STATUSES:
        return EQUIPMENT_MAINTENANCE
    if intervention_status in CLOSED_INTERVENTION_STATUSES:
        return EQUIPMENT_MAINTENANCE if has_other_active_intervention else EQUIPMENT_OPERATIONAL
    return str(current_status or EQUIPMENT_OPERATIONAL)


def enregistrer_historique_statut_equipement(
    conn,
    equipment_id: int,
    ancien_statut: str,
    nouveau_statut: str,
    *,
    source: str,
    intervention_id: int | None = None,
    raison: str = "",
    change_par: str = "",
) -> None:
    """Persist one auditable equipment status transition."""
    conn.execute(
        """INSERT INTO equipement_statut_historique
           (equipement_id, ancien_statut, nouveau_statut, source,
            intervention_id, raison, change_par)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (equipment_id, ancien_statut or "", nouveau_statut, source,
         intervention_id, raison or "", change_par or ""),
    )


def synchroniser_statut_equipement(conn, intervention_id: int, intervention_status: str) -> None:
    """Apply the equipment transition associated with an intervention event.

    The manual ``Hors Service`` status always wins. An equipment becomes
    ``En maintenance`` when an intervention starts, and returns to
    ``Opérationnel`` only when that intervention is closed and no other active
    intervention remains for the same equipment.

    This function deliberately receives an existing DB connection so the
    intervention and equipment updates commit atomically.
    """
    status = str(intervention_status or "").strip()
    if status not in {"En cours", "Cloturee", "Clôturée", "ClÃ´turÃ©e", "Terminée", "TerminÃ©e"} and status not in ACTIVE_INTERVENTION_STATUSES:
        return

    intervention = conn.execute(
        "SELECT machine, COALESCE(client, '') AS client FROM interventions WHERE id = %s",
        (intervention_id,),
    ).fetchone()
    if not intervention:
        return

    machine = str(intervention.get("machine") or "").strip()
    client = str(intervention.get("client") or "").strip()
    if not machine:
        return

    for equipment in _equipment_rows(conn, machine, client):
        equipment_id = equipment["id"]
        current_status = equipment.get("statut") or ""
        if _is_out_of_service(current_status):
            continue

        if status == WORKSHOP_TRANSFER_STATUS:
            next_status = EQUIPMENT_WORKSHOP
        elif status in ACTIVE_INTERVENTION_STATUSES:
            next_status = EQUIPMENT_MAINTENANCE
        elif status in {"Cloturee", "Clôturée", "ClÃ´turÃ©e", "Terminée", "TerminÃ©e"}:
            effective_client = client or str(equipment.get("client") or "").strip()
            if _has_other_active_intervention(conn, intervention_id, machine, equipment_id, effective_client):
                next_status = EQUIPMENT_MAINTENANCE
            else:
                next_status = EQUIPMENT_OPERATIONAL
        else:
            # Assignment/refusal does not change equipment availability. An
            # already active intervention remains in maintenance until close.
            continue

        if current_status != next_status:
            conn.execute(
                "UPDATE equipements SET statut = %s WHERE id = %s",
                (next_status, equipment_id),
            )
            enregistrer_historique_statut_equipement(
                conn,
                equipment_id,
                current_status,
                next_status,
                source="intervention",
                intervention_id=intervention_id,
            )


def reconcilier_statuts_equipements() -> int:
    """Reconcile automatic equipment statuses with active interventions.

    Intervention events normally keep this state synchronized. This defensive
    pass repairs legacy rows or events that were closed before the equipment
    link was available, while preserving manual ``Hors Service`` and
    ``En atelier`` statuses.
    """
    from database.core import get_db

    changed = 0
    with get_db() as conn:
        equipments = conn.execute(
            "SELECT id, nom, client, statut FROM equipements ORDER BY id"
        ).fetchall()
        placeholders = ", ".join(["%s"] * len(ACTIVE_INTERVENTION_STATUSES))

        for equipment in equipments:
            current_status = str(equipment.get("statut") or "").strip()
            if _is_out_of_service(current_status) or current_status == "En atelier":
                continue

            machine = str(equipment.get("nom") or "").strip()
            client = str(equipment.get("client") or "").strip()
            if not machine:
                continue

            active = conn.execute(
                f"""
                SELECT 1
                FROM interventions i
                WHERE LOWER(i.machine) = LOWER(%s)
                  AND i.statut IN ({placeholders})
                  AND LOWER(COALESCE(NULLIF(i.client, ''), %s)) = LOWER(%s)
                LIMIT 1
                """,
                (machine, *ACTIVE_INTERVENTION_STATUSES, client, client),
            ).fetchone()

            has_active_intervention = bool(active)
            is_automatic_status = current_status in {
                "", "Actif", EQUIPMENT_OPERATIONAL, EQUIPMENT_MAINTENANCE
            }
            if not is_automatic_status:
                continue

            next_status = (
                EQUIPMENT_MAINTENANCE if has_active_intervention
                else EQUIPMENT_OPERATIONAL
            )
            if current_status == next_status:
                continue

            conn.execute(
                "UPDATE equipements SET statut = %s WHERE id = %s",
                (next_status, equipment["id"]),
            )
            enregistrer_historique_statut_equipement(
                conn,
                equipment["id"],
                current_status,
                next_status,
                source="reconciliation",
                raison=(
                    "Aucune intervention active restante"
                    if not has_active_intervention
                    else "Intervention active détectée"
                ),
            )
            changed += 1

    return changed


__all__ = [
    "EQUIPMENT_OPERATIONAL",
    "EQUIPMENT_MAINTENANCE",
    "EQUIPMENT_WORKSHOP",
    "EQUIPMENT_OUT_OF_SERVICE",
    "WORKSHOP_TRANSFER_STATUS",
    "calculer_nouveau_statut_equipement",
    "enregistrer_historique_statut_equipement",
    "reconcilier_statuts_equipements",
    "synchroniser_statut_equipement",
]
