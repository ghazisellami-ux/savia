# Guide de Test d'Importation de Clients - Savia

## 🔧 Corrections Apportées

### Backend (main.py)
- ✅ Amélioration du support des fichiers CSV
- ✅ Meilleure gestion des erreurs d'encodage UTF-8
- ✅ Support complet des fichiers Excel (.xlsx, .xls) et CSV (.csv)
- ✅ Messages d'erreur plus détaillés pour le débogage

### Frontend (equipements/page.tsx)
- ✅ Accepte maintenant les fichiers CSV (.csv)
- ✅ Accepte les fichiers Excel (.xlsx, .xls)
- ✅ Bouton "Importer Excel" fonctionne avec tous les formats

### Fichiers de Test Générés
- ✅ `clients_import_sample.xlsx` - 10 clients au format Excel avec formatage professionnel
- ✅ `clients_import_extended.xlsx` - 20 clients au format Excel avec formatage professionnel
- ✅ `clients_import_sample.csv` - 10 clients au format CSV
- ✅ `clients_import_extended.csv` - 20 clients au format CSV

## 📁 Fichiers de Test Disponibles

### Format Excel (.xlsx) - Recommandé

#### 1. **clients_import_sample.xlsx** ⭐ (Recommandé pour tester)
- Format: Excel 2007+ (.xlsx)
- Nombre de clients: 10
- Colonnes: nom, code_client, matricule_fiscale, ville, region, contact, telephone, adresse, type_client
- Formatage: En-têtes en gras avec fond bleu, colonnes redimensionnées
- **À utiliser pour tester l'importation Excel**

#### 2. **clients_import_extended.xlsx**
- Format: Excel 2007+ (.xlsx)
- Nombre de clients: 20
- Couvre toutes les régions (Nord, Centre, Sud)
- **À utiliser pour un test complet avec Excel**

### Format CSV (.csv) - Alternative

#### 3. **clients_import_sample.csv**
- Format: CSV (texte)
- Nombre de clients: 10
- Colonnes: nom, code_client, matricule_fiscale, ville, region, contact, telephone, adresse, type_client
- Encodage: UTF-8
- **À utiliser pour tester l'importation CSV**

#### 4. **clients_import_extended.csv**
- Format: CSV (texte)
- Nombre de clients: 20
- Couvre toutes les régions (Nord, Centre, Sud)
- **À utiliser pour un test complet avec CSV**

#### 5. **clients_import_sample_clean.csv**
- Format: CSV (texte)
- Nombre de clients: 10
- Version nettoyée sans caractères spéciaux problématiques
- **Alternative si le fichier sample pose problème**

## 🚀 Comment Tester l'Importation

### Étape 1: Préparer le fichier
1. Téléchargez **clients_import_sample.xlsx** (Excel) ou **clients_import_sample.csv** (CSV)
2. Ouvrez-le avec Excel ou un éditeur de texte pour vérifier le contenu
3. Assurez-vous que l'encodage est UTF-8 (pour CSV)

### Étape 2: Accéder à la page d'importation
1. Allez à **Équipements** → **Clients**
2. Cliquez sur le bouton **Importer Excel**

### Étape 3: Sélectionner le fichier
1. Choisissez le fichier Excel (.xlsx) ou CSV (.csv)
2. Cliquez sur **Ouvrir**

### Étape 4: Vérifier les résultats
- Un message de confirmation affichera:
  - Nombre de clients importés
  - Nombre de clients ignorés
  - Colonnes détectées

## 📊 Structure du Fichier CSV

```
nom,code_client,matricule_fiscale,ville,region,contact,telephone,adresse,type_client
Hôpital Central Tunis,HC-001,1234567890,Tunis,Nord,Dr. Ahmed Ben Ali,+216 71 123 456,123 Avenue de la Liberté - Tunis,Privé
Clinique Sousse,CS-002,0987654321,Sousse,Centre,Dr. Fatima Karray,+216 73 234 567,456 Rue de la Paix - Sousse,Privé
```

### Colonnes (dans l'ordre)
1. **nom** - Nom du client (OBLIGATOIRE)
2. **code_client** - Code unique du client
3. **matricule_fiscale** - Numéro de matricule fiscal
4. **ville** - Ville du client
5. **region** - Région du client
6. **contact** - Personne de contact
7. **telephone** - Numéro de téléphone
8. **adresse** - Adresse complète
9. **type_client** - Type (Privé ou Public)

## ✅ Validation des Données

### Règles d'importation
- ✅ Le champ **nom** est obligatoire
- ✅ Les doublons sont détectés (même nom = doublon)
- ✅ Les régions doivent être valides (Nord, Centre, Sud)
- ✅ Les villes doivent correspondre à la région
- ✅ Le type_client doit être "Privé" ou "Public"

### Gestion des erreurs
- ❌ Ligne avec nom vide = ignorée
- ❌ Région invalide = client importé avec région vide
- ❌ Ville invalide = client importé avec ville vide
- ❌ Type_client invalide = défaut à "Privé"

## 🔍 Dépannage

### Erreur: "Erreur import: 400"
**Cause possible**: Problème d'encodage ou format invalide
**Solution**:
1. Ouvrez le fichier CSV avec Notepad++
2. Vérifiez l'encodage (doit être UTF-8)
3. Vérifiez que chaque ligne a 9 colonnes
4. Utilisez le fichier `clients_import_sample_clean.csv`

### Erreur: "Le fichier est vide"
**Cause**: Fichier vide ou non lisible
**Solution**:
1. Vérifiez que le fichier contient des données
2. Vérifiez que la première ligne est l'en-tête
3. Téléchargez à nouveau le fichier

### Erreur: "Aucun client importé"
**Cause**: Tous les clients ont été ignorés
**Solution**:
1. Vérifiez que le champ "nom" n'est pas vide
2. Vérifiez les noms des clients (pas de doublons)
3. Vérifiez l'encodage du fichier

## 📝 Exemple de Fichier Valide

```csv
nom,code_client,matricule_fiscale,ville,region,contact,telephone,adresse,type_client
Hôpital Central Tunis,HC-001,1234567890,Tunis,Nord,Dr. Ahmed Ben Ali,+216 71 123 456,123 Avenue de la Liberté - Tunis,Privé
Clinique Sousse,CS-002,0987654321,Sousse,Centre,Dr. Fatima Karray,+216 73 234 567,456 Rue de la Paix - Sousse,Privé
Laboratoire Sfax,LS-003,1122334455,Sfax,Centre,Mr. Mohamed Jebali,+216 74 345 678,789 Boulevard Habib Bourguiba - Sfax,Privé
```

## 🎯 Cas de Test

### Test 1: Importation simple avec Excel (10 clients)
- Fichier: `clients_import_sample.xlsx`
- Résultat attendu: 10 clients importés, 0 ignorés

### Test 2: Importation simple avec CSV (10 clients)
- Fichier: `clients_import_sample.csv`
- Résultat attendu: 10 clients importés, 0 ignorés

### Test 3: Importation complète avec Excel (20 clients)
- Fichier: `clients_import_extended.xlsx`
- Résultat attendu: 20 clients importés, 0 ignorés

### Test 4: Importation complète avec CSV (20 clients)
- Fichier: `clients_import_extended.csv`
- Résultat attendu: 20 clients importés, 0 ignorés

### Test 5: Doublons
- Importer le même fichier deux fois
- Résultat attendu: 0 clients importés (tous doublons), 10 ignorés

## 💡 Conseils

1. **Commencez par le fichier sample** pour tester l'importation
2. **Vérifiez l'encodage** du fichier (UTF-8)
3. **Testez avec un petit nombre** de clients d'abord
4. **Vérifiez les doublons** avant d'importer
5. **Utilisez un éditeur de texte** pour éditer les fichiers CSV

## 📞 Support

Si vous rencontrez des problèmes:
1. Consultez ce guide
2. Vérifiez le format du fichier CSV
3. Vérifiez l'encodage (UTF-8)
4. Essayez avec le fichier `clients_import_sample_clean.csv`

---

**Dernière mise à jour**: 2026-05-15
**Version**: 3.0
**Formats supportés**: Excel (.xlsx, .xls) et CSV (.csv)
