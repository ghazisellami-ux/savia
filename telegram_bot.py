# ==========================================
# 🤖 BOT TELEGRAM BIDIRECTIONNEL — SIC Radiologie
# ==========================================
"""
Bot Telegram pour les techniciens de maintenance.
Commandes:
  /start            — Enregistrer le technicien
  /mes_interventions — Voir ses interventions assignées
  /urgences         — Voir les pannes critiques
  /aide             — Aide
Callbacks inline:
  interv_prendre:<id>   — Prendre en charge
  interv_encours:<id>   — Marquer en cours
  interv_terminer:<id>  — Terminer
"""

import os
import logging
import asyncio
import threading
from datetime import datetime

logger = logging.getLogger("telegram_bot")

# ---- Config ----
def _get_token():
    """Récupère le token depuis os.environ ou st.secrets."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        try:
            import streamlit as st
            token = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
        except Exception:
            pass
    return token

TELEGRAM_BOT_TOKEN = _get_token()

# ---- Globals ----
_bot_thread = None
_bot_running = False
_bot_error = ""


def _get_db_connection():
    """Crée une connexion DB compatible (PG ou SQLite)."""
    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(database_url)
        conn.set_client_encoding('UTF8')
        return conn, "pg"
    else:
        import sqlite3
        from config import BASE_DIR
        db_path = os.path.join(BASE_DIR, "sic_radiologie.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"


def _execute_query(sql, params=None, fetch="all"):
    """Exécute une requête SQL et retourne les résultats."""
    conn, db_type = _get_db_connection()
    try:
        cur = conn.cursor()
        if db_type == "pg":
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            sql = sql.replace("?", "%s")
        cur.execute(sql, params or ())
        if fetch == "all":
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        elif fetch == "one":
            row = cur.fetchone()
            return dict(row) if row else None
        else:
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"DB error: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return [] if fetch == "all" else None
    finally:
        conn.close()


def _execute_update(sql, params=None):
    """Exécute un UPDATE/INSERT."""
    return _execute_query(sql, params, fetch="none")


# ==========================================
# FONCTIONS METIER
# ==========================================

def get_technicien_by_telegram(chat_id):
    """Trouve un technicien par son telegram_id (chat_id)."""
    return _execute_query(
        "SELECT * FROM techniciens WHERE telegram_id = ?",
        (str(chat_id),), fetch="one"
    )


def get_interventions_technicien(tech_name):
    """Récupère les interventions non terminées d'un technicien."""
    return _execute_query(
        """SELECT id, date, machine, type_intervention, description, statut, 
                  probleme, code_erreur
           FROM interventions 
           WHERE technicien = ? AND statut != 'Terminée'
           ORDER BY date DESC LIMIT 10""",
        (tech_name,)
    )


def get_urgences():
    """Récupère les interventions urgentes/critiques en cours."""
    return _execute_query(
        """SELECT id, date, machine, type_intervention, description, statut, 
                  technicien, probleme, code_erreur
           FROM interventions 
           WHERE statut NOT IN ('Terminée', 'Annulée') 
           AND (priorite = 'Haute' OR priorite = 'Critique' OR priorite IS NULL)
           ORDER BY date DESC LIMIT 15"""
    )


def get_equipements_hs():
    """Récupère les équipements hors service."""
    return _execute_query(
        """SELECT nom, client, fabricant, modele 
           FROM equipements 
           WHERE statut LIKE 'Hors%' OR statut LIKE 'En m%'"""
    )


def update_intervention_statut(interv_id, nouveau_statut, tech_name=""):
    """Met à jour le statut d'une intervention."""
    if nouveau_statut == "Terminée":
        _execute_update(
            "UPDATE interventions SET statut = ?, date_cloture = CURRENT_TIMESTAMP WHERE id = ?",
            (nouveau_statut, interv_id)
        )
    elif tech_name:
        _execute_update(
            "UPDATE interventions SET statut = ?, technicien = ? WHERE id = ?",
            (nouveau_statut, tech_name, interv_id)
        )
    else:
        _execute_update(
            "UPDATE interventions SET statut = ? WHERE id = ?",
            (nouveau_statut, interv_id)
        )
    return True


def enregistrer_telegram_id(tech_id, chat_id):
    """Enregistre le chat_id Telegram d'un technicien."""
    _execute_update(
        "UPDATE techniciens SET telegram_id = ? WHERE id = ?",
        (str(chat_id), tech_id)
    )


# ==========================================
# FORMATTERS
# ==========================================

def format_intervention(interv, show_tech=False):
    """Formatte une intervention pour affichage Telegram."""
    statut_emoji = {
        "En cours": "🔧", "Planifiée": "📅", "En attente": "⏳",
        "Terminée": "✅", "Annulée": "❌"
    }
    s = interv.get("statut", "?")
    emoji = statut_emoji.get(s, "📋")
    
    date_str = str(interv.get("date", ""))[:10]
    machine = interv.get("machine", "?")
    desc = interv.get("description", "")[:80]
    code = interv.get("code_erreur", "")
    interv_id = interv.get("id", "?")
    
    text = f"{emoji} <b>#{interv_id}</b> — {machine}\n"
    text += f"   📅 {date_str} | {s}\n"
    if code:
        text += f"   🔢 Code: {code}\n"
    if desc:
        text += f"   📝 {desc}\n"
    if show_tech and interv.get("technicien"):
        text += f"   👤 {interv.get('technicien')}\n"
    return text


# ==========================================
# HANDLERS TELEGRAM
# ==========================================

async def cmd_start(update, context):
    """Handler /start — enregistrement du technicien."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    chat_id = update.effective_chat.id
    tech = get_technicien_by_telegram(chat_id)
    
    if tech:
        nom = f"{tech.get('nom', '')} {tech.get('prenom', '')}"
        await update.message.reply_html(
            f"✅ Bonjour <b>{nom}</b> !\n\n"
            f"Vous êtes connecté en tant que technicien SIC Radiologie.\n\n"
            f"<b>Commandes disponibles :</b>\n"
            f"/mes_interventions — Vos interventions\n"
            f"/urgences — Pannes critiques\n"
            f"/aide — Aide complète"
        )
    else:
        # Chercher les techniciens sans telegram_id
        techs = _execute_query(
            "SELECT id, nom, prenom FROM techniciens WHERE telegram_id = '' OR telegram_id IS NULL"
        )
        if techs:
            buttons = []
            for t in techs:
                nom = f"{t.get('nom', '')} {t.get('prenom', '')}"
                buttons.append([InlineKeyboardButton(
                    f"👤 {nom}", callback_data=f"register:{t['id']}"
                )])
            await update.message.reply_html(
                "👋 <b>Bienvenue sur SIC Radiologie Bot !</b>\n\n"
                "Pour commencer, identifiez-vous en cliquant sur votre nom :",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        else:
            await update.message.reply_html(
                "⚠️ Tous les techniciens sont déjà enregistrés.\n"
                "Contactez votre administrateur pour être ajouté."
            )


async def cmd_mes_interventions(update, context):
    """Handler /mes_interventions — liste des interventions du technicien."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    chat_id = update.effective_chat.id
    tech = get_technicien_by_telegram(chat_id)
    
    if not tech:
        await update.message.reply_html(
            "⚠️ Vous n'êtes pas enregistré. Tapez /start pour vous connecter."
        )
        return
    
    tech_name = f"{tech.get('nom', '')} {tech.get('prenom', '')}"
    interventions = get_interventions_technicien(tech_name)
    
    if not interventions:
        await update.message.reply_html(
            f"✅ <b>{tech_name}</b>, vous n'avez aucune intervention en cours.\n"
            f"Beau travail ! 🎉"
        )
        return
    
    text = f"🔧 <b>Vos interventions ({len(interventions)}) :</b>\n\n"
    buttons = []
    
    for interv in interventions:
        text += format_intervention(interv) + "\n"
        interv_id = interv.get("id")
        s = interv.get("statut", "")
        
        row = []
        if s != "En cours":
            row.append(InlineKeyboardButton(
                "🔧 En cours", callback_data=f"interv_encours:{interv_id}"
            ))
        row.append(InlineKeyboardButton(
            "✅ Terminer", callback_data=f"interv_terminer:{interv_id}"
        ))
        buttons.append(row)
    
    await update.message.reply_html(
        text, reply_markup=InlineKeyboardMarkup(buttons)
    )


async def cmd_urgences(update, context):
    """Handler /urgences — pannes critiques."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    chat_id = update.effective_chat.id
    tech = get_technicien_by_telegram(chat_id)
    
    urgences = get_urgences()
    equip_hs = get_equipements_hs()
    
    text = "🚨 <b>TABLEAU DE BORD URGENCES</b>\n\n"
    
    if equip_hs:
        text += f"<b>🔴 {len(equip_hs)} équipement(s) hors service/maintenance :</b>\n"
        for eq in equip_hs:
            text += f"  • {eq.get('nom', '?')} ({eq.get('client', '?')}) — {eq.get('fabricant', '')} {eq.get('modele', '')}\n"
        text += "\n"
    
    if urgences:
        text += f"<b>⚡ {len(urgences)} intervention(s) en cours :</b>\n\n"
        buttons = []
        for interv in urgences:
            text += format_intervention(interv, show_tech=True) + "\n"
            interv_id = interv.get("id")
            tech_name = tech.get("nom", "") + " " + tech.get("prenom", "") if tech else ""
            
            row = []
            if not interv.get("technicien"):
                row.append(InlineKeyboardButton(
                    "🤚 Prendre en charge", callback_data=f"interv_prendre:{interv_id}"
                ))
            if interv.get("statut") != "En cours":
                row.append(InlineKeyboardButton(
                    "🔧 En cours", callback_data=f"interv_encours:{interv_id}"
                ))
            row.append(InlineKeyboardButton(
                "✅ Terminer", callback_data=f"interv_terminer:{interv_id}"
            ))
            if row:
                buttons.append(row)
        
        await update.message.reply_html(
            text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
        )
    else:
        text += "✅ Aucune urgence en cours. Tout va bien ! 🎉"
        await update.message.reply_html(text)


async def cmd_aide(update, context):
    """Handler /aide."""
    await update.message.reply_html(
        "📖 <b>SIC Radiologie Bot — Aide</b>\n\n"
        "<b>Commandes :</b>\n"
        "/start — S'enregistrer / Se connecter\n"
        "/mes_interventions — Voir vos interventions\n"
        "/urgences — Pannes critiques en cours\n"
        "/aide — Cette aide\n\n"
        "<b>Actions rapides :</b>\n"
        "Utilisez les boutons sous chaque intervention pour :\n"
        "  🤚 Prendre en charge une intervention\n"
        "  🔧 Marquer \"En cours\"\n"
        "  ✅ Terminer une intervention\n\n"
        "<b>📸 Envoyez une photo :</b>\n"
        "Envoyez une photo d'équipement ou d'erreur et l'IA SIC analysera le problème."
    )


async def callback_handler(update, context):
    """Handler pour les boutons inline."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = query.from_user.id
    tech = get_technicien_by_telegram(chat_id)
    tech_name = f"{tech.get('nom', '')} {tech.get('prenom', '')}" if tech else "Inconnu"
    
    if data.startswith("register:"):
        tech_id = int(data.split(":")[1])
        enregistrer_telegram_id(tech_id, chat_id)
        tech_info = _execute_query(
            "SELECT nom, prenom FROM techniciens WHERE id = ?", (tech_id,), fetch="one"
        )
        nom = f"{tech_info.get('nom', '')} {tech_info.get('prenom', '')}" if tech_info else "?"
        await query.edit_message_text(
            f"✅ <b>{nom}</b>, vous êtes maintenant enregistré !\n\n"
            f"Tapez /mes_interventions pour commencer.",
            parse_mode="HTML"
        )
    
    elif data.startswith("interv_prendre:"):
        interv_id = int(data.split(":")[1])
        update_intervention_statut(interv_id, "En cours", tech_name)
        await query.edit_message_text(
            f"🤚 <b>{tech_name}</b> a pris en charge l'intervention <b>#{interv_id}</b>\n"
            f"Statut → 🔧 En cours",
            parse_mode="HTML"
        )
    
    elif data.startswith("interv_encours:"):
        interv_id = int(data.split(":")[1])
        update_intervention_statut(interv_id, "En cours")
        await query.edit_message_text(
            f"🔧 Intervention <b>#{interv_id}</b> → <b>En cours</b>\n"
            f"👤 {tech_name}",
            parse_mode="HTML"
        )
    
    elif data.startswith("interv_terminer:"):
        interv_id = int(data.split(":")[1])
        update_intervention_statut(interv_id, "Terminée")
        await query.edit_message_text(
            f"✅ Intervention <b>#{interv_id}</b> → <b>Terminée</b>\n"
            f"👤 Clôturée par {tech_name} le {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            parse_mode="HTML"
        )


async def handle_photo(update, context):
    """Handler pour les photos — diagnostic IA."""
    chat_id = update.effective_chat.id
    tech = get_technicien_by_telegram(chat_id)
    
    if not tech:
        await update.message.reply_html("⚠️ Tapez /start pour vous enregistrer.")
        return
    
    await update.message.reply_html("🔍 <b>Analyse IA en cours...</b> Patientez quelques secondes.")
    
    try:
        # Télécharger la photo
        photo = update.message.photo[-1]  # La plus grande résolution
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()
        
        # Appeler Gemini pour le diagnostic
        import google.genai as genai
        from google.genai import types
        
        api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            await update.message.reply_html("⚠️ Clé API Gemini non configurée.")
            return
        
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=bytes(photo_bytes), mime_type="image/jpeg"),
                """Tu es un expert en maintenance d'équipements d'imagerie médicale (radiologie).
                Analyse cette photo et réponds en français :
                1. Quel équipement ou composant est visible ?
                2. Y a-t-il un problème visible ? Si oui, lequel ?
                3. Quelle solution recommandes-tu ?
                4. Quel est le niveau d'urgence (Faible/Moyen/Élevé/Critique) ?
                Sois concis et pratique (réponse de technicien)."""
            ]
        )
        
        diagnostic = response.text if response.text else "Diagnostic non disponible."
        
        await update.message.reply_html(
            f"🧠 <b>Diagnostic IA SIC</b>\n\n{diagnostic}"
        )
    
    except Exception as e:
        logger.error(f"Erreur diagnostic photo: {e}")
        await update.message.reply_html(
            f"❌ Erreur lors de l'analyse : <code>{str(e)[:200]}</code>"
        )


async def handle_text(update, context):
    """Handler pour les messages texte libres."""
    chat_id = update.effective_chat.id
    tech = get_technicien_by_telegram(chat_id)
    
    if not tech:
        await update.message.reply_html("👋 Tapez /start pour commencer !")
        return
    
    text = update.message.text
    
    # Essayer de répondre avec l'IA si c'est une question technique
    try:
        import google.genai as genai
        api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
        if api_key:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"""Tu es un assistant technique pour la maintenance d'équipements 
                d'imagerie médicale (Scanner CT, IRM, Mammographe, etc.).
                Réponds en français, de manière concise et pratique.
                
                Question du technicien: {text}"""
            )
            await update.message.reply_html(
                f"🧠 <b>Assistant IA SIC</b>\n\n{response.text}"
            )
            return
    except Exception as e:
        logger.error(f"Erreur IA: {e}")
    
    await update.message.reply_html(
        "💡 Utilisez les commandes :\n"
        "/mes_interventions — Vos interventions\n"
        "/urgences — Pannes critiques\n"
        "📸 Envoyez une photo pour un diagnostic IA"
    )


# ==========================================
# DÉMARRAGE DU BOT
# ==========================================

def _run_bot_async():
    """Démarre le bot dans une boucle asyncio dédiée."""
    global _bot_running
    try:
        from telegram.ext import (
            ApplicationBuilder, CommandHandler,
            CallbackQueryHandler, MessageHandler, filters
        )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Commandes
        application.add_handler(CommandHandler("start", cmd_start))
        application.add_handler(CommandHandler("mes_interventions", cmd_mes_interventions))
        application.add_handler(CommandHandler("urgences", cmd_urgences))
        application.add_handler(CommandHandler("aide", cmd_aide))
        application.add_handler(CommandHandler("help", cmd_aide))
        
        # Callbacks boutons inline
        application.add_handler(CallbackQueryHandler(callback_handler))
        
        # Photos → diagnostic IA
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        # Messages texte → assistant IA
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        
        logger.info("🤖 Bot Telegram SIC Radiologie — démarrage polling...")
        
        async def _start():
            await application.initialize()
            await application.start()
            await application.updater.start_polling(drop_pending_updates=True)
            logger.info("✅ Bot Telegram polling actif.")
            # Garder le bot en vie
            while True:
                await asyncio.sleep(3600)
        
        loop.run_until_complete(_start())
        
    except Exception as e:
        _bot_running = False
        _bot_error = str(e)
        logger.error(f"❌ Bot Telegram crashed: {e}")
        import traceback
        traceback.print_exc()


def start_bot_thread():
    """Lance le bot dans un thread séparé (appelé depuis app.py)."""
    global _bot_thread, _bot_running, _bot_error
    
    if not TELEGRAM_BOT_TOKEN:
        _bot_error = "TELEGRAM_BOT_TOKEN vide"
        logger.warning("TELEGRAM_BOT_TOKEN non configuré — bot désactivé.")
        return False
    
    if _bot_running and _bot_thread and _bot_thread.is_alive():
        return True
    
    _bot_error = ""
    try:
        _bot_thread = threading.Thread(target=_run_bot_async, daemon=True, name="TelegramBot")
        _bot_thread.start()
        _bot_running = True
        logger.info(f"✅ Thread bot Telegram lancé (token: {TELEGRAM_BOT_TOKEN[:8]}...).")
        return True
    except Exception as e:
        _bot_error = str(e)
        logger.error(f"❌ Erreur lancement bot: {e}")
        return False


def is_bot_running():
    """Vérifie si le bot tourne."""
    return _bot_running and _bot_thread is not None and _bot_thread.is_alive()


def get_bot_error():
    """Retourne l'erreur du bot si présente."""
    return _bot_error

