"""Client, equipment, catalogue, and technical-document persistence."""

import json
import re
import unicodedata
import pandas as pd
from urllib.parse import quote
from urllib.request import Request, urlopen

from database.core import _trigger_backup, get_db, logger, read_sql
from repositories.knowledge import _fix_df_text
from repositories.equipment_status import (
    EQUIPMENT_OPERATIONAL,
    ACTIVE_INTERVENTION_STATUSES,
    _is_out_of_service,
    enregistrer_historique_statut_equipement,
    reconcilier_statuts_equipements,
)

__all__ = [
    "ClientHasEquipmentsError",
    "EquipmentHasTechnicalDocumentsError",
    "EquipmentLinkedToContractsError",
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
    "lire_modeles_equipement",
    "ajouter_modele_equipement",
    "lire_services_equipement",
    "ajouter_service_equipement",
    "lire_fournisseurs",
    "ajouter_fournisseur",
    "lire_types_equipement_custom",
    "ajouter_type_equipement_custom",
    "lire_types_intervention_custom",
    "ajouter_type_intervention_custom",
    "lire_types_client_custom",
    "ajouter_type_client_custom",
    "lire_villes_custom",
    "ajouter_ville_custom",
    "supprimer_ville_custom",
    "lire_pays_custom",
    "ajouter_pays_custom",
    "supprimer_pays_custom",
    "modifier_ville_custom",
    "lire_domaines_custom",
    "ajouter_domaine_custom",
    "_ensure_domaines_custom_table",
    "supprimer_domaine_custom",
    "lire_equipement_par_id",
    "lire_historique_statut_equipement",
    "remettre_equipement_en_service",
    "ajouter_document_technique",
    "lire_documents_techniques",
    "lire_document_technique_contenu",
    "lire_document_technique_stockage",
    "supprimer_document_technique",
    "lire_tous_documents_techniques",
]

# Historique supprimé au profit de la table interventions.


class ClientHasEquipmentsError(ValueError):
    """Raised when a client still owns equipment and cannot be deleted."""

    def __init__(self, client_name, equipment_count):
        self.client_name = str(client_name or "").strip()
        self.equipment_count = int(equipment_count or 0)
        super().__init__(
            f"Le client {self.client_name} possède encore "
            f"{self.equipment_count} équipement(s)."
        )


class EquipmentLinkedToContractsError(ValueError):
    """Raised when an equipment is still covered by one or more contracts."""

    def __init__(self, equipment_name, contract_count):
        self.equipment_name = str(equipment_name or "").strip()
        self.contract_count = int(contract_count or 0)
        super().__init__(
            f"L'équipement {self.equipment_name} est encore rattaché à "
            f"{self.contract_count} contrat(s)."
        )


class EquipmentHasTechnicalDocumentsError(ValueError):
    """Raised when technical documents must be removed before equipment."""

    def __init__(self, equipment_name, document_count):
        self.equipment_name = str(equipment_name or "").strip()
        self.document_count = int(document_count or 0)
        super().__init__(
            f"L'équipement {self.equipment_name} possède encore "
            f"{self.document_count} document(s) technique(s)."
        )


COUNTRY_NAMES = {
    "TN": "Tunisie", "DZ": "Algérie", "MA": "Maroc", "SN": "Sénégal",
    "FR": "France", "US": "États-Unis", "QA": "Qatar", "SA": "Arabie saoudite",
}

COUNTRY_CENTERS = {
    "ITALIE": (41.8719, 12.5674), "ITALIA": (41.8719, 12.5674), "ITALY": (41.8719, 12.5674),
    "ESPAGNE": (40.4637, -3.7492), "SPAIN": (40.4637, -3.7492), "ESPANA": (40.4637, -3.7492),
    "ALLEMAGNE": (51.1657, 10.4515), "GERMANY": (51.1657, 10.4515),
    "PORTUGAL": (39.3999, -8.2245), "BELGIQUE": (50.5039, 4.4699), "BELGIUM": (50.5039, 4.4699),
}


def geocode_country(country_name):
    """Retourne le centre GPS d'un pays, avec alias locaux puis Nominatim."""
    name = str(country_name or "").strip()
    if not name:
        return None, None
    normalized = unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode("ascii").upper()
    if normalized in COUNTRY_CENTERS:
        return COUNTRY_CENTERS[normalized]
    try:
        url = f"https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&featuretype=country&q={quote(name)}"
        request = Request(url, headers={"User-Agent": "SAVIA/1.0 country-geocoder"})
        with urlopen(request, timeout=4) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result:
            return float(result[0]["lat"]), float(result[0]["lon"])
    except Exception as exc:
        logger.warning("Géocodage impossible pour le pays %s: %s", name, exc)
    return None, None


def lire_pays_custom():
    """Retourne les pays ajoutés manuellement."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pays_custom (
                id SERIAL PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                nom TEXT NOT NULL UNIQUE,
                flag TEXT DEFAULT '🌍',
                latitude REAL NULL,
                longitude REAL NULL,
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        rows = conn.execute("SELECT id, code, nom, flag, latitude, longitude FROM pays_custom ORDER BY nom").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if item.get("latitude") is None or item.get("longitude") is None:
                latitude, longitude = geocode_country(item.get("nom"))
                if latitude is not None and longitude is not None:
                    conn.execute(
                        "UPDATE pays_custom SET latitude = %s, longitude = %s WHERE code = %s",
                        (latitude, longitude, item["code"]),
                    )
                    item["latitude"], item["longitude"] = latitude, longitude
            result.append(item)
        return result


def ajouter_pays_custom(nom, flag="🌍"):
    """Ajoute un pays et génère un code stable réutilisable pour ses villes."""
    country_name = str(nom or "").strip()
    if not country_name:
        raise ValueError("Nom du pays requis")
    normalized = unicodedata.normalize("NFD", country_name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_").upper()[:36]
    if not slug:
        raise ValueError("Nom de pays invalide")
    code = f"CUSTOM_{slug}"
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pays_custom (
                id SERIAL PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                nom TEXT NOT NULL UNIQUE,
                flag TEXT DEFAULT '🌍',
                latitude REAL NULL,
                longitude REAL NULL,
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        latitude, longitude = geocode_country(country_name)
        conn.execute(
            """INSERT INTO pays_custom (code, nom, flag, latitude, longitude)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (code) DO UPDATE SET
                 nom = EXCLUDED.nom,
                 latitude = COALESCE(pays_custom.latitude, EXCLUDED.latitude),
                 longitude = COALESCE(pays_custom.longitude, EXCLUDED.longitude)""",
            (code, country_name, str(flag or "🌍"), latitude, longitude),
        )
        row = conn.execute("SELECT id, code, nom, flag, latitude, longitude FROM pays_custom WHERE code = %s", (code,)).fetchone()
    return dict(row)


def supprimer_pays_custom(code):
    """Supprime un pays personnalisé; ses villes restent supprimables séparément."""
    with get_db() as conn:
        conn.execute("DELETE FROM pays_custom WHERE code = %s", (str(code or "").strip().upper(),))
    return True


def geocode_city(country_code, city):
    """Résout une ville en coordonnées GPS via Nominatim, avec échec silencieux."""
    city = str(city or "").strip()
    if not city:
        return None, None
    code = str(country_code or "").strip().upper()
    country = COUNTRY_NAMES.get(code, "")
    if not country and code:
        try:
            with get_db() as conn:
                row = conn.execute("SELECT nom FROM pays_custom WHERE code = %s", (code,)).fetchone()
                country = row["nom"] if row else ""
        except Exception:
            country = ""
    query = f"{city}, {country}" if country else city
    try:
        url = f"https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q={quote(query)}"
        request = Request(url, headers={"User-Agent": "SAVIA/1.0 city-geocoder"})
        with urlopen(request, timeout=4) as response:
            result = json.loads(response.read().decode("utf-8"))
        if result:
            return float(result[0]["lat"]), float(result[0]["lon"])
    except Exception as exc:
        logger.warning("Géocodage impossible pour %s: %s", query, exc)
    return None, None


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
    latitude = client_dict.get("latitude")
    longitude = client_dict.get("longitude")
    if client_dict.get("ville") and (latitude is None or longitude is None):
        latitude, longitude = geocode_city(client_dict.get("country_code", ""), client_dict.get("ville", ""))
    with get_db() as conn:
        conn.execute("""
            INSERT INTO clients (nom, matricule_fiscale, country_code, ville, contact, telephone, adresse,
                                code_client, region, type_client, international, latitude, longitude)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(nom) DO UPDATE SET
                matricule_fiscale=excluded.matricule_fiscale,
                country_code=excluded.country_code,
                ville=excluded.ville,
                contact=excluded.contact,
                telephone=excluded.telephone,
                adresse=excluded.adresse,
                code_client=excluded.code_client,
                region=excluded.region,
                type_client=excluded.type_client,
                international=excluded.international,
                latitude=excluded.latitude,
                longitude=excluded.longitude
        """, (
            client_dict.get("nom", ""),
            client_dict.get("matricule_fiscale", ""),
            str(client_dict.get("country_code", "TN") or "TN").strip().upper(),
            client_dict.get("ville", ""),
            client_dict.get("contact", ""),
            client_dict.get("telephone", ""),
            client_dict.get("adresse", ""),
            client_dict.get("code_client", ""),
            client_dict.get("region", ""),
            client_dict.get("type_client", ""),
            bool(client_dict.get("international", False)),
            latitude,
            longitude,
        ))
    _trigger_backup()
    return True


def modifier_client(client_id, client_dict):
    """Modifie un client existant."""
    latitude = client_dict.get("latitude")
    longitude = client_dict.get("longitude")
    if client_dict.get("ville") and (latitude is None or longitude is None):
        latitude, longitude = geocode_city(client_dict.get("country_code", ""), client_dict.get("ville", ""))
    with get_db() as conn:
        conn.execute("""
            UPDATE clients SET
                nom = %s, matricule_fiscale = %s, country_code = %s, ville = %s,
                contact = %s, telephone = %s, adresse = %s,
                code_client = %s, region = %s, type_client = %s, international = %s,
                latitude = %s, longitude = %s
            WHERE id = %s
        """, (
            client_dict.get("nom", ""),
            client_dict.get("matricule_fiscale", ""),
            str(client_dict.get("country_code", "TN") or "TN").strip().upper(),
            client_dict.get("ville", ""),
            client_dict.get("contact", ""),
            client_dict.get("telephone", ""),
            client_dict.get("adresse", ""),
            client_dict.get("code_client", ""),
            client_dict.get("region", ""),
            client_dict.get("type_client", ""),
            bool(client_dict.get("international", False)),
            latitude,
            longitude,
            client_id,
        ))
    _trigger_backup()
    return True


def supprimer_client(client_id):
    """Delete a client only after all of its equipment has been removed."""
    with get_db() as conn:
        client = conn.execute(
            "SELECT id, nom FROM clients WHERE id = %s FOR UPDATE",
            (client_id,),
        ).fetchone()
        if not client:
            return False

        client_name = dict(client).get("nom", "")
        equipment_row = conn.execute(
            """SELECT COUNT(*) AS cnt
               FROM equipements
               WHERE LOWER(BTRIM(COALESCE(client, ''))) = LOWER(BTRIM(%s))""",
            (client_name,),
        ).fetchone()
        equipment_count = int(dict(equipment_row).get("cnt", 0)) if equipment_row else 0
        if equipment_count:
            raise ClientHasEquipmentsError(client_name, equipment_count)

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
        # Keep legacy/manual rows consistent with the current intervention
        # lifecycle before exposing equipment status to any page or report.
        reconcilier_statuts_equipements()
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
            if "Statut" in df.columns:
                # Keep the legacy value readable while exposing the new
                # business vocabulary to the web clients.
                df["Statut"] = df["Statut"].replace({"Actif": "Opérationnel"})
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
    """Ajoute un équipement au parc et retourne son identifiant.

    Le nom n'est pas une identité métier fiable : un même client peut posséder
    plusieurs appareils du même type/nom. L'identifiant technique ``id`` reste
    la clé de référence ; le numéro de série peut compléter l'identification.
    """
    with get_db() as conn:
        row = conn.execute("""
            INSERT INTO equipements (nom, type, fabricant, modele, num_serie,
                                     date_installation, derniere_maintenance, statut, notes,
                                     client, matricule_fiscale, document_technique,
                                     domaine, est_annexe, garantie_debut, garantie_duree, ville, region, service)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            equipement_dict.get("Nom", ""),
            equipement_dict.get("Type", ""),
            equipement_dict.get("Fabricant", ""),
            equipement_dict.get("Modele", ""),
            equipement_dict.get("NumSerie", ""),
            equipement_dict.get("DateInstallation", ""),
            equipement_dict.get("DernieresMaintenance", ""),
            equipement_dict.get("Statut", EQUIPMENT_OPERATIONAL),
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
        )).fetchone()
    _trigger_backup()
    return int(row["id"]) if row else None


def supprimer_equipement(equip_id):
    """Delete equipment only after dependent business data is removed.

    Technical documents and contract coverage must both be removed explicitly
    so that deleting an equipment never silently destroys related records.
    """
    with get_db() as conn:
        equipment = conn.execute(
            "SELECT id, nom FROM equipements WHERE id = %s FOR UPDATE",
            (equip_id,),
        ).fetchone()
        if not equipment:
            return None

        equipment_name = dict(equipment).get("nom", "")
        document_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM documents_techniques WHERE equipement_id = %s",
            (equip_id,),
        ).fetchone()
        document_count = int(dict(document_row).get("cnt", 0)) if document_row else 0
        if document_count:
            raise EquipmentHasTechnicalDocumentsError(equipment_name, document_count)

        contract_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM contrats_equipements WHERE equipement_id = %s",
            (equip_id,),
        ).fetchone()
        contract_count = int(dict(contract_row).get("cnt", 0)) if contract_row else 0
        if contract_count:
            raise EquipmentLinkedToContractsError(equipment_name, contract_count)

        conn.execute("DELETE FROM equipements WHERE id = %s", (equip_id,))
    _trigger_backup()
    return True


def lire_historique_statut_equipement(equip_id, limit=100):
    """Return the most recent auditable status transitions for an equipment."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT h.id, h.equipement_id, h.ancien_statut, h.nouveau_statut,
                      h.source, h.intervention_id, h.raison, h.change_par, h.change_le,
                      COALESCE(NULLIF(BTRIM(u.nom_complet), ''), h.change_par, '')
                          AS change_par_nom_complet,
                      e.nom AS equipement, e.client
               FROM equipement_statut_historique h
               JOIN equipements e ON e.id = h.equipement_id
               LEFT JOIN utilisateurs u
                 ON LOWER(BTRIM(u.username)) = LOWER(BTRIM(h.change_par))
               WHERE h.equipement_id = %s
               ORDER BY h.change_le DESC, h.id DESC
               LIMIT %s""",
            (equip_id, max(1, min(int(limit or 100), 500))),
        ).fetchall()
    return [dict(row) for row in rows]


def remettre_equipement_en_service(equip_id, change_par="", raison="Remise en service manuelle"):
    """Manually return an equipment to operational status."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, nom, client, statut FROM equipements WHERE id = %s FOR UPDATE",
            (equip_id,),
        ).fetchone()
        if not row:
            raise ValueError("Équipement introuvable")

        active_placeholders = ", ".join(["%s"] * len(ACTIVE_INTERVENTION_STATUSES))
        active = conn.execute(
            f"""SELECT 1
                FROM interventions i
                LEFT JOIN equipements e ON e.id = %s
                WHERE LOWER(i.machine) = LOWER(%s)
                  AND LOWER(COALESCE(NULLIF(i.client, ''), e.client, '')) =
                      LOWER(COALESCE(%s, ''))
                  AND i.statut IN ({active_placeholders})
                LIMIT 1""",
            (equip_id, row["nom"], row.get("client") or "", *ACTIVE_INTERVENTION_STATUSES),
        ).fetchone()
        if active:
            raise ValueError("Impossible de remettre l'équipement en service : une intervention est encore active")

        old_status = row.get("statut") or ""
        if old_status != EQUIPMENT_OPERATIONAL:
            conn.execute(
                "UPDATE equipements SET statut = %s WHERE id = %s",
                (EQUIPMENT_OPERATIONAL, equip_id),
            )
            enregistrer_historique_statut_equipement(
                conn,
                equip_id,
                old_status,
                EQUIPMENT_OPERATIONAL,
                source="manuel",
                raison=raison,
                change_par=change_par,
            )
    _trigger_backup()
    return True


def modifier_equipement(equip_id, equipement_dict, change_par=""):
    """Modifie un équipement existant par son ID."""
    with get_db() as conn:
        previous = conn.execute(
            "SELECT statut FROM equipements WHERE id = %s FOR UPDATE",
            (equip_id,),
        ).fetchone()
        previous_status = previous.get("statut") if previous else ""
        next_status = equipement_dict.get("Statut", EQUIPMENT_OPERATIONAL)
        if previous and _is_out_of_service(previous_status) and not _is_out_of_service(next_status):
            raise ValueError("Utilisez l'action Remettre en service pour réactiver manuellement cet équipement")
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
            next_status,
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
        if previous and previous_status != next_status:
            enregistrer_historique_statut_equipement(
                conn,
                equip_id,
                previous_status or "",
                next_status,
                source="manuel",
                raison=equipement_dict.get("RaisonStatut", ""),
                change_par=change_par,
            )
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


def lire_modeles_equipement(domaine="", type_equipement="", fabricant=""):
    """Retourne les modèles associés au contexte domaine/type/fabricant."""
    clauses = []
    params = []
    for column, value in (("domaine", domaine), ("type_equipement", type_equipement), ("fabricant", fabricant)):
        value = str(value or "").strip()
        if value:
            clauses.append(f"LOWER(BTRIM({column})) = LOWER(BTRIM(%s))")
            params.append(value)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT id, nom, domaine, type_equipement, fabricant FROM modeles_equipement{where} ORDER BY nom",
            tuple(params),
        ).fetchall()
        return [dict(r) for r in rows]


def ajouter_modele_equipement(nom, domaine, type_equipement, fabricant):
    """Ajoute un modèle dans son contexte de classification, sans doublon."""
    values = tuple(str(value or "").strip() for value in (nom, domaine, type_equipement, fabricant))
    with get_db() as conn:
        conn.execute(
            """INSERT INTO modeles_equipement (nom, domaine, type_equipement, fabricant)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            values,
        )
    return True


def lire_services_equipement():
    """Retourne les services personnalisés enregistrés."""
    with get_db() as conn:
        rows = conn.execute("SELECT id, nom FROM services_equipement ORDER BY nom").fetchall()
        return [dict(r) for r in rows]


def ajouter_service_equipement(nom):
    """Ajoute un service au catalogue, sans doublon."""
    with get_db() as conn:
        conn.execute("INSERT INTO services_equipement (nom) VALUES (%s) ON CONFLICT DO NOTHING", (str(nom or "").strip(),))
    return True


def lire_fournisseurs():
    """Retourne la liste des fournisseurs de pièces enregistrés."""
    with get_db() as conn:
        rows = conn.execute("SELECT id, nom FROM fournisseurs ORDER BY nom").fetchall()
        return [dict(r) for r in rows]


def ajouter_fournisseur(nom):
    """Ajoute un fournisseur de pièces. Ignore s'il existe déjà."""
    with get_db() as conn:
        conn.execute("INSERT INTO fournisseurs (nom) VALUES (%s) ON CONFLICT DO NOTHING", (nom.strip(),))
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


def lire_villes_custom(country_code=None):
    """Retourne les villes ajoutées manuellement, éventuellement pour un pays."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS villes_custom (
                id SERIAL PRIMARY KEY,
                country_code TEXT NOT NULL,
                nom TEXT NOT NULL,
                latitude REAL NULL,
                longitude REAL NULL,
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(country_code, nom)
            )
        """)
        if country_code:
            rows = conn.execute(
                "SELECT id, country_code, nom, latitude, longitude FROM villes_custom WHERE country_code = %s ORDER BY nom",
                (str(country_code).strip().upper(),),
            ).fetchall()
        else:
            rows = conn.execute("SELECT id, country_code, nom, latitude, longitude FROM villes_custom ORDER BY country_code, nom").fetchall()
        return [dict(r) for r in rows]


def ajouter_ville_custom(country_code, nom, latitude=None, longitude=None):
    """Ajoute une ville réutilisable pour un pays donné. Ignore les doublons."""
    country = str(country_code or "").strip().upper()
    city = str(nom or "").strip()
    if not country or not city:
        raise ValueError("Pays et ville requis")
    if latitude is None or longitude is None:
        latitude, longitude = geocode_city(country, city)
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS villes_custom (
                id SERIAL PRIMARY KEY,
                country_code TEXT NOT NULL,
                nom TEXT NOT NULL,
                latitude REAL NULL,
                longitude REAL NULL,
                date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(country_code, nom)
            )
        """)
        conn.execute(
            """
            INSERT INTO villes_custom (country_code, nom, latitude, longitude)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (country_code, nom) DO UPDATE SET
                latitude = COALESCE(villes_custom.latitude, excluded.latitude),
                longitude = COALESCE(villes_custom.longitude, excluded.longitude)
            """,
            (country, city, latitude, longitude),
        )
    return {"country_code": country, "nom": city, "latitude": latitude, "longitude": longitude}


def supprimer_ville_custom(country_code, nom):
    """Supprime une ville personnalisée pour un pays."""
    with get_db() as conn:
        conn.execute(
            "DELETE FROM villes_custom WHERE country_code = %s AND nom = %s",
            (str(country_code or "").strip().upper(), str(nom or "").strip()),
        )
    return True


def modifier_ville_custom(country_code, nom, nouveau_nom):
    """Renomme une ville personnalisée et recalcule son emplacement GPS."""
    country = str(country_code or "").strip().upper()
    old_name = str(nom or "").strip()
    new_name = str(nouveau_nom or "").strip()
    if not country or not old_name or not new_name:
        raise ValueError("Pays et noms de ville requis")
    with get_db() as conn:
        existing = conn.execute(
            "SELECT latitude, longitude FROM villes_custom WHERE country_code = %s AND nom = %s",
            (country, old_name),
        ).fetchone()
        if not existing:
            raise ValueError("Ville introuvable")
        latitude, longitude = geocode_city(country, new_name)
        if latitude is None or longitude is None:
            latitude, longitude = existing["latitude"], existing["longitude"]
        try:
            conn.execute(
                """UPDATE villes_custom SET nom = %s, latitude = %s, longitude = %s
                   WHERE country_code = %s AND nom = %s""",
                (new_name, latitude, longitude, country, old_name),
            )
        except Exception as exc:
            raise ValueError("Cette ville existe déjà pour ce pays") from exc
    return {"country_code": country, "nom": new_name, "latitude": latitude, "longitude": longitude}


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
