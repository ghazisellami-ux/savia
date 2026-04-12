# ==========================================
# 🔔 SYSTÈME DE NOTIFICATIONS
# Email (SMTP) + Telegram Bot
# ==========================================
import os
import logging
import smtplib
import urllib.request
import urllib.parse
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)


class NotificationManager:
    """Gestionnaire de notifications Email + Telegram."""

    def __init__(self):
        from dotenv import load_dotenv
        load_dotenv()

        # --- Config Email ---
        self.smtp_server = os.getenv("SMTP_SERVER", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.email_destinataire = os.getenv("EMAIL_DESTINATAIRE", "")

        # --- Config Telegram ---
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        self.email_ok = bool(self.smtp_server and self.smtp_user and self.email_destinataire)
        self.telegram_ok = bool(self.telegram_token and self.telegram_chat_id)

    def envoyer_email(self, sujet: str, corps_html: str) -> bool:
        """Envoie un email via SMTP."""
        if not self.email_ok:
            logger.warning("Email non configuré — notification ignorée.")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = sujet
            msg["From"] = self.smtp_user
            msg["To"] = self.email_destinataire

            msg.attach(MIMEText(corps_html, "html", "utf-8"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, self.email_destinataire, msg.as_string())

            logger.info(f"Email envoyé à {self.email_destinataire}")
            return True

        except Exception as e:
            logger.error(f"Erreur envoi email: {e}")
            return False

    def envoyer_telegram(self, message: str) -> bool:
        """Envoie un message via Telegram Bot API (gratuit)."""
        if not self.telegram_ok:
            logger.warning("Telegram non configuré — notification ignorée.")
            return False

        # --- Nettoyage du message ---
        # 1. Supprimer tous les astérisques (Markdown bold)
        import re
        message = message.replace("*", "")
        # 2. Mettre la première ligne (titre) en MAJUSCULES
        lines = message.split("\n")
        if lines:
            # Extraire le texte brut du titre (sans les tags HTML)
            first_line = lines[0]
            # Uppercase le contenu texte tout en préservant les tags HTML
            def _upper_text(m):
                return m.group(0).upper()
            # Remplacer le texte entre les tags par sa version MAJUSCULE
            lines[0] = re.sub(r'(?<=>)[^<]+(?=<)', _upper_text, first_line)
            # Si pas de tags HTML, uppercase toute la ligne
            if '<' not in first_line:
                lines[0] = first_line.upper()
            message = "\n".join(lines)

        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
            }).encode("utf-8")

            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())

            if result.get("ok"):
                logger.info("Message Telegram envoyé avec succès.")
                return True
            else:
                logger.error(f"Telegram erreur: {result}")
                return False

        except Exception as e:
            logger.error(f"Erreur envoi Telegram: {e}")
            return False

    def notifier_panne_critique(self, machine: str, code: str, message: str,
                                 severite: str = "CRITIQUE", client: str = ""):
        """Envoie une alerte pour panne critique (email + Telegram)."""
        horodatage = datetime.now().strftime("%d/%m/%Y %H:%M")
        client_line = f"\n🏢 Client : <b>{client}</b>" if client else ""

        # --- Telegram ---
        msg_telegram = (
            f"🚨 <b>ALERTE CRITIQUE — SIC Radiologie</b>\n\n"
            f"🖥️ Machine : <b>{machine}</b>{client_line}\n"
            f"🔴 Code : <code>{code}</code>\n"
            f"📋 Erreur : {message}\n"
            f"⚡ Sévérité : {severite}\n"
            f"🕐 Date : {horodatage}\n\n"
            f"⚙️ Action immédiate requise !"
        )
        result_tg = self.envoyer_telegram(msg_telegram)

        # --- Email ---
        sujet = f"🚨 ALERTE CRITIQUE — {machine} — {code}"
        corps = f"""
        <html><body style="font-family:Arial; background:#0f172a; color:#f1f5f9; padding:20px;">
            <div style="max-width:500px; margin:auto; background:#1e293b; border-radius:12px;
                        border-left:5px solid #ef4444; padding:24px;">
                <h2 style="color:#ef4444; margin-top:0;">🚨 ALERTE CRITIQUE</h2>
                <table style="width:100%; color:#f1f5f9; border-collapse:collapse;">
                    <tr><td style="padding:8px 0;"><b>Machine</b></td>
                        <td style="padding:8px 0;">{machine}</td></tr>
                    {f'<tr><td style="padding:8px 0;"><b>Client</b></td><td style="padding:8px 0;">{client}</td></tr>' if client else ''}
                    <tr><td style="padding:8px 0;"><b>Code</b></td>
                        <td style="padding:8px 0;"><code>{code}</code></td></tr>
                    <tr><td style="padding:8px 0;"><b>Erreur</b></td>
                        <td style="padding:8px 0;">{message}</td></tr>
                    <tr><td style="padding:8px 0;"><b>Sévérité</b></td>
                        <td style="padding:8px 0; color:#ef4444;"><b>{severite}</b></td></tr>
                    <tr><td style="padding:8px 0;"><b>Date</b></td>
                        <td style="padding:8px 0;">{horodatage}</td></tr>
                </table>
                <p style="margin-top:16px; color:#f59e0b;">⚠️ Action immédiate requise.</p>
            </div>
        </body></html>
        """
        result_email = self.envoyer_email(sujet, corps)

        return {"email": result_email, "telegram": result_tg}

    def notifier_prediction(self, machine: str, score: int, jours_restants,
                             date_predite: str):
        """Envoie une alerte prédictive (email + Telegram)."""
        horodatage = datetime.now().strftime("%d/%m/%Y %H:%M")

        urgence = "HAUTE" if score < 30 else "MOYENNE" if score < 60 else "BASSE"
        emoji = "🔴" if score < 30 else "🟠" if score < 60 else "🟢"

        # --- Telegram ---
        msg_telegram = (
            f"🔮 <b>ALERTE PRÉDICTIVE — SIC Radiologie</b>\n\n"
            f"🖥️ Machine : <b>{machine}</b>\n"
            f"{emoji} Score santé : <b>{score}%</b>\n"
            f"📅 Panne estimée : <b>{date_predite}</b>\n"
            f"⏳ Jours restants : <b>{jours_restants}</b>\n"
            f"⚡ Urgence : {urgence}\n"
            f"🕐 Date : {horodatage}\n\n"
            f"🔧 Planifiez une maintenance préventive."
        )
        result_tg = self.envoyer_telegram(msg_telegram)

        # --- Email ---
        bar_color = "#ef4444" if score < 30 else "#f59e0b" if score < 60 else "#10b981"
        sujet = f"🔮 Prédiction Maintenance — {machine} ({score}%)"
        corps = f"""
        <html><body style="font-family:Arial; background:#0f172a; color:#f1f5f9; padding:20px;">
            <div style="max-width:500px; margin:auto; background:#1e293b; border-radius:12px;
                        border-left:5px solid {bar_color}; padding:24px;">
                <h2 style="color:#3b82f6; margin-top:0;">🔮 Alerte Prédictive</h2>
                <table style="width:100%; color:#f1f5f9; border-collapse:collapse;">
                    <tr><td style="padding:8px 0;"><b>Machine</b></td>
                        <td>{machine}</td></tr>
                    <tr><td style="padding:8px 0;"><b>Score Santé</b></td>
                        <td style="color:{bar_color};"><b>{score}%</b></td></tr>
                    <tr><td style="padding:8px 0;"><b>Panne estimée</b></td>
                        <td><b>{date_predite}</b></td></tr>
                    <tr><td style="padding:8px 0;"><b>Jours restants</b></td>
                        <td>{jours_restants}</td></tr>
                    <tr><td style="padding:8px 0;"><b>Urgence</b></td>
                        <td style="color:{bar_color};"><b>{urgence}</b></td></tr>
                </table>
                <p style="margin-top:16px; color:#3b82f6;">
                    🔧 Planifiez une maintenance préventive dès que possible.
                </p>
            </div>
        </body></html>
        """
        result_email = self.envoyer_email(sujet, corps)

        return {"email": result_email, "telegram": result_tg}

    def notifier_nouvelle_intervention(self, machine: str, techniciens_tags: list,
                                       description: str,
                                       type_interv: str = "Corrective",
                                       client: str = ""):
        """
        Notifie l'equipe d'une nouvelle intervention.
        techniciens_tags: liste de tuples (nom, telegram_id)
        """
        # Construire les tags pour tous les techniciens
        tags = []
        for nom, tg_id in techniciens_tags:
            if tg_id:
                tags.append(f"@{tg_id.replace('@', '')}")
            else:
                tags.append(f"<b>{nom}</b>")
        tech_line = ", ".join(tags) if tags else "<b>Non assigné</b>"
        
        client_line = f"\n🏢 Client : <b>{client}</b>" if client else ""
        
        msg_telegram = (
            f"🆕 <b>NOUVELLE INTERVENTION</b>\n\n"
            f"👤 Tech : {tech_line}{client_line}\n"
            f"🏥 Machine : <b>{machine}</b>\n"
            f"🔧 Type : {type_interv}\n"
            f"📝 Description : {description}\n"
            f"🕐 Date : {datetime.now().strftime('%d/%m %H:%M')}\n\n"
            f"👉 Voir sur <b>SAVIA</b>"
        )
        return self.envoyer_telegram(msg_telegram)

    def notifier_nouvelle_maintenance(self, machine: str, technicien: str,
                                      tech_telegram: str, date_prevue: str,
                                      type_maint: str = "Préventive"):
        """Notifie l'équipe d'une maintenance planifiée."""
        tech_tag = f"@{tech_telegram.replace('@', '')}" if tech_telegram else f"<b>{technicien}</b>"
        
        msg_telegram = (
            f"📅 <b>MAINTENANCE PLANIFIÉE</b>\n\n"
            f"👤 Tech : {tech_tag}\n"
            f"🏥 Machine : <b>{machine}</b>\n"
            f"🔧 Type : {type_maint}\n"
            f"🗓️ Date : {date_prevue}\n\n"
            f"👉 Voir sur <b>SAVIA</b>"
        )
        return self.envoyer_telegram(msg_telegram)

    def notifier_cloture_intervention(self, machine: str, techniciens_tags: list,
                                      probleme: str, solution: str,
                                      client: str = ""):
        """
        Notifie la cloture et la solution.
        techniciens_tags: liste de tuples (nom, telegram_id)
        """
        tags = []
        for nom, tg_id in techniciens_tags:
            if tg_id:
                tags.append(f"@{tg_id.replace('@', '')}")
            else:
                tags.append(f"<b>{nom}</b>")
        tech_line = ", ".join(tags) if tags else "<b>Non assigné</b>"
        client_line = f"\n🏢 Client : <b>{client}</b>" if client else ""
        
        msg_telegram = (
            f"✅ <b>INTERVENTION CLÔTURÉE</b>\n\n"
            f"👤 Tech : {tech_line}{client_line}\n"
            f"🏥 Machine : <b>{machine}</b>\n"
            f"🔴 Problème : {probleme}\n"
            f"🟢 Solution : {solution}\n\n"
            f"🧠 <i>La base de connaissances a été mise à jour !</i>"
        )
        return self.envoyer_telegram(msg_telegram)

    def notifier_nouvelle_demande(self, client: str, equipement: str,
                                  urgence: str, description: str,
                                  date_demande: str, demandeur: str = ""):
        """
        Notifie via Telegram qu'une nouvelle demande d'intervention a été soumise.
        """
        # Icône urgence
        urg_icon = "🔴" if urgence == "Haute" else "🟡" if urgence == "Moyenne" else "🟢"

        demandeur_line = f"\n👤 Demandeur : <b>{demandeur}</b>" if demandeur else ""

        msg_telegram = (
            f"📋 <b>NOUVELLE DEMANDE D'INTERVENTION</b>\n\n"
            f"🏢 Client : <b>{client}</b>\n"
            f"🏥 Équipement : <b>{equipement}</b>\n"
            f"{urg_icon} Priorité : <b>{urgence}</b>\n"
            f"📝 Problème : {description}\n"
            f"📅 Date : <b>{date_demande}</b>"
            f"{demandeur_line}\n\n"
            f"👉 Connectez-vous à <b>SIC Radiologie</b> pour traiter cette demande."
        )
        return self.envoyer_telegram(msg_telegram)

    def notifier_traitement_demande(self, client: str, equipement: str,
                                     urgence: str, description: str,
                                     nouveau_statut: str,
                                     technicien: str = "",
                                     notes: str = "",
                                     demandeur: str = "",
                                     date_planifiee: str = ""):
        """
        Notifie via Telegram qu'une demande d'intervention a été traitée
        (acceptée, planifiée ou rejetée).
        """
        # Icône et titre selon le statut
        statut_config = {
            "Acceptée": ("✅", "DEMANDE ACCEPTÉE", "#10b981"),
            "Planifiée": ("📅", "DEMANDE PLANIFIÉE", "#3b82f6"),
            "Rejetée": ("❌", "DEMANDE REJETÉE", "#ef4444"),
        }
        icon, titre, _ = statut_config.get(nouveau_statut, ("📋", f"DEMANDE → {nouveau_statut}", "#64748b"))

        urg_icon = "🔴" if urgence == "Haute" else "🟡" if urgence == "Moyenne" else "🟢"

        tech_line = f"\n👷 Technicien : <b>{technicien}</b>" if technicien else ""
        date_plan_line = f"\n📅 Date planifiée : <b>{date_planifiee}</b>" if date_planifiee else ""
        notes_line = f"\n📌 Notes : {notes}" if notes else ""
        demandeur_line = f"\n👤 Demandeur : <b>{demandeur}</b>" if demandeur else ""

        msg_telegram = (
            f"{icon} <b>{titre}</b>\n\n"
            f"🏢 Client : <b>{client}</b>\n"
            f"🏥 Équipement : <b>{equipement}</b>\n"
            f"{urg_icon} Priorité : <b>{urgence}</b>\n"
            f"📝 Problème : {description}"
            f"{tech_line}"
            f"{date_plan_line}"
            f"{notes_line}"
            f"{demandeur_line}\n\n"
            f"📊 Statut : <b>{nouveau_statut}</b>\n"
            f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        return self.envoyer_telegram(msg_telegram)

    def statut(self):
        """Retourne l'état de la configuration des notifications."""
        return {
            "email_configure": self.email_ok,
            "telegram_configure": self.telegram_ok,
            "email_dest": self.email_destinataire if self.email_ok else None,
        }


# Singleton
_notifier = None

def get_notifier() -> NotificationManager:
    """Retourne l'instance unique du gestionnaire de notifications."""
    global _notifier
    if _notifier is None:
        _notifier = NotificationManager()
    return _notifier
