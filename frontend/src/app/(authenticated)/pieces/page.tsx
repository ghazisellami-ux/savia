'use client';
import { useState, useEffect, useCallback, useMemo } from 'react';
import type { ReactNode } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Modal } from '@/components/ui/modal';
import { Plus, Search, Package, AlertTriangle, Loader2, Save, Trash2, Edit, Sparkles,
  Wrench, Building2, TrendingDown, DollarSign, CheckCircle2, XCircle, History,
  Brain, Boxes, Factory, ThumbsUp, ThumbsDown, Calendar, ShieldCheck, ShoppingCart, Clock,
  Bell, CheckCheck, Package2, Hash, User } from 'lucide-react';
import { pieces, interventions, ai, notifications as notifApi, piecesDemandees, equipements, fournisseurs as fournisseursApi } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

interface Piece {
  id: number;
  reference: string;
  designation: string;
  domaine: string;
  equipement_type: string;
  est_annexe: boolean;
  stock_actuel: number;
  stock_minimum: number;
  prix_unitaire: number;
  prix_usd: number;
  prix_eur: number;
  delai_fournisseur_jours: number;
  fournisseur: string;
  notes: string;
}

const INPUT_CLS = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all";
const TAB_CLS = "px-4 py-2.5 text-sm font-semibold rounded-t-lg transition-all cursor-pointer border-b-2";
const TAB_ACTIVE = "border-cyan-400 text-cyan-400 bg-cyan-400/5";
const TAB_INACTIVE = "border-transparent text-savia-text-muted hover:text-savia-text hover:border-slate-500";
const DOMAINES_TYPES: Record<string, string[]> = {
  'Radiologie': ['Scanner CT', 'IRM', 'Radiographie numérique', 'Mammographie', 'Échographie', 'Fluoroscopie', 'Angiographie', 'Ostéodensitomètre', 'Amplificateur de brillance', 'Panoramique dentaire'],
  'Soins Intensifs / POC': ['Moniteur multipéramétrique', 'Respirateur / Ventilateur', 'Défibrillateur', 'ECG', 'Oxyмètre de pouls', 'Pompe à perfusion', 'Incubateur néonatal', 'Analyseur de gaz (POC)'],
  'Anesthésie': ["Appareil d'anesthésie", "Moniteur d'anesthésie", 'Vaporizateur', 'Circuit respiratoire'],
  'Laboratoire': ['Analyseur biochimique', 'Analyseur hématologique', 'Centrifugeuse', "Automate d'immunologie", 'PCR / Biologie moléculaire', 'Microscope', 'Spectrophotomètre'],
};
const ALL_DOMAINES = Object.keys(DOMAINES_TYPES);
const TYPES_EQUIPEMENTS = Object.values(DOMAINES_TYPES).flat(); // compat

function formatContractCoverage(contracts: unknown): string {
  if (!Array.isArray(contracts)) return '';
  const groups = new Map<string, { type: string; covered: boolean; count: number }>();
  for (const contract of contracts) {
    if (!contract || typeof contract !== 'object') continue;
    const item = contract as { type?: unknown; pieces_couvertes?: unknown; id?: unknown };
    const type = String(item.type || 'Contrat actif');
    const covered = Boolean(item.pieces_couvertes);
    const key = `${type}|${covered}`;
    const group = groups.get(key);
    if (group) group.count += 1;
    else groups.set(key, { type, covered, count: 1 });
  }
  return [...groups.values()]
    .map(group => `${group.type} (${group.covered ? 'pièces couvertes' : 'pièces non couvertes'})${group.count > 1 ? ` — ${group.count} contrats` : ''}`)
    .join(', ');
}

function formatFutureContractDemand(demand: unknown): string {
  if (!demand || typeof demand !== 'object') return '';
  const data = demand as Record<string, unknown>;
  const visits = Number(data.interventions_planifiees || 0);
  if (!Number.isFinite(visits) || visits <= 0) return '';
  const parts = [`${visits} maintenance${visits > 1 ? 's' : ''} contractuelle${visits > 1 ? 's' : ''} à venir`];
  if (data.prochaine_intervention) parts.push(`prochaine le ${String(data.prochaine_intervention)}`);
  const quota = Number(data.quantite_quota_contrat || 0);
  const estimated = Number(data.quantite_estimee_historique || 0);
  if (quota > 0) parts.push(`${quota} unité${quota > 1 ? 's' : ''} issue${quota > 1 ? 's' : ''} des quotas`);
  if (estimated > 0) parts.push(`${estimated} unité${estimated > 1 ? 's' : ''} estimée${estimated > 1 ? 's' : ''} selon l'historique préventif`);
  if (quota <= 0 && estimated <= 0) parts.push('sans consommation de cette référence confirmée à ce stade');
  return parts.join(' · ');
}

export default function PiecesPage() {
  const { user } = useAuth();
  const canCreatePiece = user?.role && ['Admin', 'Manager', 'Responsable Technique', 'Gestionnaire de stock', 'Gestionnaire'].includes(user.role);
  
  const [activeTab, setActiveTab] = useState(0);
  const [search, setSearch] = useState('');
  const [filterDomaine, setFilterDomaine] = useState('Tous');
  const [filterType, setFilterType] = useState('Tous');
  const [filterFournisseur, setFilterFournisseur] = useState('Tous');
  const [data, setData] = useState<Piece[]>([]);
  const [interventionData, setInterventionData] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedPiece, setSelectedPiece] = useState<Piece | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [aiResult, setAiResult] = useState<any>(null);
  // Feedback
  const [selectedFeedbackPiece, setSelectedFeedbackPiece] = useState('');
  const [feedbackHistory, setFeedbackHistory] = useState<any[]>([]);
  const [showFeedbackHistory, setShowFeedbackHistory] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [decaleDate, setDecaleDate] = useState('');
  const [feedbackSuccess, setFeedbackSuccess] = useState('');
  const [notifData, setNotifData] = useState<any[]>([]);
  const [notifCount, setNotifCount] = useState(0);
  const [editDomaineFilter, setEditDomaineFilter] = useState('');
  const [editTypeFilter, setEditTypeFilter] = useState('');
  const [editFournisseurFilter, setEditFournisseurFilter] = useState('');
  const [editSearch, setEditSearch] = useState('');
  const [traceDomaineFilter, setTraceDomaineFilter] = useState('');
  const [traceTypeFilter, setTraceTypeFilter] = useState('');
  const [traceFournisseurFilter, setTraceFournisseurFilter] = useState('');
  const [traceSearch, setTraceSearch] = useState('');
  const [selectedPredictionClients, setSelectedPredictionClients] = useState<{ piece: string; clients: string[] } | null>(null);
  const [pendingDemandes, setPendingDemandes] = useState<any[]>([]);
  const [linkedDemandeId, setLinkedDemandeId] = useState<number | null>(null);
  const [equipmentCatalog, setEquipmentCatalog] = useState<Array<{ nom: string; type: string; domaine: string }>>([]);
  const [customDomaines, setCustomDomaines] = useState<string[]>([]);
  const [customTypesForDomain, setCustomTypesForDomain] = useState<Record<string, string[]>>({});
  const [fournisseursList, setFournisseursList] = useState<string[]>([]);
  const [customFournisseur, setCustomFournisseur] = useState(false);
  const [configuredCurrency, setConfiguredCurrency] = useState(() => {
    const stored = typeof window !== 'undefined' ? String(localStorage.getItem('savia_devise') || 'TND').trim().toUpperCase() : 'TND';
    return /^[A-Z]{3}$/.test(stored) ? stored : 'TND';
  });
  const [exchangeRates, setExchangeRates] = useState<Record<string, number> | null>(null);
  const [exchangeRatesError, setExchangeRatesError] = useState('');

  const defaultDomaine = customDomaines[0] || '';
  const emptyForm = { reference: '', designation: '', domaine: defaultDomaine, equipement_type: customTypesForDomain[defaultDomaine]?.[0] || '', est_annexe: false, stock_actuel: '1', stock_minimum: '1', prix_unitaire: '0', prix_usd: '0', prix_eur: '0', delai_fournisseur_jours: '14', fournisseur: '', notes: '' };
  const [form, setForm] = useState(emptyForm);

  const loadData = useCallback(async () => {
    try {
      const [piecesRes, intervRes] = await Promise.all([pieces.list(), interventions.list()]);
      const mapped = piecesRes.map((item: any) => ({
        id: item.id || 0,
        reference: item.reference || item.Reference || '',
        designation: item.designation || item.Nom || '',
        domaine: item.domaine || item.Domaine || '',
        equipement_type: item.equipement_type || item.Compatibilite || '',
        est_annexe: Boolean(item.est_annexe),
        stock_actuel: Number(item.stock_actuel || item.Stock_Actuel || 0),
        stock_minimum: Number(item.stock_minimum || item.Seuil_Critique || 1),
        prix_unitaire: Number(item.prix_unitaire || item.Cout_Unitaire || 0),
        prix_usd: Number(item.prix_usd || 0),
        prix_eur: Number(item.prix_eur || 0),
        delai_fournisseur_jours: Number.isFinite(Number(item.delai_fournisseur_jours)) ? Number(item.delai_fournisseur_jours) : 14,
        fournisseur: item.fournisseur || item.Fournisseur || '',
        notes: item.notes || '',
      }));
      setData(mapped);
      setInterventionData(intervRes);
    } catch (err) {
      console.error("Failed to fetch pieces", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const loadExchangeRates = useCallback(async () => {
    try {
      const result = await pieces.exchangeRates();
      const rates = Object.fromEntries(
        Object.entries(result.rates || {})
          .filter(([, value]) => Number.isFinite(Number(value)) && Number(value) > 0)
          .map(([code, value]) => [code, Number(value)]),
      ) as Record<string, number>;
      if (!rates.USD || !rates.EUR) throw new Error('Taux USD ou EUR manquant');
      setExchangeRates(rates);
      setExchangeRatesError('');
    } catch (error: unknown) {
      setExchangeRatesError(error instanceof Error ? error.message : 'Les taux de change sont indisponibles.');
    }
  }, []);

  useEffect(() => { void loadExchangeRates(); }, [loadExchangeRates]);

  useEffect(() => {
    const refreshConfiguredCurrency = () => {
      const next = String(localStorage.getItem('savia_devise') || 'TND').trim().toUpperCase();
      setConfiguredCurrency(/^[A-Z]{3}$/.test(next) ? next : 'TND');
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'savia_devise') refreshConfiguredCurrency();
    };
    window.addEventListener('savia_settings_changed', refreshConfiguredCurrency);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('savia_settings_changed', refreshConfiguredCurrency);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  const convertPrice = (amount: number, sourceCurrency: string, targetCurrency: string): number | null => {
    const sourceRate = exchangeRates?.[sourceCurrency];
    const targetRate = exchangeRates?.[targetCurrency];
    if (!Number.isFinite(amount) || !sourceRate || !targetRate) return null;
    return amount / sourceRate * targetRate;
  };

  const formatPriceInput = (amount: number) => String(Math.round(amount));

  const roundedFormPrice = (value: string) => {
    if (!value) return '';
    const amount = Number(value);
    return Number.isFinite(amount) ? formatPriceInput(amount) : value;
  };

  const updatePurchasePrice = (field: 'prix_unitaire' | 'prix_usd' | 'prix_eur', sourceCurrency: string, value: string) => {
    setForm(current => {
      const next = { ...current, [field]: value };
      const amount = Number(value);
      if (!value || !Number.isFinite(amount) || amount < 0 || !exchangeRates) return next;

      const configuredValue = convertPrice(amount, sourceCurrency, configuredCurrency);
      const usdValue = convertPrice(amount, sourceCurrency, 'USD');
      const eurValue = convertPrice(amount, sourceCurrency, 'EUR');
      if (configuredValue === null || usdValue === null || eurValue === null) return next;

      return {
        ...next,
        prix_unitaire: formatPriceInput(configuredValue),
        prix_usd: formatPriceInput(usdValue),
        prix_eur: formatPriceInput(eurValue),
      };
    });
  };

  const getPriceInCurrency = (piece: Piece, currency: string): number | null => {
    const stored = currency === 'USD' ? piece.prix_usd : currency === 'EUR' ? piece.prix_eur : piece.prix_unitaire;
    if (Number.isFinite(stored) && stored > 0) return stored;
    return convertPrice(piece.prix_unitaire, configuredCurrency, currency);
  };

  const formatMoney = (value: number | null, currency: string) => (
    value === null || !Number.isFinite(value) ? '—' : `${Math.round(value).toLocaleString('fr-FR', { maximumFractionDigits: 0 })} ${currency}`
  );

  const loadFournisseurs = useCallback(async () => {
    try {
      const res = await fournisseursApi.list();
      setFournisseursList(
        (Array.isArray(res) ? res : [])
          .map(item => String(item.nom || '').trim())
          .filter(Boolean),
      );
    } catch (err) {
      console.error('Erreur chargement fournisseurs:', err);
    }
  }, []);

  useEffect(() => { loadFournisseurs(); }, [loadFournisseurs]);

  // Charger les demandes de pièces en attente
  const loadDemandes = useCallback(async () => {
    try {
      const res = await piecesDemandees.list('en_attente');
      setPendingDemandes(res as any[]);
    } catch { /* silencieux */ }
  }, []);
  useEffect(() => { loadDemandes(); }, [loadDemandes]);

  // Charger les domaines et types depuis les équipements (unique source de vérité)
  const loadEquipmentDomainesTypes = useCallback(async () => {
    try {
      const eqRes = await equipements.list().catch(() => []);
      const eqs = (eqRes as any[]);
      setEquipmentCatalog(eqs.map((eq: any) => ({
        nom: String(eq.nom || eq.Nom || '').trim(),
        type: String(eq.type || eq.Type || '').trim(),
        domaine: String(eq.domaine || eq.Domaine || '').trim(),
      })).filter(eq => eq.nom));
      
      // Extraire les domaines uniques
      const uniqueDomaines = [...new Set(eqs.map((eq: any) => eq.domaine || eq.Domaine).filter(Boolean))];
      
      // Créer un mapping domaine -> types d'équipement
      const domaineToTypes: Record<string, string[]> = {};
      uniqueDomaines.forEach(domaine => {
        const types = eqs
          .filter((eq: any) => (eq.domaine || eq.Domaine) === domaine)
          .map((eq: any) => eq.Type || eq.type || '')
          .filter(Boolean);
        domaineToTypes[domaine] = [...new Set(types)].sort();
      });
      
      setCustomDomaines(uniqueDomaines.sort());
      setCustomTypesForDomain(domaineToTypes);
    } catch (err) {
      console.error("Erreur chargement domaines depuis équipements:", err);
    }
  }, []);

  useEffect(() => {
    loadEquipmentDomainesTypes();
  }, [loadEquipmentDomainesTypes]);

  // Recharger les domaines quand le modal s'ouvre
  useEffect(() => {
    if (showAddModal || showEditModal) {
      loadEquipmentDomainesTypes();
    }
  }, [showAddModal, showEditModal, loadEquipmentDomainesTypes]);

  // Initialiser aussi le formulaire si les équipements arrivent après son ouverture.
  useEffect(() => {
    if (!showAddModal || !customDomaines.length) return;
    setForm(current => {
      if (current.domaine) return current;
      const domaine = customDomaines[0];
      return { ...current, domaine, equipement_type: customTypesForDomain[domaine]?.[0] || '' };
    });
  }, [showAddModal, customDomaines, customTypesForDomain]);

  // Obtenir les types d'équipement disponibles pour le domaine sélectionné
  const getAvailableTypes = useCallback(() => {
    const baseTypes = customTypesForDomain[form.domaine]?.length
      ? customTypesForDomain[form.domaine]
      : DOMAINES_TYPES[form.domaine] || ['Autre'];
    return form.equipement_type && !baseTypes.includes(form.equipement_type)
      ? [form.equipement_type, ...baseTypes]
      : baseTypes;
  }, [form.domaine, form.equipement_type, customTypesForDomain]);

  const getEquipmentContext = useCallback((machine: string) => {
    const normalizedMachine = String(machine || '').trim().toLowerCase();
    if (!normalizedMachine) return undefined;
    const exact = equipmentCatalog.find(eq => eq.nom.toLowerCase() === normalizedMachine);
    if (exact) return exact;
    return equipmentCatalog.find(eq => {
      const name = eq.nom.toLowerCase();
      return name.includes(normalizedMachine) || normalizedMachine.includes(name);
    });
  }, [equipmentCatalog]);

  // Charger les notifications + count
  const loadNotifs = useCallback(async () => {
    try {
      const [lst, cnt] = await Promise.all([notifApi.list(), notifApi.count()]);
      setNotifData(lst as any[]);
      setNotifCount((cnt as any).count || 0);
    } catch { /* silencieux */ }
  }, []);
  useEffect(() => { loadNotifs(); }, [loadNotifs]);

  // Quand on ouvre l'onglet Notifications, marquer toutes les non-lues comme lues
  useEffect(() => {
    if (activeTab === 4 && notifData.length > 0) {
      const unread = notifData.filter((n: any) => n.statut === 'non_lu');
      unread.forEach((n: any) => {
        notifApi.markRead(Number(n.id)).catch(() => {});
      });
      if (unread.length > 0) {
        setTimeout(() => loadNotifs(), 800);
      }
    }
  }, [activeTab, notifData, loadNotifs]);

  // Le feedback est partagé et conservé côté serveur; localStorage reste un
  // fallback pour ne pas perdre l'affichage si l'API est momentanément indisponible.
  useEffect(() => {
    pieces.predictionFeedbackList(100)
      .then((items: any[]) => setFeedbackHistory(items.map(item => ({
        ...item,
        piece: item.designation || item.reference,
        type: item.resultat,
        vraiDate: item.date_reelle,
        timestamp: item.timestamp || item.date_calcul,
      }))))
      .catch(() => {
        const saved = localStorage.getItem('savia_pieces_feedback');
        if (saved) setFeedbackHistory(JSON.parse(saved));
      });
  }, []);

  const submitFeedback = async (type: 'correct' | 'faux_positif' | 'decale', vraiDate?: string) => {
    if (!selectedFeedbackPiece) return;
    const piece = data.find(item => item.reference === selectedFeedbackPiece);
    if (!piece) return;
    const forecast = predictions[piece.id] || {};
    const entry = {
      piece: piece.designation,
      reference: piece.reference,
      designation: piece.designation,
      type,
      resultat: type,
      vraiDate,
      timestamp: new Date().toISOString(),
    };
    try {
      await pieces.predictionFeedback({
        reference: piece.reference,
        designation: piece.designation,
        resultat: type,
        date_calcul: new Date().toISOString().slice(0, 10),
        date_predite: forecast.date_rupture_prevue || forecast.date_commande || '',
        date_reelle: vraiDate || '',
        quantite: forecast.quantite_recommandee ?? null,
        risque_rupture_pct: forecast.risque_rupture_30j_pct ?? null,
        modele_version: forecast.modele || '',
        features: forecast,
      });
      setFeedbackHistory(prev => [entry, ...prev]);
    } catch (error) {
      console.error('Erreur enregistrement feedback pièce:', error);
      const updated = [entry, ...feedbackHistory];
      setFeedbackHistory(updated);
      localStorage.setItem('savia_pieces_feedback', JSON.stringify(updated));
    }
    setFeedbackSuccess(
      type === 'correct' ? 'Prédiction confirmée' :
      type === 'faux_positif' ? 'Faux positif signalé' :
      `Date corrigée → ${vraiDate}`
    );
    setShowDatePicker(false); setDecaleDate('');
    setTimeout(() => setFeedbackSuccess(''), 4000);
  };

  const validatePieceForm = () => {
    if (!form.reference.trim() || !form.designation.trim() || !form.domaine.trim() || !form.equipement_type.trim() || !form.fournisseur.trim()) {
      return 'Référence, désignation, domaine, type d’équipement et fournisseur sont obligatoires.';
    }
    if (!selectedPiece) {
      const reference = form.reference.trim().toUpperCase();
      if (data.some(piece => String(piece.reference || '').trim().toUpperCase() === reference)) {
        return 'Cette référence existe déjà.';
      }
    }
    const stock = Number(form.stock_actuel);
    const minimum = Number(form.stock_minimum);
    const price = Number(form.prix_unitaire);
    const priceUsd = Number(form.prix_usd);
    const priceEur = Number(form.prix_eur);
    const leadTime = Number(form.delai_fournisseur_jours);
    if (!Number.isInteger(stock) || stock < 0 || !Number.isInteger(minimum) || minimum < 0) {
      return 'Le stock actuel et le stock minimum doivent être des nombres entiers positifs ou nuls.';
    }
    if (![price, priceUsd, priceEur].every(value => Number.isFinite(value) && value > 0)) {
      return 'Les prix d’achat en devise configurée, USD et EUR doivent être supérieurs à zéro.';
    }
    if (form.delai_fournisseur_jours === '' || !Number.isInteger(leadTime) || leadTime < 0 || leadTime > 365) {
      return 'Le délai fournisseur doit être un nombre entier compris entre 0 et 365 jours.';
    }
    return '';
  };

  const handleSave = async () => {
    const validationError = validatePieceForm();
    if (validationError) { setFormError(validationError); return; }
    setFormError('');
    setIsSaving(true);
    try {
      await pieces.create({
        reference: form.reference.trim().toUpperCase(),
        designation: form.designation.trim(),
        domaine: form.domaine,
        equipement_type: form.equipement_type,
        est_annexe: form.est_annexe,
        stock_actuel: Number(form.stock_actuel),
        stock_minimum: Number(form.stock_minimum),
        prix_unitaire: Math.round(Number(form.prix_unitaire)),
        prix_usd: Math.round(Number(form.prix_usd)),
        prix_eur: Math.round(Number(form.prix_eur)),
        delai_fournisseur_jours: Number(form.delai_fournisseur_jours),
        fournisseur: form.fournisseur.trim(),
        notes: form.notes.trim(),
      });
      await registerFournisseur(form.fournisseur);
      // Si liée à une demande, résoudre la demande + notifier le technicien
      if (linkedDemandeId) {
        // La création du stock résout déjà la demande et envoie la notification Telegram complète.
        // Ne pas rappeler l'API de résolution : cela provoquerait un second message.
        setLinkedDemandeId(null);
        await loadDemandes();
      }
      setForm(emptyForm);
      setShowAddModal(false);
      await loadData();
    } catch (err: any) {
      console.error("Save failed", err);
      setFormError(err?.message || "Impossible d'enregistrer la pièce.");
    }
    finally { setIsSaving(false); }
  };

  const handleEdit = async () => {
    if (!selectedPiece) return;
    const validationError = validatePieceForm();
    if (validationError) { setFormError(validationError); return; }
    setFormError('');
    setIsSaving(true);
    try {
      await pieces.update(selectedPiece.id, {
        reference: form.reference.trim().toUpperCase(),
        designation: form.designation.trim(),
        domaine: form.domaine,
        equipement_type: form.equipement_type,
        est_annexe: form.est_annexe,
        stock_actuel: Number(form.stock_actuel),
        stock_minimum: Number(form.stock_minimum),
        prix_unitaire: Math.round(Number(form.prix_unitaire)),
        prix_usd: Math.round(Number(form.prix_usd)),
        prix_eur: Math.round(Number(form.prix_eur)),
        delai_fournisseur_jours: Number(form.delai_fournisseur_jours),
        fournisseur: form.fournisseur.trim(),
        notes: form.notes.trim(),
      });
      await registerFournisseur(form.fournisseur);
      setShowEditModal(false);
      setSelectedPiece(null);
      await loadData();
    } catch (err: any) {
      console.error("Edit failed", err);
      setFormError(err?.message || "Impossible de modifier la pièce.");
    }
    finally { setIsSaving(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Supprimer cette pièce ?")) return;
    try { await pieces.delete(id); await loadData(); }
    catch (err) { console.error("Delete failed", err); }
  };

  // Fetch predictions from API for each piece
  const [predictions, setPredictions] = useState<Record<number, any>>({});
  const [predictionsLoading, setPredictionsLoading] = useState(false);
  
  const loadPredictions = useCallback(async () => {
    if (data.length === 0) return;
    setPredictionsLoading(true);
    try {
      const preds: Record<number, any> = {};
      await Promise.all(data.map(async (p) => {
        try {
          const res = await pieces.prediction(p.id);
          preds[p.id] = res;
        } catch (err) {
          console.error(`Erreur prediction piece ${p.id}:`, err);
          preds[p.id] = { error: true, date_commande: null };
        }
      }));
      setPredictions(preds);
    } catch (err) {
      console.error("Erreur loading predictions:", err);
    } finally {
      setPredictionsLoading(false);
    }
  }, [data]);

  useEffect(() => {
    // Load predictions when switching to Tab 3
    if (activeTab === 3 && Object.keys(predictions).length === 0) {
      loadPredictions();
    }
  }, [activeTab, predictions, loadPredictions]);

  const registerFournisseur = async (value: string) => {
    const nom = value.trim();
    if (!nom) return;
    const exists = fournisseursList.some(item => item.toLowerCase() === nom.toLowerCase());
    if (!exists) {
      try {
        await fournisseursApi.create(nom);
        await loadFournisseurs();
      } catch (err) {
        console.error('Erreur enregistrement fournisseur:', err);
      }
    }
    setCustomFournisseur(false);
  };

  const formatForecastNumber = (value: unknown, suffix = '') => {
    if (value === null || value === undefined || value === '') return 'Non calculable';
    return `${Number(value).toLocaleString('fr-FR', { maximumFractionDigits: 1 })}${suffix}`;
  };

  const getForecastCost = (piece: Piece, forecast: any): number | null => {
    if (forecast?.cout_estime !== null && forecast?.cout_estime !== undefined) {
      const serverCost = Number(forecast.cout_estime);
      if (Number.isFinite(serverCost)) return serverCost;
    }
    const quantity = Number(
      forecast?.quantite_recommandee ?? Math.max(0, piece.stock_minimum - piece.stock_actuel + 1)
    );
    const unitPrice = Number(piece.prix_unitaire);
    if (!Number.isFinite(quantity) || quantity < 0 || !Number.isFinite(unitPrice) || unitPrice <= 0) {
      return null;
    }
    return Math.round(quantity * unitPrice * 100) / 100;
  };

  // Display deterministic values from the replenishment engine.
  const getPredictionDisplay = (p: Piece): ReactNode => {
    const pred = predictions[p.id];
    if (!pred) {
      return <span className="text-savia-text-muted text-xs">Chargement...</span>;
    }
    if (pred.error) {
      return <span className="text-orange-400 text-xs font-semibold">⚠️ Données insuffisantes</span>;
    }
    const forecastCost = getForecastCost(p, pred);
    const futureContractDemand = formatFutureContractDemand(pred.demande_contrats_futurs);
    if (pred.stock_actuel === 0 && pred.recommandation_actionnable) {
      return (
        <div className="text-xs space-y-0.5">
          <div className="font-bold text-red-400">Rupture immédiate — commander maintenant</div>
          <div>Qté minimale : {pred.quantite_recommandee ?? 'Non calculable'}</div>
          <div>Coût : {formatMoney(forecastCost, configuredCurrency)}</div>
          {futureContractDemand && <div className="text-savia-text-muted">Contrat : {futureContractDemand}</div>}
        </div>
      );
    }
    if (!pred.prediction_available) {
      return (
        <div className="text-xs space-y-0.5">
          <div className="text-orange-400 font-semibold">Prévision non calculable : {pred.raison || 'historique ou délai fournisseur manquant'}</div>
          {futureContractDemand && <div className="text-savia-text-muted">Contrat : {futureContractDemand}</div>}
        </div>
      );
    }
    return (
      <div className="text-xs space-y-0.5">
        <div className="font-semibold">Commande : {pred.date_commande || 'Non calculable'}</div>
        <div className="text-savia-text-muted">Rupture : {pred.date_rupture_prevue || 'Non calculable'}</div>
        <div className="text-savia-text-dim">Qté : {formatForecastNumber(pred.quantite_recommandee)} · Risque 30 j : {formatForecastNumber(pred.risque_rupture_30j_pct, '%')}</div>
        {futureContractDemand && <div className="text-savia-text-muted">Contrat : {futureContractDemand}</div>}
      </div>
    );
  };

  const handleAiAnalyze = async () => {
    setIsAnalyzing(true);
    setAiResult(null);
    try {
      // Get currency from localStorage (set in admin settings)
      const devise = typeof window !== 'undefined' ? localStorage.getItem('savia_devise') || 'USD' : 'USD';
      
      // Extract most common domain and equipment type from data
      const domaines = [...new Set(data.map(p => p.domaine || 'Généraliste').filter(Boolean))];
      const equipTypes = [...new Set(data.map(p => p.equipement_type || '').filter(Boolean))];
      const domain = domaines.length === 1 ? domaines[0] : domaines.join(' / ');
      const equipment_type = equipTypes.length === 1 ? equipTypes[0] : equipTypes.slice(0, 3).join(', ');
      
      const res = await ai.analyzePieces(data.map(p => ({
        designation: p.designation,
        reference: p.reference,
        equipement_type: p.equipement_type,
        stock_actuel: p.stock_actuel,
        stock_minimum: p.stock_minimum,
        prix_unitaire: p.prix_unitaire,
        fournisseur: p.fournisseur,
      })), devise, domain, equipment_type);
      if (res.ok && res.result) {
        const raw = typeof res.result === 'string' ? res.result : JSON.stringify(res.result);
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          try { setAiResult(JSON.parse(jsonMatch[0])); }
          catch { setAiResult({ analyse_risque: raw, recommandations: [], plan_achat: [], tendances: [] }); }
        } else {
          try { setAiResult(typeof res.result === 'object' ? res.result : { analyse_risque: raw, recommandations: [], plan_achat: [], tendances: [] }); }
          catch { setAiResult({ analyse_risque: raw, recommandations: [], plan_achat: [], tendances: [] }); }
        }
      } else {
        setAiResult({ analyse_risque: "L'IA n'a pas pu générer de réponse.", recommandations: [], plan_achat: [], tendances: [] });
      }
    } catch (err: any) {
      setAiResult({ analyse_risque: `Erreur: ${err?.message || 'Analyse indisponible'}`, recommandations: [], plan_achat: [], tendances: [] });
    } finally { setIsAnalyzing(false); }
  };

  // Filters
  const domaines = useMemo(() => ['Tous', ...new Set(data.map(p => p.domaine).filter(Boolean))], [data]);
  const stockTypes = useMemo(() => ['Tous', ...new Set(
    data
      .filter(piece => filterDomaine === 'Tous' || piece.domaine === filterDomaine)
      .map(piece => piece.equipement_type)
      .filter(Boolean),
  )], [data, filterDomaine]);
  const stockSupplierOptions = useMemo(() => ['Tous', ...Array.from(new Set(
    data
      .filter(piece => (filterDomaine === 'Tous' || piece.domaine === filterDomaine)
        && (filterType === 'Tous' || piece.equipement_type === filterType))
      .map(piece => piece.fournisseur)
      .filter(Boolean),
  )).sort((a, b) => a.localeCompare(b, 'fr'))], [data, filterDomaine, filterType]);
  const filtered = data.filter(p => {
    if (filterDomaine !== 'Tous' && p.domaine !== filterDomaine) return false;
    if (filterType !== 'Tous' && p.equipement_type !== filterType) return false;
    if (filterFournisseur !== 'Tous' && p.fournisseur.toLowerCase() !== filterFournisseur.toLowerCase()) return false;
    if (search) {
      const s = search.toLowerCase();
      return p.reference.toLowerCase().includes(s) || p.designation.toLowerCase().includes(s) || p.fournisseur.toLowerCase().includes(s);
    }
    return true;
  });

  // KPIs
  const lowStock = data.filter(p => p.stock_actuel <= p.stock_minimum);
  const ruptures = data.filter(p => p.stock_actuel === 0).length;
  const totalValeur = data.reduce((a, p) => a + p.stock_actuel * p.prix_unitaire, 0);
  const fournisseurs = new Set(data.map(p => p.fournisseur).filter(Boolean)).size;

  // Traceability data
  const traceData = useMemo(() => {
    const rows: any[] = [];
    interventionData.forEach((inter: any) => {
      const piecesStr = inter.pieces_utilisees || '';
      if (!piecesStr.trim()) return;
      // Les interventions récentes enregistrent une pièce par ligne afin de
      // conserver les métadonnées (référence, fournisseur, quantité). Les
      // anciennes données peuvent encore être séparées par des virgules ou
      // des points-virgules : on garde ce format comme solution de repli.
      const parts = piecesStr
        .split(/\r?\n/)
        .flatMap((line: string) => {
          const trimmed = line.trim();
          if (!trimmed) return [];
          return /\b(?:Ref(?:érence)?|Fournisseur|Qty|Qte|Quantit(?:é|e))\s*:/i.test(trimmed)
            ? [trimmed]
            : trimmed.replace(/;/g, ',').split(',');
        })
        .map((p: string) => p.trim())
        .filter(Boolean);
      parts.forEach((partName: string) => {
        const referenceMatch = partName.match(/\bRef(?:érence)?\s*:\s*([^|,]+)/i);
        const supplierMatch = partName.match(/\bFournisseur\s*:\s*([^|,]+)/i);
        const quantityMatch = partName.match(/\b(?:Qty|Qte|Quantit(?:é|e))\s*:\s*(\d+(?:[.,]\d+)?)/i);
        const reference = referenceMatch?.[1]?.trim() || '';
        const catalogPiece = data.find(piece => reference && piece.reference.toLowerCase() === reference.toLowerCase());
        // La désignation est affichée seule dans la colonne Pièce. Les
        // informations techniques restent disponibles dans leurs colonnes
        // dédiées, au lieu d'être concaténées dans une seule cellule.
        const designation = partName.split('|')[0].trim() || partName;
        rows.push({
          date: (inter.date || '').substring(0, 10),
          piece: designation,
          designation,
          reference,
          domaine: catalogPiece?.domaine || '',
          equipement_type: catalogPiece?.equipement_type || '',
          fournisseur: supplierMatch?.[1]?.trim() || catalogPiece?.fournisseur || '',
          quantite: quantityMatch?.[1] ? Number(quantityMatch[1].replace(',', '.')) : null,
          equipement: inter.machine || '',
          client: inter.client || '',
          technicien: inter.technicien || '',
          statut: inter.statut || '',
        });
      });
    });
    return rows.sort((a, b) => b.date.localeCompare(a.date));
  }, [interventionData, data]);

  const filteredTraceData = traceData.filter(row => {
    const searchTerm = traceSearch.toLowerCase().trim();
    if (searchTerm) {
      const matchesSearch = [row.piece, row.reference, row.fournisseur]
        .some(value => String(value || '').toLowerCase().includes(searchTerm));
      if (!matchesSearch) return false;
    }
    if (traceDomaineFilter && row.domaine !== traceDomaineFilter) return false;
    if (traceTypeFilter && row.equipement_type !== traceTypeFilter) return false;
    if (traceFournisseurFilter && row.fournisseur.toLowerCase() !== traceFournisseurFilter.toLowerCase()) return false;
    return true;
  });
  const traceDomaines = useMemo(() => ['Tous', ...new Set(traceData.map(row => row.domaine).filter(Boolean))], [traceData]);
  const traceTypes = useMemo(() => ['Tous', ...new Set(
    traceData
      .filter(row => !traceDomaineFilter || row.domaine === traceDomaineFilter)
      .map(row => row.equipement_type)
      .filter(Boolean),
  )], [traceData, traceDomaineFilter]);
  const traceSupplierOptions = useMemo(() => ['Tous', ...Array.from(new Set(
    traceData
      .filter(row => (!traceDomaineFilter || row.domaine === traceDomaineFilter)
        && (!traceTypeFilter || row.equipement_type === traceTypeFilter))
      .map(row => row.fournisseur)
      .filter(Boolean),
  )).sort((a, b) => a.localeCompare(b, 'fr'))], [traceData, traceDomaineFilter, traceTypeFilter]);

  const tabs = [
    { icon: <Package className="w-4 h-4" />, label: 'Stock' },
    { icon: <History className="w-4 h-4" />, label: 'Traçabilité' },
    { icon: <Edit className="w-4 h-4" />, label: 'Modifier / Supprimer' },
    { icon: <Brain className="w-4 h-4" />, label: 'Prédictions & Achats IA' },
    {
      icon: <Bell className="w-4 h-4" />,
      label: (
        <span className="flex items-center gap-1.5">
          Notifications
          {notifCount > 0 && (
            <span className="min-w-[18px] h-4.5 px-1 rounded-full bg-orange-500 text-white text-[10px] font-bold flex items-center justify-center">
              {notifCount > 99 ? '99+' : notifCount}
            </span>
          )}
        </span>
      ),
    },
  ];

  if (isLoading) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
            <Wrench className="w-7 h-7" /> Pièces de Rechange
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion du stock, traçabilité et prédictions IA</p>
        </div>
        <button onClick={() => { setSelectedPiece(null); setForm(emptyForm); setCustomFournisseur(false); setFormError(''); setShowAddModal(true); }} disabled={!canCreatePiece} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer shadow-lg disabled:opacity-50 disabled:cursor-not-allowed">
          <Plus className="w-4 h-4" /> Nouvelle Pièce
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-savia-accent"><Package className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-savia-accent">{data.length}</div>
          <div className="text-xs text-savia-text-muted mt-1">Total pièces</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-red-400"><TrendingDown className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-red-400">{lowStock.length}</div>
          <div className="text-xs text-savia-text-muted mt-1">Stock critique</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-green-400"><DollarSign className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-green-400">{(totalValeur / 1000).toFixed(0)}K</div>
          <div className="text-xs text-savia-text-muted mt-1">Valeur stock ({configuredCurrency})</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-purple-400"><Factory className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-purple-400">{fournisseurs}</div>
          <div className="text-xs text-savia-text-muted mt-1">Fournisseurs</div>
        </div>
      </div>

      {/* Alerte stock critique */}
      {lowStock.length > 0 && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <span className="font-bold text-red-400">{lowStock.length} pièce(s) en stock critique !</span>
            <span className="text-xs text-savia-text-muted ml-2">({ruptures} en rupture, {lowStock.length - ruptures} stock bas)</span>
          </div>
          <div className="space-y-2 max-h-40 overflow-y-auto">
            {lowStock.map(p => (
              <div key={p.id} className={`flex items-center justify-between p-2 rounded-lg ${p.stock_actuel === 0 ? 'bg-red-500/10 border-l-4 border-red-500' : 'bg-yellow-500/5 border-l-4 border-yellow-500'}`}>
                <div>
                  <span className="font-bold text-sm">{p.designation}</span>
                  <span className="text-xs text-savia-text-muted ml-2">{p.reference}</span>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span className="flex items-center gap-1"><Boxes className="w-3 h-3" /> {p.stock_actuel} / Min: {p.stock_minimum}</span>
                  <span className="flex items-center gap-1"><Factory className="w-3 h-3" /> {p.fournisseur}</span>
                  <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full font-bold ${p.stock_actuel === 0 ? 'bg-red-500 text-white' : 'bg-yellow-500 text-black'}`}>
                    {p.stock_actuel === 0 ? <><XCircle className="w-3 h-3" /> RUPTURE</> : <><AlertTriangle className="w-3 h-3" /> Bas</>}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Alerte pièces demandées (non référencées) */}
      {pendingDemandes.length > 0 && (
        <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <ShoppingCart className="w-5 h-5 text-blue-400" />
            <span className="font-bold text-blue-400">{pendingDemandes.length} pièce(s) demandée(s) par les techniciens</span>
            <span className="text-xs text-savia-text-muted ml-2">(non référencées — à commander)</span>
          </div>
          <div className="space-y-2 max-h-52 overflow-y-auto">
            {pendingDemandes.map((d: any) => (
              <div key={d.id} className="flex items-center justify-between p-3 rounded-lg bg-blue-500/10 border-l-4 border-blue-500">
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-sm">{d.reference}</span>
                    <span className="text-xs text-savia-text-muted">— {d.designation}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-savia-text-muted mt-1 flex-wrap">
                    <span className="flex items-center gap-1"><Hash className="w-3 h-3" /> Interv. #{d.intervention_id}</span>
                    <span className="flex items-center gap-1"><User className="w-3 h-3" /> {d.technicien}</span>
                    <span className="flex items-center gap-1"><Package2 className="w-3 h-3" /> {d.equipement}</span>
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> {d.date_creation ? new Date(d.date_creation).toLocaleDateString('fr-FR') : ''}</span>
                  </div>
                </div>
                <button
                  onClick={() => {
                    setLinkedDemandeId(d.id);
                    setFormError('');
                    // Matcher le nom machine vers un type d'équipement connu
                    const machineStr = (d.equipement || '').toLowerCase();
                    const matchedType = TYPES_EQUIPEMENTS.find(t => {
                      const keywords = t.toLowerCase().split(/[\s/]+/);
                      return keywords.some(kw => kw.length >= 3 && machineStr.includes(kw));
                    });
                    const equipmentContext = getEquipmentContext(d.equipement);
                      setForm({
                      ...emptyForm,
                      reference: d.reference || '',
                      designation: d.designation || '',
                      domaine: equipmentContext?.domaine || emptyForm.domaine,
                      equipement_type: equipmentContext?.type || matchedType || emptyForm.equipement_type,
                      notes: d.equipement ? `Équipement: ${d.equipement}` : '',
                    });
                    setShowAddModal(true);
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-green-600 hover:bg-green-500 transition-all cursor-pointer whitespace-nowrap ml-3"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Ajouter au stock
                </button>
              </div>
            ))}
          </div>
          <p className="text-xs text-blue-400/80 mt-2">
            💡 Cliquez sur « Ajouter au stock » pour créer la pièce pré-remplie. Le technicien sera notifié automatiquement après la création.
          </p>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-savia-border overflow-x-auto">
        {tabs.map((tab, i) => (
          <button key={i} onClick={() => setActiveTab(i)} className={`${TAB_CLS} ${activeTab === i ? TAB_ACTIVE : TAB_INACTIVE} whitespace-nowrap flex items-center gap-2`}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 0: STOCK */}
      {activeTab === 0 && (
        <div className="space-y-4">
          {/* Filtres propres à l'onglet Stock */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
              <input type="text" placeholder="Rechercher par référence, désignation ou fournisseur..." value={search} onChange={e => setSearch(e.target.value)}
                className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
            </div>
            <select value={filterDomaine} onChange={e => { setFilterDomaine(e.target.value); setFilterType('Tous'); setFilterFournisseur('Tous'); }} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              {domaines.map(d => <option key={d} value={d}>{d === 'Tous' ? 'Tous les domaines' : d}</option>)}
            </select>
            <select value={filterType} onChange={e => { setFilterType(e.target.value); setFilterFournisseur('Tous'); }} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              {stockTypes.map(t => <option key={t} value={t}>{t === 'Tous' ? 'Tous les types' : t}</option>)}
            </select>
            <select value={filterFournisseur} onChange={e => setFilterFournisseur(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              {stockSupplierOptions.map(name => <option key={name} value={name}>{name === 'Tous' ? 'Tous les fournisseurs' : name}</option>)}
            </select>
          </div>

          <div className="text-xs text-savia-text-muted flex items-center gap-1">
            <Package className="w-3.5 h-3.5" /> {filtered.length} pièce(s) affichée(s)
          </div>

          <SectionCard title="Inventaire Stock">
            <div className="overflow-x-auto">
              <div className="overflow-y-auto" style={{maxHeight: '380px'}}>
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-savia-surface z-10">
                    <tr className="border-b border-savia-border">
                      {['Référence', 'Désignation', 'Type Équip.', 'Stock', 'Min', 'Fournisseur', `Prix achat (${configuredCurrency})`, 'Dollar (USD)', 'Euro (EUR)'].map(h => (
                        <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(p => (
                      <tr key={p.id} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                        <td className="py-2.5 px-3 font-mono text-savia-accent font-bold text-xs">{p.reference}</td>
                        <td className="py-2.5 px-3 font-semibold">{p.designation}</td>
                        <td className="py-2.5 px-3 text-xs text-savia-text-muted">{p.equipement_type}</td>
                        <td className="py-2.5 px-3 text-center">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${p.stock_actuel === 0 ? 'bg-red-500/10 text-red-400' : p.stock_actuel <= p.stock_minimum ? 'bg-yellow-500/10 text-yellow-400' : 'bg-green-500/10 text-green-400'}`}>
                            {p.stock_actuel}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-center text-xs text-savia-text-muted">{p.stock_minimum}</td>
                        <td className="py-2.5 px-3 text-sm">{p.fournisseur}</td>
                        <td className="py-2.5 px-3 text-right font-mono text-sm">{formatMoney(p.prix_unitaire, configuredCurrency)}</td>
                        <td className="py-2.5 px-3 text-right font-mono text-sm">{formatMoney(getPriceInCurrency(p, 'USD'), 'USD')}</td>
                        <td className="py-2.5 px-3 text-right font-mono text-sm">{formatMoney(getPriceInCurrency(p, 'EUR'), 'EUR')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </SectionCard>
        </div>
      )}

      {/* TAB 1: TRAÇABILITÉ */}
      {activeTab === 1 && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div className="glass rounded-xl p-4 text-center">
              <div className="flex justify-center mb-2 text-savia-accent"><Wrench className="w-5 h-5" /></div>
              <div className="text-2xl font-black text-savia-accent">{new Set(traceData.map(t => t.piece)).size}</div>
              <div className="text-xs text-savia-text-muted mt-1">Pièces différentes</div>
            </div>
            <div className="glass rounded-xl p-4 text-center">
              <div className="flex justify-center mb-2 text-blue-400"><Building2 className="w-5 h-5" /></div>
              <div className="text-2xl font-black text-blue-400">{new Set(traceData.map(t => t.equipement)).size}</div>
              <div className="text-xs text-savia-text-muted mt-1">Équipements</div>
            </div>
            <div className="glass rounded-xl p-4 text-center">
              <div className="flex justify-center mb-2 text-purple-400"><Boxes className="w-5 h-5" /></div>
              <div className="text-2xl font-black text-purple-400">{traceData.length}</div>
              <div className="text-xs text-savia-text-muted mt-1">Utilisations totales</div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
              <input
                type="text"
                value={traceSearch}
                onChange={e => setTraceSearch(e.target.value)}
                placeholder="Rechercher une référence ou une pièce..."
                className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40"
              />
            </div>
            <select value={traceDomaineFilter} onChange={e => { setTraceDomaineFilter(e.target.value); setTraceTypeFilter(''); setTraceFournisseurFilter(''); }}
              className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              <option value="">Tous les domaines</option>
              {traceDomaines.filter(d => d !== 'Tous').map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <select value={traceTypeFilter} onChange={e => { setTraceTypeFilter(e.target.value); setTraceFournisseurFilter(''); }}
              className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              <option value="">Tous les types</option>
              {traceTypes.filter(t => t !== 'Tous').map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <select value={traceFournisseurFilter} onChange={e => setTraceFournisseurFilter(e.target.value)}
              className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              <option value="">Tous les fournisseurs</option>
              {traceSupplierOptions.filter(name => name !== 'Tous').map(name => <option key={name} value={name}>{name}</option>)}
            </select>
          </div>
          <div className="text-xs text-savia-text-muted flex items-center gap-1">
            <History className="w-3.5 h-3.5" /> {filteredTraceData.length} utilisation(s) affichée(s)
          </div>

          <SectionCard title="Historique d'utilisation des pièces">
            {filteredTraceData.length === 0 ? (
              <div className="text-center text-savia-text-muted py-8">
                {traceData.length === 0 ? 'Aucune donnée de traçabilité disponible.' : 'Aucune utilisation ne correspond aux filtres sélectionnés.'}
              </div>
            ) : (
              <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-savia-bg">
                    <tr className="border-b border-savia-border">
                      {['Date', 'Pièce', 'Référence', 'Fournisseur', 'Quantité', 'Équipement', 'Client', 'Technicien', 'Statut'].map(h => (
                        <th key={h} className="text-left py-2 px-3 text-savia-text-muted">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTraceData.map((t, i) => (
                      <tr key={i} className="border-b border-savia-border/30">
                        <td className="py-2 px-3 text-xs">{t.date}</td>
                        <td className="py-2 px-3 font-semibold text-savia-accent">{t.piece}</td>
                        <td className="py-2 px-3 font-mono text-xs">{t.reference || '—'}</td>
                        <td className="py-2 px-3 text-sm">{t.fournisseur || '—'}</td>
                        <td className="py-2 px-3 text-center">{t.quantite ?? '—'}</td>
                        <td className="py-2 px-3">{t.equipement}</td>
                        <td className="py-2 px-3 text-sm">{t.client}</td>
                        <td className="py-2 px-3">{t.technicien}</td>
                        <td className="py-2 px-3"><span className={`px-2 py-0.5 rounded-full text-xs font-bold ${t.statut?.toLowerCase().includes('tur') ? 'bg-green-500/10 text-green-400' : 'bg-yellow-500/10 text-yellow-400'}`}>{t.statut}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>
        </div>
      )}

      {/* TAB 2: MODIFIER / SUPPRIMER */}
      {activeTab === 2 && (() => {
        const editDomaines = [...new Set(data.map(p => p.domaine).filter(Boolean))].sort();
        const availableTypes = [...new Set(
          data
            .filter(p => !editDomaineFilter || p.domaine === editDomaineFilter)
            .map(p => p.equipement_type)
            .filter(Boolean)
        )].sort();
        const editSupplierOptions = [...new Set(
          data
            .filter(p => (!editDomaineFilter || p.domaine === editDomaineFilter)
              && (!editTypeFilter || p.equipement_type === editTypeFilter))
            .map(p => p.fournisseur)
            .filter(Boolean)
        )].sort((a, b) => a.localeCompare(b, 'fr'));
        const editFiltered = data.filter(p => {
          const searchTerm = editSearch.toLowerCase().trim();
          if (searchTerm && ![p.reference, p.designation, p.fournisseur]
            .some(value => String(value || '').toLowerCase().includes(searchTerm))) return false;
          if (editDomaineFilter && p.domaine !== editDomaineFilter) return false;
          if (editTypeFilter && p.equipement_type !== editTypeFilter) return false;
          if (editFournisseurFilter && p.fournisseur.toLowerCase() !== editFournisseurFilter.toLowerCase()) return false;
          return true;
        });
        return (
        <div className="space-y-3">
          <div className="flex gap-3 flex-wrap">
            <div className="relative flex-1 min-w-[240px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
              <input
                type="text"
                value={editSearch}
                onChange={e => setEditSearch(e.target.value)}
                placeholder="Rechercher une référence ou une pièce..."
                className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 text-sm"
              />
            </div>
            <select value={editDomaineFilter} onChange={e => { setEditDomaineFilter(e.target.value); setEditTypeFilter(''); setEditFournisseurFilter(''); }}
              className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 text-sm">
              <option value="">Tous domaines</option>
              {editDomaines.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <select value={editTypeFilter} onChange={e => { setEditTypeFilter(e.target.value); setEditFournisseurFilter(''); }}
              className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 text-sm">
              <option value="">Tous types équipement</option>
              {availableTypes.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <select value={editFournisseurFilter} onChange={e => setEditFournisseurFilter(e.target.value)}
              className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 text-sm">
              <option value="">Tous les fournisseurs</option>
              {editSupplierOptions.map(name => <option key={name} value={name}>{name}</option>)}
            </select>
            <span className="flex items-center text-xs text-savia-text-muted ml-auto">{editFiltered.length} pièce(s)</span>
          </div>
          {editFiltered.map(p => {
            const isLow = p.stock_actuel <= p.stock_minimum;
            return (
              <div key={p.id} className={`glass rounded-xl p-4 border ${isLow ? 'border-red-500/20' : 'border-savia-border/30'}`}>
                <div className="flex items-center justify-between flex-wrap gap-3">
                  <div className="flex items-center gap-3">
                    <span className={`text-lg flex items-center ${
                        p.stock_actuel === 0 ? 'text-red-400' : isLow ? 'text-yellow-400' : 'text-green-400'
                      }`}>
                      {p.stock_actuel === 0
                        ? <XCircle className="w-4 h-4" />
                        : isLow
                        ? <AlertTriangle className="w-4 h-4" />
                        : <CheckCircle2 className="w-4 h-4" />}
                    </span>
                    <div>
                      <div className="font-bold">{p.reference} — {p.designation}</div>
                      <div className="text-xs text-savia-text-muted">{p.equipement_type} | Stock: {p.stock_actuel} | Min: {p.stock_minimum} | {formatMoney(p.prix_unitaire, configuredCurrency)}</div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => {
                      setSelectedPiece(p);
                      setFormError('');
                    setForm({
                        reference: p.reference, designation: p.designation,
                        domaine: p.domaine || 'Radiologie',
                        equipement_type: p.equipement_type,
                        est_annexe: p.est_annexe,
                        stock_actuel: String(p.stock_actuel), stock_minimum: String(p.stock_minimum),
                        prix_unitaire: formatPriceInput(p.prix_unitaire), prix_usd: formatPriceInput(getPriceInCurrency(p, 'USD') || 0), prix_eur: formatPriceInput(getPriceInCurrency(p, 'EUR') || 0), delai_fournisseur_jours: String(p.delai_fournisseur_jours), fournisseur: p.fournisseur, notes: p.notes,
                      });
                      setCustomFournisseur(
                        Boolean(p.fournisseur) && !fournisseursList.some(item => item.toLowerCase() === p.fournisseur.toLowerCase()),
                      );
                      setShowEditModal(true);
                    }} className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 text-sm font-semibold cursor-pointer">
                      <Edit className="w-3.5 h-3.5" /> Modifier
                    </button>
                    <button onClick={() => handleDelete(p.id)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 text-sm font-semibold cursor-pointer">
                      <Trash2 className="w-3.5 h-3.5" /> Supprimer
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        );
      })()}

      {/* TAB 3: PRÉDICTIONS IA */}
      {activeTab === 3 && (
        <div className="space-y-6">

          {/* Tableau de prédictions */}
          <SectionCard title="État du Stock & Recommandations d'Achat">
            <div className="overflow-x-auto">
              <div className="overflow-y-auto" style={{maxHeight: '400px'}}>
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-savia-surface z-10">
                    <tr className="border-b border-savia-border">
                      {['Pièce', 'Type', 'Client(s) utilisateur(s)', 'Stock actuel', 'Min', 'Fournisseur', 'Prix unit.', 'Date prévision', 'Urgence'].map(h => (
                        <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data
                      .slice()
                      .sort((a, b) => {
                        // Le classement reprend la priorité du moteur serveur.
                        const priority: Record<string, number> = { CRITIQUE: 0, HAUTE: 1, NORMALE: 2, BASSE: 3, UNKNOWN: 4 };
                        const fallback = (piece: Piece) => piece.stock_actuel === 0 ? 0 : piece.stock_actuel <= piece.stock_minimum ? 1 : 3;
                        const urgA = priority[predictions[a.id]?.urgence] ?? fallback(a);
                        const urgB = priority[predictions[b.id]?.urgence] ?? fallback(b);
                        return urgA - urgB;
                      })
                      .map(p => {
                        const forecast = predictions[p.id] || {};
                        const clients = Array.isArray(forecast.clients_utilisateurs)
                          ? forecast.clients_utilisateurs.map((client: unknown) => String(client).trim()).filter(Boolean)
                          : [];
                        const isRupture = forecast.urgence === 'CRITIQUE' || p.stock_actuel === 0;
                        const isBas = !isRupture && (forecast.urgence === 'HAUTE' || p.stock_actuel <= p.stock_minimum);
                        const manquant = forecast.quantite_recommandee ?? Math.max(0, p.stock_minimum - p.stock_actuel + 1);
                        const forecastCost = getForecastCost(p, forecast);
                        return (
                          <tr key={p.id} className={`border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors ${
                            isRupture ? 'bg-red-500/5' : isBas ? 'bg-yellow-500/5' : ''
                          }`}>
                            <td className="py-2.5 px-3">
                              <div className="font-semibold text-sm">{p.designation}</div>
                              <div className="text-xs text-savia-text-muted font-mono">{p.reference}</div>
                            </td>
                            <td className="py-2.5 px-3 text-xs text-savia-text-muted">{p.equipement_type}</td>
                            <td className="py-2.5 px-3 text-xs min-w-[180px]">
                              {clients.length > 0 ? (
                                <button
                                  type="button"
                                  onClick={() => setSelectedPredictionClients({ piece: p.designation, clients })}
                                  className="text-left group cursor-pointer"
                                  aria-label={`Afficher les ${clients.length} clients concernés par ${p.designation}`}
                                >
                                  <span className="block font-semibold text-savia-accent group-hover:underline">
                                    {clients.length} client{clients.length > 1 ? 's' : ''} concerné{clients.length > 1 ? 's' : ''}
                                  </span>
                                  <span className="block text-savia-text-muted truncate max-w-[220px]" title={clients.join(', ')}>
                                    {clients.slice(0, 2).join(', ')}{clients.length > 2 ? ` +${clients.length - 2}` : ''}
                                  </span>
                                </button>
                              ) : <span className="text-savia-text-dim">Non documenté</span>}
                            </td>
                            <td className="py-2.5 px-3 text-center">
                              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                                isRupture ? 'bg-red-500/15 text-red-400' :
                                isBas ? 'bg-yellow-500/15 text-yellow-400' :
                                'bg-green-500/15 text-green-400'
                              }`}>{p.stock_actuel}</span>
                            </td>
                            <td className="py-2.5 px-3 text-center text-xs text-savia-text-muted">{p.stock_minimum}</td>
                            <td className="py-2.5 px-3 text-xs">{p.fournisseur || '—'}</td>
                            <td className="py-2.5 px-3 text-right font-mono text-xs">{formatMoney(p.prix_unitaire, configuredCurrency)}</td>
                            <td className="py-2.5 px-3">
                              <span className={`flex items-center gap-1 text-xs font-semibold ${
                                isRupture ? 'text-red-400' : isBas ? 'text-yellow-400' : 'text-green-400/80'
                              }`}>
                                <Calendar className="w-3 h-3" />
                                {getPredictionDisplay(p)}
                              </span>
                            </td>
                            <td className="py-2.5 px-3">
                              {isRupture ? (
                                <div className="space-y-0.5">
                                  <span className="flex items-center gap-1 text-xs font-bold text-red-400">
                                    <XCircle className="w-3 h-3" /> Commander immédiatement
                                  </span>
                                  <span className="text-[10px] text-red-400/70">À commander: {manquant} unité(s) · Coût: {formatMoney(forecastCost, configuredCurrency)}</span>
                                </div>
                              ) : isBas ? (
                                <div className="space-y-0.5">
                                  <span className="flex items-center gap-1 text-xs font-bold text-yellow-400">
                                    <AlertTriangle className="w-3 h-3" /> Commander bientôt
                                  </span>
                                  <span className="text-[10px] text-yellow-400/70">À commander: {manquant} unité(s) · Date: {forecast.date_commande || 'non calculable'} · Coût: {formatMoney(forecastCost, configuredCurrency)}</span>
                                </div>
                              ) : (
                                <span className="flex items-center gap-1 text-xs text-green-400">
                                  <CheckCircle2 className="w-3 h-3" /> Stock suffisant
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            </div>
          </SectionCard>

          {/* Analyse IA */}
          <SectionCard title="Assistant d'Achat Prédictif IA">
            <div className="text-center space-y-4">
              <p className="text-sm text-savia-text-muted">L&apos;IA analyse vos cycles de remplacement et niveaux de stock pour anticiper les ruptures.</p>
              <div className="flex gap-2 flex-wrap justify-center">
                <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-red-500/10 text-red-400">
                  <XCircle className="w-3 h-3" /> {ruptures} en rupture
                </span>
                <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-yellow-500/10 text-yellow-400">
                  <AlertTriangle className="w-3 h-3" /> {lowStock.length - ruptures} stock bas
                </span>
                <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-green-500/10 text-green-400">
                  <CheckCircle2 className="w-3 h-3" /> {data.length - lowStock.length} OK
                </span>
                <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-purple-500/10 text-purple-400">
                  <DollarSign className="w-3 h-3" /> Valeur: {(totalValeur / 1000).toFixed(0)}K {configuredCurrency}
                </span>
              </div>
              <button onClick={handleAiAnalyze} disabled={isAnalyzing} className="flex items-center gap-2 px-6 py-3 rounded-lg font-bold text-white bg-gradient-to-r from-purple-600 to-pink-500 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-purple-500/20 mx-auto disabled:opacity-50">
                {isAnalyzing ? <Loader2 className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
                {isAnalyzing ? 'Analyse en cours...' : 'Lancer l\'Analyse IA'}
              </button>
            </div>
          </SectionCard>

          {aiResult && (
            <SectionCard title="Résultat de l'Analyse IA">
              <div className="ai-analysis space-y-4">
                {aiResult.analyse_risque && (
                  <div className="p-4 rounded-lg bg-red-500/10 border-l-4 border-red-500">
                    <div className="flex items-center gap-2 font-bold text-sm text-red-400 mb-2 uppercase tracking-wider">
                      <AlertTriangle className="w-4 h-4" /> Analyse du Risque
                    </div>
                    <p className="text-sm text-savia-text leading-relaxed">{aiResult.analyse_risque}</p>
                  </div>
                )}
                {aiResult.couverture_donnees && (
                  <div className="p-4 rounded-lg bg-indigo-500/10 border-l-4 border-indigo-500">
                    <div className="flex items-center gap-2 font-bold text-sm text-indigo-300 mb-3 uppercase tracking-wider"><Brain className="w-4 h-4" /> Données réellement exploitées</div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                      <div className="p-2 rounded bg-savia-bg/40"><div className="font-black text-indigo-300">{aiResult.couverture_donnees.references_analysees ?? 0}</div><div className="text-[11px] text-savia-text-muted">références</div></div>
                      <div className="p-2 rounded bg-savia-bg/40"><div className="font-black text-red-400">{aiResult.couverture_donnees.ruptures_effectives ?? 0}</div><div className="text-[11px] text-savia-text-muted">ruptures réelles</div></div>
                      <div className="p-2 rounded bg-savia-bg/40"><div className="font-black text-cyan-300">{aiResult.couverture_donnees.predictions_calculables ?? 0}</div><div className="text-[11px] text-savia-text-muted">prévisions calculées</div></div>
                      <div className="p-2 rounded bg-savia-bg/40"><div className="font-black text-green-300">{aiResult.couverture_donnees.interventions_liees ?? 0}</div><div className="text-[11px] text-savia-text-muted">interventions liées</div></div>
                    </div>
                    <p className="text-xs text-savia-text-muted mt-3">Historique : {aiResult.couverture_donnees.avec_historique ?? 0}/{aiResult.couverture_donnees.references_analysees ?? 0} · Délais fournisseur : {aiResult.couverture_donnees.avec_delai_fournisseur ?? 0}/{aiResult.couverture_donnees.references_analysees ?? 0} · Prix catalogue : {aiResult.couverture_donnees.avec_prix ?? 0}/{aiResult.couverture_donnees.references_analysees ?? 0}</p>
                  </div>
                )}
                {aiResult.previsions_detaillees?.length > 0 && (
                  <div className="p-4 rounded-lg bg-savia-surface-hover/50 border-l-4 border-cyan-500">
                    <div className="flex items-center gap-2 font-bold text-sm text-cyan-400 mb-3 uppercase tracking-wider">
                      <Boxes className="w-4 h-4" /> Analyse détaillée par référence
                    </div>
                    <div className="space-y-3">
                      {aiResult.previsions_detaillees.map((d: any, i: number) => (
                        <div key={i} className="p-3 rounded-lg bg-savia-bg/40 border border-savia-border/50 text-xs space-y-2">
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <span className="font-bold">{d.piece} <span className="font-mono text-savia-text-muted">({d.reference})</span></span>
                            <span className={d.urgence === 'CRITIQUE' ? 'text-red-400 font-bold' : d.urgence === 'HAUTE' ? 'text-yellow-400 font-bold' : 'text-savia-text-muted'}>{d.urgence || 'UNKNOWN'}</span>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-5 gap-y-1 text-savia-text-muted">
                            <div>Équipement : {d.equipement_type || 'Non documenté'} · Client(s) : {d.clients?.length ? d.clients.join(', ') : 'Non documenté'}</div>
                            <div>Fournisseur : {d.fournisseur || 'Non renseigné'} · Délai : {d.delai_fournisseur_jours != null ? `${d.delai_fournisseur_jours} jours` : 'non renseigné'}</div>
                            <div>Stock : {d.stock_actuel ?? '—'} / seuil {d.stock_minimum ?? '—'} · Point de commande : {d.point_commande ?? 'non calculable'} · Stock sécurité : {d.stock_securite ?? 'non calculable'}</div>
                            <div>Prix unitaire : {d.prix_unitaire != null ? formatMoney(Number(d.prix_unitaire), configuredCurrency) : 'non renseigné'} · Coût de commande : {d.cout_estime != null ? formatMoney(Number(d.cout_estime), configuredCurrency) : 'non calculable'}</div>
                            <div>Usage : 30 j {d.consommation_30j ?? 0} · 90 j {d.consommation_90j ?? 0} · 12 mois {d.utilisations_total_365j ?? 0} · rythme {d.consommation_mensuelle ?? 0}/mois</div>
                            <div>Commande : {d.date_commande || 'non calculable'} · Rupture : {d.date_rupture_prevue || 'non calculable'} · Risque 30 j : {d.risque_rupture_30j_pct != null ? `${d.risque_rupture_30j_pct}%` : 'non calculable'} · Fiabilité : {d.fiabilite_donnees_pct ?? 0}%</div>
                          </div>
                          <div className="text-savia-text-muted bg-savia-surface/50 rounded px-2.5 py-2"><span className="font-semibold text-savia-text">Décision calculée :</span> {d.recommandation_actionnable ? `commander ${d.quantite_recommandee ?? 'à confirmer'} unité(s)` : 'pas de commande automatique'} — {d.raison || 'raison non renseignée'}.</div>
                          {formatContractCoverage(d.contrats) && <div className="text-savia-text-muted">Contrat : {formatContractCoverage(d.contrats)}</div>}
                          {formatFutureContractDemand(d.demande_contrats_futurs) && <div className="text-savia-text-muted">Maintenances à venir : {formatFutureContractDemand(d.demande_contrats_futurs)}</div>}
                          {Number(d.demandes_pieces_en_attente || 0) > 0 && <div className="text-savia-text-muted">Demandes techniciens en attente : {d.demandes_pieces_en_attente} · stock disponible après réservation : {d.stock_disponible_apres_demandes}</div>}
                          {d.diagnostics?.[0] && <div className="text-savia-text-muted">Diagnostic : {d.diagnostics[0].type || '—'} · {d.diagnostics[0].probleme || 'Problème non renseigné'} · Cause : {d.diagnostics[0].cause || 'non renseignée'} · Solution : {d.diagnostics[0].solution || 'non renseignée'}</div>}
                          {d.donnees_manquantes?.length > 0 && <div className="text-yellow-300 bg-yellow-500/10 border border-yellow-500/20 rounded px-2.5 py-2">À compléter : {d.donnees_manquantes.join(' · ')}</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {aiResult.points_a_completer?.length > 0 && (
                  <div className="p-4 rounded-lg bg-yellow-500/10 border-l-4 border-yellow-500">
                    <div className="flex items-center gap-2 font-bold text-sm text-yellow-300 mb-2 uppercase tracking-wider"><AlertTriangle className="w-4 h-4" /> Données à compléter pour fiabiliser les achats</div>
                    <div className="space-y-2 text-sm text-savia-text-muted">{aiResult.points_a_completer.map((item: any, index: number) => <div key={`${item.reference}-${index}`}><span className="font-semibold text-savia-text">{item.piece} ({item.reference}) :</span> {item.action}</div>)}</div>
                  </div>
                )}
                {aiResult.recommandations?.length > 0 && (
                  <div className="p-4 rounded-lg bg-yellow-500/10 border-l-4 border-yellow-500">
                    <div className="flex items-center gap-2 font-bold text-sm text-yellow-400 mb-3 uppercase tracking-wider">
                      <ShoppingCart className="w-4 h-4" /> Recommandations d&apos;Achat
                    </div>
                    <div className="space-y-3">
                      {aiResult.recommandations.map((r: any, i: number) => (
                        <div key={i} className={`p-3 rounded-lg ${r.urgence === 'critique' ? 'bg-red-500/10 border border-red-500/20' : r.urgence === 'haute' ? 'bg-yellow-500/10 border border-yellow-500/20' : 'bg-green-500/5 border border-green-500/10'}`}>
                          <div className="flex items-start justify-between flex-wrap gap-2 mb-2">
                            <div>
                              <span className="font-semibold text-sm">{r.piece}</span>
                              <span className="text-xs text-savia-text-muted ml-2 font-mono">{r.reference}</span>
                            </div>
                            <span className={`px-2 py-0.5 rounded-full font-bold text-[11px] ${r.urgence === 'critique' ? 'bg-red-500/20 text-red-400' : r.urgence === 'haute' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'}`}>{r.action}</span>
                          </div>
                          {r.raison && (
                            <div className="text-xs text-savia-text-muted bg-savia-bg/50 rounded px-3 py-2 mb-2 italic border-l-2 border-savia-accent/40">
                              {r.raison}
                            </div>
                          )}
                          {(r.clients_utilisateurs?.length > 0 || r.contrats?.length > 0 || r.diagnostics?.length > 0 || formatFutureContractDemand(r.demande_contrats_futurs) || Number(r.demandes_pieces_en_attente || 0) > 0) && (
                            <div className="text-xs text-savia-text-muted bg-savia-surface/50 rounded px-3 py-2 mb-2 space-y-1">
                              {r.clients_utilisateurs?.length > 0 && <div><span className="font-semibold">Clients concernés :</span> {r.clients_utilisateurs.join(', ')}</div>}
                              {formatContractCoverage(r.contrats) && <div><span className="font-semibold">Contrat :</span> {formatContractCoverage(r.contrats)}</div>}
                              {formatFutureContractDemand(r.demande_contrats_futurs) && <div><span className="font-semibold">Maintenances à venir :</span> {formatFutureContractDemand(r.demande_contrats_futurs)}</div>}
                              {Number(r.demandes_pieces_en_attente || 0) > 0 && <div><span className="font-semibold">Demandes techniciens :</span> {r.demandes_pieces_en_attente} en attente · stock disponible après réservation : {r.stock_disponible_apres_demandes}</div>}
                              {r.diagnostics?.[0] && <div><span className="font-semibold">Diagnostic récent :</span> {r.diagnostics[0].type || '—'} · {r.diagnostics[0].probleme || 'Problème non renseigné'} · Cause : {r.diagnostics[0].cause || 'non renseignée'} · Solution : {r.diagnostics[0].solution || 'non renseignée'}</div>}
                            </div>
                          )}
                          <div className="flex items-center gap-3 text-xs flex-wrap">
                            <span className="flex items-center gap-1"><Boxes className="w-3 h-3" /> {r.quantite ?? 'Non calculable'} unité(s)</span>
                            <span className="flex items-center gap-1"><Calendar className="w-3 h-3 text-blue-400" /><span className="text-blue-400 font-semibold">{r.date_achat || 'Non calculable'}</span></span>
                            <span className="flex items-center gap-1 text-green-400"><DollarSign className="w-3 h-3" />{r.cout_estime != null ? formatMoney(Number(r.cout_estime), configuredCurrency) : 'Non calculable'}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {aiResult.plan_achat?.length > 0 && (
                  <div className="p-4 rounded-lg bg-green-500/10 border-l-4 border-green-500">
                    <div className="flex items-center gap-2 font-bold text-sm text-green-400 mb-3 uppercase tracking-wider">
                      <Calendar className="w-4 h-4" /> Plan d&apos;Achat Planifié
                    </div>
                    <div className="space-y-2">
                      {aiResult.plan_achat.map((s: any, i: number) => (
                        <div key={i} className="flex items-start justify-between flex-wrap gap-2 p-3 rounded-lg bg-green-500/5">
                          <div><div className="font-semibold text-sm text-green-300">{s.semaine}</div><div className="text-xs text-savia-text-muted mt-1">{(s.pieces || []).join(' · ')}</div></div>
                          <span className="flex items-center gap-1 text-sm font-bold text-green-400"><DollarSign className="w-3.5 h-3.5" />{formatMoney(Number(s.budget), configuredCurrency)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {aiResult.impact_budget && (
                  <div className="p-4 rounded-lg bg-blue-500/10 border-l-4 border-blue-500">
                    <div className="flex items-center gap-2 font-bold text-sm text-blue-400 mb-3 uppercase tracking-wider"><DollarSign className="w-4 h-4" /> Impact Budget</div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div className="text-center p-3 rounded-lg bg-blue-500/10"><div className="text-lg font-black text-blue-400">{aiResult.impact_budget.cout_total_commande != null ? formatMoney(Number(aiResult.impact_budget.cout_total_commande), configuredCurrency) : 'Non calculable'}</div><div className="text-xs text-savia-text-muted">{aiResult.impact_budget.calcul_complet ? 'Coût total commande' : 'Coût connu (partiel)'}</div>{!aiResult.impact_budget.calcul_complet && aiResult.impact_budget.articles_sans_prix > 0 && <div className="text-[10px] text-yellow-400 mt-1">{aiResult.impact_budget.articles_sans_prix} pièce(s) sans prix</div>}</div>
                      <div className="text-center p-3 rounded-lg bg-green-500/10"><div className="text-lg font-black text-green-400">{aiResult.impact_budget.gain_potentiel != null ? formatMoney(Number(aiResult.impact_budget.gain_potentiel), configuredCurrency) : 'Non calculable'}</div><div className="text-xs text-savia-text-muted">Gain potentiel</div></div>
                      <div className="text-center p-3 rounded-lg bg-purple-500/10"><div className="text-sm font-bold text-purple-400 leading-tight">{aiResult.impact_budget.ratio}</div><div className="text-xs text-savia-text-muted mt-1">Ratio ROI</div></div>
                    </div>
                  </div>
                )}
                {aiResult.tendances?.length > 0 && (
                  <div className="p-4 rounded-lg bg-savia-surface-hover/50 space-y-2">
                    <div className="font-bold text-sm text-savia-text-muted uppercase tracking-wider mb-2">Tendances observées</div>
                    {aiResult.tendances.map((t: string, i: number) => (
                      <div key={i} className="flex items-start gap-2 text-sm text-savia-text"><span className="text-savia-accent mt-0.5">›</span>{t}</div>
                    ))}
                  </div>
                )}
              </div>
            </SectionCard>
          )}

          {/* Feedback — Validez les Prédictions */}
          <SectionCard title="Feedback — Validez les Prédictions IA">
            <div className="space-y-4">
              <p className="text-sm text-savia-text-muted">Sélectionnez une pièce et indiquez si la recommandation était correcte pour améliorer les futures analyses.</p>
              <select value={selectedFeedbackPiece} onChange={e => setSelectedFeedbackPiece(e.target.value)}
                className="w-full bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40">
                <option value="">— Sélectionner une pièce —</option>
                {data.filter(p => predictions[p.id]?.prediction_available).map(p => <option key={p.id} value={p.reference}>{p.designation} ({p.reference})</option>)}
              </select>
              {selectedFeedbackPiece && (
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-3">
                    <button onClick={() => submitFeedback('correct')} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-green-400 bg-green-500/10 border border-green-500/20 hover:bg-green-500/20 transition-all cursor-pointer"><ThumbsUp className="w-4 h-4" />Correct</button>
                    <button onClick={() => submitFeedback('faux_positif')} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-red-400 bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 transition-all cursor-pointer"><ThumbsDown className="w-4 h-4" />Faux positif</button>
                    <button onClick={() => setShowDatePicker(!showDatePicker)} className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-yellow-400 bg-yellow-500/10 border border-yellow-500/20 hover:bg-yellow-500/20 transition-all cursor-pointer ${showDatePicker ? 'ring-2 ring-yellow-500/40' : ''}`}><Calendar className="w-4 h-4" />Date décalée</button>
                    <button onClick={() => setShowFeedbackHistory(!showFeedbackHistory)} className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-savia-text-muted bg-savia-surface border border-savia-border hover:bg-savia-surface-hover transition-all cursor-pointer ${showFeedbackHistory ? 'ring-2 ring-savia-accent/40' : ''}`}><History className="w-4 h-4" />Historique</button>
                  </div>
                  {showDatePicker && (
                    <div className="flex items-center gap-3 p-4 rounded-lg bg-yellow-500/5 border border-yellow-500/20 flex-wrap">
                      <Calendar className="w-5 h-5 text-yellow-400" />
                      <span className="text-sm text-savia-text-muted">Vraie date de commande :</span>
                      <input type="date" value={decaleDate} onChange={e => setDecaleDate(e.target.value)} className="bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-savia-text focus:ring-2 focus:ring-yellow-500/40" />
                      <button onClick={() => { if (decaleDate) submitFeedback('decale', decaleDate); }} disabled={!decaleDate} className="px-4 py-2 rounded-lg font-semibold text-white bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 transition-all cursor-pointer">Valider</button>
                    </div>
                  )}
                  {feedbackSuccess && (<div className="flex items-center gap-2 p-3 rounded-lg bg-green-500/10 text-green-400 text-sm font-semibold"><ShieldCheck className="w-4 h-4" />{feedbackSuccess}</div>)}
                </div>
              )}
              {showFeedbackHistory && feedbackHistory.length > 0 && (
                <div className="mt-2 space-y-2">
                  <h4 className="text-sm font-bold text-savia-text-muted flex items-center gap-2"><History className="w-4 h-4" />Historique ({feedbackHistory.length} entrées)</h4>
                  <div className="max-h-[200px] overflow-y-auto space-y-2">
                    {feedbackHistory.map((fb: any, i: number) => (
                      <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-savia-bg/50 text-sm">
                        <div className={`p-1.5 rounded-full ${fb.type === 'correct' ? 'bg-green-500/10 text-green-400' : fb.type === 'faux_positif' ? 'bg-red-500/10 text-red-400' : 'bg-yellow-500/10 text-yellow-400'}`}>
                          {fb.type === 'correct' ? <ThumbsUp className="w-3.5 h-3.5" /> : fb.type === 'faux_positif' ? <ThumbsDown className="w-3.5 h-3.5" /> : <Calendar className="w-3.5 h-3.5" />}
                        </div>
                        <div className="flex-1"><span className="font-semibold">{fb.piece}</span><span className="text-savia-text-dim ml-2">{fb.type === 'correct' ? '— Correct' : fb.type === 'faux_positif' ? '— Faux positif' : `— Décalé → ${fb.vraiDate}`}</span></div>
                        <span className="text-xs text-savia-text-dim">{new Date(fb.timestamp).toLocaleDateString('fr-FR')}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {showFeedbackHistory && feedbackHistory.length === 0 && (
                <div className="mt-2 text-center p-6 text-savia-text-muted text-sm"><History className="w-8 h-8 mx-auto mb-2 text-savia-text-dim" />Aucun feedback enregistré.</div>
              )}
            </div>
          </SectionCard>
        </div>
      )}

      {/* TAB 4: NOTIFICATIONS */}
      {activeTab === 4 && (
        <div className="space-y-4">
          <SectionCard title="Notifications Pièces">
            {notifData.length === 0 ? (
              <div className="text-center py-12 text-savia-text-muted">
                <Bell className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p className="text-sm">Aucune notification pour le moment.</p>
                <p className="text-xs mt-1 opacity-60">Les alertes de rupture et disponibilité apparaîtront ici.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {notifData.map((n: any) => {
                  const isRupture = n.type === 'piece_rupture';
                  const isDispo = n.type === 'piece_dispo';
                  const isUnread = n.statut === 'non_lu';
                  return (
                    <div key={n.id} className={`p-4 rounded-xl border transition-colors ${
                      isUnread
                        ? isRupture
                          ? 'bg-orange-500/10 border-orange-500/30'
                          : 'bg-green-500/10 border-green-500/30'
                        : 'bg-savia-surface-hover/40 border-savia-border/30 opacity-70'
                    }`}>
                      {/* Header: icon + badge + date + action */}
                      <div className="flex items-center gap-2 mb-2">
                        <div className={`p-1.5 rounded-full flex-shrink-0 ${
                          isRupture ? 'bg-orange-500/20 text-orange-400'
                          : isDispo ? 'bg-green-500/20 text-green-400'
                          : 'bg-blue-500/20 text-blue-400'
                        }`}>
                          {isRupture ? <AlertTriangle className="w-4 h-4" /> : <Package2 className="w-4 h-4" />}
                        </div>
                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                          isRupture ? 'bg-orange-500/20 text-orange-400' : 'bg-green-500/20 text-green-400'
                        }`}>
                          {isRupture ? 'Rupture de stock' : 'Pièce disponible'}
                        </span>
                        {isUnread && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/20 text-blue-400 font-bold">NOUVEAU</span>
                        )}
                        <span className="text-xs text-savia-text-muted ml-auto">
                          {n.date_creation ? new Date(n.date_creation).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''}
                        </span>
                        <button
                          onClick={() => notifApi.markDone(Number(n.id)).then(loadNotifs)}
                          title="Marquer comme traité"
                          className="flex-shrink-0 p-1.5 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted hover:text-green-400 transition-colors cursor-pointer"
                        >
                          <CheckCheck className="w-4 h-4" />
                        </button>
                      </div>

                      {/* Piece info */}
                      {(n.piece_nom || n.piece_reference) && (
                        <div className="flex items-center gap-2 mb-2">
                          <Package className="w-4 h-4 flex-shrink-0" style={{ color: isRupture ? '#e67e22' : '#27ae60' }} />
                          <span className="font-bold text-sm">{n.piece_nom || n.piece_reference}</span>
                          {n.piece_reference && n.piece_nom && (
                            <span className="text-[11px] font-mono bg-savia-surface-hover px-1.5 py-0.5 rounded text-savia-text-muted">{n.piece_reference}</span>
                          )}
                        </div>
                      )}

                      {/* Detail grid */}
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                        {n.intervention_id && (
                          <div className="flex items-center gap-1.5">
                            <Hash className="w-3 h-3 text-savia-accent" />
                            <span className="text-savia-text-muted">Intervention</span>
                            <span className="font-semibold">#{n.intervention_id}</span>
                          </div>
                        )}
                        {n.equipement && (
                          <div className="flex items-center gap-1.5">
                            <Wrench className="w-3 h-3 text-savia-accent" />
                            <span className="text-savia-text-muted">Équip.</span>
                            <span className="font-semibold">{n.equipement}</span>
                          </div>
                        )}
                        {n.client && (
                          <div className="flex items-center gap-1.5">
                            <Building2 className="w-3 h-3 text-savia-accent" />
                            <span className="text-savia-text-muted">Client</span>
                            <span className="font-semibold">{n.client}</span>
                          </div>
                        )}
                        {n.technicien && (
                          <div className="flex items-center gap-1.5">
                            <User className="w-3 h-3 text-savia-accent" />
                            <span className="text-savia-text-muted">Tech.</span>
                            <span className="font-semibold">{n.technicien}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </SectionCard>
        </div>
      )}

      {/* Add Modal */}
      <Modal isOpen={showAddModal} onClose={() => setShowAddModal(false)} title="➕ Nouvelle Pièce" size="lg">
        <div className="space-y-4">
          {formError && <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-semibold">{formError}</div>}
          {/* Domaine médical - unique source of truth from equipment */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted mb-2 uppercase tracking-wider">Domaine médical *</label>
            <div className="flex flex-wrap gap-2">
              {customDomaines.length > 0 ? (
                // Use equipment-defined domains (dynamic)
                customDomaines.map(d => {
                  const firstType = (customTypesForDomain[d] && customTypesForDomain[d].length > 0) ? customTypesForDomain[d][0] : 'Autre';
                  return (
                    <button key={d} type="button"
                      onClick={() => setForm({...form, domaine: d, equipement_type: firstType, est_annexe: false})}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer border ${
                        form.domaine === d
                          ? 'bg-purple-600 text-white border-purple-600 shadow-md'
                          : 'bg-purple-500/10 text-purple-400 border-purple-500/30 hover:border-purple-500/60'
                      }`}>{d}</button>
                  );
                })
              ) : (
                // Fallback to hardcoded domains if no equipment has been created yet
                ALL_DOMAINES.map(d => (
                  <button key={d} type="button"
                    onClick={() => setForm({...form, domaine: d, equipement_type: DOMAINES_TYPES[d][0], est_annexe: false})}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer border ${
                      form.domaine === d
                        ? 'bg-savia-accent text-white border-savia-accent shadow-md'
                        : 'bg-savia-surface-hover text-savia-text border-savia-border hover:border-savia-accent/50'
                    }`}>{d}</button>
                ))
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-savia-text-muted mb-1">Type d&apos;équipement *</label>
              <select required className={INPUT_CLS}
                value={form.equipement_type || getAvailableTypes()[0]}
                onChange={e => setForm({...form, equipement_type: e.target.value})}>
                {getAvailableTypes().map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            {form.domaine === 'Radiologie' && (
              <div className="flex items-center">
                <label className="flex items-center gap-3 cursor-pointer group mt-5">
                  <div onClick={() => setForm({...form, est_annexe: !form.est_annexe})}
                    className={`w-5 h-5 rounded flex items-center justify-center border-2 transition-all cursor-pointer ${
                      form.est_annexe ? 'bg-savia-accent border-savia-accent' : 'border-savia-border group-hover:border-savia-accent/60'
                    }`}>
                    {form.est_annexe && <span className="text-white text-xs font-bold">✓</span>}
                  </div>
                  <div>
                    <span className="text-sm font-semibold text-savia-text">Pièce équip. annexe</span>
                    <p className="text-xs text-savia-text-muted">Gén. HT, capteur plan, etc.</p>
                  </div>
                </label>
              </div>
            )}
            <div><label className="block text-sm text-savia-text-muted mb-1">Référence *</label><input required className={INPUT_CLS} placeholder="TUBE-RX-001" value={form.reference} onChange={e => setForm({...form, reference: e.target.value})} /></div>
            <div><label className="block text-sm text-savia-text-muted mb-1">Désignation *</label><input required className={INPUT_CLS} placeholder="Tube radiogène" value={form.designation} onChange={e => setForm({...form, designation: e.target.value})} /></div>
            <div><label className="block text-sm text-savia-text-muted mb-1">Stock actuel *</label><input required min="0" step="1" type="number" className={INPUT_CLS} value={form.stock_actuel} onChange={e => setForm({...form, stock_actuel: e.target.value})} /></div>
            <div><label className="block text-sm text-savia-text-muted mb-1">Stock minimum (seuil alerte) *</label><input required min="0" step="1" type="number" className={INPUT_CLS} value={form.stock_minimum} onChange={e => setForm({...form, stock_minimum: e.target.value})} /></div>
            <div><label className="block text-sm text-savia-text-muted mb-1">Délai fournisseur (jours) *</label><input required min="0" max="365" step="1" type="number" className={INPUT_CLS} value={form.delai_fournisseur_jours} onChange={e => setForm({...form, delai_fournisseur_jours: e.target.value})} /><p className="text-xs text-savia-text-dim mt-1">0 = disponibilité immédiate</p></div>
            <div className="md:col-span-2 rounded-xl border border-savia-border/60 bg-savia-surface-hover/30 p-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div><label className="block text-sm text-savia-text-muted mb-1">Prix d&apos;achat ({configuredCurrency}) *</label><input required min="1" step="1" type="number" className={INPUT_CLS} value={roundedFormPrice(form.prix_unitaire)} onChange={e => updatePurchasePrice('prix_unitaire', configuredCurrency, e.target.value)} /></div>
                <div><label className="block text-sm text-savia-text-muted mb-1">Prix d&apos;achat (USD) *</label><input required min="1" step="1" type="number" className={INPUT_CLS} value={roundedFormPrice(form.prix_usd)} onChange={e => updatePurchasePrice('prix_usd', 'USD', e.target.value)} /></div>
                <div><label className="block text-sm text-savia-text-muted mb-1">Prix d&apos;achat (EUR) *</label><input required min="1" step="1" type="number" className={INPUT_CLS} value={roundedFormPrice(form.prix_eur)} onChange={e => updatePurchasePrice('prix_eur', 'EUR', e.target.value)} /></div>
              </div>
              <p className={`mt-2 text-xs ${exchangeRatesError ? 'text-red-400' : 'text-savia-text-dim'}`}>
                {exchangeRatesError || (exchangeRates ? 'La saisie d’un montant met automatiquement à jour les deux autres devises.' : 'Chargement des taux de change…')}
              </p>
            </div>
            <div>
              <label className="block text-sm text-savia-text-muted mb-1">Fournisseur *</label>
              {customFournisseur ? (
                <div className="flex gap-2">
                  <input required className={INPUT_CLS} placeholder="Nom du fournisseur..." value={form.fournisseur}
                    onChange={e => setForm({...form, fournisseur: e.target.value})} />
                  <button type="button" onClick={() => registerFournisseur(form.fournisseur)} disabled={!form.fournisseur.trim()}
                    className="px-3 py-2 rounded-lg bg-savia-accent/20 text-savia-accent text-xs whitespace-nowrap hover:bg-savia-accent/30 disabled:opacity-50 cursor-pointer" title="Enregistrer le fournisseur">
                    <Save className="w-3.5 h-3.5" />
                  </button>
                </div>
              ) : (
                <select required className={INPUT_CLS} value={form.fournisseur} onChange={e => {
                  if (e.target.value === '__autre__') { setCustomFournisseur(true); setForm({...form, fournisseur: ''}); }
                  else setForm({...form, fournisseur: e.target.value});
                }}>
                  <option value="">— Sélectionner —</option>
                  {fournisseursList.map(f => <option key={f} value={f}>{f}</option>)}
                  <option value="__autre__">+ Autre (saisie manuelle)</option>
                </select>
              )}
            </div>
            <div className="md:col-span-2"><label className="block text-sm text-savia-text-muted mb-1">Notes</label><input className={INPUT_CLS} value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} /></div>
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-white/5">
          <button onClick={() => setShowAddModal(false)} className="px-4 py-2 rounded-lg text-savia-text-muted hover:text-savia-text cursor-pointer">Annuler</button>
          <button onClick={handleSave} disabled={isSaving || !exchangeRates} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-savia-text bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-90 disabled:opacity-50 cursor-pointer">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Sauvegarder
          </button>
        </div>
      </Modal>

      {/* Edit Modal */}
      <Modal isOpen={showEditModal} onClose={() => setShowEditModal(false)} title={`✏️ Modifier — ${selectedPiece?.designation || ''}`} size="lg">
        <div className="space-y-4">
          {formError && <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-semibold">{formError}</div>}
          {/* Domaine médical - unique source of truth from equipment */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted mb-2 uppercase tracking-wider">Domaine médical *</label>
            <div className="flex flex-wrap gap-2">
              {customDomaines.length > 0 ? (
                // Use equipment-defined domains (dynamic)
                customDomaines.map(d => {
                  const firstType = (customTypesForDomain[d] && customTypesForDomain[d].length > 0) ? customTypesForDomain[d][0] : 'Autre';
                  return (
                    <button key={d} type="button"
                      onClick={() => setForm({...form, domaine: d, equipement_type: firstType, est_annexe: false})}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer border ${
                        form.domaine === d
                          ? 'bg-purple-600 text-white border-purple-600 shadow-md'
                          : 'bg-purple-500/10 text-purple-400 border-purple-500/30 hover:border-purple-500/60'
                      }`}>{d}</button>
                  );
                })
              ) : (
                // Fallback to hardcoded domains if no equipment has been created yet
                ALL_DOMAINES.map(d => (
                  <button key={d} type="button"
                    onClick={() => setForm({...form, domaine: d, equipement_type: DOMAINES_TYPES[d][0], est_annexe: false})}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer border ${
                      form.domaine === d
                        ? 'bg-savia-accent text-white border-savia-accent shadow-md'
                        : 'bg-savia-surface-hover text-savia-text border-savia-border hover:border-savia-accent/50'
                    }`}>{d}</button>
                ))
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-savia-text-muted mb-1">Type d&apos;équipement *</label>
              <select required className={INPUT_CLS}
                value={form.equipement_type || getAvailableTypes()[0]}
                onChange={e => setForm({...form, equipement_type: e.target.value})}>
                {getAvailableTypes().map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            {form.domaine === 'Radiologie' && (
              <div className="flex items-center">
                <label className="flex items-center gap-3 cursor-pointer group mt-5">
                  <div onClick={() => setForm({...form, est_annexe: !form.est_annexe})}
                    className={`w-5 h-5 rounded flex items-center justify-center border-2 transition-all cursor-pointer ${
                      form.est_annexe ? 'bg-savia-accent border-savia-accent' : 'border-savia-border group-hover:border-savia-accent/60'
                    }`}>
                    {form.est_annexe && <span className="text-white text-xs font-bold">✓</span>}
                  </div>
                  <div>
                    <span className="text-sm font-semibold text-savia-text">Pièce équip. annexe</span>
                    <p className="text-xs text-savia-text-muted">Gén. HT, capteur plan, etc.</p>
                  </div>
                </label>
              </div>
            )}
            <div><label className="block text-sm text-savia-text-muted mb-1">Référence *</label><input required className={INPUT_CLS} value={form.reference} onChange={e => setForm({...form, reference: e.target.value})} /></div>
            <div><label className="block text-sm text-savia-text-muted mb-1">Désignation *</label><input required className={INPUT_CLS} value={form.designation} onChange={e => setForm({...form, designation: e.target.value})} /></div>
            <div><label className="block text-sm text-savia-text-muted mb-1">Stock actuel *</label><input required min="0" step="1" type="number" className={INPUT_CLS} value={form.stock_actuel} onChange={e => setForm({...form, stock_actuel: e.target.value})} /></div>
            <div><label className="block text-sm text-savia-text-muted mb-1">Stock minimum (seuil alerte) *</label><input required min="0" step="1" type="number" className={INPUT_CLS} value={form.stock_minimum} onChange={e => setForm({...form, stock_minimum: e.target.value})} /></div>
            <div><label className="block text-sm text-savia-text-muted mb-1">Délai fournisseur (jours) *</label><input required min="0" max="365" step="1" type="number" className={INPUT_CLS} value={form.delai_fournisseur_jours} onChange={e => setForm({...form, delai_fournisseur_jours: e.target.value})} /><p className="text-xs text-savia-text-dim mt-1">0 = disponibilité immédiate</p></div>
            <div className="md:col-span-2 rounded-xl border border-savia-border/60 bg-savia-surface-hover/30 p-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div><label className="block text-sm text-savia-text-muted mb-1">Prix d&apos;achat ({configuredCurrency}) *</label><input required min="1" step="1" type="number" className={INPUT_CLS} value={roundedFormPrice(form.prix_unitaire)} onChange={e => updatePurchasePrice('prix_unitaire', configuredCurrency, e.target.value)} /></div>
                <div><label className="block text-sm text-savia-text-muted mb-1">Prix d&apos;achat (USD) *</label><input required min="1" step="1" type="number" className={INPUT_CLS} value={roundedFormPrice(form.prix_usd)} onChange={e => updatePurchasePrice('prix_usd', 'USD', e.target.value)} /></div>
                <div><label className="block text-sm text-savia-text-muted mb-1">Prix d&apos;achat (EUR) *</label><input required min="1" step="1" type="number" className={INPUT_CLS} value={roundedFormPrice(form.prix_eur)} onChange={e => updatePurchasePrice('prix_eur', 'EUR', e.target.value)} /></div>
              </div>
              <p className={`mt-2 text-xs ${exchangeRatesError ? 'text-red-400' : 'text-savia-text-dim'}`}>
                {exchangeRatesError || (exchangeRates ? 'La saisie d’un montant met automatiquement à jour les deux autres devises.' : 'Chargement des taux de change…')}
              </p>
            </div>
            <div>
              <label className="block text-sm text-savia-text-muted mb-1">Fournisseur *</label>
              {customFournisseur ? (
                <div className="flex gap-2">
                  <input required className={INPUT_CLS} placeholder="Nom du fournisseur..." value={form.fournisseur}
                    onChange={e => setForm({...form, fournisseur: e.target.value})} />
                  <button type="button" onClick={() => registerFournisseur(form.fournisseur)} disabled={!form.fournisseur.trim()}
                    className="px-3 py-2 rounded-lg bg-savia-accent/20 text-savia-accent text-xs whitespace-nowrap hover:bg-savia-accent/30 disabled:opacity-50 cursor-pointer" title="Enregistrer le fournisseur">
                    <Save className="w-3.5 h-3.5" />
                  </button>
                </div>
              ) : (
                <select required className={INPUT_CLS} value={form.fournisseur} onChange={e => {
                  if (e.target.value === '__autre__') { setCustomFournisseur(true); setForm({...form, fournisseur: ''}); }
                  else setForm({...form, fournisseur: e.target.value});
                }}>
                  <option value="">— Sélectionner —</option>
                  {fournisseursList.map(f => <option key={f} value={f}>{f}</option>)}
                  <option value="__autre__">+ Autre (saisie manuelle)</option>
                </select>
              )}
            </div>
            <div className="md:col-span-2"><label className="block text-sm text-savia-text-muted mb-1">Notes</label><input className={INPUT_CLS} value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} /></div>
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-white/5">
          <button onClick={() => setShowEditModal(false)} className="px-4 py-2 rounded-lg text-savia-text-muted hover:text-savia-text cursor-pointer">Annuler</button>
          <button onClick={handleEdit} disabled={isSaving || !exchangeRates} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-savia-text bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-90 disabled:opacity-50 cursor-pointer">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Enregistrer
          </button>
        </div>
      </Modal>

      {/* Liste détaillée des clients d'une pièce, ouverte à la demande */}
      <Modal
        isOpen={Boolean(selectedPredictionClients)}
        onClose={() => setSelectedPredictionClients(null)}
        title={`Clients concernés — ${selectedPredictionClients?.piece || ''}`}
        size="md"
      >
        {selectedPredictionClients && (
          <div className="space-y-4">
            <p className="text-sm text-savia-text-muted">
              {selectedPredictionClients.clients.length} client{selectedPredictionClients.clients.length > 1 ? 's' : ''} concerné{selectedPredictionClients.clients.length > 1 ? 's' : ''} par cette pièce.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {selectedPredictionClients.clients.map((client, index) => (
                <div key={`${client}-${index}`} className="rounded-lg border border-savia-border/60 bg-savia-surface-hover/40 px-3 py-2 text-sm">
                  {client}
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
