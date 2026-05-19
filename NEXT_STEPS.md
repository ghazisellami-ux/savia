# 📋 Prochaines Étapes - Correction app.dms.savia.tn

## ✅ Travail Complété

1. **Code**: Tous les bugs sont corrigés et commitées
   - ✅ Custom equipment entry (Task 1)
   - ✅ Custom types reloading (Task 2)
   - ✅ Dashboard region filter (Task 3)
   - ✅ Custom domains persistence (Task 4)
   - ✅ Manager role creation (Task 5)

2. **Configuration**: Docker-compose.yml simplifié
   - ✅ PostgreSQL retiré (géré par Coolify)
   - ✅ Backend, Frontend, PWA configurés
   - ✅ Variables d'environnement externalisées

3. **Documentation**: Guides créés
   - ✅ COOLIFY_DEPLOYMENT_GUIDE.md
   - ✅ FIX_APP_DMS_SAVIA_TN.md

## 🚀 Actions à Effectuer sur app.dms.savia.tn

### Étape 1: Accéder à Coolify UI

```
https://app.dms.savia.tn:3000 (ou le port Coolify)
```

### Étape 2: Supprimer et Recréer PostgreSQL

1. **Supprimer** la base de données PostgreSQL existante
   - Aller dans **Databases** → **PostgreSQL**
   - Cliquer sur **Delete**
   - Confirmer

2. **Recréer** la base de données
   - Aller dans **Databases** → **Add Database**
   - Sélectionner **PostgreSQL**
   - Configurer:
     - Database Name: `savia`
     - Username: `savia_user`
     - Password: `<strong_password>` (générer une nouvelle)
   - Cliquer sur **Create**

### Étape 3: Mettre à Jour les Variables d'Environnement

Dans Coolify, pour l'application **Backend**, ajouter/mettre à jour:

```
POSTGRES_DB=savia
POSTGRES_USER=savia_user
POSTGRES_PASSWORD=<password_from_step_2>
DATABASE_URL=postgresql://savia_user:<password_from_step_2>@postgres:5432/savia
JWT_SECRET=<generate_new_secret>
MASTER_KEY=<generate_new_secret>
ACCESS_CODE=<generate_new_secret>
PORT=8001
BACKEND_URL=https://app.dms.savia.tn
NEXT_PUBLIC_API_URL=https://app.dms.savia.tn/api
```

### Étape 4: Redéployer

1. Aller dans l'application **Backend**
2. Cliquer sur **Redeploy** ou **Deploy**
3. Attendre que le déploiement soit terminé

### Étape 5: Vérifier

```bash
# SSH sur le serveur
ssh user@app.dms.savia.tn

# Vérifier les conteneurs
docker compose ps

# Vérifier les logs du backend
docker compose logs -f backend

# Tester la connexion à la base de données
curl http://localhost:8001/docs
```

### Étape 6: Tester l'Application

1. Ouvrir https://app.dms.savia.tn
2. Se connecter avec les credentials admin
3. Tester les fonctionnalités:
   - ✅ Ajouter un équipement
   - ✅ Ajouter un domaine personnalisé
   - ✅ Changer de région dans le dashboard
   - ✅ Créer un compte manager

## 📝 Fichiers Importants

- `coolify-compose.yml` - Configuration Docker (PostgreSQL retiré)
- `COOLIFY_DEPLOYMENT_GUIDE.md` - Guide complet de déploiement
- `FIX_APP_DMS_SAVIA_TN.md` - Actions manuelles pour corriger app.dms.savia.tn
- `backend/main.py` - Backend avec validation des rôles
- `backend/db_engine.py` - Engine de base de données

## 🔄 Workflow de Déploiement

```
1. Développement local ✅
   ↓
2. Test sur savia.sic-tunisia.tn ✅
   ↓
3. Push vers develop ✅
   ↓
4. Merge develop → main ✅
   ↓
5. Merge main → main-dms ✅
   ↓
6. Coolify détecte et redéploie automatiquement
   ↓
7. Vérifier sur app.dms.savia.tn ← VOUS ÊTES ICI
```

## ⚠️ Points Importants

- **PostgreSQL est géré par Coolify** - Ne pas le modifier manuellement
- **Toujours utiliser les variables d'environnement** - Ne pas hardcoder les credentials
- **Sauvegarder les données** avant de supprimer la base de données
- **Tester sur le VPS de test d'abord** avant de déployer chez le client

## 📞 Support

Si vous rencontrez des problèmes:

1. Vérifier les logs: `docker compose logs -f backend`
2. Vérifier PostgreSQL: `docker compose exec postgres pg_isready`
3. Vérifier les variables d'environnement dans Coolify
4. Consulter `FIX_APP_DMS_SAVIA_TN.md` pour le troubleshooting

## ✨ Résumé

Le code est prêt et testé. Il ne reste que les actions manuelles sur Coolify pour corriger app.dms.savia.tn. Une fois PostgreSQL recréé et les variables d'environnement mises à jour, tout devrait fonctionner correctement.
