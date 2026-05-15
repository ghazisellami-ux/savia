# Guide d'Importation des Clients - Savia

## Vue d'ensemble
Ce guide explique comment importer une liste de clients dans Savia via la page Équipements. L'importation se fait via un fichier CSV ou Excel.

## Fichiers d'exemple
- **clients_import_sample.csv** - Fichier CSV avec 10 clients d'exemple
- **clients_import_sample.xlsx** - Fichier Excel avec 10 clients d'exemple (à générer)

## Colonnes requises

| Colonne | Type | Description | Exemple | Obligatoire |
|---------|------|-------------|---------|------------|
| **nom** | Texte | Nom du client/établissement | Hôpital Central Tunis | ✅ Oui |
| **code_client** | Texte | Code unique du client | HC-001 | ❌ Non |
| **matricule_fiscale** | Texte | Numéro de matricule fiscal | 1234567890 | ❌ Non |
| **ville** | Texte | Ville du client | Tunis | ❌ Non |
| **region** | Texte | Région du client | Nord | ❌ Non |
| **contact** | Texte | Personne de contact | Dr. Ahmed Ben Ali | ❌ Non |
| **telephone** | Texte | Numéro de téléphone | +216 71 123 456 | ❌ Non |
| **adresse** | Texte | Adresse complète | 123 Avenue de la Liberté - Tunis | ❌ Non |
| **type_client** | Texte | Type de client (Privé/Public) | Privé | ❌ Non |

## Régions et Villes valides

### Nord
- Tunis
- Ariana
- Ben Arous
- Manouba
- Bizerte
- Béja
- Jendouba
- Kef
- Siliana
- Nabeul
- Zaghouan

### Centre
- Sousse
- Monastir
- Mahdia
- Sfax
- Kairouan
- Kasserine
- Sidi Bouzid

### Sud
- Gabès
- Médenine
- Tataouine
- Gafsa
- Tozeur
- Kébili

## Types de clients valides
- **Privé** - Établissement privé
- **Public** - Établissement public

## Format du fichier

### CSV
```csv
nom,code_client,matricule_fiscale,ville,region,contact,telephone,adresse,type_client
Hôpital Central Tunis,HC-001,1234567890,Tunis,Nord,Dr. Ahmed Ben Ali,+216 71 123 456,123 Avenue de la Liberté - Tunis,Privé
Clinique Sousse,CS-002,0987654321,Sousse,Centre,Dr. Fatima Karray,+216 73 234 567,456 Rue de la Paix - Sousse,Privé
```

### Excel
- Première ligne : en-têtes (nom, code_client, matricule_fiscale, etc.)
- Lignes suivantes : données des clients
- Pas de lignes vides

## Étapes d'importation

1. **Accédez à la page Équipements**
   - Cliquez sur "Équipements" dans le menu principal

2. **Ouvrez l'onglet Clients**
   - Cliquez sur l'onglet "Clients" en haut de la page

3. **Cliquez sur "Importer Excel"**
   - Bouton situé en haut à droite de la section Clients

4. **Sélectionnez votre fichier**
   - Choisissez le fichier CSV ou Excel à importer

5. **Vérifiez les résultats**
   - Un message de confirmation affichera le nombre de clients importés
   - Les clients apparaîtront dans la liste

## Règles de validation

### Validation des données
- ✅ Le champ **nom** est obligatoire
- ✅ Les doublons sont détectés (même nom = doublon)
- ✅ Les régions et villes doivent correspondre aux listes valides
- ✅ Le type_client doit être "Privé" ou "Public"
- ✅ Le champ international doit être "true" ou "false"

### Gestion des erreurs
- ❌ Ligne avec nom vide = ignorée
- ❌ Région invalide = client importé avec région vide
- ❌ Ville invalide = client importé avec ville vide
- ❌ Type_client invalide = défaut à "Privé"

## Exemple complet

### Données à importer
```csv
nom,code_client,matricule_fiscale,ville,region,contact,telephone,adresse,type_client
Hôpital Central Tunis,HC-001,1234567890,Tunis,Nord,Dr. Ahmed Ben Ali,+216 71 123 456,123 Avenue de la Liberté - Tunis,Privé
Clinique Sousse,CS-002,0987654321,Sousse,Centre,Dr. Fatima Karray,+216 73 234 567,456 Rue de la Paix - Sousse,Privé
Laboratoire Sfax,LS-003,1122334455,Sfax,Centre,Mr. Mohamed Jebali,+216 74 345 678,789 Boulevard Habib Bourguiba - Sfax,Privé
Polyclinique Bizerte,PB-004,5566778899,Bizerte,Nord,Dr. Leila Mansouri,+216 72 456 789,321 Rue de l'Indépendance - Bizerte,Public
Centre Médical Ariana,CMA-005,9988776655,Ariana,Nord,Mr. Karim Belhadj,+216 71 567 890,654 Avenue Mohamed V - Ariana,Privé
```

### Résultat après importation
- 5 clients importés avec succès
- Tous les clients apparaissent dans la liste des clients
- Ils peuvent être utilisés pour créer des équipements

## Conseils d'utilisation

### Avant d'importer
1. ✅ Vérifiez que le fichier est au format CSV ou Excel
2. ✅ Assurez-vous que la première ligne contient les en-têtes
3. ✅ Vérifiez les noms des clients (pas de doublons)
4. ✅ Validez les régions et villes

### Après l'importation
1. ✅ Vérifiez que tous les clients sont importés
2. ✅ Corrigez les données manquantes si nécessaire
3. ✅ Créez les équipements associés

## Dépannage

### Problème : "Aucun client importé"
- **Cause** : Fichier vide ou format invalide
- **Solution** : Vérifiez que le fichier contient des données et que la première ligne est l'en-tête

### Problème : "Certains clients n'ont pas été importés"
- **Cause** : Données invalides ou doublons
- **Solution** : Vérifiez les noms des clients et les régions/villes

### Problème : "Les données ne s'affichent pas correctement"
- **Cause** : Encodage du fichier incorrect
- **Solution** : Assurez-vous que le fichier est encodé en UTF-8

## Support
Pour toute question ou problème, contactez l'équipe support Savia.
