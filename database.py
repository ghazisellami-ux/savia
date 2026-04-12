# ==========================================
# 💾 GESTION BASE DE DONNÉES (WRAPPER SQLITE)
# ==========================================
"""
Couche de compatibilité : redirige vers db_engine.py.
Maintient la même API que l'ancien module Excel pour toutes les pages existantes.
"""
import os
import pandas as pd
from config import EXCEL_PATH
from db_engine import (
    init_db,
    lire_base as _lire_base,
    ajouter_code as _ajouter_code,
    ajouter_codes_batch as _ajouter_codes_batch,
    lire_equipements as _lire_equipements,
    ajouter_equipement as _ajouter_equipement,
    supprimer_equipement as _supprimer_equipement,
    modifier_equipement,
    lire_equipement_par_id,
    lire_interventions,
    ajouter_intervention,
    lire_planning,
    ajouter_planning,
    update_planning_statut,
    lire_pieces,
    ajouter_piece,
    update_stock_piece,
    log_audit,
    lire_audit,
    get_config,
    set_config,
    migrer_depuis_excel,
)


def lire_base(excel_path=None):
    """Lit les bases CODES et SOLUTIONS. Retourne (hex_db, sol_db)."""
    return _lire_base()


def ajouter_code(excel_path, code, message, cause, solution, type_err, priorite):
    """Ajoute ou met à jour un code d'erreur dans la base."""
    return _ajouter_code(code, message, cause, solution, type_err, priorite)


def ajouter_codes_batch(excel_path, rows_hex, rows_txt):
    """Ajoute des codes en lot."""
    return _ajouter_codes_batch(rows_hex, rows_txt)


def lire_historique(excel_path=None):
    """DEPRECATED: Lit l'historique pour les analyses prédictives. Redirige vers interventions."""
    print("WARNING: lire_historique is deprecated. Use lire_interventions instead.")
    from db_engine import lire_interventions
    return lire_interventions()


def enregistrer_evenement(excel_path, machine, code, type_err, severite="MOYENNE"):
    """DEPRECATED: Enregistre un événement dans l'historique."""
    print("WARNING: enregistrer_evenement is deprecated.")
    return True


def lire_equipements(excel_path=None):
    """Lit la liste des équipements."""
    return _lire_equipements()


def ajouter_equipement(excel_path, equipement_dict):
    """Ajoute un équipement au parc."""
    return _ajouter_equipement(equipement_dict)


def supprimer_equipement(excel_path, equip_id):
    """Supprime un équipement par son ID."""
    return _supprimer_equipement(equip_id)


def lire_feuille(excel_path=None, sheet_name=""):
    """Compatibilité : lit une 'feuille' depuis SQLite au lieu d'Excel."""
    from db_engine import get_db, read_sql
    try:
        with get_db() as conn:
            if "CODE" in sheet_name.upper():
                return read_sql(
                    "SELECT code AS Code, message AS Message, niveau AS Niveau, type AS Type FROM codes_erreurs",
                    conn)
            elif "SOLUTION" in sheet_name.upper():
                return read_sql(
                    "SELECT mot_cle AS Mot_Cle, type AS Type, priorite AS Priorite, cause AS Cause, solution AS Solution FROM solutions",
                    conn)
            else:
                return pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def lire_telemetry(machine, sensor_type=None, hours=24):
    """Lit l'historique de télémétrie (Wrapper)."""
    from db_engine import lire_telemetry as _lire_telemetry
    return _lire_telemetry(machine, sensor_type, hours)
