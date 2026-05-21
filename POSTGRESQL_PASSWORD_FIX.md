# 🔐 Correction PostgreSQL - Authentification par Mot de Passe

## Problème

Le script d'initialisation PostgreSQL créait les rôles, mais le backend ne pouvait pas se connecter:

```
FATAL:  password authentication failed for user "postgres"
```

## Cause Racine

Le script créait les rôles avec des mots de passe par défaut ou sans mot de passe, mais le backend essayait de se connecter avec les mots de passe des variables d'environnement. Les mots de passe ne correspondaient pas.

## Solution

### Modification du Script `backend/init-postgres.sh`

Le script a été amélioré pour:

1. **Lire les variables d'environnement**:
   ```bash
   POSTGRES_USER="${POSTGRES_USER:-postgres}"
   POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
   POSTGRES_DB="${POSTGRES_DB:-savia}"
   ```

2. **Créer les rôles avec les bons mots de passe**:
   ```bash
   CREATE ROLE postgres WITH PASSWORD 'postgres'
   CREATE ROLE $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD'
   ```

3. **Mettre à jour les mots de passe si les rôles existent déjà**:
   ```bash
   ALTER ROLE postgres WITH PASSWORD 'postgres'
   ALTER ROLE $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD'
   ```

4. **Accorder les privilèges**:
   ```bash
   GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO $POSTGRES_USER
   ```

## Configuration Coolify Requise

Les variables d'environnement suivantes DOIVENT être définies dans Coolify:

```
POSTGRES_USER=savia_user
POSTGRES_PASSWORD=<strong_password>
POSTGRES_DB=savia
DATABASE_URL=postgresql://savia_user:<strong_password>@postgres:5432/savia
```

**Important**: Le mot de passe dans `DATABASE_URL` DOIT correspondre à `POSTGRES_PASSWORD`.

## Déploiement

Pour le prochain déploiement:

1. **Vérifier les variables d'environnement dans Coolify**:
   - `POSTGRES_USER` = `savia_user`
   - `POSTGRES_PASSWORD` = mot de passe fort
   - `DATABASE_URL` = `postgresql://savia_user:<password>@postgres:5432/savia`

2. **Redéployer le code**

3. **Vérifier les logs**:
   ```
   ✅ PostgreSQL is ready
   ✅ postgres role already exists
   🔄 Updating postgres password...
   ✅ savia_user role already exists
   🔄 Updating savia_user password...
   ✅ savia database already exists
   🔐 Granting privileges...
   ✅ PostgreSQL initialization completed!
   ```

4. **Vérifier que le backend se connecte**:
   - Les logs du backend ne doivent pas contenir "password authentication failed"
   - L'application doit démarrer correctement

## Commits

- **3ba2ba9**: Fix: PostgreSQL init script now uses environment variables for passwords

## Notes

- Le script est idempotent (peut être exécuté plusieurs fois)
- Les mots de passe sont mis à jour à chaque déploiement pour assurer la cohérence
- Les privilèges sont accordés automatiquement
- Le script gère les cas où les rôles/bases existent déjà
