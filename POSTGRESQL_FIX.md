# 🔧 Correction PostgreSQL - "role postgres does not exist"

## Problème

Lors du déploiement sur app.dms.savia.tn, PostgreSQL affichait l'erreur:
```
FATAL:  role "postgres" does not exist
```

Cela signifiait que PostgreSQL avait une base de données existante mais sans le rôle "postgres" créé.

## Cause

Coolify a créé PostgreSQL mais n'a pas initialisé les rôles correctement. La base de données existait mais était vide de rôles.

## Solution

### 1. Script d'Initialisation PostgreSQL

Créé: `backend/init-postgres.sh`

Ce script:
- ✅ Attend que PostgreSQL soit prêt
- ✅ Crée le rôle "postgres" s'il n'existe pas
- ✅ Crée le rôle "savia_user" s'il n'existe pas
- ✅ Crée la base de données "savia" s'il n'existe pas

### 2. Modification du Dockerfile

Modifié: `backend/Dockerfile`

Changements:
- ✅ Ajout de `postgresql-client` pour les outils psql
- ✅ Copie du script `init-postgres.sh`
- ✅ Exécution du script avant le démarrage de l'application

### 3. Commande de Démarrage

Avant:
```bash
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
```

Après:
```bash
CMD ["/bin/bash", "-c", "/app/init-postgres.sh && uvicorn main:app --host 0.0.0.0 --port 8001"]
```

## Déploiement

Pour le prochain déploiement sur app.dms.savia.tn:

1. **Redéployer le code** (qui contient maintenant le script d'initialisation)
2. **Le script s'exécutera automatiquement** au démarrage du backend
3. **PostgreSQL sera initialisé correctement** avec tous les rôles nécessaires

## Vérification

Après le déploiement, vérifier dans les logs:
```
✅ PostgreSQL is ready
✅ postgres role already exists (ou created)
✅ savia_user role already exists (ou created)
✅ savia database already exists (ou created)
✅ PostgreSQL initialization completed!
```

## Notes

- Le script est idempotent (peut être exécuté plusieurs fois sans problème)
- Il gère les cas où les rôles/bases existent déjà
- Il utilise les variables d'environnement `POSTGRES_PASSWORD` si disponibles
- Les erreurs non critiques sont ignorées (rôles qui existent déjà)

## Commits

- **810e9f5**: Fix: Add PostgreSQL initialization script to ensure postgres role exists

## Prochaines Étapes

1. Redéployer sur app.dms.savia.tn
2. Vérifier les logs du backend
3. Tester la connexion à la base de données
4. Tester les fonctionnalités (créer un manager, ajouter un équipement, etc.)
