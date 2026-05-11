# 📘 Manuel d'Utilisation — SAVIA
## Système Avancé de Veille et Intelligence Appliquée

> Plateforme de gestion de maintenance des équipements médicaux (GMAO)

---

## Table des Matières

1. [Connexion & Rôles](#1-connexion--rôles)
2. [Dashboard](#2-dashboard)
3. [Supervision](#3-supervision)
4. [Équipements](#4-équipements)
5. [Prédictions IA](#5-prédictions-ia)
6. [Base de Connaissances](#6-base-de-connaissances)
7. [SAV & Interventions](#7-sav--interventions)
8. [Demandes d'Intervention](#8-demandes-dintervention)
9. [Planning](#9-planning)
10. [Pièces de Rechange](#10-pièces-de-rechange)
11. [Rapports & Exports](#11-rapports--exports)
12. [Contrats](#12-contrats)
13. [Finances](#13-finances)
14. [Carte Géographique](#14-carte-géographique)
15. [Suivi SLA](#15-suivi-sla)
16. [Administration](#16-administration)
17. [Paramètres](#17-paramètres)
18. [PWA Technicien (Mobile)](#18-pwa-technicien-mobile)
19. [Notifications Telegram](#19-notifications-telegram)
20. [Alertes Automatiques (Daemon)](#20-alertes-automatiques-daemon)

---

## 1. Connexion & Rôles

### Connexion
- **URL** : `https://votre-domaine.com/login`
- **Input** : Nom d'utilisateur + Mot de passe
- **Output** : Accès à l'interface selon le rôle attribué

### Rôles et Permissions

| Module | Admin | Manager | Technicien | Gestionnaire | Lecteur |
|--------|:-----:|:-------:|:----------:|:------------:|:-------:|
| Dashboard | ✅ | ✅ | ✅ | ✅ | ✅ |
| Supervision | ✅ | ✅ | ✅ | ❌ | ✅ |
| Équipements | ✅ | ✅ | ✅ | ✅ | ✅ |
| Prédictions IA | ✅ | ✅ | ✅ | ✅ | ❌ |
| Base Connaissances | ✅ | ✅ | ✅ | ❌ | ❌ |
| SAV & Interventions | ✅ | ✅ | ✅ | ❌ | ❌ |
| Demandes | ✅ | ✅ | ✅ | ❌ | ❌ |
| Planning | ✅ | ✅ | ✅ | ❌ | ❌ |
| Pièces de Rechange | ✅ | ✅ | ✅ | ✅ | ❌ |
| Rapports & Exports | ✅ | ✅ | ✅ | ✅ | ✅ |
| Contrats | ✅ | ✅ | ✅ | ✅ | ❌ |
| Finances | ✅ | ✅ | ❌ | ✅ | ❌ |
| Carte | ✅ | ✅ | ✅ | ✅ | ✅ |
| Suivi SLA | ✅ | ✅ | ✅ | ✅ | ❌ |
| Administration | ✅ | ✅ | ❌ | ❌ | ❌ |
| Paramètres | ✅ | ✅ | ❌ | ❌ | ❌ |

---

## 2. Dashboard

### Description
Vue d'ensemble de l'état du parc d'équipements et des indicateurs clés de performance (KPIs).

### KPIs affichés
| Indicateur | Calcul | Description |
|---|---|---|
| **Total Équipements** | Comptage total | Nombre total d'équipements dans le parc |
| **Taux de Disponibilité** | `(Total - En panne) / Total × 100` | Pourcentage d'équipements opérationnels |
| **Score de Santé** | Moyenne pondérée des statuts | Indicateur global de santé du parc (0-100%) |
| **Interventions en cours** | Comptage `statut ≠ Terminée/Clôturée` | Nombre d'interventions actives |

### Graphiques
- Répartition par statut (Opérationnel, En panne, Hors service, etc.)
- Tendance des interventions sur les derniers mois
- Top équipements les plus sollicités

### Input
Aucune saisie requise — affichage automatique

### Output
Tableaux de bord visuels avec indicateurs temps réel

---

## 3. Supervision

### Description
Surveillance en temps réel de l'état de chaque équipement avec vue détaillée et analyse IA.

### Fonctionnalités
- **Liste des équipements** avec statut en temps réel (codes couleur)
- **Filtres** : par client, domaine médical, statut
- **Vue détaillée** : cliquer sur un équipement ouvre sa fiche complète
- **Analyse IA** : diagnostic automatique par intelligence artificielle

### Input
- Sélection d'un équipement pour consultation
- Clic sur "Analyse IA" pour un diagnostic

### Output
- Fiche détaillée de l'équipement (état, historique, documents)
- Rapport d'analyse IA (risques, recommandations, budget prévisionnel)

---

## 4. Équipements

### Description
Gestion complète du parc d'équipements médicaux : ajout, modification, suppression.

### Créer un équipement

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| Nom | Texte | ✅ | Identifiant unique de l'équipement |
| Client | Sélection | ✅ | Client propriétaire |
| Type d'équipement | Sélection | ✅ | Catégorie (Scanner, IRM, Mammographe, etc.) |
| Domaine médical | Sélection | ✅ | Spécialité (Radiologie, Imagerie, etc.) |
| Marque / Modèle | Texte | ❌ | Fabricant et modèle |
| N° de série | Texte | ❌ | Numéro de série unique |
| Statut | Sélection | ✅ | Opérationnel, En panne, Hors service, etc. |
| Garantie début | Date | ❌ | Date de début de la garantie |
| Garantie durée | Nombre | ❌ | Durée en années |
| Adresse / Ville | Texte | ❌ | Localisation géographique |
| Coordonnées GPS | Nombres | ❌ | Latitude / Longitude (pour la carte) |

### Input
Formulaire de saisie avec les champs ci-dessus

### Output
- Équipement créé et visible dans la liste
- Apparaît sur la carte géographique (si coordonnées renseignées)
- Pris en compte dans les KPIs du dashboard

---

## 5. Prédictions IA

### Description
Module d'intelligence artificielle qui analyse les données historiques pour prédire les pannes et recommander des actions préventives.

### Analyses disponibles
| Analyse | Input | Output |
|---|---|---|
| **Diagnostic** | Sélection d'un équipement | Rapport de risque, recommandations techniques |
| **Performance** | Sélection d'un équipement | Tendances de performance, prédictions de durée de vie |
| **Pièces de rechange** | Automatique | Prédiction de consommation de pièces |
| **Analyse SAV** | Automatique | Synthèse des interventions, patterns récurrents |
| **Analyse Coûts** | Automatique | Projection budgétaire, optimisation des coûts |

### Output
- Rapports structurés avec cartes colorées (Risque, Recommandation, Budget, Timing)
- Export PDF disponible pour l'analyse des coûts

---

## 6. Base de Connaissances

### Description
Bibliothèque centralisée de documents techniques et de fiches de résolution pour capitaliser sur l'expérience.

### Fonctionnalités
| Action | Input | Output |
|---|---|---|
| **Importer** | Fichier (PDF, Word, Excel) + métadonnées | Document indexé et consultable |
| **Rechercher** | Mot-clé | Liste de documents correspondants |
| **Consulter** | Clic sur un document | Affichage du contenu et métadonnées |
| **Chat IA** | Question en langage naturel | Réponse contextualisée basée sur les documents |

---

## 7. SAV & Interventions

### Description
Cœur du système — gestion complète du cycle de vie d'une intervention technique.

### Cycle de vie d'une intervention

```
Création → En cours → En attente de pièce (optionnel) → Terminée → Clôturée → Facturée
```

### Créer une intervention

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| Date | Date | ✅ | Date de l'intervention |
| Équipement | Sélection | ✅ | Machine concernée |
| Technicien | Sélection | ✅ | Technicien assigné |
| Type | Sélection | ✅ | Préventive / Corrective |
| Priorité | Sélection | ❌ | Basse / Moyenne / Haute / Critique |
| Description | Texte | ❌ | Description du problème |
| Code erreur | Texte | ❌ | Code d'erreur machine |

### Onglets

| Onglet | Description |
|---|---|
| **Interventions** | Liste et gestion de toutes les interventions |
| **Suivi Facturation** | Interventions clôturées en attente de facturation |
| **Fiches Signées** | Fiches d'intervention signées par le client |

### Changer le statut d'une intervention

| Statut | Action déclenchée |
|---|---|
| **En cours** | Intervention en traitement |
| **En attente de pièce** | Déclenche le flux de demande de pièce |
| **Terminée** | Intervention techniquement terminée |
| **Clôturée** | Apparaît dans le Suivi Facturation. Notification Telegram envoyée |
| **Facturée** | Marquée comme facturée dans le suivi |

### Fiche d'intervention (PDF)
- **Input** : Clic sur "Générer fiche" pour une intervention
- **Output** : PDF professionnel avec détails techniques, photos, signature client

---

## 8. Demandes d'Intervention

### Description
Interface de réception des demandes d'intervention de la part des clients ou utilisateurs internes.

### Créer une demande

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| Client | Sélection | ✅ | Client demandeur |
| Équipement | Sélection | ✅ | Machine en panne |
| Urgence | Sélection | ✅ | Basse / Moyenne / Haute / Critique |
| Description | Texte | ✅ | Description du problème |
| Code erreur | Texte | ❌ | Code affiché par la machine |
| Contact nom | Texte | ❌ | Nom du contact sur site |
| Contact tel | Texte | ❌ | Téléphone du contact |
| Technicien | Sélection | ❌ | Pré-assigner un technicien |

### Flux

```
Nouvelle → Assignée (technicien désigné) → En cours → Traitée → Clôturée
```

### Notifications
- **Telegram** : Bot Technique + Bot SAV reçoivent chaque nouvelle demande
- **Badge sidebar** : Compteur rouge des demandes non traitées

### Output
- Si technicien assigné dès la création → une intervention SAV est **automatiquement créée**
- Notification Telegram avec détails complets

---

## 9. Planning

### Description
Calendrier de planification des maintenances préventives.

### Créer un planning

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| Équipement | Texte | ✅ | Machine concernée |
| Client | Sélection | ❌ | Client propriétaire |
| Type maintenance | Sélection | ✅ | Préventive / Corrective |
| Date prévue | Date | ✅ | Date planifiée |
| Technicien | Sélection | ❌ | Peut rester vide (assignation ultérieure) |
| Récurrence | Sélection | ❌ | Aucune / Hebdomadaire / Mensuelle / Trimestrielle / Semestrielle / Annuelle |
| Description | Texte | ❌ | Notes sur la maintenance |

### Génération automatique depuis les contrats
Quand un contrat est créé avec une récurrence, le système **génère automatiquement** toutes les entrées de planning entre la date de première maintenance et la date de fin du contrat.

### Automatisations

| Événement | Action automatique |
|---|---|
| **J-14** (2 semaines avant) | Notification Telegram au bot Technique avec rappel + alerte si technicien non assigné |
| **Jour J** | Création automatique d'une intervention SAV + notification Telegram |
| **Retard** (date passée, statut "Planifiée") | Alerte quotidienne au bot Manager |

### Vues
- **Tableau** : Liste chronologique des maintenances
- **Calendrier** : Vue mensuelle interactive

---

## 10. Pièces de Rechange

### Description
Gestion du stock de pièces de rechange avec système de notifications de rupture et de disponibilité.

### Ajouter une pièce au stock

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| Référence | Texte | ✅ | Référence unique de la pièce |
| Désignation | Texte | ✅ | Nom de la pièce |
| Type d'équipement | Sélection | ✅ | Compatible avec quel type de machine |
| Stock actuel | Nombre | ✅ | Quantité en stock |
| Stock minimum | Nombre | ❌ | Seuil d'alerte de rupture |
| Prix unitaire | Nombre | ❌ | Prix d'achat |
| Fournisseur | Texte | ❌ | Nom du fournisseur |

### Flux de demande de pièce (non référencée)

```
Technicien demande pièce (PWA) → Notification Stock + Technique
→ Gestionnaire ajoute la pièce au stock (modal pré-rempli)
→ Notification de disponibilité → Technicien (bot Technique uniquement)
```

### Notifications

| Événement | Bot destinataire |
|---|---|
| Pièce en rupture (stock ≤ minimum) | Bot Stock + Bot Technique |
| Pièce demandée disponible | Bot Technique uniquement |
| Demande de pièce non référencée | Bot Technique + Bot Stock |

### Section "Pièces demandées"
- Cartes affichant les pièces en attente
- Bouton **"Disponible"** → ouvre le modal d'ajout au stock **pré-rempli** avec la référence, désignation et type d'équipement demandés
- La carte ne disparaît que quand la pièce est **réellement créée** en stock

---

## 11. Rapports & Exports

### Description
Génération de rapports professionnels et exports de données.

### Types de rapports

| Rapport | Input | Output |
|---|---|---|
| **Rapport d'intervention** | Sélection intervention | PDF avec détails, photos, signature |
| **Rapport d'activité** | Période (dates) | PDF synthèse des interventions |
| **Export Excel** | Module sélectionné | Fichier .xlsx avec toutes les données |
| **Rapport IA Coûts** | Automatique | PDF d'analyse prévisionnelle des coûts |

---

## 12. Contrats

### Description
Gestion des contrats de maintenance et SLA avec les clients.

### Créer un contrat

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| Client | Sélection | ✅ | Client signataire |
| Équipement | Sélection | ❌ | Équipement couvert |
| Type de contrat | Sélection | ✅ | Standard / Premium / Full Service |
| Date début | Date | ✅ | Début du contrat |
| Date fin | Date | ✅ | Fin du contrat |
| SLA temps réponse | Nombre (heures) | ✅ | Délai maximum de réponse garanti |
| Montant | Nombre | ❌ | Montant du contrat |
| Récurrence maintenance | Sélection | ❌ | Hebdomadaire / Mensuelle / Trimestrielle / Semestrielle / Annuelle |
| Date première maintenance | Date | ❌ | Date de la première maintenance préventive |
| Conditions | Texte | ❌ | Conditions particulières |

### Fonctionnement de la récurrence

Quand un contrat est créé avec une **récurrence** et une **date de première maintenance** :

1. Le système calcule automatiquement toutes les dates entre la première maintenance et la fin du contrat
2. Crée une entrée de **planning** pour chaque date (sans technicien assigné)
3. Envoie une notification Telegram aux bots **SAV + Manager** avec le nombre de maintenances planifiées
4. Le responsable sera notifié **2 semaines avant** chaque maintenance pour assigner un technicien

### Exemple
> Contrat : récurrence **Trimestrielle**, première maintenance **01/09/2026**, fin contrat **01/09/2027**
> → 4 plannings créés : Sep 2026, Déc 2026, Mar 2027, Juin 2027

### Alertes
- **J-30 avant expiration** : notification aux bots SAV + Manager

---

## 13. Finances

### Description
Tableau de bord financier avec suivi des coûts d'intervention et de maintenance.

### Indicateurs
| KPI | Description |
|---|---|
| Coût total interventions | Somme des coûts de main d'œuvre + pièces |
| Coût par client | Ventilation des coûts par client |
| Coût par équipement | Identification des machines les plus coûteuses |
| Évolution mensuelle | Tendance des dépenses sur 12 mois |

### Input
- Filtres : période, client, type d'intervention

### Output
- Graphiques et tableaux financiers
- Export possible via Rapports

---

## 14. Carte Géographique

### Description
Visualisation géographique de l'emplacement des équipements sur une carte interactive.

### Fonctionnalités
- **Marqueurs colorés** selon le statut (vert = opérationnel, rouge = en panne)
- **Pop-up** au clic : nom, client, statut, dernière intervention
- **Filtres** : par client, statut, domaine médical
- **Clustering** : regroupement automatique des marqueurs proches

### Input
- Les coordonnées GPS doivent être renseignées dans la fiche équipement (latitude/longitude)

### Output
- Carte interactive avec vue d'ensemble du parc géographiquement

---

## 15. Suivi SLA

### Description
Surveillance en temps réel du respect des engagements contractuels (Service Level Agreement).

### Principe de calcul

Pour chaque intervention **active** et chaque demande **en attente** :

```
Temps écoulé = Maintenant - Date début intervention
Temps restant = SLA garanti (contrat) - Temps écoulé
% utilisé = (Temps écoulé / SLA garanti) × 100
```

### Classification

| Zone | Condition | Couleur | Action |
|---|---|---|---|
| ✅ OK | < 75% du SLA | Vert | — |
| ⚠️ Danger | 75-100% du SLA | Orange | Alerte bot SAV |
| 🔴 Dépassé | > 100% du SLA | Rouge | Alerte bot Manager |

### KPIs affichés
| Indicateur | Description |
|---|---|
| Total actifs | Nombre d'interventions/demandes surveillées |
| OK / Danger / Dépassés | Répartition par zone |
| Taux de conformité historique | % des interventions clôturées ayant respecté le SLA |

### Input
- Filtre optionnel par client
- Les SLA sont définis dans les contrats

### Output
- Tableau trié par urgence (temps restant croissant)
- Barres de progression colorées pour chaque intervention

---

## 16. Administration

### Description
Gestion des utilisateurs et des accès à la plateforme.

### Gérer les utilisateurs

| Action | Input | Output |
|---|---|---|
| **Créer** | Nom, username, mot de passe, rôle, client (si Lecteur) | Nouveau compte utilisateur |
| **Modifier** | Champs à modifier | Compte mis à jour |
| **Supprimer** | Sélection de l'utilisateur | Compte désactivé |

### Rôles disponibles
- **Admin** : Accès total à toutes les fonctionnalités
- **Manager** : Accès total (identique Admin)
- **Technicien** : Accès opérationnel (pas de finances/admin/paramètres)
- **Gestionnaire** : Accès stock, finances, rapports (pas de SAV/supervision)
- **Lecteur** : Accès en lecture seule, limité à un client spécifique

---

## 17. Paramètres

### Description
Configuration globale de la plateforme.

### Options configurables

| Paramètre | Description |
|---|---|
| **Nom de l'organisation** | Nom affiché dans les rapports et PDF |
| **Telegram Bot Technique** | Token + Chat ID du bot technicien |
| **Telegram Bot SAV** | Token + Chat ID du bot back-office |
| **Telegram Bot Stock** | Token + Chat ID du bot gestion de stock |
| **Telegram Bot Manager** | Token + Chat ID du bot management |
| **Permissions par rôle** | Personnalisation des accès par rôle (override des défauts) |

---

## 18. PWA Technicien (Mobile)

### Description
Application web progressive accessible sur mobile pour les techniciens terrain.

### URL : `https://votre-domaine.com:3002`

### Pages disponibles

| Page | Fonctionnalité |
|---|---|
| **Interventions** | Liste des interventions assignées au technicien connecté |
| **Nouvelle demande** | Créer une demande d'intervention depuis le terrain |
| **Notifications** | Historique des notifications (pièces disponibles, ruptures) avec bouton marquer comme lu |

### Fonctionnalités intervention (mobile)
- Voir les détails de chaque intervention
- Accepter / Refuser une intervention
- Changer le statut (En cours → Terminée)
- Prendre des photos
- Faire signer le client
- Demander une pièce de rechange (référencée ou non référencée)

---

## 19. Notifications Telegram

### Description
4 bots Telegram spécialisés envoient des notifications ciblées selon le type d'événement.

### Routage des notifications

| Événement | 🔧 Technique | 📋 SAV | 📦 Stock | 👔 Manager |
|---|:---:|:---:|:---:|:---:|
| Nouvelle demande d'intervention | ✅ | ✅ | | |
| Intervention créée | ✅ | | | |
| Intervention acceptée/refusée | ✅ | | | |
| Intervention clôturée | ✅ | | | |
| Pièce demandée (non référencée) | ✅ | | ✅ | |
| Pièce demandée disponible | ✅ | | | |
| Pièce en rupture | ✅ | | ✅ | |
| Nouveau contrat + plannings auto | | ✅ | | ✅ |
| Rappel maintenance J-14 | ✅ | | | |
| Maintenance Jour J (auto-intervention) | ✅ | | | |
| Expiration garantie (J-30) | | ✅ | | ✅ |
| Expiration contrat (J-30) | | ✅ | | ✅ |
| Rappel facturation | | ✅ | | ✅ |
| SLA zone danger (≥75%) | | ✅ | | |
| SLA dépassement (>100%) | | | | ✅ |
| Planning en retard | | | | ✅ |
| Stock en rupture (quotidien) | | | ✅ | |

---

## 20. Alertes Automatiques (Daemon)

### Description
Un processus automatique s'exécute **chaque jour à 08h30** et vérifie les conditions suivantes :

| Alerte | Condition vérifiée | Bot destinataire |
|---|---|---|
| **Expiration garantie** | Garantie expire dans les 30 prochains jours | SAV + Manager |
| **Expiration contrat** | Contrat actif expire dans les 30 prochains jours | SAV + Manager |
| **Rappel planning** | Maintenance planifiée dans les 14 prochains jours | Technique |
| **Sync planning → intervention** | Maintenance planifiée pour aujourd'hui → crée automatiquement l'intervention | Technique |
| **Stock en rupture** | Stock actuel ≤ stock minimum | Stock |
| **Rappel facturation** | Intervention clôturée depuis 1 jour (première alerte) ou 8 jours (J-2 avant deadline) | SAV |
| **Facturation en retard** | Intervention clôturée depuis > 10 jours sans facturation | Manager |
| **SLA zone danger** | Intervention active à ≥75% du temps SLA garanti | SAV |
| **SLA dépassement** | Intervention active dépassant le temps SLA garanti | Manager |
| **Planning en retard** | Maintenance planifiée dont la date est passée mais toujours au statut "Planifiée" | Manager |

### Fréquence
- Le daemon vérifie toutes les heures si le cycle quotidien a déjà été exécuté
- S'exécute une seule fois par jour, à partir de 08h30

---

## Glossaire

| Terme | Définition |
|---|---|
| **SLA** | Service Level Agreement — engagement contractuel sur le délai de réponse |
| **GMAO** | Gestion de Maintenance Assistée par Ordinateur |
| **MP** | Maintenance Préventive |
| **MC** | Maintenance Corrective |
| **PWA** | Progressive Web App — application mobile accessible via navigateur |
| **Daemon** | Processus automatique en arrière-plan |
| **KPI** | Key Performance Indicator — indicateur clé de performance |

---

*Document généré automatiquement — SAVIA v2.0*
*Dernière mise à jour : Mai 2026*
