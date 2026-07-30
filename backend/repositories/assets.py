"""Client, equipment, catalogue, and technical-document persistence."""

import pandas as pd

from database.core import _trigger_backup, get_db, logger, read_sql
from repositories.knowledge import _fix_df_text

__all__ = [
    "lire_clients",
    "ajouter_client",
    "modifier_client",
    "supprimer_client",
    "migrer_clients_depuis_equipements",
    "lire_equipements",
    "chercher_client_par_matricule",
    "ajouter_equipement",
    "supprimer_equipement",
    "modifier_equipement",
    "lire_fabricants",
    "ajouter_fabricant",
    "lire_types_equipement_custom",
    "ajouter_type_equipement_custom",
    "lire_types_intervention_custom",
    "ajouter_type_intervention_custom",
    "lire_types_client_custom",
    "ajouter_type_client_custom",
    "lire_domaines_custom",
    "ajouter_domaine_custom",
    "_ensure_domaines_custom_table",
    "supprimer_domaine_custom",
    "lire_equipement_par_id",
    "ajouter_document_technique",
    "lire_documents_techniques",
    "lire_document_technique_contenu",
    "lire_document_technique_stockage",
    "supprimer_document_technique",
    "lire_tous_documents_techniques",
]

# Historique supprimé au profit de la table interventions.


# ==========================================
# FONCTIONS CRUD — CLIENTS
# ==========================================

def lire_clients():
    """Récupère la liste des clients."""
    try:
        with get_db() as conn:
            df = read_sql("SELECT * FROM clients ORDER BY nom", conn)
        if not df.empty:
            df = _fix_df_text(df)
        return df
    except Exception as e:
        logger.error(f"Erreur lire_clients: {e}")
        return pd.DataFrame()


def ajouter_client(client_dict):
    """Ajoute un nouveau client."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO clients (nom, matricule_fiscale, ville, contact, telephone, adresse,
                                code_client, region, type_client, international)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(nom) DO UPDATE SET
                matricule_fiscale=excluded.matricule_fiscale,
                ville=excluded.ville,
                contact=excluded.contact,
                telephone=excluded.telephone,
                adresse=excluded.adresse,
                code_client=excluded.code_client,
                region=excluded.region,
                type_client=excluded.type_client,
                international=excluded.international
        """, (
            client_dict.get("nom", ""),
            client_dict.get("matricule_fiscale", ""),
            client_dict.get("ville", ""),
            client_dict.get("contact", ""),
            client_dict.get("telephone", ""),
            client_dict.get("adresse", ""),
            client_dict.get("code_client", ""),
            client_dict.get("region", ""),
            client_dict.get("type_client", ""),
            bool(client_dict.get("international", False)),
        ))
    _trigger_backup()
    return True


def modifier_client(client_id, client_dict):
    """Modifie un client existant."""
    with get_db() as conn:
        conn.execute("""
            UPDATE clients SET
                nom = %s, matricule_fiscale = %s, ville = %s,
                contact = %s, telephone = %s, adresse = %s,
                code_client = %s, region = %s, type_client = %s, international = %s
            WHERE id = %s
        """, (
            client_dict.get("nom", ""),
            client_dict.get("matricule_fiscale", ""),
            client_dict.get("ville", ""),
            client_dict.get("contact", ""),
            client_dict.get("telephone", ""),
            client_dict.get("adresse", ""),
            client_dict.get("code_client", ""),
            client_dict.get("region", ""),
            client_dict.get("type_client", ""),
            bool(client_dict.get("international", False)),
            client_id,
        ))
    _trigger_backup()
    return True


def supprimer_client(client_id):
    """Supprime un client par son ID."""
    with get_db() as conn:
        conn.execute("DELETE FROM clients WHERE id = %s", (client_id,))
    _trigger_backup()
    return True


def migrer_clients_depuis_equipements():
    """Auto-import existing clients from equipements table into the clients table."""
    try:
        with get_db() as conn:
            existing = conn.execute("SELECT COUNT(*) as cnt FROM clients").fetchone()
            if existing and dict(existing).get("cnt", 0) > 0:
                return  # Already migrated
            rows = conn.execute("""
                SELECT DISTINCT client, matricule_fiscale, ville
                FROM equipements
                WHERE client IS NOT NULL AND client != ''
            """).fetchall()
            for row in rows:
                r = dict(row)
                nom = r.get("client", "")
                if not nom:
                    continue
                conn.execute("""
                    INSERT INTO clients (nom, matricule_fiscale, ville) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                """, (nom, r.get("matricule_fiscale", ""), r.get("ville", "")))
            logger.info(f"Migré {len(rows)} clients depuis equipements")
    except Exception as e:
        logger.error(f"Migration clients: {e}")


# ==========================================
# FONCTIONS CRUD — ÉQUIPEMENTS
# ==========================================

def lire_equipements():
    """
    Récupère la liste complète des équipements du parc.
    
    Logic:
        Exécute SELECT, renomme les colonnes pour la compatibilité UI,
        gère la valeur par défaut pour le client et nettoie l'encodage texte.
        
    Returns:
        pd.DataFrame: Liste des équipements.
    """
    try:
        with get_db() as conn:
            # Select only necessary columns to reduce data transfer and processing
            df = read_sql("""
                SELECT id, nom, type, fabricant, modele, num_serie, 
                       date_installation, derniere_maintenance, statut, notes, 
                       client, domaine, est_annexe, garantie_debut, garantie_duree,
                       ville, region, service
                FROM equipements 
                ORDER BY client, nom
            """, conn)
        if not df.empty:
            rename_map = {
                "nom": "Nom", "type": "Type", "fabricant": "Fabricant",
                "modele": "Modele", "num_serie": "NumSerie",
                "date_installation": "DateInstallation",
                "derniere_maintenance": "DernieresMaintenance",
                "statut": "Statut", "notes": "Notes",
                "client": "Client", "ville": "Ville", "region": "Region",
            }
            df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
            if "Client" in df.columns:
                df["Client"] = df["Client"].fillna("Centre Principal")
            # Only fix text on columns that are likely to have encoding issues
            text_columns = ["Nom", "Type", "Fabricant", "Modele", "Notes", "Client"]
            df = _fix_df_text(df, columns=text_columns)
        return df
    except Exception as e:
        logger.error(f"Erreur lire_equipements: {e}")
        return pd.DataFrame()


def chercher_client_par_matricule(matricule_fiscale):
    """Cherche un client existant par sa matricule fiscale. Retourne le nom du client ou None."""
    if not matricule_fiscale or not matricule_fiscale.strip():
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT client FROM equipements WHERE matricule_fiscale = %s LIMIT 1",
            (matricule_fiscale.strip(),)
        ).fetchone()
        if row:
            return row["client"]
    return None


def ajouter_equipement(equipement_dict):
    """Ajoute un équipement au parc. Unique par combinaison (nom + client)."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO equipements (nom, type, fabricant, modele, num_serie,
                                     date_installation, derniere_maintenance, statut, notes,
                                     client, matricule_fiscale, document_technique,
                                     domaine, est_annexe, garantie_debut, garantie_duree, ville, region, service)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(nom, client) DO UPDATE SET
                type=excluded.type, fabricant=excluded.fabricant, modele=excluded.modele,
                num_serie=excluded.num_serie, date_installation=excluded.date_installation,
                derniere_maintenance=excluded.derniere_maintenance, statut=excluded.statut,
                notes=excluded.notes, matricule_fiscale=excluded.matricule_fiscale,
                document_technique=excluded.document_technique,
                domaine=excluded.domaine, est_annexe=excluded.est_annexe,
                garantie_debut=excluded.garantie_debut, garantie_duree=excluded.garantie_duree,
                ville=excluded.ville, region=excluded.region, service=excluded.service
        """, (
            equipement_dict.get("Nom", ""),
            equipement_dict.get("Type", ""),
            equipement_dict.get("Fabricant", ""),
            equipement_dict.get("Modele", ""),
            equipement_dict.get("NumSerie", ""),
            equipement_dict.get("DateInstallation", ""),
            equipement_dict.get("DernieresMaintenance", ""),
            equipement_dict.get("Statut", "Actif"),
            equipement_dict.get("Notes", ""),
            equipement_dict.get("Client", "Centre Principal"),
            equipement_dict.get("MatriculeFiscale", ""),
            equipement_dict.get("DocumentTechnique", ""),
            equipement_dict.get("Domaine", "Radiologie"),
            bool(equipement_dict.get("EstAnnexe", False)),
            equipement_dict.get("GarantieDebut", ""),
            int(equipement_dict.get("GarantieDuree", 0) or 0),
            equipement_dict.get("Ville", ""),
            equipement_dict.get("Region", ""),
            equipement_dict.get("Service", ""),
        ))
    _trigger_backup()
    return True


def supprimer_equipement(equip_id):
    """Supprime un équipement par son ID."""
    with get_db() as conn:
        conn.execute("DELETE FROM equipements WHERE id = %s", (equip_id,))
    _trigger_backup()
    return True


def modifier_equipement(equip_id, equipement_dict):
    """Modifie un équipement existant par son ID."""
    with get_db() as conn:
        conn.execute("""
            UPDATE equipements SET
                nom = %s, type = %s, fabricant = %s, modele = %s, num_serie = %s,
                date_installation = %s, derniere_maintenance = %s, statut = %s,
                notes = %s, client = %s, matricule_fiscale = %s, document_technique = %s,
                domaine = %s, est_annexe = %s, garantie_debut = %s, garantie_duree = %s,
                ville = %s, region = %s, service = %s
            WHERE id = %s
        """, (
            equipement_dict.get("Nom", ""),
            equipement_dict.get("Type", ""),
            equipement_dict.get("Fabricant", ""),
            equipement_dict.get("Modele", ""),
            equipement_dict.get("NumSerie", ""),
            equipement_dict.get("DateInstallation", ""),
            equipement_dict.get("DernieresMaintenance", ""),
            equipement_dict.get("Statut", "Actif"),
            equipement_dict.get("Notes", ""),
            equipement_dict.get("Client", "Centre Principal"),
            equipement_dict.get("MatriculeFiscale", ""),
            equipement_dict.get("DocumentTechnique", ""),
            equipement_dict.get("Domaine", "Radiologie"),
            bool(equipement_dict.get("EstAnnexe", False)),
            equipement_dict.get("GarantieDebut", ""),
            int(equipement_dict.get("GarantieDuree", 0) or 0),
            equipement_dict.get("Ville", ""),
            equipement_dict.get("Region", ""),
            equipement_dict.get("Service", ""),
            equip_id,
        ))
    _trigger_backup()
    return True


def lire_fabricants():
    """Retourne la liste des fabricants enregistrés."""
    with get_db() as conn:
        rows = conn.execute("SELECT id, nom FROM fabricants ORDER BY nom").fetchall()
        return [dict(r) for r in rows]


def ajouter_fabricant(nom):
    """Ajoute un fabricant. Ignore si déjà existant."""
    with get_db() as conn:
        conn.execute("INSERT INTO fabricants (nom) VALUES (%s) ON CONFLICT DO NOTHING", (nom.strip(),))
    return True


def lire_types_equipement_custom(domaine=""):
    """Retourne la liste des types d'équipement personnalisés pour un domaine."""
    with get_db() as conn:
        ph = "%s"
        rows = conn.execute(
            f"SELECT id, nom, domaine FROM types_equipement_custom WHERE domaine = {ph} ORDER BY nom",
            (domaine,)
        ).fetchall()
        return [dict(r) for r in rows]


def ajouter_type_equipement_custom(nom, domaine=""):
    """Ajoute un type d'équipement personnalisé. Ignore si déjà existant pour ce domaine."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO types_equipement_custom (nom, domaine) VALUES (%s, %s) ON CONFLICT (nom, domaine) DO NOTHING",
            (nom.strip(), domaine)
        )
    return True


def lire_types_intervention_custom():
    """Retourne la liste des types d'intervention personnalisés."""
    with get_db() as conn:
        ph = "%s"
        rows = conn.execute("SELECT id, nom FROM types_intervention_custom ORDER BY nom").fetchall()
        return [dict(r) for r in rows]


def ajouter_type_intervention_custom(nom):
    """Ajoute un type d'intervention personnalisé. Ignore si déjà existant."""
    ph = "%s"
    with get_db() as conn:
        conn.execute(f"INSERT INTO types_intervention_custom (nom) VALUES ({ph}) ON CONFLICT (nom) DO NOTHING", (nom.strip(),))
    return True


def lire_types_client_custom():
    """Retourne les types de clients ajoutés manuellement."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS types_client_custom (
                id SERIAL PRIMARY KEY,
                nom TEXT NOT NULL UNIQUE,
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        rows = conn.execute("SELECT id, nom FROM types_client_custom ORDER BY nom").fetchall()
        return [dict(r) for r in rows]


def ajouter_type_client_custom(nom):
    """Ajoute un type de client personnalisé. Ignore les doublons."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS types_client_custom (
                id SERIAL PRIMARY KEY,
                nom TEXT NOT NULL UNIQUE,
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT INTO types_client_custom (nom) VALUES (%s) ON CONFLICT (nom) DO NOTHING",
            (nom.strip(),),
        )
    return True


def lire_domaines_custom():
    """Retourne la liste des domaines médicaux personnalisés."""
    with get_db() as conn:
        _ensure_domaines_custom_table(conn)
        rows = conn.execute("SELECT id, nom FROM domaines_custom ORDER BY nom").fetchall()
        return [dict(r) for r in rows]


def ajouter_domaine_custom(nom):
    """Ajoute un domaine médical personnalisé et retourne son enregistrement."""
    nom = str(nom or "").strip()
    if not nom:
        raise ValueError("Le nom du domaine est requis")

    with get_db() as conn:
        _ensure_domaines_custom_table(conn)
        conn.execute(
            "INSERT INTO domaines_custom (nom) VALUES (%s) ON CONFLICT (nom) DO NOTHING",
            (nom,)
        )
        row = conn.execute(
            "SELECT id, nom FROM domaines_custom WHERE nom = %s",
            (nom,)
        ).fetchone()
        if not row:
            raise RuntimeError("Le domaine n'a pas pu être enregistré")
        return dict(row)


def _ensure_domaines_custom_table(conn):
    """Garantit la présence de la table avant chaque lecture ou écriture."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS domaines_custom (
            id SERIAL PRIMARY KEY,
            nom TEXT UNIQUE NOT NULL,
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def supprimer_domaine_custom(nom):
    """Supprime un domaine médical personnalisé et ses types associés."""
    with get_db() as conn:
        # Supprimer les types d'équipement associés au domaine
        conn.execute("DELETE FROM types_equipement_custom WHERE domaine = %s", (nom.strip(),))
        # Supprimer le domaine
        conn.execute("DELETE FROM domaines_custom WHERE nom = %s", (nom.strip(),))
    return True


def lire_equipement_par_id(equip_id):
    """Lit un équipement par son ID."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM equipements WHERE id = %s", (equip_id,)).fetchone()
        if row:
            return dict(row)
    return None


# ==========================================
# FONCTIONS CRUD — DOCUMENTS TECHNIQUES
# ==========================================

def ajouter_document_technique(equipement_id, nom_fichier, contenu_base64, *, storage_key=None,
                              content_type=None, size_bytes=None, sha256=None):
    """Save document metadata; new files live in private object storage."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO documents_techniques
            (equipement_id, nom_fichier, contenu_base64, storage_key, content_type, size_bytes, sha256)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (equipement_id, nom_fichier, contenu_base64, storage_key, content_type, size_bytes, sha256))
    return True


def lire_documents_techniques(equipement_id):
    """Lit les documents techniques d'un équipement (métadonnées sans contenu pour la perf)."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, nom_fichier, date_ajout FROM documents_techniques WHERE equipement_id = %s ORDER BY date_ajout DESC",
            (equipement_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def lire_document_technique_contenu(doc_id):
    """Lit le contenu base64 d'un document technique par son ID."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT contenu_base64, nom_fichier, storage_key, content_type,
                      size_bytes, sha256 FROM documents_techniques WHERE id = %s""",
            (doc_id,)
        ).fetchone()
        if row:
            return dict(row)
    return None


def supprimer_document_technique(doc_id):
    """Supprime un document technique par son ID."""
    with get_db() as conn:
        conn.execute("DELETE FROM documents_techniques WHERE id = %s", (doc_id,))
    return True


def lire_document_technique_stockage(doc_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT storage_key FROM documents_techniques WHERE id = %s", (doc_id,)
        ).fetchone()
        return row.get("storage_key") if row else None


def lire_tous_documents_techniques():
    """Lit tous les documents techniques avec les infos de l'équipement associé."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT d.id, d.nom_fichier, d.date_ajout, d.equipement_id,
                   e.nom AS equipement_nom, e.fabricant, e.modele, e.type AS equipement_type,
                   e.client
            FROM documents_techniques d
            JOIN equipements e ON d.equipement_id = e.id
            ORDER BY d.date_ajout DESC
        """).fetchall()
        return [dict(r) for r in rows]
