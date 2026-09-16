"""Scheduled maintenance, notification, stock, and Telegram jobs.

The HTTP API imports individual functions for user-triggered actions.  The
daily batch is run only by :mod:`workers.scheduler`, never by an API replica.
"""

import os
import time
from contextlib import contextmanager
from datetime import datetime

from api.runtime import (
    get_db,
    lire_contrats,
    lire_demandes_intervention,
    lire_equipements,
    lire_interventions,
    lire_notification_schedules,
    lire_planning,
    logger,
    math,
    pd,
    update_piece_parameters_batch,
)
from repositories.contracts import get_contract_equipements
from services.sla_tracking import active_sla_contracts, elapsed_hours, sla_contract_for, sla_start_value
from services.timezone import business_now, configure_process_timezone

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
    Vérifie les maintenances et demandes d'intervention planifiées dans les
    15 prochains jours et envoie un rappel Telegram via le bot technique.

    La fenêtre est volontairement fixe pour éviter que les réglages de contrat
    à long terme (par exemple 40 jours) ne surchargent le rappel quotidien.
    """
    from datetime import date, timedelta
    try:
        df = lire_planning()
        if df is None or df.empty:
            return []
        
        today = date.today()
        reminders = []
        
        for _, row in df.iterrows():
            statut = str(row.get('statut', '') or '').strip()
            if statut not in ('Planifiée', 'En cours'):
                continue

            is_intervention_request = str(row.get('notes') or '').strip().startswith('Demande #')
            
            date_str = str(row.get('date_prevue', '') or '').strip()
            if not date_str:
                continue
            
            try:
                date_prevue = date.fromisoformat(date_str[:10])
                
                reminder_days = 15
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
                        'is_intervention_request': is_intervention_request,
                    })
            except Exception:
                continue
        
        if reminders:
            lines = '\n'.join(
                f"  • <b>{r['machine']}</b>"
                + (f" — {r['client']}" if r['client'] else "")
                + (" — <b>Demande d'intervention</b>" if r.get('is_intervention_request') else "")
                + f"\n    📅 {r['date']} ({r['jours']}j)"
                + (f" | 👨‍🔧 {r['technicien']}" if r['technicien'] else " | ⚠️ <b>Technicien non assigné</b>")
                + (f"\n    📝 {r['description'][:60]}" if r['description'] else "")
                for r in sorted(reminders, key=lambda x: x['jours'])
            )
            
            msg = (
                f"🔧 <b>Rappel des interventions planifiées</b>\n"
                f"<i>{len(reminders)} intervention(s)/maintenance(s) dans les 15 prochains jours :</i>\n\n"
                f"{lines}\n\n"
                f"📅 Vérification SAVIA — {today.strftime('%d/%m/%Y')}"
            )
            _send_telegram(msg)
            logger.info(f"Planning reminder: {len(reminders)} rappel(s) envoyé(s) | Fenêtre: 15 jours")
        return reminders
    except Exception as e:
        logger.error(f"Planning reminder check error: {e}")
        return []


def sync_planning_to_interventions(*, notify=True):
    """
    Synchronise les maintenances arrivées à échéance avec les interventions.

    La synchronisation est rattrapable : une maintenance du jour ou d'une date
    passée, assignée à au moins un technicien, doit être créée ou remise à
    ``En cours`` même si le worker n'a pas tourné le jour prévu.
    """
    from datetime import date
    import unicodedata

    def normalized_status(value):
        return unicodedata.normalize("NFKD", str(value or "")).encode(
            "ascii", "ignore"
        ).decode().lower().replace(" ", "").strip()

    try:
        today = date.today()
        today_str = today.isoformat()
        with get_db() as conn:
            planned = conn.execute(
                """SELECT pm.id, pm.machine, pm.equipement_id, pm.client, pm.technicien_assigne,
                          pm.description, pm.type_maintenance, pm.date_prevue,
                          pm.statut, pm.notes, pm.is_ghost
                   FROM planning_maintenance pm
                   WHERE pm.date_prevue <= %s
                     AND COALESCE(pm.is_ghost, FALSE) = FALSE""",
                (today_str,)
            ).fetchall()

        created = []
        synced = []
        closed_statuses = {"cloturee", "terminee", "realisee", "annulee", "decale"}
        startable_statuses = {"planifiee", "assignee", "enretard"}

        for row in planned:
            pm = dict(row)
            pm_id = pm['id']
            technicien = str(pm.get('technicien_assigne') or '').strip()
            if not technicien or normalized_status(pm.get('statut')) in closed_statuses:
                # Une maintenance échue sans technicien reste visible comme
                # retardée dans le planning, sans créer une intervention vide.
                continue

            machine = pm.get('machine', '')
            client = pm.get('client', '')
            planned_date = str(pm.get('date_prevue') or today_str)[:10]
            # Intervention requests are deliberately accepted by the
            # technician on day J, not auto-started by the maintenance
            # synchronizer.  Their planning row still remains visible (and
            # is rendered overdue when its date is in the past).
            is_intervention_request = str(pm.get('notes') or '').strip().startswith('Demande #')
            type_maintenance = pm.get('type_maintenance', 'Préventive') or 'Préventive'
            is_preventive = 'preventive' in normalized_status(type_maintenance)
            probleme = (
                pm.get('description', '') or ''
                if is_intervention_request
                else 'Maintenance préventive' if is_preventive else ''
            )
            description = pm.get('description', '') or f"Maintenance préventive — {machine}"
            notes = str(pm.get('notes') or '').strip() if is_intervention_request else (
                f"[{client}] Maintenance préventive planifiée #{pm_id}"
                if client else f"Maintenance préventive planifiée #{pm_id}"
            )

            with get_db() as conn:
                linked = conn.execute(
                    """SELECT id, statut, technicien, probleme
                       FROM interventions
                       WHERE planning_id = %s
                       ORDER BY id DESC LIMIT 1""",
                    (pm_id,)
                ).fetchone()
                is_new = not linked
                if is_new:
                    conn.execute(
                        """INSERT INTO interventions
                           (date, machine, equipement_id, client, technicien, type_intervention, description, probleme,
                            statut, priorite, notes, planning_id)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (planned_date, machine, pm.get('equipement_id'), client, technicien, type_maintenance, description, probleme,
                         'Assignée' if is_intervention_request else 'En cours', 'Moyenne', notes, pm_id)
                    )
                    linked = conn.execute(
                        "SELECT id, statut, technicien, probleme FROM interventions "
                        "WHERE planning_id = %s ORDER BY id DESC LIMIT 1",
                        (pm_id,)
                    ).fetchone()

                if not linked:
                    logger.warning("Planning #%s: intervention introuvable après création", pm_id)
                    continue

                intervention_id = linked['id']
                current_status = normalized_status(linked.get('statut'))
                if is_preventive and not str(linked.get('probleme') or '').strip():
                    conn.execute(
                        "UPDATE interventions SET probleme = %s WHERE id = %s",
                        (probleme, intervention_id)
                    )
                if current_status in startable_statuses and not is_intervention_request:
                    conn.execute(
                        """UPDATE interventions
                           SET statut = 'En cours',
                               date_debut_intervention = COALESCE(date_debut_intervention, CURRENT_TIMESTAMP)
                           WHERE id = %s""",
                        (intervention_id,)
                    )
                    current_status = 'encours'

                # Le planning suit l'état réel de l'intervention. Une fiche
                # déjà en attente de pièce ou clôturée n'est pas écrasée.
                if current_status == 'encours':
                    conn.execute(
                        "UPDATE planning_maintenance SET statut = 'En cours' WHERE id = %s",
                        (pm_id,)
                    )

                # Toujours conserver les affectations multi-techniciens, y
                # compris lors d'un rattrapage effectué après le jour J.
                for tech_name in [t.strip() for t in technicien.split(',') if t.strip()]:
                    existing_tech = conn.execute(
                        """SELECT id FROM interventions_techniciens
                           WHERE intervention_id = %s AND technicien_nom ILIKE %s""",
                        (intervention_id, f"%{tech_name}%")
                    ).fetchone()
                    if not existing_tech:
                        conn.execute(
                            """INSERT INTO interventions_techniciens
                               (intervention_id, technicien_nom, statut)
                               VALUES (%s, %s, %s)""",
                            (intervention_id, tech_name, 'Assigné')
                        )

            synced.append(intervention_id)
            if is_new:
                created.append({
                    'intervention_id': intervention_id,
                    'planning_id': pm_id,
                    'machine': machine,
                    'technicien': technicien,
                    'client': client,
                    'date': planned_date,
                })

        if created:
            lines = '\n'.join(
                f"  • <b>#{c['intervention_id']}</b> — {c['machine']}"
                + (f" ({c['client']})" if c['client'] else "")
                + f"\n    👨‍🔧 {c['technicien']}"
                for c in created
            )
            msg = (
                f"🔧 <b>Maintenance Préventive — Jour J</b>\n"
                f"<i>{len(created)} intervention(s) créée(s) automatiquement :</i>\n\n"
                f"{lines}\n\n"
                f"📅 {today.strftime('%d/%m/%Y')}"
            )
            if notify:
                _send_telegram_bot("telegram", msg)

        if synced:
            logger.info(
                "Planning sync: %s intervention(s) synchronisée(s), %s créée(s)",
                len(synced), len(created)
            )
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
    import unicodedata
    try:
        today = date.today()
        sav_alerts = []
        manager_alerts = []

        with get_db() as conn:
            # Interventions clôturées avec date_cloture, non encore facturées
            rows = conn.execute(
                """SELECT i.id, i.machine, i.technicien, i.type_intervention,
                          i.date_cloture, i.notes,
                          COALESCE(i.facture_envoyee, FALSE) as facture_envoyee,
                          COALESCE(i.rappel_facture_envoye, 0) as rappel_facture_envoye
                   FROM interventions i
                   LEFT JOIN billing_cases bc ON bc.intervention_id=i.id
                   WHERE i.statut = 'Cloturee'
                     AND i.date_cloture IS NOT NULL
                     AND COALESCE(i.facture_envoyee, FALSE) = FALSE
                     AND COALESCE(bc.coverage_status, 'unassessed') IN ('unassessed', 'partial', 'billable')
                   ORDER BY i.date_cloture ASC"""
            ).fetchall()

        for row in rows:
            d = dict(row)
            type_intervention = unicodedata.normalize(
                "NFKD", str(d.get('type_intervention') or '')
            ).encode("ascii", "ignore").decode().lower().strip()
            if type_intervention == "preventive":
                # Les maintenances préventives ne génèrent pas de rappel de
                # facturation Telegram après leur clôture.
                continue

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

            # Si pas de technicien principal, récupérer depuis interventions_techniciens
            if not d.get('technicien'):
                with get_db() as conn:
                    tech_rows = conn.execute(
                        "SELECT technicien_nom FROM interventions_techniciens WHERE intervention_id = %s ORDER BY technicien_nom",
                        (d['id'],)
                    ).fetchall()
                    if tech_rows:
                        tech_names = [str(row.get('technicien_nom', '')).strip() for row in tech_rows]
                        d['technicien'] = ', '.join(tech_names)

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
                    conn.execute("UPDATE interventions SET rappel_facture_envoye = 1 WHERE id = %s", (int_id,))

            # Rappel SAV : J+8 (2 jours avant deadline)
            elif jours_depuis >= 8 and rappel_level < 2:
                sav_alerts.append({
                    'id': int_id, 'machine': machine, 'client': client,
                    'technicien': d.get('technicien', ''),
                    'jours_restants': jours_restants,
                    'type': 'urgent',
                })
                with get_db() as conn:
                    conn.execute("UPDATE interventions SET rappel_facture_envoye = 2 WHERE id = %s", (int_id,))

            # Bot Manager : > 10 jours sans facturation
            if jours_depuis > 10 and rappel_level < 3:
                manager_alerts.append({
                    'id': int_id, 'machine': machine, 'client': client,
                    'technicien': d.get('technicien', ''),
                    'jours_retard': jours_depuis - 10,
                })
                with get_db() as conn:
                    conn.execute("UPDATE interventions SET rappel_facture_envoye = 3 WHERE id = %s", (int_id,))

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
        df_demandes = lire_demandes_intervention()
        df_equip = lire_equipements()

        contractual_slas = active_sla_contracts(
            df_contrats.to_dict("records") if df_contrats is not None and not df_contrats.empty else [],
            get_contract_equipements,
        )
        if not contractual_slas:
            return {"danger": 0, "breached": 0}

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
                cl = interv.get("client", "") or machine_client.get(machine, "")
                contract = sla_contract_for(
                    contractual_slas, cl, machine, interv.get("type_intervention", ""),
                )
                if not contract:
                    continue
                sla_h = contract["sla_h"]
                start_str = sla_start_value(interv)
                try:
                    start = pd.to_datetime(start_str)
                    if pd.isna(start):
                        continue
                except Exception:
                    continue

                elapsed_h = elapsed_hours(start_str, now, business_day_start_hour=8)
                if elapsed_h is None:
                    continue
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
                    "contract_id": contract["id"],
                }

                if pct > 100:
                    breached_items.append(item)
                elif pct >= 75:
                    danger_items.append(item)

        # An unanswered request is itself subject to the response SLA.  The
        # previous implementation only monitored interventions after they had
        # been created, leaving the initial contractual response unalerted.
        if df_demandes is not None and not df_demandes.empty:
            active_demands = df_demandes[df_demandes["statut"].isin(["Nouvelle", "En attente"])]
            for _, demand in active_demands.iterrows():
                machine = demand.get("equipement", "")
                cl = demand.get("client", "")
                contract = sla_contract_for(
                    contractual_slas, cl, machine, demand.get("type_intervention", "Corrective"),
                )
                if not contract:
                    continue
                elapsed_h = elapsed_hours(demand.get("date_demande", ""), now)
                if elapsed_h is None:
                    continue
                sla_h = contract["sla_h"]
                pct = round((elapsed_h / sla_h) * 100, 1)
                item = {
                    "id": f"DEM-{demand.get('id', '')}",
                    "machine": machine,
                    "client": cl,
                    "technicien": demand.get("technicien_assigne", ""),
                    "statut": demand.get("statut", ""),
                    "sla_h": sla_h,
                    "elapsed_h": elapsed_h,
                    "remaining_h": round(sla_h - elapsed_h, 1),
                    "pct": pct,
                    "contract_id": contract["id"],
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
                f"\n    📄 Contrat #{d['contract_id']} | ⏱ {d['elapsed_h']}h / {d['sla_h']}h ({d['pct']}%) — reste {max(0, d['remaining_h'])}h"
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
                f"\n    📄 Contrat #{b['contract_id']} | ⏱ {b['elapsed_h']}h / {b['sla_h']}h ({b['pct']}%) — <b>DÉPASSÉ de {_format_hours(b['elapsed_h'] - b['sla_h'])}</b>"
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

        return {"danger": len(danger_items), "breached": len(breached_items)}

    except Exception as e:
        logger.error(f"check_sla_alerts error: {e}")
        return {"danger": 0, "breached": 0}



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


SCHEDULER_LOCK_KEY = 7_241_990_154
SCHEDULER_LAST_RUN_KEY = "scheduled_jobs_last_run"


def _tunis_now() -> datetime:
    """Return the business clock configured by the selected country."""
    configure_process_timezone()
    return business_now()


def _get_scheduler_schedule(bot_key: str = "telegram") -> dict:
    """Read the configurable daily schedule, retaining the historical default."""
    try:
        for schedule in lire_notification_schedules():
            if schedule.get("bot_key") == bot_key:
                return schedule
    except Exception as exc:
        logger.warning("Scheduler could not read notification schedule: %s", exc)
    return {"bot_key": bot_key, "enabled": 1, "hour": 8, "minute": 30, "days_of_week": "1,2,3,4,5,6,7"}


def _is_scheduler_due(schedule: dict, now: datetime) -> bool:
    if int(schedule.get("enabled", 1) or 0) != 1:
        return False
    days = {
        int(day.strip())
        for day in str(schedule.get("days_of_week", "1,2,3,4,5,6,7")).split(",")
        if day.strip().isdigit()
    }
    return (
        now.isoweekday() in days
        and now.hour == int(schedule.get("hour", 8) or 8)
        and now.minute == int(schedule.get("minute", 30) or 30)
    )


def _scheduler_already_ran(run_date: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT valeur FROM config_client WHERE cle = %s", (SCHEDULER_LAST_RUN_KEY,)
        ).fetchone()
        return bool(row and dict(row).get("valeur") == run_date)


def _mark_scheduler_ran(run_date: str) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO config_client (cle, valeur) VALUES (%s, %s)
               ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur""",
            (SCHEDULER_LAST_RUN_KEY, run_date),
        )


@contextmanager
def scheduler_leader_lock():
    """Hold a PostgreSQL session lock while a scheduled batch is running."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT pg_try_advisory_lock(%s) AS acquired", (SCHEDULER_LOCK_KEY,)
        ).fetchone()
        acquired = bool(row and dict(row).get("acquired"))
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute("SELECT pg_advisory_unlock(%s)", (SCHEDULER_LOCK_KEY,))


def run_scheduled_cycle() -> None:
    """Run every daily task once; one failed task must not block the others."""
    jobs = (
        ("planning sync", sync_planning_to_interventions),
        ("garantie", check_garantie_expiry),
        ("contrat", check_contrat_expiry),
        ("planning reminder", check_planning_reminder),
        ("stock alerts", check_stock_alerts),
        ("piece parameters", update_piece_parameters_batch),
        ("facturation reminders", check_facturation_reminders),
        ("SLA alerts", check_sla_alerts),
        ("planning retard", check_planning_retard),
    )
    for name, job in jobs:
        try:
            result = job()
            if name == "piece parameters" and isinstance(result, dict) and not result.get("success", False):
                logger.error("Scheduled piece parameters error: %s", result.get("error"))
        except Exception:
            logger.exception("Scheduled job failed: %s", name)


def run_scheduler_once(now: datetime | None = None) -> str:
    """Evaluate and execute one polling iteration; kept separate for testing."""
    now = now or _tunis_now()
    schedule = _get_scheduler_schedule()
    if not _is_scheduler_due(schedule, now):
        return "not_due"

    run_date = now.date().isoformat()
    with scheduler_leader_lock() as is_leader:
        if not is_leader:
            logger.info("Scheduler standby: another executor owns the PostgreSQL lock")
            return "standby"
        if _scheduler_already_ran(run_date):
            logger.info("Scheduler cycle already completed for %s", run_date)
            return "already_completed"
        logger.info("Scheduler cycle starting for %s", run_date)
        run_scheduled_cycle()
        _mark_scheduler_ran(run_date)
        logger.info("Scheduler cycle completed for %s", run_date)
        return "completed"


def run_scheduler_forever(*, poll_seconds: int | None = None) -> None:
    """Polling loop for the dedicated worker process, not for API replicas."""
    poll_seconds = poll_seconds or int(os.getenv("SCHEDULER_POLL_SECONDS", "30"))
    poll_seconds = max(5, poll_seconds)
    logger.info("Scheduler worker started; poll interval=%ss", poll_seconds)
    while True:
        try:
            process_telegram_outbox()
            run_scheduler_once()
        except Exception:
            logger.exception("Scheduler loop error")
        time.sleep(poll_seconds)


def _start_garantie_daemon():
    """Lance un thread démon qui vérifie garanties + contrats + rappels planning + sync + facturation toutes les 24h."""
    import threading, time
    LOCK_KEY = "notif_daemon_last_run"

    def _already_ran_today() -> bool:
        """Vérifie si les notifications ont déjà été envoyées aujourd'hui (évite les doublons lors des redéploiements)."""
        from datetime import date
        try:
            with get_db() as conn:
                row = conn.execute("SELECT valeur FROM config_client WHERE cle = %s", (LOCK_KEY,)).fetchone()
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
                    """INSERT INTO config_client (cle, valeur) VALUES (%s, %s)
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
            # Requête PostgreSQL sur la configuration des notifications.
            rows = conn.execute(
                "SELECT cle, valeur FROM config_client WHERE cle = %s OR cle = %s",
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


def send_telegram_reliably(bot_key: str, message: str, dedupe_key: str = "") -> bool:
    """Send now and queue a retry when the caller supplied an operation key.

    The intervention mutation is not retried when Telegram is temporarily
    unavailable. Only the notification is persisted and retried by the
    scheduler, preventing duplicate status/history/stock side effects.
    """
    delivered = _send_telegram_bot(bot_key, message)
    if delivered or not dedupe_key:
        return delivered
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO telegram_outbox(dedupe_key, bot_key, message)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (dedupe_key, bot_key) DO NOTHING""",
                (dedupe_key, bot_key, message),
            )
        logger.warning("Telegram queued for retry: bot=%s key=%s", bot_key, dedupe_key)
    except Exception:
        logger.exception("Unable to queue Telegram notification: bot=%s key=%s", bot_key, dedupe_key)
    return False


def notify_workshop_transfer(
    intervention_id: int,
    operation_id: str = "",
    overrides: dict | None = None,
) -> dict:
    """Notify both technical and SAV teams after a workshop transfer is saved."""
    from html import escape

    overrides = overrides or {}
    try:
        with get_db() as conn:
            row = conn.execute(
                """SELECT i.machine, i.technicien, i.type_intervention,
                          i.priorite, i.probleme, i.description, i.cause,
                          i.code_erreur, i.type_erreur, i.notes,
                          i.date_transfert_atelier,
                          COALESCE(
                              NULLIF(i.client, ''),
                              (SELECT e.client FROM equipements e
                               WHERE LOWER(e.nom) = LOWER(i.machine)
                               ORDER BY e.id LIMIT 1),
                              ''
                          ) AS client
                   FROM interventions i
                   WHERE i.id = %s""",
                (intervention_id,),
            ).fetchone()
    except Exception:
        logger.exception(
            "Impossible de préparer la notification de transfert atelier pour #%s",
            intervention_id,
        )
        return {"telegram": False, "telegram_sav": False}

    if not row:
        logger.warning(
            "Intervention #%s introuvable pour la notification de transfert atelier",
            intervention_id,
        )
        return {"telegram": False, "telegram_sav": False}

    data = dict(row)

    def value(key: str, fallback: str = "", max_length: int = 350) -> str:
        raw = overrides.get(key)
        if raw is None or str(raw).strip() == "":
            raw = data.get(key, fallback)
        text = str(raw or fallback).strip()
        if len(text) > max_length:
            text = text[:max_length - 1].rstrip() + "…"
        return escape(text)

    declaring_technician = value("technicien_declarant") or value("technicien", "Non renseigné")
    assigned_team = value("technicien", "Non renseigné")
    problem = value("probleme", max_length=600) or value("description", "Non renseigné", 600)
    transfer_time = datetime.now().strftime("%d/%m/%Y %H:%M")

    lines = [
        f"🏭 <b>TRANSFERT VERS L'ATELIER — #{intervention_id}</b>",
        "",
        f"🔧 Équipement : <b>{value('machine', 'Non renseigné')}</b>",
        f"🏥 Client / site : <b>{value('client', 'Non renseigné')}</b>",
        f"👷 Technicien déclarant : <b>{declaring_technician}</b>",
    ]
    if assigned_team and assigned_team != declaring_technician:
        lines.append(f"👥 Équipe assignée : {assigned_team}")
    lines.extend([
        f"🔹 Type : {value('type_intervention', 'Non renseigné')}",
        f"⚡ Priorité : {value('priorite', 'Non renseignée')}",
        f"🔴 Problème : {problem}",
    ])
    if value("cause", max_length=500):
        lines.append(f"🔍 Diagnostic / cause : {value('cause', max_length=500)}")
    if value("type_erreur"):
        lines.append(f"🧩 Type d'erreur : {value('type_erreur')}")
    if value("code_erreur"):
        lines.append(f"💻 Code erreur : {value('code_erreur')}")
    if value("notes", max_length=500):
        lines.append(f"📝 Notes : {value('notes', max_length=500)}")
    lines.extend([
        "",
        "📌 Statut équipement : <b>En atelier</b>",
        "⚠️ Suivi requis : réparation en atelier puis retour sur site à confirmer avant clôture.",
        f"🕐 Transfert déclaré le {transfer_time}",
    ])
    message = "\n".join(lines)
    dedupe_key = f"{operation_id}:workshop-transfer" if operation_id else ""

    return {
        "telegram": send_telegram_reliably("telegram", message, dedupe_key),
        "telegram_sav": send_telegram_reliably("telegram_sav", message, dedupe_key),
    }


def process_telegram_outbox(limit: int = 50) -> int:
    """Retry pending messages once per scheduler poll and mark successes."""
    sent = 0
    try:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT id, bot_key, message
                   FROM telegram_outbox
                   WHERE sent_at IS NULL
                   ORDER BY created_at
                   LIMIT %s""",
                (limit,),
            ).fetchall()
        for row in rows:
            ok = _send_telegram_bot(row["bot_key"], row["message"])
            with get_db() as conn:
                if ok:
                    conn.execute(
                        """UPDATE telegram_outbox
                           SET sent_at = CURRENT_TIMESTAMP,
                               attempts = attempts + 1,
                               last_error = ''
                           WHERE id = %s""",
                        (row["id"],),
                    )
                    sent += 1
                else:
                    conn.execute(
                        """UPDATE telegram_outbox
                           SET attempts = attempts + 1,
                               last_error = %s
                           WHERE id = %s""",
                        ("Telegram indisponible", row["id"]),
                    )
    except Exception:
        logger.exception("Telegram outbox processing failed")
    return sent

__all__ = [
    "check_garantie_expiry",
    "check_planning_reminder",
    "sync_planning_to_interventions",
    "check_stock_alerts",
    "check_facturation_reminders",
    "check_sla_alerts",
    "check_planning_retard",
    "check_contrat_expiry",
    "run_scheduled_cycle",
    "run_scheduler_once",
    "run_scheduler_forever",
    "scheduler_leader_lock",
    "_df_to_records",
    "_send_telegram_bot",
    "_send_telegram",
    "send_telegram_reliably",
    "process_telegram_outbox",
]
