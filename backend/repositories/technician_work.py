"""Multi-technician intervention work and consolidation persistence."""

import json
from datetime import datetime

from database.core import _trigger_backup, get_db, logger, read_sql
from repositories.knowledge import _fix_df_text
from repositories.equipment_status import retour_site_confirmation_requise, synchroniser_statut_equipement
from services.contract_billing import assess_intervention_contract_coverage_in_savepoint

__all__ = [
    "get_or_create_interventions_techniciens",
    "update_interventions_techniciens",
    "get_interventions_techniciens",
    "all_techniciens_completed",
    "calculate_intervention_totals",
    "consolidate_technician_duplicates",
    "get_techniciens_status",
    "get_child_interventions",
    "lire_child_interventions_for_technician",
    "finalize_intervention_from_techniciens",
]

# ==========================================
# INTERVENTIONS_TECHNICIENS — Per-Technician Tracking
# ==========================================

def _ensure_workshop_transfer_status_constraint(conn):
    """Repair legacy status checks before a technician status update.

    This is also executed at request time because some deployments keep a
    long-running API process while the database schema is upgraded. Without
    this guard, an older column-level CHECK rejects the workshop value and
    the whole PWA request returns HTTP 500.
    """
    # These fields were added after the original multi-tech table. Ensure
    # legacy databases can persist the complete PWA payload as well as its
    # status, instead of failing with an undefined-column 500.
    conn.execute(
        "ALTER TABLE interventions_techniciens ADD COLUMN IF NOT EXISTS type_erreur_tech TEXT DEFAULT ''"
    )
    conn.execute(
        "ALTER TABLE interventions_techniciens ADD COLUMN IF NOT EXISTS pieces_a_deduire TEXT DEFAULT ''"
    )

    rows = conn.execute(
        """SELECT c.conname, pg_get_constraintdef(c.oid) AS definition
           FROM pg_constraint c
           JOIN pg_class t ON t.oid = c.conrelid
           WHERE t.oid = 'interventions_techniciens'::regclass
             AND c.contype = 'c'
             AND pg_get_constraintdef(c.oid) ILIKE '%statut%'"""
    ).fetchall()
    if any(
        "Transfert vers l'atelier" in str(row.get("definition", "")).replace("''", "'")
        for row in rows
    ):
        return

    for row in rows:
        constraint_name = row.get("conname")
        if constraint_name:
            conn.execute(
                f'ALTER TABLE interventions_techniciens DROP CONSTRAINT IF EXISTS "{constraint_name}"'
            )
    conn.execute(
        """ALTER TABLE interventions_techniciens
           ADD CONSTRAINT interventions_techniciens_statut_check
           CHECK (statut IN ('Assigné', 'En cours', 'Transfert vers l''atelier',
                             'Cloturee', 'Refusé', 'En attente de piece',
                             'En attente de pièce'))"""
    )

def get_or_create_interventions_techniciens(intervention_id, technicien_nom):
    """
    Récupère ou crée un enregistrement interventions_techniciens pour un technicien.
    Uses robust name matching to handle reversed name orders (e.g., "Ghazi Sellami" vs "Sellami Ghazi").
    
    Args:
        intervention_id: ID de l'intervention
        technicien_nom: Nom complet du technicien (e.g., "Jean Dupont")
    
    Returns:
        dict: Enregistrement with id, intervention_id, technicien_nom, statut, etc.
    """
    def names_match(name1, name2):
        """Check if two names refer to the same person (handles reversed order)"""
        if not name1 or not name2:
            return False
        
        n1 = str(name1).lower().strip()
        n2 = str(name2).lower().strip()
        
        # Exact match
        if n1 == n2:
            return True
        
        # Split into words (>1 char)
        words1 = [w for w in n1.split() if len(w) > 1]
        words2 = [w for w in n2.split() if len(w) > 1]
        
        if not words1 or not words2:
            return False
        
        # Check if all words match (handles reversed order)
        return (all(w in words2 for w in words1) and 
                all(w in words1 for w in words2))
    
    # Use correct placeholder based on database type
    ph = "%s"
    
    with get_db() as conn:
        # Get ALL records for this intervention
        rows = conn.execute(f"""
            SELECT * FROM interventions_techniciens 
            WHERE intervention_id = {ph}
        """, (intervention_id,)).fetchall()
        
        # Check if entry exists (using robust name matching)
        for row in rows:
            if names_match(row['technicien_nom'], technicien_nom):
                return dict(row)
        
        # Create new entry if not found
        conn.execute(f"""
            INSERT INTO interventions_techniciens 
            (intervention_id, technicien_nom, statut)
            VALUES ({ph}, {ph}, 'Assigné')
        """, (intervention_id, technicien_nom))
        
        # Fetch and return the new entry
        row = conn.execute(f"""
            SELECT * FROM interventions_techniciens 
            WHERE intervention_id = {ph} AND technicien_nom = {ph}
        """, (intervention_id, technicien_nom)).fetchone()
        
        _trigger_backup()
        return dict(row) if row else None


def update_interventions_techniciens(intervention_id, technicien_nom, data):
    """
    Met à jour les données per-technician pour une intervention.
    Now uses ID-based lookup instead of name matching for reliability.
    
    Args:
        intervention_id: ID de l'intervention
        technicien_nom: Nom complet du technicien (used to find the ID)
        data: Dict with keys like probleme_tech, solution_tech, duree_minutes_tech, etc.
              Can optionally include 'technicien_id' to bypass name matching
    
    Returns:
        bool: Success
    """
    def names_match(name1, name2):
        """Check if two names refer to the same person (handles reversed order)"""
        if not name1 or not name2:
            return False
        
        n1 = str(name1).lower().strip()
        n2 = str(name2).lower().strip()
        
        # Exact match
        if n1 == n2:
            return True
        
        # Split into words (>1 char)
        words1 = [w for w in n1.split() if len(w) > 1]
        words2 = [w for w in n2.split() if len(w) > 1]
        
        if not words1 or not words2:
            return False
        
        # Check if all words match (handles reversed order)
        return (all(w in words2 for w in words1) and 
                all(w in words1 for w in words2))
    
    ph = "%s"
    
    with get_db() as conn:
        # Ensure the record exists first. The helper uses a separate
        # connection; run the DDL compatibility guard only after it has
        # released its transaction, otherwise the table lock can block it.
        get_or_create_interventions_techniciens(intervention_id, technicien_nom)
        _ensure_workshop_transfer_status_constraint(conn)
        
        # Try to find the record ID first - use the ID if provided in data
        record_id = data.get('technicien_id')
        logger.info(f"🔍 update_interventions_techniciens: looking for tech '{technicien_nom}' (provided ID: {record_id})")
        
        if not record_id:
            # Find matching technician using fuzzy matching by name
            rows = conn.execute(f"""
                SELECT id, technicien_nom FROM interventions_techniciens 
                WHERE intervention_id = {ph}
            """, (intervention_id,)).fetchall()
            
            logger.info(f"  📋 Found {len(rows)} technician records for intervention {intervention_id}")
            
            for row in rows:
                row_dict = dict(row)
                tech_name_in_db = row_dict.get('technicien_nom')
                logger.info(f"    Checking: '{tech_name_in_db}' vs '{technicien_nom}' -> {names_match(tech_name_in_db, technicien_nom)}")
                
                if tech_name_in_db and names_match(tech_name_in_db, technicien_nom):
                    record_id = row_dict['id']
                    logger.info(f"    ✅ MATCHED! Using record ID: {record_id}")
                    break
        
        if not record_id:
            logger.warning(f"❌ No matching technician record found for '{technicien_nom}' in intervention {intervention_id}")
            return False
        
        # Build update query using ID (most reliable)
        updates = []
        params = []
        
        allowed_fields = [
            'statut', 'probleme_tech', 'cause_tech', 'solution_tech',
            'heure_debut_tech', 'heure_fin_tech', 'duree_minutes_tech',
            'duree_deplacement_tech', 'notes_tech', 'type_erreur_tech',
            'pieces_a_deduire'  # JSON array of pieces to deduct
        ]
        
        for field in allowed_fields:
            if field in data and field != 'technicien_id':
                # Serialize pieces_a_deduire as JSON if it's a list
                value = data[field]
                if field == 'pieces_a_deduire' and isinstance(value, list):
                    import json
                    value = json.dumps(value)
                
                updates.append(f"{field} = {ph}")
                params.append(value)
                logger.debug(f"    {field}: {value if field != 'pieces_a_deduire' else '(JSON array)'}")
        
        if not updates:
            logger.warning(f"  ⚠️ No fields to update!")
            return False
        
        params.append(record_id)
        
        query = f"""
            UPDATE interventions_techniciens 
            SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph}
        """
        
        logger.info(f"  🔄 Executing UPDATE for record ID {record_id}")
        logger.debug(f"     Query: {query}")
        logger.debug(f"     Params: {params}")
        
        result = conn.execute(query, params)
        logger.info(f"  ✅ Updated technician record ID {record_id} in intervention {intervention_id}")
        _trigger_backup()
        return True


def get_interventions_techniciens(intervention_id):
    """
    Récupère tous les enregistrements pour une intervention.
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        list: Liste des techniciens assignés avec leurs données
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT * FROM interventions_techniciens 
            WHERE intervention_id = %s
            ORDER BY created_at ASC
        """, (intervention_id,)).fetchall()
        return [dict(r) for r in rows]


def all_techniciens_completed(intervention_id):
    """
    Checks if all technicians have marked as Cloturee.
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        bool: True if all techniciens have statut='Cloturee'
    """
    with get_db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as total, 
                   SUM(CASE WHEN statut = 'Cloturee' THEN 1 ELSE 0 END) as completed
            FROM interventions_techniciens 
            WHERE intervention_id = %s
        """, (intervention_id,)).fetchone()
        
        if not row:
            return False
        
        total = row['total'] or 0
        completed = row['completed'] or 0
        
        return total > 0 and total == completed


def calculate_intervention_totals(intervention_id):
    """
    Calcule les totaux pour une intervention à partir des données per-technician.
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        dict: {total_duree_minutes, total_duree_deplacement}
    """
    with get_db() as conn:
        row = conn.execute("""
            SELECT 
                COALESCE(SUM(duree_minutes_tech), 0) as total_duree,
                COALESCE(SUM(duree_deplacement_tech), 0) as total_deplacement
            FROM interventions_techniciens 
            WHERE intervention_id = %s AND statut = 'Terminé'
        """, (intervention_id,)).fetchone()
        
        if row:
            return {
                'total_duree_minutes': row['total_duree'] or 0,
                'total_duree_deplacement': row['total_deplacement'] or 0
            }
        
        return {'total_duree_minutes': 0, 'total_duree_deplacement': 0}


def consolidate_technician_duplicates(intervention_id):
    """
    Consolidates duplicate technician records (with reversed names) into one.
    When Sellami Ghazi and Ghazi Sellami exist, keeps one and merges data from both.
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        int: Number of duplicates consolidated
    """
    def names_match(name1, name2):
        """Check if two names refer to the same person (handles reversed order)"""
        if not name1 or not name2:
            return False
        
        n1 = str(name1).lower().strip()
        n2 = str(name2).lower().strip()
        
        if n1 == n2:
            return True
        
        words1 = [w for w in n1.split() if len(w) > 1]
        words2 = [w for w in n2.split() if len(w) > 1]
        
        if not words1 or not words2:
            return False
        
        return (all(w in words2 for w in words1) and 
                all(w in words1 for w in words2))
    
    ph = "%s"
    consolidated = 0
    
    with get_db() as conn:
        # Get all records for this intervention
        rows = conn.execute(f"""
            SELECT id, technicien_nom, statut FROM interventions_techniciens 
            WHERE intervention_id = {ph}
            ORDER BY id ASC
        """, (intervention_id,)).fetchall()
        
        techs = [dict(r) for r in rows]
        processed = set()
        
        for i, tech1 in enumerate(techs):
            if tech1['id'] in processed:
                continue
            
            tech1_id = tech1['id']
            tech1_name = tech1['technicien_nom']
            tech1_status = tech1['statut']
            
            # Find all duplicates of this technician
            duplicates = []
            for j, tech2 in enumerate(techs):
                if i == j or tech2['id'] in processed:
                    continue
                
                if names_match(tech1_name, tech2['technicien_nom']):
                    duplicates.append(tech2)
            
            # If duplicates found, consolidate
            if duplicates:
                logger.info(f"  🔄 Consolidating {tech1_name}: found {len(duplicates)} duplicate(s)")
                
                # If primary is not Cloturee but a duplicate is, promote the duplicate
                if tech1_status != 'Cloturee':
                    for dup in duplicates:
                        if dup['statut'] == 'Cloturee':
                            # Copy Cloturee status to primary
                            conn.execute(f"""
                                UPDATE interventions_techniciens 
                                SET statut = 'Cloturee'
                                WHERE id = {ph}
                            """, (tech1_id,))
                            tech1_status = 'Cloturee'
                            logger.info(f"    ✅ Promoted primary record to Cloturee")
                            break
                
                # Delete duplicate records
                for dup in duplicates:
                    conn.execute(f"""
                        DELETE FROM interventions_techniciens 
                        WHERE id = {ph}
                    """, (dup['id'],))
                    processed.add(dup['id'])
                    consolidated += 1
                    logger.info(f"    🗑️ Deleted duplicate record ID {dup['id']}: {dup['technicien_nom']}")
        
        if consolidated > 0:
            _trigger_backup()
            logger.info(f"  ✅ Consolidated {consolidated} duplicate technician records for intervention {intervention_id}")
        
        return consolidated


def get_techniciens_status(intervention_id):
    """
    Gets the status of all technicians for an intervention.
    Returns completed count, total count, and list of pending technicians.
    Deduplicates technician names with reversed word order (e.g., "Ghazi Sellami" vs "Sellami Ghazi").
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        dict: {
            'total': total number of unique technicians,
            'completed': number completed (statut='Cloturee'),
            'pending_names': list of unique technician names not yet completed,
            'is_all_completed': bool
        }
    """
    def names_match(name1, name2):
        """Check if two names refer to the same person (handles reversed order)"""
        if not name1 or not name2:
            return False
        
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()
        
        # Exact match
        if n1 == n2:
            return True
        
        # Split into words (>1 char)
        words1 = [w for w in n1.split() if len(w) > 1]
        words2 = [w for w in n2.split() if len(w) > 1]
        
        if not words1 or not words2:
            return False
        
        # Check if all words match (handles reversed order)
        return (all(w in words2 for w in words1) and 
                all(w in words1 for w in words2))
    
    with get_db() as conn:
        rows = conn.execute("""
            SELECT technicien_nom, statut FROM interventions_techniciens 
            WHERE intervention_id = %s
            ORDER BY technicien_nom
        """, (intervention_id,)).fetchall()
        
        techs = [dict(r) for r in rows]
        
        # Deduplicate technicians with reversed names
        unique_techs = []
        for tech in techs:
            tech_name = tech['technicien_nom']
            # Check if this technician already exists in unique list
            is_duplicate = any(names_match(unique['technicien_nom'], tech_name) 
                             for unique in unique_techs)
            if not is_duplicate:
                unique_techs.append(tech)
        
        total = len(unique_techs)
        completed = sum(1 for t in unique_techs if t.get('statut') == 'Cloturee')
        pending = [t['technicien_nom'] for t in unique_techs if t.get('statut') != 'Cloturee']
        
        return {
            'total': total,
            'completed': completed,
            'pending_names': pending,
            'is_all_completed': total > 0 and completed == total
        }


def get_child_interventions(parent_intervention_id):
    """
    Récupère toutes les interventions enfants d'une intervention parent.
    """
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, technicien, statut FROM interventions 
            WHERE parent_intervention_id = %s AND is_temporary = 1
            ORDER BY technicien
        """, (parent_intervention_id,)).fetchall()
        return [dict(r) for r in rows]


def lire_child_interventions_for_technician(technician_name):
    """
    Récupère toutes les interventions enfants assignées à un technicien spécifique.
    Utilisé par les techniciens sur PWA pour voir leurs interventions enfants.
    """
    with get_db() as conn:
        # Query child interventions assigned to this technician
        # Use word-boundary regex matching to avoid false positives
        # (e.g., "al" matching inside "Salah" for "Ahmed Ben Salah")
        base_query = """
            SELECT i.id, i.date, i.machine, i.technicien, i.type_intervention,
                   i.description, i.probleme, i.cause, i.solution,
                   i.pieces_utilisees, i.cout, i.cout_pieces, i.duree_minutes,
                   i.duree_deplacement,
                   i.code_erreur, i.statut, i.notes,
                   i.date_debut_intervention, i.date_cloture,
                   i.type_erreur, i.priorite,
                   i.start_time, i.end_time,
                   COALESCE(i.fiche_photo_nom, '') AS fiche_photo_nom,
                   COALESCE(i.fiche_validation, 'En attente') AS fiche_validation,
                   (NULLIF(i.fiche_storage_key, '') IS NOT NULL OR
                    (i.fiche_photo_data IS NOT NULL AND octet_length(i.fiche_photo_data) > 0)) AS has_fiche,
                   COALESCE(e.client, '') AS client,
                   i.parent_intervention_id
            FROM interventions i
            LEFT JOIN equipements e ON e.id = i.equipement_id
            WHERE i.is_temporary = 1 AND i.technicien ILIKE %s
            ORDER BY i.date DESC
        """
        
        # Use ILIKE for initial broad match, then filter precisely in Python
        search_pattern = f"%{technician_name}%"
        df = read_sql(base_query, conn, params=(search_pattern,))
    
    # Post-filter: ensure ALL words from technician_name appear as whole words
    # in the technicien field (prevents "al" in "Salah Al Salah" from matching "Ahmed Ben Salah")
    # Strip punctuation (commas, etc.) before splitting to handle "Salah Al Salah, Other Tech"
    if not df.empty and "technicien" in df.columns:
        import re as _re
        def _extract_words_db(text):
            cleaned = _re.sub(r'[,;/\-_\.\(\)\[\]]+', ' ', text.lower())
            return [w for w in cleaned.split() if len(w) > 1]
        
        user_words = _extract_words_db(technician_name)
        if user_words:
            df = df[df["technicien"].astype(str).apply(
                lambda t: all(word in _extract_words_db(t) for word in user_words)
            )]
    
    # Apply text fixes
    text_columns = ["machine", "description", "probleme", "cause", "solution", "notes", "client"]
    if not df.empty:
        df = _fix_df_text(df, columns=text_columns)
    
    # Fill remaining NaN with empty string
    if "client" in df.columns:
        df["client"] = df["client"].fillna("")
    
    # Normalize statut
    if not df.empty and "statut" in df.columns:
        df["statut"] = df["statut"].apply(
            lambda s: "Cloturee" if "tur" in str(s).lower() else str(s)
        )
    
    return df


def finalize_intervention_from_techniciens(intervention_id):
    """
    Finalizes an intervention by aggregating all technician data.
    When ALL technicians mark as Cloturee, AUTOMATICALLY closes the parent intervention.
    Deduplicates technician names with reversed word order.
    
    Args:
        intervention_id: ID de l'intervention
    
    Returns:
        dict: {
            'success': bool,
            'total_duree_minutes': int,
            'total_duree_deplacement': int,
            'combined_solution': str,
            'completed': int,
            'total': int
        }
    """
    def names_match(name1, name2):
        """Check if two names refer to the same person (handles reversed order)"""
        if not name1 or not name2:
            return False
        
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()
        
        # Exact match
        if n1 == n2:
            return True
        
        # Split into words (>1 char)
        words1 = [w for w in n1.split() if len(w) > 1]
        words2 = [w for w in n2.split() if len(w) > 1]
        
        if not words1 or not words2:
            return False
        
        # Check if all words match (handles reversed order)
        return (all(w in words2 for w in words1) and 
                all(w in words1 for w in words2))
    
    with get_db() as conn:
        # Use correct SQL placeholder based on database type
        ph = "%s"

        # Serialize finalization for a shared intervention. Two technicians
        # may submit their closure at nearly the same time.
        parent_state = conn.execute(
            """SELECT id, statut, date_transfert_atelier, retour_site_confirme, solution
               FROM interventions WHERE id = %s FOR UPDATE""",
            (intervention_id,),
        ).fetchone()

        if (
            parent_state
            and retour_site_confirmation_requise(
                parent_state.get("statut"),
                parent_state.get("retour_site_confirme"),
            )
        ):
            return {
                'success': False,
                'reason': 'return_site_confirmation_required',
                'error': "Le retour de l'équipement sur site doit être confirmé avant la clôture.",
            }
        
        # Get ALL technician records (only aggregate Cloturee ones)
        rows = conn.execute(f"""
            SELECT * FROM interventions_techniciens 
            WHERE intervention_id = {ph}
            ORDER BY technicien_nom
            FOR UPDATE
        """, (intervention_id,)).fetchall()
        
        if not rows:
            logger.warning(f"No technicians for intervention {intervention_id}")
            return {'success': False, 'error': 'No technicians found'}
        
        techs = [dict(r) for r in rows]
        
        # Deduplicate technicians with reversed names
        unique_techs = []
        for tech in techs:
            tech_name = tech['technicien_nom']
            # Check if this technician already exists in unique list
            is_duplicate = any(names_match(unique['technicien_nom'], tech_name) 
                             for unique in unique_techs)
            if not is_duplicate:
                unique_techs.append(tech)
        
        # Check if ALL are completed (using deduplicated count)
        completed_count = sum(1 for t in unique_techs if t.get('statut') == 'Cloturee')
        total_count = len(unique_techs)
        
        if completed_count != total_count:
            logger.info(f"Intervention {intervention_id}: Only {completed_count}/{total_count} completed, not finalizing yet")
            return {
                'success': False,
                'reason': 'not_all_completed',
                'completed': completed_count,
                'total': total_count
            }
        
        # Aggregate data from completed technicians
        completed_techs = [t for t in unique_techs if t.get('statut') == 'Cloturee']
        total_duree = sum(t.get('duree_minutes_tech') or 0 for t in completed_techs)
        total_deplacement = sum(t.get('duree_deplacement_tech') or 0 for t in completed_techs)
        
        # Combine technical notes
        solutions = []
        for technician in completed_techs:
            solution_value = technician.get('solution_tech', '').strip()
            if solution_value and solution_value not in solutions:
                solutions.append(solution_value)
        combined_solution = str(parent_state.get('solution') or '').strip() or (" | ".join(solutions) if solutions else "")
        
        # Get the first type_erreur_tech from completed technicians (if any)
        first_error_type = next((t.get('type_erreur_tech', '').strip() for t in completed_techs 
                                 if t.get('type_erreur_tech', '').strip()), '')
        
        # Aggregate pieces from all technicians
        import json
        all_pieces_used = []
        for tech in completed_techs:
            pieces_json = tech.get('pieces_a_deduire', '')
            if pieces_json and isinstance(pieces_json, str):
                try:
                    pieces_list = json.loads(pieces_json)
                    if isinstance(pieces_list, list):
                        all_pieces_used.extend(pieces_list)
                except json.JSONDecodeError:
                    logger.debug(f"Could not parse pieces_a_deduire for tech {tech.get('technicien_nom')}: {pieces_json}")
        
        # Format pieces for pieces_utilisees - deduplicate by ref and sum quantities
        pieces_by_ref = {}
        for piece in all_pieces_used:
            if isinstance(piece, dict):
                ref = piece.get('ref') or piece.get('reference', '')
                qty = int(piece.get('qty') or piece.get('quantite') or 0)
                
                if ref and qty > 0:
                    if ref not in pieces_by_ref:
                        pieces_by_ref[ref] = {
                            'ref': ref,
                            'qty': 0,
                            'designation': piece.get('designation', ref),
                            'fournisseur': piece.get('fournisseur', ''),
                            'prix_unitaire': float(piece.get('prix_unitaire', 0) or 0)
                        }
                    pieces_by_ref[ref]['qty'] += qty
        
        # Format pieces for display
        formatted_pieces = []
        total_cout_pieces = 0.0
        for ref, piece_info in pieces_by_ref.items():
            prix_unitaire = float(piece_info.get('prix_unitaire', 0) or 0)
            try:
                piece_row = conn.execute(
                    f"SELECT prix_unitaire, designation, fournisseur FROM pieces_rechange WHERE reference = {ph} LIMIT 1",
                    (ref,)
                ).fetchone()
                if piece_row:
                    prix_unitaire = float(piece_row.get('prix_unitaire', 0) or prix_unitaire or 0)
                    piece_info['designation'] = piece_row.get('designation', piece_info['designation'])
                    piece_info['fournisseur'] = piece_row.get('fournisseur', piece_info['fournisseur'])
            except Exception as piece_err:
                logger.warning(f"Could not fetch price for piece {ref}: {piece_err}")

            total_cout_pieces += prix_unitaire * int(piece_info.get('qty') or 0)
            # Format: Désignation | Ref: XXX | Fournisseur: YYY | Qty: Z
            piece_line = f"{piece_info['designation']} | Ref: {piece_info['ref']} | Fournisseur: {piece_info['fournisseur']} | Qty: {piece_info['qty']}"
            formatted_pieces.append(piece_line)
        
        pieces_utilisees_str = "\n".join(formatted_pieces) if formatted_pieces else ""
        logger.info(f"Aggregated {len(formatted_pieces)} unique pieces for intervention {intervention_id}: {pieces_utilisees_str}")
        
        try:
            config_row = conn.execute("SELECT valeur FROM config_client WHERE cle = 'taux_horaire_technicien'").fetchone()
            if not config_row or not config_row["valeur"]:
                raise ValueError("Taux horaire technicien non configure")
            taux_horaire = float(config_row["valeur"])
        except (ValueError, TypeError) as e:
            raise Exception(f"Erreur configuration: {str(e)}")

        cout_main_oeuvre = round((total_duree / 60.0) * taux_horaire, 2)
        total_cout_pieces = round(total_cout_pieces, 2)

        # ✅ AUTOMATICALLY CLOSE the parent intervention (statut = 'Cloturee')
        # This is the key change - we now close it instead of leaving it "En cours"
        date_cloture = datetime.now().isoformat()

        # Get planning_id before updating intervention
        interv_row = conn.execute(f"SELECT planning_id FROM interventions WHERE id = {ph}", (intervention_id,)).fetchone()
        planning_id = interv_row.get('planning_id') if interv_row else None

        conn.execute(f"""
            UPDATE interventions 
            SET statut = {ph},
                duree_minutes = {ph},
                duree_deplacement = {ph},
                solution = CASE WHEN solution = '' THEN {ph} ELSE solution END,
                type_erreur = CASE WHEN type_erreur = '' OR type_erreur IS NULL THEN {ph} ELSE type_erreur END,
                date_cloture = {ph},
                pieces_utilisees = {ph},
                cout = {ph},
                cout_pieces = {ph}
            WHERE id = {ph}
        """, ('Cloturee', total_duree, total_deplacement, combined_solution, first_error_type, date_cloture, pieces_utilisees_str, cout_main_oeuvre, total_cout_pieces, intervention_id))

        # Synchronise la demande d'intervention liée avec la clôture du parent
        # multi-techniciens. Le flux single effectue déjà cette mise à jour,
        # mais la finalisation multi passait auparavant directement par ici.
        conn.execute(f"""
            UPDATE demandes_intervention
            SET statut = {ph},
                date_traitement = {ph}
            WHERE intervention_id = {ph}
              AND statut != {ph}
        """, ('Résolue', date_cloture, intervention_id, 'Résolue'))
        logger.info(f"✅ Demande liée à l'intervention #{intervention_id} marquée Résolue")

        synchroniser_statut_equipement(conn, intervention_id, "Cloturee")
        
        # Update related planning to "Cloturee" if it exists
        if planning_id:
            conn.execute(f"""
                UPDATE planning_maintenance
                SET statut = {ph},
                    date_realisee = {ph}
                WHERE id = {ph} AND statut != {ph}
            """, ('Cloturee', date_cloture[:10], planning_id, 'Cloturee'))
            logger.info(f"✅ Planning #{planning_id} marked as Cloturee (intervention #{intervention_id} auto-closed)")

        try:
            assess_intervention_contract_coverage_in_savepoint(conn, intervention_id)
        except Exception as exc:
            logger.exception("Contract coverage assessment failed for intervention #%s: %s", intervention_id, exc)
        
        logger.info(f"✅ Intervention #{intervention_id} AUTOMATICALLY CLOSED after all {total_count} technicians completed")
        
        conn.commit()
        _trigger_backup()
        
        return {
            'success': True,
            'total_duree_minutes': total_duree,
            'total_duree_deplacement': total_deplacement,
            'cout_main_oeuvre': cout_main_oeuvre,
            'cout_pieces': total_cout_pieces,
            'combined_solution': combined_solution,
            'completed': completed_count,
            'total': total_count
        }
        
        _trigger_backup()
        logger.info(f"✅ Intervention {intervention_id} fully finalized: {total_count} technicians, {total_duree} minutes total")
        
        return {
            'success': True,
            'completed': completed_count,
            'total': total_count,
            'total_duree_minutes': total_duree,
            'total_duree_deplacement': total_deplacement,
            'combined_solution': combined_solution
        }
