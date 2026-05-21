# 🚀 Guide de Déploiement Coolify pour SAVIA

## ⚠️ Important: PostgreSQL est géré par Coolify

Coolify gère PostgreSQL automatiquement. **Ne pas ajouter PostgreSQL dans docker-compose.yml**.

## Configuration sur Coolify

### 1. Créer l'Application

1. Aller sur Coolify UI
2. Créer une nouvelle application
3. Connecter le repository Git (branche `main-dms`)
4. Sélectionner le Dockerfile du backend

### 2. Variables d'Environnement Requises

Dans Coolify, ajouter ces variables d'environnement:

```
# Database (PostgreSQL géré par Coolify)
POSTGRES_DB=savia
POSTGRES_USER=savia_user
POSTGRES_PASSWORD=<strong_password_here>
DATABASE_URL=postgresql://savia_user:<strong_password_here>@postgres:5432/savia

# JWT & Security
JWT_SECRET=<generate_strong_secret>
MASTER_KEY=<generate_strong_secret>
ACCESS_CODE=<generate_strong_secret>

# Backend
PORT=8001
BACKEND_URL=https://app.dms.savia.tn

# Frontend
NEXT_PUBLIC_API_URL=https://app.dms.savia.tn/api

# S3 / MinIO (si utilisé)
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=savia-logs
S3_REGION=us-east-1

# Google API (si utilisé)
GOOGLE_API_KEY=<your_key>
GOOGLE_API_KEYS=<your_keys>
```

### 3. Configuration du Docker Compose

Le `docker-compose.yml` doit **UNIQUEMENT** contenir:
- Backend (FastAPI)
- Frontend (Next.js)
- MinIO (optionnel, pour S3)

**Ne PAS inclure PostgreSQL** - Coolify le gère.

### 4. Déploiement

1. Push le code vers `main-dms`
2. Coolify détecte automatiquement les changements
3. Coolify redéploie les conteneurs
4. PostgreSQL reste intact (géré par Coolify)

### 5. Vérification Post-Déploiement

```bash
# Vérifier les conteneurs
docker compose ps

# Vérifier les logs du backend
docker compose logs -f backend

# Tester la connexion à la base de données
curl https://app.dms.savia.tn/api/health

# Vérifier les tables
docker compose exec backend python -c "from db_engine import get_connection; conn = get_connection(); print('✅ Connected')"
```

## Troubleshooting

### Erreur: "role postgres does not exist"

**Cause**: PostgreSQL n'a pas été initialisé correctement par Coolify.

**Solution**:
1. Aller dans Coolify UI
2. Supprimer la base de données PostgreSQL
3. Recréer la base de données (Coolify le fera automatiquement)
4. Redéployer l'application

### Erreur: "Cannot connect to database"

**Vérifier**:
1. Les variables d'environnement sont correctes dans Coolify
2. Le `DATABASE_URL` correspond aux credentials PostgreSQL
3. Les conteneurs sont en cours d'exécution: `docker compose ps`

### Erreur: "Connection refused"

**Vérifier**:
1. PostgreSQL est en cours d'exécution (géré par Coolify)
2. Le backend peut accéder à PostgreSQL: `docker compose logs backend`
3. Les pare-feu n'bloquent pas la connexion

## Workflow de Déploiement

```
1. Développement local
   ↓
2. Test sur savia.sic-tunisia.tn (test VPS)
   ↓
3. Push vers develop
   ↓
4. Merge develop → main
   ↓
5. Merge main → main-dms
   ↓
6. Coolify détecte et redéploie automatiquement
   ↓
7. Vérifier sur app.dms.savia.tn
```

## Notes Importantes

- **Ne jamais modifier PostgreSQL manuellement** - Coolify le gère
- **Toujours utiliser les variables d'environnement** - Ne pas hardcoder les credentials
- **Sauvegarder les données** avant de supprimer la base de données
- **Tester sur le VPS de test d'abord** avant de déployer chez le client
