# ==========================================
# 📡 MODULE IOT & TÉLÉMÉTRIE (MQTT)
# ==========================================
import json
import logging
import threading
import time
import paho.mqtt.client as mqtt
from config import MQTT_BROKER, MQTT_PORT, MQTT_TOPIC
from db_engine import log_telemetry

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Variable globale pour stocker l'instance du client
_mqtt_client = None
_is_running = False

# Seuils d'alerte par type de capteur
SEUILS = {
    "TEMP": {"warning": 45, "critical": 50, "unit": "°C",
             "recommandation": "🔧 Vérifier le système de climatisation / refroidissement de la salle."},
    "VIBRATION": {"warning": 0.6, "critical": 0.8, "unit": "G",
                  "recommandation": "🔧 Inspecter les fixations et amortisseurs de la machine."},
    "VOLTAGE": {"warning": 210, "critical": 200, "unit": "V",
                "recommandation": "🔧 Vérifier l'alimentation électrique et le régulateur de tension."},
    "HUMIDITY": {"warning": 70, "critical": 80, "unit": "%",
                 "recommandation": "🔧 Vérifier la ventilation et le déshumidificateur."},
}

# Déduplication : {(machine, sensor): timestamp dernière alerte}
_alert_cache = {}
_ALERT_COOLDOWN = 3600  # 1 heure entre deux alertes identiques

def on_connect(client, userdata, flags, rc, *args):
    """Callback lors de la connexion au broker."""
    if isinstance(rc, int) and rc == 0 or hasattr(rc, 'value') and rc.value == 0:
        logger.info(f"✅ Connecté au broker MQTT : {MQTT_BROKER}")
        client.subscribe(MQTT_TOPIC)
        logger.info(f"📡 Abonné au topic : {MQTT_TOPIC}")
    else:
        logger.error(f"❌ Échec connexion MQTT. Code : {rc}")

def _check_threshold_alert(machine, sensor, value):
    """Vérifie si le seuil est dépassé et envoie une alerte si nécessaire."""
    import time as _time
    
    seuil = SEUILS.get(sensor)
    if not seuil:
        return
    
    niveau = None
    if value >= seuil["critical"]:
        niveau = "CRITIQUE"
    elif value >= seuil["warning"]:
        niveau = "ATTENTION"
    else:
        return  # Tout va bien
    
    # Déduplication : pas d'alerte si déjà envoyée dans la dernière heure
    cache_key = (machine, sensor)
    now = _time.time()
    last_alert = _alert_cache.get(cache_key, 0)
    if now - last_alert < _ALERT_COOLDOWN:
        return
    
    _alert_cache[cache_key] = now
    
    # Construire le message d'alerte
    msg_alerte = (
        f"🚨 ALERTE IoT — {niveau}\n\n"
        f"📍 Machine : {machine}\n"
        f"📊 Capteur : {sensor} = {value} {seuil['unit']}\n"
        f"⚠️ Seuil {niveau.lower()} dépassé ({seuil['critical' if niveau == 'CRITIQUE' else 'warning']} {seuil['unit']})\n\n"
        f"{seuil['recommandation']}"
    )
    
    # Envoyer notification
    try:
        from notifications import get_notifier
        notifier = get_notifier()
        notifier.envoyer(
            sujet=f"🚨 IoT {niveau}: {machine} — {sensor}",
            corps=msg_alerte
        )
        logger.warning(f"🚨 Alerte IoT envoyée : {machine}/{sensor}={value}")
    except Exception as e:
        logger.error(f"❌ Erreur envoi alerte IoT : {e}")

def on_message(client, userdata, msg):
    """Callback lors de la réception d'un message."""
    try:
        payload = msg.payload.decode("utf-8")
        logger.debug(f"📨 Message reçu sur {msg.topic}: {payload}")
        
        # Format attendu : {"machine": "IRM-01", "sensor": "TEMP", "value": 24.5}
        data = json.loads(payload)
        
        machine = data.get("machine")
        sensor = data.get("sensor")
        value = data.get("value")
        
        if machine and sensor and value is not None:
            # Enregistrement en base
            log_telemetry(machine, sensor, value)
            logger.info(f"💾 Télémétrie enregistrée : {machine} / {sensor} = {value}")
            
            # Vérifier les seuils et alerter si nécessaire
            _check_threshold_alert(machine, sensor, float(value))
        else:
            logger.warning(f"⚠️ Payload invalide : {data}")
            
    except json.JSONDecodeError:
        logger.error("❌ Erreur décodage JSON MQTT")
    except Exception as e:
        logger.error(f"❌ Erreur processing MQTT : {e}")

def start_mqtt_listener():
    """Démarre le client MQTT dans un thread séparé."""
    global _mqtt_client, _is_running
    
    if _is_running:
        logger.warning("⚠️ Le listener MQTT tourne déjà.")
        return

    try:
        # paho-mqtt v2.x
        try:
            _mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        except (AttributeError, TypeError):
            # paho-mqtt v1.x fallback
            _mqtt_client = mqtt.Client()
        _mqtt_client.on_connect = on_connect
        _mqtt_client.on_message = on_message
        
        logger.info(f"🔄 Connexion au broker {MQTT_BROKER}:{MQTT_PORT}...")
        _mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        
        # Démarrage de la boucle dans un thread non-bloquant
        _mqtt_client.loop_start()
        _is_running = True
        logger.info("🚀 Service IoT démarré.")
        
    except Exception as e:
        logger.error(f"❌ Impossible de démarrer MQTT : {e}")

def stop_mqtt_listener():
    """Arrête le client MQTT."""
    global _mqtt_client, _is_running
    if _mqtt_client:
        _mqtt_client.loop_stop()
        _mqtt_client.disconnect()
        _is_running = False
        logger.info("🛑 Service IoT arrêté.")

# Pour test autonome
if __name__ == "__main__":
    start_mqtt_listener()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_mqtt_listener()
