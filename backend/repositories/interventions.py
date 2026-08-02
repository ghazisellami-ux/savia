"""Intervention and maintenance-planning persistence."""

from datetime import datetime

from database.core import (
    _fill_missing_cout_pieces,
    _trigger_backup,
    get_db,
    read_sql,
)
from repositories.knowledge import _fix_df_text
from repositories.equipment_status import synchroniser_statut_equipement

__all__ = [
    "lire_interventions",
    "ajouter_intervention",
    "lire_planning",
    "ajouter_planning",
    "update_planning_statut",
    "supprimer_planning",
    "reprogrammer_planning",
]

# ==========================================
# FONCTIONS CRUD — INTERVENTIONS
# ==========================================

def lire_interventions(machine=None):
    """Lit les interventions, optionnellement filtrées par machine. Inclut le client via JOIN.
    Note: fiche_photo_data (BYTEA) est exclu intentionnellement pour éviter les erreurs de sérialisation JSON.
    Utiliser GET /api/interventions/{id}/fiche pour télécharger la photo."""
    with get_db() as conn:
        # Use JOIN instead of subquery to avoid N+1 pattern
        # Select only necessary columns to reduce data transfer
        # Note: start_time, end_time are TIME columns for shift tracking
        base_query = """
            SELECT i.id, i.date, i.machine, i.technicien, i.type_intervention,
                   i.description, i.probleme, i.cause, i.solution,
                   i.pieces_utilisees, i.cout, i.cout_pieces, i.duree_minutes,
                   i.duree_deplacement,
                   i.code_erreur, i.statut, i.notes,
                   i.date_debut_intervention, i.date_cloture,
                   i.type_erreur, i.priorite,
                   i.start_time, i.end_time, i.planning_id,
                   COALESCE(i.fiche_photo_nom, '') AS fiche_photo_nom,
                   COALESCE(i.fiche_validation, 'En attente') AS fiche_validation,
                   (NULLIF(i.fiche_storage_key, '') IS NOT NULL OR
                    (i.fiche_photo_data IS NOT NULL AND octet_length(i.fiche_photo_data) > 0)) AS has_fiche,
                   COALESCE(NULLIF(i.client, ''), e.client, '') AS client
            FROM interventions i
            LEFT JOIN equipements e ON LOWER(e.nom) = LOWER(i.machine)
            WHERE i.is_temporary = 0
        """
        if machine:
            df = read_sql(
                base_query + " AND i.machine = %s ORDER BY i.date DESC",
                conn, params=(machine,))
        else:
            df = read_sql(base_query + " ORDER BY i.date DESC", conn)
        df = _fill_missing_cout_pieces(df, conn)

    
    # Only apply text fixes to text columns that need it
    text_columns = ["machine", "description", "probleme", "cause", "solution", "notes", "client"]
    if not df.empty:
        df = _fix_df_text(df, columns=text_columns)
    
    # Fill remaining NaN with empty string
    if "client" in df.columns:
        df["client"] = df["client"].fillna("")
    
    # Normaliser le statut
    if not df.empty and "statut" in df.columns:
        df["statut"] = df["statut"].apply(
            lambda s: "Cloturee" if "tur" in str(s).lower() else str(s)
        )
    
    # Convert technicien username to full name (nom + prenom) if it looks like a username
    # BUT: Cache the lookups to avoid N+1 queries
    if not df.empty and "technicien" in df.columns:
        tech_cache = {}
        
        def convert_technicien(tech_str):
            if not tech_str or not isinstance(tech_str, str):
                return tech_str
            
            # Check cache first
            if tech_str in tech_cache:
                return tech_cache[tech_str]
            
            # Try to get full name from techniciens table
            try:
                with get_db() as conn:
                    row = conn.execute(
                        "SELECT nom, prenom FROM techniciens WHERE username = %s",
                        (tech_str,)
                    ).fetchone()
                    if row:
                        nom = row.get("nom", "").strip() if hasattr(row, 'get') else (row[0] or "").strip()
                        prenom = row.get("prenom", "").strip() if hasattr(row, 'get') else (row[1] or "").strip()
                        result = f"{prenom} {nom}".strip() if prenom else nom
                        tech_cache[tech_str] = result
                        return result
            except Exception:
                pass
            
            tech_cache[tech_str] = tech_str
            return tech_str
        
        df["technicien"] = df["technicien"].apply(convert_technicien)
    
    return df



def ajouter_intervention(intervention_dict):
    """Ajoute une intervention."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO interventions (date, machine, technicien, type_intervention,
                                       description, probleme, cause, solution,
                                       pieces_utilisees, cout, cout_pieces, duree_minutes,
                                       code_erreur, statut, notes, type_erreur, priorite,
                                       duree_deplacement, start_time, end_time, fiche_validation, client)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            intervention_dict.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            intervention_dict.get("machine") or "",
            intervention_dict.get("technicien") or "",
            intervention_dict.get("type_intervention", "Corrective"),
            intervention_dict.get("description") or "",
            intervention_dict.get("probleme") or "",
            intervention_dict.get("cause") or "",
            intervention_dict.get("solution") or "",
            intervention_dict.get("pieces_utilisees") or "",
            intervention_dict.get("cout", 0.0),
            intervention_dict.get("cout_pieces", 0.0),
            intervention_dict.get("duree_minutes", 0),
            intervention_dict.get("code_erreur") or "",
            intervention_dict.get("statut", "Assignée"),
            intervention_dict.get("notes") or "",
            intervention_dict.get("type_erreur") or "",
            intervention_dict.get("priorite") or "",
            intervention_dict.get("duree_deplacement", 0),
            intervention_dict.get("start_time") or None,
            intervention_dict.get("end_time") or None,
            intervention_dict.get("fiche_validation", "En attente"),
            intervention_dict.get("client") or "",
        ))
        new_intervention = conn.execute(
            "SELECT id FROM interventions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if new_intervention:
            synchroniser_statut_equipement(
                conn,
                new_intervention["id"],
                intervention_dict.get("statut", "Assignée"),
            )
    _trigger_backup()
    return True


# ==========================================
# FONCTIONS CRUD — PLANNING MAINTENANCE
# ==========================================

def lire_planning(machine=None, statut=None, region=None, ville=None):
    """Lit le planning de maintenance avec filtres optionnels."""
    query = "SELECT * FROM planning_maintenance WHERE 1=1"
    params = []
    if machine:
        query += " AND machine = %s"
        params.append(machine)
    if statut:
        query += " AND statut = %s"
        params.append(statut)
    query += " ORDER BY date_prevue ASC"

    with get_db() as conn:
        df = read_sql(query, conn, params=params)

        # A rescheduled maintenance keeps a historical ghost row at its
        # original date. Once the linked maintenance is closed, expose that
        # history as closed too, including rows created before this sync fix.
        if not df.empty and {"is_ghost", "original_planning_id"}.issubset(df.columns):
            closed_rows = conn.execute(
                """
                SELECT id AS planning_id
                FROM planning_maintenance
                WHERE statut IN ('Cloturee', 'Réalisée', 'Terminée', 'Annulée')
                UNION
                SELECT DISTINCT planning_id
                FROM interventions
                WHERE planning_id IS NOT NULL
                  AND statut IN ('Cloturee', 'Clôturée', 'Terminée', 'Annulée')
                """
            ).fetchall()
            closed_ids = {
                row.get("planning_id")
                for row in closed_rows
                if row.get("planning_id") is not None
            }
            if closed_ids:
                planning_mask = df["id"].isin(closed_ids)
                df.loc[planning_mask, "statut"] = "Cloturee"

            # The original-date ghost is an immutable visual reference for
            # the delay and must remain grey after the real intervention is
            # closed.
            ghost_mask = df["is_ghost"].fillna(False).astype(bool)
            df.loc[ghost_mask, "statut"] = "Décalé"
    
    # Apply region and ville filters if provided
    if (region or ville) and not df.empty:
        # Get clients with their region/ville info
        with get_db() as conn:
            clients_df = read_sql(
                "SELECT nom, region, ville FROM clients WHERE 1=1",
                conn
            )
        
        if not clients_df.empty:
            # Create a mapping of client name to region/ville
            client_info = {}
            for _, row in clients_df.iterrows():
                client_name = str(row.get('nom', '')).lower()
                client_info[client_name] = {
                    'region': str(row.get('region', '')).lower(),
                    'ville': str(row.get('ville', '')).lower()
                }
            
            # Filter planning by region/ville
            def matches_filters(client_name):
                if not client_name:
                    return False
                client_lower = str(client_name).lower()
                info = client_info.get(client_lower, {})
                
                if region and region.lower() != 'tous':
                    if info.get('region', '').lower() != region.lower():
                        return False
                if ville and ville.lower() != 'tous':
                    if info.get('ville', '').lower() != ville.lower():
                        return False
                return True
            
            if 'client' in df.columns:
                df = df[df['client'].apply(matches_filters)]
    
    # Convert technicien_assigne username to full name
    if not df.empty and "technicien_assigne" in df.columns:
        def convert_technicien(tech_str):
            if not tech_str or not isinstance(tech_str, str):
                return tech_str
            try:
                with get_db() as conn:
                    row = conn.execute(
                        "SELECT nom, prenom FROM techniciens WHERE username = %s",
                        (tech_str,)
                    ).fetchone()
                    if row:
                        nom = row.get("nom", "").strip() if hasattr(row, 'get') else (row[0] or "").strip()
                        prenom = row.get("prenom", "").strip() if hasattr(row, 'get') else (row[1] or "").strip()
                        return f"{prenom} {nom}".strip() if prenom else nom
            except Exception:
                pass
            return tech_str
        
        df["technicien_assigne"] = df["technicien_assigne"].apply(convert_technicien)
    
    return df


def ajouter_planning(planning_dict):
    """Ajoute une maintenance planifiée."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO planning_maintenance (machine, client, type_maintenance, description,
                                              date_prevue, technicien_assigne, recurrence, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            planning_dict.get("machine", ""),
            planning_dict.get("client", ""),
            planning_dict.get("type_maintenance", "Préventive"),
            planning_dict.get("description", ""),
            planning_dict.get("date_prevue", ""),
            planning_dict.get("technicien_assigne", ""),
            planning_dict.get("recurrence", ""),
            planning_dict.get("notes", ""),
        ))
    _trigger_backup()
    return True


def update_planning_statut(planning_id, statut, date_realisee=None):
    """Met à jour le statut d'une maintenance planifiée."""
    with get_db() as conn:
        if date_realisee:
            conn.execute(
                "UPDATE planning_maintenance SET statut=%s, date_realisee=%s WHERE id=%s",
                (statut, date_realisee, planning_id))
        else:
            conn.execute(
                "UPDATE planning_maintenance SET statut=%s WHERE id=%s",
                (statut, planning_id))
    _trigger_backup()
    return True


# ==========================================
# SUPPRIMER PLANNING
# ==========================================

def supprimer_planning(planning_id):
    """Supprime une maintenance planifiée."""
    with get_db() as conn:
        conn.execute("DELETE FROM planning_maintenance WHERE id=%s", (planning_id,))
    _trigger_backup()
    return True


def reprogrammer_planning(planning_id, nouvelle_date):
    """Reprogramme une maintenance à une nouvelle date et remet le statut à Planifiée."""
    with get_db() as conn:
        conn.execute(
            "UPDATE planning_maintenance SET date_prevue=%s, statut='Planifiée' WHERE id=%s",
            (nouvelle_date, planning_id))
    _trigger_backup()
    return True
