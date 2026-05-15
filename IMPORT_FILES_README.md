# Fichiers d'Importation de Clients - Savia

## 📋 Fichiers générés

### 1. **clients_import_sample.csv**
- **Description** : Fichier CSV avec 10 clients d'exemple
- **Taille** : ~1.5 KB
- **Utilisation** : Test basique de l'importation
- **Contenu** : Clients de différentes régions (Nord et Centre)

### 2. **clients_import_extended.csv**
- **Description** : Fichier CSV avec 20 clients d'exemple
- **Taille** : ~3 KB
- **Utilisation** : Test complet avec toutes les régions
- **Contenu** : Clients de toutes les régions (Nord, Centre, Sud)

### 3. **CLIENTS_IMPORT_GUIDE.md**
- **Description** : Guide complet d'importation
- **Contenu** :
  - Description des colonnes requises
  - Régions et villes valides
  - Étapes d'importation
  - Règles de validation
  - Conseils et dépannage

## 📊 Structure des données

### Colonnes du fichier CSV/Excel

| Colonne | Type | Obligatoire | Exemple |
|---------|------|------------|---------|
| nom | Texte | ✅ Oui | Hôpital Central Tunis |
| code_client | Texte | ❌ Non | HC-001 |
| matricule_fiscale | Texte | ❌ Non | 1234567890 |
| ville | Texte | ❌ Non | Tunis |
| region | Texte | ❌ Non | Nord |
| contact | Texte | ❌ Non | Dr. Ahmed Ben Ali |
| telephone | Texte | ❌ Non | +216 71 123 456 |
| adresse | Texte | ❌ Non | 123 Avenue de la Liberté |
| type_client | Texte | ❌ Non | Privé |

## 🚀 Comment utiliser

### Étape 1 : Télécharger le fichier
- Choisissez **clients_import_sample.csv** pour un test simple
- Ou **clients_import_extended.csv** pour un test complet

### Étape 2 : Accéder à la page d'importation
1. Allez à la page **Équipements**
2. Cliquez sur l'onglet **Clients**
3. Cliquez sur le bouton **Importer Excel**

### Étape 3 : Sélectionner le fichier
- Choisissez le fichier CSV ou Excel
- Cliquez sur **Ouvrir**

### Étape 4 : Vérifier les résultats
- Un message de confirmation affichera le nombre de clients importés
- Les clients apparaîtront dans la liste

## 📝 Données d'exemple

### Clients du Nord (10)
- Hôpital Central Tunis
- Polyclinique Bizerte
- Centre Médical Ariana
- Clinique Privée Ben Arous
- Clinique Internationale Tunis
- Hôpital Militaire Tunis
- Polyclinique Nabeul
- Et plus...

### Clients du Centre (7)
- Clinique Sousse
- Laboratoire Sfax
- Hôpital Régional Kairouan
- Centre de Diagnostic Monastir
- Hôpital Universitaire Mahdia
- Clinique Dentaire Sfax
- Centre Chirurgical Sousse

### Clients du Sud (3)
- Hôpital Régional Gabès
- Clinique Privée Médenine
- Centre Médical Tataouine
- Hôpital Régional Gafsa
- Clinique Tozeur
- Centre Médical Kébili

## ✅ Validation des données

### Avant l'importation
- ✅ Vérifiez que le fichier est au format CSV ou Excel
- ✅ Assurez-vous que la première ligne contient les en-têtes
- ✅ Vérifiez les noms des clients (pas de doublons)
- ✅ Validez les régions et villes

### Après l'importation
- ✅ Vérifiez que tous les clients sont importés
- ✅ Corrigez les données manquantes si nécessaire
- ✅ Créez les équipements associés

## 🔍 Régions et villes valides

### Nord
Tunis, Ariana, Ben Arous, Manouba, Bizerte, Béja, Jendouba, Kef, Siliana, Nabeul, Zaghouan

### Centre
Sousse, Monastir, Mahdia, Sfax, Kairouan, Kasserine, Sidi Bouzid

### Sud
Gabès, Médenine, Tataouine, Gafsa, Tozeur, Kébili

## 💡 Conseils

1. **Commencez par le fichier sample** pour tester l'importation
2. **Utilisez le fichier extended** pour importer tous les clients d'exemple
3. **Créez votre propre fichier** en copiant la structure du fichier sample
4. **Vérifiez les doublons** avant d'importer
5. **Utilisez UTF-8** comme encodage du fichier

## 📞 Support

Pour toute question ou problème :
1. Consultez le **CLIENTS_IMPORT_GUIDE.md**
2. Vérifiez que les données respectent le format
3. Contactez l'équipe support Savia

## 🎯 Cas d'usage

### Test 1 : Importation simple
- Fichier : clients_import_sample.csv
- Résultat attendu : 10 clients importés

### Test 2 : Importation complète
- Fichier : clients_import_extended.csv
- Résultat attendu : 20 clients importés

### Test 3 : Création d'équipements
- Après importation, créez des équipements pour les clients
- Associez les équipements aux domaines médicaux
- Planifiez les maintenances

## 📌 Notes importantes

- Le champ **nom** est obligatoire
- Les doublons sont détectés automatiquement
- Les régions et villes doivent correspondre aux listes valides
- Le type_client par défaut est "Privé"
- Le champ international par défaut est "false"

---

**Généré le** : 2026-05-15
**Version** : 1.0
**Format** : CSV (compatible Excel)
