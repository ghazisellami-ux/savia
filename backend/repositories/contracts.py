"""Technician, contract, intervention completion, and compliance persistence."""

import json
import logging
from datetime import datetime

import pandas as pd

from database.core import _trigger_backup, get_db, read_sql
from repositories.equipment_status import (
    WORKSHOP_TRANSFER_STATUS,
    retour_site_confirmation_requise,
    synchroniser_statut_equipement,
)
from services.contract_billing import assess_intervention_contract_coverage_in_savepoint

logger = logging.getLogger("db_engine")

__all__ = [
    "lire_techniciens",
    "ajouter_technicien",
    "update_technicien",
    "supprimer_technicien",
    "lire_contrats",
    "get_contract_equipements",
    "ajouter_contrat",
    "generer_planning_from_contrat",
    "modifier_contrat",
    "supprimer_contrat",
    "update_intervention_statut",
    "cloturer_intervention",
    "lire_conformite",
    "ajouter_conformite",
    "supprimer_conformite",
    "lire_fichier_conformite",
]

# ==========================================
# FONCTIONS CRUD — TECHNICIENS
# ==========================================

def _normalize_disponibilite(value):
    """Convertit les libellés frontend de disponibilité vers le format DB 1/0."""
    if isinstance(value, str):
        return 1 if value.strip().lower() in {"1", "true", "oui", "yes", "disponible", "available"} else 0
    return 1 if value else 0

def lire_techniciens():
    """
    Lit la liste des techniciens.
    
    Returns:
        pd.DataFrame: Liste des techniciens.
    """
    try:
        with get_db() as conn:
            return read_sql("""
                SELECT 
                    id, username, nom, prenom, specialite, 
                    qualification, niveau_competence, dispo, notes,
                    email, telephone, telegram_id
                FROM techniciens
                ORDER BY nom
            """, conn)
    except Exception as e:
        logger.error(f"Erreur lire_techniciens: {e}")
        return pd.DataFrame()

def ajouter_technicien(tech_dict):
    """
    Ajoute un technicien.
    """
    dispo = _normalize_disponibilite(tech_dict.get("dispo", 1))
    try:
        with get_db() as conn:
            res = conn.execute("""
                INSERT INTO techniciens (nom, prenom, specialite, qualification, niveau_competence, dispo, notes, email, telephone, telegram_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                tech_dict.get("nom", ""),
                tech_dict.get("prenom", ""),
                tech_dict.get("specialite", "Généraliste"),
                tech_dict.get("qualification", ""),
                tech_dict.get("niveau_competence", "Junior"),
                dispo,
                tech_dict.get("notes", ""),
                tech_dict.get("email", ""),
                tech_dict.get("telephone", ""),
                tech_dict.get("telegram_id", ""),
            ))
            tech_id = res.fetchone()["id"]
        
        nom_comp = f"{tech_dict.get('nom', '')} {tech_dict.get('prenom', '')}".strip()
        logger.info(f"Audit Trail: Nouveau technicien {nom_comp} ajouté (ID: {tech_id})")
        return True
    except Exception as e:
        logger.error(f"Erreur ajouter_technicien: {e}")
        raise

def update_technicien(tech_id, tech_dict):
    """
    Met à jour un technicien.
    """
    dispo = _normalize_disponibilite(tech_dict.get("dispo", 1))
    try:
        with get_db() as conn:
            conn.execute("""
                UPDATE techniciens
                SET nom=%s, prenom=%s, specialite=%s, qualification=%s, niveau_competence=%s, dispo=%s, notes=%s,
                    email=%s, telephone=%s, telegram_id=%s
                WHERE id=%s
            """, (
                tech_dict.get("nom", ""),
                tech_dict.get("prenom", ""),
                tech_dict.get("specialite", ""),
                tech_dict.get("qualification", ""),
                tech_dict.get("niveau_competence", "Junior"),
                dispo,
                tech_dict.get("notes", ""),
                tech_dict.get("email", ""),
                tech_dict.get("telephone", ""),
                tech_dict.get("telegram_id", ""),
                tech_id
            ))
        
        logger.info(f"Audit Trail: Technicien ID {tech_id} mis à jour.")
        return True
    except Exception as e:
        logger.error(f"Erreur update_technicien ID {tech_id}: {e}")
        return False

def supprimer_technicien(tech_id):
    """Supprime un technicien."""
    with get_db() as conn:
        conn.execute("DELETE FROM techniciens WHERE id = %s", (tech_id,))
    return True


# ==========================================

# ==========================================
# FONCTIONS CRUD — CONTRATS / SLA
# ==========================================

def lire_contrats(client=None):
    """Lit les contrats, optionnellement filtrés par client."""
    with get_db() as conn:
        if client:
            # Client names are user-managed labels. Match the same normalized
            # value used by the authorization layer so case/spacing differences
            # do not hide contracts from a client account.
            df = read_sql(
                """SELECT * FROM contrats
                   WHERE LOWER(TRIM(client)) = LOWER(TRIM(%s))
                   ORDER BY date_fin DESC""",
                conn,
                params=(client,),
            )
        else:
            df = read_sql("SELECT * FROM contrats ORDER BY date_fin DESC", conn)
    return df

def get_contract_equipements(contrat_id):
    """Récupère les équipements d'un contrat avec leurs détails d'identification."""
    with get_db() as conn:
        ph = "%s"
        
        try:
            # Ensure contrat_id is a Python int (handles numpy.int64 from pandas)
            contrat_id = int(contrat_id)
            
            rows = conn.execute(
                f"""SELECT e.id, e.nom, e.type, e.fabricant, e.modele, e.num_serie
                    FROM contrats_equipements ce
                    JOIN equipements e ON ce.equipement_id = e.id
                    WHERE ce.contrat_id = {ph}
                    ORDER BY ce.id""",
                (contrat_id,)
            ).fetchall()
            
            if rows:
                equipements = [
                    {
                        "id": row["id"],
                        "nom": row["nom"],
                        "type": row.get("type") or "",
                        "fabricant": row.get("fabricant") or "",
                        "modele": row.get("modele") or "",
                        "num_serie": row.get("num_serie") or "",
                    }
                    for row in rows
                    if row.get("nom")
                ]
                logger.debug(f"Retrieved {len(equipements)} equipment(s) for contract {contrat_id}")
                return equipements
            
            logger.debug(f"No equipements found for contract {contrat_id}")
            return []
        except Exception as e:
            logger.error(f"Error retrieving equipements for contract {contrat_id}: {e}")
            return []

def _contract_equipment_ids(values):
    """Parse equipment IDs sent by the current UI while tolerating legacy payloads."""
    if isinstance(values, (str, int)):
        values = [values]
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        try:
            equipment_id = int(value)
        except (TypeError, ValueError):
            continue
        if equipment_id > 0 and equipment_id not in result:
            result.append(equipment_id)
    return result


def _resolve_contract_equipment_rows(conn, contrat_dict):
    """Resolve exact equipment IDs, with name-based fallback for old clients."""
    equipment_ids = _contract_equipment_ids(contrat_dict.get("equipement_ids"))
    client = str(contrat_dict.get("client") or "").strip()
    if equipment_ids:
        rows = conn.execute(
            """SELECT id, nom FROM equipements
               WHERE id = ANY(%s)
                 AND LOWER(TRIM(client)) = LOWER(TRIM(%s))""",
            (equipment_ids, client),
        ).fetchall()
        rows_by_id = {int(row["id"]): row for row in rows}
        missing = [equipment_id for equipment_id in equipment_ids if equipment_id not in rows_by_id]
        if missing:
            raise ValueError(f"Équipement(s) introuvable(s) pour ce client : {', '.join(map(str, missing))}")
        return [(equipment_id, rows_by_id[equipment_id]["nom"]) for equipment_id in equipment_ids]

    names = contrat_dict.get("equipements", [])
    if isinstance(names, str):
        names = [names] if names else []
    elif not isinstance(names, list):
        names = []
    if not names:
        single_name = contrat_dict.get("equipement", "")
        if single_name:
            names = [single_name]

    resolved = []
    for name in names:
        if not name:
            continue
        row = conn.execute(
            """SELECT id, nom FROM equipements
               WHERE nom = %s AND LOWER(TRIM(client)) = LOWER(TRIM(%s))
               ORDER BY id LIMIT 1""",
            (name, client),
        ).fetchone()
        resolved.append((int(row["id"]) if row else None, name))
    return resolved

def ajouter_contrat(contrat_dict):
    """
    Ajoute un contrat et ses équipements, retourne son ID.
    
    Supporte deux formats:
    - equipement (str): rétrocompatibilité - sera converti en array
    - equipements (list): array d'équipements
    
    Stocke aussi les pièces incluses en JSON si avec_pieces=true
    """
    with get_db() as conn:
        equipment_rows = _resolve_contract_equipment_rows(conn, contrat_dict)
        equipements = [name for _, name in equipment_rows]
        
        # Store first equipment in main table for backward compatibility
        first_equipment = equipements[0] if equipements else ""
        
        # Handle pieces_incluses - convert list to JSON string
        pieces_incluses = contrat_dict.get("pieces_incluses", "")
        if isinstance(pieces_incluses, (list, dict)):
            import json
            pieces_incluses = json.dumps(pieces_incluses)
        
        # PostgreSQL returns the generated identifier atomically.
        ph = "%s"
        contrat_id = None
        
        try:
            row = conn.execute(f"""
                INSERT INTO contrats (client, type_contrat, date_debut, date_fin,
                    sla_temps_reponse_h, interventions_incluses, montant, conditions, notes,
                    fichier_contrat, equipement, recurrence_maintenance, date_premiere_maintenance, statut,
                    pieces_incluses, avec_pieces, rappel_avant_jours)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                RETURNING id
            """, (
                contrat_dict.get("client", ""),
                contrat_dict.get("type_contrat", "Standard"),
                contrat_dict.get("date_debut", ""),
                contrat_dict.get("date_fin", ""),
                contrat_dict.get("sla_temps_reponse_h", 0),
                contrat_dict.get("interventions_incluses", -1),
                contrat_dict.get("montant", 0.0),
                contrat_dict.get("conditions", ""),
                contrat_dict.get("notes", ""),
                contrat_dict.get("fichier_contrat", ""),
                first_equipment,
                contrat_dict.get("recurrence_maintenance", ""),
                contrat_dict.get("date_premiere_maintenance", ""),
                contrat_dict.get("statut", "Actif"),
                pieces_incluses,
                1 if contrat_dict.get("avec_pieces") else 0,
                contrat_dict.get("rappel_avant_jours", 14),
            ))
            inserted = row.fetchone()
            contrat_id = inserted["id"] if inserted else None
            logger.info(f"✅ Contrat created with ID: {contrat_id}")
        except Exception as e:
            logger.error(f"Error inserting contrat: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
        
        if not contrat_id:
            logger.error("Failed to retrieve contrat ID after insertion")
            return None
        
        # Insert equipments into junction table
        # PostgreSQL only: contrats_equipements(contrat_id, equipement_id)
        logger.info(f"Inserting {len(equipements)} equipment(s) for contrat {contrat_id}: {equipements}")
        
        for eq_id, eq in equipment_rows:
            if eq:  # Only insert non-empty equipments
                try:
                    if eq_id:
                        conn.execute(
                            "INSERT INTO contrats_equipements (contrat_id, equipement_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (contrat_id, eq_id)
                        )
                        logger.info(f"✅ Equipment '{eq}' (ID: {eq_id}) inserted for contrat {contrat_id}")
                    else:
                        logger.warning(f"Equipment '{eq}' not found in equipements table")
                except Exception as e:
                    logger.error(f"❌ Error inserting equipment '{eq}' for contract {contrat_id}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
    
    _trigger_backup()
    logger.info(f"✅ Contrat #{contrat_id} saved successfully with {len(equipements)} equipment(s)")
    return contrat_id


def generer_planning_from_contrat(contrat_id):
    """
    Génère automatiquement les entrées de planning de maintenance préventive
    à partir d'un contrat, selon sa récurrence et ses dates.
    
    Supporte les équipements multiples: génère une entrée de planning pour 
    CHAQUE équipement du contrat.
    
    Utilise le rappel_avant_jours du contrat pour les notifications.
    
    Retourne le nombre d'entrées créées.
    """
    from dateutil.relativedelta import relativedelta
    import logging
    logger = logging.getLogger("db_engine")
    
    # Ensure contrat_id is a Python int (handles numpy.int64 from pandas)
    contrat_id = int(contrat_id)

    RECURRENCE_DELTAS = {
        "Hebdomadaire": relativedelta(weeks=1),
        "Mensuelle": relativedelta(months=1),
        "Trimestrielle": relativedelta(months=3),
        "Semestrielle": relativedelta(months=6),
        "Annuelle": relativedelta(years=1),
    }

    with get_db() as conn:
        ph = "%s"
        
        try:
            row = conn.execute(
                f"SELECT * FROM contrats WHERE id = {ph}", (contrat_id,)
            ).fetchone()
            if not row:
                logger.warning(f"generer_planning: Contrat #{contrat_id} not found")
                return 0

            contrat = dict(row)
            recurrence = (contrat.get("recurrence_maintenance") or "").strip()
            if not recurrence or recurrence not in RECURRENCE_DELTAS:
                logger.warning(f"generer_planning: Contrat #{contrat_id} has invalid or missing recurrence: {recurrence}")
                return 0

            date_fin_str = str(contrat.get("date_fin", "") or "")[:10]
            date_premiere_str = str(contrat.get("date_premiere_maintenance", "") or "")[:10]
            client = contrat.get("client", "")
            rappel_avant_jours = contrat.get("rappel_avant_jours", 14) or 14

            if not date_fin_str or not date_premiere_str:
                logger.warning(f"generer_planning: Contrat #{contrat_id} missing dates. date_fin={date_fin_str}, date_premiere={date_premiere_str}")
                return 0

            try:
                from datetime import date as _date
                date_premiere = _date.fromisoformat(date_premiere_str)
                date_fin = _date.fromisoformat(date_fin_str)
            except ValueError as ve:
                logger.error(f"generer_planning: Invalid date format for contrat #{contrat_id}: {ve}")
                return 0

            # Récupérer tous les équipements du contrat (utilise le schema standard equipement_id)
            equipements = []
            
            try:
                equipements_rows = conn.execute(
                    f"""SELECT e.nom as equipement_nom FROM contrats_equipements ce
                        JOIN equipements e ON ce.equipement_id = e.id
                        WHERE ce.contrat_id = {ph}
                        ORDER BY ce.id""",
                    (contrat_id,)
                ).fetchall()
                
                if equipements_rows:
                    equipements = [dict(row)["equipement_nom"] for row in equipements_rows]
                    logger.debug(f"Retrieved {len(equipements)} equipment(s) for planning generation")
            except Exception as e:
                logger.error(f"Error retrieving equipements for planning generation: {e}")
                equipements = []
            
            if not equipements:
                logger.warning(f"generer_planning: Contrat #{contrat_id} has no equipments")
                return 0  # Aucun équipement à planifier

            delta = RECURRENCE_DELTAS[recurrence]
            count = 0

            # Générer planning pour CHAQUE équipement
            for equipement in equipements:
                if not equipement:
                    logger.warning(f"generer_planning: Skipping empty equipement name for contrat #{contrat_id}")
                    continue
                    
                current_date = date_premiere
                while current_date <= date_fin:
                    try:
                        conn.execute(f"""
                            INSERT INTO planning_maintenance
                                (machine, client, type_maintenance, description,
                                 date_prevue, technicien_assigne, recurrence, contrat_id, statut, notes)
                            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                        """, (
                            equipement,
                            client,
                            "Préventive",
                            f"MP Contrat #{contrat_id} — {equipement}",
                            current_date.isoformat(),
                            "",  # Technicien non assigné — sera assigné via rappel
                            recurrence,
                            contrat_id,
                            "Planifiée",
                            f"[{client}] Généré automatiquement depuis contrat #{contrat_id} | Rappel: {rappel_avant_jours}j",
                        ))
                        count += 1
                    except Exception as e:
                        logger.error(f"generer_planning: Error inserting planning for {equipement} on {current_date}: {e}")
                    
                    current_date = current_date + delta

            logger.info(f"✅ generer_planning: Generated {count} planning entries for contrat #{contrat_id} across {len(equipements)} equipements (Rappel: {rappel_avant_jours}j)")
            return count
            
        except Exception as e:
            logger.error(f"generer_planning: Unexpected error for contrat #{contrat_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0


def modifier_contrat(contrat_id, contrat_dict):
    """Modifie un contrat existant et ses équipements."""
    with get_db() as conn:
        equipment_rows = _resolve_contract_equipment_rows(conn, contrat_dict)
        equipements = [name for _, name in equipment_rows]
        
        # Store first equipment in main table for backward compatibility
        first_equipment = equipements[0] if equipements else ""
        
        # Handle pieces_incluses - convert list to JSON string
        pieces_incluses = contrat_dict.get("pieces_incluses", "")
        if isinstance(pieces_incluses, (list, dict)):
            import json
            pieces_incluses = json.dumps(pieces_incluses)
        
        ph = "%s"
        conn.execute(f"""
            UPDATE contrats SET client={ph}, type_contrat={ph}, date_debut={ph}, date_fin={ph},
                sla_temps_reponse_h={ph}, interventions_incluses={ph}, montant={ph}, conditions={ph}, notes={ph}, statut={ph},
                equipement={ph}, pieces_incluses={ph}, avec_pieces={ph}, rappel_avant_jours={ph}
            WHERE id={ph}
        """, (
            contrat_dict.get("client", ""),
            contrat_dict.get("type_contrat", "Standard"),
            contrat_dict.get("date_debut", ""),
            contrat_dict.get("date_fin", ""),
            contrat_dict.get("sla_temps_reponse_h", 0),
            contrat_dict.get("interventions_incluses", -1),
            contrat_dict.get("montant", 0.0),
            contrat_dict.get("conditions", ""),
            contrat_dict.get("notes", ""),
            contrat_dict.get("statut", "Actif"),
            first_equipment,
            pieces_incluses,
            1 if contrat_dict.get("avec_pieces") else 0,
            contrat_dict.get("rappel_avant_jours", 14),
            contrat_id,
        ))
        
        # Delete existing equipments for this contract
        conn.execute("DELETE FROM contrats_equipements WHERE contrat_id=%s", (contrat_id,))
        
        # Insert new equipments into junction table
        # PostgreSQL only: contrats_equipements(contrat_id, equipement_id)
        logger.info(f"Inserting {len(equipements)} equipment(s) for contrat {contrat_id}: {equipements}")
        
        for eq_id, eq in equipment_rows:
            if eq:  # Only insert non-empty equipments
                try:
                    if eq_id:
                        conn.execute(
                            "INSERT INTO contrats_equipements (contrat_id, equipement_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (contrat_id, eq_id)
                        )
                        logger.info(f"✅ Equipment '{eq}' (ID: {eq_id}) inserted for contrat {contrat_id}")
                    else:
                        logger.warning(f"Equipment '{eq}' not found in equipements table")
                except Exception as e:
                    logger.error(f"Error inserting equipment '{eq}' for contract {contrat_id}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
    
    _trigger_backup()

def supprimer_contrat(contrat_id):
    """Supprime un contrat et toutes ses données associées (planning, interventions, équipements)."""
    with get_db() as conn:
        try:
            # 1. Delete planning entries for this contract
            conn.execute("DELETE FROM planning_maintenance WHERE contrat_id = %s", (contrat_id,))
            
            # 2. Delete interventions associated through planning entries
            # First, get all interventions that are linked through planning
            # (Note: interventions may not have direct contrat_id, but are linked via planning)
            
            # 3. Delete equipment associations
            conn.execute("DELETE FROM contrats_equipements WHERE contrat_id = %s", (contrat_id,))
            
            # 4. Delete the contract itself
            conn.execute("DELETE FROM contrats WHERE id = %s", (contrat_id,))
            
            conn.commit()
            logger.info(f"✅ Contrat #{contrat_id} et toutes ses données associées supprimés")
        except Exception as e:
            logger.error(f"Error deleting contrat #{contrat_id}: {e}")
            try:
                conn.rollback()
            except:
                pass
            raise
    _trigger_backup()

def _mark_linked_planning_closed(conn, intervention_id, date_realisee=None):
    """Close the real planning row while preserving the delay history."""
    linked = conn.execute(
        "SELECT planning_id FROM interventions WHERE id=%s",
        (intervention_id,)
    ).fetchone()
    planning_id = linked.get("planning_id") if linked else None
    if not planning_id:
        return

    planning = conn.execute(
        "SELECT id, original_planning_id, is_ghost FROM planning_maintenance WHERE id=%s",
        (planning_id,)
    ).fetchone()
    if not planning:
        return

    real_planning_id = (
        planning.get("original_planning_id")
        if planning.get("is_ghost") and planning.get("original_planning_id")
        else planning_id
    )
    closed_date = date_realisee or datetime.now().date().isoformat()
    conn.execute(
        """
        UPDATE planning_maintenance
        SET statut='Cloturee', date_realisee=%s
        WHERE id=%s
        """,
        (closed_date, real_planning_id)
    )


def update_intervention_statut(intervention_id, nouveau_statut):
    """Met a jour le statut d'une intervention avec horodatage."""
    with get_db() as conn:
        now = datetime.now().isoformat()
        if nouveau_statut == WORKSHOP_TRANSFER_STATUS:
            conn.execute(
                """UPDATE interventions
                   SET statut=%s, date_transfert_atelier=%s,
                       retour_site_confirme=false, date_retour_site=NULL,
                       retour_site_confirme_par=''
                   WHERE id=%s""",
                (nouveau_statut, now, intervention_id),
            )
        elif nouveau_statut == "En cours":
            conn.execute("UPDATE interventions SET statut=%s, date_debut_intervention=%s WHERE id=%s",
                         (nouveau_statut, now, intervention_id))
        elif nouveau_statut in ("Cloturee", "Cl\u00f4tur\u00e9e"):
            conn.execute("UPDATE interventions SET statut='Cloturee', date_cloture=%s WHERE id=%s",
                         (now, intervention_id))
        else:
            conn.execute("UPDATE interventions SET statut=%s WHERE id=%s",
                         (nouveau_statut, intervention_id))
        synchroniser_statut_equipement(conn, intervention_id, nouveau_statut)
        if nouveau_statut in ("Cloturee", "Clôturée"):
            _mark_linked_planning_closed(conn, intervention_id, now[:10])
    _trigger_backup()


# FONCTIONS SPÉCIALES — WORKFLOW SAV
# ==========================================

def cloturer_intervention(
    intervention_id,
    probleme,
    cause,
    solution,
    pieces_a_deduire=None,
    duree_minutes=None,
    start_time=None,
    end_time=None,
    duree_deplacement=None,
    retour_site_confirme=False,
    retour_site_confirme_par="",
):
    """
    Clôture une intervention, déduit le stock et alimente la base de connaissances.
    pieces_a_deduire: liste de dict {'ref': str, 'qty': int, 'designation': str}
    duree_minutes: durée de l'intervention en minutes
    """
    if not solution:
        return False, "La Solution (ou Actions réalisées) est obligatoire pour clôturer."

    print(f"[CLOTURE] intervention_id={intervention_id}, pieces_a_deduire={pieces_a_deduire}")

    with get_db() as conn:
        intervention_state = conn.execute(
            """SELECT statut, date_transfert_atelier, retour_site_confirme
               FROM interventions WHERE id = %s FOR UPDATE""",
            (intervention_id,),
        ).fetchone()
        if not intervention_state:
            return False, "Intervention non trouvée."

        retour_requis = retour_site_confirmation_requise(
            intervention_state.get("statut"),
            intervention_state.get("retour_site_confirme"),
        )
        if retour_requis and retour_site_confirme is not True:
            return False, (
                "Confirmez que l'équipement a bien été transféré sur site avant de clôturer l'intervention."
            )

        # NOTE: La migration cout_pieces est dans verifier_et_migrer_schema(), PAS ici.
        # Un ALTER TABLE échoué invalide la transaction PostgreSQL !

        # Use correct SQL placeholder based on database type
        ph = "%s"

        # 1. Gestion du Stock + calcul coût pièces
        synthese_pieces = []
        total_cout_pieces = 0.0
        if pieces_a_deduire:
            for p in pieces_a_deduire:
                if not isinstance(p, dict):
                    continue
                ref = p.get('ref') or p.get('reference') or ''
                qty = int(p.get('qty') or p.get('quantite') or 0)
                prix = float(p.get('prix_unitaire', 0) or 0)
                designation = p.get('designation', ref)
                fournisseur = p.get('fournisseur', '')
                
                if qty > 0 and ref:
                    print(f"[CLOTURE] Déduction stock: ref={ref}, qty={qty}, prix={prix}, designation={designation}")
                    
                    # Chercher la pièce dans la base de données pour obtenir les infos complètes
                    piece_row = conn.execute(
                        f"SELECT prix_unitaire, designation, fournisseur FROM pieces_rechange WHERE reference = {ph} LIMIT 1",
                        (ref,)
                    ).fetchone()
                    
                    if piece_row:
                        # Utiliser les infos de la base de données
                        prix = float(piece_row.get('prix_unitaire', 0) or prix or 0)
                        designation = piece_row.get('designation', designation)
                        fournisseur = piece_row.get('fournisseur', fournisseur)
                    
                    # Déduire le stock
                    conn.execute(f"""
                        UPDATE pieces_rechange
                        SET stock_actuel = stock_actuel - {ph}
                        WHERE reference = {ph}
                    """, (qty, ref))
                    
                    cout_piece = prix * qty
                    total_cout_pieces += cout_piece
                    
                    # Format: Désignation | Ref: XXX | Fournisseur: YYY | Qty: Z (sans prix)
                    piece_line = f"{designation} | Ref: {ref} | Fournisseur: {fournisseur} | Qty: {qty}"
                    synthese_pieces.append(piece_line)
        else:
            print(f"[CLOTURE] Aucune pièce à déduire (pieces_a_deduire={pieces_a_deduire})")

        pieces_str = "\n".join(synthese_pieces)

        # Calculer le coût main d'oeuvre (taux_horaire × durée)
        # NOTE: cout = main d'oeuvre ONLY (NOT including pieces)
        # cout_pieces = pieces cost ONLY (stored separately)
        duree_val = duree_minutes if duree_minutes is not None else 0
        cout_main_oeuvre = 0.0
        try:
            config_row = conn.execute("SELECT valeur FROM config_client WHERE cle = 'taux_horaire_technicien'").fetchone()
            if not config_row or not config_row["valeur"]:
                raise ValueError("Taux horaire technicien non configuré dans les paramètres")
            taux_horaire = float(config_row["valeur"])
        except (ValueError, TypeError) as e:
            raise Exception(f"Erreur configuration: {str(e)}")
        cout_main_oeuvre = round((duree_val / 60) * taux_horaire, 2)

        # 2. Mettre à jour l'intervention (date = date de clôture)
        date_cloture = datetime.now().isoformat()
        
        # Préparer l'UPDATE avec un dictionnaire pour éviter les décalages
        # IMPORTANT: cout = main d'oeuvre ONLY (NOT including pieces)
        # cout_pieces = pieces cost (stored separately)
        # Dashboard calculates total cost as: cout + cout_pieces
        update_data = {
            "statut": "Cloturee",
            "probleme": probleme,
            "cause": cause,
            "solution": solution,
            "duree_minutes": duree_val,
            "cout": cout_main_oeuvre,  # ← Main d'oeuvre ONLY
            "date": date_cloture,
            "date_cloture": date_cloture
        }

        if retour_requis:
            update_data["retour_site_confirme"] = True
            update_data["date_retour_site"] = date_cloture
            update_data["retour_site_confirme_par"] = retour_site_confirme_par or ""
        
        # Ajouter les champs optionnels s'ils sont fournis
        if start_time is not None:
            update_data["start_time"] = start_time
        if end_time is not None:
            update_data["end_time"] = end_time
        if duree_deplacement is not None:
            update_data["duree_deplacement"] = duree_deplacement
        if pieces_str:
            update_data["pieces_utilisees"] = pieces_str
            update_data["cout_pieces"] = total_cout_pieces  # ← Pièces ONLY
        
        # Construire l'UPDATE dynamiquement
        set_clauses = [f"{k}=%s" for k in update_data.keys()]
        update_values = list(update_data.values())
        update_values.append(intervention_id)
        
        sql = f"""
            UPDATE interventions
            SET {", ".join(set_clauses)}
            WHERE id={ph}
        """
        conn.execute(sql, update_values)

        synchroniser_statut_equipement(conn, intervention_id, "Cloturee")

        _mark_linked_planning_closed(conn, intervention_id, date_cloture[:10])

        # Preserve the technical cost while deciding the customer-billable
        # share from the contract linked to this scheduled intervention.
        try:
            assess_intervention_contract_coverage_in_savepoint(conn, intervention_id)
        except Exception as exc:
            # Contract assessment must never prevent the operational closure;
            # unresolved cases are assessed again when billing is opened.
            logger.exception("Contract coverage assessment failed for intervention #%s: %s", intervention_id, exc)

        # 3. Récupérer le code erreur associé pour l'auto-apprentissage
        row = conn.execute(f"SELECT code_erreur, type_intervention, type_erreur FROM interventions WHERE id={ph}", (intervention_id,)).fetchone()
        code_erreur = row["code_erreur"] if row else ""

        # 4. Auto-Learning : Alimenter la table solutions si un code erreur existe
        # (sauf pour les Formations qui n'ont pas de diagnostic technique)
        type_intervention = row["type_intervention"] if row else ""
        type_erreur_val = row["type_erreur"] if row else "Hardware"
        if code_erreur and type_intervention != "Formation":
            conn.execute(f"""
                INSERT INTO solutions (mot_cle, type, priorite, cause, solution, validated_by, updated_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                ON CONFLICT(mot_cle) DO UPDATE SET
                    cause=excluded.cause,
                    solution=excluded.solution,
                    updated_at=excluded.updated_at,
                    validated_by='Auto-Learning'
            """, (code_erreur, type_erreur_val or "Hardware", "MOYENNE", cause, solution, "SAV-Auto", datetime.now().isoformat()))

    return True, "Intervention clôturée, stock mis à jour et connaissances sauvegardées !"



# ==========================================
# FONCTIONS CRUD — CONFORMITÉ / QHSE
# ==========================================

def lire_conformite(client=None):
    """Lit les contrôles de conformité, optionnellement filtrés par client."""
    query = "SELECT id, equipement, client, type_controle, description, date_controle, date_expiration, fichier_nom, statut, notes, created_by, created_at FROM conformite"
    params = []
    if client:
        query += " WHERE client = %s"
        params.append(client)
    query += " ORDER BY date_expiration ASC"
    with get_db() as conn:
        return read_sql(query, conn, params=params)


def ajouter_conformite(data, fichier_bytes=None):
    """Ajoute un contrôle de conformité avec fichier PDF optionnel."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO conformite (equipement, client, type_controle, description,
                                     date_controle, date_expiration, fichier_nom, fichier_data,
                                     statut, notes, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get("equipement", ""),
            data.get("client", ""),
            data.get("type_controle", ""),
            data.get("description", ""),
            data.get("date_controle", ""),
            data.get("date_expiration", ""),
            data.get("fichier_nom", ""),
            fichier_bytes,
            data.get("statut", "Conforme"),
            data.get("notes", ""),
            data.get("created_by", ""),
        ))
    return True


def supprimer_conformite(conformite_id):
    """Supprime un contrôle de conformité."""
    with get_db() as conn:
        conn.execute("DELETE FROM conformite WHERE id = %s", (conformite_id,))
    return True


def lire_fichier_conformite(conformite_id):
    """Récupère le fichier PDF d'un contrôle de conformité."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT fichier_nom, fichier_data FROM conformite WHERE id = %s",
            (conformite_id,)
        ).fetchone()
        if row and row["fichier_data"]:
            return row["fichier_nom"], bytes(row["fichier_data"])
    return None, None
