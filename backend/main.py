# ==========================================
# 🚀 SAVIA FastAPI Backend
# ==========================================
"""
FastAPI backend for the SAVIA Next.js frontend.
Replaces Flask api_server.py with modern async endpoints.
"""
import math
import os
import base64
import tempfile
import jwt
import bcrypt
import logging
import auth
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fastapi import FastAPI, Depends, HTTPException, Query, Header, status, UploadFile, File, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from db_engine import (
    init_db, get_db, read_sql, _trigger_backup,
    lire_equipements, ajouter_equipement, modifier_equipement, supprimer_equipement,
    lire_interventions, ajouter_intervention, update_intervention_statut, cloturer_intervention,
    lire_pieces, ajouter_piece, modifier_piece, supprimer_piece,
    lire_notifications_pieces, compter_notifications_non_lues, ajouter_notification_piece,
    marquer_notification_lue, marquer_notification_traitee, notifications_rupture_pour_piece,
    ajouter_piece_demandee, lire_pieces_demandees_en_attente, resoudre_piece_demandee, lire_toutes_pieces_demandees,
    lire_contrats, ajouter_contrat, modifier_contrat, supprimer_contrat, generer_planning_from_contrat, get_contract_equipements,
    lire_conformite, ajouter_conformite, supprimer_conformite,
    lire_planning, ajouter_planning, update_planning_statut, supprimer_planning,
    lire_techniciens, ajouter_technicien, update_technicien, supprimer_technicien,
    lire_base,
    lire_audit, log_audit,
    get_config, set_config,
    lire_demandes_intervention,
    lire_clients as db_lire_clients, ajouter_client, modifier_client, supprimer_client,
    migrer_clients_depuis_equipements,
    lire_fabricants, ajouter_fabricant,
    lire_types_equipement_custom, ajouter_type_equipement_custom,
    lire_types_intervention_custom, ajouter_type_intervention_custom,
    lire_notification_schedules, sauvegarder_notification_schedules_batch,
    predict_commande_date, predict_pieces_a_commander,
    update_piece_parameters_batch, calculate_piece_parameters,
)

logger = logging.getLogger("savia-api")

# ── Helper function to get technician full name from username ─────────
def _get_technician_fullname(username: str) -> str:
    """
    Converts a username to technician full name (nom + prenom).
    If not found, returns the username as fallback.
    """
    if not username:
        return ""
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT nom, prenom FROM techniciens WHERE username = ?",
                (username,)
            ).fetchone()
            if row:
                nom = row.get("nom", "").strip()
                prenom = row.get("prenom", "").strip()
                return f"{prenom} {nom}".strip() if prenom else nom
    except Exception as e:
        logger.debug(f"Failed to get technician name for {username}: {e}")
    return username  # Fallback to username if not found


import re as _re

def _extract_words(text: str) -> list:
    """
    Extrait tous les mots significatifs d'un texte en supprimant la ponctuation.
    NE PAS filtrer les mots courts (inclure les prénoms comme "Ali", "Al", etc).
    
    Ex: "Salah Al Salah, Ahmed Ben Salah" → ["salah", "al", "salah", "ahmed", "ben", "salah"]
    Ex: "Ali Ben Haj" → ["ali", "ben", "haj"]
    """
    # Remplacer toute ponctuation par des espaces, puis split
    cleaned = _re.sub(r'[,;/\-_\.\(\)\[\]]+', ' ', text.lower())
    # Garder TOUS les mots non-vides (ne pas filtrer par len > 1)
    return [w for w in cleaned.split() if w.strip()]


def _tech_name_matches(user_name: str, technicien_field: str) -> bool:
    """
    Vérifie si le nom du technicien connecté correspond au champ technicien d'une intervention.
    
    Gère correctement :
    - Ordre inversé des noms ("Salah Al Salah" vs "Al Salah Salah")
    - Noms multiples séparés par virgule ("Salah Al Salah, Ahmed Ben Salah")
    - Ponctuation dans les noms
    - Noms courts et prénoms ("Ali", "Al", "A", etc)
    - Évite les faux positifs par sous-chaîne ("al" ne matche PAS "Salah" mais "ali" = "ali")
    
    Returns True si TOUS les mots du nom utilisateur
    apparaissent comme mots entiers dans le champ technicien.
    """
    if not user_name or not technicien_field:
        logger.warning(f"[_tech_name_matches] Empty inputs: user_name='{user_name}', technicien_field='{technicien_field}'")
        return False
    
    user_words = _extract_words(user_name)
    tech_words = _extract_words(technicien_field)
    
    logger.info(f"[_tech_name_matches] Comparing: user='{user_name}' (words={user_words}) vs tech='{technicien_field}' (words={tech_words})")
    
    # IMPORTANT: Si l'utilisateur n'a aucun mot (nom vide?), refuser
    if not user_words:
        logger.warning(f"[_tech_name_matches] No user words extracted from '{user_name}'")
        return False
    
    # IMPORTANT: Si le champ technicien est vide, refuser
    if not tech_words:
        logger.warning(f"[_tech_name_matches] No tech words extracted from '{technicien_field}'")
        return False
    
    # Tous les mots de l'utilisateur doivent être présents dans le champ technicien
    result = all(word in tech_words for word in user_words)
    logger.info(f"[_tech_name_matches] Result: {result} (all user_words in tech_words: {[word in tech_words for word in user_words]})")
    return result


def _tech_name_or_username_matches(user_name_or_username: str, technicien_field: str) -> bool:
    """
    Vérifie si le nom OU username du technicien correspond au champ technicien.
    Utile pour les filtres où on peut avoir des usernames comme 'tech_07' ou des noms comme 'Salah Al Salah'.
    
    Returns True si:
    - C'est une correspondance exacte par username (case-insensitive), OU
    - C'est une correspondance par nom (case-insensitive word matching)
    """
    if not user_name_or_username or not technicien_field:
        return False
    
    # Vérifier correspondance exacte par username (ex: "tech_07" == "tech_07")
    if user_name_or_username.lower() == technicien_field.lower():
        return True
    
    # Sinon, vérifier correspondance par nom
    return _tech_name_matches(user_name_or_username, technicien_field)


# ── Auto-copy DejaVu Sans from matplotlib on startup ─────────────────
def _ensure_dejavu_font():
    import shutil
    dst = "/app/DejaVuSans.ttf"
    if os.path.exists(dst): return
    try:
        import matplotlib
        src = os.path.join(os.path.dirname(matplotlib.__file__),
                           "mpl-data", "fonts", "ttf", "DejaVuSans.ttf")
        if os.path.exists(src):
            shutil.copy2(src, dst)
            logger.info(f"DejaVu Sans copied: {os.path.getsize(dst):,} bytes")
        else:
            logger.warning("DejaVu not found in matplotlib")
    except Exception as _e:
        logger.warning(f"DejaVu copy failed: {_e}")

_ensure_dejavu_font()

# ── Auto-convert Font Awesome WOFF2 → TTF on startup ─────────────────
def _ensure_fa_font():
    import shutil, subprocess as _sp
    dst = "/app/fa-solid-900.ttf"
    if os.path.exists(dst): return
    src_woff2 = "/usr/local/lib/node_modules/@fortawesome/fontawesome-free/webfonts/fa-solid-900.woff2"
    if not os.path.exists(src_woff2):
        logger.warning("FA woff2 not found - run: npm install @fortawesome/fontawesome-free")
        return
    try:
        from fontTools.ttLib import TTFont
        t = TTFont(src_woff2)
        t.flavor = None
        t.save(dst)
        logger.info(f"Font Awesome TTF ready: {os.path.getsize(dst):,} bytes")
    except Exception as _e:
        logger.warning(f"FA font conversion failed: {_e}")

_ensure_fa_font()
# ─────────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)

# ---- Config ----
JWT_SECRET = os.getenv("JWT_SECRET", "sic-terrain-secret-2026")
JWT_EXPIRY_HOURS = 72
security = HTTPBearer(auto_error=False)

IS_PRODUCTION = os.getenv("NODE_ENV") == "production"

# ---- App ----
app = FastAPI(
    title="SAVIA API",
    description="Backend API for SAVIA — Superviseur Intelligent Clinique",
    version="2.0.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    auth.creer_admin_defaut()
    _ensure_dejavu_font()
    _ensure_fa_font()
    # Migration: colonnes fiche signée
    try:
        with get_db() as conn:
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_photo_nom TEXT DEFAULT ''")
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_photo_data BYTEA")
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fiche_validation TEXT DEFAULT 'En attente'")
        logger.info("✅ Migration fiche_photo: colonnes OK")
    except Exception as e:
        logger.error(f"❌ Migration fiche_photo échouée: {e}")
    
    # Vérifier et ajouter colonnes time persistence
    try:
        from db_engine import verifier_et_migrer_schema
        verifier_et_migrer_schema()
        logger.info("✅ Migration schema (time persistence): OK")
    except Exception as e:
        logger.error(f"❌ Migration schema échouée: {e}")
    except Exception as e:
        logger.info(f"Migration fiche_photo (déjà faite ou erreur): {e}")
    # Migration: planning_id + facture_envoyee on interventions
    try:
        with get_db() as conn:
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS planning_id INTEGER")
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS facture_envoyee BOOLEAN DEFAULT FALSE")
            conn.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS rappel_facture_envoye INTEGER DEFAULT 0")
        logger.info("✅ Migration planning_id + facture: colonnes OK")
    except Exception as e:
        logger.info(f"Migration planning_id/facture (déjà faite ou erreur): {e}")
    _start_garantie_daemon()
    # Auto-migrate existing clients from equipements table
    try:
        migrer_clients_depuis_equipements()
    except Exception as e:
        logger.warning(f"Client migration skipped: {e}")
    logger.info("✅ SAVIA FastAPI started — DB initialized")


# ==========================================
# HELPERS
# ==========================================


def check_garantie_expiry():
    """
    Vérifie les garanties équipements qui expirent dans les 30 prochains jours
    et envoie une notification Telegram pour chaque équipement concerné.
    """
    from datetime import date, timedelta
    try:
        df = lire_equipements()
        if df is None or df.empty:
            return []
        today = date.today()
        alert_limit = today + timedelta(days=30)
        alerts = []
        for _, row in df.iterrows():
            debut_str = str(row.get('garantie_debut', '') or '').strip()
            duree = int(row.get('garantie_duree', 0) or 0)
            if not debut_str or not duree:
                continue
            try:
                debut = date.fromisoformat(debut_str[:10])
                # Add years without dateutil
                try:
                    fin = debut.replace(year=debut.year + duree)
                except ValueError:  # Feb 29 edge case
                    fin = debut.replace(year=debut.year + duree, day=28)
                if today <= fin <= alert_limit:
                    alerts.append({
                        'nom': row.get('Nom') or row.get('nom', '?'),
                        'client': row.get('Client') or row.get('client', '?'),
                        'fin': fin.strftime('%d/%m/%Y'),
                        'jours': (fin - today).days,
                    })
            except Exception:
                continue
        if alerts:
            lines = '\n'.join(
                f"  • <b>{a['nom']}</b> ({a['client']}) — expire le {a['fin']} ({a['jours']}j)"
                for a in alerts
            )
            msg = (
                f"⚠️ <b>Garanties expirant bientôt</b>\n\n"
                f"{lines}\n\n"
                f"📅 Vérification SAVIA — {today.strftime('%d/%m/%Y')}"
            )
            _send_telegram_bot("telegram_sav", msg)
            _send_telegram_bot("telegram_manager", msg)
            logger.info(f"Garantie check: {len(alerts)} alerte(s) envoyée(s) aux bots SAV + Manager")
        return alerts
    except Exception as e:
        logger.error(f"Garantie expiry check error: {e}")
        return []


def check_planning_reminder():
    """
    Vérifie les maintenances préventives planifiées dans les prochains jours
    et envoie un rappel Telegram pour chacune.
    
    Utilise le rappel_avant_jours configuré dans le contrat associé.
    Par défaut: 14 jours si pas de contrat ou rappel non configuré.
    """
    from datetime import date, timedelta
    try:
        df = lire_planning()
        if df is None or df.empty:
            return []
        
        today = date.today()
        reminders = []
        
        # Track reminder days used - for logging
        reminder_days_by_contrat = {}
        
        for _, row in df.iterrows():
            statut = str(row.get('statut', '') or '').strip()
            if statut not in ('Planifiée', 'En cours'):
                continue
            
            date_str = str(row.get('date_prevue', '') or '').strip()
            if not date_str:
                continue
            
            try:
                date_prevue = date.fromisoformat(date_str[:10])
                
                # Get contrat_id to fetch rappel_avant_jours
                contrat_id = row.get('contrat_id')
                reminder_days = 14  # Default
                
                if contrat_id:
                    try:
                        with get_db() as conn:
                            ph = "%s"
                            contrat_row = conn.execute(
                                f"SELECT rappel_avant_jours FROM contrats WHERE id = {ph}",
                                (contrat_id,)
                            ).fetchone()
                            if contrat_row:
                                contrat_dict = dict(contrat_row)
                                reminder_days = contrat_dict.get("rappel_avant_jours", 14) or 14
                                reminder_days_by_contrat[contrat_id] = reminder_days
                    except Exception as e:
                        logger.debug(f"Could not fetch rappel_avant_jours for contrat {contrat_id}: {e}")
                
                alert_limit = today + timedelta(days=reminder_days)
                
                if today <= date_prevue <= alert_limit:
                    jours = (date_prevue - today).days
                    reminders.append({
                        'id': row.get('id', '?'),
                        'machine': row.get('machine', '?'),
                        'client': row.get('client', ''),
                        'type': row.get('type_maintenance', 'Préventive'),
                        'description': row.get('description', ''),
                        'date': date_prevue.strftime('%d/%m/%Y'),
                        'technicien': row.get('technicien_assigne', ''),
                        'jours': jours,
                        'reminder_days': reminder_days,
                    })
            except Exception:
                continue
        
        if reminders:
            lines = '\n'.join(
                f"  • <b>{r['machine']}</b>"
                + (f" — {r['client']}" if r['client'] else "")
                + f"\n    📅 {r['date']} ({r['jours']}j)"
                + (f" | 👨‍🔧 {r['technicien']}" if r['technicien'] else " | ⚠️ <b>Technicien non assigné</b>")
                + (f"\n    📝 {r['description'][:60]}" if r['description'] else "")
                for r in sorted(reminders, key=lambda x: x['jours'])
            )
            
            # Build dynamic message based on max reminder days used
            max_days = max((r['reminder_days'] for r in reminders), default=14)
            msg = (
                f"🔧 <b>Rappel Maintenance Préventive</b>\n"
                f"<i>{len(reminders)} maintenance(s) dans les {max_days} prochains jours :</i>\n\n"
                f"{lines}\n\n"
                f"📅 Vérification SAVIA — {today.strftime('%d/%m/%Y')}"
            )
            _send_telegram(msg)
            logger.info(f"Planning reminder: {len(reminders)} rappel(s) envoyé(s) | Jours config: {reminder_days_by_contrat}")
        return reminders
    except Exception as e:
        logger.error(f"Planning reminder check error: {e}")
        return []


def sync_planning_to_interventions():
    """
    Auto-crée des interventions pour les maintenances planifiées dont la date_prevue est aujourd'hui.
    Envoie une notification au Bot Technicien pour chaque intervention créée.
    """
    from datetime import date
    try:
        today = date.today()
        today_str = today.isoformat()
        with get_db() as conn:
            # Trouver les maintenances planifiées pour aujourd'hui sans intervention déjà créée
            planned = conn.execute(
                """SELECT pm.id, pm.machine, pm.client, pm.technicien_assigne, pm.description,
                          pm.type_maintenance
                   FROM planning_maintenance pm
                   WHERE pm.date_prevue = ?
                     AND pm.statut = 'Planifiée'
                     AND NOT EXISTS (
                         SELECT 1 FROM interventions i
                         WHERE i.planning_id = pm.id
                     )""",
                (today_str,)
            ).fetchall()

        created = []
        for row in planned:
            pm = dict(row)
            pm_id = pm['id']
            machine = pm.get('machine', '')
            client = pm.get('client', '')
            technicien = pm.get('technicien_assigne', '')
            description = pm.get('description', '') or f"Maintenance préventive — {machine}"
            notes = f"[{client}] Maintenance préventive planifiée #{pm_id}" if client else f"Maintenance préventive planifiée #{pm_id}"

            with get_db() as conn:
                conn.execute(
                    """INSERT INTO interventions
                       (date, machine, technicien, type_intervention, description,
                        statut, priorite, notes, planning_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (today_str, machine, technicien, 'Préventive', description,
                     'En cours', 'Moyenne', notes, pm_id)
                )
                # Récupérer l'ID de l'intervention créée
                new_id_row = conn.execute(
                    "SELECT id FROM interventions WHERE planning_id = ? ORDER BY id DESC LIMIT 1",
                    (pm_id,)
                ).fetchone()
                new_id = new_id_row['id'] if new_id_row else '?'

                # Mettre à jour le statut du planning
                conn.execute(
                    "UPDATE planning_maintenance SET statut = 'En cours' WHERE id = ?",
                    (pm_id,)
                )

            created.append({
                'intervention_id': new_id,
                'planning_id': pm_id,
                'machine': machine,
                'technicien': technicien,
                'client': client,
            })

        # Envoyer notification groupée au bot Technicien
        if created:
            lines = '\n'.join(
                f"  • <b>#{c['intervention_id']}</b> — {c['machine']}"
                + (f" ({c['client']})" if c['client'] else "")
                + (f"\n    👨‍🔧 {c['technicien']}" if c['technicien'] else "")
                for c in created
            )
            msg = (
                f"🔧 <b>Maintenance Préventive — Jour J</b>\n"
                f"<i>{len(created)} intervention(s) créée(s) automatiquement :</i>\n\n"
                f"{lines}\n\n"
                f"📅 {today.strftime('%d/%m/%Y')}"
            )
            _send_telegram_bot("telegram", msg)
            logger.info(f"Planning sync: {len(created)} intervention(s) créées pour {today_str}")

        return created
    except Exception as e:
        logger.error(f"sync_planning_to_interventions error: {e}")
        return []


def check_stock_alerts():
    """
    Vérifie les pièces en rupture de stock (stock_actuel <= stock_minimum)
    et les interventions en attente de pièce.
    Envoie une notification au Bot Stock.
    """
    try:
        alerts = []
        with get_db() as conn:
            # 1. Pièces en rupture de stock
            ruptures = conn.execute(
                """SELECT reference, designation, stock_actuel, stock_minimum, fournisseur
                   FROM pieces_rechange
                   WHERE stock_actuel <= stock_minimum AND stock_minimum > 0
                   ORDER BY (stock_minimum - stock_actuel) DESC"""
            ).fetchall()
            for r in ruptures:
                d = dict(r)
                alerts.append(
                    f"  🔴 <b>{d.get('designation', d.get('reference', '?'))}</b>"
                    f" — Réf: {d.get('reference', '?')}"
                    f"\n    Stock: <b>{d.get('stock_actuel', 0)}</b> / Min: {d.get('stock_minimum', 0)}"
                    + (f" | Fournisseur: {d['fournisseur']}" if d.get('fournisseur') else "")
                )

            # 2. Interventions en attente de pièce
            attente = conn.execute(
                """SELECT id, machine, technicien FROM interventions
                   WHERE statut = 'En attente de piece'
                   ORDER BY id DESC"""
            ).fetchall()
            for a in attente:
                d = dict(a)
                alerts.append(
                    f"  ⏳ Intervention <b>#{d['id']}</b> — {d.get('machine', '?')}"
                    f" ({d.get('technicien', '?')}) en attente de pièce"
                )

        if alerts:
            from datetime import date
            msg = (
                f"📦 <b>Alerte Stock & Pièces</b>\n"
                f"<i>{len(alerts)} alerte(s) :</i>\n\n"
                + '\n'.join(alerts) + "\n\n"
                f"📅 Vérification SAVIA — {date.today().strftime('%d/%m/%Y')}"
            )
            _send_telegram_bot("telegram_stock", msg)
            logger.info(f"Stock alerts: {len(alerts)} alerte(s) envoyée(s)")
        return alerts
    except Exception as e:
        logger.error(f"check_stock_alerts error: {e}")
        return []


def check_facturation_reminders():
    """
    Vérifie les interventions clôturées pour envoyer des rappels de facturation :
    - Bot SAV : rappel quand une intervention est clôturée depuis ~8 jours (J-2 avant deadline)
    - Bot SAV : rappel quand clôturée depuis ~1 jour (première alerte)
    - Bot Manager : alerte quand la facturation n'a pas eu lieu après 10 jours
    """
    from datetime import date, timedelta
    try:
        today = date.today()
        sav_alerts = []
        manager_alerts = []

        with get_db() as conn:
            # Interventions clôturées avec date_cloture, non encore facturées
            rows = conn.execute(
                """SELECT id, machine, technicien, date_cloture, notes,
                          COALESCE(facture_envoyee, FALSE) as facture_envoyee,
                          COALESCE(rappel_facture_envoye, 0) as rappel_facture_envoye
                   FROM interventions
                   WHERE statut = 'Cloturee'
                     AND date_cloture IS NOT NULL
                     AND COALESCE(facture_envoyee, FALSE) = FALSE
                   ORDER BY date_cloture ASC"""
            ).fetchall()

        for row in rows:
            d = dict(row)
            try:
                dc = d['date_cloture']
                if isinstance(dc, str):
                    cloture_date = date.fromisoformat(str(dc)[:10])
                elif hasattr(dc, 'date'):
                    # datetime object → convert to date
                    cloture_date = dc.date()
                elif hasattr(dc, 'year'):
                    cloture_date = dc
                else:
                    cloture_date = date.fromisoformat(str(dc)[:10])
            except Exception:
                continue

            jours_depuis = (today - cloture_date).days
            rappel_level = d.get('rappel_facture_envoye', 0) or 0
            deadline = cloture_date + timedelta(days=10)
            jours_restants = (deadline - today).days

            # Extraire client depuis notes
            notes = str(d.get('notes', '') or '')
            client = notes[1:notes.index(']')] if notes.startswith('[') and ']' in notes else ''
            machine = d.get('machine', '?')
            int_id = d['id']

            # Rappel SAV : J+1 après clôture (première notification)
            if jours_depuis >= 1 and rappel_level < 1:
                sav_alerts.append({
                    'id': int_id, 'machine': machine, 'client': client,
                    'technicien': d.get('technicien', ''),
                    'jours_restants': jours_restants,
                    'type': 'premier',
                })
                with get_db() as conn:
                    conn.execute("UPDATE interventions SET rappel_facture_envoye = 1 WHERE id = ?", (int_id,))

            # Rappel SAV : J+8 (2 jours avant deadline)
            elif jours_depuis >= 8 and rappel_level < 2:
                sav_alerts.append({
                    'id': int_id, 'machine': machine, 'client': client,
                    'technicien': d.get('technicien', ''),
                    'jours_restants': jours_restants,
                    'type': 'urgent',
                })
                with get_db() as conn:
                    conn.execute("UPDATE interventions SET rappel_facture_envoye = 2 WHERE id = ?", (int_id,))

            # Bot Manager : > 10 jours sans facturation
            if jours_depuis > 10 and rappel_level < 3:
                manager_alerts.append({
                    'id': int_id, 'machine': machine, 'client': client,
                    'technicien': d.get('technicien', ''),
                    'jours_retard': jours_depuis - 10,
                })
                with get_db() as conn:
                    conn.execute("UPDATE interventions SET rappel_facture_envoye = 3 WHERE id = ?", (int_id,))

        # Envoyer notifications SAV
        if sav_alerts:
            lines = '\n'.join(
                f"  {'🔴' if a['type']=='urgent' else '🟡'} <b>#{a['id']}</b> — {a['machine']}"
                + (f" ({a['client']})" if a['client'] else "")
                + f"\n    ⏳ {a['jours_restants']}j restants pour facturer"
                for a in sav_alerts
            )
            msg = (
                f"💰 <b>Rappel Facturation SAV</b>\n"
                f"<i>{len(sav_alerts)} intervention(s) à facturer :</i>\n\n"
                f"{lines}\n\n"
                f"📅 {today.strftime('%d/%m/%Y')}"
            )
            _send_telegram_bot("telegram_sav", msg)
            logger.info(f"Facturation SAV: {len(sav_alerts)} rappel(s) envoyé(s)")

        # Envoyer alertes Manager
        if manager_alerts:
            lines = '\n'.join(
                f"  🚨 <b>#{a['id']}</b> — {a['machine']}"
                + (f" ({a['client']})" if a['client'] else "")
                + f"\n    ⚠️ {a['jours_retard']}j de retard de facturation"
                for a in manager_alerts
            )
            msg = (
                f"🚨 <b>ALERTE — Facturation en retard</b>\n"
                f"<i>{len(manager_alerts)} intervention(s) non facturées après 10 jours :</i>\n\n"
                f"{lines}\n\n"
                f"📅 {today.strftime('%d/%m/%Y')}"
            )
            _send_telegram_bot("telegram_manager", msg)
            logger.info(f"Facturation Manager: {len(manager_alerts)} alerte(s) envoyée(s)")

        return {'sav': len(sav_alerts), 'manager': len(manager_alerts)}
    except Exception as e:
        logger.error(f"check_facturation_reminders error: {e}")
        return {'sav': 0, 'manager': 0}


def check_sla_alerts():
    """
    Vérifie les interventions actives par rapport aux SLA des contrats :
    - ⚠️ Bot SAV : alerte quand une intervention atteint 75% du SLA (zone danger)
    - 🔴 Bot Manager : alerte quand une intervention dépasse le SLA du contrat
    """
    from datetime import datetime as _dt
    
    def _format_hours(hours: float) -> str:
        """Format hours as 'X jours Y heures' or just 'X heures'"""
        if hours < 24:
            return f"{round(hours)}h"
        days = int(hours // 24)
        remaining_hours = int(hours % 24)
        if remaining_hours == 0:
            return f"{days}j"
        return f"{days}j {remaining_hours}h"
    
    try:
        df_contrats = lire_contrats()
        df_interv = lire_interventions()
        df_equip = lire_equipements()

        # Build client → SLA mapping from active contracts
        client_sla = {}
        if df_contrats is not None and not df_contrats.empty:
            for _, c in df_contrats.iterrows():
                cl = c.get("client", "")
                sla_h = c.get("sla_temps_reponse_h", 24)
                statut = str(c.get("statut", "")).lower()
                if cl and "actif" in statut:
                    if cl not in client_sla or sla_h < client_sla[cl]:
                        client_sla[cl] = int(sla_h)

        if not client_sla:
            return  # No active contracts with SLA

        # Build machine → client mapping
        machine_client = {}
        if df_equip is not None and not df_equip.empty:
            for _, eq in df_equip.iterrows():
                machine_client[eq.get("Nom", "")] = eq.get("Client", "")

        now = _dt.now()
        danger_items = []   # 75-100% SLA
        breached_items = [] # >100% SLA

        if df_interv is not None and not df_interv.empty:
            active = df_interv[~df_interv["statut"].str.lower().str.contains("termin|clotur|clôtur", na=False)]
            for _, interv in active.iterrows():
                machine = interv.get("machine", "")
                cl = machine_client.get(machine, "")
                if cl not in client_sla:
                    continue  # No SLA for this client

                sla_h = client_sla[cl]
                start_str = interv.get("date_debut_intervention") or interv.get("date", "")
                try:
                    start = pd.to_datetime(start_str)
                    if pd.isna(start):
                        continue
                except Exception:
                    continue

                elapsed_h = round((now - start).total_seconds() / 3600, 1)
                pct = round((elapsed_h / sla_h) * 100, 1) if sla_h > 0 else 100
                remaining_h = round(sla_h - elapsed_h, 1)

                item = {
                    "id": interv.get("id"),
                    "machine": machine,
                    "client": cl,
                    "technicien": interv.get("technicien", ""),
                    "statut": interv.get("statut", ""),
                    "sla_h": sla_h,
                    "elapsed_h": elapsed_h,
                    "remaining_h": remaining_h,
                    "pct": pct,
                }

                if pct > 100:
                    breached_items.append(item)
                elif pct >= 75:
                    danger_items.append(item)

        # ⚠️ Bot SAV : zone danger (75-100%)
        if danger_items:
            lines = '\n'.join(
                f"  ⚠️ <b>#{d['id']}</b> — {d['machine']}"
                f"\n    👤 {d['client']} | 👷 {d['technicien'] or 'Non assigné'}"
                f"\n    ⏱ {d['elapsed_h']}h / {d['sla_h']}h ({d['pct']}%) — reste {max(0, d['remaining_h'])}h"
                for d in sorted(danger_items, key=lambda x: -x['pct'])
            )
            msg = (
                f"⚠️ <b>ALERTE SLA — Zone Danger</b>\n"
                f"<i>{len(danger_items)} intervention(s) approchent le délai SLA :</i>\n\n"
                f"{lines}\n\n"
                f"📅 {now.strftime('%d/%m/%Y %H:%M')}"
            )
            _send_telegram_bot("telegram_sav", msg)
            logger.info(f"SLA danger alerts: {len(danger_items)} envoyée(s) au bot SAV")

        # 🔴 Bot Manager : dépassement SLA
        if breached_items:
            lines = '\n'.join(
                f"  🔴 <b>#{b['id']}</b> — {b['machine']}"
                f"\n    👤 {b['client']} | 👷 {b['technicien'] or 'Non assigné'}"
                f"\n    ⏱ {b['elapsed_h']}h / {b['sla_h']}h ({b['pct']}%) — <b>DÉPASSÉ de {_format_hours(b['elapsed_h'] - b['sla_h'])}</b>"
                for b in sorted(breached_items, key=lambda x: -x['pct'])
            )
            msg = (
                f"🔴 <b>ALERTE SLA — DÉPASSEMENT</b>\n"
                f"<i>{len(breached_items)} intervention(s) dépassent le délai contractuel :</i>\n\n"
                f"{lines}\n\n"
                f"📅 {now.strftime('%d/%m/%Y %H:%M')}"
            )
            _send_telegram_bot("telegram_manager", msg)
            logger.info(f"SLA breach alerts: {len(breached_items)} envoyée(s) au bot Manager")

    except Exception as e:
        logger.error(f"check_sla_alerts error: {e}")



def check_planning_retard():
    """
    Vérifie les maintenances planifiées en retard (date_prevue passée mais statut toujours 'Planifiée').
    Envoie une alerte au Bot Manager.
    """
    from datetime import date
    try:
        df = lire_planning()
        if df is None or df.empty:
            return
        today = date.today()
        retard_items = []
        for _, row in df.iterrows():
            statut = str(row.get('statut', '') or '').strip()
            if statut != 'Planifiée':
                continue
            date_str = str(row.get('date_prevue', '') or '').strip()
            if not date_str:
                continue
            try:
                date_prevue = date.fromisoformat(date_str[:10])
                if date_prevue < today:
                    jours_retard = (today - date_prevue).days
                    retard_items.append({
                        'id': row.get('id', '?'),
                        'machine': row.get('machine', '?'),
                        'client': row.get('client', ''),
                        'technicien': row.get('technicien_assigne', ''),
                        'date': date_prevue.strftime('%d/%m/%Y'),
                        'jours': jours_retard,
                        'description': row.get('description', ''),
                    })
            except Exception:
                continue

        if retard_items:
            lines = '\n'.join(
                f"  🔴 <b>#{r['id']}</b> — {r['machine']}"
                + (f" — {r['client']}" if r['client'] else "")
                + f"\n    📅 Prévue le {r['date']} (<b>{r['jours']}j de retard</b>)"
                + (f" | 👨‍🔧 {r['technicien']}" if r['technicien'] else " | ⚠️ Technicien non assigné")
                for r in sorted(retard_items, key=lambda x: -x['jours'])
            )
            msg = (
                f"🔴 <b>PLANNING EN RETARD</b>\n"
                f"<i>{len(retard_items)} maintenance(s) non réalisée(s) :</i>\n\n"
                f"{lines}\n\n"
                f"📅 Vérification SAVIA — {today.strftime('%d/%m/%Y')}"
            )
            _send_telegram_bot("telegram_manager", msg)
            logger.info(f"Planning retard: {len(retard_items)} alerte(s) envoyée(s) au bot Manager")
    except Exception as e:
        logger.error(f"check_planning_retard error: {e}")


def _start_garantie_daemon():
    """Lance un thread démon qui vérifie garanties + contrats + rappels planning + sync + facturation toutes les 24h."""
    import threading, time
    LOCK_KEY = "notif_daemon_last_run"

    def _already_ran_today() -> bool:
        """Vérifie si les notifications ont déjà été envoyées aujourd'hui (évite les doublons lors des redéploiements)."""
        from datetime import date
        try:
            with get_db() as conn:
                row = conn.execute("SELECT valeur FROM config_client WHERE cle = ?", (LOCK_KEY,)).fetchone()
                if row:
                    return dict(row)['valeur'] == str(date.today())
            return False
        except Exception:
            return False

    def _mark_ran_today():
        """Marque la date d'aujourd'hui comme traitée."""
        from datetime import date
        try:
            with get_db() as conn:
                conn.execute(
                    """INSERT INTO config_client (cle, valeur) VALUES (?, ?)
                       ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur""",
                    (LOCK_KEY, str(date.today()))
                )
        except Exception as e:
            logger.error(f"Failed to mark notification run: {e}")

    def _get_notification_schedule(bot_key: str) -> dict:
        """Récupère l'horaire de notification pour un bot depuis la base de données."""
        try:
            schedule = lire_notification_schedules()
            for s in schedule:
                if s.get('bot_key') == bot_key:
                    return s
        except Exception as e:
            logger.debug(f"Failed to get notification schedule for {bot_key}: {e}")
        
        # Fallback: horaire par défaut (8h30, tous les jours)
        return {
            'bot_key': bot_key,
            'enabled': 1,
            'hour': 8,
            'minute': 30,
            'days_of_week': '1,2,3,4,5,6,7'
        }

    def _should_send_notifications_today(schedule: dict) -> bool:
        """Vérifie si les notifications doivent être envoyées aujourd'hui selon l'horaire."""
        if schedule.get('enabled') != 1:
            return False
        
        # Vérifier le jour de la semaine (1=Lundi, 7=Dimanche)
        import datetime as _dt
        today_weekday = _dt.date.today().isoweekday()  # 1=Monday, 7=Sunday
        days_str = schedule.get('days_of_week', '1,2,3,4,5,6,7')
        days_list = [int(d.strip()) for d in days_str.split(',') if d.strip().isdigit()]
        
        return today_weekday in days_list

    def _run():
        import datetime as _dt
        time.sleep(30)
        last_run_date = None
        
        while True:
            try:
                # Récupérer l'horaire de notification depuis la base de données
                schedule = _get_notification_schedule('telegram')
                target_hour = schedule.get('hour', 8)
                target_minute = schedule.get('minute', 30)

                # Obtenir l'heure actuelle (heure Tunisie UTC+1)
                try:
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo("Africa/Tunis")
                except Exception:
                    tz = _dt.timezone(_dt.timedelta(hours=1))
                
                now_local = _dt.datetime.now(tz)
                today = now_local.date()

                # Vérifier si c'est l'heure d'envoyer les notifications
                is_target_time = (now_local.hour == target_hour and now_local.minute >= target_minute and now_local.minute < target_minute + 1)
                
                # Vérifier si c'est un jour configuré
                should_send_today = _should_send_notifications_today(schedule)
                
                # Vérifier si on a déjà envoyé aujourd'hui
                already_sent_today = (last_run_date == today)

                if is_target_time and should_send_today and not already_sent_today:
                    logger.info(f"Notifications daemon: déclenchement à {now_local.hour:02d}:{now_local.minute:02d}")
                    
                    # sync_planning_to_interventions crée les interventions ET envoie la notif Jour J
                    try:
                        sync_planning_to_interventions()
                    except Exception as e:
                        logger.error(f"Planning sync daemon error: {e}")

                    try:
                        check_garantie_expiry()
                    except Exception as e:
                        logger.error(f"Garantie daemon error: {e}")
                    try:
                        check_contrat_expiry()
                    except Exception as e:
                        logger.error(f"Contrat daemon error: {e}")
                    try:
                        check_planning_reminder()
                    except Exception as e:
                        logger.error(f"Planning reminder daemon error: {e}")
                    try:
                        check_stock_alerts()
                    except Exception as e:
                        logger.error(f"Stock alerts daemon error: {e}")
                    
                    # Update piece parameters (consommation, equipements, utilisation) from historical data
                    try:
                        result = update_piece_parameters_batch()
                        if result.get('success'):
                            logger.info(f"Piece parameters updated: {result['updated']} pieces, {result['failed']} failed")
                        else:
                            logger.error(f"Piece parameters update error: {result.get('error')}")
                    except Exception as e:
                        logger.error(f"Piece parameters daemon error: {e}")
                    
                    try:
                        check_facturation_reminders()
                    except Exception as e:
                        logger.error(f"Facturation reminders daemon error: {e}")
                    try:
                        check_sla_alerts()
                    except Exception as e:
                        logger.error(f"SLA alerts daemon error: {e}")
                    try:
                        check_planning_retard()
                    except Exception as e:
                        logger.error(f"Planning retard daemon error: {e}")

                    last_run_date = today
                    _mark_ran_today()
                    logger.info("Notifications daemon: cycle terminé")
                
                # Attendre 30 secondes avant de vérifier à nouveau
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Notifications daemon error: {e}")
                time.sleep(30)
                
    threading.Thread(target=_run, daemon=True, name="notifications-daemon").start()
    logger.info("⏰ Notifications daemon: démarré (garanties + contrats + planning + sync + stock + facturation + SLA + retards, horaires configurables)")


def check_contrat_expiry():
    """Vérifie les contrats actifs expirant dans les 30 prochains jours."""
    from datetime import date, timedelta
    try:
        df = lire_contrats()
        if df is None or df.empty:
            return []
        today = date.today()
        alert_limit = today + timedelta(days=30)
        alerts = []
        for _, row in df.iterrows():
            statut = str(row.get('statut', '') or '').strip().lower()
            if statut not in ('actif', 'active', ''):
                continue
            date_fin_str = str(row.get('date_fin', '') or '').strip()
            if not date_fin_str:
                continue
            try:
                date_fin = date.fromisoformat(date_fin_str[:10])
                if today <= date_fin <= alert_limit:
                    jours = (date_fin - today).days
                    alerts.append({
                        'id': row.get('id', '?'),
                        'client': row.get('client') or row.get('Client', '?'),
                        'equipement': row.get('equipement', ''),
                        'type_contrat': row.get('type_contrat', ''),
                        'fin': date_fin.strftime('%d/%m/%Y'),
                        'jours': jours,
                    })
            except Exception:
                continue
        if alerts:
            lines = '\n'.join(
                f"  • <b>#{a['id']}</b> {a['client']}"
                + (f" ({a['equipement']})" if a['equipement'] else "")
                + f" — <i>{a['type_contrat']}</i>"
                + f" — expire le {a['fin']} ({a['jours']}j)"
                for a in alerts
            )
            msg = (
                f"📄 <b>Contrats expirant bientôt</b>\n"
                f"{lines}\n"
                f"📅 Vérification SAVIA — {today.strftime('%d/%m/%Y')}"
            )
            _send_telegram_bot("telegram_sav", msg)
            _send_telegram_bot("telegram_manager", msg)
            logger.info(f"Contrat check: {len(alerts)} alerte(s) envoyée(s) aux bots SAV + Manager")
        return alerts
    except Exception as e:
        logger.error(f"Contrat expiry check error: {e}")
        return []


def _df_to_records(df) -> list:
    """Convert DataFrame to JSON-safe list of dicts."""
    if df is None or df.empty:
        return []
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            if isinstance(v, float) and math.isnan(v):
                r[k] = None
            elif hasattr(v, 'isoformat'):
                r[k] = v.isoformat()
    return records


def _send_telegram_bot(bot_key: str, message: str) -> bool:
    """
    Envoie un message Telegram via un bot spécifique.
    bot_key: 'telegram' (technicien), 'telegram_sav', 'telegram_manager', 'telegram_stock'
    """
    import urllib.request, urllib.parse, json as _json
    token_key = f"{bot_key}_token"
    chat_key = f"{bot_key}_chat_id"
    try:
        with get_db() as conn:
            # Use database-agnostic query (SQLite + PostgreSQL compatible)
            rows = conn.execute(
                "SELECT cle, valeur FROM config_client WHERE cle = ? OR cle = ?",
                (token_key, chat_key)
            ).fetchall()
        config = {r["cle"]: r["valeur"] for r in rows}
        token   = config.get(token_key, "").strip()
        chat_id = config.get(chat_key, "").strip()
        if not token:
            logger.warning(f"Telegram bot '{bot_key}' non configuré (pas de token) — notification ignorée")
            return False
        if not chat_id:
            logger.warning(f"Telegram bot '{bot_key}' pas de chat_id — notification ignorée")
            return False

        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id":    chat_id,
            "text":       message,
            "parse_mode": "HTML",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = _json.loads(resp.read().decode())
        if result.get("ok"):
            logger.info(f"Message Telegram envoyé via {bot_key}")
            return True
        logger.error(f"Telegram API error ({bot_key}): {result}")
        return False
    except Exception as e:
        logger.error(f"Erreur Telegram ({bot_key}): {e}")
        return False


def _send_telegram(message: str) -> bool:
    """Rétrocompatibilité — envoie via le bot technicien."""
    return _send_telegram_bot("telegram", message)


def _verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT and return user payload. Returns guest user if no token (allows public read)."""
    if not credentials:
        return {"sub": "guest", "role": "Lecteur", "nom": "Visiteur"}
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        # Rétrocompatibilité : si Lecteur mais client absent du token, le récupérer en DB
        if payload.get("role") == "Lecteur" and not payload.get("client"):
            try:
                with get_db() as conn:
                    row = conn.execute(
                        "SELECT client FROM utilisateurs WHERE username = ?",
                        (payload.get("sub", ""),)
                    ).fetchone()
                    if row and row["client"]:
                        payload["client"] = row["client"]
            except Exception:
                pass
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expiré")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")



def _optional_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[dict]:
    """Verify JWT if present, return None if missing (allows public read access)."""
    if not credentials:
        return None
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None


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
    username: str
    password: str


@app.get("/")
def root():
    return {"status": "ok", "service": "SAVIA API", "version": "2.0.0"}


@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request):
    ip_address = request.client.host if request.client else "unknown"
    
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM utilisateurs WHERE username = ? AND actif = 1",
            (body.username,)
        ).fetchone()

    if not row or not _verify_password(body.password, row["password_hash"]):
        log_audit(body.username, "LOGIN_FAILED", f"Identifiants incorrects", "auth", ip_address)
        raise HTTPException(status_code=401, detail="Identifiants incorrects")

    user_data = dict(row)
    
    # Log successful login
    log_audit(body.username, "LOGIN", "Connexion réussie", "auth", ip_address)
    
    payload = {
        "sub": user_data["username"],
        "role": user_data["role"],
        "nom": user_data.get("nom_complet", ""),
        "client": user_data.get("client", "") or "",
        "pages_autorisees": user_data.get("pages_autorisees", "") or "",
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    return {
        "token": token,
        "user": {
            "username": user_data["username"],
            "nom": user_data.get("nom_complet", ""),
            "role": user_data["role"],
            "client": user_data.get("client", "") or "",
            "pages_autorisees": user_data.get("pages_autorisees", "") or "",
        }
    }


@app.get("/api/auth/me")
def me(user: dict = Depends(_verify_token)):
    return {"user": user}


def _get_client_filter(user: dict) -> Optional[str]:
    """Retourne le client restricté pour un Lecteur, None sinon (accès total)."""
    if user.get("role") == "Lecteur":
        c = user.get("client", "").strip()
        return c if c else None
    return None


# ==========================================
# DASHBOARD — Aggregated KPIs
# ==========================================

@app.get("/api/dashboard/kpis")
def get_dashboard_kpis(
    client: Optional[str] = None,
    region: Optional[str] = None,
    ville: Optional[str] = None,
    equipment_type: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Compute real KPIs from the database, optionally filtered by client, region, ville, equipment type, and date range."""
    try:
        df_eq = lire_equipements()
        df_int = lire_interventions()
        df_clients = db_lire_clients()  # Get ALL clients from clients table
        
        # Debug logging
        logger.info(f"KPI filters: client={client}, region={region}, ville={ville}, equipment_type={equipment_type}")
        logger.info(f"Initial equipements count: {len(df_eq)}")
        logger.info(f"Initial interventions count: {len(df_int)}")
        logger.info(f"Total clients in database: {len(df_clients)}")

        # Pour Lecteur : forcer le filtre par son client
        effective_client = _get_client_filter(user) or client

        # IMPORTANT: Count unique clients from ALL clients table (not just equipements)
        # This ensures we show all clients, even those without equipment
        nb_clients_all = 0
        if not df_clients.empty and "nom" in df_clients.columns:
            nb_clients_all = len(df_clients["nom"].dropna().unique())

        # Create a COPY of df_eq for CURRENT STATUS calculation (not filtered by date)
        df_eq_for_status = df_eq.copy()
        
        # Filter equipements by client
        if effective_client and not df_eq.empty and "Client" in df_eq.columns:
            df_eq = df_eq[df_eq["Client"].astype(str).str.lower() == effective_client.lower()]
            df_eq_for_status = df_eq_for_status[df_eq_for_status["Client"].astype(str).str.lower() == effective_client.lower()]
            logger.info(f"After client filter: {len(df_eq)} equipements")

        # Filter equipements by region (join with clients table to get region)
        if region and not df_eq.empty and not df_clients.empty:
            if region.lower() == "international":
                # Get international clients
                clients_in_region = df_clients[
                    df_clients["international"].notna() & 
                    (df_clients["international"].astype(bool) == True)
                ]["nom"].tolist() if "international" in df_clients.columns else []
            else:
                # Get clients in this region
                clients_in_region = df_clients[
                    df_clients["region"].notna() & 
                    (df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip())
                ]["nom"].tolist() if "region" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_region and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_region)]
                df_eq_for_status = df_eq_for_status[df_eq_for_status["Client"].astype(str).isin(clients_in_region)]
                logger.info(f"After region filter (via clients): {len(df_eq)} equipements from {len(clients_in_region)} clients")

        # Filter equipements by ville (join with clients table to get ville)
        if ville and not df_eq.empty and not df_clients.empty:
            # Get clients in this ville
            clients_in_ville = df_clients[
                df_clients["ville"].notna() & 
                (df_clients["ville"].astype(str).str.lower().str.strip() == ville.lower().strip())
            ]["nom"].tolist() if "ville" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_ville and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_ville)]
                df_eq_for_status = df_eq_for_status[df_eq_for_status["Client"].astype(str).isin(clients_in_ville)]
                logger.info(f"After ville filter (via clients): {len(df_eq)} equipements from {len(clients_in_ville)} clients")

        # Filter equipements by equipment type
        # Add .str.strip() to handle whitespace and .notna() to handle NULL values
        if equipment_type and not df_eq.empty and "Type" in df_eq.columns:
            df_eq = df_eq[df_eq["Type"].notna() & (df_eq["Type"].astype(str).str.lower().str.strip() == equipment_type.lower().strip())]
            df_eq_for_status = df_eq_for_status[df_eq_for_status["Type"].notna() & (df_eq_for_status["Type"].astype(str).str.lower().str.strip() == equipment_type.lower().strip())]
            logger.info(f"After equipment_type filter: {len(df_eq)} equipements")

        # Filter interventions by client (via matching machines)
        if effective_client and not df_eq.empty and not df_int.empty and "machine" in df_int.columns:
            machines_client = df_eq["Nom"].tolist() if "Nom" in df_eq.columns else []
            df_int = df_int[df_int["machine"].isin(machines_client)]
            logger.info(f"After client intervention filter: {len(df_int)} interventions")

        # Filter interventions by region/ville/type (via matching machines)
        if (region or ville or equipment_type) and not df_int.empty and "machine" in df_int.columns:
            machines_filtered = df_eq["Nom"].tolist() if (not df_eq.empty and "Nom" in df_eq.columns) else []
            df_int = df_int[df_int["machine"].isin(machines_filtered)]
            logger.info(f"After region/ville/type intervention filter: {len(df_int)} interventions")

        # Filter interventions by date range
        if not df_int.empty and "date" in df_int.columns:
            df_int["date"] = pd.to_datetime(df_int["date"], errors="coerce")
            if date_start:
                df_int = df_int[df_int["date"] >= pd.to_datetime(date_start)]
            if date_end:
                df_int = df_int[df_int["date"] <= pd.to_datetime(date_end)]
            logger.info(f"After date filter: {len(df_int)} interventions")

        nb_eq = len(df_eq_for_status) if not df_eq_for_status.empty else 0
        nb_critiques = 0
        dispo = 100.0
        
        # Alertes Critiques = CURRENT equipment status (not filtered by month)
        # Shows all equipment currently in critical/down state
        if not df_eq_for_status.empty and "Statut" in df_eq_for_status.columns:
            nb_critiques = len(df_eq_for_status[df_eq_for_status["Statut"].isin(["Hors Service", "Critique"])])

        # Disponibilité = based on interventions in selected period
        # Equipment with interventions in the period = had issues = not available
        # Disponibilité = % of equipment that had NO interventions in the period
        if not df_int.empty and "machine" in df_int.columns:
            machines_with_issues = df_int["machine"].unique()
            equipment_with_issues_count = len(machines_with_issues)
            available_equipment = nb_eq - equipment_with_issues_count
            dispo = round((available_equipment / nb_eq) * 100, 1) if nb_eq > 0 else 100.0
        elif nb_eq > 0:
            # No interventions in period = all equipment available
            dispo = 100.0

        # Count unique clients
        # If NO filters applied: show ALL clients from clients table (66)
        # If filters applied: show only clients with equipment matching those filters
        nb_clients = 0
        if region or ville or equipment_type or effective_client:
            # Filters applied: count clients from filtered equipements only
            if not df_eq.empty and "Client" in df_eq.columns:
                nb_clients = len(df_eq["Client"].dropna().unique())
        else:
            # No filters applied: show ALL clients from clients table
            nb_clients = nb_clients_all

        # Calculate intervention-based KPIs
        nb_interventions = len(df_int) if not df_int.empty else 0
        
        # Calculate MTBF (Mean Time Between Failures) - average days between interventions
        mtbf = 0.0
        if nb_interventions > 1 and not df_int.empty and "date" in df_int.columns:
            df_int_sorted = df_int.sort_values("date")
            dates = pd.to_datetime(df_int_sorted["date"], errors="coerce").dropna()
            if len(dates) > 1:
                time_diffs = dates.diff().dropna()
                avg_days = time_diffs.dt.total_seconds().mean() / (24 * 3600)  # Convert to days
                mtbf = avg_days * 24 if avg_days > 0 else 0  # Convert to hours
        
        # Calculate MTTR (Mean Time To Repair) - average duration of interventions
        mttr = 0.0
        if not df_int.empty:
            # Check for duration column (could be "duree_intervention", "duree", etc.)
            duration_col = None
            for col in ["duree_intervention", "duree", "duration", "Duree"]:
                if col in df_int.columns:
                    duration_col = col
                    break
            
            if duration_col:
                durations = pd.to_numeric(df_int[duration_col], errors="coerce").dropna()
                if len(durations) > 0:
                    mttr = float(durations.mean())
        
        # Calculate total cost = cout_main_oeuvre + cout_pieces (NOT cout_interventions which double-counts)
        # Only from CLOSED interventions
        cout_main_oeuvre_total = 0.0
        cout_pieces_total = 0.0
        
        if not df_int.empty:
            # First filter to only closed interventions
            status_col = None
            for col in ["Statut", "statut", "status", "Status"]:
                if col in df_int.columns:
                    status_col = col
                    break
            
            if status_col:
                closed_statuses = {"clôturée", "cloturee", "closed", "resolved", "terminée", "terminee", "complétée", "completee"}
                df_int_closed = df_int[df_int[status_col].astype(str).str.lower().str.strip().isin(closed_statuses)]
            else:
                df_int_closed = df_int
            
            # Debug: log available columns
            logger.info(f"Available intervention columns: {list(df_int_closed.columns)}")
            
            # Sum cout_main_oeuvre (column is named "cout" in interventions table)
            for col in ["cout", "cout_main_oeuvre", "main_oeuvre", "cout_mo", "mo_cost", "cout_MO", "Cout_Main_Oeuvre", "Cout_MO"]:
                if col in df_int_closed.columns:
                    mo_costs = pd.to_numeric(df_int_closed[col], errors="coerce").dropna()
                    if len(mo_costs) > 0:
                        cout_main_oeuvre_total = float(mo_costs.sum())
                    logger.info(f"Found {col}: total = {cout_main_oeuvre_total}")
                    break
            
            # Sum cout_pieces
            for col in ["cout_pieces", "pieces", "cout_pieces_utilisees", "pieces_cost", "cout_Pieces", "Cout_Pieces", "Cout_pieces_utilisees", "Cost_Pieces"]:
                if col in df_int_closed.columns:
                    pieces_costs = pd.to_numeric(df_int_closed[col], errors="coerce").dropna()
                    if len(pieces_costs) > 0:
                        cout_pieces_total = float(pieces_costs.sum())
                    logger.info(f"Found {col}: total = {cout_pieces_total}")
                    break
        
        # Total cost = main d'oeuvre + pièces (no double-counting)
        cout_total = cout_main_oeuvre_total + cout_pieces_total
        logger.info(f"Dashboard KPIs: cout_main_oeuvre_total={cout_main_oeuvre_total}, cout_pieces_total={cout_pieces_total}, cout_total={cout_total}")

        # Calculate resolution rate (% of closed interventions)
        taux_resolution = 0.0
        if nb_interventions > 0 and not df_int.empty:
            # Check for status column (could be "Statut", "statut", "status", etc.)
            status_col = None
            for col in ["Statut", "statut", "status", "Status"]:
                if col in df_int.columns:
                    status_col = col
                    break
            
            if status_col:
                # Count closed/resolved interventions
                closed_statuses = {"clôturée", "cloturee", "closed", "resolved", "terminée", "terminee", "complétée", "completee"}
                nb_closed = len(df_int[df_int[status_col].astype(str).str.lower().str.strip().isin(closed_statuses)])
                taux_resolution = round((nb_closed / nb_interventions) * 100, 1) if nb_interventions > 0 else 0

        return {
            "nb_equipements": nb_eq,
            "nb_critiques": nb_critiques,
            "disponibilite": dispo,
            "mtbf": round(mtbf, 1),
            "mttr": round(mttr, 1),
            "cout_total": round(cout_total, 2),
            "nb_interventions": nb_interventions,
            "nb_clients": nb_clients,
            "taux_resolution": taux_resolution,
        }
    except Exception as e:
        logger.error(f"Dashboard KPIs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/health-scores")
def get_health_scores(
    client: Optional[str] = None,
    region: Optional[str] = None,
    ville: Optional[str] = None,
    equipment_type: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Compute health scores per equipment based on intervention history."""
    try:
        # Load data efficiently with selective columns
        df_eq = lire_equipements()
        
        # Load only necessary intervention columns for scoring
        with get_db() as conn:
            int_query = """
            SELECT i.machine, i.type_intervention, i.date, i.statut
            FROM interventions i
            ORDER BY i.date DESC
            """
            df_int = read_sql(int_query, conn)
        
        df_clients = db_lire_clients()  # Get clients table for region/ville filtering

        # Pour Lecteur : forcer le filtre par son client
        effective_client = _get_client_filter(user) or client

        # Filter equipements by client
        if effective_client and not df_eq.empty and "Client" in df_eq.columns:
            df_eq = df_eq[df_eq["Client"].astype(str).str.lower() == effective_client.lower()]

        # Filter equipements by region (join with clients table to get region)
        if region and not df_eq.empty and not df_clients.empty:
            if region.lower() == "international":
                # Get international clients
                clients_in_region = df_clients[
                    df_clients["international"].notna() & 
                    (df_clients["international"].astype(bool) == True)
                ]["nom"].tolist() if "international" in df_clients.columns else []
            else:
                # Get clients in this region
                clients_in_region = df_clients[
                    df_clients["region"].notna() & 
                    (df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip())
                ]["nom"].tolist() if "region" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_region and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_region)]

        # Filter equipements by ville (join with clients table to get ville)
        if ville and not df_eq.empty and not df_clients.empty:
            # Get clients in this ville
            clients_in_ville = df_clients[
                df_clients["ville"].notna() & 
                (df_clients["ville"].astype(str).str.lower().str.strip() == ville.lower().strip())
            ]["nom"].tolist() if "ville" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_ville and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_ville)]

        # Filter equipements by equipment type
        if equipment_type and not df_eq.empty and "Type" in df_eq.columns:
            df_eq = df_eq[df_eq["Type"].notna() & (df_eq["Type"].astype(str).str.lower().str.strip() == equipment_type.lower().strip())]

        # Filter interventions by date range
        if not df_int.empty and "date" in df_int.columns:
            df_int["date"] = pd.to_datetime(df_int["date"], errors="coerce")
            if date_start:
                df_int = df_int[df_int["date"] >= pd.to_datetime(date_start)]
            if date_end:
                df_int = df_int[df_int["date"] <= pd.to_datetime(date_end)]

        scores = []

        if df_eq.empty:
            return []

        # Compute period duration in months (for rate-based scoring)
        period_months = 12.0  # default: 1 year
        if date_start and date_end:
            import datetime as _dt
            try:
                d0 = _dt.date.fromisoformat(str(date_start))
                d1 = _dt.date.fromisoformat(str(date_end))
                days = max(1, (d1 - d0).days + 1)
                period_months = max(0.1, days / 30.0)
            except Exception:
                period_months = 12.0

        # Exclude tracabilite interventions from panne count
        TRACABILITE = {"installation", "formation"}
        df_sav = df_int.copy()
        if not df_sav.empty and "type_intervention" in df_sav.columns:
            df_sav = df_sav[~df_sav["type_intervention"].str.lower().isin(TRACABILITE)]

        # Get current date for recent intervention calculation
        import datetime as _dt
        today = _dt.date.today()
        thirty_days_ago = today - _dt.timedelta(days=30)

        seen_keys = set()
        for _, eq in df_eq.iterrows():
            nom = eq.get("Nom", "")
            client_val = str(eq.get("Client", "") or "")
            statut = str(eq.get("Statut", "")).lower()
            dedup_key = (nom.lower(), client_val.lower())
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            pannes = 0
            recent_interventions = 0
            if not df_sav.empty and "machine" in df_sav.columns:
                # Case-insensitive matching for machine names
                pannes = len(df_sav[df_sav["machine"].str.lower() == nom.lower()])
                # Count interventions in last 30 days
                df_machine = df_sav[df_sav["machine"].str.lower() == nom.lower()]
                if not df_machine.empty and "date" in df_machine.columns:
                    df_machine_recent = df_machine[df_machine["date"] >= pd.Timestamp(thirty_days_ago)]
                    recent_interventions = len(df_machine_recent)

            # Score based on absolute number of pannes in the selected period
            # Do NOT normalize by period duration - use absolute counts
            # This ensures monthly view shows actual interventions for that month
            if pannes <= 0:
                score = 100
            elif pannes <= 1:
                score = 90
            elif pannes <= 2:
                score = 78
            elif pannes <= 3:
                score = 65
            elif pannes <= 5:
                score = 48
            elif pannes <= 10:
                score = 30
            elif pannes <= 15:
                score = 18
            else:
                score = 10

            # Apply penalties for critical status and recent interventions
            # If equipment is in critical status, apply significant penalty
            if statut in ["critique", "hors service", "en panne"]:
                score = min(score, 35)  # Cap score at 35 for critical equipment
                if recent_interventions >= 2:
                    score = min(score, 20)  # Further reduce if multiple recent interventions
                elif recent_interventions >= 1:
                    score = min(score, 25)  # Reduce if at least one recent intervention

            # If equipment has multiple recent interventions (last 30 days), flag as at-risk
            elif recent_interventions >= 3:
                score = min(score, 40)  # Flag as at-risk if 3+ interventions in 30 days
            elif recent_interventions >= 2:
                score = min(score, 50)  # Moderate risk if 2 interventions in 30 days

            tendance = "stable"
            if pannes > 3:
                tendance = "baisse"
            elif pannes == 0:
                tendance = "hausse"

            scores.append({
                "machine": nom,
                "score": score,
                "tendance": tendance,
                "pannes": pannes,
                "client": client_val,
            })

        return sorted(scores, key=lambda x: x["score"])
    except Exception as e:
        logger.error(f"Erreur get_health_scores: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ÉQUIPEMENTS
# ==========================================

@app.get("/api/equipements")
def get_equipements(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    df = lire_equipements()
    # Priority: explicit ?client= param, then user's client filter
    client_filter = client or _get_client_filter(user)
    if client_filter and not df.empty and "Client" in df.columns:
        df = df[df["Client"].astype(str).str.lower() == client_filter.lower()]
    return _df_to_records(df)


@app.post("/api/equipements")
def create_equipement(body: dict, user: dict = Depends(_verify_token)):
    # Check permission
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins"
        )
    
    ajouter_equipement(body)
    # Return the ID of the created/upserted equipment
    nom = body.get("Nom", "")
    client = body.get("Client", "Centre Principal")
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM equipements WHERE nom = ? AND client = ?",
            (nom, client)
        ).fetchone()
    equip_id = dict(row)["id"] if row else None
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({"equipement": nom, "client": client, "id": equip_id}, ensure_ascii=False)
    log_audit(username, "CREATE_EQUIPEMENT", details, "equipements")
    
    return {"ok": True, "id": equip_id}


@app.put("/api/equipements/{equip_id}")
def update_equipement(equip_id: int, body: dict, user: dict = Depends(_verify_token)):
    modifier_equipement(equip_id, body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({"equipement_id": equip_id, "changes": body}, ensure_ascii=False)
    log_audit(username, "UPDATE_EQUIPEMENT", details, "equipements")
    
    return {"ok": True}


@app.delete("/api/equipements/{equip_id}")
def delete_equipement(equip_id: int, user: dict = Depends(_verify_token)):
    # Get equipment name before deleting for logging
    try:
        with get_db() as conn:
            row = conn.execute("SELECT nom, client FROM equipements WHERE id = ?", (equip_id,)).fetchone()
            equip_name = dict(row)["nom"] if row else "Unknown"
    except:
        equip_name = "Unknown"
    
    supprimer_equipement(equip_id)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({"equipement_id": equip_id, "equipement": equip_name}, ensure_ascii=False)
    log_audit(username, "DELETE_EQUIPEMENT", details, "equipements")
    
    return {"ok": True}


@app.post("/api/equipements/sync-region-ville")
def sync_region_ville():
    """Sync region and ville from clients to equipements based on client name. Admin operation."""
    try:
        from db_engine import _trigger_backup
        
        df_clients = db_lire_clients()
        df_eq = lire_equipements()
        
        if df_clients.empty or df_eq.empty:
            return {"ok": True, "updated": 0}
        
        logger.info(f"Starting sync: {len(df_clients)} clients, {len(df_eq)} equipements")
        
        # Use SQL UPDATE with JOIN to sync region/ville from clients to equipements (PostgreSQL)
        with get_db() as conn:
            cur = conn.cursor()
            
            # Update equipements where client name matches exactly
            cur.execute("""
                UPDATE equipements e
                SET region = c.region, ville = c.ville
                FROM clients c
                WHERE LOWER(e.client) = LOWER(c.nom)
            """)
            exact_matches = cur.rowcount
            conn.commit()
            
            logger.info(f"Exact matches: {exact_matches}")
            
            # For remaining equipements, try fuzzy matching
            # Get equipements that still have region='Nord' but don't have exact client match
            cur.execute("""
                SELECT e.id, e.client
                FROM equipements e
                LEFT JOIN clients c ON LOWER(e.client) = LOWER(c.nom)
                WHERE c.id IS NULL
            """)
            unmatched_equips = cur.fetchall()
            logger.info(f"Unmatched equipements: {len(unmatched_equips)}")
            
            # Try fuzzy matching for unmatched equipements
            fuzzy_matches = 0
            for equip_id, equip_client in unmatched_equips:
                # Find best match in clients table
                best_match = None
                best_score = 0
                
                for _, client_row in df_clients.iterrows():
                    client_nom = str(client_row.get("nom", "")).lower()
                    equip_client_lower = str(equip_client).lower()
                    
                    # Simple fuzzy match: check if one contains the other
                    if equip_client_lower in client_nom or client_nom in equip_client_lower:
                        best_match = client_row
                        break
                
                if best_match is not None:
                    region = str(best_match.get("region", "")).strip()
                    ville = str(best_match.get("ville", "")).strip()
                    
                    cur.execute(
                        "UPDATE equipements SET region = %s, ville = %s WHERE id = %s",
                        (region, ville, equip_id)
                    )
                    fuzzy_matches += 1
            
            conn.commit()
            logger.info(f"Fuzzy matches: {fuzzy_matches}")
            
            total_updated = exact_matches + fuzzy_matches
        
        logger.info(f"Sync completed: {total_updated} equipements updated")
        _trigger_backup()
        return {"ok": True, "updated": total_updated}
    except Exception as e:
        logger.error(f"Sync region/ville error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fabricants")
def get_fabricants(user: dict = Depends(_verify_token)):
    return lire_fabricants()


@app.post("/api/fabricants")
def post_fabricant(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    nom = payload.get("nom", "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    ajouter_fabricant(nom)
    return {"ok": True}


@app.get("/api/types-equipement-custom")
def get_types_equipement_custom(domaine: str = Query(""), user: dict = Depends(_verify_token)):
    return lire_types_equipement_custom(domaine)


@app.post("/api/types-equipement-custom")
def post_type_equipement_custom(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    nom = payload.get("nom", "").strip()
    domaine = payload.get("domaine", "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    ajouter_type_equipement_custom(nom, domaine)
    return {"ok": True}


@app.get("/api/types-intervention-custom")
def get_types_intervention_custom(user: dict = Depends(_verify_token)):
    return lire_types_intervention_custom()


@app.post("/api/types-intervention-custom")
def post_type_intervention_custom(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    nom = payload.get("nom", "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    ajouter_type_intervention_custom(nom)
    return {"ok": True}


@app.get("/api/domaines-custom")
def get_domaines_custom(user: dict = Depends(_verify_token)):
    from db_engine import lire_domaines_custom
    return lire_domaines_custom()


@app.post("/api/domaines-custom")
def post_domaine_custom(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    from db_engine import ajouter_domaine_custom
    nom = payload.get("nom", "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    ajouter_domaine_custom(nom)
    return {"ok": True}


@app.delete("/api/domaines-custom/{nom}")
def delete_domaine_custom(nom: str, user: dict = Depends(_verify_token)):
    from db_engine import supprimer_domaine_custom
    if not nom.strip():
        raise HTTPException(400, "Nom requis")
    supprimer_domaine_custom(nom)
    return {"ok": True}


# ==========================================
# DOCUMENTS TECHNIQUES
# ==========================================

@app.post("/api/documents-techniques/upload")
def upload_document(body: dict, user: dict = Depends(_verify_token)):
    """Upload a technical document (base64 encoded) for an equipment."""
    from db_engine import ajouter_document_technique
    equip_id = body.get("equipement_id")
    nom_fichier = body.get("nom_fichier", "")
    contenu_base64 = body.get("contenu_base64", "")
    if not equip_id or not nom_fichier or not contenu_base64:
        raise HTTPException(status_code=400, detail="equipement_id, nom_fichier et contenu_base64 requis")
    ajouter_document_technique(equip_id, nom_fichier, contenu_base64)
    return {"ok": True}


@app.get("/api/documents-techniques")
def get_all_documents(user: dict = Depends(_verify_token)):
    """List all technical documents with associated equipment info."""
    from db_engine import lire_tous_documents_techniques
    return lire_tous_documents_techniques()


@app.get("/api/documents-techniques/{equip_id}")
def get_documents_by_equipment(equip_id: int, user: dict = Depends(_verify_token)):
    """List technical documents for a specific equipment."""
    from db_engine import lire_documents_techniques
    return lire_documents_techniques(equip_id)


@app.get("/api/documents-techniques/download/{doc_id}")
def download_document(doc_id: int, user: dict = Depends(_verify_token)):
    """Download a specific technical document (returns base64 content)."""
    from db_engine import lire_document_technique_contenu
    doc = lire_document_technique_contenu(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document non trouvé")
    return doc


@app.delete("/api/documents-techniques/{doc_id}")
def delete_document(doc_id: int, user: dict = Depends(_verify_token)):
    """Delete a technical document."""
    from db_engine import supprimer_document_technique
    supprimer_document_technique(doc_id)
    return {"ok": True}


# ==========================================
# INTERVENTIONS / SAV
# ==========================================

@app.get("/api/interventions")
def get_interventions(
    machine: Optional[str] = None,
    technicien: Optional[str] = None,
    offset: int = 0,
    limit: int = 200,
    user: dict = Depends(_verify_token),
):
    from db_engine import lire_child_interventions_for_technician
    
    df = lire_interventions(machine=machine)
    
    # Si le user est un Technicien → filtrer automatiquement ses interventions
    # ET inclure ses interventions enfants (temporary child interventions)
    if user.get("role") == "Technicien":
        user_nom_complet = (user.get("nom") or "").strip()
        user_username = (user.get("sub") or "").strip()
        # Filter by name (primary) or username (secondary)
        if user_nom_complet and not df.empty and "technicien" in df.columns:
            df = df[df["technicien"].astype(str).apply(
                lambda t: _tech_name_or_username_matches(user_nom_complet, t) or _tech_name_or_username_matches(user_username, t)
            )]
        
        # Also fetch child interventions assigned to this technician
        try:
            df_children = lire_child_interventions_for_technician(user_nom_complet)
            if not df_children.empty:
                # Combine parent and child interventions
                import pandas as pd
                df = pd.concat([df, df_children], ignore_index=True)
                logger.info(f"Technician {user_nom_complet}: {len(df)} total interventions (parents + children)")
        except Exception as e:
            logger.warning(f"Error fetching child interventions for {user_nom_complet}: {e}")
            # Continue with just parent interventions if children fetch fails
            pass
        
    elif technicien and not df.empty and "technicien" in df.columns:
        df = df[df["technicien"].astype(str).apply(
            lambda t: _tech_name_or_username_matches(technicien, t)
        )]
    
    # Filtrage par client pour Lecteur
    client_filter = _get_client_filter(user)
    if client_filter and not df.empty:
        df_eq = lire_equipements()
        if not df_eq.empty and "Client" in df_eq.columns and "Nom" in df_eq.columns:
            machines_client = set(
                df_eq[df_eq["Client"].astype(str).str.lower() == client_filter.lower()]["Nom"].tolist()
            )
            if "machine" in df.columns:
                df = df[df["machine"].isin(machines_client)]
    
    # Apply pagination (offset + limit)
    if not df.empty:
        total = len(df)
        df = df.iloc[offset:offset + limit]
    else:
        total = 0
    
    return _df_to_records(df)


@app.get("/api/interventions/{parent_id}/children")
def get_child_interventions_endpoint(
    parent_id: int,
    user: dict = Depends(_verify_token),
):
    """
    Récupère les interventions enfants d'une intervention parent.
    Utilisé par PWA pour afficher les technicians assignés à une demande.
    """
    from db_engine import get_child_interventions
    
    try:
        children = get_child_interventions(parent_id)
        return {
            "success": True,
            "parent_id": parent_id,
            "children": children,
            "count": len(children)
        }
    except Exception as e:
        logger.error(f"Error fetching child interventions for parent {parent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des enfants: {str(e)}")


@app.post("/api/interventions")
def create_intervention(body: dict, user: dict = Depends(_verify_token)):
    # Check permission
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins"
        )
    
    # Convert technicien username to full name (nom + prenom)
    technicien_username = body.get("technicien", "")
    if technicien_username:
        body["technicien"] = _get_technician_fullname(technicien_username)
    
    ajouter_intervention(body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "machine": body.get("machine", ""),
        "type": body.get("type_intervention", ""),
        "technicien": body.get("technicien", ""),
        "priorite": body.get("priorite", ""),
    }, ensure_ascii=False)
    log_audit(username, "CREATE_INTERVENTION", details, "interventions")
    
    # Notification Telegram au bot technique
    try:
        machine = body.get("machine", "N/A")
        technicien = body.get("technicien", "N/A")
        type_interv = body.get("type_intervention", "N/A")
        priorite = body.get("priorite", "Moyenne")
        description = body.get("description", "") or body.get("probleme", "")
        client = body.get("client", "")
        msg = (
            f"🔧 <b>Nouvelle Intervention</b>\n"
            f"📋 Machine : <b>{machine}</b>\n"
            f"{'🏢 Client : ' + client + chr(10) if client else ''}"
            f"👨‍🔧 Technicien : {technicien}\n"
            f"🔹 Type : {type_interv}\n"
            f"⚡ Priorité : {priorite}\n"
            f"{'📝 ' + description[:200] + chr(10) if description else ''}"
            f"📅 Date : {body.get('date', 'N/A')}"
        )
        _send_telegram_bot("telegram", msg)
    except Exception as e:
        logger.warning(f"Notification Telegram nouvelle intervention échouée: {e}")
    return {"ok": True}


@app.get("/api/interventions/facturation")
def get_facturation_tracking(user: dict = Depends(_verify_token)):
    """Retourne les interventions cloturees avec le suivi de facturation."""
    from datetime import date, timedelta
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT i.id, i.machine, i.technicien, i.type_intervention,
                       COALESCE(i.date_cloture, i.date) as date_cloture,
                       i.facture_envoyee, i.notes,
                       i.pieces_utilisees, i.cout, i.duree_minutes,
                       i.description, i.probleme, i.cause, i.solution,
                       i.priorite, i.type_erreur, i.code_erreur,
                       i.date_debut_intervention, i.date, i.cout_pieces
                FROM interventions i
                WHERE i.statut IN ('Cloturee', 'Terminee', 'Terminée')
                ORDER BY COALESCE(i.date_cloture, i.date) DESC
            """).fetchall()
        today = date.today()
        result = []
        for row in rows:
            d = dict(row)
            dc = d['date_cloture']
            if isinstance(dc, str):
                cloture_date = date.fromisoformat(str(dc)[:10])
            elif hasattr(dc, 'date'):
                cloture_date = dc.date()
            elif hasattr(dc, 'year'):
                cloture_date = dc
            else:
                cloture_date = date.fromisoformat(str(dc)[:10])
            jours_depuis = (today - cloture_date).days
            deadline = cloture_date + timedelta(days=10)
            jours_restants = (deadline - today).days
            notes = str(d.get('notes', '') or '')
            client = notes[1:notes.index(']')] if notes.startswith('[') and ']' in notes else ''
            # Extract ville from client name if format "Name Ville"
            result.append({
                "id": d['id'],
                "machine": d.get('machine', ''),
                "technicien": d.get('technicien', ''),
                "type_intervention": d.get('type_intervention', ''),
                "client": client,
                "date_cloture": str(cloture_date),
                "facture_envoyee": bool(d.get('facture_envoyee', False)),
                "jours_depuis_cloture": jours_depuis,
                "jours_restants": jours_restants,
                "deadline": str(deadline),
                "pieces_utilisees": d.get('pieces_utilisees', ''),
                "cout": d.get('cout', 0) or 0,
                "cout_pieces": d.get('cout_pieces', 0) or 0,
                "duree_minutes": d.get('duree_minutes', 0) or 0,
                "en_retard": jours_restants < 0 and not d.get('facture_envoyee', False),
                "description": d.get('description', ''),
                "probleme": d.get('probleme', ''),
                "cause": d.get('cause', ''),
                "solution": d.get('solution', ''),
                "priorite": d.get('priorite', ''),
                "type_erreur": d.get('type_erreur', ''),
                "code_erreur": d.get('code_erreur', ''),
                "date_intervention": str(d.get('date', '') or '')[:10] if d.get('date') else '',
                "date_debut_intervention": str(d.get('date_debut_intervention', '') or '')[:10] if d.get('date_debut_intervention') else '',
            })
        return result
    except Exception as e:
        logger.error(f"Facturation tracking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/interventions/{intervention_id}")
def update_intervention(intervention_id: int, body: dict = Body(...), user: dict = Depends(_verify_token)):
    logger.info(f"📥 update_intervention #{intervention_id} received: {body}")
    
    # Vérifier les permissions : un technicien ne peut éditer que ses interventions
    if user.get("role") == "Technicien":
        with get_db() as conn:
            row = conn.execute(
                "SELECT technicien FROM interventions WHERE id = ?",
                (intervention_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
            
            current_tech = str(row.get("technicien") or "").strip()
            user_nom_complet = (user.get("nom") or "").strip()
            user_username = (user.get("sub") or "").strip()
            
            # Cas 1: Intervention avec champ technicien rempli (single-technicien)
            if current_tech:
                # Vérifier si c'est une correspondance par NOM (ex: "Salah Al Salah")
                # OU par USERNAME (ex: "tech_07")
                # Check both directions: name->tech and username->tech
                is_assigned = (
                    _tech_name_or_username_matches(user_nom_complet, current_tech) or
                    _tech_name_or_username_matches(user_username, current_tech)
                )
                
                logger.info(f"🔐 Permission check (single-tech): user='{user_nom_complet}' (username={user_username}) vs tech='{current_tech}' → assigned={is_assigned}")
                if not is_assigned:
                    raise HTTPException(
                        status_code=403,
                        detail="Vous ne pouvez éditer que vos propres interventions"
                    )
            else:
                # Cas 2: Intervention sans technicien principal (multi-technicien) → vérifier interventions_techniciens
                logger.info(f"🔐 Permission check (multi-tech): checking interventions_techniciens table")
                tech_row = conn.execute(
                    "SELECT user_id FROM interventions_techniciens WHERE intervention_id = ? AND user_id = ?",
                    (intervention_id, user_username)  # user_username est le username
                ).fetchone()
                
                if not tech_row:
                    # Technicien n'est pas dans la liste interventions_techniciens
                    logger.warning(f"🔐 Technicien '{user_nom_complet}' (username={user_username}) not in interventions_techniciens for #{intervention_id}")
                    raise HTTPException(
                        status_code=403,
                        detail="Vous ne pouvez éditer que vos propres interventions"
                    )
                logger.info(f"🔐 Technicien '{user_nom_complet}' found in interventions_techniciens")
    
    new_statut = body.get("statut")
    if new_statut and "tur" in new_statut.lower():
        # Normaliser pieces_a_deduire : s'assurer que c'est une liste de dicts avec clé 'ref' ou 'reference'
        raw_pieces = body.get("pieces_a_deduire") or []
        if not isinstance(raw_pieces, list):
            raw_pieces = []
        # Accepter 'ref' ou 'reference', 'qty' ou 'quantite'
        pieces_valides = []
        for p in raw_pieces:
            if isinstance(p, dict):
                ref = p.get("ref") or p.get("reference")
                if ref:
                    pieces_valides.append({
                        'ref': ref,
                        'reference': ref,
                        'qty': p.get("qty") or p.get("quantite") or 0,
                        'quantite': p.get("qty") or p.get("quantite") or 0,
                        'designation': p.get("designation", ""),
                        'prix_unitaire': p.get("prix_unitaire", 0),
                    })

        try:
            ok, msg = cloturer_intervention(
                intervention_id,
                body.get("probleme", ""),
                body.get("cause", ""),
                body.get("solution", ""),
                pieces_a_deduire=pieces_valides if pieces_valides else None,
                duree_minutes=body.get("duree_minutes", 0),
                start_time=body.get("start_time"),
                end_time=body.get("end_time"),
                duree_deplacement=body.get("deplacement"),  # PWA sends "deplacement"
            )
            if not ok:
                raise HTTPException(status_code=400, detail=msg)

            # --- Update type_erreur if provided ---
            if body.get("type_erreur"):
                with get_db() as conn:
                    conn.execute(
                        "UPDATE interventions SET type_erreur = ? WHERE id = ?",
                        (body.get("type_erreur"), intervention_id)
                    )

            # --- Telegram notification clôture ---
            try:
                with get_db() as conn:
                    row = conn.execute(
                        "SELECT machine, technicien, probleme, cause, solution, duree_minutes, notes, pieces_utilisees FROM interventions WHERE id = ?",
                        (intervention_id,)
                    ).fetchone()
                if row:
                    d = dict(row)
                    # Convert technicien username to full name
                    if d.get('technicien'):
                        d['technicien'] = _get_technician_fullname(d['technicien'])
                    duree_h = round((d.get('duree_minutes') or 0) / 60, 1)
                    notes_raw = str(d.get('notes', '') or '')
                    # Extraire client depuis notes [Client]
                    client_name = notes_raw[1:notes_raw.index(']')] if notes_raw.startswith('[') and ']' in notes_raw else ''
                    # Si pas de client dans notes, chercher via equipement
                    if not client_name:
                        try:
                            eq_row = conn.execute(
                                "SELECT \"Client\" FROM equipements WHERE \"Nom\" = ? LIMIT 1",
                                (d.get('machine', ''),)
                            ).fetchone()
                            if eq_row:
                                client_name = eq_row['Client'] or ''
                        except Exception:
                            pass
                    pieces = str(d.get('pieces_utilisees', '') or '').strip()
                    notes_line = f"\n📌 Notes : {notes_raw}" if notes_raw and not notes_raw.startswith('[') else ""
                    client_line = f"\n👤 Client : <b>{client_name}</b>" if client_name else ""
                    pieces_line = f"\n🔩 Pièces : {pieces}" if pieces else ""
                    msg_tg = (
                        f"✅ <b>INTERVENTION CLÔTURÉE — #{intervention_id}</b>\n\n"
                        f"🏥 Machine : <b>{d.get('machine', '')}</b>"
                        f"{client_line}\n"
                        f"👷 Technicien : <b>{d.get('technicien', '')}</b>\n"
                        f"🔴 Problème : {str(d.get('probleme', ''))[:200]}\n"
                        f"🔍 Cause : {str(d.get('cause', ''))[:200]}\n"
                        f"🟢 Solution : {str(d.get('solution', ''))[:200]}\n"
                        f"⏱️ Durée : <b>{duree_h}h</b>"
                        f"{pieces_line}"
                        f"{notes_line}\n"
                        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    )
                    _send_telegram(msg_tg)
                    # Notification SAV : intervention clôturée → à facturer
                    msg_sav = (
                        f"📋 <b>Intervention Clôturée — À facturer</b>\n\n"
                        f"🔧 Intervention <b>#{intervention_id}</b>\n"
                        f"🏥 Machine : <b>{d.get('machine', '')}</b>"
                        f"{client_line}\n"
                        f"👷 Technicien : {d.get('technicien', '')}\n"
                        f"⏱️ Durée : {duree_h}h"
                        f"{pieces_line}\n\n"
                        f"💰 <i>Délai de facturation : 10 jours</i>\n"
                        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    )
                    _send_telegram_bot("telegram_sav", msg_sav)
            except Exception as te:
                logger.error(f"Telegram clôture erreur: {te}")

            # --- Mettre à jour la demande liée (si elle existe) → statut "Résolue" ---
            try:
                with get_db() as conn:
                    conn.execute(
                        """UPDATE demandes_intervention
                           SET statut = 'Résolue',
                               date_traitement = ?
                         WHERE intervention_id = ?
                           AND statut != 'Résolue'""",
                        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), intervention_id)
                    )
                    logger.info(f"Demande liée à l'intervention #{intervention_id} marquée Résolue")
            except Exception as de:
                logger.error(f"Erreur mise à jour demande liée: {de}")

            # --- Mettre à jour le planning lié (si planning_id) → statut "Réalisée" ---
            try:
                with get_db() as conn:
                    prow = conn.execute(
                        "SELECT planning_id FROM interventions WHERE id = ?",
                        (intervention_id,)
                    ).fetchone()
                    if prow and prow['planning_id']:
                        pm_id = prow['planning_id']
                        conn.execute(
                            """UPDATE planning_maintenance
                               SET statut = 'Réalisée',
                                   date_realisee = ?
                             WHERE id = ? AND statut != 'Réalisée'""",
                            (datetime.now().strftime("%Y-%m-%d"), pm_id)
                        )
                        logger.info(f"Planning #{pm_id} marqué Réalisée (intervention #{intervention_id} clôturée)")
            except Exception as pe:
                logger.error(f"Erreur mise à jour planning lié: {pe}")

            return {"ok": True, "message": msg}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erreur clôture intervention #{intervention_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Erreur lors de la clôture: {str(e)}")
    if new_statut and "attente" in new_statut.lower() and "pi" in new_statut.lower():
        # Statut = "En attente de pièce" → notification rupture pour gestionnaires
        pieces_attente = body.get("pieces_rupture") or []
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT machine, technicien, notes, probleme FROM interventions WHERE id = ?",
                    (intervention_id,)
                ).fetchone()
            if row:
                machine = row["machine"] or ""
                technicien = row["technicien"] or ""
                # Convert technicien username to full name
                if technicien:
                    technicien = _get_technician_fullname(technicien)
                # Extraire client depuis notes [Client]
                notes = str(row.get("notes") or "")
                client = notes[1:notes.index("]")] if notes.startswith("[") and "]" in notes else ""
                # Si pas de client dans notes, chercher via equipement
                if not client:
                    try:
                        with get_db() as conn2:
                            eq_row = conn2.execute(
                                'SELECT client FROM equipements WHERE nom = ? LIMIT 1',
                                (machine,)
                            ).fetchone()
                            if eq_row:
                                client = dict(eq_row).get('client', '') or ''
                    except Exception:
                        pass
                for piece in pieces_attente:
                    ref = piece.get("reference") or piece.get("ref") or ""
                    nom = piece.get("designation") or piece.get("nom") or ref
                    ajouter_notification_piece({
                        "type": "piece_rupture",
                        "intervention_id": intervention_id,
                        "piece_reference": ref,
                        "piece_nom": nom,
                        "intervention_ref": f"#{intervention_id}",
                        "equipement": machine,
                        "client": client,
                        "technicien": technicien,
                        "message": f"⚠️ Intervention #{intervention_id} sur {machine} en attente de la pièce "
                                   f"{ref} ({nom}) — rupture de stock",
                        "source": "sav",
                        "destination": "gestionnaire",
                    })
                    logger.info(f"Notif rupture créée: pièce {ref} pour intervention #{intervention_id}")

                # ── Envoi Telegram immédiat ──
                pieces_txt = ""
                if pieces_attente:
                    pieces_list = [f"  • {p.get('reference') or p.get('ref','')} — {p.get('designation') or p.get('nom','')}" for p in pieces_attente]
                    pieces_txt = "\n🔩 Pièces demandées :\n" + "\n".join(pieces_list)
                client_line = f"\n👤 Client : <b>{client}</b>" if client else ""
                msg_tg = (
                    f"⏳ <b>INTERVENTION EN ATTENTE DE PIÈCE — #{intervention_id}</b>\n\n"
                    f"🏥 Machine : <b>{machine}</b>"
                    f"{client_line}\n"
                    f"👷 Technicien : <b>{technicien}</b>"
                    f"{pieces_txt}\n\n"
                    f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                )
                _send_telegram_bot("telegram_stock", msg_tg)
                _send_telegram_bot("telegram", msg_tg)
        except Exception as ne:
            logger.error(f"Erreur création notif rupture: {ne}")

        # ── Pièces manuelles (non référencées dans le stock) ──
        pieces_manuelles = body.get("pieces_manuelles") or []
        if pieces_manuelles:
            try:
                for pm in pieces_manuelles:
                    ref = pm.get("reference") or ""
                    designation = pm.get("designation") or ref
                    if not ref:
                        continue
                    # Enregistrer la demande
                    ajouter_piece_demandee({
                        "reference": ref,
                        "designation": designation,
                        "intervention_id": intervention_id,
                        "equipement": machine,
                        "client": client,
                        "technicien": technicien,
                        "probleme": row.get("probleme", "") if row else "",
                    })
                    # Notification gestionnaire
                    ajouter_notification_piece({
                        "type": "piece_rupture",
                        "intervention_id": intervention_id,
                        "piece_reference": ref,
                        "piece_nom": designation,
                        "intervention_ref": f"#{intervention_id}",
                        "equipement": machine,
                        "client": client,
                        "technicien": technicien,
                        "message": f"🆕 Pièce non référencée demandée: {ref} ({designation}) "
                                   f"pour intervention #{intervention_id} sur {machine}",
                        "source": "sav",
                        "destination": "gestionnaire",
                    })
                    logger.info(f"Demande pièce manuelle créée: {ref} pour intervention #{intervention_id}")

                # Telegram pour pièces manuelles
                pm_list = [f"  • {p.get('reference','')} — {p.get('designation','')}" for p in pieces_manuelles if p.get("reference")]
                if pm_list:
                    client_line_m = f"\n👤 Client : <b>{client}</b>" if client else ""
                    msg_tg_m = (
                        f"🆕 <b>DEMANDE PIÈCE NON RÉFÉRENCÉE — #{intervention_id}</b>\n\n"
                        f"🏥 Machine : <b>{machine}</b>"
                        f"{client_line_m}\n"
                        f"👷 Technicien : <b>{technicien}</b>\n"
                        f"🔩 Pièces demandées :\n" + "\n".join(pm_list) + "\n\n"
                        f"⚠️ Ces pièces ne sont pas dans le stock — à commander\n"
                        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    )
                    _send_telegram_bot("telegram_stock", msg_tg_m)
                    _send_telegram_bot("telegram", msg_tg_m)
            except Exception as pe:
                logger.error(f"Erreur pièces manuelles: {pe}")

    if new_statut:
        update_intervention_statut(intervention_id, new_statut)
    
    # Update other fields
    fields = []
    params = []
    
    # Map of field names in request body to database column names
    field_mapping = {
        "technicien": "technicien",
        "probleme": "probleme",
        "cause": "cause",
        "solution": "solution",
        "pieces_utilisees": "pieces_utilisees",
        "cout": "cout",
        "duree_minutes": "duree_minutes",
        "description": "description",
        "notes": "notes",
        "type_erreur": "type_erreur",
        "priorite": "priorite",
        "fiche_validation": "fiche_validation",
        "start_time": "start_time",
        "end_time": "end_time",
        "deplacement": "duree_deplacement",  # PWA sends "deplacement", map to "duree_deplacement"
    }
    
    for body_field, db_column in field_mapping.items():
        if body_field in body:
            value = body[body_field]
            fields.append(f"{db_column} = ?")
            params.append(value)
            logger.info(f"  ✓ {db_column} = {value}")
    
    if fields:
        params.append(intervention_id)
        logger.info(f"update_intervention #{intervention_id}: fields={fields}, params={params}")
        try:
            with get_db() as conn:
                conn.execute(f"UPDATE interventions SET {', '.join(fields)} WHERE id = ?", params)
            logger.info(f"✅ update_intervention #{intervention_id}: SUCCESS - Updated {len(fields)} fields")
        except Exception as e:
            logger.error(f"❌ update_intervention #{intervention_id} FAILED: {e}")
            raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")
    return {"ok": True}


@app.delete("/api/interventions/{intervention_id}")
def delete_intervention(intervention_id: int, user: dict = Depends(_verify_token)):
    """Supprime une intervention (Admin/Manager uniquement)."""
    # Vérifier les permissions
    if user.get("role") not in ["Admin", "Manager"]:
        raise HTTPException(status_code=403, detail="Seuls les Admin/Manager peuvent supprimer une intervention")
    
    try:
        with get_db() as conn:
            # Vérifier que l'intervention existe et récupérer ses infos
            row = conn.execute(
                "SELECT id, machine, type_intervention FROM interventions WHERE id = ?",
                (intervention_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
            
            row_dict = dict(row)
            machine = row_dict.get("machine", "Unknown")
            type_intervention = row_dict.get("type_intervention", "Unknown")
            
            # Supprimer l'intervention
            conn.execute("DELETE FROM interventions WHERE id = ?", (intervention_id,))
            
            # Log audit
            username = user.get("sub", "unknown")
            import json
            details = json.dumps({
                "intervention_id": intervention_id,
                "machine": machine,
                "type": type_intervention,
            }, ensure_ascii=False)
            log_audit(username, "DELETE_INTERVENTION", details, "interventions")
            
        return {"ok": True, "message": f"Intervention #{intervention_id} supprimée"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur suppression intervention #{intervention_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")


@app.post("/api/interventions/{intervention_id}/fiche")
async def upload_fiche(intervention_id: int, file: UploadFile = File(...), user: dict = Depends(_verify_token)):
    """Upload la photo de la fiche signée pour une intervention clôturée."""
    contents = await file.read()
    logger.info(f"Fiche upload: intervention #{intervention_id}, file={file.filename}, size={len(contents)} bytes")
    # psycopg2 requires Binary wrapper for bytea columns
    try:
        import psycopg2
        binary_data = psycopg2.Binary(contents)
    except ImportError:
        binary_data = contents
    with get_db() as conn:
        conn.execute(
            "UPDATE interventions SET fiche_photo_nom = ?, fiche_photo_data = ? WHERE id = ?",
            (file.filename, binary_data, intervention_id)
        )
    logger.info(f"Fiche photo uploadée pour intervention #{intervention_id}: {file.filename}")
    return {"ok": True, "filename": file.filename}


@app.post("/api/interventions/{intervention_id}/photo")
async def upload_photo_alias(intervention_id: int,
                             photo: UploadFile = File(None),
                             file: UploadFile = File(None),
                             user: dict = Depends(_verify_token)):
    """Alias /photo → /fiche pour compatibilité avec l'ancien api_server.py (Streamlit).
    Accepte le champ 'photo' ou 'file'."""
    upload = photo or file
    if not upload:
        raise HTTPException(status_code=400, detail="Aucun fichier fourni")
    contents = await upload.read()
    logger.info(f"Photo upload (alias): intervention #{intervention_id}, file={upload.filename}, size={len(contents)} bytes")
    # psycopg2 requires Binary wrapper for bytea columns
    try:
        import psycopg2
        binary_data = psycopg2.Binary(contents)
    except ImportError:
        binary_data = contents
    with get_db() as conn:
        conn.execute(
            "UPDATE interventions SET fiche_photo_nom = ?, fiche_photo_data = ? WHERE id = ?",
            (upload.filename, binary_data, intervention_id)
        )
    logger.info(f"[/photo alias] Fiche photo uploadée pour intervention #{intervention_id}: {upload.filename}")
    return {"ok": True, "message": "Photo enregistrée", "filename": upload.filename}


@app.get("/api/interventions/{intervention_id}/fiche")
def download_fiche(intervention_id: int, token: Optional[str] = Query(None), user: dict = Depends(_verify_token)):
    """Télécharge la photo de fiche pour une intervention (accepte token en query param pour img src)."""
    from fastapi.responses import Response
    # Si token en query param, valider manuellement
    if token:
        try:
            jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        except Exception:
            raise HTTPException(status_code=401, detail="Token invalide")
    with get_db() as conn:
        try:
            row = conn.execute(
                "SELECT fiche_photo_nom, fiche_photo_data FROM interventions WHERE id = ?",
                (intervention_id,)
            ).fetchone()
        except Exception:
            raise HTTPException(status_code=404, detail="Colonne fiche non trouvée")
    if not row or not row["fiche_photo_data"]:
        raise HTTPException(status_code=404, detail="Aucune fiche pour cette intervention")
    nom = row["fiche_photo_nom"] or f"fiche_{intervention_id}.jpg"
    data = bytes(row["fiche_photo_data"])
    ext = nom.rsplit('.', 1)[-1].lower() if '.' in nom else 'jpg'
    mime_map = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
                'pdf': 'application/pdf', 'webp': 'image/webp'}
    mime = mime_map.get(ext, 'application/octet-stream')
    return Response(content=data, media_type=mime,
                    headers={"Content-Disposition": f'inline; filename="{nom}"'})



@app.get("/api/interventions/fiches")
def list_fiches(user: dict = Depends(_verify_token)):
    """Liste uniquement les interventions clôturées AVEC photo attachée."""
    with get_db() as conn:
        try:
            rows = conn.execute("""
                SELECT id, date, machine, technicien, statut, probleme, solution,
                       duree_minutes,
                       COALESCE(fiche_photo_nom, '') AS fiche_photo_nom,
                       (fiche_photo_data IS NOT NULL AND octet_length(fiche_photo_data) > 0) AS has_fiche,
                       COALESCE(fiche_validation, 'En attente') AS fiche_validation
                FROM interventions
                WHERE (statut ILIKE '%lotur%' OR statut ILIKE '%termin%' OR statut = 'Cloturee')
                  AND fiche_photo_data IS NOT NULL
                  AND octet_length(fiche_photo_data) > 0
                ORDER BY id DESC
                LIMIT 200
            """).fetchall()
        except Exception as e:
            logger.error(f"Erreur list_fiches: {e}")
            return []
    result = []
    for r in rows:
        d = dict(r)
        if hasattr(d.get('date'), 'isoformat'):
            d['date'] = d['date'].isoformat()
        d['has_fiche'] = bool(d.get('has_fiche'))
        d['fiche_validation'] = d.get('fiche_validation') or 'En attente'
        result.append(d)
    return result


@app.patch("/api/interventions/{intervention_id}/fiche-validation")
def update_fiche_validation(intervention_id: int, body: dict, user: dict = Depends(_verify_token)):
    """Met à jour le statut de validation client d'une fiche.
    Une fois 'Validée', aucune modification n'est plus possible."""
    nouveau_statut = body.get("validation", "").strip()
    valeurs_autorisees = {"En attente", "Validée"}
    if nouveau_statut not in valeurs_autorisees:
        raise HTTPException(status_code=400, detail=f"Valeur invalide: {nouveau_statut}. Valeurs autorisées: {valeurs_autorisees}")

    with get_db() as conn:
        # Vérifier le statut actuel
        row = conn.execute(
            "SELECT fiche_validation FROM interventions WHERE id = ?",
            (intervention_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Intervention non trouvée")
        statut_actuel = (row["fiche_validation"] or "En attente").strip()
        if statut_actuel == "Validée":
            raise HTTPException(status_code=403, detail="Fiche déjà validée — aucune modification possible")
        conn.execute(
            "UPDATE interventions SET fiche_validation = ? WHERE id = ?",
            (nouveau_statut, intervention_id)
        )
    logger.info(f"Fiche #{intervention_id}: validation mise à jour → '{nouveau_statut}' par {user.get('nom', '?')}")
    return {"ok": True, "validation": nouveau_statut}


@app.delete("/api/interventions/{intervention_id}/fiche")
def delete_fiche(intervention_id: int, user: dict = Depends(_verify_token)):
    """Supprime la photo de fiche d'une intervention (Manager/Admin uniquement).
    Impossible si la fiche est validée."""
    # Vérifier les permissions
    user_role = user.get("role", "").strip()
    if user_role not in {"Admin", "Manager"}:
        raise HTTPException(status_code=403, detail="Seuls les Managers et Admins peuvent supprimer une fiche")
    
    with get_db() as conn:
        # Vérifier le statut de validation
        row = conn.execute(
            "SELECT fiche_validation, fiche_photo_nom FROM interventions WHERE id = ?",
            (intervention_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Intervention non trouvée")
        
        statut_validation = (row["fiche_validation"] or "En attente").strip()
        if statut_validation == "Validée":
            raise HTTPException(status_code=403, detail="Impossible de supprimer une fiche validée")
        
        # Supprimer la fiche
        conn.execute(
            "UPDATE interventions SET fiche_photo_nom = '', fiche_photo_data = NULL, fiche_validation = 'En attente' WHERE id = ?",
            (intervention_id,)
        )
    
    logger.info(f"Fiche #{intervention_id} supprimée par {user.get('nom', '?')} ({user_role})")
    return {"ok": True, "message": "Fiche supprimée avec succès"}


# ==========================================
# DEMANDES D'INTERVENTION
# ==========================================

@app.get("/api/demandes")
def get_demandes(
    statuts: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    df = lire_demandes_intervention()
    # Lecteur : ne voit que les demandes de son client
    client_filter = _get_client_filter(user)
    if client_filter and not df.empty and "client" in df.columns:
        df = df[df["client"].astype(str).str.lower() == client_filter.lower()]
    if statuts and not df.empty and "statut" in df.columns:
        lst = [s.strip() for s in statuts.split(",")]
        df = df[df["statut"].isin(lst)]
    return _df_to_records(df)


@app.post("/api/demandes")
def create_demande(body: dict, user: dict = Depends(_verify_token)):
    """
    Crée une demande d'intervention avec support multi-techniciens.
    Crée 1 intervention PARENT visible + N interventions ENFANTS temporaires (1 par technicien).
    """
    # Check permission - Lecteurs (clients) peuvent créer des demandes
    if not _check_create_demande_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas le droit de créer une demande d'intervention"
        )
    
    from db_engine import get_db
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    demandeur          = body.get("demandeur") or user.get("username", "")
    client             = body.get("client") or ""
    equipement         = body.get("equipement") or ""
    urgence            = body.get("urgence") or "Moyenne"
    description        = body.get("description") or ""
    code_erreur        = body.get("code_erreur") or ""
    contact_nom        = body.get("contact_nom") or ""
    contact_tel        = body.get("contact_tel") or ""
    
    # Support for multiple technicians: can be string (single/comma-separated) or list (multiple)
    techniciens_input = body.get("technicien_assigne") or body.get("techniciens") or []
    if isinstance(techniciens_input, str):
        # If it's a comma-separated string, split it
        techniciens_input = [t.strip() for t in techniciens_input.split(",")] if techniciens_input else []
    
    # Convert all to full names
    techniciens_fullnames = []
    for tech_username in techniciens_input:
        if tech_username:
            tech_fullname = _get_technician_fullname(tech_username)
            techniciens_fullnames.append(tech_fullname)
    
    # First tech (for parent intervention)
    first_tech = techniciens_fullnames[0] if techniciens_fullnames else ""
    statut = "Assignée" if first_tech else "En attente"
    
    # Use PostgreSQL placeholder
    ph = "%s"

    demande_id = None
    parent_intervention_id = None

    with get_db() as conn:
        # Create the DEMAND
        conn.execute(f"""
            INSERT INTO demandes_intervention
              (date_demande, demandeur, client, equipement, urgence,
               description, code_erreur, contact_nom, contact_tel,
               statut, technicien_assigne)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """, (
            body.get("date_demande") or now_str,
            demandeur, client, equipement, urgence,
            description, code_erreur, contact_nom, contact_tel,
            statut, ", ".join(techniciens_fullnames),  # All techs in the demand
        ))
        
        # Get the newly created demand ID
        new_demande = conn.execute(
            "SELECT id FROM demandes_intervention ORDER BY id DESC LIMIT 1"
        ).fetchone()
        demande_id = new_demande["id"] if new_demande else None

        # --- Create SINGLE SHARED intervention (visible to all assigned technicians) ---
        # NEW APPROACH: One intervention for ALL technicians instead of N children
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notes_intervention = f"[{client}] Demande #{demande_id}"
        
        # Store all technicians in technicien field (comma-separated for reference)
        # Each tech will update their own row in interventions_techniciens
        all_techs_str = ", ".join(techniciens_fullnames)
        
        conn.execute(f"""
            INSERT INTO interventions
              (date, machine, technicien, type_intervention, description,
               probleme, code_erreur, statut, priorite, notes,
               is_temporary, parent_intervention_id)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """, (
            now,
            equipement,
            all_techs_str,  # Store all technician names
            "Corrective",
            description[:500],
            description[:500],
            code_erreur,
            "Assignée",  # Always "Assignée" for multi-tech shared intervention
            urgence,
            notes_intervention,
            0,  # is_temporary = FALSE (visible to all technicians)
            None,  # No parent - this is a standalone intervention
        ))
        
        intervention = conn.execute(
            "SELECT id FROM interventions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        intervention_id = intervention["id"] if intervention else None
        
        # Link demand to intervention
        if intervention_id:
            conn.execute(
                f"UPDATE demandes_intervention SET intervention_id = {ph} WHERE id = {ph}",
                (intervention_id, demande_id)
            )
        
        # --- Populate interventions_techniciens table: one row per technician ---
        # This table tracks per-technician data (hours, solution, statut)
        if intervention_id:
            for tech_fullname in techniciens_fullnames:
                conn.execute(f"""
                    INSERT INTO interventions_techniciens 
                    (intervention_id, technicien_nom, statut)
                    VALUES ({ph}, {ph}, 'Assigné')
                """, (intervention_id, tech_fullname))
                logger.info(f"[MULTI-TECH] Technician '{tech_fullname}' assigned to intervention #{intervention_id}")
            
            logger.info(f"[MULTI-TECH] Intervention #{intervention_id} created as SHARED with {len(techniciens_fullnames)} technicians: {all_techs_str}")
        
        _trigger_backup()

    # --- Telegram notifications ---
    urg_icon = "\U0001f534" if urgence in ("Haute", "Critique") else "\U0001f7e1" if urgence == "Moyenne" else "\U0001f7e2"
    contact_line = f"\n\U0001f4de Contact : <b>{contact_nom}</b>" + (f" — {contact_tel}" if contact_tel else "") if contact_nom else ""
    code_line    = f"\n\U0001f522 Code erreur : <code>{code_erreur}</code>" if code_erreur else ""
    techs_line   = f"\n\U0001f477 Assigné à : <b>{', '.join(techniciens_fullnames)}</b>" if techniciens_fullnames else ""
    msg = (
        f"\U0001f4cb <b>NOUVELLE DEMANDE D'INTERVENTION</b>\n\n"
        f"\U0001f3e2 Client : <b>{client}</b>\n"
        f"\U0001f3e5 Équipement : <b>{equipement}</b>\n"
        f"{urg_icon} Urgence : <b>{urgence}</b>\n"
        f"\U0001f4dd Problème : {description[:300]}"
        f"{code_line}"
        f"{contact_line}"
        f"{techs_line}\n"
        f"\U0001f464 Demandeur : <b>{demandeur}</b>\n"
        f"\U0001f550 Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        f"\U0001f449 Connectez-vous à <b>SAVIA</b> pour traiter cette demande."
    )
    _send_telegram(msg)
    
    # Log audit
    username = user.get("sub", "unknown")
    log_audit(username, "CREATE_DEMANDE", f"{{\"client\": \"{client}\", \"demande_id\": {demande_id}}}", "demandes")
    
    logger.info(f"Demande #{demande_id} créée avec {len(techniciens_fullnames)} techniciens → Intervention PARTAGÉE #{intervention_id}")
    
    return {"success": True, "demande_id": demande_id, "intervention_id": intervention_id}


@app.put("/api/demandes/{demande_id}/statut")
def update_demande_statut(demande_id: int, body: dict, user: dict = Depends(_verify_token)):
    # Check permission - only Admin, Manager, Responsable Technique can update status
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Seuls les Managers, Responsables et Admins peuvent mettre à jour le statut des demandes"
        )
    
    from db_engine import get_db
    nouveau_statut      = body.get("statut") or "En cours"
    technicien_assigne  = body.get("technicien_assigne") or ""
    # Convert technicien username to full name
    if technicien_assigne:
        technicien_assigne = _get_technician_fullname(technicien_assigne)
    notes_traitement    = body.get("notes_traitement") or ""

    # Récupérer les données de la demande AVANT mise à jour pour le message
    demande_info = {}
    with get_db() as conn:
        row = conn.execute(
            "SELECT client, equipement, urgence, description, demandeur, contact_nom, contact_tel FROM demandes_intervention WHERE id = ?",
            (demande_id,)
        ).fetchone()
        if row:
            demande_info = dict(row)
        conn.execute("""
            UPDATE demandes_intervention
            SET statut = ?, technicien_assigne = ?, notes_traitement = ?,
                date_traitement = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (nouveau_statut, technicien_assigne, notes_traitement, demande_id))

    # --- Notification Telegram (tous les changements de statut) ---
    statut_icons = {
        "En attente": "\u23f3",
        "En cours":   "\U0001f527",
        "Assign\u00e9e": "\U0001f477",
        "R\u00e9solue":  "\u2705",
        "Cl\u00f4tur\u00e9e": "\U0001f3c1",
        "Plan\u00e0fi\u00e9e": "\U0001f4c5",
        "Planifi\u00e9e":  "\U0001f4c5",
        "Rejet\u00e9e":    "\u274c",
        "Accept\u00e9e":  "\u2705",
    }
    icon = statut_icons.get(nouveau_statut, "\U0001f4cb")
    client     = demande_info.get("client", "")
    equipement = demande_info.get("equipement", "")
    urgence    = demande_info.get("urgence", "")
    description = str(demande_info.get("description", ""))[:300]
    demandeur  = demande_info.get("demandeur", "")
    contact_nom = demande_info.get("contact_nom", "")
    contact_tel = demande_info.get("contact_tel", "")

    urg_icon     = "\U0001f534" if urgence in ("Haute", "Critique") else "\U0001f7e1" if urgence == "Moyenne" else "\U0001f7e2"
    tech_line    = f"\n\U0001f477 Technicien : <b>{technicien_assigne}</b>" if technicien_assigne else ""
    notes_line   = f"\n\U0001f4cc Notes : {notes_traitement}" if notes_traitement else ""
    contact_line = f"\n\U0001f4de Contact : <b>{contact_nom}</b>" + (f" — {contact_tel}" if contact_tel else "") if contact_nom else ""
    demandeur_line = f"\n\U0001f464 Demandeur : <b>{demandeur}</b>" if demandeur else ""

    msg = (
        f"{icon} <b>DEMANDE #{demande_id} \u2014 MISE \u00c0 JOUR STATUT</b>\n\n"
        f"\U0001f3e2 Client : <b>{client}</b>\n"
        f"\U0001f3e5 \u00c9quipement : <b>{equipement}</b>\n"
        f"{urg_icon} Urgence : <b>{urgence}</b>\n"
        f"\U0001f4ca Statut : <b>{nouveau_statut}</b>\n"
        f"\U0001f4dd Probl\u00e8me : {description}"
        f"{tech_line}"
        f"{notes_line}"
        f"{contact_line}"
        f"{demandeur_line}\n"
        f"\U0001f550 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    _send_telegram(msg)

    # --- Auto-créer une intervention si technicien assigné et pas déjà liée ---
    if technicien_assigne:
        try:
            with get_db() as conn:
                # Vérifier si une intervention existe déjà pour cette demande
                existing = conn.execute(
                    "SELECT intervention_id FROM demandes_intervention WHERE id = ?",
                    (demande_id,)
                ).fetchone()
                already_linked = existing and existing["intervention_id"]

                if not already_linked:
                    # Créer l'intervention
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    notes_interv = f"[{client}] Demande #{demande_id}"
                    if notes_traitement:
                        notes_interv += f" — {notes_traitement}"
                    conn.execute("""
                        INSERT INTO interventions
                          (date, machine, technicien, type_intervention, description,
                           probleme, code_erreur, statut, priorite, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        now,
                        equipement,
                        technicien_assigne,
                        "Corrective",
                        description[:500],
                        description[:500],
                        demande_info.get("code_erreur", "") or "",
                        "Assignée",
                        urgence,
                        notes_interv,
                    ))
                    # Récupérer l'id de l'intervention créée
                    new_interv = conn.execute(
                        "SELECT id FROM interventions ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if new_interv:
                        conn.execute(
                            "UPDATE demandes_intervention SET intervention_id = ? WHERE id = ?",
                            (new_interv["id"], demande_id)
                        )
                        logger.info(f"Intervention #{new_interv['id']} auto-créée pour demande #{demande_id} → {technicien_assigne}")
                else:
                    # Intervention déjà liée → mettre à jour technicien + statut (ex: réassignation après refus)
                    interv_id = existing["intervention_id"]
                    conn.execute(
                        "UPDATE interventions SET technicien = ?, statut = ? WHERE id = ?",
                        (technicien_assigne, "Assignée", interv_id)
                    )
                    logger.info(f"Intervention #{interv_id} réassignée à {technicien_assigne} (demande #{demande_id})")
        except Exception as e:
            logger.error(f"Erreur auto-création intervention: {e}")

    return {"success": True}


# ------ Technicien Update Per-Technician Data ------

@app.put("/api/interventions/{intervention_id}/technicien-data")
def update_technicien_data(intervention_id: int, body: dict = Body(...), user: dict = Depends(_verify_token)):
    """
    Updates per-technician data in interventions_techniciens table.
    When technician marks their work as Cloturee, check if all are complete.
    Only then finalize the parent intervention.
    
    Expected body:
    {
        "probleme_tech": "...",
        "cause_tech": "...",
        "solution_tech": "...",
        "heure_debut_tech": "HH:MM",
        "heure_fin_tech": "HH:MM",
        "duree_minutes_tech": 60,
        "duree_deplacement_tech": 30,
        "notes_tech": "...",
        "statut": "Cloturee" (marks this tech as done)
    }
    """
    from db_engine import (
        get_db, update_interventions_techniciens, 
        get_or_create_interventions_techniciens, get_techniciens_status,
        finalize_intervention_from_techniciens, consolidate_technician_duplicates
    )
    
    logger.info(f"🔵 PUT /api/interventions/{intervention_id}/technicien-data CALLED")
    logger.info(f"   User: {user.get('nom')} (role: {user.get('role')})")
    logger.info(f"   Body: {body}")
    
    try:
        # Get intervention to verify it exists
        machine = None
        client = None
        technicien = None
        
        with get_db() as conn:
            intervention = conn.execute(
                "SELECT id, machine, technicien FROM interventions WHERE id = ?",
                (intervention_id,)
            ).fetchone()
            
            if not intervention:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
            
            # Extract intervention data
            machine = intervention.get("machine", "")
            technicien = intervention.get("technicien", "")
            
            # Get client from equipements table (joined by machine name)
            try:
                eq_row = conn.execute(
                    "SELECT client FROM equipements WHERE nom = ? LIMIT 1",
                    (machine,)
                ).fetchone()
                if eq_row:
                    client = dict(eq_row).get('client', '') or ''
            except Exception:
                client = ''
            
            # Verify technician permissions
            if user.get("role") == "Technicien":
                current_tech = str(intervention.get("technicien") or "").strip()
                user_nom_complet = (user.get("nom") or "").strip()
                user_username = (user.get("sub") or "").strip()
                
                # Cas 1: Intervention avec champ technicien rempli (single-technicien)
                if current_tech:
                    # Vérifier si c'est une correspondance par NOM (ex: "Salah Al Salah")
                    # OU par USERNAME (ex: "tech_07")
                    # Check both directions: name->tech and username->tech
                    is_assigned = (
                        _tech_name_or_username_matches(user_nom_complet, current_tech) or
                        _tech_name_or_username_matches(user_username, current_tech)
                    )
                    
                    logger.info(f"🔐 Permission check (single-tech): user='{user_nom_complet}' (username={user_username}) vs tech='{current_tech}' → assigned={is_assigned}")
                    if not is_assigned:
                        raise HTTPException(
                            status_code=403,
                            detail="Vous ne pouvez éditer que vos propres interventions"
                        )
                else:
                    # Cas 2: Intervention sans technicien principal (multi-technicien) → vérifier interventions_techniciens
                    logger.info(f"🔐 Permission check (multi-tech): checking interventions_techniciens table")
                    tech_row = conn.execute(
                        "SELECT user_id FROM interventions_techniciens WHERE intervention_id = ? AND user_id = ?",
                        (intervention_id, user_username)  # user_username est le username
                    ).fetchone()
                    
                    if not tech_row:
                        # Technicien n'est pas dans la liste interventions_techniciens
                        logger.warning(f"🔐 Technicien '{user_nom_complet}' (username={user_username}) not in interventions_techniciens for #{intervention_id}")
                        raise HTTPException(
                            status_code=403,
                            detail="Vous ne pouvez éditer que vos propres interventions"
                        )
                    logger.info(f"🔐 Technicien '{user_nom_complet}' found in interventions_techniciens")
        
        # Get or create entry for this technician
        tech_nom = body.get("technicien_nom") or user.get("nom", "Unknown")
        logger.info(f"   ✓ Tech name: {tech_nom}")
        
        get_or_create_interventions_techniciens(intervention_id, tech_nom)
        
        # Update the per-technician data
        success = update_interventions_techniciens(intervention_id, tech_nom, body)
        logger.info(f"   ✓ Update result: {success}")
        
        if not success:
            raise HTTPException(status_code=400, detail="Aucune donnée à mettre à jour")
        
        # Deduct stock if technician marked as Cloturee and pieces are provided
        if body.get("statut") == "Cloturee" and body.get("pieces_a_deduire"):
            try:
                pieces_list = body.get("pieces_a_deduire", [])
                logger.info(f"   📦 Deducting stock for {len(pieces_list)} pieces...")
                
                with get_db() as conn:
                    for piece in pieces_list:
                        if not isinstance(piece, dict):
                            continue
                        ref = piece.get('ref') or piece.get('reference') or ''
                        qty = int(piece.get('qty') or piece.get('quantite') or 0)
                        
                        if qty > 0 and ref:
                            logger.info(f"      Deducting: {ref} qty={qty}")
                            conn.execute("""
                                UPDATE pieces_rechange
                                SET stock_actuel = stock_actuel - %s
                                WHERE reference = %s
                            """, (qty, ref))
                
                logger.info(f"   ✅ Stock deducted successfully")
            except Exception as e:
                logger.warning(f"   ⚠️ Error deducting stock: {e}")
                # Don't fail the whole request if stock deduction fails

        # Handle pieces_rupture if technician marked as "En attente de piece"
        if body.get("statut") == "En attente de piece" and body.get("pieces_rupture"):
            try:
                pieces_rupture_list = body.get("pieces_rupture", [])
                logger.info(f"   🔴 Creating rupture badges for {len(pieces_rupture_list)} pieces...")
                
                with get_db() as conn:
                    for piece in pieces_rupture_list:
                        if not isinstance(piece, dict):
                            continue
                        ref = piece.get('reference', '')
                        designation = piece.get('designation', '')
                        
                        if ref:
                            # Create rupture notification (same as mode single tech)
                            conn.execute("""
                                INSERT INTO notif_rupture (intervention_id, reference, designation, created_at)
                                VALUES (?, ?, ?, datetime('now'))
                            """, (intervention_id, ref, designation))
                            logger.info(f"      Created rupture badge: {ref} - {designation}")
                
                logger.info(f"   ✅ Rupture badges created successfully")
                
                # Send Telegram notification
                try:
                    pieces_txt = ""
                    if pieces_rupture_list:
                        pieces_txt = "\n".join([f"  • {p.get('reference', '')} — {p.get('designation', '')}" for p in pieces_rupture_list if p.get("reference")])
                    
                    if pieces_txt:
                        msg_tg = (
                            f"🔴 <b>Pièce(s) en rupture — #{intervention_id}</b>\n\n"
                            f"⚠️ Pièces manquantes :\n{pieces_txt}\n\n"
                            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                        )
                        _send_telegram_bot("telegram_stock", msg_tg)
                        _send_telegram("📬 " + msg_tg)
                        logger.info(f"📬 Rupture notification sent")
                except Exception as tg_err:
                    logger.warning(f"   ⚠️ Telegram rupture notification failed: {tg_err}")
            except Exception as e:
                logger.warning(f"   ⚠️ Error handling rupture pieces: {e}")
                # Don't fail the whole request if rupture handling fails

        # Handle pieces_manuelles (manual/non-referenced pieces) - multi-tech mode
        if body.get("pieces_manuelles"):
            try:
                pieces_manuelles_list = body.get("pieces_manuelles", [])
                logger.info(f"   📋 Creating manual piece requests for {len(pieces_manuelles_list)} pieces...")
                
                for piece in pieces_manuelles_list:
                    if not isinstance(piece, dict):
                        continue
                    ref = piece.get('reference', '').strip()
                    designation = piece.get('designation', '').strip()
                    
                    if ref:
                        # Create manual piece request (same as mode single tech, using same function)
                        # Use tech_nom (current technician) instead of original technicien
                        ajouter_piece_demandee({
                            "reference": ref,
                            "designation": designation,
                            "intervention_id": intervention_id,
                            "equipement": machine,
                            "client": client,
                            "technicien": tech_nom,  # Use current tech submitting, not original
                            "probleme": "",
                        })
                        # Notification gestionnaire (same as single-tech mode)
                        ajouter_notification_piece({
                            "type": "piece_rupture",
                            "intervention_id": intervention_id,
                            "piece_reference": ref,
                            "piece_nom": designation,
                            "intervention_ref": f"#{intervention_id}",
                            "equipement": machine,
                            "client": client,
                            "technicien": tech_nom,  # Use current tech submitting
                            "message": f"🆕 Pièce non référencée demandée: {ref} ({designation}) "
                                       f"pour intervention #{intervention_id} sur {machine}",
                            "source": "sav",
                            "destination": "gestionnaire",
                        })
                        logger.info(f"      Created manual piece request: {ref} - {designation}")
                
                logger.info(f"   ✅ Manual piece requests created successfully")
                
                # Send Telegram notification (same format as single-tech mode)
                try:
                    pm_list = [f"  • {p.get('reference','')} — {p.get('designation','')}" for p in pieces_manuelles_list if p.get("reference")]
                    if pm_list:
                        client_line_m = f"\n👤 Client : <b>{client}</b>" if client else ""
                        msg_tg_m = (
                            f"🆕 <b>DEMANDE PIÈCE NON RÉFÉRENCÉE — #{intervention_id}</b>\n\n"
                            f"🏥 Machine : <b>{machine}</b>"
                            f"{client_line_m}\n"
                            f"👷 Technicien : <b>{tech_nom}</b>\n"
                            f"🔩 Pièces demandées :\n" + "\n".join(pm_list) + "\n\n"
                            f"⚠️ Ces pièces ne sont pas dans le stock — à commander\n"
                            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                        )
                        # Send to both stock bot and tech bot (same as single-tech mode)
                        _send_telegram_bot("telegram_stock", msg_tg_m)
                        _send_telegram_bot("telegram", msg_tg_m)
                        logger.info(f"📋 Manual piece notifications sent to both bots")
                except Exception as tg_err:
                    logger.warning(f"   ⚠️ Telegram manual piece notification failed: {tg_err}")
            except Exception as e:
                logger.warning(f"   ⚠️ Error handling manual pieces: {e}")
                # Don't fail the whole request if manual piece handling fails
                # Don't fail the whole request if manual piece handling fails
        
        # Consolidate any duplicate technician records (with reversed names)
        consolidate_technician_duplicates(intervention_id)
        
        # Get current status
        status_info = get_techniciens_status(intervention_id)
        
        # Check if all technicians are now completed
        if status_info['is_all_completed']:
            # All done - aggregate data AND automatically close the parent intervention
            finalize_result = finalize_intervention_from_techniciens(intervention_id)
            
            if finalize_result.get('success'):
                logger.info(f"✅ Intervention #{intervention_id} AUTOMATICALLY CLOSED after all {status_info['total']} technicians completed")
                
                # Send Telegram: INTERVENTION CLOSED - À FACTURER
                try:
                    # Fetch updated intervention data with pieces_utilisees
                    with get_db() as conn:
                        updated_row = conn.execute(
                            "SELECT machine, technicien, probleme, cause, solution, duree_minutes, notes, pieces_utilisees FROM interventions WHERE id = ?",
                            (intervention_id,)
                        ).fetchone()
                    
                    if updated_row:
                        d = dict(updated_row)
                    else:
                        d = {'machine': machine, 'pieces_utilisees': ''}
                    
                    machine = d.get('machine', '')
                    total_duree_h = round(finalize_result.get('total_duree_minutes', 0) / 60, 1)
                    solutions = finalize_result.get('combined_solution', '')
                    pieces = str(d.get('pieces_utilisees', '') or '').strip()
                    
                    # Get client info from notes or equipement
                    notes_raw = str(d.get('notes', '') or intervention.get('notes', '') or '')
                    client_name = notes_raw[1:notes_raw.index(']')] if notes_raw.startswith('[') and ']' in notes_raw else ''
                    client_line = f"\n👤 Client : <b>{client_name}</b>" if client_name else ""
                    pieces_line = f"\n🔩 Pièces : {pieces}" if pieces else ""
                    
                    # Message for SAV team: À facturer
                    msg_sav = (
                        f"📋 <b>Intervention À facturer — #{intervention_id}</b>\n\n"
                        f"🏥 Machine : <b>{machine}</b>"
                        f"{client_line}\n"
                        f"👷 Tous les techniciens : <b>{status_info['total']}/{status_info['total']}</b>\n"
                        f"⏱️ Durée totale : <b>{total_duree_h}h</b>\n"
                        f"🔧 Solutions : {solutions}"
                        f"{pieces_line}\n"
                        f"✅ Intervention fermée automatiquement\n"
                        f"💰 <i>Délai de facturation : 10 jours</i>\n"
                        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    )
                    _send_telegram_bot("telegram_sav", msg_sav)
                    logger.info(f"✅ Telegram SAV message sent: Intervention #{intervention_id} à facturer")
                    
                    # Message for technicians: INTERVENTION CLÔTURÉE
                    msg_tech = (
                        f"✅ <b>INTERVENTION CLÔTURÉE — #{intervention_id}</b>\n\n"
                        f"🏥 Machine : <b>{machine}</b>"
                        f"{client_line}\n"
                        f"👷 Tous les techniciens : <b>{status_info['total']}/{status_info['total']}</b>\n"
                        f"⏱️ Durée totale : <b>{total_duree_h}h</b>\n"
                        f"🔧 Solutions : {solutions}"
                        f"{pieces_line}\n"
                        f"✅ Intervention fermée automatiquement\n"
                        f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    )
                    _send_telegram(msg_tech)
                    logger.info(f"✅ Telegram TECH message sent: Intervention #{intervention_id} clôturée")
                except Exception as te:
                    logger.warning(f"⚠️ Closing telegram notifications failed: {te}")
                
                return {
                    "success": True,
                    "message": f"✅ Tous les techniciens ont complété! Intervention #{intervention_id} clôturée automatiquement.",
                    "intervention_finalized": True,
                    "status": "CLOSED",
                    "completed": status_info['completed'],
                    "total": status_info['total']
                }
            else:
                logger.error(f"❌ Finalization failed: {finalize_result}")
                return HTTPException(status_code=500, detail="Erreur lors de la finalisation")
        else:
            logger.info(f"   ✓ Partial completion: {status_info['completed']}/{status_info['total']}")
            # Partial completion - still waiting for others
            pending_list = ", ".join(status_info['pending_names'])
            logger.info(f"⏳ Intervention #{intervention_id} partially complete: {status_info['completed']}/{status_info['total']} (pending: {pending_list})")
            
            # Send Telegram: PARTIALLY CLOSED - but only if this technician marked as "Cloturee"
            # Don't send if technician marked as "En attente de piece"
            if body.get("statut") == "Cloturee":
                try:
                    machine = intervention.get('machine', '')
                    msg_tg = (
                        f"⏳ <b>INTERVENTION PARTIELLEMENT CLÔTURÉE — #{intervention_id}</b>\n\n"
                        f"🏥 Machine : <b>{machine}</b>\n"
                        f"✅ Techniciens complétés : <b>{status_info['completed']}/{status_info['total']}</b>\n"
                        f"⏳ Techniciens restants :\n"
                    )
                    for pending_tech in status_info['pending_names']:
                        msg_tg += f"  • {pending_tech}\n"
                    
                    msg_tg += f"\n🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                    _send_telegram(msg_tg)
                    logger.info(f"✅ Partial closure telegram sent: Intervention #{intervention_id} ({status_info['completed']}/{status_info['total']} completed)")
                except Exception as te:
                    logger.warning(f"⚠️ Partial closure telegram notification failed (will retry later): {te}")
            else:
                logger.info(f"   ✓ Technician marked as '{body.get('statut')}' - no partial closure telegram sent")
            
            logger.info(f"   ✓ Returning PARTIAL response with {len(status_info['pending_names'])} pending: {status_info['pending_names']}")
            return {
                "success": True,
                "message": f"Données sauvegardées ({status_info['completed']}/{status_info['total']} techniciens complétés)",
                "intervention_finalized": False,
                "status": "PARTIAL",
                "completed": status_info['completed'],
                "total": status_info['total'],
                "pending_technicians": status_info['pending_names']
            }
        
    except HTTPException:
        logger.error(f"❌ HTTPException in update_technicien_data")
        raise
    except Exception as e:
        logger.error(f"❌ Erreur update_technicien_data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/interventions/{intervention_id}/techniciens")
def get_intervention_techniciens(intervention_id: int, user: dict = Depends(_verify_token)):
    """
    Récupère tous les enregistrements de techniciens pour une intervention.
    Retourne les données per-technician depuis interventions_techniciens table.
    """
    from db_engine import get_db, get_interventions_techniciens
    
    try:
        # Verify intervention exists
        with get_db() as conn:
            intervention = conn.execute(
                "SELECT id FROM interventions WHERE id = %s",
                (intervention_id,)
            ).fetchone()
            
            if not intervention:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
        
        # Get technician records
        tech_records = get_interventions_techniciens(intervention_id)
        
        # Convert to list of dicts for JSON serialization
        result = []
        for record in tech_records:
            result.append(dict(record) if hasattr(record, 'keys') else record)
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur get_intervention_techniciens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/interventions/{intervention_id}/techniciens-aggregated")
def get_intervention_techniciens_aggregated(intervention_id: int, user: dict = Depends(_verify_token)):
    """
    Retourne les données agrégées de tous les techniciens pour une intervention.
    Utilisé pour afficher un tableau récapitulatif et générer les PDFs multi-tech.
    
    Retourne:
    {
        "intervention_id": int,
        "total_duree_minutes": int (somme de tous),
        "total_duree_deplacement": int (somme de tous),
        "tous_solutions": [{"technicien": str, "solution": str}],
        "statut_completion": bool (tous complétés?),
        "techniciens": [
            {
                "nom": str,
                "probleme": str,
                "cause": str,
                "solution": str,
                "heure_debut": str (HH:MM),
                "heure_fin": str (HH:MM),
                "duree_minutes": int,
                "duree_deplacement": int,
                "statut": str
            }
        ]
    }
    """
    from db_engine import get_db, get_interventions_techniciens
    
    try:
        # Verify intervention exists
        with get_db() as conn:
            intervention = conn.execute(
                "SELECT id, statut FROM interventions WHERE id = %s",
                (intervention_id,)
            ).fetchone()
            
            if not intervention:
                raise HTTPException(status_code=404, detail="Intervention non trouvée")
        
        # Get all technician records
        tech_records = get_interventions_techniciens(intervention_id)
        
        # Aggregate data
        total_duree = 0
        total_deplacement = 0
        solutions_list = []
        all_completed = True
        techniciens_data = []
        
        for record in tech_records:
            rec_dict = dict(record) if hasattr(record, 'keys') else record
            
            duree = int(rec_dict.get('duree_minutes_tech') or 0)
            deplacement = int(rec_dict.get('duree_deplacement_tech') or 0)
            
            total_duree += duree
            total_deplacement += deplacement
            
            statut = str(rec_dict.get('statut') or 'En cours')
            if statut != 'Cloturee':
                all_completed = False
            
            solution = str(rec_dict.get('solution_tech') or '')
            if solution.strip():
                solutions_list.append({
                    "technicien": rec_dict.get('technicien_nom', 'Unknown'),
                    "solution": solution
                })
            
            # Build tech data entry
            techniciens_data.append({
                "nom": rec_dict.get('technicien_nom', 'Unknown'),
                "probleme": str(rec_dict.get('probleme_tech') or ''),
                "cause": str(rec_dict.get('cause_tech') or ''),
                "solution": solution,
                "heure_debut": str(rec_dict.get('heure_debut_tech') or ''),
                "heure_fin": str(rec_dict.get('heure_fin_tech') or ''),
                "duree_minutes": duree,
                "duree_deplacement": deplacement,
                "statut": statut
            })
        
        return {
            "intervention_id": intervention_id,
            "total_duree_minutes": total_duree,
            "total_duree_deplacement": total_deplacement,
            "tous_solutions": solutions_list,
            "statut_completion": all_completed,
            "techniciens": techniciens_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur get_intervention_techniciens_aggregated: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------ Technicien Accept / Refuse intervention ------

@app.put("/api/interventions/{intervention_id}/accept")
def accept_intervention(intervention_id: int, user: dict = Depends(_verify_token)):
    from db_engine import get_db
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, machine, technicien, statut FROM interventions WHERE id = ?",
            (intervention_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Intervention introuvable")

        conn.execute(
            "UPDATE interventions SET statut = ? WHERE id = ?",
            ("En cours", intervention_id)
        )

    tech_name = user.get("nom") or user.get("username") or "?"
    machine = row["machine"] if row else ""
    msg = (
        f"\u2705 <b>INTERVENTION #{intervention_id} — ACCEPTÉE</b>\n\n"
        f"\U0001f477 Technicien : <b>{tech_name}</b>\n"
        f"\U0001f3e5 Équipement : <b>{machine}</b>\n"
        f"\U0001f4ca Statut : <b>En cours</b>\n"
        f"\U0001f550 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    _send_telegram(msg)

    return {"success": True, "statut": "En cours"}


@app.put("/api/interventions/{intervention_id}/refuse")
def refuse_intervention(intervention_id: int, body: dict, user: dict = Depends(_verify_token)):
    from db_engine import get_db
    raison = body.get("raison", "").strip()
    if not raison:
        raise HTTPException(status_code=400, detail="La raison du refus est obligatoire")

    with get_db() as conn:
        row = conn.execute(
            """SELECT id, machine, technicien, statut, notes,
                      (SELECT e.client FROM equipements e WHERE LOWER(e.nom) = LOWER(interventions.machine) LIMIT 1) AS client
               FROM interventions WHERE id = ?""",
            (intervention_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Intervention introuvable")

        tech_name = user.get("nom") or user.get("username") or row.get("technicien", "?")
        machine = row["machine"] if row else ""
        client = row.get("client", "") or ""

        # Mark intervention back to "En attente" and clear technician
        conn.execute(
            "UPDATE interventions SET statut = ?, technicien = ?, notes = COALESCE(notes, '') || ? WHERE id = ?",
            ("En attente", "", f"\n[REFUS par {tech_name}] {raison}", intervention_id)
        )

        # Also update the linked demande if it exists
        conn.execute("""
            UPDATE demandes_intervention
            SET statut = 'En attente', technicien_assigne = '',
                notes_traitement = COALESCE(notes_traitement, '') || ?
            WHERE intervention_id = ?
        """, (f"\n[REFUS par {tech_name}] {raison}", intervention_id))

    # Send Telegram notification
    msg = (
        f"\u274c <b>INTERVENTION #{intervention_id} — REFUSÉE</b>\n\n"
        f"\U0001f477 Technicien : <b>{tech_name}</b>\n"
        f"\U0001f3e5 Équipement : <b>{machine}</b>\n"
        f"\U0001f3e2 Client : <b>{client}</b>\n"
        f"\U0001f4ac Raison : <i>{raison}</i>\n\n"
        f"\u23f3 Statut : <b>En attente</b> — à réassigner\n"
        f"\U0001f550 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    _send_telegram(msg)

    return {"success": True, "statut": "En attente"}


# ==========================================
# PIÈCES DE RECHANGE
# ==========================================

@app.get("/api/pieces")
def get_pieces(user: dict = Depends(_verify_token)):
    return _df_to_records(lire_pieces())


@app.get("/api/pieces/predictions/priorite")
def get_pieces_a_commander(limit: int = 10, user: dict = Depends(_verify_token)):
    """
    Retourne les pièces à commander en priorité (N pièces les plus urgentes).
    Utilise la prédiction avancée multi-facteur.
    
    Query params:
        - limit: Nombre de pièces à retourner (défaut: 10)
    
    Returns:
        List of pieces ranked by urgence (CRITIQUE, HAUTE, NORMALE, BASSE)
    """
    try:
        predictions = predict_pieces_a_commander(nb_to_return=limit)
        return predictions
    except Exception as e:
        logger.error(f"Erreur prédiction pièces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pieces/{piece_id}/prediction")
def predict_piece_order_date(piece_id: int, user: dict = Depends(_verify_token)):
    """
    Génère une prédiction détaillée pour une pièce spécifique.
    Utilise tous les paramètres avancés (consommation, lead time, criticité, etc).
    
    Returns:
        {
            'date_commande': ISO date,
            'urgence': 'CRITIQUE' | 'HAUTE' | 'NORMALE' | 'BASSE',
            'raison': str (explication du calcul),
            'jours_avant_rupture': float,
            'stock_previsionnel_jours': float,
            'details': {...}
        }
    """
    try:
        with get_db() as conn:
            piece = conn.execute(
                """SELECT id, reference, designation, stock_actuel, stock_minimum,
                          consommation_moyenne_mois, delai_fournisseur_jours, criticite,
                          prix_unitaire, nombre_equipements_relies, utilisation_recente_30j
                   FROM pieces_rechange WHERE id = ?""",
                (piece_id,)
            ).fetchone()
        
        if not piece:
            raise HTTPException(status_code=404, detail="Pièce non trouvée")
        
        prediction = predict_commande_date(dict(piece))
        return {
            'piece_id': piece_id,
            'reference': piece['reference'],
            'designation': piece['designation'],
            **prediction
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur prédiction pièce {piece_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _normalize_ref(ref: str) -> str:
    """Normalise une référence pour matching flou: supprime tirets, espaces, points, underscores, met en minuscule."""
    import re
    return re.sub(r'[\s\-_.\\/]+', '', ref).lower().strip()


def _refs_match(ref1: str, ref2: str) -> bool:
    """Vérifie si deux références correspondent (matching strict normalisé).
    Normalise en supprimant tirets, espaces, points, underscores et compare en minuscule.
    Ex: PS-XR400 == PSXR400 == ps xr 400  ✅
    Ex: XR400 != PS-XR400  ❌ (pas de matching partiel pour éviter les faux positifs)
    """
    n1 = _normalize_ref(ref1)
    n2 = _normalize_ref(ref2)
    if not n1 or not n2:
        return False
    return n1 == n2


def _check_pieces_demandees_disponibles(reference: str, nom_piece: str, stock: int):
    """Vérifie si des demandes de pièces en attente correspondent à cette référence.
    Utilise un matching flou (normalisation des tirets, espaces, casse).
    Si oui, envoie notifications PWA + Telegram et marque les demandes comme résolues."""
    # Récupérer TOUTES les demandes en attente et filtrer par matching flou
    df_demandes = lire_pieces_demandees_en_attente()  # sans filtre ref
    if df_demandes.empty:
        return

    # Filtrer par matching flou
    matched_indices = []
    for idx, d in df_demandes.iterrows():
        demande_ref = d.get("reference") or ""
        if _refs_match(reference, demande_ref):
            matched_indices.append(idx)
    
    if not matched_indices:
        return
    
    df_matched = df_demandes.loc[matched_indices]

    # Grouper par technicien
    tech_map: dict = {}
    for _, d in df_matched.iterrows():
        t = d.get("technicien") or "inconnu"
        if t not in tech_map:
            tech_map[t] = []
        tech_map[t].append({
            "intervention_id": d.get("intervention_id") or "",
            "equipement": d.get("equipement") or "",
            "client": d.get("client") or "",
            "probleme": d.get("probleme") or "",
            "demande_id": int(d["id"]),
        })

    for tech, demandes in tech_map.items():
        machines = ", ".join(set(d["equipement"] for d in demandes if d["equipement"]))
        clients = ", ".join(set(d["client"] for d in demandes if d.get("client")))
        problemes = "; ".join(set(d["probleme"] for d in demandes if d.get("probleme")))
        inter_ids = ", ".join(f"#{d['intervention_id']}" for d in demandes if d.get("intervention_id"))
        nb = len(demandes)
        # Notification PWA → technicien
        ajouter_notification_piece({
            "type": "piece_dispo",
            "piece_reference": reference,
            "piece_nom": nom_piece,
            "technicien": tech,
            "equipement": machines,
            "client": clients,
            "message": (
                f"✅ La pièce demandée {reference} ({nom_piece}) est maintenant disponible — "
                f"{nb} intervention(s) en attente : {inter_ids or 'N/A'}"
            ),
            "source": "stock",
            "destination": "technicien",
        })
        logger.info(f"Notif pièce demandée disponible pour {tech}: {reference}")

    # Telegram : pièce demandée disponible
    try:
        all_techs = ", ".join(tech_map.keys()) or "N/A"
        all_machines = ", ".join(
            set(d["equipement"] for ds in tech_map.values() for d in ds if d.get("equipement"))
        ) or "N/A"
        all_clients = ", ".join(
            set(d["client"] for ds in tech_map.values() for d in ds if d.get("client"))
        ) or "N/A"
        all_problemes = "; ".join(
            set(d["probleme"] for ds in tech_map.values() for d in ds if d.get("probleme"))
        )
        all_inter_ids = ", ".join(
            f"#{d['intervention_id']}" for ds in tech_map.values() for d in ds if d.get("intervention_id")
        ) or "N/A"
        client_line = f"\n👤 Client : <b>{all_clients}</b>" if all_clients != "N/A" else ""
        probleme_line = f"\n🔧 Problème : {all_problemes}" if all_problemes else ""
        msg_tg = (
            f"🟢 <b>PIÈCE DEMANDÉE DISPONIBLE</b>\n\n"
            f"🔩 Pièce : <b>{nom_piece}</b>\n"
            f"🏷 Référence : <b>{reference}</b>\n"
            f"📦 Stock actuel : <b>{stock}</b>\n\n"
            f"🔗 Intervention(s) : {all_inter_ids}\n"
            f"🏥 Équipement(s) : {all_machines}"
            f"{client_line}"
            f"{probleme_line}\n"
            f"👷 Technicien(s) : {all_techs}\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        _send_telegram_bot("telegram", msg_tg)
        logger.info(f"Telegram pièce demandée disponible envoyé: {reference}")
    except Exception as tg_err:
        logger.error(f"Telegram pièce demandée dispo erreur: {tg_err}")

    # Marquer les demandes comme résolues
    for ds in tech_map.values():
        for d in ds:
            try:
                resoudre_piece_demandee(d["demande_id"])
            except Exception:
                pass


# ── API Pièces demandées (non référencées) ──

@app.get("/api/pieces-demandees")
def get_pieces_demandees(statut: str = None, user: dict = Depends(_verify_token)):
    """Liste les demandes de pièces. ?statut=en_attente pour filtrer."""
    df = lire_toutes_pieces_demandees(statut=statut)
    return _df_to_records(df)


@app.post("/api/pieces-demandees/{demande_id}/resoudre")
def resolve_piece_demandee(demande_id: int, user: dict = Depends(_verify_token)):
    """Résoudre manuellement une demande de pièce (le gestionnaire confirme la disponibilité)."""
    try:
        # Récupérer la demande pour envoyer la notification
        df = lire_toutes_pieces_demandees()
        demande = None
        for _, d in df.iterrows():
            if int(d["id"]) == demande_id:
                demande = d
                break
        
        resoudre_piece_demandee(demande_id)
        
        # Envoyer notification au technicien si on a les infos
        if demande is not None:
            tech = demande.get("technicien") or ""
            ref = demande.get("reference") or ""
            designation = demande.get("designation") or ref
            intervention_id = demande.get("intervention_id") or ""
            client = demande.get("client") or ""
            equipement = demande.get("equipement") or ""
            probleme = demande.get("probleme") or ""
            if tech:
                ajouter_notification_piece({
                    "type": "piece_dispo",
                    "piece_reference": ref,
                    "piece_nom": designation,
                    "technicien": tech,
                    "intervention_id": intervention_id,
                    "equipement": equipement,
                    "client": client,
                    "message": f"✅ La pièce demandée {ref} ({designation}) est maintenant disponible — intervention #{intervention_id}",
                    "source": "stock",
                    "destination": "technicien",
                })
                # Telegram avec détails complets
                client_line = f"\n👤 Client : <b>{client}</b>" if client else ""
                equip_line = f"\n🏥 Équipement : <b>{equipement}</b>" if equipement else ""
                probleme_line = f"\n🔧 Problème : {probleme}" if probleme else ""
                msg_tg = (
                    f"🟢 <b>PIÈCE DEMANDÉE DISPONIBLE</b>\n\n"
                    f"🔩 Pièce : <b>{designation}</b>\n"
                    f"🏷 Référence : <b>{ref}</b>\n"
                    f"🔗 Intervention : #{intervention_id}"
                    f"{client_line}"
                    f"{equip_line}"
                    f"{probleme_line}\n"
                    f"👷 Technicien : {tech}\n"
                    f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                )
                _send_telegram_bot("telegram", msg_tg)
        
        return {"ok": True}
    except Exception as e:
        logger.error(f"Erreur résolution pièce demandée: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pieces")
def create_piece(body: dict, user: dict = Depends(_verify_token)):
    # Check permission
    if not _check_create_piece_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Gestionnaires de stock, Responsables, Managers et Admins"
        )
    
    ajouter_piece(body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "reference": body.get("reference", ""),
        "designation": body.get("designation", ""),
        "stock_initial": body.get("stock_actuel", 0),
    }, ensure_ascii=False)
    log_audit(username, "CREATE_PIECE", details, "pieces")

    # Vérifier si cette pièce était demandée par un technicien (non référencée)
    reference = body.get("reference", "")
    stock = int(body.get("stock_actuel", 0) or 0)
    nom_piece = body.get("designation", "") or reference
    if reference and stock > 0:
        try:
            _check_pieces_demandees_disponibles(reference, nom_piece, stock)
        except Exception as e:
            logger.error(f"Erreur check pièces demandées (POST): {e}")

    return {"ok": True}


@app.put("/api/pieces/{piece_id}")
def update_piece(piece_id: int, body: dict, user: dict = Depends(_verify_token)):
    """Mise à jour d'une pièce. Si stock passe de 0 → >0, déclenche notifications pour les techniciens en attente."""
    # Récupérer le stock AVANT modification pour détecter le réapprovisionnement
    nouveau_stock = body.get("stock_actuel")
    try:
        with get_db() as conn:
            old = conn.execute(
                "SELECT reference, designation, stock_actuel FROM pieces_rechange WHERE id = ?",
                (piece_id,)
            ).fetchone()
        stock_avant = int(old["stock_actuel"]) if old else None
        reference = old["reference"] if old else ""
        nom_piece = old["designation"] if old else ""
    except Exception:
        stock_avant = None
        reference = ""
        nom_piece = ""

    modifier_piece(piece_id, body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "piece_id": piece_id,
        "reference": reference,
        "changes": body,
    }, ensure_ascii=False)
    log_audit(username, "UPDATE_PIECE", details, "pieces")

    # Détecter réapprovisionnement : stock passe de 0 (ou négatif) → positif
    if nouveau_stock is not None and stock_avant is not None:
        try:
            if int(stock_avant) <= 0 and int(nouveau_stock) > 0 and reference:
                # Chercher toutes les notifications rupture non traitées pour cette pièce
                df_notifs = notifications_rupture_pour_piece(reference)
                if not df_notifs.empty:
                    # Grouper par technicien
                    tech_map: dict = {}
                    for _, n in df_notifs.iterrows():
                        t = n.get("technicien") or "inconnu"
                        if t not in tech_map:
                            tech_map[t] = []
                        tech_map[t].append({
                            "machine": n.get("equipement") or "",
                            "intervention_id": n.get("intervention_id") or "",
                        })

                    for tech, interventions_list in tech_map.items():
                        machines = ", ".join(set(i["machine"] for i in interventions_list if i["machine"]))
                        nb = len(interventions_list)
                        inter_ids = ", ".join(
                            f"#{i['intervention_id']}" for i in interventions_list if i.get("intervention_id")
                        )
                        ajouter_notification_piece({
                            "type": "piece_dispo",
                            "piece_reference": reference,
                            "piece_nom": nom_piece,
                            "technicien": tech,
                            "equipement": machines,
                            "message": (
                                f"✅ La pièce {reference} ({nom_piece}) est maintenant disponible — "
                                f"{nb} intervention(s) en attente sur : {machines or 'N/A'}"
                            ),
                            "source": "stock",
                            "destination": "technicien",
                        })
                        logger.info(f"Notif piece_dispo créée pour technicien {tech}: pièce {reference}")

                    # --- Telegram : pièce à nouveau disponible ---
                    try:
                        all_techs = ", ".join(tech_map.keys()) or "N/A"
                        all_machines = ", ".join(
                            set(i["machine"] for ivs in tech_map.values() for i in ivs if i.get("machine"))
                        ) or "N/A"
                        all_inter_ids = ", ".join(
                            f"#{i['intervention_id']}"
                            for ivs in tech_map.values() for i in ivs
                            if i.get("intervention_id")
                        ) or "N/A"
                        msg_tg = (
                            f"🟢 <b>PIÈCE DISPONIBLE</b>\n\n"
                            f"🔩 Pièce : <b>{nom_piece}</b>\n"
                            f"🏷 Référence : <b>{reference}</b>\n"
                            f"📦 Stock actuel : <b>{nouveau_stock}</b>\n\n"
                            f"🔗 Intervention(s) concernée(s) : {all_inter_ids}\n"
                            f"🏥 Équipement(s) : {all_machines}\n"
                            f"👷 Technicien(s) : {all_techs}\n"
                            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
                        )
                        _send_telegram(msg_tg)
                        logger.info(f"Telegram pièce disponible envoyé: {reference}")
                    except Exception as tg_err:
                        logger.error(f"Telegram pièce dispo erreur: {tg_err}")

                    # Marquer les notifications rupture comme traitées
                    for _, n in df_notifs.iterrows():
                        try:
                            marquer_notification_traitee(int(n["id"]))
                        except Exception:
                            pass
        except Exception as ne:
            logger.error(f"Erreur notif réappro pièce {piece_id}: {ne}")

    # Vérifier aussi les pièces demandées manuellement (non référencées)
    if nouveau_stock is not None and reference:
        try:
            if int(nouveau_stock) > 0:
                _check_pieces_demandees_disponibles(reference, nom_piece, int(nouveau_stock))
        except Exception as e:
            logger.error(f"Erreur check pièces demandées (PUT): {e}")

    return {"ok": True}


@app.delete("/api/pieces/{piece_id}")
def delete_piece(piece_id: int, user: dict = Depends(_verify_token)):
    # Get piece info before deleting
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT reference, designation FROM pieces_rechange WHERE id = ?",
                (piece_id,)
            ).fetchone()
            piece_info = dict(row) if row else {"reference": "Unknown", "designation": "Unknown"}
    except:
        piece_info = {"reference": "Unknown", "designation": "Unknown"}
    
    supprimer_piece(piece_id)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "piece_id": piece_id,
        "reference": piece_info.get("reference", ""),
        "designation": piece_info.get("designation", ""),
    }, ensure_ascii=False)
    log_audit(username, "DELETE_PIECE", details, "pieces")
    
    return {"ok": True}


@app.post("/api/pieces/recalculate-parameters")
def recalculate_piece_parameters(user: dict = Depends(_verify_token)):
    """
    Recalculate and update all piece parameters from historical data.
    This triggers the automatic calculation of:
    - consommation_moyenne_mois
    - nombre_equipements_relies  
    - utilisation_recente_30j
    - data_confidence level
    
    Used for testing or manual refresh.
    """
    try:
        result = update_piece_parameters_batch()
        
        if result.get('success'):
            logger.info(f"Piece parameters updated: {result['updated']} pieces updated, {result['failed']} failed")
            
            # Log audit
            username = user.get("sub", "unknown")
            log_audit(username, "RECALCULATE_PIECE_PARAMETERS", 
                     f"Updated {result['updated']} pieces", "pieces")
            
            return {
                'success': True,
                'message': 'Parametres recalcules avec succes',
                'updated': result['updated'],
                'failed': result['failed'],
                'total': result['total']
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('error', 'Unknown error'))
    except Exception as e:
        logger.error(f"Erreur recalculate_piece_parameters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pieces/{piece_id}/parameters")
def get_piece_parameters(piece_id: int, user: dict = Depends(_verify_token)):
    """
    Get calculated parameters for a specific piece with confidence level.
    Shows:
    - consommation_moyenne_mois
    - data_confidence level
    - Reasoning for prediction reliability
    """
    try:
        with get_db() as conn:
            piece = conn.execute("""
                SELECT reference, designation, equipement_type,
                       consommation_moyenne_mois, delai_fournisseur_jours, criticite,
                       nombre_equipements_relies, utilisation_recente_30j
                FROM pieces_rechange WHERE id = %s
            """, (piece_id,)).fetchone()
            
            if not piece:
                raise HTTPException(status_code=404, detail="Piece not found")
            
            # Recalculate to get current confidence level
            params = calculate_piece_parameters(
                piece['reference'],
                piece['equipement_type']
            )
            
            return {
                'piece_id': piece_id,
                'reference': piece['reference'],
                'designation': piece['designation'],
                'consommation_moyenne_mois': piece['consommation_moyenne_mois'],
                'data_confidence': params['data_confidence'],
                'utilisation_recente_30j': piece['utilisation_recente_30j'],
                'nombre_equipements_relies': piece['nombre_equipements_relies'],
                'details': params['details']
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur get_piece_parameters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# CONTRATS
# ==========================================

@app.get("/api/contrats")
def get_contrats(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    # Pour Lecteur : forcer le filtre par son client
    effective_client = _get_client_filter(user) or client
    df = lire_contrats(client=effective_client)
    records = _df_to_records(df)
    
    # Enrich each contract with its equipements array
    for record in records:
        contrat_id = record.get("id")
        if contrat_id:
            try:
                equipements = get_contract_equipements(contrat_id)
                record["equipements"] = equipements if equipements else []
            except Exception as e:
                logger.debug(f"Could not get equipements for contract {contrat_id}: {e}")
                record["equipements"] = []
    
    return records


@app.post("/api/contrats")
def create_contrat(body: dict, user: dict = Depends(_verify_token)):
    contrat_id = ajouter_contrat(body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "client": body.get("client", ""),
        "equipements": body.get("equipements", []),
        "recurrence": body.get("recurrence_maintenance", ""),
        "contrat_id": contrat_id,
    }, ensure_ascii=False)
    log_audit(username, "CREATE_CONTRAT", details, "contrats")
    
    nb_plannings = 0
    if contrat_id:
        try:
            nb_plannings = generer_planning_from_contrat(contrat_id)
            if nb_plannings > 0:
                logger.info(f"✅ Contrat #{contrat_id}: {nb_plannings} maintenance(s) préventive(s) planifiées")
                # Notification Telegram - Send in background (non-blocking)
                def send_telegram_async():
                    try:
                        recurrence = body.get("recurrence_maintenance", "")
                        equipements = body.get("equipements", [])
                        if isinstance(equipements, str):
                            equipements = [equipements] if equipements else []
                        if not equipements:
                            single_eq = body.get("equipement", "")
                            if single_eq:
                                equipements = [single_eq]
                        equipement_str = ", ".join(equipements) if equipements else "— Non spécifié —"
                        client = body.get("client", "")
                        date_fin = body.get("date_fin", "")
                        rappel_avant_jours = body.get("rappel_avant_jours", 14) or 14
                        msg = (
                            f"📋 <b>Nouveau Contrat #{contrat_id}</b>\n\n"
                            f"👤 Client : <b>{client}</b>\n"
                            f"🏥 Équipement(s) : <b>{equipement_str}</b>\n"
                            f"🔄 Récurrence : <b>{recurrence}</b>\n"
                            f"📅 Jusqu'au : {date_fin}\n"
                            f"🔔 Rappel configuré : <b>{rappel_avant_jours} jours</b> avant chaque date\n\n"
                            f"✅ <b>{nb_plannings} maintenance(s) préventive(s)</b> planifiées automatiquement\n"
                            f"⚠️ <i>Techniciens non assignés — vous serez notifié {rappel_avant_jours} jours avant chaque date</i>"
                        )
                        _send_telegram_bot("telegram_sav", msg)
                        _send_telegram_bot("telegram_manager", msg)
                        logger.info(f"📨 Telegram notifications sent for contrat #{contrat_id}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to send Telegram for contrat #{contrat_id}: {e}")
                
                import threading
                telegram_thread = threading.Thread(target=send_telegram_async, daemon=True)
                telegram_thread.start()
        except Exception as e:
            logger.error(f"Erreur génération planning pour contrat #{contrat_id}: {e}")
    return {"ok": True, "contrat_id": contrat_id, "nb_plannings": nb_plannings}


@app.put("/api/contrats/{contrat_id}")
def update_contrat(contrat_id: int, body: dict, user: dict = Depends(_verify_token)):
    modifier_contrat(contrat_id, body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "contrat_id": contrat_id,
        "changes": body,
    }, ensure_ascii=False)
    log_audit(username, "UPDATE_CONTRAT", details, "contrats")
    
    return {"ok": True}


@app.delete("/api/contrats/{contrat_id}")
def delete_contrat(contrat_id: int, user: dict = Depends(_verify_token)):
    # Get contrat info before deleting
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT client FROM contrats WHERE id = ?",
                (contrat_id,)
            ).fetchone()
            client = dict(row)["client"] if row else "Unknown"
    except:
        client = "Unknown"
    
    supprimer_contrat(contrat_id)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "contrat_id": contrat_id,
        "client": client,
    }, ensure_ascii=False)
    log_audit(username, "DELETE_CONTRAT", details, "contrats")
    
    return {"ok": True}


# ==========================================
# CONFORMITÉ
# ==========================================

@app.get("/api/conformite")
def get_conformite(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    return _df_to_records(lire_conformite(client=client))


@app.post("/api/conformite")
def create_conformite(body: dict, user: dict = Depends(_verify_token)):
    ajouter_conformite(body)
    return {"ok": True}


@app.delete("/api/conformite/{conformite_id}")
def delete_conformite(conformite_id: int, user: dict = Depends(_verify_token)):
    supprimer_conformite(conformite_id)
    return {"ok": True}


# ==========================================
# PLANNING
# ==========================================

@app.get("/api/planning")
def get_planning(
    machine: Optional[str] = None,
    statut: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    df = lire_planning(machine=machine, statut=statut)
    
    # Si le user est un Technicien → filtrer automatiquement ses plannings
    if user.get("role") == "Technicien" and not df.empty:
        user_nom_complet = (user.get("nom") or "").strip()
        user_username = (user.get("sub") or "").strip()
        # Filter by name (primary) or username (secondary)
        if user_nom_complet and "technicien_assigne" in df.columns:
            df = df[df["technicien_assigne"].astype(str).apply(
                lambda t: _tech_name_or_username_matches(user_nom_complet, t) or _tech_name_or_username_matches(user_username, t)
            )]
    
    # Pour Lecteur : filtrer par les machines de son client
    client_filter = _get_client_filter(user)
    if client_filter and not df.empty:
        df_eq = lire_equipements()
        if not df_eq.empty and "Client" in df_eq.columns and "Nom" in df_eq.columns:
            machines_client = set(
                df_eq[df_eq["Client"].astype(str).str.lower() == client_filter.lower()]["Nom"].tolist()
            )
            if "machine" in df.columns:
                df = df[df["machine"].isin(machines_client)]
    return _df_to_records(df)


@app.post("/api/planning")
def create_planning(body: dict, user: dict = Depends(_verify_token)):
    # Check permission
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins"
        )
    
    ajouter_planning(body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({
        "machine": body.get("machine", ""),
        "type": body.get("type", ""),
        "date": body.get("date", ""),
    }, ensure_ascii=False)
    log_audit(username, "CREATE_PLANNING", details, "planning")
    
    return {"ok": True}


@app.post("/api/planning/sync")
def force_planning_sync(user: dict = Depends(_verify_token)):
    """Force la synchronisation planning -> interventions pour aujourd'hui."""
    created = sync_planning_to_interventions()
    return {"ok": True, "created": len(created), "interventions": created}


@app.post("/api/planning/pdf")
def generate_planning_pdf(body: dict = {}, user: dict = Depends(_verify_token)):
    """Generate a maintenance planning PDF using FPDF with proper header.
    Supports date range filtering. Uses landscape orientation for better column visibility."""
    from io import BytesIO
    from fastapi.responses import Response
    from datetime import datetime
    from fpdf import FPDF

    SAVIA_LOGO = "/app/logo-savia.png"

    try:
        rows = body.get("rows", [])
        logger.info(f"[PDF] Received {len(rows)} rows from frontend")
        filter_label = body.get("filter_label", "Tous les clients")
        company_name = body.get("company_name", "SAVIA")
        company_logo = body.get("company_logo", "")

        # Use landscape orientation (L) instead of portrait
        pdf = FPDF(orientation='L')
        pdf.set_auto_page_break(auto=True, margin=10)

        # Page 1: Header with logo
        pdf.add_page()
        # Use built-in Arial font instead of DejaVu
        pdf.set_font("Arial", size=10)

        # Left: SAVIA logo
        if os.path.exists(SAVIA_LOGO):
            pdf.image(SAVIA_LOGO, x=10, y=10, w=30)
        
        # Right: Company logo (uploaded in admin)
        if company_logo:
            try:
                # company_logo is base64 data URL: "data:image/png;base64,..."
                if company_logo.startswith('data:'):
                    # Extract base64 part
                    base64_data = company_logo.split(',')[1]
                    image_bytes = base64.b64decode(base64_data)
                    
                    # Create temporary file
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                        tmp.write(image_bytes)
                        tmp_path = tmp.name
                    
                    # Add company logo to top right (adjusted for landscape page width ~277mm)
                    # x=240 aligns it to right of landscape page, y=10, w=35 for width
                    pdf.image(tmp_path, x=240, y=10, w=35)
                    
                    # Clean up temp file
                    os.unlink(tmp_path)
            except Exception as e:
                logger.warning(f"Failed to add company logo: {e}")
        
        # Right: Company info (below logo, adjusted for landscape)
        pdf.set_xy(210, 50)
        pdf.set_font("Arial", 'B', size=12)
        pdf.cell(0, 5, company_name, ln=True, align='R')
        pdf.set_xy(210, 55)
        pdf.set_font("Arial", size=9)
        pdf.cell(0, 4, f"Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align='R')
        
        # Title
        pdf.set_xy(10, 50)
        pdf.set_font("Arial", 'B', size=16)
        pdf.cell(0, 10, "PLANNING MAINTENANCE", ln=True)
        
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 5, f"Filtre: {filter_label}", ln=True)
        pdf.cell(0, 3, f"Nombre d'interventions: {len(rows)}", ln=True)
        pdf.ln(5)

        # Table header - optimized for landscape width
        # Landscape page width is approximately 277mm, with 10mm margins = 257mm available
        pdf.set_font("Arial", 'B', size=9)
        col_widths = [30, 38, 28, 38, 38, 28, 78]  # Notes: 78mm
        headers = ["Date", "Machine", "Type", "Technicien", "Client", "Statut", "Notes"]
        
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 7, header, border=1, align='C')
        pdf.ln()

        # Table data - Using multi_cell for notes to support line wrapping
        pdf.set_font("Arial", size=8)
        
        for row in rows:
            # Extract data
            date_str = row.get("date_planifiee", "")[:10] if row.get("date_planifiee") else ""
            machine = str(row.get("machine", ""))[:25]
            type_maint = str(row.get("type_maintenance", ""))[:15]
            tech = str(row.get("technicien", ""))[:20]
            client = str(row.get("client", ""))[:20]
            statut = str(row.get("statut", ""))[:12]
            notes_full = str(row.get("notes", ""))
            
            # For notes with potential line breaks, we need multi-line support
            # Calculate how many lines the notes will need (approximately 11 chars per line at this width and font size)
            line_width_mm = 78  # col_widths[6]
            chars_per_line = 45  # approximate for Arial 8pt at 78mm
            
            # Split notes into lines
            notes_lines = []
            remaining = notes_full
            while remaining:
                if len(remaining) <= chars_per_line:
                    notes_lines.append(remaining)
                    break
                else:
                    split_pos = remaining.rfind(' ', 0, chars_per_line)
                    if split_pos == -1:
                        split_pos = chars_per_line
                    notes_lines.append(remaining[:split_pos])
                    remaining = remaining[split_pos:].lstrip()
            
            # Limit to max 3 lines to avoid oversized rows
            if len(notes_lines) > 3:
                notes_lines = notes_lines[:3]
                notes_lines[-1] = notes_lines[-1][:chars_per_line-3] + "..."
            
            # Ensure at least one line
            if not notes_lines:
                notes_lines = [""]
            
            # Row height depends on number of notes lines (5mm per line)
            num_lines = len(notes_lines)
            row_height = 5 * num_lines
            
            # Get current Y position
            current_y = pdf.get_y()
            # Page bottom is around 190mm with 10mm margin
            if current_y + row_height > 190:
                # Add new page and re-draw header
                pdf.add_page()
                pdf.set_font("Arial", 'B', size=9)
                for i, header in enumerate(headers):
                    pdf.cell(col_widths[i], 7, header, border=1, align='C')
                pdf.ln()
                pdf.set_font("Arial", size=8)
            
            # Draw row cells - use manual positioning for multi-line notes
            y_start = pdf.get_y()
            
            # Draw all columns except notes first
            pdf.set_xy(10, y_start)
            pdf.cell(col_widths[0], row_height, date_str, border=1, align='C')
            
            pdf.set_xy(10 + col_widths[0], y_start)
            pdf.cell(col_widths[1], row_height, machine, border=1, align='L')
            
            pdf.set_xy(10 + col_widths[0] + col_widths[1], y_start)
            pdf.cell(col_widths[2], row_height, type_maint, border=1, align='L')
            
            pdf.set_xy(10 + col_widths[0] + col_widths[1] + col_widths[2], y_start)
            pdf.cell(col_widths[3], row_height, tech, border=1, align='L')
            
            x_pos = 10 + col_widths[0] + col_widths[1] + col_widths[2] + col_widths[3]
            pdf.set_xy(x_pos, y_start)
            pdf.cell(col_widths[4], row_height, client, border=1, align='L')
            
            x_pos += col_widths[4]
            pdf.set_xy(x_pos, y_start)
            pdf.cell(col_widths[5], row_height, statut, border=1, align='C')
            
            # Draw notes cell with border and multi-line content
            x_pos += col_widths[5]
            pdf.set_xy(x_pos, y_start)
            pdf.rect(x_pos, y_start, col_widths[6], row_height, 'D')
            
            # Draw each line of notes
            for line_num, notes_line in enumerate(notes_lines):
                line_y = y_start + (line_num * 5) + 1
                pdf.set_xy(x_pos + 1, line_y)
                pdf.cell(col_widths[6] - 2, 4.5, notes_line, border=0, align='L')
            
            # Move to next row
            pdf.set_y(y_start + row_height)

        # Footer
        pdf.set_y(-15)
        pdf.set_font("Arial", size=8)
        pdf.cell(0, 5, f"Page {pdf.page_no()}", align='C')

        pdf_output = pdf.output(dest='S')
        # pdf.output(dest='S') returns bytearray in FPDF2
        if isinstance(pdf_output, bytearray):
            pdf_bytes = bytes(pdf_output)
        elif isinstance(pdf_output, str):
            pdf_bytes = pdf_output.encode('latin-1')
        else:
            pdf_bytes = pdf_output
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=planning.pdf"}
        )
    except Exception as e:
        logger.error(f"Error generating planning PDF: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating PDF: {str(e)}"
        )


@app.post("/api/planning/comparateur/pdf")
def export_comparateur_pdf(body: dict, user: dict = Depends(_verify_token)):
    """
    Generate PDF from comparateur data.
    Input: comparateur data from GET /api/planning/{id}/comparateur
    Output: PDF file
    """
    try:
        from fpdf import FPDF
        from datetime import datetime
        
        # Get comparateur data from body
        data = body
        
        # Create PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("DejaVu", size=12)
        
        # Title
        pdf.set_font("DejaVu", 'B', size=16)
        pdf.cell(0, 10, "RAPPORT COMPARATEUR PLANNING", ln=True, align='C')
        pdf.ln(5)
        
        # Timestamp
        pdf.set_font("DejaVu", size=9)
        pdf.cell(0, 8, f"Généré le: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True)
        pdf.ln(3)
        
        # Equipment info
        pdf.set_font("DejaVu", 'B', size=11)
        pdf.cell(0, 8, "INFORMATIONS ÉQUIPEMENT", ln=True)
        pdf.set_font("DejaVu", size=10)
        pdf.cell(0, 7, f"Machine: {data.get('machine', '')}", ln=True)
        pdf.cell(0, 7, f"Client: {data.get('client', '')}", ln=True)
        pdf.cell(0, 7, f"Type: {data.get('type_maintenance', '')}", ln=True)
        pdf.cell(0, 7, f"Description: {data.get('description', '')}", ln=True)
        pdf.ln(3)
        
        # Real planning
        pdf.set_font("DejaVu", 'B', size=11)
        pdf.cell(0, 8, "PLANNING RÉEL (Nouvelle date)", ln=True)
        pdf.set_font("DejaVu", size=10)
        real = data.get('real', {})
        pdf.cell(0, 7, f"Date: {real.get('date', '')}", ln=True)
        pdf.cell(0, 7, f"Technicien: {real.get('technicien', '')}", ln=True)
        pdf.cell(0, 7, f"Statut: {real.get('statut', '')}", ln=True)
        pdf.ln(3)
        
        # Ghost planning
        if data.get('has_ghost'):
            pdf.set_font("DejaVu", 'B', size=11)
            pdf.cell(0, 8, "PLANNING DÉCALÉ (Date originale)", ln=True)
            pdf.set_font("DejaVu", size=10)
            ghost = data.get('ghost', {})
            pdf.cell(0, 7, f"Date: {ghost.get('date', '')}", ln=True)
            pdf.cell(0, 7, f"Technicien: {ghost.get('technicien', '')}", ln=True)
            pdf.cell(0, 7, f"Statut: {ghost.get('statut', '')}", ln=True)
            pdf.ln(3)
        
        # Differences
        pdf.set_font("DejaVu", 'B', size=11)
        pdf.cell(0, 8, "CHANGEMENTS", ln=True)
        pdf.set_font("DejaVu", size=10)
        diff = data.get('differences', {})
        if diff.get('date_changed'):
            old_date = diff.get('old_date', '')
            new_date = diff.get('new_date', '')
            pdf.cell(0, 7, f"Date modifiée: {old_date} → {new_date}", ln=True)
        if diff.get('technicien_changed'):
            old_tech = diff.get('old_technicien', 'Non assigné')
            new_tech = diff.get('new_technicien', 'Non assigné')
            pdf.cell(0, 7, f"Technicien modifié: {old_tech} → {new_tech}", ln=True)
        pdf.ln(3)
        
        # Reasons
        reasons = data.get('reasons', [])
        if reasons:
            pdf.set_font("DejaVu", 'B', size=11)
            pdf.cell(0, 8, "RAISONS DU DÉCALAGE", ln=True)
            pdf.set_font("DejaVu", size=10)
            for idx, reason in enumerate(reasons, 1):
                # Use multi_cell for text wrapping
                pdf.multi_cell(0, 5, f"{idx}. {reason}")
            pdf.ln(2)
        
        # Footer
        pdf.set_font("DejaVu", size=8)
        pdf.ln(5)
        pdf.cell(0, 5, "---", ln=True)
        pdf.cell(0, 5, "Rapport généré automatiquement par SAVIA", align='C')
        
        # Return PDF as blob
        from io import BytesIO
        pdf_output = pdf.output(dest='S')
        # pdf.output(dest='S') returns bytearray in FPDF2
        if isinstance(pdf_output, bytearray):
            pdf_bytes = bytes(pdf_output)
        elif isinstance(pdf_output, str):
            pdf_bytes = pdf_output.encode('latin-1')
        else:
            pdf_bytes = pdf_output
        
        from fastapi.responses import StreamingResponse
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type='application/pdf',
            headers={'Content-Disposition': 'attachment; filename=comparateur.pdf'}
        )
    except Exception as e:
        logger.error(f"Error generating comparateur PDF: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating PDF: {str(e)}"
        )


@app.get("/api/planning/{planning_id}/comparateur")
def get_planning_comparateur(planning_id: int, user: dict = Depends(_verify_token)):
    """
    Get comparison between real planning and ghost (décalé) entry.
    Returns data for generating comparateur export (planning réel vs planning décalé).
    Accepts either the real planning ID or the ghost planning ID.
    """
    try:
        with get_db() as conn:
            # Check if the provided ID is a ghost entry
            test_entry = conn.execute(
                "SELECT * FROM planning_maintenance WHERE id = ?",
                (planning_id,)
            ).fetchone()
            
            if not test_entry:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Planning entry not found"
                )
            
            # If the provided ID is a ghost entry, use its original_planning_id as the real ID
            test_dict = dict(test_entry)
            if test_dict.get("is_ghost"):
                real_planning_id = test_dict.get("original_planning_id")
                if not real_planning_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Ghost entry has no associated original planning"
                    )
            else:
                real_planning_id = planning_id
            
            # Get the real planning entry
            real = conn.execute(
                "SELECT * FROM planning_maintenance WHERE id = ? AND is_ghost = false",
                (real_planning_id,)
            ).fetchone()
            
            if not real:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Real planning entry not found"
                )
            
            # Get the ghost entry associated with this planning
            ghost = conn.execute(
                "SELECT * FROM planning_maintenance WHERE original_planning_id = ? AND is_ghost = true",
                (real_planning_id,)
            ).fetchone()
            
            # Extract reason from notes (format: "[Raison décalage] text")
            reason_lines = []
            if ghost:
                ghost_notes = ghost.get("notes", "") or ""
                # Extract all "[Raison décalage]" lines
                for line in ghost_notes.split("|"):
                    line = line.strip()
                    if line.startswith("[Raison décalage]"):
                        reason = line.replace("[Raison décalage]", "").strip()
                        reason_lines.append(reason)
            
            # Build comparison data
            real_dict = dict(real) if real else {}
            ghost_dict = dict(ghost) if ghost else {}
            
            comparison = {
                "planning_id": real_planning_id,
                "machine": real_dict.get("machine", ""),
                "client": real_dict.get("client", ""),
                "type_maintenance": real_dict.get("type_maintenance", ""),
                "description": real_dict.get("description", ""),
                
                # Real planning (new date after reschedule)
                "real": {
                    "date": real_dict.get("date_prevue", ""),
                    "technicien": real_dict.get("technicien_assigne", ""),
                    "statut": real_dict.get("statut", ""),
                },
                
                # Ghost planning (original date - décalé)
                "ghost": {
                    "date": ghost_dict.get("date_prevue", "") if ghost else None,
                    "technicien": ghost_dict.get("technicien_assigne", "") if ghost else None,
                    "statut": ghost_dict.get("statut", "") if ghost else None,
                } if ghost else None,
                
                # Differences
                "differences": {
                    "date_changed": real_dict.get("date_prevue") != ghost_dict.get("date_prevue") if ghost else False,
                    "technicien_changed": real_dict.get("technicien_assigne") != ghost_dict.get("technicien_assigne") if ghost else False,
                    "old_date": ghost_dict.get("date_prevue") if ghost else None,
                    "new_date": real_dict.get("date_prevue"),
                    "old_technicien": ghost_dict.get("technicien_assigne") if ghost else None,
                    "new_technicien": real_dict.get("technicien_assigne"),
                },
                
                # Reschedule reasons (accumulated)
                "reasons": reason_lines if reason_lines else [],
                
                # Meta
                "has_ghost": ghost is not None,
            }
            
            return comparison
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting planning comparateur for {planning_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching comparateur data: {str(e)}"
        )


@app.get("/api/planning/comparateur-periode")
def get_planning_comparateur_periode(
    date_debut: str = Query(..., description="Start date (YYYY-MM-DD)"),
    date_fin: str = Query(..., description="End date (YYYY-MM-DD)"),
    user: dict = Depends(_verify_token)
):
    """
    Get all reschedules (comparisons) within a date range.
    Returns all ghost entries (décalés) between date_debut and date_fin.
    """
    try:
        # Validate dates
        try:
            from datetime import datetime
            d_debut = datetime.strptime(date_debut, "%Y-%m-%d")
            d_fin = datetime.strptime(date_fin, "%Y-%m-%d")
            if d_debut > d_fin:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="date_debut must be before date_fin"
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD"
            )
        
        with get_db() as conn:
            # Get all ghost entries (décalés) with their original entries
            # Filter by ghost entry's date_prevue (the rescheduled date)
            ghosts = conn.execute(
                """SELECT * FROM planning_maintenance 
                   WHERE is_ghost = true 
                   AND date_prevue BETWEEN ? AND ?
                   ORDER BY date_prevue ASC""",
                (date_debut, date_fin)
            ).fetchall()
            
            comparisons = []
            for ghost_row in ghosts:
                ghost_dict = dict(ghost_row)
                original_planning_id = ghost_dict.get("original_planning_id")
                
                if not original_planning_id:
                    continue  # Skip if no original planning
                
                # Get the real planning entry
                real = conn.execute(
                    "SELECT * FROM planning_maintenance WHERE id = ? AND is_ghost = false",
                    (original_planning_id,)
                ).fetchone()
                
                if not real:
                    continue
                
                real_dict = dict(real)
                
                # Extract reason from notes of the REAL entry (not the ghost)
                # The reschedule reason is stored in the real entry's notes
                reason_lines = []
                real_notes = real_dict.get("notes", "") or ""
                for line in real_notes.split("|"):
                    line = line.strip()
                    if line.startswith("[Raison décalage]"):
                        reason = line.replace("[Raison décalage]", "").strip()
                        reason_lines.append(reason)
                
                # For clarity: ghost = original date, real = rescheduled date
                # Calculate days difference (rescheduled - original)
                try:
                    from datetime import datetime, date
                    ghost_date = ghost_dict.get("date_prevue")
                    real_date = real_dict.get("date_prevue")
                    
                    # Convert to date objects if they're strings
                    if isinstance(ghost_date, str):
                        ghost_date = datetime.strptime(ghost_date, "%Y-%m-%d").date()
                    if isinstance(real_date, str):
                        real_date = datetime.strptime(real_date, "%Y-%m-%d").date()
                    
                    if ghost_date and real_date:
                        days_diff = (real_date - ghost_date).days
                    else:
                        days_diff = 0
                except Exception as e:
                    logger.error(f"Error calculating days diff: {e}, ghost_date={ghost_dict.get('date_prevue')}, real_date={real_dict.get('date_prevue')}")
                    days_diff = 0
                
                comparison = {
                    "planning_id": original_planning_id,
                    "ghost_id": ghost_dict.get("id"),
                    "machine": real_dict.get("machine", ""),
                    "client": real_dict.get("client", ""),
                    "type_maintenance": real_dict.get("type_maintenance", ""),
                    "old_date": ghost_dict.get("date_prevue"),  # Original date (ghost entry)
                    "new_date": real_dict.get("date_prevue"),   # Rescheduled date (real entry)
                    "days_difference": days_diff,  # This is now (real - ghost) = newer - older
                    "old_technicien": ghost_dict.get("technicien_assigne", ""),
                    "new_technicien": real_dict.get("technicien_assigne", ""),
                    "statut": real_dict.get("statut", ""),
                    "reasons": reason_lines if reason_lines else [],
                }
                comparisons.append(comparison)
            
            return {
                "total": len(comparisons),
                "period": {"debut": date_debut, "fin": date_fin},
                "comparisons": comparisons
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting planning comparateur-periode: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching comparateur data: {str(e)}"
        )


@app.put("/api/planning/{planning_id}")
def update_planning_status(planning_id: int, body: dict, user: dict = Depends(_verify_token)):
    update_planning_statut(planning_id, body.get("statut", ""), body.get("date_realisee"))
    return {"ok": True}


@app.put("/api/planning/{planning_id}/reschedule")
def reschedule_planning(planning_id: int, body: dict, user: dict = Depends(_verify_token)):
    """Reschedule an intervention (change date and/or technicians).
    Only Admin and Manager can perform this action.
    Creates a greyed-out "Décalé" entry at the old date for audit trail.
    """
    # Check authorization (Admin or Manager only)
    if user.get("role") not in ["Admin", "Manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin and Manager can reschedule interventions"
        )
    
    ph = "%s"  # PostgreSQL placeholder
    
    new_date = body.get("date_planifiee")
    new_technicians = body.get("technicien_assigne")
    reason = body.get("reason", "").strip()  # ← Add reason support
    
    if not new_date and new_technicians is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least date_planifiee or technicien_assigne must be provided"
        )
    
    try:
        with get_db() as conn:
            # Get current planning item
            current = conn.execute(
                f"SELECT * FROM planning_maintenance WHERE id = {ph}",
                (planning_id,)
            ).fetchone()
            
            if not current:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Planning item not found"
                )
            
            old_date = current.get("date_prevue")
            
            # Update the main planning entry
            update_data = {}
            if new_date:
                update_data["date_prevue"] = new_date
            if new_technicians is not None:
                update_data["technicien_assigne"] = new_technicians
            
            # ← Add reason to notes if provided
            if reason:
                old_notes = current.get("notes", "")
                new_notes = f"[Raison décalage] {reason}"
                if old_notes:
                    new_notes = f"{old_notes} | {new_notes}"
                update_data["notes"] = new_notes
            
            if update_data:
                set_clause = ", ".join([f"{k} = {ph}" for k in update_data.keys()])
                values = list(update_data.values()) + [planning_id]
                conn.execute(
                    f"UPDATE planning_maintenance SET {set_clause} WHERE id = {ph}",
                    values
                )
                conn.commit()
                logger.info(f"Planning {planning_id} updated: {update_data}")
            
            # Create a greyed-out "Décalé" entry at the old date AFTER updating (separate transaction)
            # BUT: Only if the DATE ACTUALLY CHANGED (not if only technicien changed)
            # AND only if this is NOT already a ghost entry
            is_current_ghost = current.get("is_ghost", False)
            
            # Check if date actually changed (compare as strings for consistency)
            date_has_changed = new_date and str(new_date) != str(old_date)
            
            if date_has_changed and not is_current_ghost:
                try:
                    old_machine = current.get("machine", "")
                    old_client = current.get("client", "")
                    old_description = current.get("description", "")
                    old_notes = current.get("notes", "")
                    old_type = current.get("type_maintenance", "Préventive")
                    
                    # Check if a ghost ALREADY EXISTS for this ORIGINAL planning
                    # Using original_planning_id to link ghost to its source intervention
                    # This prevents duplicate ghosts when same intervention is rescheduled multiple times
                    existing_ghost = conn.execute(
                        f"SELECT id FROM planning_maintenance WHERE original_planning_id = {ph} AND is_ghost = true",
                        (planning_id,)
                    ).fetchone()
                    
                    if not existing_ghost:
                        # Create a ghost from the ORIGINAL intervention at the old date
                        # Set original_planning_id to track that this ghost belongs to planning_id
                        insert_sql = f"""INSERT INTO planning_maintenance 
                               (machine, client, date_prevue, technicien_assigne, type_maintenance, 
                                recurrence, statut, description, notes, is_ghost, original_planning_id)
                               VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})"""
                        conn.execute(
                            insert_sql,
                            (old_machine, old_client, old_date, "", old_type, 
                             "Aucune", "Décalé", f"[DÉCALÉ] {old_description}", old_notes, True, planning_id)
                        )
                        conn.commit()
                        logger.info(f"✅ Ghost entry created for planning {planning_id}: {old_machine} on {old_date}")
                    else:
                        # Ghost already exists - update its notes to accumulate all reschedule reasons
                        ghost_id = existing_ghost.get("id")
                        ghost_current = conn.execute(
                            f"SELECT notes FROM planning_maintenance WHERE id = {ph}",
                            (ghost_id,)
                        ).fetchone()
                        ghost_notes = ghost_current.get("notes", "") if ghost_current else ""
                        
                        # Append reason if provided and not already there
                        if reason:
                            new_reason_line = f"[Raison décalage] {reason}"
                            if new_reason_line not in ghost_notes:
                                if ghost_notes:
                                    updated_notes = f"{ghost_notes} | {new_reason_line}"
                                else:
                                    updated_notes = new_reason_line
                                conn.execute(
                                    f"UPDATE planning_maintenance SET notes = {ph} WHERE id = {ph}",
                                    (updated_notes, ghost_id)
                                )
                                conn.commit()
                                logger.info(f"Ghost {ghost_id} notes updated with reschedule reason")
                        logger.info(f"Ghost already exists for planning {planning_id}, notes accumulated")
                except Exception as e:
                    logger.warning(f"Could not create ghost entry for planning {planning_id}: {e}")
                    # Don't fail if ghost entry creation fails - main update already succeeded
            
            # Log audit
            log_audit(
                user.get("sub", "unknown"),
                "RESCHEDULE_PLANNING",
                f"Planning {planning_id}: {update_data}"
            )
            
            # Send Telegram notification to assigned technicians
            if new_technicians:
                try:
                    machine = current.get("machine", "?")
                    client = current.get("client", "")
                    tech_list = [t.strip() for t in new_technicians.split(",") if t.strip()]
                    
                    msg = (
                        f"🔧 <b>Nouvelle Intervention Assignée</b>\n"
                        f"<i>{len(tech_list)} technicien(s) assigné(s) :</i>\n\n"
                    )
                    
                    for tech in tech_list:
                        msg += f"  • <b>{tech}</b>\n"
                    
                    msg += (
                        f"\n<b>Détails :</b>\n"
                        f"  📦 Équipement : {machine}\n"
                    )
                    if client:
                        msg += f"  🏢 Client : {client}\n"
                    if new_date:
                        msg += f"  📅 Date : {new_date}\n"
                    if reason:
                        msg += f"  💬 Raison : {reason}\n"
                    
                    msg += f"\n📱 Consultez le PWA pour plus de détails."
                    
                    # Send to general telegram bot (technicien will receive it)
                    _send_telegram_bot("telegram", msg)
                    logger.info(f"Telegram notification sent to {len(tech_list)} technician(s) for planning {planning_id}")
                except Exception as e:
                    logger.warning(f"Failed to send Telegram notification for planning {planning_id}: {e}")
            
            # Auto-sync planning to interventions (create intervention if date is today)
            try:
                sync_planning_to_interventions()
            except Exception as e:
                logger.warning(f"Planning sync after reschedule failed: {e}")
            
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rescheduling planning {planning_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rescheduling intervention: {str(e)}"
        )

@app.delete("/api/planning/{planning_id}")
def delete_planning(planning_id: int, user: dict = Depends(_verify_token)):
    supprimer_planning(planning_id)
    return {"ok": True}


# ==========================================
# PLANNING SYNC + FACTURATION
# ==========================================

@app.post("/api/planning/sync")
def force_planning_sync(user: dict = Depends(_verify_token)):
    """Force la synchronisation planning -> interventions pour aujourd'hui."""
    created = sync_planning_to_interventions()
    return {"ok": True, "created": len(created), "interventions": created}


@app.post("/api/interventions/{intervention_id}/factured")

def mark_intervention_factured(intervention_id: int, user: dict = Depends(_verify_token)):
    """Marque une intervention comme facturee (arrete les rappels)."""
    with get_db() as conn:
        conn.execute(
            "UPDATE interventions SET facture_envoyee = TRUE WHERE id = ?",
            (intervention_id,)
        )
    return {"ok": True}



# ==========================================
# KNOWLEDGE BASE
# ==========================================


@app.get("/api/knowledge")
def get_knowledge(user: dict = Depends(_verify_token)):
    """Return error codes + solutions merged."""
    hex_db, sol_db = lire_base()
    results = []
    for code, info in hex_db.items():
        sol = sol_db.get(code, {})
        results.append({
            "code": code,
            "message": info.get("Msg", ""),
            "level": info.get("Level", ""),
            "type": info.get("Type", ""),
            "cause": sol.get("Cause", ""),
            "solution": sol.get("Solution", ""),
            "priorite": sol.get("Priorité", ""),
        })
    return results


def _parse_text_to_rows(text: str) -> list:
    """Parse unstructured text (from PDF/Word) into error code rows using AI or regex."""
    import re
    rows = []

    # Try AI extraction first
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
        if AI_AVAILABLE and len(text) > 50:
            prompt = f"""Extrais les codes d'erreur de ce texte technique. 
Pour chaque code trouvé, donne: code, message, type (Hardware/Software/Network), cause, solution, priorite (HAUTE/MOYENNE/BASSE).
Texte (extrait): {text[:4000]}

Réponds en JSON: [{{"code":"ERR001","message":"...","type":"Hardware","cause":"...","solution":"...","priorite":"MOYENNE"}}]"""
            raw = _call_ia(prompt, timeout=30, is_json=True)
            if raw:
                result = clean_json_response(raw)
                if isinstance(result, list) and len(result) > 0:
                    return result
    except Exception:
        pass

    # Fallback: regex-based extraction
    # Common patterns: "ERR-001", "E001", "0x1234", "ERROR 001"
    patterns = [
        r'((?:ERR|ERROR|E|WARN|W|FAULT|F|CODE)[_\-\s]?\d{2,5})',
        r'(0x[0-9A-Fa-f]{4,8})',
        r'((?:H|S|N)\d{4})',
    ]
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            code = match.group(1).strip()
            # Get surrounding context (100 chars)
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 200)
            context = text[start:end].replace('\n', ' ').strip()
            if code not in [r.get('code') for r in rows]:
                rows.append({
                    "code": code,
                    "message": context[:120],
                    "type": "Hardware",
                    "cause": "",
                    "solution": "",
                    "priorite": "MOYENNE",
                })

    if not rows:
        # If no codes found, store the document text as a single entry
        lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 10]
        for i, line in enumerate(lines[:50]):
            rows.append({
                "code": f"DOC-{i+1:03d}",
                "message": line[:200],
                "type": "Documentation",
                "cause": "",
                "solution": "",
                "priorite": "BASSE",
            })

    return rows


@app.post("/api/knowledge/import")
async def import_knowledge(file: UploadFile = File(...), user: dict = Depends(_verify_token)):
    """Import error codes from an uploaded Excel/CSV file."""
    import io
    
    def sanitize_text(text: str) -> str:
        """Nettoie le texte en fixant les problèmes de mojibake et caractères corrompus."""
        if not text:
            return text
        
        # ÉTAPE 1: Détecter et réparer la mojibake UTF-8 mal décodée
        # Pattern: caractères UTF-8 multi-bytes mal interprétés comme latin-1
        # Ex: "â€¯" (U+00E2 U+0080 U+00AF) = corruption de U+203F (overline)
        try:
            # Essayer de ré-encoder en latin-1 puis décoder en UTF-8
            # Cela répare souvent les problèmes de mojibake
            text = text.encode('latin-1', errors='ignore').decode('utf-8', errors='replace')
        except Exception:
            pass
        
        # ÉTAPE 2: Remplacer les caractères de typographie spéciaux par ASCII
        char_map = {
            ''': "'",           # apostrophe courbe
            ''': "'",           # autre apostrophe
            '"': '"',           # guillemet ouvrant courbe
            '"': '"',           # guillemet fermant courbe
            '–': '-',           # tiret court
            '—': '--',          # tiret long
            '«': '"',           # guillemet français
            '»': '"',           # guillemet français
            '‹': '<',           # chevron ouvrant
            '›': '>',           # chevron fermant
            '\u00A0': ' ',      # espace insécable
            '\u2000': ' ',      # en quad
            '\u2001': ' ',      # em quad
            '\u2002': ' ',      # en space
            '\u2003': ' ',      # em space
            '\u2004': ' ',      # three-per-em space
            '\u2005': ' ',      # four-per-em space
            '\u2006': ' ',      # six-per-em space
            '\u2007': ' ',      # figure space
            '\u2008': ' ',      # punctuation space
            '\u2009': ' ',      # thin space
            '\u200A': ' ',      # hair space
            '\u200B': '',       # zero-width space
            '\u200C': '',       # zero-width non-joiner
            '\u200D': '',       # zero-width joiner
            '\u3000': ' ',      # ideographic space
            '\ufeff': '',       # BOM
        }
        
        for old_char, new_char in char_map.items():
            text = text.replace(old_char, new_char)
        
        # ÉTAPE 3: Supprimer les caractères de contrôle sauf newline et tab
        text = ''.join(c if ord(c) >= 32 or c in '\n\t\r' else '' for c in text)
        
        # ÉTAPE 4: Convertir en NFD (décomposé) puis en NFC (composé) pour normaliser
        import unicodedata
        text = unicodedata.normalize('NFC', text)
        
        # ÉTAPE 5: Nettoyer les espaces multiples
        text = ' '.join(text.split())
        
        return text
    
    filename = file.filename or ""
    content = await file.read()

    try:
        if filename.endswith(".csv"):
            import csv
            # Essayer différents encodages
            text = None
            for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
                try:
                    text = content.decode(encoding)
                    break
                except (UnicodeDecodeError, AttributeError):
                    continue
            
            if text is None:
                text = content.decode('utf-8', errors='replace')
            
            text = sanitize_text(text)
            reader = csv.DictReader(io.StringIO(text))
            rows = list(reader)
        
        elif filename.endswith((".xlsx", ".xls")):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
            ws = wb.active
            headers = [sanitize_text(str(c.value or "").strip()) for c in next(ws.iter_rows(min_row=1, max_row=1))]
            rows = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                row_dict = {}
                for i, v in enumerate(row):
                    if i < len(headers):
                        val = str(v) if v else ""
                        row_dict[headers[i]] = sanitize_text(val)
                rows.append(row_dict)
        
        elif filename.endswith(".pdf"):
            try:
                import fitz
                doc = fitz.open(stream=content, filetype="pdf")
                full_text = "\n".join(page.get_text() for page in doc)
            except Exception:
                full_text = content.decode("utf-8", errors="replace")
            full_text = sanitize_text(full_text)
            rows = _parse_text_to_rows(full_text)
        
        elif filename.endswith((".docx", ".doc")):
            try:
                import docx
                doc = docx.Document(io.BytesIO(content))
                full_text = "\n".join(sanitize_text(p.text) for p in doc.paragraphs if p.text.strip())
                for table in doc.tables:
                    for row in table.rows:
                        full_text += "\n" + " | ".join(sanitize_text(cell.text) for cell in row.cells)
            except Exception:
                full_text = content.decode("utf-8", errors="replace")
            full_text = sanitize_text(full_text)
            rows = _parse_text_to_rows(full_text)
        
        else:
            raise HTTPException(status_code=400, detail="Format non supporté. Utilisez CSV, XLSX, PDF ou DOCX.")

        # Auto-detect column mapping
        col_map = {}
        for h in (rows[0].keys() if rows else []):
            hl = h.lower().strip()
            if "code" in hl: col_map["code"] = h
            elif "message" in hl or "msg" in hl: col_map["message"] = h
            elif "type" in hl: col_map["type"] = h
            elif "cause" in hl: col_map["cause"] = h
            elif "solution" in hl: col_map["solution"] = h
            elif "priorit" in hl: col_map["priorite"] = h

        if "code" not in col_map:
            raise HTTPException(status_code=400, detail="Colonne 'Code' non trouvée dans le fichier.")

        imported = 0
        with get_db() as conn:
            for row in rows:
                code = sanitize_text(row.get(col_map.get("code", ""), "").strip())
                if not code:
                    continue
                msg = sanitize_text(row.get(col_map.get("message", ""), ""))
                typ = sanitize_text(row.get(col_map.get("type", ""), "Hardware"))
                cause = sanitize_text(row.get(col_map.get("cause", ""), ""))
                solution = sanitize_text(row.get(col_map.get("solution", ""), ""))
                priorite = sanitize_text(row.get(col_map.get("priorite", ""), "MOYENNE"))

                # Insert or update codes_erreurs
                conn.execute(
                    "INSERT INTO codes_erreurs (code, message, type) VALUES (?, ?, ?) "
                    "ON CONFLICT (code) DO UPDATE SET message=EXCLUDED.message, type=EXCLUDED.type",
                    (code, msg, typ)
                )
                # Insert or update solutions
                conn.execute(
                    "INSERT INTO solutions (code, cause, solution, priorite) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (code) DO UPDATE SET cause=EXCLUDED.cause, solution=EXCLUDED.solution, priorite=EXCLUDED.priorite",
                    (code, cause, solution, priorite)
                )
                imported += 1

        return {"ok": True, "imported": imported, "message": f"{imported} codes importés avec succès."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'import: {str(e)}")


@app.delete("/api/knowledge/{code}")
def delete_knowledge_code(code: str, user: dict = Depends(_verify_token)):
    """Supprimer un code d'erreur spécifique et ses solutions."""
    try:
        with get_db() as conn:
            # Supprimer la solution d'abord (FK contraint) - utiliser mot_cle
            conn.execute("DELETE FROM solutions WHERE mot_cle = ?", (code,))
            # Puis le code d'erreur - utiliser code
            conn.execute("DELETE FROM codes_erreurs WHERE code = ?", (code,))
        return {"ok": True, "message": f"Code {code} supprimé avec succès."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de suppression: {str(e)}")


# ==========================================
# TECHNICIENS
# ==========================================

@app.get("/api/techniciens")
def get_techniciens(user: dict = Depends(_verify_token)):
    return _df_to_records(lire_techniciens())


@app.post("/api/techniciens")
def create_technicien(body: dict, user: dict = Depends(_verify_token)):
    # Validate username uniqueness if provided
    username = body.get("username", "").strip()
    if username:
        with get_db() as conn:
            # Check in utilisateurs
            existing_user = conn.execute(
                "SELECT id FROM utilisateurs WHERE username = ?",
                (username,)
            ).fetchone()
            
            if existing_user:
                raise HTTPException(
                    status_code=409,
                    detail=f"Ce nom d'utilisateur '{username}' est déjà utilisé dans le système utilisateurs. Veuillez choisir un autre."
                )
            
            # Check in techniciens
            existing_tech = conn.execute(
                "SELECT id FROM techniciens WHERE username = ?",
                (username,)
            ).fetchone()
            
            if existing_tech:
                raise HTTPException(
                    status_code=409,
                    detail=f"Ce nom d'utilisateur '{username}' est déjà utilisé par un autre technicien. Veuillez choisir un autre."
                )
    
    ajouter_technicien(body)
    return {"ok": True}


@app.put("/api/techniciens/{tech_id}")
def modifier_techniciens_route(tech_id: int, body: dict, user: dict = Depends(_verify_token)):
    update_technicien(tech_id, body)
    return {"ok": True}


@app.delete("/api/techniciens/{tech_id}")
def delete_technicien(tech_id: int, user: dict = Depends(_verify_token)):
    supprimer_technicien(tech_id)
    return {"ok": True}


# ==========================================
# LOGS UPLOAD (Supervision) — S3/MinIO + PostgreSQL
# ==========================================

@app.post("/api/logs/upload")
def upload_log(body: dict, user: dict = Depends(_verify_token)):
    """Upload un fichier log : contenu vers S3/MinIO, métadonnées vers PostgreSQL."""
    import hashlib
    equipement = body.get("equipement", "")
    filename = body.get("filename", "unknown.log")
    content = body.get("content", "")
    nb_errors = body.get("nb_errors", 0)
    nb_critiques = body.get("nb_critiques", 0)
    import json as _json_import
    parsed_errors_raw = body.get("parsed_errors", None)
    parsed_errors_str = _json_import.dumps(parsed_errors_raw) if parsed_errors_raw is not None else None

    if not equipement or not content:
        raise HTTPException(status_code=400, detail="Équipement et contenu requis")

    content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
    username = user.get("sub", "system") if user else "system"

    try:
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id FROM logs_uploaded WHERE content_hash = ? AND equipement = ?",
                (content_hash, equipement)
            ).fetchone()
            if existing:
                eid = existing.get("id") if isinstance(existing, dict) else existing[0]
                # Update parsed_errors on duplicate if not already stored
                if parsed_errors_str:
                    conn.execute(
                        "UPDATE logs_uploaded SET parsed_errors = ? WHERE id = ? AND (parsed_errors IS NULL OR parsed_errors = '')",
                        (parsed_errors_str, eid)
                    )
                return {"ok": True, "message": "Ce log a déjà été enregistré", "id": eid, "duplicate": True}

            # Upload contenu vers S3/MinIO
            s3_key = ""
            size_bytes = len(content.encode('utf-8'))
            try:
                from s3_storage import upload_file as s3_upload
                s3_result = s3_upload(content, filename, equipement, {
                    "nb_errors": str(nb_errors), "uploaded_by": username,
                })
                if s3_result:
                    s3_key = s3_result["s3_key"]
                    size_bytes = s3_result["size_bytes"]
            except Exception as s3_err:
                logger.warning(f"S3 upload failed (non-blocking): {s3_err}")

            # Métadonnées en PostgreSQL
            cursor = conn.execute(
                """INSERT INTO logs_uploaded (equipement, filename, s3_key, content_hash, size_bytes, nb_errors, nb_critiques, uploaded_by, parsed_errors)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (equipement, filename, s3_key, content_hash, size_bytes, nb_errors, nb_critiques, username, parsed_errors_str)
            )
            new_row = cursor.fetchone()
            new_id = (new_row["id"] if isinstance(new_row, dict) else new_row[0]) if new_row else None
            conn.execute(
                "INSERT INTO audit_log (username, action, details) VALUES (?, ?, ?)",
                (username, "Upload Log", f"Log '{filename}' S3:{s3_key or 'N/A'} ({nb_errors} erreurs)")
            )
            return {"ok": True, "id": new_id, "s3_key": s3_key,
                    "message": f"Log enregistré — {size_bytes} octets, {nb_errors} erreur(s), S3: {'ok' if s3_key else 'fallback'}"}
    except Exception as e:
        logger.error(f"Log upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs")
def list_logs(equipement: str = None, user: dict = Depends(_verify_token)):
    """Liste les logs uploadés (métadonnées depuis PostgreSQL)."""
    try:
        with get_db() as conn:
            if equipement:
                rows = conn.execute(
                    "SELECT id, equipement, filename, s3_key, size_bytes, nb_errors, nb_critiques, uploaded_by, uploaded_at FROM logs_uploaded WHERE equipement = ? ORDER BY uploaded_at DESC",
                    (equipement,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, equipement, filename, s3_key, size_bytes, nb_errors, nb_critiques, uploaded_by, uploaded_at FROM logs_uploaded ORDER BY uploaded_at DESC"
                ).fetchall()
            def _row(r):
                if isinstance(r, dict):
                    return {"id": r.get("id"), "equipement": r.get("equipement"), "filename": r.get("filename"), "s3_key": r.get("s3_key"), "size_bytes": r.get("size_bytes"), "nb_errors": r.get("nb_errors"), "nb_critiques": r.get("nb_critiques"), "uploaded_by": r.get("uploaded_by"), "uploaded_at": str(r.get("uploaded_at", ""))}
                return {"id": r[0], "equipement": r[1], "filename": r[2], "s3_key": r[3], "size_bytes": r[4], "nb_errors": r[5], "nb_critiques": r[6], "uploaded_by": r[7], "uploaded_at": str(r[8])}
            return [_row(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/logs/{log_id}")
def get_log(log_id: int, user: dict = Depends(_verify_token)):
    """Récupère le contenu d'un log depuis S3/MinIO."""
    try:
        with get_db() as conn:
            row = conn.execute("SELECT s3_key, equipement, filename, parsed_errors FROM logs_uploaded WHERE id = ?", (log_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Log non trouvé")
            # Support both dict (PG) and tuple (SQLite) rows
            if isinstance(row, dict):
                s3_key = row.get("s3_key", "")
                equipement = row.get("equipement", "")
                filename = row.get("filename", "")
            else:
                s3_key, equipement, filename = row[0], row[1], row[2]
            if not s3_key:
                import json as _json_nk
                _pe_nk = None
                if (isinstance(row, dict) and row.get("parsed_errors")) or (not isinstance(row, dict) and len(row) > 3 and row[3]):
                    _pe_nk_raw = row.get("parsed_errors") if isinstance(row, dict) else row[3]
                    try: _pe_nk = _json_nk.loads(_pe_nk_raw)
                    except: _pe_nk = None
                return {"id": log_id, "equipement": equipement, "filename": filename, "content": "", "parsed_errors": _pe_nk}
            try:
                from s3_storage import download_file
                content = download_file(s3_key)
                import json as _json_ret
                _pe = None
                if (isinstance(row, dict) and row.get("parsed_errors")) or (not isinstance(row, dict) and len(row) > 3 and row[3]):
                    _pe_raw = row.get("parsed_errors") if isinstance(row, dict) else row[3]
                    try: _pe = _json_ret.loads(_pe_raw)
                    except: _pe = None
                return {"id": log_id, "equipement": equipement, "filename": filename, "content": content or "", "s3_key": s3_key, "parsed_errors": _pe}
            except Exception:
                return {"id": log_id, "equipement": equipement, "filename": filename, "content": ""}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# AI INTEGRATION
# ==========================================

@app.post("/api/ai/analyze-diagnostic")
def analyze_diagnostic(body: dict, user: dict = Depends(_verify_token)):
    """Calls Gemini to diagnose a machine error code and log contexts."""
    try:
        from ai_engine import get_ai_suggestion, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible. (Vérifiez GOOGLE_API_KEY).")

    machine = body.get("machine", "Équipement inconnu")
    code_erreur = body.get("code_erreur", "")
    message_erreur = body.get("message_erreur", "")
    log_context = body.get("log_context", "")
    equipment_type = body.get("equipment_type", "")

    try:
        result = get_ai_suggestion(code_erreur, message_erreur, machine, log_context=log_context, equipment_type=equipment_type)
        import json
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except:
                return {"ok": True, "result": result}
        
        if result and isinstance(result, dict):
            # Map uppercase keys from ai_engine to lowercase keys expected by frontend
            return {"ok": True, "result": {
                "probleme": result.get("Probleme", result.get("probleme", "Non identifié")),
                "cause": result.get("Cause", result.get("cause", "À déterminer")),
                "solution": result.get("Solution", result.get("solution", "Analyse manuelle requise")),
                "prevention": result.get("Prevention", result.get("prevention", "Maintenance préventive recommandée")),
                "urgence": result.get("Urgence", result.get("urgence", "À évaluer")),
                "type": result.get("Type", result.get("type", "?")),
                "priorite": result.get("Priorite", result.get("priorite", "MOYENNE")),
                "confidence": result.get("Confidence_Score", result.get("confidence", 0)),
            }}
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnostic IA échoué: {e}")

@app.post("/api/ai/analyze-performance")
def analyze_performance(body: dict, user: dict = Depends(_verify_token)):
    """Calls Gemini to produce a detailed predictive maintenance report (v2)."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    kpis = body.get("kpis", {})
    sym = body.get("sym", "TND")

    # --- Fetch real per-machine data from DB ---
    machine_details = ""
    equip_detail = ""
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT machine, COUNT(*) as nb, "
                "SUM(CASE WHEN type_intervention='Corrective' THEN 1 ELSE 0 END) as corr, "
                "SUM(CASE WHEN type_intervention ILIKE '%%r\u00e9ventive%%' THEN 1 ELSE 0 END) as prev, "
                "ROUND(AVG(duree_minutes)::numeric,1) as mttr_m, "
                "ROUND(SUM(cout)::numeric,0) as cout "
                "FROM interventions GROUP BY machine ORDER BY nb DESC LIMIT 20"
            ).fetchall()
            for r in rows:
                machine_details += f"  - {r['machine']}: {r['nb']} int ({r['corr']} corr, {r['prev']} prev), MTTR={r['mttr_m']}min, co\u00fbt={r['cout']} {sym}\n"
            eqs = conn.execute('SELECT "Nom","Client","Type","Statut","DateInstallation" FROM equipements ORDER BY "Nom" LIMIT 25').fetchall()
            for eq in eqs:
                equip_detail += f"  - {eq['Nom']} ({eq.get('Type','?')}) — {eq.get('Client','?')}, install\u00e9: {eq.get('DateInstallation','?')}, statut: {eq.get('Statut','?')}\n"
    except Exception as db_err:
        logger.warning(f"DB fetch for AI failed: {db_err}")

    risk_detail = ""
    for r in kpis.get("top_risques", []):
        risk_detail += f"  - {r.get('machine','?')}: risque={r.get('risque_panne_pct',0)}%, pi\u00e8ce={r.get('composant_a_risque','?')}, panne_dans={r.get('jours_avant_panne','?')}j, sant\u00e9={r.get('score_sante',0)}%\n"

    import datetime
    today = datetime.date.today()

    prompt = f"""Tu es Directeur du Service Technique d'une entreprise de maintenance d'\u00e9quipements d'imagerie m\u00e9dicale en Tunisie.
Analyse ces donn\u00e9es R\u00c9ELLES et produis un rapport pr\u00e9dictif d\u00e9taill\u00e9.

=== CHIFFRES DU PARC ===
- \u00c9quipements : {kpis.get('nb_equipements', 0)} | Interventions : {kpis.get('nb_interventions', 0)}
- Correctives : {kpis.get('interventions_correctives', 0)} | Pr\u00e9ventives : {kpis.get('interventions_preventives', 0)} | Calibrations : {kpis.get('interventions_calibration', 0)}
- Disponibilit\u00e9 : {kpis.get('disponibilite', 0)}% | MTBF : {kpis.get('mtbf', 0)}h | MTTR : {kpis.get('mttr', 0)}h
- Co\u00fbt total : {kpis.get('cout_total', 0)} {sym}

=== HISTORIQUE PAR MACHINE ===
{machine_details if machine_details else 'Non disponible'}

=== PR\u00c9DICTIONS IA ===
{risk_detail if risk_detail else 'Aucune'}

=== \u00c9QUIPEMENTS ===
{equip_detail if equip_detail else 'Non disponible'}

PRODUIS un rapport JSON STRICT :
{{{{
  "alertes_critiques": [
    {{{{
      "machine": "Nom (Client)",
      "score_sante": 41,
      "jours_avant_panne": 2,
      "nb_interventions": 19,
      "risque": "Risque concret",
      "action_immediate": "Action + pi\u00e8ces"
    }}}}
  ],
  "machines_stables": [
    {{{{
      "machine": "Nom (Client)",
      "score_sante": 84,
      "commentaire": "Pourquoi fiable"
    }}}}
  ],
  "plan_maintenance": [
    {{{{
      "jour": "Lundi {today.strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }}}},
    {{{{
      "jour": "Mardi {(today + datetime.timedelta(days=1)).strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }}}},
    {{{{
      "jour": "Mercredi {(today + datetime.timedelta(days=2)).strftime('%d/%m')}",
      "cibles": "Machines",
      "action": "Action"
    }}}}
  ],
  "estimation_couts": {{{{
    "cout_curatif_historique": {int(kpis.get('cout_total', 0))},
    "cout_preventif_propose": 0,
    "detail_preventif": "D\u00e9tail calcul",
    "gain_potentiel": 0,
    "ratio": "Pour 1 TND investi, X TND \u00e9conomis\u00e9s"
  }}}},
  "tendances": ["Tendance 1", "Tendance 2", "Tendance 3"],
  "conclusion": "Priorit\u00e9 absolue \u00e0..."
}}}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas r\u00e9pondu.")
    result = clean_json_response(raw)
    return {"ok": True, "result": result}


@app.post("/api/ai/analyze-pieces")
def analyze_pieces(body: dict, user: dict = Depends(_verify_token)):
    """
    Advanced AI analysis of spare parts with historical usage and predictions.
    Uses calculated consumption, data confidence, and intervention history.
    Generates buying recommendations and purchase planning.
    """
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
        from db_engine import get_ai_pieces_context
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI engine is not available.")

    # Get domain and equipment type from request (or use defaults)
    domaine = body.get("domain", "")
    equipment_type = body.get("equipment_type", "")
    sym = body.get("sym", "USD")  # Default to USD for universality

    # Get comprehensive context from database
    context = get_ai_pieces_context(domaine, equipment_type)
    pieces_data = context.get('pieces', [])
    stats = context.get('statistics', {})
    
    if not pieces_data:
        raise HTTPException(status_code=400, detail="No spare parts data available for analysis.")

    import datetime
    today = datetime.date.today()
    def fmt(d): return d.strftime("%d/%m/%Y")

    # Build detailed inventory report with predictions
    inventory_lines = ""
    critical_pieces = []
    for p in pieces_data:
        ref = p['reference']
        nom = p['designation']
        stock = p['current_stock']
        mini = p['minimum_stock']
        prix = p['unit_price']
        four = p['supplier']
        consomm = p['monthly_consumption']
        confiance = p['data_confidence']
        urgency = p['urgency']
        jours_rupture = p['days_until_rupture']
        recent_use = p['recent_usage_30d']
        
        # Format stock status with prediction (in French)
        if stock == 0:
            status = "EN RUPTURE - CRITIQUE"
        elif stock <= mini:
            status = f"STOCK BAS (besoin {mini - stock + 1})"
        elif jours_rupture is not None and jours_rupture <= 7:
            status = f"CORRECT mais RUPTURE en {jours_rupture:.0f} jours"
        else:
            status = f"ADAPTÉ (marge {stock - mini})"
        
        # Consumption info (in French)
        consump_info = f"Consommation: {consomm:.2f}/mois | Usage récent (30j): {recent_use}x | Confiance: {confiance}"
        
        line = f"  • {nom} ({ref}) | Équip: {p['equipment_type']} | Stock: {stock}/{mini} [{status}] | {consump_info} | Fournisseur: {four} | Prix: {prix:.2f} {sym}\n"
        inventory_lines += line
        
        # Track critical items
        if 'CRITICAL' in urgency:
            critical_pieces.append((ref, nom, urgency))
    
    # Timeline weeks
    s1 = f"{fmt(today)} - {fmt(today+datetime.timedelta(days=6))}"
    s2 = f"{fmt(today+datetime.timedelta(days=7))} - {fmt(today+datetime.timedelta(days=13))}"
    s3 = f"{fmt(today+datetime.timedelta(days=14))} - {fmt(today+datetime.timedelta(days=20))}"
    d0 = fmt(today)
    d3 = fmt(today+datetime.timedelta(days=3))
    d7 = fmt(today+datetime.timedelta(days=7))
    d14 = fmt(today+datetime.timedelta(days=14))
    
    # Contextualize for domain if provided (in French)
    domain_context = ""
    if domaine:
        domain_context = f"\nDomaine: {domaine}"
        if equipment_type:
            domain_context += f" | Équipement principal: {equipment_type}"
    
    prompt = f"""Tu es un expert en gestion de stock et approvisionnement pour équipements médicaux critiques.
Analyse cet inventaire de pièces de rechange avec prédictions et génère un plan d'achat stratégique EN FRANÇAIS.

=== CONTEXTE INSTALLATION ===
Aujourd'hui: {fmt(today)}{domain_context}
Total pièces: {stats['total_pieces']} références
Valeur stock: {stats['total_stock_value']:,.0f} {sym}
Articles urgence CRITIQUE: {stats['critical_urgency_count']}
Articles urgence HAUTE: {stats['high_urgency_count']}

=== INVENTAIRE PIÈCES AVEC PRÉDICTIONS ===
{inventory_lines}

=== DIRECTIVES D'ANALYSE ===
1. Utiliser les données de consommation mensuelle et usage récent pour générer des prédictions fiables
2. Data_confidence indique la fiabilité (INSUFFICIENT/LOW/MEDIUM/HIGH) - prioriser MEDIUM+
3. days_until_rupture = jours avant rupture de stock
4. Patterns usage 30j = indicatif de la tendance réelle
5. Générer quantités commandées basées sur consommation + délai fournisseur
6. Prioriser urgence CRITIQUE + haute confiance données

=== FORMAT RÉPONSE ===
RÉPONDS UNIQUEMENT en JSON valide (pas de markdown, texte avant/après):
{{
  "analyse_risque": "Résumé exécutif (3-4 phrases): identifier pièces critiques, impact opérationnel, capital à risque",
  "recommandations": [
    {{"piece": "Nom pièce", "reference": "REF", "raison": "Impact opérationnel si non commandé (ex: arrêt équipement = X patients)", "action": "Commander immédiatement", "quantite": 2, "date_achat": "{d0}", "urgence": "critique", "cout_estime": 500, "delai_fournisseur": 14}},
    {{"piece": "Nom pièce 2", "reference": "REF2", "raison": "Raison opérationnelle basée pattern consommation", "action": "Commander rapidement", "quantite": 1, "date_achat": "{d7}", "urgence": "haute", "cout_estime": 300, "delai_fournisseur": 14}}
  ],
  "plan_achat": [
    {{"semaine": "Semaine 1 ({s1})", "pieces": ["reference_1"], "budget": 1200, "priorite": "Critique", "raison": "Besoins immédiats"}},
    {{"semaine": "Semaine 2 ({s2})", "pieces": ["reference_2"], "budget": 800, "priorite": "Haute", "raison": "Prévenir rupture"}},
    {{"semaine": "Semaine 3 ({s3})", "pieces": ["reference_3"], "budget": 500, "priorite": "Normale", "raison": "Maintenir stock minimum"}}
  ],
  "impact_budget": {{
    "cout_total_commande": 2500,
    "gain_potentiel": 8000,
    "ratio": "Pour chaque 1 {sym} investi, X {sym} d'économie sur indisponibilité",
    "cout_indisponibilite_estime": 3000,
    "calcul_methode": "Basé sur nombre équipements critiques et consommation mensuelle"
  }},
  "tendances": ["Tendance 1 avec données concrètes", "Tendance 2", "Tendance 3"]
}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="AI did not respond.")
    result = clean_json_response(raw)
    
    # Log the analysis
    username = user.get("sub", "unknown")
    log_audit(username, "AI_ANALYZE_PIECES", f"Analyzed {len(pieces_data)} spare parts", "pieces")
    
    return {"ok": True, "result": result}


@app.post("/api/ai/analyze-sav")
def analyze_sav(body: dict, user: dict = Depends(_verify_token)):
    """Comprehensive SAV/Interventions analysis using Gemini."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    sav_data = body.get("sav_data", {})
    sym = body.get("sym", "TND")

    prompt = f"""Tu es un expert en gestion de maintenance SAV pour équipements d'imagerie médicale en Tunisie.
Analyse ces données SAV RÉELLES et produis un rapport COMPLET et DÉTAILLÉ.

=== STATISTIQUES GLOBALES ===
- Total interventions : {sav_data.get('nb_total', 0)}
- Clôturées : {sav_data.get('nb_cloturees', 0)}
- En cours : {sav_data.get('nb_en_cours', 0)}
- Taux résolution : {sav_data.get('taux_resolution', 0)}%
- MTTR moyen : {sav_data.get('mttr_h', 0)}h
- Durée totale : {sav_data.get('duree_totale_h', 0)}h

=== RÉPARTITION PAR TYPE ===
- Correctives : {sav_data.get('nb_correctives', 0)}
- Préventives : {sav_data.get('nb_preventives', 0)}  
- Installations : {sav_data.get('nb_installations', 0)}
- Ratio correctif : {sav_data.get('ratio_correctif_pct', 0)}%

=== COÛTS ===
- Coût total interventions : {sav_data.get('cout_interventions', 0)} {sym}
- Coût pièces : {sav_data.get('cout_pieces', 0)} {sym}
- Coût total : {sav_data.get('cout_total', 0)} {sym}
- Coût moyen/intervention : {sav_data.get('cout_moyen', 0)} {sym}

=== PERFORMANCE ÉQUIPE (par technicien) ===
{sav_data.get('tech_details', 'Non disponible')}

=== DÉTAIL DES INTERVENTIONS RÉCENTES ===
{sav_data.get('interventions_detail', 'Non disponible')}

=== MACHINES LES PLUS INTERVENUES ===
{sav_data.get('machines_detail', 'Non disponible')}

=== CLIENTS ===
{sav_data.get('clients_detail', 'Non disponible')}

IMPORTANT: Analyse en profondeur et produis un JSON STRICT avec cette structure exacte :
{{{{
  "analyse": "Résumé exécutif complet de la situation SAV (3-5 phrases détaillées)",
  "score_global": 75,
  "points_forts": [
    "Point fort 1 détaillé avec chiffres",
    "Point fort 2 détaillé avec chiffres",
    "Point fort 3 détaillé avec chiffres"
  ],
  "points_faibles": [
    "Point faible 1 détaillé avec chiffres",
    "Point faible 2 détaillé avec chiffres", 
    "Point faible 3 détaillé avec chiffres"
  ],
  "recommandations": [
    {{{{
      "titre": "Titre recommandation",
      "description": "Description détaillée de l'action à entreprendre",
      "impact": "HAUT"
    }}}},
    {{{{
      "titre": "Titre recommandation 2",
      "description": "Description détaillée",
      "impact": "MOYEN"
    }}}},
    {{{{
      "titre": "Titre recommandation 3",
      "description": "Description détaillée",
      "impact": "BAS"
    }}}}
  ],
  "performance_equipe": [
    {{{{
      "technicien": "Nom",
      "evaluation": "Excellent/Bon/À améliorer",
      "commentaire": "Commentaire détaillé sur ses performances"
    }}}}
  ],
  "analyse_couts": {{{{
    "verdict": "Maîtrisés/Élevés/Critiques",
    "detail": "Analyse détaillée des coûts",
    "economie_possible": "Estimation d'économie possible et comment"
  }}}},
  "tendances": [
    "Tendance 1 observée",
    "Tendance 2 observée",
    "Tendance 3 observée"
  ],
  "priorites_immediates": [
    "Action prioritaire 1",
    "Action prioritaire 2"
  ]
}}}}"""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas répondu.")
    result = clean_json_response(raw)
    return {"ok": True, "result": result}


# ==========================================
# AI — Analyse des coûts (cartes structurées)
# ==========================================

@app.post("/api/ai/analyze-costs")
def ai_analyze_costs(body: dict, user: dict = Depends(_verify_token)):
    """Analyse IA structurée des coûts clients — retourne des cartes comme le diagnostic IA."""
    try:
        from ai_engine import _call_ia, clean_json_response, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    clients_data = body.get("clients", [])
    kpis = body.get("kpis", {})
    if not clients_data:
        raise HTTPException(status_code=400, detail="Aucune donnée client.")

    # ── Fetch TCO data server-side ──
    tco_data = []
    try:
        tco_data = finances_tco(client=None, user=user)
    except Exception:
        pass

    # Build compact summary
    avg_cout = sum(c.get('cout_total', 0) for c in clients_data) / max(len(clients_data), 1)
    client_lines = []
    for c in clients_data:
        ecart = round(((c.get('cout_total', 0) - avg_cout) / avg_cout * 100)) if avg_cout > 0 else 0
        nb_interv = c.get('nb_interventions', 0)
        nb_equip = c.get('nb_equipements', 0)
        ratio_interv = round(nb_interv / nb_equip, 1) if nb_equip > 0 else 0
        client_lines.append(
            f"{c.get('client','?')}: "
            f"revenu={c.get('revenu_contrats',0)} TND, "
            f"coûts_total={c.get('cout_total',0)} TND, "
            f"coût_interventions={c.get('cout_interventions',0)} TND, "
            f"coût_pièces={c.get('cout_pieces',0)} TND, "
            f"coût_main_oeuvre={c.get('cout_main_oeuvre',0)} TND, "
            f"marge={c.get('marge_pct',0)}%, "
            f"interventions={nb_interv} (correctives={c.get('nb_correctives',0)}, préventives={c.get('nb_preventives',0)}), "
            f"equipements={nb_equip}, "
            f"ratio_interv/equip={ratio_interv}, "
            f"ratio_préventif={round(c.get('nb_preventives',0)/nb_interv*100) if nb_interv>0 else 0}%, "
            f"écart_vs_moy={'+' if ecart>0 else ''}{ecart}%"
        )
    summary = "\n".join(client_lines)

    # ── TCO summary (top 15 by cost) ──
    tco_summary = ""
    if tco_data:
        top_tco = sorted(tco_data, key=lambda x: x.get('tco_total', 0), reverse=True)[:15]
        tco_total_global = sum(t.get('tco_total', 0) for t in tco_data)
        tco_lines = []
        for t in top_tco:
            age_ans = round(t.get('age_jours', 0) / 365, 1)
            tco_lines.append(
                f"  {t.get('equipement','?')} ({t.get('client','')}): "
                f"TCO={t.get('tco_total',0)} TND, "
                f"pièces={t.get('cout_pieces',0)} TND, MO={t.get('cout_main_oeuvre',0)} TND, interv={t.get('cout_interventions',0)} TND, "
                f"nb_interv={t.get('nb_interventions',0)} (corr={t.get('nb_correctives',0)}/prev={t.get('nb_preventives',0)}), "
                f"âge={age_ans}ans, TCO/mois={t.get('tco_mensuel',0)} TND"
            )
        tco_summary = f"""
═══ TCO — TOTAL COST OF OWNERSHIP (Top 15 équipements) ═══
TCO global parc: {round(tco_total_global)} TND | Nb équipements: {len(tco_data)} | TCO moyen/équipement: {round(tco_total_global/max(len(tco_data),1))} TND
{chr(10).join(tco_lines)}"""

    prompt = f"""Tu es un expert en gestion financière de maintenance biomédicale (GMAO). Analyse ces données financières SAVIA en profondeur.

═══ INDICATEURS GLOBAUX ═══
• Coût moyen par client: {round(avg_cout)} TND
• Marge globale: {kpis.get('marge_pct',0)}%
• Marge brute: {kpis.get('marge_globale',0)} TND
• Revenu total contrats: {kpis.get('revenu_total',0)} TND
• Coût total: {kpis.get('cout_total',0)} TND
• Clients rentables: {kpis.get('nb_rentables',0)} / {kpis.get('nb_clients',0)}
• Clients déficitaires: {kpis.get('nb_deficitaires',0)}

═══ DONNÉES DÉTAILLÉES PAR CLIENT ═══
{summary}
{tco_summary}

═══ CONSIGNES D'ANALYSE ═══
Retourne UNIQUEMENT un JSON valide avec cette structure exacte:
{{
  "clients_couteux": "Pour chaque client dont le coût dépasse la moyenne: nomme-le, donne son écart en % et en TND vs la moyenne, son ratio interventions/équipement, la répartition de ses coûts (pièces vs MO vs interventions). Indique le coût par équipement. Utilise • pour chaque client. Sois PRÉCIS avec tous les chiffres.",

  "causes": "Analyse technique des causes racines: taux de maintenance corrective vs préventive par client (un ratio préventif <30% est problématique), coût moyen par intervention, concentration des coûts pièces ou main d'œuvre, équipements vieillissants potentiels, fréquence d'interventions anormale (>4 interv/équipement/an = critique). Utilise • pour chaque cause identifiée avec les chiffres.",

  "optimisations": "Propositions concrètes avec estimation d'impact financier: ex. 'Augmenter le préventif de X à Y% pour [client] → économie estimée de Z TND/an', 'Négocier un contrat pièces forfaitaire pour [client]', 'Former les techniciens sur [type d'équipement] pour réduire le taux de rappel'. Chiffre chaque recommandation. Utilise • pour chaque proposition.",

  "clients_performants": "Pour chaque client rentable: nomme-le, donne sa marge en % et TND, son ratio préventif/correctif, son coût par équipement. Explique POURQUOI il performe (bon ratio préventif, peu de pannes, contrat bien dimensionné...). Identifie les bonnes pratiques réplicables. Utilise • pour chaque client.",

  "tco_analyse": "Analyse TCO du parc équipement: identifie les 3-5 équipements avec le TCO le plus élevé, calcule le TCO/mois et compare-le à la moyenne du parc. Pour chaque équipement critique: donne le TCO total, la ventilation pièces/MO/interventions, l'âge, le ratio correctif/préventif. Indique si le TCO justifie un remplacement (seuil: TCO > 60% du prix neuf estimé ou TCO/mois en hausse). Propose un plan de renouvellement priorisé. Utilise • pour chaque équipement.",

  "recommandations": "Actions stratégiques prioritaires classées par impact: renégociation tarifaire avec montants suggérés, plan de transition corrective→préventive avec calendrier, optimisation stock pièces de rechange (quelles pièces, quel fournisseur), seuils d'alerte à mettre en place (coût/équipement max, ratio correctif max), KPIs de suivi mensuel à implémenter. Utilise • pour chaque recommandation.",

  "tags": ["3-5 tags pertinents parmi: Surcoût Pièces, Ratio Correctif Élevé, Marge Négative, Contrat Sous-dimensionné, Maintenance Préventive Insuffisante, Optimisation Stock, Renégociation Contrat, Performance Élevée, Équipements Critiques, TCO Élevé, Renouvellement Requis"],
  "confiance": 85
}}

IMPORTANT: Sois un consultant expert. Chaque section doit faire 4-8 lignes avec des données chiffrées précises. Retourne UNIQUEMENT le JSON, rien d'autre."""

    raw = _call_ia(prompt, timeout=90, is_json=True)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas répondu.")
    result = clean_json_response(raw)
    return {"ok": True, "result": result}


@app.post("/api/ai/analyze-costs/pdf")
def ai_analyze_costs_pdf(body: dict, user: dict = Depends(_verify_token)):
    """Genere un PDF a partir du resultat d'analyse IA des couts."""
    from io import BytesIO
    from starlette.responses import StreamingResponse
    import base64 as _b64
    import urllib.request as _ur

    data = body.get("result", {})
    kpis = body.get("kpis", {})
    company_name = body.get("company_name", "")
    company_logo = body.get("company_logo", "")
    if not data:
        raise HTTPException(status_code=400, detail="Aucune donnee d'analyse.")

    SAVIA_LOGO = "/app/logo-savia.png"

    # Client logo
    _client_logo_io = None
    if company_logo:
        try:
            clogo = company_logo.strip()
            if clogo.startswith("data:"):
                _b64_part = clogo.split(",", 1)[1] if "," in clogo else clogo
                _client_logo_io = BytesIO(_b64.b64decode(_b64_part))
            elif clogo.startswith("http"):
                req_ = _ur.Request(clogo, headers={"User-Agent": "Mozilla/5.0"})
                with _ur.urlopen(req_, timeout=6) as _r:
                    _client_logo_io = BytesIO(_r.read())
        except Exception:
            pass

    pdf = SaviaPDF(orientation="P", unit="mm", format="A4")
    pdf.set_header_data(
        SAVIA_LOGO, _client_logo_io,
        company_name if company_name and company_name != "SAVIA" else "",
        "",
        report_title="ANALYSE FINANCIERE IA"
    )
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_top_margin(pdf.HEADER_H + 10)
    pdf.add_page()

    # KPIs summary bar
    ky = pdf.get_y() + 2
    pdf.set_fill_color(238, 243, 246)
    pdf.rect(8, ky, pdf.w - 16, 12, 'F')
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(47, 65, 86)
    kpi_items = [
        f"Revenu: {_fmt_number(kpis.get('revenu_total', 0))} TND",
        f"Couts: {_fmt_number(kpis.get('cout_total', 0))} TND",
        f"Marge: {kpis.get('marge_pct', 0)}%",
        f"Rentables: {kpis.get('nb_rentables', 0)}/{kpis.get('nb_clients', 0)}",
    ]
    pdf.set_xy(10, ky + 2)
    pdf.cell(pdf.w - 20, 8, _sanitize("   |   ".join(kpi_items)), align="C")
    pdf.ln(16)

    # Section card renderer with bullet support
    def render_card(title, content, color_rgb):
        r, g, b = color_rgb
        W = pdf.w - 20  # usable width

        if pdf.get_y() > 250:
            pdf.add_page()

        # Colored section header
        pdf.set_fill_color(r, g, b)
        pdf.rect(10, pdf.get_y(), W, 7, 'F')
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.set_x(12)
        pdf.cell(W - 4, 7, _sanitize(title.upper()), new_x="LMARGIN", new_y="NEXT")

        pdf.ln(1)

        # Content: split by bullet markers
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(50, 50, 50)
        raw = content or "-"
        bullets = [b.strip() for b in raw.replace('\n', ' ').split(chr(0x2022)) if b.strip()]
        if not bullets:
            bullets = [b.strip() for b in raw.split('\n') if b.strip()]

        for bullet in bullets:
            if not bullet:
                continue
            if pdf.get_y() > 270:
                pdf.add_page()
            cy = pdf.get_y()
            # Small black bullet dot
            pdf.set_fill_color(50, 50, 50)
            pdf.ellipse(12, cy + 1.2, 2, 2, 'F')
            pdf.set_x(16)
            pdf.multi_cell(pdf.w - 28, 4.2, _sanitize(bullet))
            pdf.ln(0.8)

        pdf.ln(3)

    # Render all cards
    cards = [
        ("Clients Couteux", data.get("clients_couteux", ""), (220, 53, 53)),
        ("Causes Identifiees", data.get("causes", ""), (234, 88, 12)),
        ("Optimisations Proposees", data.get("optimisations", ""), (22, 163, 74)),
        ("Analyse TCO - Cout Total de Possession", data.get("tco_analyse", ""), (13, 148, 136)),
        ("Clients Performants", data.get("clients_performants", ""), (37, 99, 235)),
        ("Recommandations Strategiques", data.get("recommandations", ""), (124, 58, 237)),
    ]
    for title, content, color in cards:
        render_card(title, content, color)

    # Footer info
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 4, _sanitize(f"Genere le {datetime.now().strftime('%d/%m/%Y a %H:%M')} | SAVIA Maintenance - Confidentiel"), align="C")

    buf = BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=SAVIA_Analyse_Couts_IA.pdf"}
    )


# ==========================================
# AI CHATBOT — Assistant conversationnel
# ==========================================

@app.post("/api/ai/chat")
def ai_chat(body: dict, user: dict = Depends(_verify_token)):
    """Assistant IA conversationnel — répond aux questions en langage naturel sur les données SAVIA."""
    from datetime import date, timedelta
    try:
        from ai_engine import _call_ia, AI_AVAILABLE
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not AI_AVAILABLE:
        raise HTTPException(status_code=503, detail="L'IA n'est pas disponible.")

    message = body.get("message", "").strip()
    history = body.get("history", [])
    if not message:
        raise HTTPException(status_code=400, detail="Message vide.")

    # ── Aggregate compact data context ──
    today = date.today()
    ctx_parts = []
    try:
        df_interv = lire_interventions()
        if not df_interv.empty:
            total = len(df_interv)
            by_statut = df_interv['statut'].value_counts().to_dict() if 'statut' in df_interv.columns else {}
            by_type = df_interv['type_intervention'].value_counts().head(5).to_dict() if 'type_intervention' in df_interv.columns else {}
            by_tech = df_interv['technicien'].value_counts().head(5).to_dict() if 'technicien' in df_interv.columns else {}
            by_machine = df_interv['machine'].value_counts().head(5).to_dict() if 'machine' in df_interv.columns else {}
            by_client = df_interv['client'].value_counts().head(5).to_dict() if 'client' in df_interv.columns else {}
            # This month
            mois = 0
            if 'date' in df_interv.columns:
                month_str = today.strftime('%Y-%m')
                mois = int(df_interv['date'].astype(str).str[:7].eq(month_str).sum())
            ctx_parts.append(f"INTERVENTIONS: {total} total, {mois} ce mois. Statuts: {by_statut}. Types(top5): {by_type}. Techniciens(top5): {by_tech}. Machines(top5): {by_machine}. Clients(top5): {by_client}.")
    except Exception:
        pass
    try:
        df_equip = lire_equipements()
        if not df_equip.empty:
            n = len(df_equip)
            by_dom = df_equip['domaine'].value_counts().to_dict() if 'domaine' in df_equip.columns else {}
            by_st = df_equip['Statut'].value_counts().to_dict() if 'Statut' in df_equip.columns else {}
            by_cl = df_equip['Client'].value_counts().head(5).to_dict() if 'Client' in df_equip.columns else {}
            ctx_parts.append(f"EQUIPEMENTS: {n} total. Domaines: {by_dom}. Statuts: {by_st}. Clients(top5): {by_cl}.")
    except Exception:
        pass
    try:
        df_pieces = lire_pieces()
        if not df_pieces.empty:
            n = len(df_pieces)
            rupture = []
            if 'stock_actuel' in df_pieces.columns and 'stock_minimum' in df_pieces.columns:
                low = df_pieces[df_pieces['stock_actuel'] <= df_pieces['stock_minimum']]
                rupture = low['nom'].head(5).tolist() if 'nom' in low.columns else []
            ctx_parts.append(f"PIECES: {n} références. En rupture/stock bas: {rupture if rupture else 'aucune'}.")
    except Exception:
        pass
    try:
        df_plan = lire_planning()
        if not df_plan.empty:
            upcoming = df_plan[df_plan['date_prevue'].astype(str).str[:10] >= str(today)]
            n_upcoming = len(upcoming) if not upcoming.empty else 0
            ctx_parts.append(f"PLANNING: {n_upcoming} maintenances à venir.")
    except Exception:
        pass
    try:
        df_contrats = lire_contrats()
        if not df_contrats.empty:
            n = len(df_contrats)
            ctx_parts.append(f"CONTRATS: {n} contrats.")
    except Exception:
        pass

    data_context = "\n".join(ctx_parts) if ctx_parts else "Données non disponibles."

    # ── Build conversation ──
    hist_text = ""
    for h in history[-6:]:
        role = "Utilisateur" if h.get("role") == "user" else "Assistant"
        hist_text += f"{role}: {h.get('content','')}\n"

    prompt = f"""Tu es SAVIA Assistant, l'assistant IA intelligent de la plateforme SAVIA de gestion de maintenance d'équipements médicaux.

RÔLE: Tu aides les responsables techniques, managers et techniciens à comprendre leurs données, prendre des décisions et obtenir des insights sur leur parc d'équipements.

DONNÉES EN TEMPS RÉEL DE LA PLATEFORME:
{data_context}

DATE DU JOUR: {today.strftime('%d/%m/%Y')}

RÈGLES:
- Réponds en français, de manière concise et professionnelle
- Utilise les données ci-dessus pour répondre avec des chiffres précis
- Si la question ne concerne pas les données, réponds quand même de manière utile (conseils maintenance, bonnes pratiques...)
- Formate ta réponse en texte simple (pas de markdown complexe), utilise des puces • pour les listes
- À la fin de ta réponse, sur une ligne séparée commençant par SUGGESTIONS:, propose 2-3 questions de suivi pertinentes séparées par |

{f"HISTORIQUE DE CONVERSATION:{chr(10)}{hist_text}" if hist_text else ""}

QUESTION DE L'UTILISATEUR: {message}"""

    raw = _call_ia(prompt, timeout=60)
    if not raw:
        raise HTTPException(status_code=500, detail="L'IA n'a pas répondu.")

    # Parse suggestions from response
    response_text = raw.strip()
    suggestions = []
    if "SUGGESTIONS:" in response_text:
        parts = response_text.split("SUGGESTIONS:")
        response_text = parts[0].strip()
        if len(parts) > 1:
            suggestions = [s.strip() for s in parts[1].strip().split("|") if s.strip()]

    return {"response": response_text, "suggestions": suggestions[:3]}


# ==========================================
# ADMIN — Utilisateurs
# ==========================================

@app.get("/api/admin/users")
def get_users(user: dict = Depends(_verify_token)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, nom_complet, role, client, email, actif, profil, pages_autorisees, created_at, last_login FROM utilisateurs ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/users")
def create_user(body: dict, user: dict = Depends(_verify_token)):
    # Validate role
    valid_roles = ['Admin', 'Technicien', 'Lecteur', 'Manager', 'Responsable Technique', 'Gestionnaire']
    role = body.get("role", "Lecteur")
    if role not in valid_roles:
        return {"error": f"Invalid role. Must be one of: {', '.join(valid_roles)}"}, 400
    
    username = body.get("username", "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username est requis")
    
    # Check if username already exists
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM utilisateurs WHERE username = ?",
            (username,)
        ).fetchone()
        
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Ce nom d'utilisateur '{username}' est déjà utilisé. Veuillez choisir un autre."
            )
        
        hashed = bcrypt.hashpw(body["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        conn.execute(
            "INSERT INTO utilisateurs (username, password_hash, nom_complet, role, client, email, actif, profil, pages_autorisees) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (username, hashed, body.get("nom_complet", ""), role, body.get("client", ""), body.get("email", ""), body.get("profil", ""), body.get("pages_autorisees", ""))
        )
    return {"ok": True}


@app.put("/api/admin/users/{user_id}")
def update_user(user_id: int, body: dict, user: dict = Depends(_verify_token)):
    fields = []
    params = []
    for f in ["nom_complet", "role", "client", "actif", "email", "profil", "pages_autorisees"]:
        if f in body:
            fields.append(f"{f} = ?")
            params.append(body[f])
    if "password" in body and body["password"]:
        fields.append("password_hash = ?")
        params.append(bcrypt.hashpw(body["password"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8"))
    if fields:
        params.append(user_id)
        with get_db() as conn:
            conn.execute(f"UPDATE utilisateurs SET {', '.join(fields)} WHERE id = ?", params)
    return {"ok": True}


@app.delete("/api/admin/users/{user_id}")
def delete_user(user_id: int, user: dict = Depends(_verify_token)):
    with get_db() as conn:
        conn.execute("DELETE FROM utilisateurs WHERE id = ?", (user_id,))
    return {"ok": True}


# ==========================================
# AUDIT LOG
# ==========================================

@app.get("/api/audit")
def get_audit_log(limit: int = 100, user: dict = Depends(_verify_token)):
    return _df_to_records(lire_audit(limit=limit))


@app.get("/api/admin/audit-logs")
def get_admin_audit_logs(
    limit: int = Query(1000, ge=1, le=5000),
    username: str = Query(""),
    action: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    user: dict = Depends(_verify_token),
):
    """
    GET /api/admin/audit-logs - Retourne les logs filtrés (ADMIN ONLY)
    
    Query Parameters:
      - limit: Nombre max de logs (1-5000, défaut 1000)
      - username: Filtrer par utilisateur (optionnel)
      - action: Filtrer par type d'action (optionnel)
      - date_from: Date début YYYY-MM-DD (optionnel)
      - date_to: Date fin YYYY-MM-DD (optionnel)
    
    Returns: Array of audit log entries
    """
    # Vérifier que l'utilisateur est ADMIN
    if user.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    try:
        df = lire_audit(
            limit=limit,
            username=username if username else "",
            action=action if action else "",
            date_from=date_from if date_from else "",
            date_to=date_to if date_to else ""
        )
        return _df_to_records(df)
    except Exception as e:
        logger.error(f"Error fetching audit logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class AuditExportRequest(BaseModel):
    limit: int = 1000
    username: str = ""
    action: str = ""
    date_from: str = ""
    date_to: str = ""


@app.post("/api/admin/audit-logs/export-pdf")
def export_audit_logs_pdf(
    req: AuditExportRequest,
    user: dict = Depends(_verify_token),
):
    """
    POST /api/admin/audit-logs/export-pdf - Exporte les logs en PDF (ADMIN ONLY)
    
    Body parameters:
      - limit: Nombre max de logs
      - username: Filtrer par utilisateur
      - action: Filtrer par type d'action
      - date_from: Date début YYYY-MM-DD
      - date_to: Date fin YYYY-MM-DD
    
    Returns: PDF file
    """
    # Vérifier que l'utilisateur est ADMIN
    if user.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    
    try:
        # Récupérer les logs avec les filtres
        df = lire_audit(
            limit=req.limit,
            username=req.username,
            action=req.action,
            date_from=req.date_from,
            date_to=req.date_to
        )
        
        if df.empty:
            raise HTTPException(status_code=400, detail="Aucun log à exporter")
        
        # Créer le PDF en format PAYSAGE
        pdf = FPDF(orientation='L')  # L = Landscape
        pdf.add_page()
        
        # Charger la police DejaVu
        _DJVU = '/app/DejaVuSans.ttf'
        if os.path.exists(_DJVU):
            try:
                pdf.add_font('DejaVu', fname=_DJVU)
            except Exception as e:
                logger.warning(f"Could not load DejaVu font: {e}, falling back to Helvetica")
                _DJVU = None
        else:
            _DJVU = None
        
        # Utiliser Helvetica comme fallback si DejaVu n'est pas disponible
        font_name = 'DejaVu' if _DJVU else 'Helvetica'
        pdf.set_font(font_name, size=10)
        
        # En-tête
        pdf.set_font(font_name, "B", size=14)
        pdf.cell(0, 10, "Journal d'Audit SAVIA", ln=True, align="C")
        
        pdf.set_font(font_name, size=9)
        pdf.cell(0, 5, f"Généré le: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=True, align="R")
        pdf.cell(0, 5, f"Par: {user.get('nom', user.get('username', 'N/A'))}", ln=True, align="R")
        
        # Filtres appliqués
        filters_text = []
        if req.username:
            filters_text.append(f"Utilisateur: {req.username}")
        if req.action:
            filters_text.append(f"Action: {req.action}")
        if req.date_from or req.date_to:
            date_range = f"Période: {req.date_from or '...'} à {req.date_to or '...'}"
            filters_text.append(date_range)
        
        if filters_text:
            pdf.set_font(font_name, "I", size=8)
            pdf.cell(0, 4, "Filtres appliqués: " + " | ".join(filters_text), ln=True)
        
        pdf.ln(3)
        
        # Tableau des logs - colonnes plus larges pour le paysage
        pdf.set_font(font_name, "B", size=9)
        # Largeurs pour format paysage avec Action et Détails +40%
        col_widths = [30, 30, 49, 98, 25, 20]  # Total ~252mm (ajusté)
        headers = ["Date/Heure", "Utilisateur", "Action", "Détails", "Page", "IP"]
        
        # En-têtes du tableau avec couleur de fond
        pdf.set_fill_color(1, 180, 188)  # Couleur SAVIA (cyan)
        pdf.set_text_color(255, 255, 255)  # Texte blanc
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 8, header, border=1, align="C", fill=True)
        pdf.ln()
        
        # Contenu du tableau
        pdf.set_font(font_name, size=8)
        pdf.set_text_color(0, 0, 0)  # Texte noir pour le contenu
        for _, row in df.iterrows():
            timestamp = str(row.get("timestamp", ""))[:16]  # Format: YYYY-MM-DD HH:MM
            username_val = str(row.get("username", ""))[:25]
            action_val = str(row.get("action", ""))[:25]
            details_val = str(row.get("details", ""))[:50]
            page_val = str(row.get("page", ""))[:20]
            ip_val = str(row.get("ip_address", ""))[:15]
            
            # Écrire les cellules avec hauteur augmentée pour multi-ligne
            pdf.cell(col_widths[0], 7, timestamp, border=1)
            pdf.cell(col_widths[1], 7, username_val, border=1)
            pdf.cell(col_widths[2], 7, action_val, border=1)
            pdf.cell(col_widths[3], 7, details_val, border=1)
            pdf.cell(col_widths[4], 7, page_val, border=1)
            pdf.cell(col_widths[5], 7, ip_val, border=1)
            pdf.ln()
        
        # Retourner le PDF
        pdf_bytes = pdf.output(dest='S')
        # pdf.output() retourne bytes ou bytearray selon la version de fpdf
        if isinstance(pdf_bytes, (str, bytearray)):
            if isinstance(pdf_bytes, str):
                pdf_bytes = pdf_bytes.encode('latin-1')
            else:
                pdf_bytes = bytes(pdf_bytes)
        
        from fastapi.responses import Response
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=audit-logs-{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting audit logs to PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# NOTIFICATIONS
# ==========================================

@app.get("/api/notifications")
def get_notifications(
    destination: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Liste les notifications. Destination auto-detectée selon le rôle."""
    role = user.get("role", "")
    nom = (user.get("nom") or "").strip()
    if destination is None:
        destination = "technicien" if role == "Technicien" else "gestionnaire"
    df = lire_notifications_pieces(destination=destination)
    # Pour les techniciens : filtrer par leur nom
    if role == "Technicien" and nom and not df.empty:
        from db_engine import read_sql
        df = df[df["technicien"].fillna("").str.lower().apply(
            lambda t: all(w in t for w in nom.lower().split() if len(w) > 1)
        )]
    return _df_to_records(df)


@app.get("/api/notifications/count")
def get_notification_count(
    destination: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Compte les notifications non lues. Destination auto-detectée selon le rôle."""
    role = user.get("role", "")
    nom = (user.get("nom") or "").strip()
    if destination is None:
        destination = "technicien" if role == "Technicien" else "gestionnaire"
    count = compter_notifications_non_lues(destination, technicien=nom if role == "Technicien" else None)
    return {"count": count}


@app.patch("/api/notifications/{notif_id}/read")
def mark_notification_read(notif_id: int, user: dict = Depends(_verify_token)):
    """Marque une notification comme lue."""
    marquer_notification_lue(notif_id)
    return {"ok": True}


@app.patch("/api/notifications/{notif_id}/done")
def mark_notification_done(notif_id: int, user: dict = Depends(_verify_token)):
    """Marque une notification comme traitée."""
    marquer_notification_traitee(notif_id)
    return {"ok": True}


# ==========================================
# SETTINGS / CONFIG
# ==========================================

@app.get("/api/settings")
def get_settings(user: dict = Depends(_verify_token)):
    keys = [
        "nom_organisation", "logo_path", "langue", "theme",
        "taux_horaire_technicien", "telegram_token", "telegram_chat_id",
        "telegram_sav_token", "telegram_sav_chat_id",
        "telegram_manager_token", "telegram_manager_chat_id",
        "telegram_stock_token", "telegram_stock_chat_id",
        "gemini_api_key", "role_permissions",
    ]
    try:
        with get_db() as conn:
            result = {k: "" for k in keys}
            for k in keys:
                row = conn.execute(
                    "SELECT valeur FROM config_client WHERE cle = ?",
                    (k,)
                ).fetchone()
                if row:
                    result[k] = row["valeur"] or ""
            return result
    except Exception as e:
        import traceback
        logger.error(f"Erreur get_settings: {e}\n{traceback.format_exc()}")
        # Fallback: chercher clé par clé
        result = {}
        for k in keys:
            result[k] = get_config(k, "")
        return result


@app.put("/api/settings")
def update_settings(body: dict = Body(...), user: dict = Depends(_verify_token)):
    try:
        logger.info(f"[UPDATE_SETTINGS] Received body: {body}")
        with get_db() as conn:
            for k, v in body.items():
                logger.info(f"[UPDATE_SETTINGS] Saving key='{k}', value_type={type(v).__name__}, value_length={len(str(v))}")
                # Use SQLite-compatible syntax with ? placeholder
                # Note: PgCursorWrapper translates ? to ? and EXCLUDED handles both SQLite and PostgreSQL
                conn.execute(
                    """
                    INSERT INTO config_client (cle, valeur) VALUES (?, ?)
                    ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur
                    """,
                    (k, str(v))
                )
                logger.info(f"[UPDATE_SETTINGS] Successfully saved key='{k}'")
        logger.info(f"[UPDATE_SETTINGS] All settings saved successfully")
        return {"ok": True}
    except Exception as e:
        import traceback
        logger.error(f"[UPDATE_SETTINGS] Error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erreur sauvegarde config: {e}")


# ==========================================
# NOTIFICATION SCHEDULES
# ==========================================

@app.get("/api/notification-schedules")
def get_notification_schedules(user: dict = Depends(_verify_token)):
    """Récupère tous les horaires de notification pour les bots Telegram."""
    try:
        schedules = lire_notification_schedules()
        
        # Si aucun horaire n'existe, initialiser avec les valeurs par défaut
        if not schedules:
            default_bots = ['telegram', 'telegram_sav', 'telegram_manager', 'telegram_stock']
            for bot_key in default_bots:
                sauvegarder_notification_schedule(bot_key, 1, 8, 30, '1,2,3,4,5,6,7')
            schedules = lire_notification_schedules()
        
        return {"ok": True, "schedules": schedules}
    except Exception as e:
        import traceback
        logger.error(f"Erreur get_notification_schedules: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erreur lecture horaires: {e}")


@app.put("/api/notification-schedules")
def update_notification_schedules(body: dict, user: dict = Depends(_verify_token)):
    """Sauvegarde les horaires de notification pour les bots Telegram.
    
    Body format:
    {
        "telegram": {"enabled": 1, "hour": 8, "minute": 30, "days_of_week": "1,2,3,4,5,6,7"},
        "telegram_sav": {...},
        ...
    }
    """
    try:
        sauvegarder_notification_schedules_batch(body)
        return {"ok": True}
    except Exception as e:
        import traceback
        logger.error(f"Erreur update_notification_schedules: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erreur sauvegarde horaires: {e}")


# ==========================================
# CLIENTS (derived from equipements)
# ==========================================

@app.get("/api/clients")
def get_clients(user: dict = Depends(_verify_token)):
    """List clients from the dedicated clients table, enriched with equipment stats using SQL aggregates."""
    try:
        with get_db() as conn:
            # Get all clients from clients table
            df_clients = read_sql("SELECT * FROM clients ORDER BY nom", conn)
            
            if df_clients.empty:
                return []
            
            # Get equipment stats by client (using exact string match, case-insensitive)
            eq_stats_query = """
            SELECT 
                client,
                COUNT(*) as nb_eq,
                SUM(CASE WHEN statut IN ('Hors Service', 'Critique') THEN 1 ELSE 0 END) as nb_hs
            FROM equipements
            WHERE client IS NOT NULL AND client != ''
            GROUP BY client
            """
            df_eq_stats = read_sql(eq_stats_query, conn)
            
            # Get intervention stats by client
            int_stats_query = """
            SELECT 
                e.client,
                COUNT(DISTINCT i.id) as nb_int
            FROM interventions i
            JOIN equipements e ON e.nom = i.machine
            WHERE e.client IS NOT NULL AND e.client != ''
            GROUP BY e.client
            """
            df_int_stats = read_sql(int_stats_query, conn)
            
            # Build result with enriched data
            result = []
            for _, row in df_clients.iterrows():
                client_name = row.get("nom", "")
                
                # Find stats for this client (case-insensitive match)
                eq_stat = None
                if not df_eq_stats.empty:
                    eq_stat = df_eq_stats[df_eq_stats["client"].str.lower() == client_name.lower()].iloc[0] if len(df_eq_stats[df_eq_stats["client"].str.lower() == client_name.lower()]) > 0 else None
                
                int_stat = None
                if not df_int_stats.empty:
                    int_stat = df_int_stats[df_int_stats["client"].str.lower() == client_name.lower()].iloc[0] if len(df_int_stats[df_int_stats["client"].str.lower() == client_name.lower()]) > 0 else None
                
                # Calculate health score
                nb_eq = int(eq_stat.get("nb_eq", 0)) if eq_stat is not None else 0
                nb_hs = int(eq_stat.get("nb_hs", 0)) if eq_stat is not None else 0
                score_sante = max(0, round(((nb_eq - nb_hs) / nb_eq * 100))) if nb_eq > 0 else 100
                
                nb_int = int(int_stat.get("nb_int", 0)) if int_stat is not None else 0
                
                result.append({
                    "id": row.get("id"),
                    "nom": client_name,
                    "code_client": row.get("code_client", ""),
                    "matricule_fiscale": row.get("matricule_fiscale", ""),
                    "ville": row.get("ville", ""),
                    "region": row.get("region", ""),
                    "contact": row.get("contact", ""),
                    "telephone": row.get("telephone", ""),
                    "adresse": row.get("adresse", ""),
                    "type_client": row.get("type_client", ""),
                    "international": bool(row.get("international", False)),
                    "nb_equipements": nb_eq,
                    "nb_interventions": nb_int,
                    "score_sante": score_sante,
                })
            
            return result
    except Exception as e:
        logger.error(f"Erreur get_clients: {e}")
        return []


@app.get("/api/dashboard/equipment-types")
def get_dashboard_equipment_types(
    client: Optional[str] = None,
    region: Optional[str] = None,
    ville: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Get equipment types filtered by client, region, and ville."""
    try:
        df_eq = lire_equipements()
        df_clients = db_lire_clients()
        equipment_types = set()
        
        # Pour Lecteur : forcer le filtre par son client
        effective_client = _get_client_filter(user) or client

        # Filter equipements by client
        if effective_client and not df_eq.empty and "Client" in df_eq.columns:
            df_eq = df_eq[df_eq["Client"].astype(str).str.lower() == effective_client.lower()]

        # Filter equipements by region (join with clients table to get region)
        if region and not df_eq.empty and not df_clients.empty:
            if region.lower() == "international":
                # Get international clients
                clients_in_region = df_clients[
                    df_clients["international"].notna() & 
                    (df_clients["international"].astype(bool) == True)
                ]["nom"].tolist() if "international" in df_clients.columns else []
            else:
                # Get clients in this region
                clients_in_region = df_clients[
                    df_clients["region"].notna() & 
                    (df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip())
                ]["nom"].tolist() if "region" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_region and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_region)]

        # Filter equipements by ville (join with clients table to get ville)
        if ville and not df_eq.empty and not df_clients.empty:
            # Get clients in this ville
            clients_in_ville = df_clients[
                df_clients["ville"].notna() & 
                (df_clients["ville"].astype(str).str.lower().str.strip() == ville.lower().strip())
            ]["nom"].tolist() if "ville" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_ville and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_ville)]

        # Extract equipment types from filtered equipements
        if not df_eq.empty and "Type" in df_eq.columns:
            equipment_types.update(
                df_eq["Type"]
                .dropna()
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
            )
        
        # Return sorted list
        return sorted([t for t in equipment_types if t])
    except Exception as e:
        logger.error(f"Failed to get equipment types: {e}")
        return []


@app.get("/api/dashboard/regions")
def get_dashboard_regions(user: dict = Depends(_verify_token)):
    """Get all existing regions from clients table - ONLY the 4 main regions."""
    try:
        df_clients = db_lire_clients()
        regions = set()
        
        # List of valid regions
        VALID_REGIONS = {"sud", "centre", "nord"}
        
        if not df_clients.empty:
            # Add regular regions - ONLY if they match the 4 valid regions
            if "region" in df_clients.columns:
                client_regions = df_clients["region"].dropna().astype(str).str.strip().str.lower().unique().tolist()
                for r in client_regions:
                    if r in VALID_REGIONS:
                        regions.add(r.capitalize())  # Capitalize: sud → Sud
            
            # Add International if any client has international=True
            if "international" in df_clients.columns:
                if (df_clients["international"].astype(bool)).any():
                    regions.add("International")
        
        # Return sorted list - ONLY the 4 main regions
        return sorted(list(regions))
    except Exception as e:
        logger.error(f"Failed to get regions: {e}")
        return []


@app.get("/api/dashboard/villes")
def get_dashboard_villes(region: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Get all existing villes, optionally filtered by region."""
    try:
        df_clients = db_lire_clients()
        villes = set()
        
        if not df_clients.empty and region:
            # IMPORTANT: Only return villes when a region is specified
            # Filter by region
            if region.lower() == "international":
                # Get villes from international clients
                if "international" in df_clients.columns and "ville" in df_clients.columns:
                    international_clients = df_clients[
                        df_clients["international"].astype(bool) == True
                    ]
                    villes.update(
                        international_clients["ville"]
                        .dropna()
                        .astype(str)
                        .str.strip()
                        .unique()
                        .tolist()
                    )
            else:
                # Get villes from clients in this region
                if "region" in df_clients.columns and "ville" in df_clients.columns:
                    region_clients = df_clients[
                        df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip()
                    ]
                    villes.update(
                        region_clients["ville"]
                        .dropna()
                        .astype(str)
                        .str.strip()
                        .unique()
                        .tolist()
                    )
        
        # Return sorted list - ONLY villes, no regions
        return sorted([v for v in villes if v and v.lower() not in ["sud", "centre", "nord", "international"]])
    except Exception as e:
        logger.error(f"Failed to get villes: {e}")
        return []


@app.get("/api/dashboard/availability-trend")
def get_availability_trend(
    client: Optional[str] = None,
    region: Optional[str] = None,
    ville: Optional[str] = None,
    equipment_type: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Calculate real availability trend for the last 6 months based on interventions."""
    try:
        from datetime import datetime, timedelta
        import calendar
        
        df_eq = lire_equipements()
        df_int = lire_interventions()
        df_clients = db_lire_clients()
        
        # Apply same filters as KPI endpoint
        effective_client = _get_client_filter(user) or client
        
        # Filter equipements by client
        if effective_client and not df_eq.empty and "Client" in df_eq.columns:
            df_eq = df_eq[df_eq["Client"].astype(str).str.lower() == effective_client.lower()]
        
        # Filter equipements by region
        if region and not df_eq.empty and not df_clients.empty:
            if region.lower() == "international":
                clients_in_region = df_clients[
                    df_clients["international"].notna() & 
                    (df_clients["international"].astype(bool) == True)
                ]["nom"].tolist() if "international" in df_clients.columns else []
            else:
                clients_in_region = df_clients[
                    df_clients["region"].notna() & 
                    (df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip())
                ]["nom"].tolist() if "region" in df_clients.columns else []
            
            if clients_in_region and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_region)]
        
        # Filter equipements by ville
        if ville and not df_eq.empty and not df_clients.empty:
            clients_in_ville = df_clients[
                df_clients["ville"].notna() & 
                (df_clients["ville"].astype(str).str.lower().str.strip() == ville.lower().strip())
            ]["nom"].tolist() if "ville" in df_clients.columns else []
            
            if clients_in_ville and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_ville)]
        
        # Filter equipements by equipment type
        if equipment_type and not df_eq.empty and "Type" in df_eq.columns:
            df_eq = df_eq[df_eq["Type"].notna() & (df_eq["Type"].astype(str).str.lower().str.strip() == equipment_type.lower().strip())]
        
        nb_eq = len(df_eq) if not df_eq.empty else 0
        
        # If no equipment, return default data
        if nb_eq == 0:
            today = datetime.now()
            trend_data = []
            for i in range(5, -1, -1):
                month_date = today - timedelta(days=30*i)
                month_name = calendar.month_name[month_date.month][:3]
                trend_data.append({"mois": month_name, "dispo": 0})
            return {"ok": True, "trend": trend_data}
        
        # Get all machines for filtered equipements
        machines = df_eq["Nom"].tolist() if "Nom" in df_eq.columns else []
        
        # Filter interventions by machines
        if machines and not df_int.empty and "machine" in df_int.columns:
            df_int = df_int[df_int["machine"].isin(machines)]
        
        # Parse dates
        if not df_int.empty and "date" in df_int.columns:
            df_int["date"] = pd.to_datetime(df_int["date"], errors="coerce")
        
        # Calculate availability for each month
        today = datetime.now()
        trend_data = []
        
        for i in range(5, -1, -1):
            month_date = today - timedelta(days=30*i)
            month_name = calendar.month_name[month_date.month][:3]
            month_start = month_date.replace(day=1)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            
            # Count interventions in this month
            if not df_int.empty:
                month_int = df_int[(df_int["date"] >= month_start) & (df_int["date"] <= month_end)]
                nb_interventions = len(month_int)
            else:
                nb_interventions = 0
            
            # Calculate availability: assume 100% if no issues, decrease by 2% per intervention as rough estimate
            # More sophisticated: count "Terminée" status as available, others as not available
            availability = 100.0
            if not df_int.empty and nb_interventions > 0:
                # Count interventions that are NOT "Terminée" (corrective or in-progress)
                if "statut" in df_int.columns:
                    unfinished = len(month_int[month_int["statut"].astype(str).str.lower() != "terminée"])
                    # Rough estimate: each unfinished intervention reduces availability by 2%
                    availability = max(0, 100.0 - (unfinished * 2.0))
                else:
                    availability = max(0, 100.0 - (nb_interventions * 2.0))
            
            trend_data.append({"mois": month_name, "dispo": round(availability, 1)})
        
        return {"ok": True, "trend": trend_data}
    except Exception as e:
        import traceback
        logger.error(f"Erreur get_availability_trend: {e}\n{traceback.format_exc()}")
        # Return default trend data on error
        today = datetime.now()
        trend_data = []
        for i in range(5, -1, -1):
            month_date = today - timedelta(days=30*i)
            month_name = calendar.month_name[month_date.month][:3]
            trend_data.append({"mois": month_name, "dispo": 0})
        return {"ok": True, "trend": trend_data}


@app.get("/api/dashboard/clients-by-region")
def get_clients_by_region(region: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Get all clients, optionally filtered by region."""
    try:
        df_clients = db_lire_clients()
        clients = set()
        
        if not df_clients.empty and "nom" in df_clients.columns:
            if region:
                # Filter by region
                if region.lower() == "international":
                    # Get international clients
                    if "international" in df_clients.columns:
                        international_clients = df_clients[
                            df_clients["international"].astype(bool) == True
                        ]
                        clients.update(
                            international_clients["nom"]
                            .dropna()
                            .astype(str)
                            .str.strip()
                            .unique()
                            .tolist()
                        )
                else:
                    # Get clients in this region
                    if "region" in df_clients.columns:
                        region_clients = df_clients[
                            df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip()
                        ]
                        clients.update(
                            region_clients["nom"]
                            .dropna()
                            .astype(str)
                            .str.strip()
                            .unique()
                            .tolist()
                        )
            else:
                # Get all clients
                clients.update(
                    df_clients["nom"]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .unique()
                    .tolist()
                )
        
        # Return sorted list
        return sorted([c for c in clients if c])
    except Exception as e:
        logger.error(f"Failed to get clients by region: {e}")
        return []


@app.post("/api/clients")
def create_client(body: dict, user: dict = Depends(_verify_token)):
    """Create a new client."""
    # Check permission
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins"
        )
    
    ajouter_client(body)
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({"client": body.get("nom", "")}, ensure_ascii=False)
    log_audit(username, "CREATE_CLIENT", details, "clients")
    
    return {"ok": True}


@app.post("/api/clients/import-excel")
async def import_clients_excel(file: UploadFile = File(...), user: dict = Depends(_verify_token)):
    """Import clients from an Excel or CSV file with auto-detection of columns."""
    # Check permission
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins"
        )
    
    import io
    try:
        content = await file.read()
        
        # Determine file type
        filename = file.filename.lower()
        is_csv = filename.endswith('.csv')
        
        # Read file
        try:
            if is_csv:
                # For CSV files, use StringIO
                text_content = content.decode('utf-8')
                df = pd.read_csv(io.StringIO(text_content))
            else:
                # For Excel files
                try:
                    df = pd.read_excel(io.BytesIO(content), engine="openpyxl")
                except Exception:
                    df = pd.read_excel(io.BytesIO(content))
        except Exception as e:
            logger.error(f"File read error: {e}")
            return {"ok": False, "error": f"Erreur lecture fichier: {str(e)}", "imported": 0, "skipped": 0}

        if df.empty:
            return {"ok": False, "error": "Le fichier est vide", "imported": 0, "skipped": 0}

        # Column name mapping (lowercase, stripped)
        COLUMN_MAP = {
            "nom": ["nom", "name", "client", "raison_sociale", "raison sociale", "société", "societe", "company"],
            "code_client": ["code_client", "code client", "code", "ref", "reference", "référence", "ref_client"],
            "matricule_fiscale": ["matricule_fiscale", "matricule fiscale", "matricule", "mf", "tax_id", "identifiant fiscal"],
            "ville": ["ville", "city", "localité", "localite"],
            "region": ["region", "région", "zone", "gouvernorat"],
            "contact": ["contact", "contact_name", "responsable", "interlocuteur", "nom_contact", "nom contact"],
            "telephone": ["telephone", "tel", "phone", "téléphone", "tel_contact", "numéro"],
            "adresse": ["adresse", "address", "adr", "siege", "siège"],
            "type_client": ["type_client", "type client", "type", "secteur", "nature", "privé/public"],
            "international": ["international", "intl", "étranger", "etranger", "pays_etranger"],
        }

        # Auto-detect column mapping
        detected = {}
        excel_cols = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        original_cols = list(df.columns)

        for field, variants in COLUMN_MAP.items():
            for i, col_lower in enumerate(excel_cols):
                # Also check without underscores/spaces
                col_clean = col_lower.replace("_", "").replace(" ", "")
                for variant in variants:
                    variant_clean = variant.replace("_", "").replace(" ", "")
                    if col_lower == variant or col_clean == variant_clean:
                        detected[field] = original_cols[i]
                        break
                if field in detected:
                    break

        columns_detected = list(detected.keys())
        imported = 0
        skipped = 0

        for _, row in df.iterrows():
            client_dict = {}
            for field, excel_col in detected.items():
                val = row.get(excel_col, "")
                if pd.isna(val):
                    val = ""
                if field == "international":
                    val = str(val).strip().lower() in ("true", "1", "oui", "yes", "vrai", "o")
                else:
                    val = str(val).strip()
                client_dict[field] = val

            # Skip if no name
            nom = client_dict.get("nom", "").strip()
            if not nom:
                skipped += 1
                continue

            try:
                ajouter_client(client_dict)
                imported += 1
            except Exception as e:
                logger.warning(f"Import client skip '{nom}': {e}")
                skipped += 1

        # Log audit
        username = user.get("sub", "unknown")
        log_audit(username, "IMPORT_CLIENTS", f"{{\"imported\": {imported}, \"skipped\": {skipped}}}", "clients")

        return {
            "ok": True,
            "imported": imported,
            "skipped": skipped,
            "columns_detected": columns_detected,
            "total_rows": len(df),
        }
    except Exception as e:
        logger.error(f"Excel import error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/clients/{client_id}")
def update_client_api(client_id: int, body: dict, user: dict = Depends(_verify_token)):
    """Update an existing client."""
    modifier_client(client_id, body)
    return {"ok": True}


@app.delete("/api/clients/{client_id}")
def delete_client_api(client_id: int, user: dict = Depends(_verify_token)):
    """Delete a client."""
    supprimer_client(client_id)
    return {"ok": True}


# ==========================================
# LOGS / S3 MANAGEMENT
# ==========================================

try:
    import s3_storage
except ImportError:
    s3_storage = None


@app.delete("/api/logs")
def api_delete_log(key: str = Query(..., description="S3 key of the log to delete"), user=Depends(_verify_token)):
    """Delete a specific log file from S3 by its key."""
    if not s3_storage:
        raise HTTPException(status_code=503, detail="S3 storage not available")
    s3_storage._init_s3()
    if not s3_storage.S3_AVAILABLE:
        raise HTTPException(status_code=503, detail="S3 storage not connected")

    success = s3_storage.delete_file(key)
    if success:
        return {"ok": True, "message": f"Log supprimé: {key}"}
    raise HTTPException(status_code=500, detail="Échec de la suppression du log")


@app.delete("/api/logs/machine/{machine_name}")
def api_delete_machine_logs(machine_name: str, user=Depends(_verify_token)):
    """Delete ALL log files for a given machine from S3."""
    if not s3_storage:
        raise HTTPException(status_code=503, detail="S3 storage not available")
    s3_storage._init_s3()
    if not s3_storage.S3_AVAILABLE:
        raise HTTPException(status_code=503, detail="S3 storage not connected")

    # Find all logs matching this machine
    all_files = s3_storage.list_files("logs/")
    machine_key = machine_name.replace(' ', '_')
    to_delete = [f for f in all_files if f"/{machine_key}/" in f["key"] or machine_key in f["key"]]

    deleted = 0
    for f in to_delete:
        if s3_storage.delete_file(f["key"]):
            deleted += 1

    return {"ok": True, "deleted": deleted, "message": f"{deleted} log(s) supprimé(s) pour {machine_name}"}




# ==========================================
# PDF REPORT GENERATION (server-side fpdf2)
# ==========================================

def _sanitize(text):
    if not text:
        return ""
    text = str(text)
    # Replace specific chars with ASCII equivalents
    text = text.replace(chr(0x2014), " - ")  # em dash
    text = text.replace(chr(0x2013), " - ")  # en dash
    text = text.replace(chr(0x202F), " ")     # narrow no-break space
    text = text.replace(chr(0x00A0), " ")     # no-break space
    text = text.replace(chr(0x2022), "-")     # bullet
    text = text.replace(chr(0x2019), "'")    # right single quote
    text = text.replace(chr(0x2018), "'")    # left single quote
    text = text.replace(chr(0x201C), '"')    # left double quote
    text = text.replace(chr(0x201D), '"')    # right double quote
    text = text.replace(chr(0x2026), "...")   # ellipsis
    text = text.replace(chr(0x20AC), "EUR")   # euro sign
    # Final fallback: encode to Latin-1, unknown chars become ?
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _fmt_number(n):
    try:
        val = int(round(float(n)))
        s = str(abs(val))
        result = ""
        for i, c in enumerate(reversed(s)):
            if i > 0 and i % 3 == 0:
                result = " " + result
            result = c + result
        return ("-" if val < 0 else "") + result
    except Exception:
        return str(n)


class SaviaPDF(FPDF):
    """FPDF subclass with auto-repeated compact header on every page."""
    _savia_logo   = None    # path
    _client_logo  = None    # BytesIO (seekable)
    _company_name = ''
    _company_sub  = ''
    _report_title = ''     # centered between logos
    HEADER_H = 26           # header height mm

    def header(self):
        from io import BytesIO
        H = self.HEADER_H
        y0 = 5
        W  = self.w - 16   # 8mm each side

        # ── SAVIA logo (left) ──────────────────────────────────────
        savia_w = 0
        if self._savia_logo and os.path.exists(self._savia_logo):
            try:
                logo_h = (H - 4) * 0.28
                self.image(self._savia_logo, x=8, y=y0 + (H - 4 - logo_h) / 2, h=logo_h)
                savia_w = 8
            except Exception:
                savia_w = 0

        # ── Client logo (right) ───────────────────────────────────
        client_w = 0
        if self._client_logo:
            try:
                self._client_logo.seek(0)
                self.image(self._client_logo, x=self.w - 8 - 28, y=y0, h=H - 4)
                client_w = 30
            except Exception:
                client_w = 0

        # ── Center zone: report title + company name ───────────────
        cx = 8 + savia_w + 2
        cw = W - savia_w - client_w - 4

        # Report title (top, bold, centered between logos)
        if self._report_title:
            self.set_xy(cx, y0 + 1)
            self.set_font('Helvetica', 'B', 11)
            self.set_text_color(30, 40, 55)
            self.cell(cw, 7, _sanitize(self._report_title[:70]), align='C')

        # Company name (below title, smaller)
        if self._company_name:
            y_cn = y0 + 9 if self._report_title else y0 + 4
            self.set_xy(cx, y_cn)
            self.set_font('Helvetica', 'B', 9)
            self.set_text_color(1, 180, 188)
            self.cell(cw, 6, _sanitize(self._company_name[:55]), align='C')
            if self._company_sub:
                self.set_xy(cx, y_cn + 6)
                self.set_font('Helvetica', '', 7)
                self.set_text_color(130, 145, 160)
                self.cell(cw, 4.5, _sanitize(self._company_sub[:90]), align='C')

        # ── Separator line ─────────────────────────────────────────
        sep = y0 + H
        self.set_fill_color(1, 180, 188)
        self.rect(8, sep, self.w - 16, 0.8, style='F')
        self.set_y(sep + 3)
        self.set_text_color(40, 50, 65)

    def set_header_data(self, savia_logo, client_logo_bytes, company_name, company_sub, report_title=""):
        self._savia_logo   = savia_logo
        self._client_logo  = client_logo_bytes
        self._company_name = company_name
        self._company_sub  = company_sub
        self._report_title = report_title



class PdfRequest(BaseModel):
    title: str = "Rapport SAVIA"
    subtitle: str = ""
    filename: str = "rapport"
    company_name: str = "SAVIA"
    company_logo: str = ""
    kpis: list = []
    head: list = []
    rows: list = []
    tables: list = []  # List of {title, head, rows} dicts
    type_data: list = []
    table_title: str = ""
    is_ai_report: bool = False
    ai_content: str = ""


@app.post("/api/reports/generate-pdf")
def generate_pdf_report(data: PdfRequest, user: dict = Depends(_verify_token)):
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    from io import BytesIO
    from fastapi.responses import Response
    import json

    SAVIA_LOGO = "/app/logo-savia.png"
    try:
        from io import BytesIO as _BytesIO
        import base64 as _b64
        import urllib.request as _ur

        orientation = "P" if data.is_ai_report else "L"
        pdf = SaviaPDF(orientation=orientation, unit="mm", format="A4")

        # ── Resolve client logo (URL or base64) ──────────────
        _client_logo_io = None
        if data.company_logo:
            try:
                clogo = data.company_logo.strip()
                if clogo.startswith("data:"):
                    _b64_part = clogo.split(",", 1)[1] if "," in clogo else clogo
                    _client_logo_io = _BytesIO(_b64.b64decode(_b64_part))
                elif clogo.startswith("http"):
                    req_ = _ur.Request(clogo, headers={"User-Agent": "Mozilla/5.0"})
                    with _ur.urlopen(req_, timeout=6) as _r:
                        _client_logo_io = _BytesIO(_r.read())
            except Exception as _e:
                logger.warning(f"Client logo error: {_e}")

        pdf.set_header_data(
            SAVIA_LOGO, _client_logo_io,
            data.company_name if data.company_name != "SAVIA" else "",
            "Systeme Intelligent de Controle et de Gestion",  # Always fixed - footer has date/name
            report_title=data.title if data.title and data.title != "Rapport SAVIA" else ""
        )
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_top_margin(pdf.HEADER_H + 10)  # content starts below header
        pdf.add_page()
        page_w = pdf.w

        # Title is now shown in header (between logos)


        # KPIs
        if data.kpis:
            box_w, box_h, margin_ = 64, 16, 5
            kpi_y = pdf.get_y()
            # Centrer les KPIs au milieu de la page
            num_kpis = len(data.kpis[:4])
            total_width = num_kpis * box_w + (num_kpis - 1) * margin_
            start_x = (pdf.w - total_width) / 2  # Centrer horizontalement
            
            for i, kpi in enumerate(data.kpis[:4]):
                kx = start_x + i * (box_w + margin_)
                color = kpi.get("color", [15, 118, 110])
                # Support both hex string "#RRGGBB" and [r,g,b] list
                if isinstance(color, str) and color.startswith("#") and len(color) >= 7:
                    h = color.lstrip("#")
                    r1,g1,b1 = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
                elif isinstance(color, (list,tuple)) and len(color) >= 3:
                    r1,g1,b1 = int(color[0]),int(color[1]),int(color[2])
                else:
                    r1,g1,b1 = 15,118,110
                lc = [min(r1+215,255), min(g1+215,255), min(b1+215,255)]
                pdf.set_fill_color(*lc)
                pdf.set_draw_color(r1,g1,b1)
                pdf.set_line_width(0.4)
                pdf.rect(kx, kpi_y, box_w, box_h, style="FD")
                # Top accent bar (Dopely palette solid)
                pdf.set_fill_color(r1,g1,b1)
                pdf.rect(kx, kpi_y, box_w, 3, style="F")
                # Small white round dot on top bar
                pdf.set_fill_color(255, 255, 255)
                pdf.ellipse(kx + box_w/2 - 1.5, kpi_y + 0.3, 3, 2.4, style="F")
                # Value
                pdf.set_xy(kx, kpi_y + 3)
                pdf.set_font("Helvetica", "B", 13)
                vr = max(30, min(r1-30, 180)); vg = max(30, min(g1-20, 120)); vb = max(30, min(b1-20, 150))
                pdf.set_text_color(vr, vg, vb)
                pdf.cell(box_w, 8, _sanitize(str(kpi.get("val", ""))), align="C")
                # Label
                pdf.set_xy(kx, kpi_y + 11)
                pdf.set_font("Helvetica", "", 6.5)
                pdf.set_text_color(90, 100, 115)
                pdf.cell(box_w, 4, _sanitize(str(kpi.get("label", ""))), align="C")
            pdf.set_y(kpi_y + box_h + 6)
            pdf.set_text_color(0, 0, 0)

        # Type distribution table
        if data.type_data:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(50, 70, 90)
            pdf.cell(0, 6, "Repartition par type", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_draw_color(1, 180, 188)
            pdf.set_fill_color(1, 180, 188)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(100, 7, "Type", border=1, fill=True)
            pdf.cell(30, 7, "Nombre", border=1, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 8)
            for idx, row in enumerate(data.type_data):
                fill = idx % 2 == 0
                if fill: pdf.set_fill_color(225, 250, 251)
                else: pdf.set_fill_color(255, 255, 255)
                pdf.set_text_color(30, 40, 60)
                pdf.cell(100, 6, _sanitize(str(row[0])) if row else "", border=1, fill=fill)
                pdf.cell(30, 6, str(row[1]) if len(row) > 1 else "", border=1, fill=fill, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)

        # AI Report mode - WEB UI STYLE (colored text headers + Unicode symbols)
        if data.is_ai_report and data.ai_content:
            try: ai = json.loads(data.ai_content)
            except Exception: ai = {'summary': data.ai_content}

            W = page_w - 20

            # Load DejaVu for Unicode bullet symbols
            _DJVU = '/app/DejaVuSans.ttf'
            _has_djvu = os.path.exists(_DJVU)
            if _has_djvu:
                try: pdf.add_font('DejaVu', fname=_DJVU)
                except Exception: _has_djvu = False

            # Font Awesome icons (requires fonttools space-glyph fix)
            _FA = '/app/fa-solid-900.ttf'
            # NOTE: FA TTF converted from WOFF2 lacks 'space' glyph
            # fpdf2 crashes on output() -> disabled, using test + fallback
            _has_fa = False
            if os.path.exists(_FA):
                try:
                    pdf.add_font('FA', fname=_FA)
                    from fpdf import FPDF as _FPDF_TEST
                    _pt = _FPDF_TEST(); _pt.add_page()
                    _pt.add_font('FA', fname=_FA); _pt.set_font('FA', size=10)
                    _pt.cell(10, 10, chr(0xF164))
                    bytes(_pt.output())  # test that it works
                    _has_fa = True
                except Exception as _efa:
                    _has_fa = False
                    logger.debug(f"FA font disabled: {_efa}")

            def _sym(size=8):
                if _has_djvu:
                    try: pdf.set_font('DejaVu', size=size); return True
                    except: pass
                pdf.set_font('Helvetica', size=size); return False

            def _hel(style='', size=8.5):
                pdf.set_font('Helvetica', style, size)

            # FA section icon codes (matches Lucide React)
            FA = {
                'resume':   chr(0xf080),  # bar-chart (BarChart3)
                'strong':   chr(0xf164),  # thumbs-up (ThumbsUp)
                'weak':     chr(0xf165),  # thumbs-down (ThumbsDown)
                'reco':     chr(0xf0eb),  # lightbulb (Lightbulb)
                'alert':    chr(0xf071),  # triangle-exclamation (AlertTriangle)
                'trend':    chr(0xf201),  # chart-line (TrendingUp)
                'team':     chr(0xf0c0),  # users (Users)
                'cost':     chr(0xf155),  # dollar-sign (DollarSign)
                'priority': chr(0xf0e7),  # bolt (Zap)
                'done':     chr(0xf058),  # circle-check (CheckCircle2)
                'score':    chr(0xf201),  # chart-line (BarChart2)
            }

            def sec_hdr(lbl, bg, fa_key=None):
                # Web-style: white bg, FA icon + colored bold title, thin underline
                if pdf.get_y() > pdf.h - 45: pdf.add_page()
                yh = pdf.get_y() + 2
                R_, G_, B_ = bg
                # Font Awesome icon before title
                if fa_key and _has_fa and fa_key in FA:
                    pdf.set_xy(10, yh - 0.5)
                    pdf.set_font('FA', size=9)
                    pdf.set_text_color(R_, G_, B_)
                    pdf.cell(7, 6, FA[fa_key])
                    pdf.set_xy(18, yh)
                else:
                    # Fallback: colored rect
                    pdf.set_fill_color(R_, G_, B_)
                    pdf.rect(10, yh, 3, 5.5, style='F')
                    pdf.set_xy(15, yh)
                # Colored bold title
                _hel('B', 10)
                pdf.set_text_color(R_, G_, B_)
                pdf.cell(W - 8, 5.5, _sanitize(lbl))
                # Thin underline
                pdf.set_draw_color(R_, G_, B_)
                pdf.set_line_width(0.4)
                pdf.line(10, yh + 7, page_w - 10, yh + 7)
                pdf.set_y(yh + 10)
                pdf.set_text_color(40, 50, 65)

            def body_item(txt, bg, sym='\u25cf'):
                if not txt: return
                if pdf.get_y() > pdf.h - 20: pdf.add_page()
                yi = pdf.get_y()
                R_, G_, B_ = bg
                if _has_djvu:
                    _sym(8)
                    pdf.set_text_color(R_, G_, B_)
                    pdf.set_xy(13, yi)
                    pdf.cell(5, 4.8, sym)
                else:
                    pdf.set_fill_color(R_, G_, B_)
                    pdf.ellipse(13.5, yi + 2.0, 2.5, 2.5, style='F')
                _hel('', 8.5)
                pdf.set_text_color(40, 50, 65)
                pdf.set_xy(19, yi)
                pdf.multi_cell(W - 10, 4.8, _sanitize(str(txt)[:300]))
                pdf.ln(0.5)

            def add_sec(lbl, items, bg, sym='\u25cf', fa_key=None):
                if not items: return
                sec_hdr(lbl, bg, fa_key)
                _hel('', 8.5)
                for it in items:
                    txt = it if isinstance(it, str) else it.get('action', it.get('machine', str(it))) if isinstance(it, dict) else str(it)
                    body_item(txt, bg, sym)
                pdf.ln(4)

            # Score global
            score = ai.get('score_global')
            if score is not None:
                sc = int(score)
                if sc >= 70:   s_bg = [95,165,90]
                elif sc >= 40: s_bg = [250,137,37]
                else:          s_bg = [250,84,87]
                y_sc = pdf.get_y()
                pdf.set_fill_color(255, 255, 255)
                pdf.set_draw_color(s_bg[0], s_bg[1], s_bg[2])
                pdf.set_line_width(0.8)
                pdf.rect(10, y_sc, W, 16, style='FD')
                pdf.set_fill_color(s_bg[0], s_bg[1], s_bg[2])
                pdf.rect(10, y_sc, 5, 16, style='F')
                pdf.set_xy(18, y_sc + 1.5)
                _hel('B', 15)
                pdf.set_text_color(s_bg[0], s_bg[1], s_bg[2])
                pdf.cell(25, 9, str(sc))
                pdf.set_xy(36, y_sc + 2)
                _hel('B', 9)
                slabel = 'Excellent' if sc>=70 else 'Satisfaisant' if sc>=40 else 'A ameliorer'
                pdf.set_text_color(s_bg[0], s_bg[1], s_bg[2])
                pdf.cell(50, 5.5, slabel)
                pdf.set_xy(36, y_sc + 8.5)
                _hel('', 7)
                pdf.set_text_color(130, 145, 160)
                pdf.cell(W - 28, 4, '/100 - Score global de performance')
                pdf.set_y(y_sc + 19)

            # Resume Executif - ORANGE #FA8925
            analyse = ai.get('analyse') or ai.get('summary')
            if analyse:
                sec_hdr('RESUME EXECUTIF', [250,137,37], 'resume')
                _hel('', 8.5)
                pdf.set_text_color(40, 50, 65)
                pdf.set_x(13)
                pdf.multi_cell(W - 3, 5, _sanitize(str(analyse)[:2500]))
                pdf.ln(5)

            # Points Forts - GREEN + CHECK
            add_sec('POINTS FORTS',     ai.get('points_forts', []),    [95,165,90],  '\u2713', 'strong')
            # Points Faibles - CORAL + TRIANGLE
            add_sec('POINTS FAIBLES',   ai.get('points_faibles', []),  [250,84,87],  '\u25b3', 'weak')
            # Recommandations - TEAL + ARROW
            recs = ai.get('recommandations', [])
            recs_c = [r if isinstance(r, str) else r.get('action', str(r)) for r in recs]
            add_sec('RECOMMANDATIONS',  recs_c,                        [1,180,188],  '\u2192', 'reco')
            # Alertes - CORAL + WARNING
            add_sec('ALERTES CRITIQUES',ai.get('alertes_critiques',[]),[250,84,87],  '\u26a0', 'alert')
            # Tendances - TEAL + UP-ARROW
            add_sec('TENDANCES',        ai.get('tendances', []),       [1,180,188],  '\u2197', 'trend')

            # Performance Equipe - AMBER
            perf = ai.get('performance_equipe', [])
            if perf:
                sec_hdr('EVALUATION DE L\'EQUIPE', [155,110,5], 'team')
                _hel('', 8.5)
                for pe in perf:
                    if isinstance(pe, dict):
                        nm_ = pe.get('technicien', pe.get('nom', ''))
                        sc_ = pe.get('score', pe.get('note', ''))
                        dt_ = pe.get('detail', pe.get('commentaire', ''))
                        body_item(_sanitize(str(nm_))+' : '+str(sc_)+(' - '+str(dt_) if dt_ else ''), [155,110,5], '\u25cf')
                    else: body_item(str(pe), [155,110,5], '\u25cf')
                pdf.ln(4)

            # Analyse Financiere - ORANGE
            couts = ai.get('analyse_couts')
            if couts and isinstance(couts, dict):
                sec_hdr('ANALYSE DES COUTS', [250,137,37], 'cost')
                _hel('', 8.5)
                for k_, v_ in couts.items():
                    if v_: body_item(str(k_)+' : '+str(v_), [250,137,37], '\u25cf')
                pdf.ln(4)

            # Priorites - ORANGE + LIGHTNING
            add_sec('PRIORITES IMMEDIATES', ai.get('priorites_immediates',[]),[250,137,37],'\u26a1', 'priority')

            # Conclusion - TEAL
            conclusion = ai.get('conclusion')
            if conclusion:
                sec_hdr('CONCLUSION', [1,180,188], 'done')
                _hel('', 9)
                pdf.set_text_color(50, 62, 78)
                pdf.set_x(13)
                pdf.multi_cell(W - 3, 5, _sanitize(str(conclusion)[:2500]))

        # ── Multi-table support (tables: [{title, head, rows}]) ──────
        if data.tables:
            def _render_table(tbl_head, tbl_rows, tbl_title=""):
                if not tbl_head: return
                if pdf.get_y() > pdf.h - 45: pdf.add_page()
                if tbl_title:
                    pdf.ln(3)
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.set_text_color(1, 180, 188)
                    pdf.cell(0, 7, _sanitize(str(tbl_title)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                n_cols = len(tbl_head)
                total_w = page_w - 20
                # Smart column width distribution
                if n_cols == 2:
                    col_w = [total_w * 0.38, total_w * 0.62]
                elif n_cols == 7:
                    # Optimized for SAV: Date(12%), Machine(18%), Client(18%), Technicien(18%), Type(12%), Statut(12%), Durée(10%)
                    col_w = [total_w * p for p in [0.12, 0.18, 0.18, 0.18, 0.12, 0.12, 0.10]]
                else:
                    col_w = [total_w / n_cols] * n_cols
                # Header row
                pdf.set_font("Helvetica", "B", 7.5)
                pdf.set_draw_color(1, 180, 188)
                pdf.set_fill_color(1, 180, 188)
                pdf.set_text_color(255, 255, 255)
                for i, h in enumerate(tbl_head):
                    pdf.cell(col_w[i], 8, _sanitize(str(h)[:20]), border=1, fill=True, align="C")
                pdf.ln()
                # Data rows
                pdf.set_font("Helvetica", "", 7.5)
                for row_idx, row in enumerate(tbl_rows):
                    if pdf.get_y() > pdf.h - 15:
                        pdf.add_page()
                        pdf.set_font("Helvetica", "B", 7.5)
                        pdf.set_fill_color(1, 180, 188)
                        pdf.set_text_color(255, 255, 255)
                        for i, h in enumerate(tbl_head):
                            pdf.cell(col_w[i], 8, _sanitize(str(h)[:20]), border=1, fill=True, align="C")
                        pdf.ln()
                        pdf.set_font("Helvetica", "", 7.5)
                    fill = row_idx % 2 == 0
                    pdf.set_fill_color(244, 252, 251) if fill else pdf.set_fill_color(255, 255, 255)
                    pdf.set_text_color(25, 35, 55)
                    for i, cell in enumerate(row[:n_cols]):
                        # Dynamically truncate based on column width (~2.5mm per char at 7.5pt)
                        max_chars = max(5, int(col_w[i] / 2.3))
                        raw = str(cell) if cell is not None else "-"
                        val_s = _sanitize(raw[:max_chars])
                        align = "C" if i >= n_cols - 3 else "L"
                        pdf.cell(col_w[i], 6.5, val_s, border=1, fill=fill, align=align)
                    pdf.ln()
                pdf.ln(4)

            for tbl in data.tables:
                if isinstance(tbl, dict):
                    _render_table(tbl.get("head",[]), tbl.get("rows",[]), tbl.get("title",""))

        # Standard table (legacy: head + rows directly on request)
        elif data.head and data.rows:
            if pdf.get_y() > pdf.h - 45: pdf.add_page()
            if data.table_title:
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(50, 70, 90)
                pdf.cell(0, 7, _sanitize(data.table_title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            n_cols = len(data.head)
            total_w = page_w - 20
            # Equal distribution: each column gets the same width
            # Exception: 2-col tables use 38%/62% (label/value)
            if n_cols == 2:
                col_w = [total_w * 0.38, total_w * 0.62]
            else:
                col_w = [total_w / n_cols] * n_cols
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_draw_color(1, 180, 188)
            pdf.set_fill_color(1, 180, 188)
            pdf.set_text_color(255, 255, 255)
            for i, h in enumerate(data.head):
                pdf.cell(col_w[i], 8, _sanitize(str(h)[:20]), border=1, fill=True, align="C")
            pdf.ln()
            pdf.set_font("Helvetica", "", 7.5)
            for row_idx, row in enumerate(data.rows):
                if pdf.get_y() > pdf.h - 15:
                    pdf.add_page()
                    pdf.set_font("Helvetica", "B", 8)
                    pdf.set_fill_color(15, 118, 110)
                    pdf.set_text_color(255, 255, 255)
                    for i, h in enumerate(data.head):
                        pdf.cell(col_w[i], 8, _sanitize(str(h)[:20]), border=1, fill=True, align="C")
                    pdf.ln()
                    pdf.set_font("Helvetica", "", 7.5)
                fill = row_idx % 2 == 0
                if fill: pdf.set_fill_color(244, 252, 251)
                else: pdf.set_fill_color(255, 255, 255)
                pdf.set_text_color(25, 35, 55)
                for i, cell in enumerate(row[:n_cols]):
                    val = _sanitize(_fmt_number(cell)) if i == n_cols - 1 else _sanitize(str(cell)[:25]) if cell else "-"
                    align = "R" if i == n_cols - 1 else "L"
                    pdf.cell(col_w[i], 6.5, val, border=1, fill=fill, align=align)
                pdf.ln()

        # ── CRITICAL: disable auto-page-break before footer loop ──────────────
        # cell() at y=h-10=287mm exceeds auto-break threshold (h-15=282mm)
        # → triggers unwanted new page with "Genere par" at top
        pdf.set_auto_page_break(auto=False)

        # Also remove last page if only header drawn (extra safety)
        try:
            _EMPTY_THRESHOLD = 46
            _last_y = pdf.get_y()
            _n_pages = len(pdf.pages)
            logger.info(f"PDF: {_n_pages} pages, last_y={_last_y:.1f}mm")
            if _last_y <= _EMPTY_THRESHOLD and _n_pages > 1:
                _last_pg = max(pdf.pages.keys())
                del pdf.pages[_last_pg]
                pdf.page = _last_pg - 1
                logger.info(f"Removed empty last page #{_last_pg}")
        except Exception as _ep:
            logger.warning(f"Empty page removal: {_ep}")

        # Footer on all pages (auto-break already disabled above)
        total_pages = len(pdf.pages)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        for pg in range(1, total_pages + 1):
            pdf.page = pg
            pdf.set_xy(10, pdf.h - 11)
            pdf.set_draw_color(200, 205, 220)
            pdf.set_line_width(0.3)
            pdf.line(10, pdf.h - 11, page_w - 10, pdf.h - 11)
            pdf.set_xy(10, pdf.h - 9)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(160, 170, 190)
            pdf.cell(page_w - 40, 5, _sanitize(f"Genere par {data.company_name} - {now_str}"), align="L")
            pdf.cell(30, 5, f"Page {pg} / {total_pages}", align="R")

        pdf_bytes = bytes(pdf.output()
        )
        # Sanitize filename for HTTP headers (latin-1 only)
        import urllib.parse as _up, unicodedata as _ud
        _fn = str(data.filename or "rapport")
        _ascii = _ud.normalize("NFKD", _fn).encode("ascii","ignore").decode()
        _ascii = "".join(c if c.isalnum() or c in "._-" else "_" for c in _ascii).strip("_") or "rapport"
        _utf8  = _up.quote(_fn + ".pdf", safe="")
        _cd = "attachment; filename=" + _ascii + ".pdf; filename*=UTF-8''" + _utf8
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": _cd,
                "Content-Length": str(len(pdf_bytes)),
            }
        )
    except Exception as e:
        logging.error(f"PDF generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

# ==========================================
# PDF FICHE INTERVENTION (server-side fpdf2)
# ==========================================

@app.post("/api/interventions/{interv_id}/fiche-pdf")
def generate_fiche_intervention_pdf(interv_id: int, body: dict = {}, user: dict = Depends(_verify_token)):
    """Generate a professional intervention fiche PDF with all details, logos, and signature areas.
    
    For multi-technician interventions, includes a table with one row per technician.
    """
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
    from io import BytesIO
    from fastapi.responses import Response
    import base64 as _b64
    import urllib.request as _ur
    from db_engine import get_interventions_techniciens

    SAVIA_LOGO = "/app/logo-savia.png"

    try:
        # Fetch intervention data
        df_interv = lire_interventions()
        interv = None
        if not df_interv.empty:
            match = df_interv[df_interv["id"] == interv_id]
            if not match.empty:
                interv = match.iloc[0].to_dict()
        if not interv:
            raise HTTPException(status_code=404, detail="Intervention non trouvee")

        # Check if multi-technician intervention (has comma-separated techniciens)
        technicien_str = str(interv.get("technicien", "")).strip()
        technicians = [t.strip() for t in technicien_str.split(",") if t.strip()]
        is_multi_tech = len(technicians) > 1
        
        # Load technician records if multi-tech
        tech_records = []
        if is_multi_tech:
            try:
                tech_records = get_interventions_techniciens(interv_id)
            except Exception as e:
                logger.debug(f"Could not load tech records: {e}")
                tech_records = []

        # Fetch equipment to determine warranty and serial number
        df_equip = lire_equipements()
        matched_equip = None
        if not df_equip.empty and "Nom" in df_equip.columns:
            machine_name = str(interv.get("machine", "")).strip()
            if machine_name:
                exact = df_equip[df_equip["Nom"].str.strip() == machine_name]
                if not exact.empty:
                    matched_equip = exact.iloc[0].to_dict()
                else:
                    partial = df_equip[df_equip["Nom"].str.contains(machine_name, case=False, na=False)]
                    if not partial.empty:
                        matched_equip = partial.iloc[0].to_dict()

        # Warranty check
        sous_garantie = False
        if matched_equip:
            g_debut = matched_equip.get("garantie_debut", "")
            g_duree = int(matched_equip.get("garantie_duree", 0) or 0)
            if g_debut and g_duree:
                try:
                    fin = datetime.strptime(str(g_debut)[:10], "%Y-%m-%d")
                    fin = fin.replace(year=fin.year + g_duree)
                    sous_garantie = fin > datetime.now()
                except Exception:
                    pass

        # Contract check
        sous_contrat = False
        client_name = str(interv.get("client", "")).strip()
        if client_name:
            df_contrats = lire_contrats()
            if not df_contrats.empty:
                client_col = "client" if "client" in df_contrats.columns else "Client"
                if client_col in df_contrats.columns:
                    client_contracts = df_contrats[df_contrats[client_col].str.strip().str.lower() == client_name.lower()]
                    if not client_contracts.empty:
                        for _, c in client_contracts.iterrows():
                            fin_str = c.get("date_fin", c.get("DateFin", ""))
                            if not fin_str:
                                sous_contrat = True
                                break
                            try:
                                if datetime.strptime(str(fin_str)[:10], "%Y-%m-%d") > datetime.now():
                                    sous_contrat = True
                                    break
                            except Exception:
                                sous_contrat = True
                                break

        # Extract fields
        num_serie = (matched_equip or {}).get("NumSerie", "") or (matched_equip or {}).get("num_serie", "") or "-"
        equip_type = (matched_equip or {}).get("Type", "") or (matched_equip or {}).get("type", "") or str(interv.get("type_intervention", "-"))
        duree_min = int(interv.get("duree_minutes", 0) or 0)
        duree_h = round(duree_min / 60, 2) if duree_min else 0
        deplacement_min = int(interv.get("duree_deplacement", 0) or 0)
        deplacement_h = round(deplacement_min / 60, 2) if deplacement_min else 0

        # Fetch client region/ville
        client_region = ""
        client_ville = ""
        if client_name:
            try:
                with get_db() as conn:
                    cl_row = conn.execute("SELECT region, ville FROM clients WHERE nom = ? LIMIT 1", (client_name,)).fetchone()
                    if cl_row:
                        client_region = dict(cl_row).get("region", "") or ""
                        client_ville = dict(cl_row).get("ville", "") or ""
            except Exception:
                pass

        # Client logo
        company_name = body.get("company_name", "SAVIA")
        company_logo = body.get("company_logo", "")
        _client_logo_io = None
        if company_logo:
            try:
                clogo = company_logo.strip()
                if clogo.startswith("data:"):
                    _b64_part = clogo.split(",", 1)[1] if "," in clogo else clogo
                    _client_logo_io = BytesIO(_b64.b64decode(_b64_part))
                elif clogo.startswith("http"):
                    req_ = _ur.Request(clogo, headers={"User-Agent": "Mozilla/5.0"})
                    with _ur.urlopen(req_, timeout=6) as _r:
                        _client_logo_io = BytesIO(_r.read())
            except Exception as _e:
                logger.warning(f"Client logo error: {_e}")

        # Build PDF
        pdf = SaviaPDF(orientation="P", unit="mm", format="A4")
        pdf.set_header_data(
            SAVIA_LOGO, _client_logo_io,
            company_name if company_name != "SAVIA" else "",
            "",
            report_title=f"FICHE D'INTERVENTION N. {interv_id}"
        )
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_top_margin(pdf.HEADER_H + 10)
        pdf.add_page()
        W = pdf.w - 20

        # Date line
        pdf.set_font("Helvetica", "", 9)
        # INFORMATION PRINCIPALE - Two columns layout
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 0, 0)
        
        date_str = str(interv.get("date", ""))[:10]
        intervention_id = str(interv.get("id", ""))
        technicien = str(interv.get("technicien", "-")).strip()
        
        # Left column
        left_x = 14
        right_col_x = pdf.w / 2 + 5
        line_h = 5
        y_start = pdf.get_y()
        
        # LEFT COLUMN: Date, Client, Equipement, Marque/Modele, N° Serie
        pdf.set_xy(left_x, y_start)
        pdf.cell(70, line_h, _sanitize(f"Date: {date_str}"))
        
        pdf.set_xy(left_x, y_start + 5)
        pdf.cell(70, line_h, _sanitize(f"Client: {client_name or '-'}"))
        
        pdf.set_xy(left_x, y_start + 10)
        pdf.cell(70, line_h, _sanitize(f"Equipement: {str(interv.get('machine', '-'))[:35]}"))
        
        pdf.set_xy(left_x, y_start + 15)
        pdf.cell(70, line_h, _sanitize(f"Marque/Modele: {str(equip_type or '-')[:30]}"))
        
        pdf.set_xy(left_x, y_start + 20)
        pdf.cell(70, line_h, _sanitize(f"N° Serie: {str(num_serie or '-')[:25]}"))
        
        # RIGHT COLUMN: Technicien, Garantie, Contrat
        pdf.set_xy(right_col_x, y_start)
        pdf.cell(70, line_h, _sanitize(f"Technicien: {technicien}"))
        
        pdf.set_xy(right_col_x, y_start + 5)
        pdf.cell(70, line_h, _sanitize(f"Garantie: {'OUI' if sous_garantie else 'NON'}"))
        
        pdf.set_xy(right_col_x, y_start + 10)
        pdf.cell(70, line_h, _sanitize(f"Contrat: {'OUI' if sous_contrat else 'NON'}"))
        
        # Move down after info section
        pdf.set_y(y_start + 28)

        # TRAVAUX EFFECTUES - Table with Date, Start, End, Travel
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 0, 0)
        if is_multi_tech:
            pdf.cell(W, 6, "Travaux Effectues (Multi-Technicien)")
        else:
            pdf.cell(W, 6, "Travaux Effectues")
        pdf.ln(7)  # Increased space before table
        
        # Table header - Add Technicien column for multi-tech
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(200, 200, 200)
        pdf.set_text_color(0, 0, 0)
        
        if is_multi_tech:
            # Multi-tech table: Technicien, Debut, Fin, Trajet, Solution
            col_widths = [30, 25, 25, 25, 50]
            headers = ["Technicien", "Heure Debut", "Heure Fin", "Trajet (h)", "Solution"]
        else:
            # Single-tech table: Date, Debut, Fin, Trajet, Solution
            col_widths = [35, 30, 30, 30, 50]
            headers = ["Date", "Heure Debut", "Heure Fin", "Trajet (h)", "Solution Appliquee"]
        
        for i, header in enumerate(headers):
            pdf.cell(col_widths[i], 6, header, border=1, align="C", fill=True)
        pdf.ln(6)
        
        # Table data rows
        pdf.set_font("Helvetica", "", 8)
        pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(0, 0, 0)
        
        if is_multi_tech and tech_records:
            # Multi-tech mode: one row per technician from interventions_techniciens
            for tech_record in tech_records:
                rec_dict = dict(tech_record) if hasattr(tech_record, 'keys') else tech_record
                
                tech_nom = str(rec_dict.get('technicien_nom', 'Unknown'))[:20]
                heure_debut = str(rec_dict.get('heure_debut_tech', '-') or '-')[:5]
                heure_fin = str(rec_dict.get('heure_fin_tech', '-') or '-')[:5]
                duree_depl_min = int(rec_dict.get('duree_deplacement_tech', 0) or 0)
                trajet = f"{round(duree_depl_min / 60, 1)}" if duree_depl_min > 0 else "-"
                solution = _sanitize(str(rec_dict.get('solution_tech', ''))[:50])
                
                pdf.cell(col_widths[0], 6, _sanitize(tech_nom), border=1)
                pdf.cell(col_widths[1], 6, _sanitize(heure_debut), border=1)
                pdf.cell(col_widths[2], 6, _sanitize(heure_fin), border=1)
                pdf.cell(col_widths[3], 6, _sanitize(trajet), border=1)
                pdf.cell(col_widths[4], 6, solution, border=1)
                pdf.ln(6)
        else:
            # Single-tech mode: original behavior
            # Extract time data - USE start_time and end_time from database, with fallbacks
            date_val = date_str
            
            # Get start_time and end_time directly from database (TIME type columns)
            start_time = str(interv.get("start_time", "") or "").strip()
            if not start_time or start_time == "None" or start_time == "00:00":
                # Fallback: try to extract from date_debut_intervention
                start_time_fb = str(interv.get("date_debut_intervention", "") or "").strip()
                if start_time_fb and start_time_fb != "None" and len(start_time_fb) >= 16:
                    start_time = start_time_fb[11:16]  # Extract HH:MM (indices 11-16 exclusive)
                else:
                    # Second fallback: use date field
                    start_time_fb2 = str(interv.get("date", "") or "").strip()
                    if start_time_fb2 and start_time_fb2 != "None" and len(start_time_fb2) >= 16:
                        start_time = start_time_fb2[11:16]  # Extract HH:MM
                    else:
                        start_time = "-"
            else:
                # Ensure we only have HH:MM (remove seconds if present)
                if len(start_time) > 5 and start_time[5] == ':':
                    start_time = start_time[:5]  # Remove :SS
            
            end_time = str(interv.get("end_time", "") or "").strip()
            if not end_time or end_time == "None" or end_time == "00:00":
                # Fallback: use date_cloture
                end_time_fb = str(interv.get("date_cloture", "") or "").strip()
                if end_time_fb and end_time_fb != "None" and len(end_time_fb) >= 16:
                    end_time = end_time_fb[11:16]  # Extract HH:MM (indices 11-16 exclusive)
                else:
                    end_time = "-"
            else:
                # Ensure we only have HH:MM (remove seconds if present)
                if len(end_time) > 5 and end_time[5] == ':':
                    end_time = end_time[:5]  # Remove :SS
            
            # Trajet: duree_deplacement is in MINUTES, convert to hours
            trajet = f"{round(deplacement_min / 60, 1)}" if deplacement_min > 0 else "-"
            description = _sanitize(str(interv.get("solution", ""))[:50])  # Solution field
            
            # Row with borders - SANITIZE ALL VALUES
            pdf.cell(col_widths[0], 6, _sanitize(date_val), border=1)
            pdf.cell(col_widths[1], 6, _sanitize(start_time), border=1)
            pdf.cell(col_widths[2], 6, _sanitize(end_time), border=1)
            pdf.cell(col_widths[3], 6, _sanitize(trajet), border=1)
            pdf.cell(col_widths[4], 6, description, border=1)
            pdf.ln(6)
        
        # Add empty rows for manual fill (per model) - only for single-tech
        if not is_multi_tech:
            for _ in range(2):
                pdf.cell(col_widths[0], 6, "", border=1)
                pdf.cell(col_widths[1], 6, "", border=1)
                pdf.cell(col_widths[2], 6, "", border=1)
                pdf.cell(col_widths[3], 6, "", border=1)
                pdf.cell(col_widths[4], 6, "", border=1)
            pdf.ln(6)
        
        pdf.ln(8)
        
        # STATUT INTERVENTION - MOVED AFTER TABLE, IN BOLD
        pdf.set_font("Helvetica", "B", 10)  # Bold
        pdf.set_text_color(0, 0, 0)
        statut_val = str(interv.get("statut", "-"))
        status_map = {
            "Clôturee": "Clôturee",
            "En cours": "En cours",
            "En attente de piece": "En attente de piece",
        }
        display_status = status_map.get(statut_val, statut_val)
        pdf.cell(W, 5, _sanitize(f"Statut: {display_status}"))
        pdf.ln(8)
        
        # PIECES UTILISEES / REFERENCES TABLE
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(W, 6, "References - Pieces Utilisees")
        pdf.ln(7)  # Increased space before table
        
        # Table header - INCREASED REFERENCE COLUMN WIDTH
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(200, 200, 200)
        pdf.set_text_color(0, 0, 0)
        ref_col_widths = [50, 15, 100]  # Increased reference from 30 to 50
        ref_headers = ["Reference", "Qte", "Designation"]
        for i, header in enumerate(ref_headers):
            pdf.cell(ref_col_widths[i], 6, header, border=1, align="C", fill=True)
        pdf.ln(6)
        
        # Parse pieces data - USE PIPE DELIMITER - SHOW MORE TEXT
        pdf.set_font("Helvetica", "", 7)  # Smaller font for pieces
        pdf.set_fill_color(255, 255, 255)
        pdf.set_text_color(0, 0, 0)
        
        pieces = str(interv.get("pieces_utilisees", "") or "").strip()
        row_count = 0
        if pieces:
            pieces_lines = pieces.split('\n')  # Multiple pieces separated by newlines
            for piece_line in pieces_lines[:8]:  # Max 8 rows
                if piece_line.strip():
                    # Parse format: "Product | Ref: XXX | Fournisseur: YYY | Qty: Z"
                    parts = piece_line.split('|')
                    
                    # Extract each part
                    product_name = _sanitize(parts[0].strip()[:80]) if len(parts) > 0 else "-"
                    
                    # Find reference and quantity
                    ref_val = "-"
                    qty_val = "-"
                    for part in parts[1:]:
                        part_lower = part.lower()
                        if "ref:" in part_lower:
                            ref_val = _sanitize(part.replace("Ref:", "").replace("ref:", "").strip()[:45])  # Increased from 30 to 45
                        if "qty:" in part_lower:
                            qty_val = _sanitize(part.replace("Qty:", "").replace("qty:", "").strip()[:10])
                    
                    # Full designation includes product name
                    desc_val = product_name
                    
                    pdf.cell(ref_col_widths[0], 6, ref_val, border=1)
                    pdf.cell(ref_col_widths[1], 6, qty_val, border=1)
                    pdf.cell(ref_col_widths[2], 6, desc_val, border=1)
                    pdf.ln(6)
                    row_count += 1
        
        # Add empty rows for manual fill
        for _ in range(max(0, 8 - row_count)):
            pdf.cell(ref_col_widths[0], 6, "", border=1)
            pdf.cell(ref_col_widths[1], 6, "", border=1)
            pdf.cell(ref_col_widths[2], 6, "", border=1)
            pdf.ln(6)
        
        pdf.ln(8)
        
        # OBSERVATIONS section
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(W, 5, "Observations:")
        pdf.ln(6)
        
        # Add 2 extended dotted lines for client to write observations
        pdf.set_font("Helvetica", "", 9)
        for _ in range(2):
            # Create a dotted line that extends to the right edge
            # Each dot is about 1.5-2 characters wide, so we need about 130-150 dots for full width
            dots = "." * 150
            pdf.cell(W, 5, dots)
            pdf.ln(5)

        # SIGNATURES SECTION
        pdf.ln(8)
        sig_start_y = pdf.get_y()
        
        if sig_start_y > pdf.h - 60:
            pdf.add_page()
            sig_start_y = pdf.get_y()
        
        # Separator line
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.5)
        pdf.line(10, sig_start_y, pdf.w - 10, sig_start_y)
        
        pdf.set_y(sig_start_y + 3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(W, 5, "Signatures & Approbations")
        pdf.ln(8)
        
        # Three signature labels on ONE line
        col1_x = 18
        col2_x = pdf.w / 3 + 10
        col3_x = (pdf.w / 3) * 2 + 2
        box_w = 45
        box_h = 22
        label_y = pdf.get_y()
        
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(0, 0, 0)
        
        # Position labels horizontally
        pdf.set_xy(col1_x, label_y)
        pdf.cell(box_w, 5, "Visa Intervenant", align="C")
        
        pdf.set_xy(col2_x, label_y)
        pdf.cell(box_w, 5, "Visa Client", align="C")
        
        pdf.set_xy(col3_x, label_y)
        pdf.cell(box_w, 5, "Visa Administration", align="C")
        
        # Draw signature boxes below each label
        box_y = label_y + 6
        pdf.set_draw_color(0, 0, 0)
        pdf.set_line_width(0.3)
        pdf.rect(col1_x, box_y, box_w, box_h, style="D")
        pdf.rect(col2_x, box_y, box_w, box_h, style="D")
        pdf.rect(col3_x, box_y, box_w, box_h, style="D")

        # Footer
        pdf.set_auto_page_break(auto=False)
        total_pages = len(pdf.pages)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        for pg in range(1, total_pages + 1):
            pdf.page = pg
            pdf.set_xy(10, pdf.h - 12)
            pdf.set_draw_color(150, 180, 180)
            pdf.set_line_width(0.5)
            pdf.line(10, pdf.h - 12, pdf.w - 10, pdf.h - 12)
            pdf.set_xy(10, pdf.h - 9)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(120, 140, 150)
            pdf.cell(pdf.w - 40, 5, _sanitize(f"Généré par {company_name} - {now_str}"), align="L")
            pdf.cell(30, 5, f"Page {pg}/{total_pages}", align="R")

        pdf_bytes = bytes(pdf.output())
        _fn = f"fiche_intervention_{interv_id}"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={_fn}.pdf",
                "Content-Length": str(len(pdf_bytes)),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Fiche PDF generation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

@app.post("/api/equipements/{equip_id}/attestation-pdf")
def generate_attestation_pdf(equip_id: int, body: dict = {}, user: dict = Depends(_verify_token)):
    """Generate an 'Attestation de Bon Fonctionnement' PDF for an operational equipment."""
    from io import BytesIO
    from fastapi.responses import Response

    SAVIA_LOGO = "/app/logo-savia.png"

    try:
        df_equip = lire_equipements()
        equip = None
        if not df_equip.empty:
            match = df_equip[df_equip["id"] == equip_id]
            if not match.empty:
                equip = match.iloc[0].to_dict()
        if not equip:
            raise HTTPException(status_code=404, detail="Equipement non trouve")

        nom = str(equip.get("Nom", "") or equip.get("nom", "") or "-")
        client_name = str(equip.get("Client", "") or equip.get("client", "") or "-")
        num_serie = str(equip.get("NumSerie", "") or equip.get("num_serie", "") or "-")
        marque = str(equip.get("Marque", "") or equip.get("marque", "") or "-")
        modele = str(equip.get("Modele", "") or equip.get("modele", "") or "-")
        equip_type = str(equip.get("Type", "") or equip.get("type", "") or "-")
        localisation = str(equip.get("Localisation", "") or equip.get("localisation", "") or "-")
        date_installation = str(equip.get("DateInstallation", "") or equip.get("date_installation", "") or "")[:10]
        statut = str(equip.get("Statut", "") or equip.get("statut", "") or "-")

        # Fetch client info
        client_region = ""
        client_ville = ""
        client_adresse = ""
        client_telephone = ""
        if client_name and client_name != "-":
            try:
                with get_db() as conn:
                    cl_row = conn.execute("SELECT region, ville, adresse, telephone FROM clients WHERE nom = ? LIMIT 1", (client_name,)).fetchone()
                    if cl_row:
                        d = dict(cl_row)
                        client_region = d.get("region", "") or ""
                        client_ville = d.get("ville", "") or ""
                        client_adresse = d.get("adresse", "") or ""
                        client_telephone = d.get("telephone", "") or ""
            except Exception:
                pass

        # Warranty check
        sous_garantie = False
        garantie_fin_str = ""
        g_debut = equip.get("garantie_debut", "")
        g_duree = int(equip.get("garantie_duree", 0) or 0)
        if g_debut and g_duree:
            try:
                fin = datetime.strptime(str(g_debut)[:10], "%Y-%m-%d")
                fin = fin.replace(year=fin.year + g_duree)
                sous_garantie = fin > datetime.now()
                garantie_fin_str = fin.strftime("%d/%m/%Y")
            except Exception:
                pass

        # Contract check
        sous_contrat = False
        if client_name and client_name != "-":
            df_contrats = lire_contrats()
            if not df_contrats.empty:
                ccol = "client" if "client" in df_contrats.columns else "Client"
                if ccol in df_contrats.columns:
                    cc = df_contrats[df_contrats[ccol].str.strip().str.lower() == client_name.lower()]
                    if not cc.empty:
                        for _, c in cc.iterrows():
                            fin_str = c.get("date_fin", c.get("DateFin", ""))
                            if not fin_str:
                                sous_contrat = True
                                break
                            try:
                                if datetime.strptime(str(fin_str)[:10], "%Y-%m-%d") > datetime.now():
                                    sous_contrat = True
                                    break
                            except Exception:
                                sous_contrat = True
                                break

        # Company info from admin settings
        company_name = body.get("company_name", "SAVIA")
        company_logo = body.get("company_logo", "")
        import base64 as _b64
        import urllib.request as _ur
        _client_logo_io = None
        if company_logo:
            try:
                clogo = company_logo.strip()
                if clogo.startswith("data:"):
                    _b64_part = clogo.split(",", 1)[1] if "," in clogo else clogo
                    _client_logo_io = BytesIO(_b64.b64decode(_b64_part))
                elif clogo.startswith("http"):
                    req_ = _ur.Request(clogo, headers={"User-Agent": "Mozilla/5.0"})
                    with _ur.urlopen(req_, timeout=6) as _r:
                        _client_logo_io = BytesIO(_r.read())
            except Exception as _e:
                logger.warning(f"Client logo error: {_e}")

        # Build PDF
        pdf = SaviaPDF(orientation="P", unit="mm", format="A4")
        pdf.set_header_data(
            SAVIA_LOGO, _client_logo_io,
            company_name if company_name != "SAVIA" else "",
            "",
            report_title="ATTESTATION DE BON FONCTIONNEMENT"
        )
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_top_margin(pdf.HEADER_H + 10)
        pdf.add_page()
        W = pdf.w - 20

        today_str = datetime.now().strftime("%d/%m/%Y")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 120, 140)
        pdf.cell(W, 5, _sanitize(f"Date : {today_str}    |    R\u00e9f : ATT-{equip_id}-{datetime.now().strftime('%Y%m%d')}"), align="C")
        pdf.ln(10)

        # Introduction
        display_name = company_name if company_name and company_name != "SAVIA" else "SAVIA"
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 40, 60)
        pdf.multi_cell(W, 6, _sanitize(
            f"La soci\u00e9t\u00e9 {display_name} atteste par la pr\u00e9sente que l'\u00e9quipement ci-dessous, "
            f"install\u00e9 chez le client {client_name}, est en parfait \u00e9tat de fonctionnement "
            f"\u00e0 la date du {today_str}."
        ), align="L")
        pdf.ln(6)

        # ── SECTION: EQUIPEMENT ──
        y0 = pdf.get_y()
        pdf.set_fill_color(242, 252, 250)
        pdf.set_draw_color(180, 220, 215)
        pdf.set_line_width(0.3)
        box_h = 52
        pdf.rect(10, y0, W, box_h, style="FD")
        pdf.set_xy(14, y0 + 2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(W - 8, 6, _sanitize("INFORMATIONS \u00c9QUIPEMENT"))
        pdf.set_text_color(30, 40, 60)
        left_x = 14
        right_x = pdf.w / 2 + 5
        row_h = 7

        for i, (label, value) in enumerate([
            ("\u00c9quipement", _sanitize(nom)),
            ("Type", _sanitize(equip_type)),
            ("Marque / Mod\u00e8le", _sanitize(f"{marque} {modele}".strip())),
            ("N\u00b0 de s\u00e9rie", _sanitize(num_serie)),
            ("Localisation", _sanitize(localisation)),
        ]):
            pdf.set_xy(left_x, y0 + 9 + i * row_h)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(30, row_h, _sanitize(label + " :"))
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.cell(55, row_h, value[:40])

        for i, (label, value, color) in enumerate([
            ("Date installation", date_installation or "-", (30, 40, 60)),
            ("Statut", _sanitize(statut), (22, 163, 74)),
            ("Sous garantie", "Oui" if sous_garantie else "Non", (22, 163, 74) if sous_garantie else (200, 50, 50)),
            ("Sous contrat", "Oui" if sous_contrat else "Non", (22, 163, 74) if sous_contrat else (200, 50, 50)),
        ]):
            pdf.set_xy(right_x, y0 + 9 + i * row_h)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_text_color(30, 40, 60)
            pdf.cell(28, row_h, _sanitize(label + " :"))
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.set_text_color(*color)
            pdf.cell(40, row_h, value[:35])
        pdf.set_text_color(30, 40, 60)

        # ── SECTION: CLIENT ──
        pdf.set_y(y0 + box_h + 6)
        y1 = pdf.get_y()
        pdf.set_fill_color(240, 245, 255)
        pdf.set_draw_color(180, 200, 230)
        client_box_h = 38
        pdf.rect(10, y1, W, client_box_h, style="FD")
        pdf.set_xy(14, y1 + 2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(30, 80, 170)
        pdf.cell(W - 8, 6, "INFORMATIONS CLIENT")
        pdf.set_text_color(30, 40, 60)

        for i, (label, value) in enumerate([
            ("Client", _sanitize(client_name)),
            ("R\u00e9gion / Ville", _sanitize(f"{client_region} - {client_ville}".strip(" -") or "-")),
            ("Adresse", _sanitize(client_adresse or "-")),
            ("T\u00e9l\u00e9phone", _sanitize(client_telephone or "-")),
        ]):
            pdf.set_xy(left_x, y1 + 9 + i * row_h)
            pdf.set_font("Helvetica", "", 8)
            pdf.cell(30, row_h, _sanitize(label + " :"))
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.cell(130, row_h, value[:70])

        # ── DECLARATION ──
        pdf.set_y(y1 + client_box_h + 8)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 40, 60)
        pdf.multi_cell(W, 6, _sanitize(
            "Nous attestons que l'\u00e9quipement susmentionn\u00e9 a \u00e9t\u00e9 v\u00e9rifi\u00e9 et test\u00e9 par nos techniciens qualifi\u00e9s. "
            "Tous les param\u00e8tres de fonctionnement sont conformes aux sp\u00e9cifications du fabricant. "
            "L'\u00e9quipement est apte \u00e0 une utilisation normale dans le cadre de ses fonctions d\u00e9sign\u00e9es."
        ), align="L")
        pdf.ln(4)

        if sous_garantie and garantie_fin_str:
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(22, 163, 74)
            pdf.cell(W, 6, _sanitize(f"Cet \u00e9quipement est sous garantie jusqu'au {garantie_fin_str}."), align="L")
            pdf.ln(8)
            pdf.set_text_color(30, 40, 60)

        # ── SIGNATURES ──
        pdf.ln(6)
        y_sig = pdf.get_y()
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(80, 90, 110)
        pdf.set_xy(14, y_sig)
        pdf.cell(80, 6, _sanitize(f"Pour {display_name} :"))
        pdf.set_xy(14, y_sig + 8)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(80, 5, "Nom et signature :")
        pdf.set_draw_color(180, 180, 200)
        pdf.line(14, y_sig + 30, 90, y_sig + 30)

        pdf.set_xy(right_x, y_sig)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(80, 6, _sanitize(f"Pour le client ({client_name[:30]}) :"))
        pdf.set_xy(right_x, y_sig + 8)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(80, 5, "Nom, signature et cachet :")
        pdf.line(right_x, y_sig + 30, right_x + 76, y_sig + 30)

        # Footer
        pdf.set_y(-30)
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(140, 150, 165)
        pdf.cell(W, 4, _sanitize(f"Ce document est g\u00e9n\u00e9r\u00e9 automatiquement par {display_name} - {today_str}"), align="C")

        buf = BytesIO()
        pdf.output(buf)
        buf.seek(0)
        return Response(
            content=buf.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=attestation_bon_fonctionnement_{equip_id}.pdf"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Attestation PDF error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


# ==========================================
# PDF CONTRAT DE MAINTENANCE (document juridique)
# ==========================================

@app.post("/api/contrats/{contrat_id}/contrat-pdf")
def generate_contrat_pdf(contrat_id: int, body: dict = {}, user: dict = Depends(_verify_token)):
    """Genere un PDF de contrat de maintenance reel (parties, articles, signatures)."""
    from io import BytesIO
    from fastapi.responses import Response
    import base64 as _b64
    import urllib.request as _ur

    SAVIA_LOGO = "/app/logo-savia.png"

    try:
        # ── Fetch contract ──
        df_contrats = lire_contrats()
        contrat = None
        if not df_contrats.empty:
            match = df_contrats[df_contrats["id"] == contrat_id]
            if not match.empty:
                contrat = match.iloc[0].to_dict()
        if not contrat:
            raise HTTPException(status_code=404, detail="Contrat non trouve")

        # ── Extract fields ──
        client_name = str(contrat.get("client", "") or "-")
        equipement = str(contrat.get("equipement", "") or "")
        type_contrat = str(contrat.get("type_contrat", "") or "Standard")
        date_debut = str(contrat.get("date_debut", "") or "")[:10]
        date_fin = str(contrat.get("date_fin", "") or "")[:10]
        sla_h = int(contrat.get("sla_temps_reponse_h", 24) or 24)
        montant = float(contrat.get("montant", 0) or 0)
        statut = str(contrat.get("statut", "Actif") or "Actif")
        conditions = str(contrat.get("conditions", "") or "").strip()
        notes = str(contrat.get("notes", "") or "").strip()
        recurrence = str(contrat.get("recurrence_maintenance", "") or "").strip()
        date_premiere_mp = str(contrat.get("date_premiere_maintenance", "") or "")[:10]

        def _fmt_date(s):
            try:
                return datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y") if s else "-"
            except Exception:
                return s or "-"

        date_debut_fr = _fmt_date(date_debut)
        date_fin_fr = _fmt_date(date_fin)
        date_premiere_mp_fr = _fmt_date(date_premiere_mp)

        # Duration in months / years
        duree_str = "-"
        try:
            if date_debut and date_fin:
                d1 = datetime.strptime(date_debut, "%Y-%m-%d")
                d2 = datetime.strptime(date_fin, "%Y-%m-%d")
                months = (d2.year - d1.year) * 12 + (d2.month - d1.month)
                if months >= 12 and months % 12 == 0:
                    yrs = months // 12
                    duree_str = f"{yrs} an{'s' if yrs > 1 else ''}"
                else:
                    duree_str = f"{months} mois"
        except Exception:
            pass

        # ── Client info ──
        client_adresse = ""
        client_ville = ""
        client_telephone = ""
        client_contact = ""
        client_mf = ""
        if client_name and client_name != "-":
            try:
                with get_db() as conn:
                    cl_row = conn.execute(
                        "SELECT ville, adresse, telephone, contact, matricule_fiscale FROM clients WHERE nom = ? LIMIT 1",
                        (client_name,)
                    ).fetchone()
                    if cl_row:
                        d = dict(cl_row)
                        client_ville = d.get("ville", "") or ""
                        client_adresse = d.get("adresse", "") or ""
                        client_telephone = d.get("telephone", "") or ""
                        client_contact = d.get("contact", "") or ""
                        client_mf = d.get("matricule_fiscale", "") or ""
            except Exception as e:
                logger.debug(f"Client lookup failed: {e}")

        # ── Equipment details (optional) ──
        equip_marque = ""
        equip_modele = ""
        equip_serie = ""
        equip_type = ""
        if equipement:
            try:
                df_equip = lire_equipements()
                if not df_equip.empty and "Nom" in df_equip.columns:
                    eq_match = df_equip[df_equip["Nom"].str.strip() == equipement.strip()]
                    if not eq_match.empty:
                        eq = eq_match.iloc[0].to_dict()
                        equip_marque = str(eq.get("Marque", "") or eq.get("marque", "") or "")
                        equip_modele = str(eq.get("Modele", "") or eq.get("modele", "") or "")
                        equip_serie = str(eq.get("NumSerie", "") or eq.get("num_serie", "") or "")
                        equip_type = str(eq.get("Type", "") or eq.get("type", "") or "")
            except Exception as e:
                logger.debug(f"Equipment lookup failed: {e}")

        # ── Company / prestataire info ──
        company_name = body.get("company_name", "SAVIA") or "SAVIA"
        company_logo = body.get("company_logo", "")
        prestataire = company_name if company_name and company_name != "SAVIA" else "SAVIA"

        _client_logo_io = None
        if company_logo:
            try:
                clogo = company_logo.strip()
                if clogo.startswith("data:"):
                    _b64_part = clogo.split(",", 1)[1] if "," in clogo else clogo
                    _client_logo_io = BytesIO(_b64.b64decode(_b64_part))
                elif clogo.startswith("http"):
                    req_ = _ur.Request(clogo, headers={"User-Agent": "Mozilla/5.0"})
                    with _ur.urlopen(req_, timeout=6) as _r:
                        _client_logo_io = BytesIO(_r.read())
            except Exception as _e:
                logger.warning(f"Client logo error: {_e}")

        # ── Build PDF (Portrait A4) ──
        pdf = SaviaPDF(orientation="P", unit="mm", format="A4")
        pdf.set_header_data(
            SAVIA_LOGO, _client_logo_io,
            company_name if company_name != "SAVIA" else "",
            "",
            report_title=f"CONTRAT DE MAINTENANCE N. {contrat_id}"
        )
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.set_top_margin(pdf.HEADER_H + 8)
        pdf.add_page()
        W = pdf.w - 20
        LM = 10

        today_str = datetime.now().strftime("%d/%m/%Y")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 115, 135)
        pdf.cell(W, 5, _sanitize(f"R\u00e9f. : CTR-{contrat_id}-{datetime.now().strftime('%Y')}    |    \u00c9tabli le : {today_str}    |    Statut : {statut}"), align="C")
        pdf.ln(8)

        def section_title(num, label, color=(15, 118, 110)):
            if pdf.get_y() > pdf.h - 35:
                pdf.add_page()
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.set_text_color(*color)
            pdf.cell(W, 6, _sanitize(f"ARTICLE {num} \u2014 {label.upper()}"))
            pdf.ln(6)
            pdf.set_draw_color(*color)
            pdf.set_line_width(0.4)
            pdf.line(LM, pdf.get_y(), pdf.w - LM, pdf.get_y())
            pdf.ln(3)
            pdf.set_text_color(30, 40, 60)
            pdf.set_font("Helvetica", "", 9.5)

        def body_text(txt, indent=0):
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(35, 45, 65)
            pdf.set_x(LM + indent)
            pdf.multi_cell(W - indent, 5.2, _sanitize(txt))
            pdf.ln(1)

        def kv_line(label, value, label_w=55):
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(80, 95, 115)
            pdf.set_x(LM + 4)
            pdf.cell(label_w, 5.5, _sanitize(label + " :"))
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(25, 35, 55)
            pdf.multi_cell(W - label_w - 4, 5.5, _sanitize(str(value)))

        # ─── ENTRE LES SOUSSIGNES ───
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(W, 7, "ENTRE LES SOUSSIGN\u00c9S", align="C")
        pdf.ln(9)

        # Prestataire box
        y_p = pdf.get_y()
        pdf.set_fill_color(242, 252, 250)
        pdf.set_draw_color(180, 220, 215)
        pdf.set_line_width(0.3)
        prest_h = 26
        pdf.rect(LM, y_p, W, prest_h, style="FD")
        pdf.set_xy(LM + 4, y_p + 2)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(W - 8, 5, _sanitize("LE PRESTATAIRE"))
        pdf.set_xy(LM + 4, y_p + 8)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(25, 35, 55)
        pdf.cell(W - 8, 5, _sanitize(prestataire))
        pdf.set_xy(LM + 4, y_p + 14)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(70, 85, 105)
        pdf.multi_cell(W - 8, 4.5, _sanitize(
            "Soci\u00e9t\u00e9 sp\u00e9cialis\u00e9e dans la maintenance d'\u00e9quipements techniques, "
            "agissant en qualit\u00e9 de prestataire de services. Ci-apr\u00e8s d\u00e9nomm\u00e9e \u00ab le Prestataire \u00bb."
        ))

        # Client box
        pdf.set_y(y_p + prest_h + 4)
        y_c = pdf.get_y()
        pdf.set_fill_color(240, 245, 255)
        pdf.set_draw_color(180, 200, 230)
        cli_h = 32
        pdf.rect(LM, y_c, W, cli_h, style="FD")
        pdf.set_xy(LM + 4, y_c + 2)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(30, 80, 170)
        pdf.cell(W - 8, 5, _sanitize("LE CLIENT"))
        pdf.set_xy(LM + 4, y_c + 8)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(25, 35, 55)
        pdf.cell(W - 8, 5, _sanitize(client_name))

        col_left_x = LM + 4
        col_right_x = pdf.w / 2 + 2
        info_y = y_c + 14
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(60, 75, 95)

        left_pairs = [
            ("Adresse", client_adresse or "-"),
            ("Ville", client_ville or "-"),
        ]
        right_pairs = [
            ("T\u00e9l\u00e9phone", client_telephone or "-"),
            ("Contact", client_contact or "-"),
        ]
        for i, (lbl, val) in enumerate(left_pairs):
            pdf.set_xy(col_left_x, info_y + i * 5)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(20, 4.5, _sanitize(lbl + " :"))
            pdf.set_font("Helvetica", "", 8.5)
            pdf.cell(70, 4.5, _sanitize(str(val))[:50])
        for i, (lbl, val) in enumerate(right_pairs):
            pdf.set_xy(col_right_x, info_y + i * 5)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(20, 4.5, _sanitize(lbl + " :"))
            pdf.set_font("Helvetica", "", 8.5)
            pdf.cell(70, 4.5, _sanitize(str(val))[:50])

        if client_mf:
            pdf.set_xy(col_left_x, info_y + 10)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(35, 4.5, _sanitize("Matricule fiscale :"))
            pdf.set_font("Helvetica", "", 8.5)
            pdf.cell(80, 4.5, _sanitize(client_mf)[:50])

        pdf.set_y(y_c + cli_h + 4)
        pdf.set_x(LM)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(70, 85, 105)
        pdf.multi_cell(W, 4.5, _sanitize("Ci-apr\u00e8s d\u00e9nomm\u00e9 \u00ab le Client \u00bb."), align="R")
        pdf.ln(3)

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(W, 6, "IL A \u00c9T\u00c9 CONVENU CE QUI SUIT :", align="C")
        pdf.ln(8)

        # ARTICLE 1 - OBJET
        section_title(1, "Objet du contrat")
        intro_obj = (
            f"Le pr\u00e9sent contrat a pour objet de d\u00e9finir les conditions et modalit\u00e9s dans lesquelles "
            f"le Prestataire assure, au profit du Client, la maintenance de type \u00ab {type_contrat} \u00bb"
        )
        if equipement:
            intro_obj += " portant sur l'\u00e9quipement d\u00e9sign\u00e9 ci-dessous."
        else:
            intro_obj += " sur l'ensemble des \u00e9quipements d\u00e9clar\u00e9s par le Client."
        body_text(intro_obj)

        if equipement:
            pdf.ln(1)
            kv_line("D\u00e9signation", equipement)
            if equip_type:
                kv_line("Type", equip_type)
            if equip_marque or equip_modele:
                kv_line("Marque / Mod\u00e8le", f"{equip_marque} {equip_modele}".strip() or "-")
            if equip_serie:
                kv_line("N\u00b0 de s\u00e9rie", equip_serie)
        pdf.ln(3)

        # ARTICLE 2 - DUREE
        section_title(2, "Dur\u00e9e du contrat")
        body_text(
            f"Le pr\u00e9sent contrat est conclu pour une dur\u00e9e de {duree_str}, "
            f"prenant effet le {date_debut_fr} et expirant le {date_fin_fr}. "
            f"Au-del\u00e0 de ce terme, toute reconduction fera l'objet d'un avenant \u00e9crit entre les parties."
        )

        # ARTICLE 3 - PRESTATIONS
        section_title(3, "Nature des prestations")
        type_lower = type_contrat.lower()
        prest_desc = []
        if "pr\u00e9ventive" in type_lower or "preventive" in type_lower:
            prest_desc = [
                "Visites de maintenance pr\u00e9ventive planifi\u00e9es selon le calendrier convenu.",
                "Contr\u00f4le visuel et fonctionnel des composants critiques.",
                "Nettoyage, lubrification et r\u00e9glages selon recommandations du constructeur.",
                "R\u00e9daction d'un rapport d'intervention apr\u00e8s chaque visite.",
            ]
        elif "corrective" in type_lower:
            prest_desc = [
                "Intervention sur site en cas de panne ou dysfonctionnement signal\u00e9 par le Client.",
                "Diagnostic, r\u00e9paration et remise en service de l'\u00e9quipement.",
                "Fourniture et remplacement des pi\u00e8ces d\u00e9fectueuses (selon Article 6).",
                "Remise d'un rapport d'intervention d\u00e9taill\u00e9 apr\u00e8s chaque op\u00e9ration.",
            ]
        elif "full" in type_lower:
            prest_desc = [
                "Maintenance pr\u00e9ventive p\u00e9riodique programm\u00e9e.",
                "Maintenance corrective illimit\u00e9e (interventions sur panne).",
                "Fourniture et remplacement des pi\u00e8ces d\u00e9tach\u00e9es selon Article 6.",
                "Main d'\u0153uvre et frais de d\u00e9placement inclus.",
                "Support technique distance disponible aux heures ouvr\u00e9es.",
            ]
        elif "premium" in type_lower:
            prest_desc = [
                "Maintenance pr\u00e9ventive et corrective illimit\u00e9e.",
                "Pi\u00e8ces d\u00e9tach\u00e9es et main d'\u0153uvre incluses.",
                "Support technique prioritaire 24h/24, 7j/7.",
                "Reporting mensuel d\u00e9taill\u00e9 sur l'\u00e9tat du parc.",
                "Acc\u00e8s prioritaire aux mises \u00e0 jour techniques.",
            ]
        elif "main" in type_lower and "uvre" in type_lower:
            prest_desc = [
                "Main d'\u0153uvre des techniciens lors des interventions.",
                "D\u00e9placements sur site dans la zone de couverture.",
                "Diagnostic et r\u00e9parations (hors fourniture de pi\u00e8ces).",
                "Les pi\u00e8ces d\u00e9tach\u00e9es restent \u00e0 la charge du Client.",
            ]
        else:
            prest_desc = [
                "Maintenance pr\u00e9ventive et corrective de l'\u00e9quipement d\u00e9sign\u00e9.",
                "Diagnostic, r\u00e9paration et remise en service en cas de panne.",
                "R\u00e9daction d'un rapport apr\u00e8s chaque intervention.",
                "Conseil et support technique pendant les heures ouvr\u00e9es.",
            ]
        for it in prest_desc:
            pdf.set_x(LM + 4)
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(35, 45, 65)
            pdf.cell(4, 5.2, "-")
            pdf.multi_cell(W - 8, 5.2, _sanitize(it))
        pdf.ln(2)

        # ARTICLE 4 - SLA
        section_title(4, "Engagements de service (SLA)")
        body_text(
            f"Le Prestataire s'engage \u00e0 intervenir dans un d\u00e9lai maximum de {sla_h} heure(s) "
            f"\u00e0 compter de la r\u00e9ception de la demande d'intervention par le Client, durant les heures "
            f"ouvr\u00e9es (du lundi au vendredi, 8h\u201318h). Pour les interventions hors plages ouvr\u00e9es, "
            f"un d\u00e9lai compl\u00e9mentaire pourra s'appliquer."
        )

        # ARTICLE 5 - PLANNING (optionnel)
        if recurrence:
            section_title(5, "Planning des maintenances pr\u00e9ventives")
            body_text(
                f"Les visites de maintenance pr\u00e9ventive sont planifi\u00e9es selon une fr\u00e9quence "
                f"{recurrence.lower()}. La premi\u00e8re visite est pr\u00e9vue le {date_premiere_mp_fr}. "
                f"Les visites suivantes seront communiqu\u00e9es au Client au moins deux (2) semaines \u00e0 l'avance "
                f"par notification \u00e9crite (e-mail ou SMS)."
            )
            article_n = 6
        else:
            article_n = 5

        # ARTICLE - MONTANT
        section_title(article_n, "Montant et modalit\u00e9s de paiement")
        body_text(
            "En contrepartie des prestations d\u00e9finies au pr\u00e9sent contrat, le Client s'engage "
            "\u00e0 verser au Prestataire la somme annuelle de "
        )
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(15, 118, 110)
        pdf.set_x(LM + 4)
        pdf.cell(W - 4, 7, _sanitize(f"{montant:,.3f} TND".replace(",", " ")))
        pdf.ln(8)
        pdf.set_text_color(35, 45, 65)
        body_text(
            "hors taxes, payable selon les modalit\u00e9s convenues entre les parties (annuelle, "
            "trimestrielle ou mensuelle). Tout retard de paiement sup\u00e9rieur \u00e0 trente (30) jours "
            "pourra entra\u00eener la suspension des prestations apr\u00e8s mise en demeure rest\u00e9e infructueuse."
        )
        article_n += 1

        # ARTICLE - CONDITIONS PARTICULIERES
        if conditions:
            section_title(article_n, "Conditions particuli\u00e8res")
            body_text(conditions)
            article_n += 1

        # ARTICLE - OBLIGATIONS DU CLIENT
        section_title(article_n, "Obligations du Client")
        for it in [
            "Permettre l'acc\u00e8s libre aux \u00e9quipements lors des interventions programm\u00e9es.",
            "Signaler dans les meilleurs d\u00e9lais tout dysfonctionnement constat\u00e9.",
            "Ne pas faire intervenir de tiers non agr\u00e9\u00e9 sur les \u00e9quipements couverts.",
            "Utiliser les \u00e9quipements conform\u00e9ment aux pr\u00e9conisations du constructeur.",
            "R\u00e9gler les sommes dues aux \u00e9ch\u00e9ances convenues.",
        ]:
            pdf.set_x(LM + 4)
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(35, 45, 65)
            pdf.cell(4, 5.2, "-")
            pdf.multi_cell(W - 8, 5.2, _sanitize(it))
        pdf.ln(2)
        article_n += 1

        # ARTICLE - RESILIATION
        section_title(article_n, "R\u00e9siliation")
        body_text(
            "Le pr\u00e9sent contrat pourra \u00eatre r\u00e9sili\u00e9 par l'une ou l'autre des parties, "
            "moyennant un pr\u00e9avis \u00e9crit de soixante (60) jours adress\u00e9 par lettre recommand\u00e9e "
            "avec accus\u00e9 de r\u00e9ception. En cas de manquement grave et persistant aux obligations "
            "contractuelles, la r\u00e9siliation pourra intervenir de plein droit apr\u00e8s mise en demeure "
            "rest\u00e9e sans effet pendant trente (30) jours."
        )
        article_n += 1

        # ARTICLE - LITIGES
        section_title(article_n, "Loi applicable et juridiction comp\u00e9tente")
        body_text(
            "Le pr\u00e9sent contrat est soumis au droit tunisien. Tout litige relatif \u00e0 son interpr\u00e9tation "
            "ou \u00e0 son ex\u00e9cution sera soumis, \u00e0 d\u00e9faut de r\u00e8glement amiable, aux tribunaux "
            "comp\u00e9tents du si\u00e8ge social du Prestataire."
        )

        # NOTES (optionnel)
        if notes:
            pdf.ln(2)
            pdf.set_font("Helvetica", "BI", 9)
            pdf.set_text_color(110, 95, 30)
            pdf.set_x(LM)
            pdf.cell(W, 5, _sanitize("Notes compl\u00e9mentaires :"))
            pdf.ln(5)
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(80, 90, 110)
            pdf.set_x(LM + 4)
            pdf.multi_cell(W - 4, 4.8, _sanitize(notes))
            pdf.ln(2)

        # ─── SIGNATURES ───
        if pdf.get_y() > pdf.h - 70:
            pdf.add_page()
        else:
            pdf.ln(6)

        pdf.set_draw_color(15, 118, 110)
        pdf.set_line_width(0.5)
        pdf.line(LM, pdf.get_y(), pdf.w - LM, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(W, 6, _sanitize(f"Fait \u00e0 {client_ville or '-'}, le {today_str}, en deux exemplaires originaux."))
        pdf.ln(8)

        sig_y = pdf.get_y()
        col1_x = LM + 4
        col2_x = pdf.w / 2 + 5
        box_w = (pdf.w / 2) - 14
        box_h = 38

        pdf.set_xy(col1_x, sig_y)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(15, 118, 110)
        pdf.cell(box_w, 5, _sanitize(f"Pour le Prestataire ({prestataire})"))
        pdf.set_xy(col1_x, sig_y + 6)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(80, 95, 115)
        pdf.cell(box_w, 4.5, "Nom, qualit\u00e9, signature et cachet :")
        pdf.set_draw_color(180, 195, 215)
        pdf.set_line_width(0.3)
        pdf.rect(col1_x, sig_y + 11, box_w, box_h - 11, style="D")

        client_short = client_name[:35] + ("..." if len(client_name) > 35 else "")
        pdf.set_xy(col2_x, sig_y)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(30, 80, 170)
        pdf.cell(box_w, 5, _sanitize(f"Pour le Client ({client_short})"))
        pdf.set_xy(col2_x, sig_y + 6)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(80, 95, 115)
        pdf.cell(box_w, 4.5, "Nom, qualit\u00e9, signature et cachet :")
        pdf.rect(col2_x, sig_y + 11, box_w, box_h - 11, style="D")

        # ─── FOOTER ───
        pdf.set_auto_page_break(auto=False)
        total_pages = len(pdf.pages)
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
        for pg in range(1, total_pages + 1):
            pdf.page = pg
            pdf.set_xy(LM, pdf.h - 11)
            pdf.set_draw_color(200, 205, 220)
            pdf.set_line_width(0.3)
            pdf.line(LM, pdf.h - 11, pdf.w - LM, pdf.h - 11)
            pdf.set_xy(LM, pdf.h - 9)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(160, 170, 190)
            pdf.cell(pdf.w - 40, 5, _sanitize(f"Contrat #{contrat_id} - G\u00e9n\u00e9r\u00e9 par {prestataire} le {now_str}"), align="L")
            pdf.cell(30, 5, f"Page {pg} / {total_pages}", align="R")

        pdf_bytes = bytes(pdf.output())
        import urllib.parse as _up, unicodedata as _ud
        _fn = f"contrat_maintenance_{contrat_id}_{client_name.replace(' ', '_')}"
        _ascii = _ud.normalize("NFKD", _fn).encode("ascii", "ignore").decode()
        _ascii = "".join(c if c.isalnum() or c in "._-" else "_" for c in _ascii).strip("_") or f"contrat_{contrat_id}"
        _utf8 = _up.quote(_fn + ".pdf", safe="")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={_ascii}.pdf; filename*=UTF-8''{_utf8}",
                "Content-Length": str(len(pdf_bytes)),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Contrat PDF error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


# ==========================================
# FINANCES — Rentabilite & TCO
# ==========================================

@app.get("/api/finances/dashboard")
def finances_dashboard(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Dashboard financier : rentabilité par client, marges, TCO."""
    try:
        df_contrats = lire_contrats()
        df_interv = lire_interventions()
        df_equip = lire_equipements()
        df_pieces = lire_pieces()

        # --- Client profitability ---
        clients_profit = []
        all_clients = []
        # Only include clients that have a maintenance contract
        contrat_clients = set()
        if not df_contrats.empty and "client" in df_contrats.columns:
            contrat_clients = set(df_contrats["client"].dropna().unique().tolist())
        if not df_equip.empty and "Client" in df_equip.columns:
            all_clients = sorted([c for c in df_equip["Client"].dropna().unique().tolist() if c in contrat_clients])

        for cl in all_clients:
            if client and cl != client:
                continue
            # Revenue from contracts
            revenu = 0
            if not df_contrats.empty and "client" in df_contrats.columns:
                cl_contrats = df_contrats[df_contrats["client"] == cl]
                revenu = cl_contrats["montant"].sum() if "montant" in cl_contrats.columns else 0

            # Costs from interventions
            cout_interv = 0
            cout_pieces = 0
            nb_interv = 0
            duree_totale = 0
            cl_machines = df_equip[df_equip["Client"] == cl]["Nom"].tolist() if "Nom" in df_equip.columns else []
            if not df_interv.empty and "machine" in df_interv.columns and cl_machines:
                cl_interventions = df_interv[df_interv["machine"].isin(cl_machines)]
                nb_interv = len(cl_interventions)
                cout_interv = cl_interventions["cout"].sum() if "cout" in cl_interventions.columns else 0
                cout_pieces = cl_interventions["cout_pieces"].sum() if "cout_pieces" in cl_interventions.columns else 0
                duree_totale = cl_interventions["duree_minutes"].sum() if "duree_minutes" in cl_interventions.columns else 0

            # Get taux horaire from config (required, no default)
            try:
                taux_str = get_config("taux_horaire_technicien", "")
                if not taux_str:
                    raise ValueError("Taux horaire technicien non configuré dans les paramètres")
                taux = float(taux_str)
            except (ValueError, TypeError) as e:
                raise HTTPException(400, f"Erreur: {str(e)}")
            
            # Calculate labor cost from duration (for recalculation with current rate)
            cout_mo_recalculated = float((duree_totale / 60.0) * taux)
            
            # Service cost = Total intervention cost - Labor cost - Parts cost
            cout_service = max(0, float(cout_interv) - cout_mo_recalculated - float(cout_pieces))

            # Total cost remains the same
            cout_total_final = cout_service + cout_mo_recalculated + float(cout_pieces)
            marge = float(revenu) - cout_total_final
            marge_pct = round((marge / float(revenu) * 100), 1) if float(revenu) > 0 else 0.0

            nb_equip = int(len(df_equip[df_equip["Client"] == cl])) if not df_equip.empty else 0

            clients_profit.append({
                "client": cl,
                "nb_equipements": int(nb_equip),
                "revenu_contrats": round(float(revenu), 0),
                "cout_interventions": round(float(cout_service), 0),
                "cout_pieces": round(float(cout_pieces), 0),
                "cout_main_oeuvre": round(float(cout_mo_recalculated), 0),
                "cout_total": round(float(cout_total_final), 0),
                "marge": round(float(marge), 0),
                "marge_pct": float(marge_pct),
                "nb_interventions": int(nb_interv),
                "duree_totale_h": round(float(duree_totale) / 60.0, 1),
                "rentable": bool(marge >= 0),
            })

        # --- Global KPIs ---
        total_revenu = sum(c["revenu_contrats"] for c in clients_profit)
        total_cout = sum(c["cout_total"] for c in clients_profit)
        total_marge = total_revenu - total_cout
        nb_rentables = sum(1 for c in clients_profit if c["rentable"])
        nb_deficitaires = len(clients_profit) - nb_rentables

        # Sort by margin (worst first for alerts)
        clients_profit.sort(key=lambda x: x["marge"])

        return {
            "kpis": {
                "revenu_total": round(float(total_revenu), 0),
                "cout_total": round(float(total_cout), 0),
                "marge_globale": round(float(total_marge), 0),
                "marge_pct": round(float(total_marge / total_revenu * 100), 1) if total_revenu > 0 else 0.0,
                "nb_clients": int(len(clients_profit)),
                "nb_rentables": int(nb_rentables),
                "nb_deficitaires": int(nb_deficitaires),
            },
            "clients": clients_profit,
        }
    except Exception as e:
        logger.error(f"Finances dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/finances/tco")
def finances_tco(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Total Cost of Ownership par équipement."""
    try:
        df_equip = lire_equipements()
        df_interv = lire_interventions()

        tco_list = []
        if df_equip.empty:
            return tco_list

        try:
            taux_str = get_config("taux_horaire_technicien", "")
            if not taux_str:
                raise ValueError("Taux horaire technicien non configuré dans les paramètres")
            taux = float(taux_str)
        except (ValueError, TypeError) as e:
            raise HTTPException(400, f"Erreur: {str(e)}")

        for _, eq in df_equip.iterrows():
            nom = eq.get("Nom", "")
            cl = eq.get("Client", "")
            if client and cl != client:
                continue

            cout_interv = 0
            cout_pieces = 0
            nb_interv = 0
            nb_correctives = 0
            nb_preventives = 0
            duree = 0
            if not df_interv.empty and "machine" in df_interv.columns:
                eq_interv = df_interv[df_interv["machine"] == nom]
                nb_interv = len(eq_interv)
                cout_interv = eq_interv["cout"].sum() if "cout" in eq_interv.columns else 0
                cout_pieces = eq_interv["cout_pieces"].sum() if "cout_pieces" in eq_interv.columns else 0
                duree = eq_interv["duree_minutes"].sum() if "duree_minutes" in eq_interv.columns else 0
                nb_correctives = len(eq_interv[eq_interv["type_intervention"].str.lower().str.contains("correct", na=False)]) if "type_intervention" in eq_interv.columns else 0
                nb_preventives = nb_interv - nb_correctives

            cout_mo = (duree / 60.0) * taux
            # Extract service cost (intervention cost - labor - parts)
            cout_service = max(0, float(cout_interv) - cout_mo - float(cout_pieces))
            tco_total = float(cout_service) + float(cout_pieces) + cout_mo

            # Installation age (days)
            age_jours = 0
            date_install = eq.get("DateInstallation", eq.get("date_installation", ""))
            if date_install:
                try:
                    d = pd.to_datetime(str(date_install), errors="coerce")
                    if pd.notna(d):
                        age_jours = (datetime.now() - d).days
                except Exception:
                    pass

            tco_mensuel = round(tco_total / max(age_jours / 30.0, 1), 0) if age_jours > 0 else 0

            tco_list.append({
                "equipement": str(nom),
                "client": str(cl),
                "type": str(eq.get("Type", eq.get("type", ""))),
                "statut": str(eq.get("Statut", eq.get("statut", ""))),
                "age_jours": int(age_jours),
                "nb_interventions": int(nb_interv),
                "nb_correctives": int(nb_correctives),
                "nb_preventives": int(nb_preventives),
                "cout_interventions": round(float(cout_service), 0),
                "cout_pieces": round(float(cout_pieces), 0),
                "cout_main_oeuvre": round(float(cout_mo), 0),
                "tco_total": round(float(tco_total), 0),
                "tco_mensuel": round(float(tco_mensuel), 0),
                "duree_totale_h": round(float(duree) / 60.0, 1),
            })

        tco_list.sort(key=lambda x: x["tco_total"], reverse=True)
        return tco_list
    except Exception as e:
        logger.error(f"TCO error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 🗺️ CARTE GÉOGRAPHIQUE
# ==========================================

@app.get("/api/map/sites")
def map_sites(user: dict = Depends(_verify_token)):
    """Retourne les sites clients avec coordonnées GPS et score de santé."""
    import random, hashlib

    # Tunisian cities with GPS coordinates
    TUNISIAN_CITIES = {
        'tunis': (36.8065, 10.1815), 'ariana': (36.8601, 10.1956), 'ben arous': (36.7533, 10.2281),
        'manouba': (36.8100, 10.0987), 'nabeul': (36.4561, 10.7376), 'zaghouan': (36.4028, 10.1428),
        'bizerte': (37.2744, 9.8739), 'beja': (36.7256, 9.1817), 'jendouba': (36.5011, 8.7803),
        'kef': (36.1676, 8.7049), 'siliana': (36.0847, 9.3711), 'sousse': (35.8254, 10.6369),
        'monastir': (35.7643, 10.8113), 'mahdia': (35.5047, 11.0622), 'sfax': (34.7404, 10.7602),
        'kairouan': (35.6804, 10.0963), 'kasserine': (35.1672, 8.8365), 'sidi bouzid': (35.0380, 9.4849),
        'gabes': (33.8819, 10.0982), 'gabès': (33.8819, 10.0982), 'medenine': (33.3540, 10.5050),
        'tataouine': (32.9297, 10.4518), 'gafsa': (34.4250, 8.7842), 'tozeur': (33.9197, 8.1339),
        'kebili': (33.7041, 8.9711), 'kébili': (33.7041, 8.9711),
        'hammamet': (36.4000, 10.6167), 'tabarka': (36.9541, 8.7580), 'djerba': (33.8076, 10.8451),
        'grombalia': (36.6017, 10.5042), 'la marsa': (36.8783, 10.3252), 'carthage': (36.8528, 10.3233),
        'omrane': (36.8300, 10.1600), 'el omrane': (36.8300, 10.1600),
    }
    CITY_LIST = list(TUNISIAN_CITIES.values())

    def _guess_city_coords(client_name: str, ville: str):
        """Try to guess coordinates from client name or ville field."""
        for text in [ville, client_name]:
            if not text:
                continue
            lower = text.lower()
            for city, coords in TUNISIAN_CITIES.items():
                if city in lower:
                    return coords
        return None

    def _deterministic_random_coords(client_name: str):
        """Assign a deterministic 'random' city based on client name hash, with slight jitter."""
        h = int(hashlib.md5(client_name.encode()).hexdigest(), 16)
        city_coords = CITY_LIST[h % len(CITY_LIST)]
        # Add slight jitter (±0.01 degrees ≈ ±1km) so markers don't overlap
        jitter_lat = ((h >> 8) % 200 - 100) / 10000.0
        jitter_lng = ((h >> 16) % 200 - 100) / 10000.0
        return (city_coords[0] + jitter_lat, city_coords[1] + jitter_lng)

    try:
        df_equip = lire_equipements()
        df_interv = lire_interventions()
        df_plan = lire_planning()  # ← Load ONCE before the loop
        
        # Load clients to get ville and region info
        try:
            df_clients = db_lire_clients()
        except:
            df_clients = None

        sites = {}
        if df_equip.empty:
            return []

        for _, eq in df_equip.iterrows():
            cl = eq.get("Client", "")
            if not cl:
                continue
            if cl not in sites:
                # Get ville and region from clients table if available
                ville = ""
                if df_clients is not None and not df_clients.empty:
                    client_row = df_clients[df_clients["nom"] == cl]
                    if not client_row.empty:
                        ville = client_row.iloc[0].get("ville", "") or ""
                
                # Fallback to equipment ville if client ville not found
                if not ville:
                    ville = eq.get("Ville", eq.get("ville", ""))
                
                sites[cl] = {
                    "client": cl,
                    "equipements": [],
                    "nb_equipements": 0,
                    "latitude": eq.get("latitude", None),
                    "longitude": eq.get("longitude", None),
                    "adresse": eq.get("adresse", ""),
                    "ville": ville,
                }
            nom = eq.get("Nom", "")
            statut = eq.get("Statut", eq.get("statut", "Actif"))
            sites[cl]["equipements"].append({"nom": nom, "type": eq.get("Type", ""), "statut": statut})
            sites[cl]["nb_equipements"] += 1

        # Compute health scores per site + auto-assign coordinates
        result = []
        for cl, site in sites.items():
            nb = site["nb_equipements"]
            nb_hs = sum(1 for e in site["equipements"] if e["statut"] in ("Hors Service", "Critique", "En panne"))
            score = max(0, round(((nb - nb_hs) / nb) * 100)) if nb > 0 else 100

            # Auto-assign coordinates if missing
            lat, lng = site["latitude"], site["longitude"]
            assigned_ville = site.get("ville", "") or ""
            if not lat or not lng:
                guessed = _guess_city_coords(cl, assigned_ville)
                if guessed:
                    lat, lng = guessed
                    # Extract the matched city name for the ville field
                    if not assigned_ville:
                        lower = cl.lower()
                        for city_name in TUNISIAN_CITIES:
                            if city_name in lower:
                                assigned_ville = city_name.capitalize()
                                break
                else:
                    lat, lng = _deterministic_random_coords(cl)
                    if not assigned_ville:
                        # Find the closest city name for display
                        h = int(hashlib.md5(cl.encode()).hexdigest(), 16)
                        city_names = list(TUNISIAN_CITIES.keys())
                        assigned_ville = city_names[h % len(city_names)].capitalize()

            # Count interventions
            machines = [e["nom"] for e in site["equipements"]]
            nb_interv = 0
            if not df_interv.empty and "machine" in df_interv.columns:
                nb_interv = len(df_interv[df_interv["machine"].isin(machines)])

            # Next planned maintenance
            prochaine_maintenance = None
            try:
                if not df_plan.empty and "machine" in df_plan.columns:
                    today = datetime.now().strftime("%Y-%m-%d")
                    planned = df_plan[(df_plan["machine"].isin(machines)) & 
                                     (df_plan["date_prevue"] >= today) &
                                     (df_plan["statut"].isin(["Planifiée", "En cours"]))]
                    if not planned.empty:
                        prochaine_maintenance = planned["date_prevue"].min()
                        if hasattr(prochaine_maintenance, 'strftime'):
                            prochaine_maintenance = prochaine_maintenance.strftime("%Y-%m-%d")
                        else:
                            prochaine_maintenance = str(prochaine_maintenance)[:10]
            except Exception:
                pass

            result.append({
                **site,
                "latitude": float(lat) if lat and lat == lat else None,  # Check for NaN
                "longitude": float(lng) if lng and lng == lng else None,  # Check for NaN
                "ville": assigned_ville,
                "equipements": site["equipements"][:20],  # Limit for performance
                "score_sante": score,
                "nb_interventions": nb_interv,
                "prochaine_maintenance": prochaine_maintenance,
            })

        return result
    except Exception as e:
        logger.error(f"Map sites error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/map/sites/{client_name}/coordinates")
def update_site_coordinates(client_name: str, body: dict, user: dict = Depends(_verify_token)):
    """Met à jour les coordonnées GPS d'un site client (sur tous ses équipements)."""
    lat = body.get("latitude")
    lng = body.get("longitude")
    adresse = body.get("adresse", "")

    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="latitude et longitude requis")

    try:
        with get_db() as conn:
            # Update all equipments for this client
            conn.execute(
                "UPDATE equipements SET latitude = ?, longitude = ?, adresse = ? WHERE client = ?",
                (float(lat), float(lng), adresse, client_name)
            )
        return {"ok": True, "message": f"Coordonnées mises à jour pour {client_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 📅 SLA TRACKING
# ==========================================

@app.get("/api/sla/status")
def sla_status(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    """Suivi SLA temps réel : interventions ouvertes vs engagements contractuels."""
    try:
        df_contrats = lire_contrats()
        df_interv = lire_interventions()
        df_equip = lire_equipements()
        df_demandes = lire_demandes_intervention()

        # Build client → SLA mapping from contracts
        client_sla = {}
        if not df_contrats.empty:
            for _, c in df_contrats.iterrows():
                cl = c.get("client", "")
                sla_h = c.get("sla_temps_reponse_h", 24)
                statut = str(c.get("statut", "")).lower()
                if cl and "actif" in statut:
                    if cl not in client_sla or sla_h < client_sla[cl]:
                        client_sla[cl] = int(sla_h)

        # Build machine → client mapping
        machine_client = {}
        if not df_equip.empty:
            for _, eq in df_equip.iterrows():
                machine_client[eq.get("Nom", "")] = eq.get("Client", "")

        now = datetime.now()
        sla_items = []

        # Active interventions (not clôturées)
        if not df_interv.empty:
            active = df_interv[~df_interv["statut"].str.lower().str.contains("termin|clotur|clôtur", na=False)]
            if client:
                machines_client = [m for m, c in machine_client.items() if c == client]
                active = active[active["machine"].isin(machines_client)]

            for _, interv in active.iterrows():
                machine = interv.get("machine", "")
                cl = machine_client.get(machine, "")
                sla_h = client_sla.get(cl, 24)  # Default 24h if no contract

                # Start time: date_debut_intervention or date (creation)
                start_str = interv.get("date_debut_intervention") or interv.get("date", "")
                try:
                    start = pd.to_datetime(start_str)
                    if pd.isna(start):
                        continue
                except Exception:
                    continue

                elapsed_h = round((now - start).total_seconds() / 3600, 1)
                remaining_h = round(sla_h - elapsed_h, 1)
                pct = min(100, round((elapsed_h / sla_h) * 100, 1)) if sla_h > 0 else 100
                breached = elapsed_h > sla_h

                sla_items.append({
                    "id": interv.get("id"),
                    "machine": machine,
                    "client": cl,
                    "technicien": interv.get("technicien", ""),
                    "type_intervention": interv.get("type_intervention", ""),
                    "statut": interv.get("statut", ""),
                    "date_debut": str(start_str)[:16],
                    "sla_h": sla_h,
                    "elapsed_h": elapsed_h,
                    "remaining_h": max(0, remaining_h),
                    "pct_used": pct,
                    "breached": breached,
                    "priorite": interv.get("priorite", ""),
                })

        # Active demandes (waiting response)
        if not df_demandes.empty:
            active_dem = df_demandes[df_demandes["statut"].isin(["Nouvelle", "En attente"])]
            if client:
                active_dem = active_dem[active_dem["client"] == client]

            for _, dem in active_dem.iterrows():
                cl = dem.get("client", "")
                sla_h = client_sla.get(cl, 24)
                start_str = dem.get("date_demande", "")
                try:
                    start = pd.to_datetime(start_str)
                    if pd.isna(start):
                        continue
                except Exception:
                    continue

                elapsed_h = round((now - start).total_seconds() / 3600, 1)
                remaining_h = round(sla_h - elapsed_h, 1)
                pct = min(100, round((elapsed_h / sla_h) * 100, 1)) if sla_h > 0 else 100
                breached = elapsed_h > sla_h

                sla_items.append({
                    "id": f"DEM-{dem.get('id', '')}",
                    "machine": dem.get("equipement", ""),
                    "client": cl,
                    "technicien": dem.get("technicien_assigne", ""),
                    "type_intervention": "Demande",
                    "statut": dem.get("statut", ""),
                    "date_debut": str(start_str)[:16],
                    "sla_h": sla_h,
                    "elapsed_h": elapsed_h,
                    "remaining_h": max(0, remaining_h),
                    "pct_used": pct,
                    "breached": breached,
                    "priorite": dem.get("urgence", ""),
                })

        # Sort by remaining time (most urgent first)
        sla_items.sort(key=lambda x: x["remaining_h"])

        # Compute KPIs
        total_active = len(sla_items)
        nb_breached = sum(1 for s in sla_items if s["breached"])
        nb_danger = sum(1 for s in sla_items if not s["breached"] and s["pct_used"] >= 75)
        nb_ok = total_active - nb_breached - nb_danger

        # Historical compliance (closed interventions)
        compliance_pct = 100
        if not df_interv.empty:
            closed = df_interv[df_interv["statut"].str.lower().str.contains("termin|clotur|clôtur", na=False)]
            if not closed.empty and "date_debut_intervention" in closed.columns and "date_cloture" in closed.columns:
                compliant = 0
                total_measured = 0
                for _, ci in closed.iterrows():
                    try:
                        start = pd.to_datetime(ci.get("date_debut_intervention"))
                        end = pd.to_datetime(ci.get("date_cloture"))
                        if pd.isna(start) or pd.isna(end):
                            continue
                        cl_name = machine_client.get(ci.get("machine", ""), "")
                        sla = client_sla.get(cl_name, 24)
                        duration_h = (end - start).total_seconds() / 3600
                        total_measured += 1
                        if duration_h <= sla:
                            compliant += 1
                    except Exception:
                        continue
                if total_measured > 0:
                    compliance_pct = round((compliant / total_measured) * 100, 1)

        return {
            "kpis": {
                "total_active": total_active,
                "nb_breached": nb_breached,
                "nb_danger": nb_danger,
                "nb_ok": nb_ok,
                "compliance_pct": compliance_pct,
            },
            "items": sla_items,
        }
    except Exception as e:
        logger.error(f"SLA status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ENTRY POINT
# ==========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
