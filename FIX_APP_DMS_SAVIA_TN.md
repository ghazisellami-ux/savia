# 🔧 Corriger app.dms.savia.tn - Actions Manuelles

## Situation Actuelle

- PostgreSQL sur app.dms.savia.tn a été recréé récemment
- Le code contient maintenant la correction (contrainte CHECK supprimée)
- Il suffit de redéployer le code corrigé

## Actions à Effectuer sur app.dms.savia.tn

### Étape 1: Redéployer le Code Corrigé

1. Aller dans Coolify UI: `https://app.dms.savia.tn:3000`
2. Aller dans l'application **Backend**
3. Cliquer sur **Redeploy** ou **Deploy**
4. Attendre que le déploiement soit terminé

**Pourquoi?** Le code contient maintenant:
- ✅ Suppression de la contrainte CHECK sur les rôles
- ✅ Validation Python pour les rôles (plus flexible)
- ✅ Configuration Docker-compose simplifiée

### Étape 2: Vérifier le Déploiement

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

### Étape 3: Tester l'Application

1. Ouvrir https://app.dms.savia.tn
2. Se connecter avec les credentials admin
3. Tester les fonctionnalités:
   - ✅ Ajouter un équipement
   - ✅ Ajouter un domaine personnalisé
   - ✅ Changer de région dans le dashboard
   - ✅ **Créer un compte manager** (cette fonctionnalité est maintenant corrigée)

## Troubleshooting

### Erreur: "Invalid role"

**Cause**: Le backend utilise maintenant la validation Python au lieu de la contrainte CHECK.

**Solution**: Assurez-vous que le rôle est l'un de: `Admin`, `Technicien`, `Lecteur`, `Manager`

### Erreur: "Cannot connect to database"

**Vérifier**:
1. PostgreSQL est en cours d'exécution: `docker compose ps`
2. Les logs du backend: `docker compose logs backend`
3. Les variables d'environnement dans Coolify

### Erreur: "Connection refused"

**Vérifier**:
1. PostgreSQL est prêt: `docker compose exec postgres pg_isready`
2. Le backend peut accéder à PostgreSQL
3. Les pare-feu n'bloquent pas la connexion

## Après la Correction

Une fois que app.dms.savia.tn fonctionne correctement:

1. Tester toutes les fonctionnalités
2. Créer une sauvegarde de la base de données
3. Informer le client que l'application est prête

## Notes Importantes

- **PostgreSQL est géré par Coolify** - Ne pas le modifier manuellement
- **Toujours utiliser les variables d'environnement** - Ne pas hardcoder les credentials
- **Le code est maintenant flexible** - Vous pouvez ajouter de nouveaux rôles sans modifier la base de données
