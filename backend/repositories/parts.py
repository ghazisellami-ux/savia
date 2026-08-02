"""Spare-parts, stock-request, and stock-notification persistence."""

import pandas as pd

from database.core import _trigger_backup, get_db, logger, read_sql

__all__ = [
    "lire_pieces",
    "ajouter_piece",
    "update_stock_piece",
    "modifier_piece",
    "supprimer_piece",
    "ajouter_notification_piece",
    "lire_notifications_pieces",
    "_ensure_notifications_pieces_exists",
    "compter_notifications_non_lues",
    "marquer_notification_lue",
    "marquer_notification_traitee",
    "notifications_rupture_pour_piece",
    "ajouter_piece_demandee",
    "lire_pieces_demandees_en_attente",
    "resoudre_piece_demandee",
    "lire_toutes_pieces_demandees",
]

# ==========================================
# FONCTIONS CRUD — PIÈCES DE RECHANGE
# ==========================================

def lire_pieces():
    """Lit le stock de pièces de rechange."""
    with get_db() as conn:
        return read_sql("SELECT * FROM pieces_rechange ORDER BY designation", conn)


def ajouter_piece(piece_dict):
    """Ajoute une pièce de rechange."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO pieces_rechange (reference, designation, domaine, equipement_type, est_annexe,
                                         stock_actuel, stock_minimum, fournisseur, prix_unitaire, notes,
                                         consommation_moyenne_mois, delai_fournisseur_jours, criticite,
                                         nombre_equipements_relies, utilisation_recente_30j)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(reference) DO UPDATE SET
                domaine=excluded.domaine, equipement_type=excluded.equipement_type,
                est_annexe=excluded.est_annexe, stock_actuel=excluded.stock_actuel,
                prix_unitaire=excluded.prix_unitaire
        """, (
            piece_dict.get("reference", ""),
            piece_dict.get("designation", ""),
            piece_dict.get("domaine", "Radiologie"),
            piece_dict.get("equipement_type", ""),
            piece_dict.get("est_annexe", False),
            piece_dict.get("stock_actuel", 0),
            piece_dict.get("stock_minimum", 1),
            piece_dict.get("fournisseur", ""),
            piece_dict.get("prix_unitaire", 0.0),
            piece_dict.get("notes", ""),
            piece_dict.get("consommation_moyenne_mois", 1.0),
            piece_dict.get("delai_fournisseur_jours", 14),
            piece_dict.get("criticite", "NORMAL"),
            piece_dict.get("nombre_equipements_relies", 1),
            piece_dict.get("utilisation_recente_30j", 0),
        ))
    _trigger_backup()
    return True


def update_stock_piece(reference, nouveau_stock):
    """Met à jour le stock d'une pièce."""
    with get_db() as conn:
        conn.execute(
            "UPDATE pieces_rechange SET stock_actuel=%s WHERE reference=%s",
            (nouveau_stock, reference))
    _trigger_backup()
    return True


def modifier_piece(piece_id, piece_dict):
    """Modifie une pièce de rechange par son ID."""
    with get_db() as conn:
        conn.execute("""
            UPDATE pieces_rechange SET
                reference=%s, designation=%s, domaine=%s, equipement_type=%s, est_annexe=%s,
                stock_actuel=%s, stock_minimum=%s, fournisseur=%s,
                prix_unitaire=%s, notes=%s,
                consommation_moyenne_mois=%s, delai_fournisseur_jours=%s, criticite=%s,
                nombre_equipements_relies=%s, utilisation_recente_30j=%s
            WHERE id=%s
        """, (
            piece_dict.get("reference", ""),
            piece_dict.get("designation", ""),
            piece_dict.get("domaine", "Radiologie"),
            piece_dict.get("equipement_type", ""),
            piece_dict.get("est_annexe", False),
            piece_dict.get("stock_actuel", 0),
            piece_dict.get("stock_minimum", 1),
            piece_dict.get("fournisseur", ""),
            piece_dict.get("prix_unitaire", 0.0),
            piece_dict.get("notes", ""),
            piece_dict.get("consommation_moyenne_mois", 1.0),
            piece_dict.get("delai_fournisseur_jours", 14),
            piece_dict.get("criticite", "NORMAL"),
            piece_dict.get("nombre_equipements_relies", 1),
            piece_dict.get("utilisation_recente_30j", 0),
            piece_id,
        ))
    _trigger_backup()
    return True


def supprimer_piece(piece_id):
    """Supprime une pièce de rechange par son ID."""
    with get_db() as conn:
        conn.execute("DELETE FROM pieces_rechange WHERE id=%s", (piece_id,))
    _trigger_backup()
    return True


# ==========================================
# FONCTIONS CRUD — NOTIFICATIONS PIÈCES
# ==========================================

def ajouter_notification_piece(notif_dict):
    """Ajoute une notification pièce (rupture ou arrivée)."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO notifications_pieces
            (type, intervention_id, piece_reference, piece_nom, intervention_ref,
             equipement, client, technicien, message, source, destination, statut)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'non_lu')
        """, (
            notif_dict.get("type", ""),
            notif_dict.get("intervention_id"),
            notif_dict.get("piece_reference", ""),
            notif_dict.get("piece_nom", ""),
            notif_dict.get("intervention_ref", ""),
            notif_dict.get("equipement", ""),
            notif_dict.get("client", ""),
            notif_dict.get("technicien", ""),
            notif_dict.get("message", ""),
            notif_dict.get("source", ""),
            notif_dict.get("destination", ""),
        ))
    return True


def lire_notifications_pieces(destination=None, statut=None, technicien=None):
    """Lit les notifications pièces, filtrées par destination, statut et/ou technicien."""
    _ensure_notifications_pieces_exists()
    query = "SELECT * FROM notifications_pieces WHERE 1=1"
    params = []
    if destination:
        query += " AND destination = %s"
        params.append(destination)
    if statut:
        query += " AND statut = %s"
        params.append(statut)
    if technicien:
        query += " AND LOWER(technicien) LIKE LOWER(%s)"
        params.append(f"%{technicien}%")
    query += " ORDER BY date_creation DESC LIMIT 200"
    with get_db() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def _ensure_notifications_pieces_exists():
    """Crée la table notifications_pieces si elle n'existe pas (defensive initialization)."""
    with get_db() as conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'notifications_pieces'
            """)
            if not cur.fetchone():
                # Table doesn't exist, create it
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS notifications_pieces (
                        id SERIAL PRIMARY KEY,
                        type TEXT NOT NULL,
                        intervention_id INTEGER,
                        piece_reference TEXT,
                        piece_nom TEXT,
                        intervention_ref TEXT,
                        equipement TEXT,
                        client TEXT,
                        technicien TEXT,
                        message TEXT,
                        source TEXT NOT NULL DEFAULT '',
                        destination TEXT NOT NULL,
                        statut TEXT DEFAULT 'non_lu',
                        date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        date_lecture TIMESTAMP,
                        date_traitement TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info("⚠️  Table notifications_pieces created dynamically (defensive)")
        except Exception as e:
            logger.debug(f"_ensure_notifications_pieces_exists: {e}")


def compter_notifications_non_lues(destination, technicien=None):
    """Compte les notifications non lues pour une destination (et optionnellement un technicien)."""
    _ensure_notifications_pieces_exists()
    query = "SELECT COUNT(*) as cnt FROM notifications_pieces WHERE destination = %s AND statut = 'non_lu'"
    params = [destination]
    if technicien:
        query += " AND LOWER(technicien) LIKE LOWER(%s)"
        params.append(f"%{technicien}%")
    with get_db() as conn:
        row = conn.execute(query, tuple(params)).fetchone()
        return int(row["cnt"]) if row else 0


def marquer_notification_lue(notif_id):
    """Marque une notification comme lue."""
    with get_db() as conn:
        conn.execute(
            "UPDATE notifications_pieces SET statut = 'lu', date_lecture = CURRENT_TIMESTAMP WHERE id = %s",
            (notif_id,)
        )
    return True


def marquer_notification_traitee(notif_id):
    """Marque une notification comme traitée."""
    with get_db() as conn:
        conn.execute(
            "UPDATE notifications_pieces SET statut = 'traite', date_traitement = CURRENT_TIMESTAMP WHERE id = %s",
            (notif_id,)
        )
    return True


def notifications_rupture_pour_piece(piece_reference):
    """Retourne les notifications de rupture non traitées pour une pièce donnée."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM notifications_pieces WHERE type = 'piece_rupture' AND piece_reference = %s AND statut != 'traite'",
            (piece_reference,),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


# ==========================================
# FONCTIONS CRUD — PIÈCES DEMANDÉES (NON RÉFÉRENCÉES)
# ==========================================

def ajouter_piece_demandee(demande_dict):
    """Ajoute une demande de pièce non référencée."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO pieces_demandees
            (reference, designation, intervention_id, equipement, client, technicien, probleme, statut)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'en_attente')
        """, (
            demande_dict.get("reference", ""),
            demande_dict.get("designation", ""),
            demande_dict.get("intervention_id"),
            demande_dict.get("equipement", ""),
            demande_dict.get("client", ""),
            demande_dict.get("technicien", ""),
            demande_dict.get("probleme", ""),
        ))
    return True


def lire_pieces_demandees_en_attente(reference=None):
    """Lit les demandes de pièces en attente, optionnellement filtrées par référence (ILIKE)."""
    query = "SELECT * FROM pieces_demandees WHERE statut = 'en_attente'"
    params = []
    if reference:
        query += " AND LOWER(reference) = LOWER(%s)"
        params.append(reference)
    query += " ORDER BY date_creation DESC"
    with get_db() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def resoudre_piece_demandee(demande_id):
    """Marque une demande de pièce comme disponible."""
    with get_db() as conn:
        conn.execute(
            "UPDATE pieces_demandees SET statut = 'disponible', date_resolution = CURRENT_TIMESTAMP WHERE id = %s",
            (demande_id,)
        )
    return True


def lire_toutes_pieces_demandees(statut=None):
    """Lit toutes les demandes de pièces, optionnellement filtrées par statut."""
    query = "SELECT * FROM pieces_demandees WHERE 1=1"
    params = []
    if statut:
        query += " AND statut = %s"
        params.append(statut)
    query += " ORDER BY date_creation DESC"
    with get_db() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return pd.DataFrame([dict(row) for row in rows])
