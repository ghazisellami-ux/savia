"""Dated work-session persistence for mono- and multi-technician interventions."""

from datetime import date, datetime, time, timedelta

from database.core import get_db


def _minutes_between(start_value: str, end_value: str) -> int:
    try:
        start = datetime.strptime(start_value, "%H:%M")
        end = datetime.strptime(end_value, "%H:%M")
    except (TypeError, ValueError) as exc:
        raise ValueError("Les heures doivent utiliser le format HH:MM") from exc
    minutes = int((end - start).total_seconds() // 60)
    if minutes <= 0:
        minutes += 24 * 60
    return minutes


def validate_work_sessions(raw_sessions) -> list[dict]:
    if not isinstance(raw_sessions, list) or not raw_sessions:
        raise ValueError("Ajoutez au moins un créneau de travail")

    validated: list[dict] = []
    seen_entries: set[str] = set()
    intervals: list[tuple[datetime, datetime]] = []
    for raw in raw_sessions:
        if not isinstance(raw, dict):
            raise ValueError("Format de créneau invalide")
        entry_uuid = str(raw.get("entry_uuid") or "").strip()
        work_date = str(raw.get("work_date") or "").strip()
        start_time = str(raw.get("start_time") or "")[:5]
        end_time = str(raw.get("end_time") or "")[:5]
        if not entry_uuid or len(entry_uuid) > 128 or entry_uuid in seen_entries:
            raise ValueError("Identifiant de créneau invalide ou dupliqué")
        seen_entries.add(entry_uuid)
        try:
            parsed_date = date.fromisoformat(work_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("Date de travail invalide") from exc
        duration = _minutes_between(start_time, end_time)
        try:
            travel = int(raw.get("travel_minutes") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Temps de déplacement invalide") from exc
        if travel < 0:
            raise ValueError("Le temps de déplacement ne peut pas être négatif")

        start_at = datetime.combine(parsed_date, time.fromisoformat(start_time))
        end_at = start_at + timedelta(minutes=duration)
        if any(start_at < existing_end and end_at > existing_start for existing_start, existing_end in intervals):
            raise ValueError("Deux créneaux du même technicien se chevauchent")
        intervals.append((start_at, end_at))
        validated.append({
            "entry_uuid": entry_uuid,
            "work_date": work_date,
            "start_time": start_time,
            "end_time": end_time,
            "duration_minutes": duration,
            "travel_minutes": travel,
        })
    return validated


def list_work_sessions(intervention_id: int, include_deleted: bool = False) -> list[dict]:
    deleted_filter = "" if include_deleted else "AND deleted_at IS NULL"
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT id, entry_uuid, intervention_id, intervention_technicien_id,
                       technicien_nom, work_date, start_time, end_time,
                       duration_minutes, travel_minutes, created_at, updated_at, deleted_at
                FROM intervention_work_sessions
                WHERE intervention_id = %s {deleted_filter}
                ORDER BY work_date, start_time, technicien_nom, id""",
            (intervention_id,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for field in ("work_date", "created_at", "updated_at"):
            value = item.get(field)
            if hasattr(value, "isoformat"):
                item[field] = value.isoformat()
        for field in ("start_time", "end_time"):
            value = item.get(field)
            if hasattr(value, "strftime"):
                item[field] = value.strftime("%H:%M")
        result.append(item)
    return result


def replace_technician_work_sessions(
    intervention_id: int,
    assignment_id: int,
    technician_name: str,
    raw_sessions,
    updated_by: str,
) -> list[dict]:
    sessions = validate_work_sessions(raw_sessions)
    entry_ids = [session["entry_uuid"] for session in sessions]
    with get_db() as conn:
        conn.execute(
            """UPDATE intervention_work_sessions
               SET intervention_technicien_id = %s, updated_at = CURRENT_TIMESTAMP
               WHERE intervention_id = %s AND intervention_technicien_id IS NULL
                 AND LOWER(BTRIM(technicien_nom)) = LOWER(BTRIM(%s))""",
            (assignment_id, intervention_id, technician_name),
        )
        existing_entries = conn.execute(
            """SELECT entry_uuid, intervention_technicien_id
               FROM intervention_work_sessions
               WHERE intervention_id = %s AND entry_uuid = ANY(%s)""",
            (intervention_id, entry_ids),
        ).fetchall()
        if any(int(row.get("intervention_technicien_id") or 0) != assignment_id for row in existing_entries):
            raise ValueError("Un créneau appartient déjà à un autre technicien")
        conn.execute(
            """UPDATE intervention_work_sessions
               SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, updated_by = %s
               WHERE intervention_id = %s AND intervention_technicien_id = %s
                 AND deleted_at IS NULL AND NOT (entry_uuid = ANY(%s))""",
            (updated_by, intervention_id, assignment_id, entry_ids),
        )
        for session in sessions:
            conn.execute(
                """INSERT INTO intervention_work_sessions
                       (entry_uuid, intervention_id, intervention_technicien_id,
                        technicien_nom, work_date, start_time, end_time,
                        duration_minutes, travel_minutes, created_by, updated_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (intervention_id, entry_uuid) DO UPDATE SET
                       intervention_technicien_id = EXCLUDED.intervention_technicien_id,
                       technicien_nom = EXCLUDED.technicien_nom,
                       work_date = EXCLUDED.work_date,
                       start_time = EXCLUDED.start_time,
                       end_time = EXCLUDED.end_time,
                       duration_minutes = EXCLUDED.duration_minutes,
                       travel_minutes = EXCLUDED.travel_minutes,
                       updated_by = EXCLUDED.updated_by,
                       updated_at = CURRENT_TIMESTAMP,
                       deleted_at = NULL""",
                (
                    session["entry_uuid"], intervention_id, assignment_id,
                    technician_name, session["work_date"], session["start_time"],
                    session["end_time"], session["duration_minutes"],
                    session["travel_minutes"], updated_by, updated_by,
                ),
            )

        totals = conn.execute(
            """SELECT COALESCE(SUM(duration_minutes), 0) AS duration_minutes,
                      COALESCE(SUM(travel_minutes), 0) AS travel_minutes,
                      MIN(start_time) AS first_start, MAX(end_time) AS last_end
               FROM intervention_work_sessions
               WHERE intervention_id = %s AND intervention_technicien_id = %s
                 AND deleted_at IS NULL""",
            (intervention_id, assignment_id),
        ).fetchone()
        conn.execute(
            """UPDATE interventions_techniciens
               SET heure_debut_tech = %s, heure_fin_tech = %s,
                   duree_minutes_tech = %s, duree_deplacement_tech = %s,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (
                totals.get("first_start"), totals.get("last_end"),
                totals.get("duration_minutes", 0), totals.get("travel_minutes", 0),
                assignment_id,
            ),
        )
        parent_totals = conn.execute(
            """SELECT COALESCE(SUM(duration_minutes), 0) AS duration_minutes,
                      COALESCE(SUM(travel_minutes), 0) AS travel_minutes,
                      MIN(start_time) AS first_start, MAX(end_time) AS last_end
               FROM intervention_work_sessions
               WHERE intervention_id = %s AND deleted_at IS NULL""",
            (intervention_id,),
        ).fetchone()
        conn.execute(
            """UPDATE interventions
               SET duree_minutes = %s, duree_deplacement = %s,
                   start_time = %s, end_time = %s
               WHERE id = %s""",
            (
                parent_totals.get("duration_minutes", 0), parent_totals.get("travel_minutes", 0),
                parent_totals.get("first_start"), parent_totals.get("last_end"), intervention_id,
            ),
        )
    return list_work_sessions(intervention_id)
