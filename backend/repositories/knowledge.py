"""Knowledge-base persistence and legacy text normalization."""

import pandas as pd
from datetime import datetime

from database.core import get_db, logger, read_sql

__all__ = [
    "_fix_text",
    "_fix_df_text",
    "lire_historique",
    "lire_base",
    "ajouter_code",
    "ajouter_codes_batch",
]

# ---- Nettoyage texte double-encodé UTF-8 (à la lecture) ----

_ENCODING_MAP = {
    "Ã©": "é", "Ã¨": "è", "Ãª": "ê", "Ã«": "ë",
    "Ã ": "à", "Ã¢": "â", "Ã¤": "ä",
    "Ã¹": "ù", "Ã»": "û", "Ã¼": "ü",
    "Ã®": "î", "Ã¯": "ï", "Ã´": "ô", "Ã¶": "ö",
    "Ã§": "ç", "Ã‰": "É", "Ãˆ": "È", "Ã€": "À",
    "\u00c3\u0094": "Ô", "\u00c3\u009b": "Û",
}

def _fix_text(val):
    """Corrige un texte double-encodé UTF-8 → UTF-8 correct."""
    if not isinstance(val, str):
        return val
    for broken, correct in _ENCODING_MAP.items():
        if broken in val:
            val = val.replace(broken, correct)
    # Fallback: essayer decode latin1 → utf8
    try:
        val_bytes = val.encode('latin-1')
        decoded = val_bytes.decode('utf-8')
        if decoded != val:
            return decoded
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return val

def _fix_df_text(df, columns=None):
    """Applique _fix_text sur les colonnes texte d'un DataFrame."""
    if df.empty:
        return df
    cols = columns or [c for c in df.columns if df[c].dtype == 'object']
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: _fix_text(v) if isinstance(v, str) else v)
    return df


def lire_historique():
    """
    Lit l'historique complet des pannes.
    
    Returns:
        pd.DataFrame: DataFrame contenant l'historique avec colonnes renommées.
    """
    try:
        with get_db() as conn:
            df = read_sql("SELECT * FROM historique ORDER BY date DESC", conn)
        if not df.empty:
            rename_map = {
                "machine": "Machine", "code": "Code", "type": "Type",
                "severite": "Severite", "resolu": "Resolu",
            }
            df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
            if "date" in df.columns:
                df["Date"] = pd.to_datetime(df["date"], errors="coerce")
            df = _fix_df_text(df)
        return df
    except Exception as e:
        logger.error(f"Erreur lire_historique: {e}")
        return pd.DataFrame()


# ==========================================
# FONCTIONS CRUD — CODES & SOLUTIONS
# ==========================================

def lire_base():
    """Lit les codes et solutions. Retourne (hex_db, sol_db) — même format qu'avant."""
    hex_db = {}
    sol_db = {}

    with get_db() as conn:
        # Codes
        for row in conn.execute("SELECT code, message, niveau, type FROM codes_erreurs").fetchall():
            hex_db[row["code"]] = {
                "Msg": row["message"],
                "Level": row["niveau"],
                "Type": row["type"],
            }

        # Solutions
        for row in conn.execute("SELECT mot_cle, type, priorite, cause, solution FROM solutions").fetchall():
            sol_db[row["mot_cle"]] = {
                "Type": row["type"],
                "Priorité": row["priorite"],
                "Cause": row["cause"],
                "Solution": row["solution"],
            }

    return hex_db, sol_db


def ajouter_code(code, message, cause, solution, type_err, priorite, username="system"):
    """Ajoute ou met à jour un code d'erreur et sa solution."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO codes_erreurs (code, message, type)
            VALUES (%s, %s, %s)
            ON CONFLICT(code) DO UPDATE SET message=excluded.message, type=excluded.type
        """, (code, message[:200], type_err))

        conn.execute("""
            INSERT INTO solutions (mot_cle, type, priorite, cause, solution, validated_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(mot_cle) DO UPDATE SET
                type=excluded.type, priorite=excluded.priorite,
                cause=excluded.cause, solution=excluded.solution,
                validated_by=excluded.validated_by, updated_at=excluded.updated_at
        """, (code, type_err, priorite, cause, solution, username, datetime.now().isoformat()))

    return True


def ajouter_codes_batch(rows_hex, rows_txt):
    """Ajoute des codes en lot."""
    with get_db() as conn:
        for row in rows_hex:
            conn.execute("""
                INSERT INTO codes_erreurs (code, message, niveau, type)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(code) DO UPDATE SET message=excluded.message, niveau=excluded.niveau, type=excluded.type
            """, (row.get("Code", ""), row.get("Message", ""), row.get("Niveau", "ATTENTION"), row.get("Type", "")))

        for row in rows_txt:
            conn.execute("""
                INSERT INTO solutions (mot_cle, type, priorite, cause, solution)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(mot_cle) DO UPDATE SET
                    type=excluded.type, priorite=excluded.priorite,
                    cause=excluded.cause, solution=excluded.solution
            """, (row.get("Mot_Cle", ""), row.get("Type", ""), row.get("Priorite", "MOYENNE"),
                  row.get("Cause", ""), row.get("Solution", "")))

    return True

