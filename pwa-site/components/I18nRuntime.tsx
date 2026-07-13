'use client';

import { useEffect, useRef, useState } from 'react';

type Lang = 'fr' | 'en';

const PHRASES: Array<[string, string]> = [
  ['Mes interventions', 'My interventions'],
  ['Mes Interventions', 'My interventions'],
  ['Interventions', 'Interventions'],
  ['Intervention', 'Intervention'],
  ['Détails', 'Details'],
  ['Details', 'Details'],
  ['Retour', 'Back'],
  ['Accueil', 'Home'],
  ['Planning', 'Planning'],
  ['Notifications', 'Notifications'],
  ['Alertes', 'Alerts'],
  ['Nouvelle', 'New'],
  ['Nouvelle intervention', 'New intervention'],
  ['Profil', 'Profile'],
  ['Paramètres', 'Settings'],
  ['Parametres', 'Settings'],
  ['Déconnexion', 'Sign out'],
  ['Se déconnecter', 'Sign out'],
  ['Technicien', 'Technician'],
  ['Client', 'Client'],
  ['Machine', 'Machine'],
  ['Équipement', 'Equipment'],
  ['Equipement', 'Equipment'],
  ['Type', 'Type'],
  ['Date', 'Date'],
  ['Statut', 'Status'],
  ['Description', 'Description'],
  ['Problème', 'Problem'],
  ['Probleme', 'Problem'],
  ['Cause', 'Cause'],
  ['Cause racine', 'Root cause'],
  ['Solution', 'Solution'],
  ['Solution appliquée', 'Applied solution'],
  ['Solution appliquee', 'Applied solution'],
  ['Prévention', 'Prevention'],
  ['Prevention', 'Prevention'],
  ['Notes', 'Notes'],
  ['Durée', 'Duration'],
  ['Duree', 'Duration'],
  ['Durée intervention', 'Intervention duration'],
  ['Déplacement', 'Travel'],
  ['Deplacement', 'Travel'],
  ['Temps de trajet', 'Travel time'],
  ['Pièces utilisées', 'Parts used'],
  ['Pieces utilisees', 'Parts used'],
  ['Photo', 'Photo'],
  ['Signature', 'Signature'],
  ['En cours', 'In progress'],
  ['Clôturée', 'Closed'],
  ['Cloturee', 'Closed'],
  ['En attente de pièce', 'Waiting for part'],
  ['En attente de piece', 'Waiting for part'],
  ['Planifiée', 'Scheduled'],
  ['Planifiee', 'Scheduled'],
  ['Réalisée', 'Completed'],
  ['Realisee', 'Completed'],
  ['En retard', 'Overdue'],
  ['Acceptée', 'Accepted'],
  ['Acceptee', 'Accepted'],
  ['Refusée', 'Refused'],
  ['Refusee', 'Refused'],
  ['Accepter', 'Accept'],
  ['Refuser', 'Refuse'],
  ['Clôturer', 'Close'],
  ['Cloturer', 'Close'],
  ['Terminer', 'Finish'],
  ['Mettre en attente de pièce', 'Put on hold for part'],
  ['Mettre en attente de piece', 'Put on hold for part'],
  ['Enregistrer', 'Save'],
  ['Sauvegarder', 'Save'],
  ['Annuler', 'Cancel'],
  ['Valider', 'Confirm'],
  ['Fermer', 'Close'],
  ['Modifier', 'Edit'],
  ['Supprimer', 'Delete'],
  ['Ajouter', 'Add'],
  ['Rechercher', 'Search'],
  ['Filtrer', 'Filter'],
  ['Actualiser', 'Refresh'],
  ['Télécharger', 'Download'],
  ['Telecharger', 'Download'],
  ['Envoyer', 'Send'],
  ['Début', 'Start'],
  ['Debut', 'Start'],
  ['Fin', 'End'],
  ['Heure début', 'Start time'],
  ['Heure debut', 'Start time'],
  ['Heure de début', 'Start time'],
  ['Heure de debut', 'Start time'],
  ['HEURE DE DÉBUT', 'START TIME'],
  ['HEURE DE DEBUT', 'START TIME'],
  ['Heure fin', 'End time'],
  ['Heure de fin', 'End time'],
  ['HEURE DE FIN', 'END TIME'],
  ['— Sélectionner —', '— Select —'],
  ['— Selectionner —', '— Select —'],
  ['Disponible', 'Available'],
  ['Indisponible', 'Unavailable'],
  ['Aucune intervention', 'No interventions'],
  ['Aucune notification', 'No notifications'],
  ['Aucun résultat', 'No results'],
  ['Aucun resultat', 'No results'],
  ['Chargement', 'Loading'],
  ['Erreur', 'Error'],
  ['Connexion', 'Sign in'],
  ['Connexion...', 'Signing in...'],
  ['Se connecter', 'Sign in'],
  ['Interface Technicien', 'Technician Interface'],
  ['Identifiant', 'Username'],
  ['votre identifiant', 'your username'],
  ['Nom d\'utilisateur', 'Username'],
  ['Mot de passe', 'Password'],
  ['Accès réservé aux techniciens.', 'Access reserved for technicians.'],
  ['Identifiant ou mot de passe incorrect.', 'Incorrect username or password.'],
  ['Techniciens uniquement', 'Technicians only'],
  ['Intervention terminée', 'Intervention completed'],
  ['Intervention terminee', 'Intervention completed'],
  ['Intervention enregistrée', 'Intervention saved'],
  ['Intervention enregistree', 'Intervention saved'],
  ['Rapport', 'Report'],
  ['Fiche intervention', 'Intervention form'],
  ['Référence', 'Reference'],
  ['Reference', 'Reference'],
  ['Désignation', 'Description'],
  ['Designation', 'Description'],
  ['Quantité', 'Quantity'],
  ['Quantite', 'Quantity'],
  ['Prix', 'Price'],
  ['Stock', 'Stock'],
  ['Urgence', 'Urgency'],
  ['Priorité', 'Priority'],
  ['Priorite', 'Priority'],
];

const ADDITIONAL_PHRASES: Array<[string, string]> = [
  ['Mes interventions', 'My interventions'],
  ['Tous les statuts', 'All statuses'],
  ['En attente', 'Pending'],
  ['Assignée', 'Assigned'],
  ['Assignee', 'Assigned'],
  ['Aucune intervention trouvée', 'No intervention found'],
  ['Aucune intervention trouvee', 'No intervention found'],
  ['Nouvelle Intervention', 'New Intervention'],
  ['Intervention enregistrée !', 'Intervention saved!'],
  ['Intervention enregistree !', 'Intervention saved!'],
  ['Technicien(s)', 'Technician(s)'],
  ['Aucune', 'None'],
  ['Préventive', 'Preventive'],
  ['Preventive', 'Preventive'],
  ['Réseau', 'Network'],
  ['Reseau', 'Network'],
  ['Mécanique', 'Mechanical'],
  ['Mecanique', 'Mechanical'],
  ['Électrique', 'Electrical'],
  ['Electrique', 'Electrical'],
  ['Autre', 'Other'],
  ['Code Erreur', 'Error Code'],
  ["Type d'erreur", 'Error type'],
  ['Type erreur', 'Error type'],
  ['Durée (heures)', 'Duration (hours)'],
  ['Duree (heures)', 'Duration (hours)'],
  ['Déplacement (h)', 'Travel (h)'],
  ['Deplacement (h)', 'Travel (h)'],
  ['Pièces de rechange', 'Spare parts'],
  ['Pièces requises', 'Required parts'],
  ['Pieces requises', 'Required parts'],
  ['rupture', 'out of stock'],
  ['sélectionnée', 'selected'],
  ['selectionnee', 'selected'],
  ['compatible', 'compatible'],
  ['Tap long pour sélectionner plusieurs pièces', 'Long tap to select several parts'],
  ['Tap long pour selectionner plusieurs pieces', 'Long tap to select several parts'],
  ['Observations complémentaires...', 'Additional comments...'],
  ['Observations complementaires...', 'Additional comments...'],
  ['Fiche Signée', 'Signed Form'],
  ['Fiche signée', 'Signed form'],
  ['Fiche signee', 'Signed form'],
  ['Validation Client', 'Client validation'],
  ['Aperçu', 'Preview'],
  ['Apercu', 'Preview'],
  ['Validée', 'Validated'],
  ['Validee', 'Validated'],
  ['Enregistrement...', 'Saving...'],
  ["Enregistrer l'intervention", 'Save intervention'],
  ['Intervention introuvable.', 'Intervention not found.'],
  ['Erreur lors du chargement.', 'Error while loading.'],
  ['Erreur lors de la mise à jour.', 'Error while updating.'],
  ['Erreur lors de la mise a jour.', 'Error while updating.'],
  ['Erreur lors de la sauvegarde.', 'Error while saving.'],
  ['Erreur lors de l’enregistrement.', 'Error while saving.'],
  ["Erreur lors de l'enregistrement.", 'Error while saving.'],
  ['Intervention mise à jour !', 'Intervention updated!'],
  ['Intervention mise a jour !', 'Intervention updated!'],
  ['Intervention acceptée ! Vous pouvez maintenant la compléter.', 'Intervention accepted! You can now complete it.'],
  ['Intervention acceptee ! Vous pouvez maintenant la completer.', 'Intervention accepted! You can now complete it.'],
  ['Intervention refusée. Le manager sera notifié.', 'Intervention refused. The manager will be notified.'],
  ['Intervention refusee. Le manager sera notifie.', 'Intervention refused. The manager will be notified.'],
  ['La "Solution appliquée" est obligatoire pour clôturer l’intervention.', 'The "Applied solution" is required to close the intervention.'],
  ["La \"Solution appliquée\" est obligatoire pour clôturer l'intervention.", 'The "Applied solution" is required to close the intervention.'],
  ['La "Solution" est obligatoire pour clôturer votre intervention.', 'The "Solution" is required to close your intervention.'],
  ['Tous les techniciens ont complété', 'All technicians have completed'],
  ['Tous les techniciens ont complete', 'All technicians have completed'],
  ['En attente de clôture administrative.', 'Waiting for administrative closure.'],
  ['En attente de cloture administrative.', 'Waiting for administrative closure.'],
  ['Données sauvegardées', 'Data saved'],
  ['Donnees sauvegardees', 'Data saved'],
  ['techniciens complétés', 'technicians completed'],
  ['techniciens completes', 'technicians completed'],
  ['Restants', 'Remaining'],
  ['Vos données ont été enregistrées.', 'Your data has been saved.'],
  ['Vos donnees ont ete enregistrees.', 'Your data has been saved.'],
  ['Problème constaté', 'Observed problem'],
  ['Probleme constate', 'Observed problem'],
  ['Symptômes observés...', 'Observed symptoms...'],
  ['Symptomes observes...', 'Observed symptoms...'],
  ['Cause racine', 'Root cause'],
  ['Analyse de la cause...', 'Cause analysis...'],
  ['Solution appliquée', 'Applied solution'],
  ['Solution appliquee', 'Applied solution'],
  ['Actions correctives...', 'Corrective actions...'],
  ['Début (HH:MM)', 'Start (HH:MM)'],
  ['Debut (HH:MM)', 'Start (HH:MM)'],
  ["Durée de l'intervention", 'Intervention duration'],
  ["Duree de l'intervention", 'Intervention duration'],
  ['Mon Statut', 'My Status'],
  ['Intervention terminée', 'Intervention completed'],
  ['Intervention terminee', 'Intervention completed'],
  ['Sélectionnez les pièces nécessaires', 'Select the required parts'],
  ['Selectionnez les pieces necessaires', 'Select the required parts'],
  ['un badge rouge sera créé dans Pièces de rechange', 'a red badge will be created in Spare Parts'],
  ['un badge rouge sera cree dans Pieces de rechange', 'a red badge will be created in Spare Parts'],
  ['Rechercher une pièce...', 'Search for a part...'],
  ['Rechercher une piece...', 'Search for a part...'],
  ['Aucune pièce trouvée', 'No part found'],
  ['Aucune piece trouvee', 'No part found'],
  ['Demander une pièce non référencée', 'Request an unreferenced part'],
  ['Demander une piece non referencee', 'Request an unreferenced part'],
  ['Référence', 'Reference'],
  ['Reference', 'Reference'],
  ['Ajouter à la demande', 'Add to request'],
  ['Ajouter a la demande', 'Add to request'],
  ['pièce(s) non référencée(s)', 'unreferenced part(s)'],
  ['piece(s) non referencee(s)', 'unreferenced part(s)'],
  ['notification dès disponibilité', 'notification when available'],
  ['notification des disponibilite', 'notification when available'],
  ['Enregistrer Mes Données', 'Save My Data'],
  ['Enregistrer Mes Donnees', 'Save My Data'],
  ['Données de', 'Data from'],
  ['Donnees de', 'Data from'],
  ['Pas encore de données pour ce technicien.', 'No data yet for this technician.'],
  ['Pas encore de donnees pour ce technicien.', 'No data yet for this technician.'],
  ['Horaires', 'Schedule'],
  ['Intervention assignée', 'Assigned intervention'],
  ['Intervention assignee', 'Assigned intervention'],
  ['Cette intervention vous a été assignée. Acceptez pour commencer le travail ou refusez avec une justification.', 'This intervention has been assigned to you. Accept to start work or refuse with a justification.'],
  ['Cette intervention vous a ete assignee. Acceptez pour commencer le travail ou refusez avec une justification.', 'This intervention has been assigned to you. Accept to start work or refuse with a justification.'],
  ['Expliquez la raison du refus', 'Explain the refusal reason'],
  ['indisponibilité', 'unavailability'],
  ['indisponibilite', 'unavailability'],
  ['compétence', 'skill'],
  ['competence', 'skill'],
  ["Statut de l'intervention", 'Intervention status'],
  ['Fiche d’intervention signée', 'Signed intervention form'],
  ["Fiche d'intervention signée", 'Signed intervention form'],
  ['Joignez une photo de la fiche d’intervention signée par le client', 'Attach a photo of the intervention form signed by the client'],
  ["Joignez une photo de la fiche d'intervention signée par le client", 'Attach a photo of the intervention form signed by the client'],
  ['Statut de la fiche signée', 'Signed form status'],
  ['Statut de la fiche signee', 'Signed form status'],
  ['SIGNED FORM STATUS', 'SIGNED FORM STATUS'],
  ['Prendre / Importer photo', 'Take / Import photo'],
  ['Prendre / Importer Photo', 'Take / Import photo'],
  ['En attente', 'Pending'],
  ['Validée', 'Validated'],
  ['Validee', 'Validated'],
  ['Validated', 'Validated'],
  ['Mettre à jour', 'Update'],
  ['Mettre a jour', 'Update'],
  ['Pièce disponible', 'Part available'],
  ['Piece disponible', 'Part available'],
  ['Rupture de stock', 'Out of stock'],
  ['Équip.', 'Equip.'],
  ['Equip.', 'Equip.'],
  ['Deplacement (heures)', 'Travel (hours)'],
  ['Deplacement (en heures)', 'Travel (hours)'],
  ['Confirmer le refus', 'Confirm refusal'],
  ['Pieces qui seront notifiees', 'Parts that will be notified'],
  ['Complete', 'Completed'],
  ['selectionnee', 'selected'],
  ['selectionnees', 'selected'],
  ['piece compatible', 'compatible part'],
  ['pieces compatibles', 'compatible parts'],
  ['Fiche d intervention signee', 'Signed intervention form'],
  ['Apercu fiche', 'Form preview'],
  ['equipements', 'equipment'],
];

const ALL_PHRASES = [...PHRASES, ...ADDITIONAL_PHRASES];
const EXPANDED_PHRASES = ALL_PHRASES.flatMap(([from, to]) =>
  phraseVariants(from).map(variant => [variant, to] as [string, string])
);
const EXACT = new Map(EXPANDED_PHRASES);
const REPLACEMENTS = [...EXPANDED_PHRASES].sort((a, b) => b[0].length - a[0].length);
const ATTRS = ['placeholder', 'title', 'aria-label'];
const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'CODE', 'PRE']);

function normalizeLang(value: unknown): Lang {
  return String(value || '').toLowerCase().startsWith('en') ? 'en' : 'fr';
}

function repairMojibake(value: string): string {
  let current = value;
  for (let i = 0; i < 2 && /[ÃÂâ]/.test(current); i += 1) {
    try {
      const next = decodeURIComponent(escape(current));
      if (next === current) break;
      current = next;
    } catch {
      break;
    }
  }
  return current;
}

function stripDiacritics(value: string): string {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function phraseVariants(value: string): string[] {
  const repaired = repairMojibake(value);
  const variants = [
    value,
    repaired,
    stripDiacritics(value),
    stripDiacritics(repaired),
  ];
  return Array.from(new Set(variants.filter(Boolean)));
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function isWordLike(value: string): boolean {
  return /^[\p{L}\p{N}_]+$/u.test(value);
}

function replacePhrase(text: string, from: string, to: string): string {
  if (!from || !text.includes(from)) return text;
  if (!isWordLike(from)) return text.split(from).join(to);
  const pattern = new RegExp(`(^|[^\\p{L}\\p{N}_])${escapeRegExp(from)}(?=$|[^\\p{L}\\p{N}_])`, 'gu');
  return text.replace(pattern, (_match, prefix: string) => `${prefix}${to}`);
}

function translateText(value: string): string {
  if (!value.trim()) return value;
  const leading = value.match(/^\s*/)?.[0] || '';
  const trailing = value.match(/\s*$/)?.[0] || '';
  const core = value.slice(leading.length, value.length - trailing.length);
  const repairedCore = repairMojibake(core);
  const compact = repairedCore.replace(/\s+/g, ' ').trim();
  let translated = EXACT.get(compact) || EXACT.get(stripDiacritics(compact));
  if (!translated) {
    translated = repairedCore;
    for (const [from, to] of REPLACEMENTS) {
      translated = replacePhrase(translated, from, to);
    }
  }
  return `${leading}${translated}${trailing}`;
}

export default function I18nRuntime() {
  const [lang, setLang] = useState<Lang>('fr');
  const originals = useRef<WeakMap<Text, string>>(new WeakMap());
  const observer = useRef<MutationObserver | null>(null);

  useEffect(() => {
    const stored = normalizeLang(localStorage.getItem('savia_site_lang') || localStorage.getItem('savia_lang'));
    setLang(stored);

    const loadSettings = async () => {
      const token = localStorage.getItem('savia_site_token');
      if (!token) return;
      try {
        const res = await fetch('/api/settings', {
          headers: { Authorization: `Bearer ${token}`, 'X-SAVIA-Lang': stored },
        });
        if (!res.ok) return;
        const data = await res.json();
        const next = normalizeLang(data.langue);
        localStorage.setItem('savia_site_lang', next);
        localStorage.setItem('savia_lang', next);
        setLang(next);
      } catch {}
    };

    loadSettings();

    const onLanguage = (event: Event) => {
      const detailLang = (event as CustomEvent<{ lang?: string }>).detail?.lang;
      setLang(normalizeLang(detailLang || localStorage.getItem('savia_site_lang') || localStorage.getItem('savia_lang')));
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'savia_site_lang' || event.key === 'savia_lang') {
        setLang(normalizeLang(event.newValue || localStorage.getItem('savia_site_lang') || localStorage.getItem('savia_lang')));
      }
    };

    window.addEventListener('savia_language_changed', onLanguage);
    window.addEventListener('savia_site_session_changed', loadSettings);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('savia_language_changed', onLanguage);
      window.removeEventListener('savia_site_session_changed', loadSettings);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  useEffect(() => {
    const nativeAlert = window.alert;
    const nativeConfirm = window.confirm;
    const nativeFetch = window.fetch.bind(window);

    window.alert = (message?: unknown) => {
      const text = typeof message === 'string' && lang === 'en' ? translateText(message) : message;
      nativeAlert.call(window, text);
    };

    window.confirm = (message?: string) => {
      const text = typeof message === 'string' && lang === 'en' ? translateText(message) : message;
      return nativeConfirm.call(window, text);
    };

    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.startsWith('/api/') || url.includes('/api/')) {
        const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
        headers.set('X-SAVIA-Lang', localStorage.getItem('savia_site_lang') || localStorage.getItem('savia_lang') || lang);
        return nativeFetch(input, { ...init, headers });
      }
      return nativeFetch(input, init);
    };

    return () => {
      window.alert = nativeAlert;
      window.confirm = nativeConfirm;
      window.fetch = nativeFetch;
    };
  }, [lang]);

  useEffect(() => {
    document.documentElement.lang = lang;

    const shouldSkip = (element: Element | null) =>
      !element || SKIP_TAGS.has(element.tagName) || Boolean(element.closest('[data-savia-i18n-ignore]'));

    const applyTextNode = (node: Text) => {
      const parent = node.parentElement;
      if (shouldSkip(parent)) return;
      const current = node.nodeValue || '';
      let original = originals.current.get(node);
      if (original === undefined) {
        original = current;
        originals.current.set(node, original);
      } else {
        const translatedOriginal = translateText(original);
        if (current !== original && current !== translatedOriginal) {
          original = current;
          originals.current.set(node, original);
        }
      }
      const next = lang === 'en' ? translateText(original) : original;
      if (current !== next) node.nodeValue = next;
    };

    const applyElementAttrs = (element: Element) => {
      if (shouldSkip(element)) return;
      for (const attr of ATTRS) {
        const current = element.getAttribute(attr);
        if (!current) continue;
        const originalAttr = `data-savia-original-${attr}`;
        if (!element.hasAttribute(originalAttr)) element.setAttribute(originalAttr, current);
        let original = element.getAttribute(originalAttr) || current;
        const translatedOriginal = translateText(original);
        if (current !== original && current !== translatedOriginal) {
          original = current;
          element.setAttribute(originalAttr, original);
        }
        const next = lang === 'en' ? translateText(original) : original;
        if (current !== next) element.setAttribute(attr, next);
      }
      if (element instanceof HTMLInputElement && element.type === 'date') {
        element.setAttribute('lang', lang === 'en' ? 'en-US' : 'fr-FR');
      }
    };

    const applyTree = (root: ParentNode) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        applyTextNode(node as Text);
        node = walker.nextNode();
      }
      if (root instanceof Element) applyElementAttrs(root);
      root.querySelectorAll?.('*').forEach(applyElementAttrs);
    };

    observer.current?.disconnect();
    if (document.body) applyTree(document.body);
    observer.current = new MutationObserver(records => {
      for (const record of records) {
        if (record.type === 'characterData') applyTextNode(record.target as Text);
        record.addedNodes.forEach(node => {
          if (node.nodeType === Node.TEXT_NODE) applyTextNode(node as Text);
          if (node.nodeType === Node.ELEMENT_NODE) applyTree(node as Element);
        });
        if (record.type === 'attributes' && record.target instanceof Element) applyElementAttrs(record.target);
      }
    });
    if (document.body) {
      observer.current.observe(document.body, {
        subtree: true,
        childList: true,
        characterData: true,
        attributes: true,
        attributeFilter: ATTRS,
      });
    }
    return () => observer.current?.disconnect();
  }, [lang]);

  return null;
}
