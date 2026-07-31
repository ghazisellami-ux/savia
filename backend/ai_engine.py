# ==========================================
# 🧠 MOTEUR IA (GOOGLE GEMINI — SDK google.genai)
# ==========================================
import re
import json
import time
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from google import genai
from google.genai import types
from config import GOOGLE_API_KEY, GOOGLE_API_KEYS
from log_preprocessor import clean_log

logger = logging.getLogger(__name__)

# --- EU AI Act Compliance: Data Anonymization Protocol ---
def mask_pii_locally(text):
    """
    Masque localement les données personnelles (PII) avant envoi à l'IA.
    Remplace les emails, numéros de tel, et formats Sécurité Sociale / Patient ID.
    """
    if not text:
        return text
    # Mask Emails
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[EMAIL_CENSURÉ]', text)
    # Mask numéros de téléphone (formats fr/intl courants)
    text = re.sub(r'(?:(?:\+|00)33|0)\s*[1-9](?:[\s.-]*\d{2}){4}', '[TEL_CENSURÉ]', text)
    # Mask N° SS ou Patient ID suspects (séquences de 10 à 15 chiffres)
    text = re.sub(r'\b\d{10,15}\b', '[ID_PATIENT_CENSURÉ]', text)
    return text

# Modèles à essayer par ordre de préférence (chacun a son propre quota)
_configured_models = os.getenv("GEMINI_MODELS", "gemini-3.1-flash-lite")
MODELS = [model.strip() for model in _configured_models.split(",") if model.strip()]
AI_ATTEMPT_TIMEOUT_SECONDS = max(5, int(os.getenv("GEMINI_ATTEMPT_TIMEOUT_SECONDS", "35")))


def _generation_config(is_json: bool, timeout_seconds: int):
    """Construit une requête Gemini bornée, sans appel de fonction distant."""
    config = {
        "temperature": 0.2,
        "candidate_count": 1,
        "max_output_tokens": 4096,
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        "http_options": types.HttpOptions(
            timeout=timeout_seconds * 1000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
        "safety_settings": [
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        ],
    }
    if is_json:
        config["response_mime_type"] = "application/json"
    return config

# --- Initialisation multi-clés ---
AI_AVAILABLE = False
_clients = []  # Liste de clients Gemini (un par clé API)
_current_key_index = 0  # Index de la clé active

for _key in GOOGLE_API_KEYS:
    try:
        _clients.append(genai.Client(api_key=_key))
    except Exception as e:
        logger.warning(f"Impossible d'initialiser clé API ...{_key[-6:]}: {e}")

if _clients:
    AI_AVAILABLE = True
    logger.info(f"🧠 IA initialisée avec {len(_clients)} clé(s) API × {len(MODELS)} modèles")
else:
    logger.warning("⚠️ Aucune clé API valide. IA non disponible.")

# Compat : garder un `client` pour le code existant
client = _clients[0] if _clients else None


def _call_ia(prompt, timeout=120, is_json=False):
    """
    Appelle l'IA avec rotation automatique et audit trail.
    
    Args:
        prompt (str): Le texte envoyé à l'IA.
        timeout (int): Temps max d'attente.
        is_json (bool): Forcer l'API Gemini à répondre en JSON strict.

        
    Logic:
        Parcourt les modèles du plus performant au plus léger. Pour chaque modèle, 
        essaie d'utiliser les clés API disponibles (Rotation).
    """
    global _current_key_index

    if not _clients:
        logger.error("Tentative d'appel IA sans client initialisé.")
        return None

    total_keys = len(_clients)
    deadline = time.monotonic() + max(1, timeout)
    
    # Audit Trail
    logger.info(f"Initiation Audit Trail IA | Prompt Length: {len(prompt)}")

    for model_name in MODELS:
        keys_tried = 0

        while keys_tried < total_keys:
            current_client = _clients[_current_key_index]
            key_suffix = GOOGLE_API_KEYS[_current_key_index][-6:]

            try:
                remaining_seconds = int(deadline - time.monotonic())
                if remaining_seconds <= 0:
                    logger.warning("AI global timeout reached before another attempt.")
                    return None
                attempt_timeout = min(AI_ATTEMPT_TIMEOUT_SECONDS, remaining_seconds)
                gen_config = _generation_config(is_json, attempt_timeout)

                executor = ThreadPoolExecutor(max_workers=1)
                try:
                    future = executor.submit(
                        current_client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                        config=gen_config
                    )
                    resp = future.result(timeout=attempt_timeout + 2)
                finally:
                    try: executor.shutdown(wait=False, cancel_futures=True)
                    except TypeError: executor.shutdown(wait=False)
                
                # Succès Log (Pillier 3)
                logger.info(f"✅ Décision IA OK | Modèle: {model_name} | Clé: ...{key_suffix}")
                return resp.text

            except FuturesTimeoutError:
                logger.warning(f"⏰ Audit Trail: Timeout {timeout}s sur {model_name} (Clé ...{key_suffix})")
                _current_key_index = (_current_key_index + 1) % total_keys
                keys_tried += 1
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if any(marker in err_str for marker in ("429", "resource_exhausted", "503", "404", "not_found", "timeout", "timed out", "connection")):
                    logger.warning(f"⚠️ Audit Trail: Quota atteint pour {model_name} (Clé ...{key_suffix}). Bascule auto.")
                    _current_key_index = (_current_key_index + 1) % total_keys
                    keys_tried += 1
                else:
                    logger.error(f"❌ Échec Audit Trail IA ({model_name}): {e}")
                    return f"Erreur technique IA ({model_name}) : {e}"

        logger.warning(f"⚠️ Modèle {model_name} épuisé (Quota). Passage au modèle suivant.")

    logger.critical("❌ Audit Trail: Échec total. Tous les modèles et clés sont épuisés.")
    return f"Erreur de Quota IA : {last_error}" if 'last_error' in locals() else "Erreur IA inconnue"


def _call_ia_fast(prompt, timeout=20):
    """
    Version rapide de _call_ia : saute les modèles lents (2.5-flash = thinking model)
    et utilise un timeout court. Idéal pour les analyses légères.
    """
    global _current_key_index

    if not _clients:
        return None

    total_keys = len(_clients)
    fast_models = [m for m in MODELS if "2.5" not in m]  # exclure le thinking model
    if not fast_models:
        fast_models = MODELS[-1:]  # au moins le dernier

    for model_name in fast_models:
        keys_tried = 0
        _current_key_index = 0

        while keys_tried < total_keys:
            current_client = _clients[_current_key_index]
            key_suffix = GOOGLE_API_KEYS[_current_key_index][-6:]

            try:
                attempt_timeout = min(AI_ATTEMPT_TIMEOUT_SECONDS, timeout)
                executor = ThreadPoolExecutor(max_workers=1)
                try:
                    future = executor.submit(
                        current_client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                        config=_generation_config(False, attempt_timeout),
                    )
                    resp = future.result(timeout=attempt_timeout + 2)
                finally:
                    try: executor.shutdown(wait=False, cancel_futures=True)
                    except TypeError: executor.shutdown(wait=False)
                logger.info(f"✅ IA Fast OK ({model_name}, clé ...{key_suffix})")
                return resp.text
            except FuturesTimeoutError:
                logger.warning(f"⏰ Fast timeout {timeout}s ({model_name}, clé ...{key_suffix})")
                _current_key_index = (_current_key_index + 1) % total_keys
                keys_tried += 1
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    logger.warning(f"⚠️ {model_name} clé ...{key_suffix} épuisée (429)")
                    _current_key_index = (_current_key_index + 1) % total_keys
                    keys_tried += 1
                else:
                    logger.error(f"Erreur IA fast ({model_name}): {e}")
                    return None

        logger.warning(f"⚠️ Fast: {model_name} épuisé. Modèle suivant...")

    logger.error("❌ Fast IA: tous les modèles rapides épuisés.")
    return None


def verifier_ia():
    """Teste si l'IA est opérationnelle. Retourne (bool, str) : (ok, message)."""
    if not GOOGLE_API_KEYS:
        return False, "Clé API non configurée"
    if not _clients:
        return False, "Client IA non initialisé"

    # Tester avec un appel léger
    result = _call_ia("Réponds uniquement OK")
    if result and "OK" in result.upper():
        nb = len(_clients)
        return True, f"IA opérationnelle ({nb} clé{'s' if nb > 1 else ''})"
    elif result:
        return True, "IA connectée"
    else:
        return False, f"Toutes les clés/modèles épuisés"


def clean_json_response(text_response):
    """Parse une réponse IA contenant du JSON, même entouré de markdown."""
    if not text_response:
        return None
    text = text_response.strip()
    
    # Supprimer TOUS les blocs markdown (```json, ```, etc.)
    text = re.sub(r'```\w*\s*', '', text)
    text = re.sub(r'```', '', text)
    text = text.strip()

    # Essayer de trouver un objet JSON
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        json_str = text[start : end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e} | Extrait: {json_str[:200]}...")
            # Tentative de réparation: supprimer les virgules traînantes
            json_str_fixed = re.sub(r',\s*}', '}', json_str)
            json_str_fixed = re.sub(r',\s*]', ']', json_str_fixed)
            try:
                return json.loads(json_str_fixed)
            except json.JSONDecodeError:
                pass

    # Essayer un tableau JSON
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        json_str = text[start : end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            json_str_fixed = re.sub(r',\s*]', ']', json_str)
            try:
                return json.loads(json_str_fixed)
            except json.JSONDecodeError:
                pass

    return None


def get_ai_suggestion(code, msg, context, log_context="", equipment_type="", response_language="fr"):
    """
    Demande à l'IA un diagnostic précis.
    Inclut les solutions validées de la base locale pour un apprentissage continu.
    log_context : lignes du fichier log AVANT l'erreur pour contextualiser.
    equipment_type : type d'équipement (ex: Mammographie, Scanner CT, IRM) pour contextualiser le diagnostic.
    Fallback local si l'IA n'est pas disponible.
    Retourne un dict {Probleme, Cause, Solution, Type, Priorite, Confidence_Score} ou None.
    """
    # EU AI Act: Zero-Knowledge Data Masking
    code = mask_pii_locally(code)
    msg = mask_pii_locally(msg)
    context = mask_pii_locally(context)
    log_context = mask_pii_locally(log_context)

    # Récupérer les solutions validées pour enrichir le contexte IA
    solutions_context = ""
    try:
        from db_engine import lire_base
        _, sol_db = lire_base()
        # Chercher des solutions similaires dans la base locale
        similar = []
        code_upper = code.upper() if code else ""
        msg_upper = msg.upper() if msg else ""
        for key, sol in sol_db.items():
            if (code_upper and code_upper in key.upper()) or \
               (msg_upper and any(w in key.upper() for w in msg_upper.split()[:3] if len(w) > 3)):
                similar.append(sol)
            if len(similar) >= 5:
                break

        if similar:
            solutions_context = "\n\nSOLUTIONS VALIDÉES LOCALEMENT (base de connaissances terrain) :\n"
            for i, s in enumerate(similar, 1):
                solutions_context += f"{i}. Cause: {s.get('Cause','')} → Solution: {s.get('Solution','')}\n"
            solutions_context += "\nUtilise ces retours terrain pour affiner ton diagnostic.\n"
    except Exception:
        pass

    # ---- Tentative IA en ligne (avec rotation de clés) ----
    if AI_AVAILABLE:
        # Construire la section "ce que la base contient déjà"
        db_info_section = ""
        if solutions_context:
            db_info_section = f"""
INFORMATION DÉJÀ CONNUE (base de données locale — NE PAS RÉPÉTER) :
{solutions_context}
⚠️ L'utilisateur a DÉJÀ ces informations affichées à l'écran.
Tu dois aller PLUS LOIN que ces données basiques."""

        # Construire la section contexte log
        log_section = ""
        if log_context:
            try:
                # Nettoyer et réduire le contexte log pour éviter les erreurs "prompt is too long"
                from log_preprocessor import clean_log
                clean_context = clean_log(log_context)
            except Exception as e:
                logger.error(f"Erreur lors du nettoyage des logs: {e}")
                clean_context = log_context[-10000:] # fallback rudimentaire
                
            log_section = f"""

CONTEXTE LOG (événements AVANT l'erreur, du plus ancien au plus récent) :
```
{clean_context}
```
⚠️ Analyse cette séquence d'événements pour identifier la chaîne causale qui a mené à l'erreur.
Les étapes précédentes peuvent révéler la vraie cause racine."""

        language_instruction = (
            "IMPORTANT LANGUAGE RULE: Write every user-facing JSON value in English only. Keep JSON keys exactly as requested. If examples or known solutions are in French, translate the generated values to English."
            if str(response_language).lower().startswith("en")
            else "IMPORTANT: Redige toutes les valeurs JSON destinees a l'utilisateur en francais. Garde exactement les cles JSON demandees."
        )

        prompt = f"""Tu es un Ingénieur d'Escalade (Support Niveau 3) spécialisé en radiologie médicale (CT, IRM, RX, Mammo).
Tu dois fournir un diagnostic clinique et technique pointu suite à une anomalie signalée.
{language_instruction}

🚨 Symptômes signalés :
- Code Erreur : "{code}"
- Constat : "{msg}"
- Équipement : "{context}"
- Type d'équipement : "{equipment_type or 'Non spécifié'}"
{db_info_section}
{log_section}

CONTEXTE TECHNIQUE PAR TYPE D'ÉQUIPEMENT:
- Mammographie: Pas de slipring (composant du scanner CT). Les défauts typiques concernent le tube RX, les détecteurs, le système d'imagerie 2D/3D, le réfrigérant, les encodeurs.
- Scanner CT: Risque de slipring, anneaux de slip-ring, détecteurs, haute tension, tube RX rotatif.
- IRM: Bobines RF, gradient, cryogénique (hélium), shimming, détecteur, refroidissement.
- RX (Radiographie): Tube RX, haute tension, système de collimation, détecteur, refroidissement.

RÈGLES :
- Sois BREF et DIRECT (2-3 lignes max par champ)
- Ne donne pas de réponses génériques. Identifie précisément la carte électronique, le composant mécanique (tube RX, inverter, détécteur...), ou la perturbation réseau en cause.
- IMPORTANT: Assure-toi que ta réponse est appropriée au type d'équipement "{equipment_type or 'Unknown'}". Ne suggère pas de composants inexistants sur ce type (ex: pas de slipring sur une Mammographie).
- Définis l'impact immédiat : Y a-t-il un risque d'émission de rayons X incontrôlée ? La machine est-elle immobilisée (Down) ?
- Propose une procédure de dépannage avec les valeurs de test exactes (ex: vérification des tensions au multimètre, purge, etc).
- Si la base contient déjà une solution, NE LA RÉPÈTE PAS — donne un complément utile de niveau 3.
- IMPORTANT: Fournis un Confidence_Score (entier de 0 à 100) représentant ta certitude sur ce diagnostic.

Réponds en JSON strict uniquement :
{{
    "Probleme": "Description technique du défaut et de l'impact immédiat",
    "Cause": "Cause racine identifiée (carte, mécanique, réseau) — PERTINENTE AU TYPE: {equipment_type or 'Unknown'}",
    "Solution": "Procédure de dépannage exacte et ciblée",
    "Prevention": "Action préventive pour éviter la récurrence",
    "Urgence": "Impact clinique : machine utilisable ou non ?",
    "Type": "Hardware|Software|Power|Calibration|Tube RX|Détecteur|Network|Thermal|Autre",
    "Priorite": "HAUTE|MOYENNE|BASSE",
    "Confidence_Score": 95
}}"""
        # Appel IA avec rotation automatique des clés et contrainte JSON strict
        raw_response = _call_ia(prompt, timeout=120, is_json=True)
        if raw_response:
            result = clean_json_response(raw_response)
            if result:
                confidence = int(result.get("Confidence_Score", 0))
                logger.info(f"IA diagnostic OK (confiance: {confidence}%), keys: {list(result.keys())}")
                return result
            else:
                logger.warning(f"IA JSON parsing failed. Raw: {raw_response[:500]}")
                return None

    # ---- Fallback local (mode hors-ligne) ----
    return _fallback_local(code, msg)


def _fallback_local(code, msg):
    """Recherche locale de solution quand l'IA est indisponible."""
    try:
        from db_engine import lire_base
        hex_db, sol_db = lire_base()

        # Chercher par clé exacte
        code_upper = code.upper() if code else ""
        for key, sol in sol_db.items():
            if code_upper and code_upper in key:
                return {
                    "Probleme": f"Erreur {code} détectée — {msg}",
                    "Cause": sol.get("Cause", "Voir base de connaissances"),
                    "Solution": sol.get("Solution", "Consulter la documentation constructeur"),
                    "Type": sol.get("Type", "Autre"),
                    "Priorite": sol.get("Priorité", "MOYENNE"),
                    "_source": "local"
                }

        # Chercher par mots-clés dans le message
        if msg:
            msg_words = [w for w in msg.upper().split() if len(w) > 3]
            best_match = None
            best_score = 0
            for key, sol in sol_db.items():
                score = sum(1 for w in msg_words if w in key.upper())
                if score > best_score:
                    best_score = score
                    best_match = sol
            if best_match and best_score >= 2:
                return {
                    "Probleme": f"Erreur détectée — {msg}",
                    "Cause": best_match.get("Cause", ""),
                    "Solution": best_match.get("Solution", ""),
                    "Type": best_match.get("Type", "Autre"),
                    "Priorite": best_match.get("Priorité", "MOYENNE"),
                    "_source": "local"
                }
    except Exception:
        pass

    return None


def extraire_erreurs_texte(texte_page):
    """Demande à l'IA d'extraire les codes d'erreur d'un texte de page PDF."""
    if not AI_AVAILABLE or not client:
        return []

    try:
        # PII Masking
        texte_page = mask_pii_locally(texte_page)

        prompt = f"""
Extrait TOUS les codes d'erreur et messages de ce texte technique.
Réponds UNIQUEMENT en JSON strict, un tableau :
[{{"Code":"...", "Message":"...", "Cause":"...", "Solution":"...", "Confidence_Score": 95}}]

Si aucune erreur trouvée, réponds : []

Texte :
{texte_page[:4000]}
"""
        response = _call_ia(prompt, timeout=AI_ATTEMPT_TIMEOUT_SECONDS, is_json=True)
        result = clean_json_response(response)
        
        return result if isinstance(result, list) else []

    except Exception as e:
        logger.error(f"Erreur IA extraction: {e}")
        return []


def extraire_erreurs_image(image_bytes):
    """Demande à l'IA d'extraire les codes d'erreur d'une image de page PDF."""
    if not AI_AVAILABLE or not client:
        return []

    try:
        from google.genai import types

        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        prompt = """
Extrait TOUS les codes d'erreur visibles dans cette image (tableau, liste...).
Réponds UNIQUEMENT en JSON strict, un tableau :
[{"Code":"...", "Message":"...", "Cause":"...", "Solution":"..."}]

Si rien trouvé, réponds : []
"""
        response = _call_ia([prompt, image_part], timeout=AI_ATTEMPT_TIMEOUT_SECONDS, is_json=True)
        result = clean_json_response(response)
        return result if isinstance(result, list) else []

    except Exception as e:
        logger.error(f"Erreur IA image: {e}")
        return []
