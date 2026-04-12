#!/bin/bash
# ==========================================
# 🔒 Script d'installation HTTPS — SAVIA
# ==========================================
# Usage : sudo bash setup_ssl.sh votredomaine.com votre@email.com
#
# Ce script :
# 1. Installe Nginx + Certbot
# 2. Configure le reverse proxy
# 3. Génère les certificats SSL Let's Encrypt
# 4. Active le renouvellement automatique

set -e

DOMAIN=${1:?"Usage: sudo bash setup_ssl.sh DOMAINE EMAIL"}
EMAIL=${2:?"Usage: sudo bash setup_ssl.sh DOMAINE EMAIL"}
API_DOMAIN="api.${DOMAIN}"

echo "=========================================="
echo "🔒 Installation HTTPS pour SAVIA"
echo "   Domaine : ${DOMAIN}"
echo "   API     : ${API_DOMAIN}"
echo "   Email   : ${EMAIL}"
echo "=========================================="

# --- 1. Installation des paquets ---
echo "[1/5] Installation Nginx + Certbot..."
apt update
apt install -y nginx certbot python3-certbot-nginx

# --- 2. Copier la config Nginx ---
echo "[2/5] Configuration Nginx..."
NGINX_CONF="/etc/nginx/sites-available/savia"

# Remplacer les placeholders par le vrai domaine
sed "s/VOTRE_DOMAINE/${DOMAIN}/g" \
    "$(dirname "$0")/nginx/savia.conf" > "${NGINX_CONF}"

# Activer le site
ln -sf "${NGINX_CONF}" /etc/nginx/sites-enabled/savia
rm -f /etc/nginx/sites-enabled/default

# Tester la config
nginx -t
systemctl reload nginx
echo "   ✅ Nginx configuré"

# --- 3. Vérifier que le DNS pointe vers ce serveur ---
echo "[3/5] Vérification DNS..."
MY_IP=$(curl -s ifconfig.me)
DOMAIN_IP=$(dig +short "${DOMAIN}" | head -1)
API_IP=$(dig +short "${API_DOMAIN}" | head -1)

if [ "${DOMAIN_IP}" != "${MY_IP}" ]; then
    echo "   ⚠️  ATTENTION: ${DOMAIN} pointe vers ${DOMAIN_IP}, pas ${MY_IP}"
    echo "   Configurez l'enregistrement DNS A avant de continuer."
    echo "   Appuyez sur Entrée quand c'est fait, ou Ctrl+C pour annuler."
    read
fi

# --- 4. Générer les certificats SSL ---
echo "[4/5] Génération certificats SSL Let's Encrypt..."
certbot --nginx \
    -d "${DOMAIN}" \
    -d "${API_DOMAIN}" \
    --email "${EMAIL}" \
    --agree-tos \
    --non-interactive \
    --redirect

echo "   ✅ Certificats SSL installés"

# --- 5. Vérifier le renouvellement automatique ---
echo "[5/5] Vérification renouvellement automatique..."
certbot renew --dry-run
echo "   ✅ Renouvellement automatique configuré"

echo ""
echo "=========================================="
echo "✅ HTTPS installé avec succès !"
echo ""
echo "🌐 SIC Radiologie : https://${DOMAIN}"
echo "📱 SIC Terrain    : https://${API_DOMAIN}"
echo ""
echo "Les certificats se renouvellent automatiquement."
echo "=========================================="
