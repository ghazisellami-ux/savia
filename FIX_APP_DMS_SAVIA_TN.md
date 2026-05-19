# 🔧 Corriger app.dms.savia.tn - Actions Manuelles

## Situation Actuelle

- PostgreSQL sur app.dms.savia.tn a des problèmes d'initialisation
- Coolify gère PostgreSQL automatiquement (pas besoin de le définir dans docker-compose.yml)
- Le docker-compose.yml a été simplifié pour ne contenir que Backend, Frontend, et PWA

## Actions à Effectuer sur app.dms.savia.tn

### 1. Accéder à Coolify UI

```
https://app.dms.savia.tn:3000 (ou le port Coolify)
```

### 2. Supprimer la Base de Données PostgreSQL Existante

1. Aller dans **Databases** → **PostgreSQL**
2. Cliquer sur **Delete** (ou **Remove**)
3. Confirmer la suppression
4. Attendre que la base soit supprimée

### 3. Recréer la Base de Données PostgreSQL

1. Aller dans **Databases** → **Add Database**
2. Sélectionner **PostgreSQL**
3. Configurer:
   - **Database Name**: `savia`
   - **Username**: `savia_user`
   - **Password**: `<strong_password>` (générer une nouvelle)
4. Cliquer sur **Create**
5. Attendre que PostgreSQL soit prêt

### 4. Mettre à Jour les Variables d'Environnement

1. Aller dans l'application **Backend**
2. Aller dans **Environment Variables**
3. Mettre à jour ou ajouter:

```
POSTGRES_DB=savia
POSTGRES_USER=savia_user
POSTGRES_PASSWORD=<password_from_step_3>
DATABASE_URL=postgresql://savia_user:<password_from_step_3>@postgres:5432/savia
JWT_SECRET=<generate_new_secret>
MASTER_KEY=<generate_new_secret>
ACCESS_CODE=<generate_new_secret>
PORT=8001
BACKEND_URL=https://app.dms.savia.tn
NEXT_PUBLIC_API_URL=https://app.dms.savia.tn/api
```

### 5. Redéployer l'Application

1. Aller dans l'application **Backend**
2. Cliquer sur **Redeploy** ou **Deploy**
3. Attendre que le déploiement soit terminé
4. Vérifier les logs: **Logs** → **Backend**

### 6. Vérifier le Déploiement

```bash
# SSH sur le serveur
ssh user@app.dms.savia.tn

# Vérifier les conteneurs
docker compose ps

# Vérifier les logs du backend
docker compose logs -f backend

# Tester la connexion à la base de données
curl http://localhost:8001/docs

# Vérifier que les tables sont créées
docker compose exec backend python -c "from db_engine import get_connection; conn = get_connection(); print('✅ Connected')"
```

### 7. Tester l'Application

1. Ouvrir https://app.dms.savia.tn
2. Se connecter avec les credentials admin
3. Tester les fonctionnalités principales:
   - Ajouter un équipement
   - Ajouter un domaine personnalisé
   - Changer de région dans le dashboard
   - Créer un compte manager

## Troubleshooting

### Erreur: "role postgres does not exist"

**Cause**: PostgreSQL n'a pas été initialisé correctement.

**Solution**:
1. Supprimer la base de données dans Coolify
2. Recréer la base de données
3. Redéployer l'application

### Erreur: "Cannot connect to database"

**Vérifier**:
1. Les variables d'environnement sont correctes
2. PostgreSQL est en cours d'exécution: `docker compose ps`
3. Les logs du backend: `docker compose logs backend`

### Erreur: "Connection refused"

**Vérifier**:
1. PostgreSQL est prêt: `docker compose exec postgres pg_isready`
2. Le backend peut accéder à PostgreSQL
3. Les pare-feu n'bloquent pas la connexion

## Après la Correction

Une fois que app.dms.savia.tn fonctionne correctement:

1. Documenter la configuration finale
2. Créer une sauvegarde de la base de données
3. Tester toutes les fonctionnalités
4. Informer le client que l'application est prête

## Notes Importantes

- **Ne jamais modifier PostgreSQL manuellement** - Coolify le gère
- **Toujours utiliser les variables d'environnement** - Ne pas hardcoder les credentials
- **Sauvegarder les données** avant de supprimer la base de données
- **Tester sur le VPS de test d'abord** avant de déployer chez le client
