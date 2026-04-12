# ==========================================
# 🔍 ANALYSEUR DE LOGS INTELLIGENT
# ==========================================
import os
import re
import csv
import io
import pandas as pd


def _detecter_format_csv(contenu):
    """
    Détecte si le contenu est un fichier CSV avec champs entre guillemets.
    Retourne True si c'est un CSV structuré type Giotto/IMS.
    """
    lines = contenu.strip().split("\n")
    # Vérifier les premières lignes non-vides
    count_csv = 0
    for line in lines[:20]:
        line = line.strip()
        if line and line.startswith('"') and '","' in line:
            count_csv += 1
    return count_csv >= 3


def _parse_csv_log(contenu, hex_db, sol_db=None):
    """
    Parse un fichier log au format CSV avec champs entre guillemets.
    Format type Giotto: "ID","Timestamp","Version","Level","Code","Message","SubCode","SubMessage",...
    Extrait intelligemment : Code numérique, Message propre, Niveau.
    """
    evenements = []
    reader = csv.reader(io.StringIO(contenu))

    for row in reader:
        if len(row) < 6:
            continue

        # Champs de base
        try:
            entry_id = row[0].strip()
            timestamp = row[1].strip()
            version = row[2].strip()
            level = row[3].strip()
            code_num = row[4].strip()
            message = row[5].strip()
        except (IndexError, ValueError):
            continue

        # Ignorer les lignes Info qui ne sont pas des erreurs/alarmes
        if level == "Info":
            # Mais garder les lignes avec "Error" dans le message
            if "Error" not in message and "Fault" not in message:
                continue

        # Déterminer la sévérité
        if level == "Alarm":
            severite = "ERREUR"
        elif level in ("Critical", "Fatal"):
            severite = "CRITIQUE"
        elif level == "Warning":
            severite = "ATTENTION"
        else:
            severite = "ATTENTION"

        # Sub-code et sub-message (champs 6 et 7 si disponibles)
        sub_code = row[6].strip() if len(row) > 6 else ""
        sub_message = row[7].strip() if len(row) > 7 else ""

        # Construire le message propre (sans guillemets, sans state data)
        msg_clean = message
        if sub_message and sub_message != message:
            msg_clean = f"{message} — {sub_message}"

        # Extraire les états en erreur (State Error) pour enrichir le diagnostic
        etats_erreur = []
        i = 8
        while i + 1 < len(row):
            name = row[i].strip() if i < len(row) else ""
            val = row[i + 1].strip() if i + 1 < len(row) else ""
            if val == "State Error":
                etats_erreur.append(name)
            i += 2

        if etats_erreur:
            msg_clean += f" [{', '.join(etats_erreur)}]"

        # --- Rechercher dans la base de données ---
        found_info = None
        found_sol = None
        statut = "INCONNU"

        # 1) Chercher le code numérique dans hex_db
        if code_num and hex_db.get(code_num):
            found_info = hex_db[code_num]
            statut = "Connue"

        # 2) Chercher le sub_code dans hex_db
        if not found_info and sub_code and hex_db.get(sub_code):
            found_info = hex_db[sub_code]
            statut = "Connue"

        # 3) Recherche dans le texte du message pour tout code connu
        if not found_info:
            line_upper = (message + " " + sub_message).upper()
            for db_code, info in hex_db.items():
                if len(db_code) >= 3 and db_code.upper() in line_upper:
                    found_info = info
                    statut = "Connue"
                    code_num = db_code
                    break

        # 4) Recherche mots-clés dans sol_db
        if sol_db:
            search_text = (message + " " + sub_message).upper()
            best_match = None
            best_len = 0
            for mot_cle, sol_info in sol_db.items():
                mk = mot_cle.upper()
                if len(mk) >= 3 and mk in search_text and len(mk) > best_len:
                    best_match = sol_info
                    best_len = len(mk)
                    if not found_info:
                        code_num = mot_cle
                        statut = "Connue"
            found_sol = best_match

        evenements.append({
            "Timestamp": timestamp,
            "Code": code_num,
            "Message": msg_clean,
            "Statut": statut,
            "Source": "CSV",
            "Type": found_info["Type"] if found_info else (found_sol.get("Type", "?") if found_sol else "?"),
            "Severite": severite,
            "Raw": ",".join(row[:8]) if len(row) >= 8 else ",".join(row),
        })

    return evenements


def _parse_text_log(contenu, hex_db, sol_db=None):
    """
    Parse un fichier log au format texte libre (syslog, .log classique).
    Détecte les codes structurés, hex, et mots-clés.
    """
    lines = contenu.split("\n")
    evenements = []

    pat_timestamp = r"(\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}:\d{2})"
    pat_code_struct = r"(?:Code|code|ERR|Err|ERROR|error|FAULT|fault)[:\s]+([0-9A-Fa-f]{4,8})"
    pat_hex_isole = r"(?<![0-9A-Za-z])0x([0-9A-Fa-f]{2,8})(?![0-9A-Za-z])"

    for line in lines:
        line = line.strip()
        if not line:
            continue

        ts_match = re.search(pat_timestamp, line)
        timestamp = ts_match.group(1) if ts_match else ""
        line_sans_ts = re.sub(pat_timestamp, "", line).strip() if timestamp else line

        # Sévérité
        if re.search(r"\b(CRITICAL|FATAL|CRITIQUE)\b", line, re.IGNORECASE):
            severite = "CRITIQUE"
        elif re.search(r"\b(ERROR|ERREUR)\b", line, re.IGNORECASE) and not re.search(r"[\\/]\w*error\w*\.", line, re.IGNORECASE):
            severite = "ERREUR"
        elif re.search(r"\b(WARNING|WARN|ATTENTION)\b", line, re.IGNORECASE) and not re.search(r"[\\/]\w*warn\w*\.", line, re.IGNORECASE):
            severite = "ATTENTION"
        else:
            severite = ""

        # ---- 1) Code structuré (Code XXXX, err XXXX) ----
        struct_match = re.search(pat_code_struct, line_sans_ts)
        if struct_match:
            code = struct_match.group(1).strip().upper()
            msg_match = re.search(
                r"(?:Code|code|ERR|Err|ERROR|error|FAULT|fault)[:\s]+[0-9A-Fa-f]{4,8}\s*[-:]\s*(.+)",
                line_sans_ts
            )
            message_extrait = msg_match.group(1).strip()[:120] if msg_match else ""
            info = hex_db.get(code)
            evenements.append({
                "Timestamp": timestamp,
                "Code": code,
                "Message": info["Msg"] if info else (message_extrait or "Erreur Inconnue"),
                "Statut": "Connue" if info else "INCONNU",
                "Source": "HEXA",
                "Type": info["Type"] if info else "?",
                "Severite": severite or (info.get("Level", "ATTENTION") if info else "ATTENTION"),
                "Raw": line,
            })
            continue

        # ---- 2) Code hex 0xNNNN ----
        hex_match = re.search(pat_hex_isole, line_sans_ts)
        if hex_match:
            code = hex_match.group(1).strip().upper()
            info = hex_db.get(code)
            evenements.append({
                "Timestamp": timestamp,
                "Code": code,
                "Message": info["Msg"] if info else "Erreur Inconnue",
                "Statut": "Connue" if info else "INCONNU",
                "Source": "HEXA",
                "Type": info["Type"] if info else "?",
                "Severite": severite or (info.get("Level", "ATTENTION") if info else "ATTENTION"),
                "Raw": line,
            })
            continue

        # ---- 3) Mots-clés textuels ----
        if severite:
            msg_clean = re.sub(r"\[.*?\]", "", line_sans_ts).strip()
            msg_clean = re.sub(r"^\d+\s*", "", msg_clean).strip()

            found_in_db = False
            line_upper = line.upper()

            # 3a) Chercher un code de hex_db dans le texte
            for db_code, info in hex_db.items():
                if len(db_code) >= 3 and db_code in line_upper:
                    evenements.append({
                        "Timestamp": timestamp,
                        "Code": db_code,
                        "Message": info["Msg"],
                        "Statut": "Connue",
                        "Source": "TEXTE→HEXA",
                        "Type": info["Type"],
                        "Severite": severite or info.get("Level", "ATTENTION"),
                        "Raw": line,
                    })
                    found_in_db = True
                    break

            # 3b) Chercher mots-clés sol_db dans le texte
            if not found_in_db and sol_db:
                best_match = None
                best_code = None
                best_len = 0
                for mot_cle, sol_info in sol_db.items():
                    mk = mot_cle.upper()
                    if len(mk) >= 3 and mk in line_upper and len(mk) > best_len:
                        best_match = sol_info
                        best_code = mot_cle
                        best_len = len(mk)
                if best_match:
                    evenements.append({
                        "Timestamp": timestamp,
                        "Code": best_code,
                        "Message": msg_clean[:120] if msg_clean else line[:100],
                        "Statut": "Connue",
                        "Source": "TEXTE→SOL",
                        "Type": best_match.get("Type", "Log"),
                        "Severite": severite,
                        "Raw": line,
                    })
                    found_in_db = True

            # 3c) Rien trouvé
            if not found_in_db:
                evenements.append({
                    "Timestamp": timestamp,
                    "Code": "TXT",
                    "Message": msg_clean[:120] if msg_clean else line[:100],
                    "Statut": "Texte",
                    "Source": "TXT",
                    "Type": "Log",
                    "Severite": severite,
                    "Raw": line,
                })

    return evenements


def analyser_log(contenu, hex_db, sol_db=None):
    """
    Analyse intelligente du contenu d'un fichier log.
    Détecte automatiquement le format (CSV structuré ou texte libre)
    et applique le parseur approprié.
    Retourne un DataFrame d'événements.
    """
    if _detecter_format_csv(contenu):
        evenements = _parse_csv_log(contenu, hex_db, sol_db)
    else:
        evenements = _parse_text_log(contenu, hex_db, sol_db)

    return pd.DataFrame(evenements)


def scanner_dossier_logs(folder_path, hex_db, sol_db=None):
    """
    Scanne un dossier de logs et retourne un résumé de l'état du parc.
    Retourne une liste de dicts : {Machine, État, Erreurs, Critiques, Chemin, DataFrame}.
    """
    fleet = []

    if not os.path.exists(folder_path):
        return fleet

    for root, dirs, files in os.walk(folder_path):
        for file_name in files:
            # Ignorer uniquement les fichiers binaires connus
            skip_ext = (".xlsx", ".xls", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".exe", ".dll")
            if file_name.lower().endswith(skip_ext):
                continue

            file_path = os.path.join(root, file_name)
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    contenu = f.read()
            except Exception:
                continue

            df_err = analyser_log(contenu, hex_db, sol_db)

            nb_erreurs = len(df_err)
            nb_critiques = 0
            if not df_err.empty and "Severite" in df_err.columns:
                nb_critiques = len(df_err[df_err["Severite"] == "CRITIQUE"])

            if nb_critiques > 0:
                etat = "🔴 CRITIQUE"
            elif nb_erreurs > 0:
                etat = "🟠 ATTENTION"
            else:
                etat = "🟢 OK"

            fleet.append({
                "Machine": file_name,
                "État": etat,
                "Erreurs": nb_erreurs,
                "Critiques": nb_critiques,
                "Chemin": file_path,
                "df_erreurs": df_err,
            })

    fleet.sort(key=lambda x: (
        0 if "CRITIQUE" in x["État"] else (1 if "ATTENTION" in x["État"] else 2)
    ))

    return fleet
