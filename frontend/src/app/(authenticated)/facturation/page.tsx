'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle, ArrowRight, Banknote, Ban, Building2, Calendar,
  Check, CheckCircle2, Circle, Clock3, Eye, FileCheck2, FileText, History,
  Loader2, PackageCheck, Plus, Receipt, RefreshCw, Search, Send,
  Trash2, Users, WalletCards, Wrench, X,
} from 'lucide-react';
import { billing, clients as clientsApi, equipements, interventions, settings as settingsApi } from '@/lib/api';
import { Modal } from '@/components/ui/modal';
import { useAuth } from '@/lib/auth-context';
import { useRoleGuard } from '@/lib/use-role-guard';
import { KpiCard } from '@/components/ui/cards';


type StepType = 'quote' | 'purchase_order' | 'delivery_note' | 'invoice';

interface BillingStep {
  id: number;
  step_type: StepType;
  effective_date?: string | null;
  due_date?: string | null;
  reference?: string;
  amount?: number | null;
  not_required?: boolean;
  note?: string;
  created_by?: string;
  updated_by?: string;
  updated_at?: string;
}

interface BillingPayment {
  id: number;
  effective_date: string;
  amount: number;
  reference?: string;
  payment_method?: string;
  note?: string;
  created_by?: string;
}

interface BillingCase {
  id: number;
  reused_existing_case?: boolean;
  merged_into_case_id?: number | null;
  intervention_id?: number | null;
  request_id?: number | null;
  client: string;
  equipment: string;
  owner_username: string;
  currency: string;
  case_state: 'active' | 'blocked' | 'cancelled';
  block_reason: string;
  created_by?: string;
  contract_id?: number | null;
  contract_type?: string;
  coverage_status: 'unassessed' | 'covered' | 'partial' | 'billable' | 'review';
  coverage_status_label: string;
  coverage_reason?: string;
  labor_amount?: number;
  parts_amount?: number;
  uncovered_labor_cost: number;
  uncovered_parts_cost: number;
  uncovered_total_cost: number;
  coverage_assessed_at?: string | null;
  intervention_status?: string;
  technicien?: string;
  intervention_date?: string | null;
  intervention_started_at?: string | null;
  intervention_closed_at?: string | null;
  intervention_type?: string;
  intervention_description?: string;
  intervention_problem?: string;
  intervention_cause?: string;
  intervention_solution?: string;
  intervention_error_code?: string;
  intervention_error_type?: string;
  intervention_priority?: string;
  intervention_notes?: string;
  intervention_duration_minutes?: number;
  intervention_travel_minutes?: number;
  intervention_start_time?: string;
  intervention_end_time?: string;
  intervention_technicians?: Array<{
    name: string;
    duration_minutes: number;
    travel_minutes: number;
    status: string;
  }>;
  pieces_utilisees?: string;
  has_parts: boolean;
  steps: Partial<Record<StepType, BillingStep>>;
  payments: BillingPayment[];
  paid_amount: number;
  invoice_amount: number;
  remaining_amount: number;
  status: string;
  status_label: string;
  next_step?: string | null;
  overdue: boolean;
  overdue_days: number;
  stage_age_days?: number | null;
  data_incomplete: boolean;
  lead_times: Record<string, number | null>;
}

interface HistoryItem {
  id: number;
  action: string;
  entity_type: string;
  change_reason?: string;
  actor_username: string;
  occurred_at: string;
  before_data?: Record<string, unknown> | null;
  after_data?: Record<string, unknown> | null;
}

interface InterventionOption {
  id: number;
  client: string;
  machine: string;
  statut: string;
  date: string;
}

interface EquipmentOption {
  id: number;
  name: string;
  client: string;
}

interface ResponsibleOption {
  username: string;
  display_name: string;
  role: string;
}

interface DuplicateResolutionState {
  first: BillingCase;
  second: BillingCase;
  keepCaseId: number;
  interventionCaseId: number;
  reason: string;
}

const INPUT = 'w-full rounded-lg border border-savia-border bg-savia-surface-hover px-3 py-2.5 text-sm text-savia-text outline-none transition focus:ring-2 focus:ring-savia-accent/40';
const LABEL = 'mb-1 block text-xs font-semibold uppercase tracking-wider text-savia-text-muted';

const STEP_META: Record<StepType, { label: string; icon: typeof FileText }> = {
  quote: { label: 'Devis créé', icon: FileText },
  purchase_order: { label: 'Bon de commande reçu', icon: FileCheck2 },
  delivery_note: { label: 'Bon de livraison validé', icon: PackageCheck },
  invoice: { label: 'Facture envoyée', icon: Send },
};

const STATUS_STYLE: Record<string, string> = {
  quote_pending: 'bg-slate-500/15 text-slate-300 border-slate-500/25',
  purchase_order_pending: 'bg-blue-500/15 text-blue-300 border-blue-500/25',
  ready_for_intervention: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/25',
  intervention_in_progress: 'bg-violet-500/15 text-violet-300 border-violet-500/25',
  delivery_note_pending: 'bg-amber-500/15 text-amber-300 border-amber-500/25',
  invoice_pending: 'bg-orange-500/15 text-orange-300 border-orange-500/25',
  payment_pending: 'bg-teal-500/15 text-teal-300 border-teal-500/25',
  partial_payment: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/25',
  paid: 'bg-green-500/15 text-green-300 border-green-500/25',
  covered_by_contract: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25',
  coverage_review: 'bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/25',
  blocked: 'bg-red-500/15 text-red-300 border-red-500/25',
  cancelled: 'bg-slate-500/15 text-slate-400 border-slate-500/25',
};

const NEXT_ACTION: Record<string, string> = {
  quote: 'Renseigner le devis',
  purchase_order: 'Valider le bon de commande',
  intervention: "Démarrer l'intervention",
  intervention_close: "Clôturer l'intervention",
  delivery_note: 'Valider le bon de livraison',
  invoice: "Renseigner l'envoi de la facture",
  payment: 'Enregistrer un paiement',
};

const today = () => new Date().toISOString().substring(0, 10);
const money = (value: number, currency: string) => `${Number(value || 0).toLocaleString('fr-FR', { maximumFractionDigits: 3 })} ${currency}`;
const formatDate = (value?: string | null) => value ? new Date(`${value.substring(0, 10)}T00:00:00`).toLocaleDateString('fr-FR') : '—';
const formatDateTime = (value?: string | null) => value ? new Date(value).toLocaleString('fr-FR') : '—';
const errorMessage = (error: unknown, fallback: string) => error instanceof Error ? error.message : fallback;
const stepCompleted = (step?: BillingStep) => Boolean(step && (step.id || step.not_required));
const billingActivityCount = (item: BillingCase) => Object.keys(item.steps || {}).length + (item.payments || []).length;
const isAutomaticBillingCase = (item: BillingCase) => ['system', 'system-migration'].includes(String(item.created_by || ''));
const interventionProgressScore = (item: BillingCase) => {
  if (item.intervention_closed_at) return 4;
  if (item.intervention_started_at) return 3;
  const status = String(item.intervention_status || '').toLocaleLowerCase('fr');
  if (status.includes('cours') || status.includes('atelier')) return 2;
  return item.intervention_id ? 1 : 0;
};
const hasOpenTechnicalCycle = (item: BillingCase) => Boolean(
  !item.merged_into_case_id
  && item.case_state !== 'cancelled'
  && (!item.intervention_id || !item.intervention_closed_at),
);

const historyLabel = (event: HistoryItem) => {
  const after = event.after_data || {};
  const stepType = String(after.step_type || '');
  const stepLabels: Record<string, string> = {
    quote: 'Devis',
    purchase_order: 'Bon de commande',
    delivery_note: 'Bon de livraison',
    invoice: 'Facture',
  };
  if (event.action === 'CREATE_CASE') return 'Dossier créé';
  if (event.action === 'SYNC_MISSING_CASE') return 'Dossier créé automatiquement';
  if (event.action === 'LINK_REQUEST_AND_INTERVENTION') return 'Demande et intervention associées';
  if (event.action === 'RESOLVE_DUPLICATE') return 'Doublon résolu';
  if (event.action === 'MERGED_AS_DUPLICATE') return 'Dossier archivé comme doublon';
  if (event.action === 'CREATE_PAYMENT') return 'Paiement reçu';
  if (event.action === 'ASSESS_CONTRACT_COVERAGE') return 'Couverture contractuelle évaluée';
  if (event.action === 'UPDATE_PAYMENT') return 'Paiement corrigé';
  if (event.action === 'CREATE_STEP' || event.action === 'UPDATE_STEP') {
    const label = stepLabels[stepType] || 'Étape';
    if (Boolean(after.not_required)) return `${label} marqué non requis`;
    if (event.action === 'CREATE_STEP') {
      if (stepType === 'quote') return 'Devis créé';
      if (stepType === 'invoice') return 'Facture envoyée';
      return `${label} créé`;
    }
    return stepType === 'invoice' ? 'Facture corrigée' : `${label} corrigé`;
  }
  if (event.action === 'UPDATE_CASE') {
    if (after.case_state === 'blocked') return 'Dossier bloqué';
    if (event.before_data?.case_state === 'blocked' && after.case_state === 'active') return 'Dossier remis en activité';
    if (after.intervention_id && after.intervention_id !== event.before_data?.intervention_id) return 'Intervention associée';
    return 'Dossier modifié';
  }
  return event.action.replaceAll('_', ' ');
};

const emptyStepForm = () => ({
  effective_date: today(), due_date: '', reference: '', amount: '',
  not_required: false, note: '', change_reason: '',
});

const emptyPaymentForm = () => ({
  effective_date: today(), amount: '', reference: '', payment_method: '', note: '',
});

export default function FacturationPage() {
  useRoleGuard('facturation');
  const { user } = useAuth();
  const [cases, setCases] = useState<BillingCase[]>([]);
  const [clients, setClients] = useState<string[]>([]);
  const [equipmentOptions, setEquipmentOptions] = useState<EquipmentOption[]>([]);
  const [responsibles, setResponsibles] = useState<ResponsibleOption[]>([]);
  const [selectedCurrency, setSelectedCurrency] = useState('TND');
  const [interventionOptions, setInterventionOptions] = useState<InterventionOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');
  const [clientFilter, setClientFilter] = useState('');
  const [equipmentFilter, setEquipmentFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selected, setSelected] = useState<BillingCase | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [stepDialog, setStepDialog] = useState<{ item: BillingCase; type: StepType } | null>(null);
  const [stepForm, setStepForm] = useState(emptyStepForm());
  const [paymentCase, setPaymentCase] = useState<BillingCase | null>(null);
  const [paymentForm, setPaymentForm] = useState(emptyPaymentForm());
  const [newCaseOpen, setNewCaseOpen] = useState(false);
  const [newCaseForm, setNewCaseForm] = useState({ client: '', equipment: '', owner_username: '', currency: 'TND' });
  const [duplicateDialog, setDuplicateDialog] = useState<DuplicateResolutionState | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await billing.list();
      const typedResult = result as unknown as BillingCase[];
      setCases(typedResult);
      const requestedCaseId = typeof window !== 'undefined'
        ? Number(new URLSearchParams(window.location.search).get('case_id'))
        : 0;
      setSelected(previous => {
        const targetId = previous?.id || requestedCaseId;
        return targetId ? typedResult.find(item => item.id === targetId) || null : null;
      });
    } catch (err: unknown) {
      setError(errorMessage(err, 'Impossible de charger le suivi de facturation.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    clientsApi.list()
      .then(data => setClients([...new Set((data as Array<Record<string, unknown>>).map(item => String(item.nom || item.client || '')).map(value => value.trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fr'))))
      .catch(() => {});
    equipements.list()
      .then(data => setEquipmentOptions((data as Array<Record<string, unknown>>).map((item, index) => ({
        id: Number(item.id) || index,
        name: String(item.Nom || item.nom || item.name || '').trim(),
        client: String(item.Client || item.client || '').trim(),
      })).filter(item => item.name)))
      .catch(() => {});
    billing.responsibles()
      .then(data => setResponsibles((data as Array<Record<string, unknown>>).map(item => ({
        username: String(item.username || ''),
        display_name: String(item.display_name || item.nom_complet || item.username || ''),
        role: String(item.role || ''),
      })).filter(item => item.username)))
      .catch(() => {});
    settingsApi.public()
      .then(data => {
        const configured = String(data.devise || '').trim().toUpperCase();
        const fallback = typeof window !== 'undefined' ? String(window.localStorage.getItem('savia_devise') || '').trim().toUpperCase() : '';
        const currency = /^[A-Z]{3}$/.test(configured) ? configured : (/^[A-Z]{3}$/.test(fallback) ? fallback : 'TND');
        setSelectedCurrency(currency);
        setNewCaseForm(value => ({ ...value, currency }));
      })
      .catch(() => {
        const fallback = typeof window !== 'undefined' ? String(window.localStorage.getItem('savia_devise') || '').trim().toUpperCase() : '';
        if (/^[A-Z]{3}$/.test(fallback)) {
          setSelectedCurrency(fallback);
          setNewCaseForm(value => ({ ...value, currency: fallback }));
        }
      });
    interventions.list({ limit: 1000 })
      .then(data => setInterventionOptions((data as Array<Record<string, unknown>>).map(item => ({
        id: Number(item.id),
        client: String(item.client || ''),
        machine: String(item.machine || ''),
        statut: String(item.statut || ''),
        date: String(item.date || ''),
      })).filter(item => item.id)))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!responsibles.length) return;
    setNewCaseForm(value => {
      if (value.owner_username && responsibles.some(item => item.username === value.owner_username)) return value;
      const current = responsibles.find(item => item.username === user?.username);
      return { ...value, owner_username: current?.username || responsibles[0].username };
    });
  }, [responsibles, user?.username]);

  const openNewCase = () => {
    setNotice('');
    setNewCaseForm(value => ({ ...value, currency: selectedCurrency }));
    setNewCaseOpen(true);
  };

  const equipmentForSelectedClient = useMemo(
    () => equipmentOptions.filter(item => item.client.toLowerCase() === newCaseForm.client.toLowerCase()),
    [equipmentOptions, newCaseForm.client],
  );

  const selectClient = (client: string) => {
    const matching = equipmentOptions.filter(item => item.client.toLowerCase() === client.toLowerCase());
    setNewCaseForm(value => ({ ...value, client, equipment: matching.length === 1 ? matching[0].name : '' }));
  };

  const availableEquipmentFilters = useMemo(() => {
    const selectedClient = clientFilter.toLocaleLowerCase('fr');
    const equipmentNames = [
      ...equipmentOptions
        .filter(item => !selectedClient || item.client.toLocaleLowerCase('fr') === selectedClient)
        .map(item => item.name),
      ...cases
        .filter(item => !selectedClient || item.client.toLocaleLowerCase('fr') === selectedClient)
        .map(item => item.equipment),
    ].map(value => value.trim()).filter(Boolean);
    return [...new Set(equipmentNames)].sort((a, b) => a.localeCompare(b, 'fr'));
  }, [cases, clientFilter, equipmentOptions]);

  const filteredCases = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return cases.filter(item => {
      if (clientFilter && item.client !== clientFilter) return false;
      if (equipmentFilter && item.equipment !== equipmentFilter) return false;
      if (statusFilter === 'overdue' && !item.overdue) return false;
      if (statusFilter === 'to_invoice' && !['delivery_note_pending', 'invoice_pending'].includes(item.status)) return false;
      if (statusFilter === 'waiting_payment' && !['payment_pending', 'partial_payment'].includes(item.status)) return false;
      if (statusFilter && !['overdue', 'to_invoice', 'waiting_payment'].includes(statusFilter) && item.status !== statusFilter) return false;
      if (!needle) return true;
      const invoiceRef = item.steps.invoice?.reference || '';
      return `${item.id} ${item.client} ${item.equipment} ${item.technicien || ''} ${invoiceRef}`.toLowerCase().includes(needle);
    });
  }, [cases, clientFilter, equipmentFilter, search, statusFilter]);

  const kpis = useMemo(() => ({
    toInvoice: cases.filter(item => item.status === 'invoice_pending' || item.status === 'delivery_note_pending').length,
    waitingPayment: cases.filter(item => ['payment_pending', 'partial_payment'].includes(item.status)).length,
    overdue: cases.filter(item => item.overdue).length,
    receivable: cases.reduce((sum, item) => sum + item.remaining_amount, 0),
    paid: cases.filter(item => item.status === 'paid').length,
    covered: cases.filter(item => item.coverage_status === 'covered').length,
    review: cases.filter(item => item.coverage_status === 'review').length,
  }), [cases]);

  const openStep = (item: BillingCase, type: StepType) => {
    const existing = item.steps[type];
    setStepForm({
      effective_date: existing?.effective_date?.substring(0, 10) || today(),
      due_date: existing?.due_date?.substring(0, 10) || '',
      reference: existing?.reference || '',
      amount: existing?.amount === null || existing?.amount === undefined ? '' : String(existing.amount),
      not_required: Boolean(existing?.not_required),
      note: existing?.note || '',
      change_reason: '',
    });
    setStepDialog({ item, type });
    setError('');
  };

  const openPayment = (item: BillingCase) => {
    setPaymentForm({ ...emptyPaymentForm(), amount: item.remaining_amount > 0 ? String(item.remaining_amount) : '' });
    setPaymentCase(item);
    setError('');
  };

  const refreshCase = (updated: BillingCase) => {
    setCases(previous => previous.map(item => item.id === updated.id ? updated : item));
    setSelected(previous => previous?.id === updated.id ? updated : previous);
  };

  const saveStep = async () => {
    if (!stepDialog) return;
    setSaving(true);
    setError('');
    try {
      const updated = await billing.saveStep(stepDialog.item.id, stepDialog.type, {
        ...stepForm,
        effective_date: stepForm.not_required ? null : stepForm.effective_date,
        due_date: stepDialog.type === 'invoice' ? stepForm.due_date : null,
        amount: stepForm.not_required || stepForm.amount === '' ? null : Number(stepForm.amount),
      }) as unknown as BillingCase;
      refreshCase(updated);
      setStepDialog(null);
    } catch (err: unknown) {
      setError(errorMessage(err, "Impossible d'enregistrer cette étape."));
    } finally {
      setSaving(false);
    }
  };

  const savePayment = async () => {
    if (!paymentCase) return;
    setSaving(true);
    setError('');
    try {
      const updated = await billing.addPayment(paymentCase.id, {
        ...paymentForm,
        amount: Number(paymentForm.amount),
      }) as unknown as BillingCase;
      refreshCase(updated);
      setPaymentCase(null);
    } catch (err: unknown) {
      setError(errorMessage(err, "Impossible d'enregistrer le paiement."));
    } finally {
      setSaving(false);
    }
  };

  const createCase = async () => {
    setSaving(true);
    setError('');
    setNotice('');
    try {
      const created = await billing.create(newCaseForm) as unknown as BillingCase;
      setCases(previous => [created, ...previous.filter(item => item.id !== created.id)]);
      setNewCaseOpen(false);
      setNewCaseForm({ client: '', equipment: '', owner_username: responsibles.find(item => item.username === user?.username)?.username || responsibles[0]?.username || '', currency: selectedCurrency });
      setSelected(created);
      if (created.reused_existing_case) {
        setNotice(`Le dossier #${created.id} était déjà en cours pour cet équipement : aucun nouveau dossier n'a été créé.`);
      }
    } catch (err: unknown) {
      setError(errorMessage(err, 'Impossible de créer le dossier.'));
    } finally {
      setSaving(false);
    }
  };

  const toggleBlocked = async (item: BillingCase) => {
    const blocking = item.case_state !== 'blocked';
    const reason = window.prompt(blocking ? 'Motif du blocage :' : 'Motif de la remise en activité :');
    if (!reason?.trim()) return;
    try {
      const updated = await billing.updateCase(item.id, {
        case_state: blocking ? 'blocked' : 'active',
        block_reason: blocking ? reason.trim() : '',
        change_reason: reason.trim(),
      }) as unknown as BillingCase;
      refreshCase(updated);
    } catch (err: unknown) {
      setError(errorMessage(err, 'Modification impossible.'));
    }
  };

  const linkIntervention = async (item: BillingCase, interventionId: number) => {
    setError('');
    try {
      const updated = await billing.updateCase(item.id, {
        intervention_id: interventionId,
        change_reason: `Association à l'intervention #${interventionId}`,
      }) as unknown as BillingCase;
      refreshCase(updated);
    } catch (err: unknown) {
      setError(errorMessage(err, "Impossible d'associer l'intervention."));
    }
  };

  const openDuplicateResolution = (first: BillingCase, second: BillingCase) => {
    const firstActivity = billingActivityCount(first);
    const secondActivity = billingActivityCount(second);
    const keepCase = firstActivity === secondActivity
      ? (first.id < second.id ? first : second)
      : (firstActivity > secondActivity ? first : second);
    const interventionCase = interventionProgressScore(first) === interventionProgressScore(second)
      ? keepCase
      : (interventionProgressScore(first) > interventionProgressScore(second) ? first : second);
    setDuplicateDialog({
      first,
      second,
      keepCaseId: keepCase.id,
      interventionCaseId: interventionCase.intervention_id ? interventionCase.id : keepCase.id,
      reason: 'Deux dossiers ouverts pour la même intervention réelle',
    });
    setSelected(null);
    setError('');
  };

  const resolveDuplicate = async () => {
    if (!duplicateDialog) return;
    const discarded = duplicateDialog.keepCaseId === duplicateDialog.first.id
      ? duplicateDialog.second
      : duplicateDialog.first;
    if (billingActivityCount(discarded) > 0) {
      setError('Le dossier à archiver contient des documents ou paiements. Choisissez-le comme dossier à conserver.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const updated = await billing.resolveDuplicate({
        keep_case_id: duplicateDialog.keepCaseId,
        duplicate_case_id: discarded.id,
        intervention_case_id: duplicateDialog.interventionCaseId,
        reason: duplicateDialog.reason,
      }) as unknown as BillingCase;
      setCases(previous => previous
        .filter(item => item.id !== discarded.id)
        .map(item => item.id === updated.id ? updated : item));
      setSelected(updated);
      setNotice(`Le dossier #${discarded.id} a été archivé comme doublon du dossier #${updated.id}.`);
      setDuplicateDialog(null);
    } catch (err: unknown) {
      setError(errorMessage(err, 'Impossible de résoudre ce doublon.'));
    } finally {
      setSaving(false);
    }
  };

  const showHistory = async (item: BillingCase) => {
    setHistoryLoading(true);
    try {
      setHistory(await billing.history(item.id) as unknown as HistoryItem[]);
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const reassessCoverage = async (item: BillingCase) => {
    setSaving(true);
    setError('');
    try {
      const updated = await billing.reassessCoverage(item.id) as unknown as BillingCase;
      setCases(previous => previous.map(candidate => candidate.id === updated.id ? updated : candidate));
      setSelected(updated);
      setNotice('Couverture contractuelle recalculée.');
    } catch (err) {
      setError(errorMessage(err, 'Impossible de recalculer la couverture contractuelle.'));
    } finally {
      setSaving(false);
    }
  };

  const deleteCase = async (item: BillingCase) => {
    if (isAutomaticBillingCase(item)) return;
    if (!window.confirm(`Supprimer définitivement le dossier #${item.id} ? Cette action supprimera aussi ses étapes, paiements et son historique.`)) return;
    setSaving(true);
    setError('');
    try {
      const result = await billing.delete(item.id);
      setCases(previous => previous.filter(candidate => candidate.id !== item.id));
      setSelected(null);
      setHistory([]);
      if (result.replacement_case_id) {
        setNotice(`Le dossier #${item.id} a été supprimé. Le dossier automatique #${result.replacement_case_id} a été recréé pour l'intervention #${item.intervention_id}.`);
        await load();
      } else {
        setNotice(`Le dossier #${item.id} a été supprimé.`);
      }
    } catch (err: unknown) {
      setError(errorMessage(err, 'Impossible de supprimer le dossier.'));
    } finally {
      setSaving(false);
    }
  };

  const primaryAction = (item: BillingCase) => {
    if (!item.next_step) return null;
    if (item.next_step === 'intervention' || item.next_step === 'intervention_close') {
      if (!item.intervention_id) {
        return (
          <Link href={`/demandes?billing_case_id=${item.id}`} className="inline-flex items-center gap-1.5 rounded-lg bg-violet-500/10 px-3 py-2 text-xs font-bold text-violet-300 hover:bg-violet-500/20">
            Créer la demande <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        );
      }
      return (
        <Link href={`/sav?intervention_id=${item.intervention_id}`} className="inline-flex items-center gap-1.5 rounded-lg bg-violet-500/10 px-3 py-2 text-xs font-bold text-violet-300 hover:bg-violet-500/20">
          {NEXT_ACTION[item.next_step]} <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      );
    }
    if (item.next_step === 'payment') {
      return <button onClick={() => openPayment(item)} className="rounded-lg bg-green-500/10 px-3 py-2 text-xs font-bold text-green-300 hover:bg-green-500/20">{NEXT_ACTION.payment}</button>;
    }
    return <button onClick={() => openStep(item, item.next_step as StepType)} className="rounded-lg bg-savia-accent/10 px-3 py-2 text-xs font-bold text-savia-accent hover:bg-savia-accent/20">{NEXT_ACTION[item.next_step]}</button>;
  };

  if (loading) {
    return <div className="flex h-64 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-savia-accent" /></div>;
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-black gradient-text"><Receipt className="h-7 w-7" /> Suivi Facturation</h1>
          <p className="mt-1 text-sm text-savia-text-muted">Pilotage opérationnel du devis jusqu&apos;à l&apos;encaissement</p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} className="rounded-lg border border-savia-border p-2.5 text-savia-text-muted hover:text-savia-accent" title="Actualiser"><RefreshCw className="h-4 w-4" /></button>
          <button onClick={openNewCase} className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-savia-accent to-savia-accent-blue px-4 py-2.5 text-sm font-bold text-white"><Plus className="h-4 w-4" /> Nouveau dossier</button>
        </div>
      </div>

      {error && <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300"><AlertTriangle className="h-4 w-4 shrink-0" />{error}<button onClick={() => setError('')} className="ml-auto"><X className="h-4 w-4" /></button></div>}
      {notice && <div className="flex items-center gap-2 rounded-xl border border-blue-500/30 bg-blue-500/10 px-4 py-3 text-sm text-blue-200"><CheckCircle2 className="h-4 w-4 shrink-0" />{notice}<button onClick={() => setNotice('')} className="ml-auto"><X className="h-4 w-4" /></button></div>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-7">
        {[
          { label: 'À facturer', value: kpis.toInvoice, icon: Receipt, color: 'text-orange-300', filter: 'to_invoice' },
          { label: 'Paiement attendu', value: kpis.waitingPayment, icon: Clock3, color: 'text-teal-300', filter: 'waiting_payment' },
          { label: 'En retard', value: kpis.overdue, icon: AlertTriangle, color: 'text-red-300', filter: 'overdue' },
          { label: 'Reste à encaisser', value: money(kpis.receivable, cases[0]?.currency || 'TND'), icon: Banknote, color: 'text-yellow-300', filter: '' },
          { label: 'Dossiers payés', value: kpis.paid, icon: CheckCircle2, color: 'text-green-300', filter: 'paid' },
          { label: 'Couverts contrat', value: kpis.covered, icon: CheckCircle2, color: 'text-emerald-300', filter: 'covered_by_contract' },
          { label: 'À vérifier', value: kpis.review, icon: AlertTriangle, color: 'text-fuchsia-300', filter: 'coverage_review' },
        ].map(card => {
          const Icon = card.icon;
          return <KpiCard key={card.label} className={statusFilter === card.filter && card.filter ? 'ring-2 ring-savia-accent' : undefined}
            appearance="status-stripe" icon={<Icon className="h-5 w-5" />} value={String(card.value)} label={card.label}
            variant={card.label === 'En retard' || card.label === 'À vérifier' ? (Number(card.value) > 0 ? 'danger' : 'success') : card.label === 'Dossiers payés' || card.label === 'Couverts contrat' ? 'success' : card.label === 'Paiement attendu' || card.label === 'Reste à encaisser' ? 'warning' : 'default'}
            onClick={card.filter ? () => setStatusFilter(current => current === card.filter ? '' : card.filter) : undefined} />;
        })}
      </div>

      <div className="glass grid grid-cols-1 gap-3 rounded-xl p-3 xl:grid-cols-[minmax(260px,1fr)_minmax(180px,0.55fr)_minmax(180px,0.55fr)_minmax(210px,0.65fr)_auto]">
        <div className="relative min-w-0"><Search className="absolute left-3 top-2.5 h-4 w-4 text-savia-text-dim" /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Client, équipement, technicien, référence…" className={`${INPUT} pl-9`} /></div>
        <select value={clientFilter} onChange={event => { setClientFilter(event.target.value); setEquipmentFilter(''); }} className={`${INPUT} min-w-0`}><option value="">Tous les clients</option>{[...new Set([...clients, ...cases.map(item => item.client)])].filter(Boolean).sort().map(client => <option key={client}>{client}</option>)}</select>
        <select value={equipmentFilter} onChange={event => setEquipmentFilter(event.target.value)} disabled={availableEquipmentFilters.length === 0} className={`${INPUT} min-w-0 disabled:cursor-not-allowed disabled:opacity-50`}><option value="">Tous les équipements</option>{availableEquipmentFilters.map(equipment => <option key={equipment}>{equipment}</option>)}</select>
        <select value={statusFilter} onChange={event => setStatusFilter(event.target.value)} className={`${INPUT} min-w-0`}>
          <option value="">Tous les statuts</option>
          <option value="to_invoice">Toutes les actions avant facture</option>
          <option value="waiting_payment">Tous les paiements attendus</option>
          {[...new Map(cases.map(item => [item.status, item.status_label])).entries()].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          <option value="overdue">Paiement en retard</option>
        </select>
        {(search || clientFilter || equipmentFilter || statusFilter) && <button onClick={() => { setSearch(''); setClientFilter(''); setEquipmentFilter(''); setStatusFilter(''); }} className="text-xs font-semibold text-savia-accent">Réinitialiser</button>}
      </div>

      <div className="glass overflow-hidden rounded-xl">
        <div className="border-b border-savia-border px-4 py-3 text-sm font-semibold">{filteredCases.length} dossier{filteredCases.length > 1 ? 's' : ''}</div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1050px] text-sm">
            <thead className="bg-savia-surface-hover/70 text-left text-xs text-savia-text-muted">
              <tr><th className="px-3 py-3">Dossier</th><th className="px-3 py-3">Client / équipement</th><th className="px-3 py-3">Progression</th><th className="px-3 py-3">Statut</th><th className="px-3 py-3 text-right">Facture</th><th className="px-3 py-3 text-right">Reste</th><th className="px-3 py-3">Action suivante</th><th className="px-3 py-3"></th></tr>
            </thead>
            <tbody>
              {filteredCases.map((item, rowIndex) => (
                <tr key={`${item.id}-${rowIndex}`} className={`border-t border-savia-border/40 hover:bg-savia-surface-hover/40 ${item.overdue ? 'bg-red-500/5' : ''}`}>
                  <td className="px-3 py-3"><button onClick={() => setSelected(item)} className="font-mono font-bold text-savia-accent">#{item.id}</button><div className="mt-1 text-[11px] text-savia-text-dim">{item.intervention_id ? `Interv. #${item.intervention_id}` : 'Avant intervention'}</div></td>
                  <td className="px-3 py-3"><div className="font-semibold">{item.client}</div><div className="mt-0.5 text-xs text-savia-text-muted">{item.equipment || 'Équipement non renseigné'}</div></td>
                  <td className="px-3 py-3"><Progress item={item} /></td>
                  <td className="px-3 py-3"><span className={`inline-flex rounded-full border px-2 py-1 text-xs font-bold ${STATUS_STYLE[item.status] || STATUS_STYLE.quote_pending}`}>{item.status_label}</span>{item.coverage_status === 'partial' && <div className="mt-1 text-[11px] font-bold text-amber-300">Partiellement facturable</div>}{item.overdue && <div className="mt-1 text-xs font-bold text-red-300">{item.overdue_days} j de retard</div>}{!item.overdue && item.stage_age_days !== null && item.stage_age_days !== undefined && <div className="mt-1 text-[11px] text-savia-text-muted">Depuis {item.stage_age_days} jour{item.stage_age_days === 1 ? '' : 's'}</div>}{item.data_incomplete && <div className="mt-1 text-[11px] text-amber-300">Informations à confirmer</div>}</td>
                  <td className="px-3 py-3 text-right font-semibold">{item.invoice_amount ? money(item.invoice_amount, item.currency) : '—'}</td>
                  <td className={`px-3 py-3 text-right font-bold ${item.remaining_amount > 0 ? 'text-yellow-300' : 'text-green-300'}`}>{item.invoice_amount ? money(item.remaining_amount, item.currency) : '—'}</td>
                  <td className="px-3 py-3">{primaryAction(item) || <span className="text-xs font-semibold text-green-300">Dossier terminé</span>}</td>
                  <td className="px-3 py-3 text-right"><button onClick={() => setSelected(item)} className="rounded-lg border border-savia-border px-2.5 py-1.5 text-xs font-semibold text-savia-text-muted hover:text-savia-accent">Détails</button></td>
                </tr>
              ))}
              {filteredCases.length === 0 && <tr><td colSpan={8} className="py-12 text-center text-savia-text-muted"><Receipt className="mx-auto mb-2 h-8 w-8 opacity-30" />Aucun dossier ne correspond aux filtres.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <Modal isOpen={!!selected} onClose={() => { setSelected(null); setHistory([]); }} title={selected ? `Dossier de facturation #${selected.id}` : ''} size="xl">
        {selected && <CaseDetail item={selected} interventionOptions={interventionOptions} duplicateCases={cases.filter(candidate => candidate.id !== selected.id && hasOpenTechnicalCycle(selected) && hasOpenTechnicalCycle(candidate) && candidate.client.trim().toLocaleLowerCase('fr') === selected.client.trim().toLocaleLowerCase('fr') && candidate.equipment.trim().toLocaleLowerCase('fr') === selected.equipment.trim().toLocaleLowerCase('fr'))} canResolveDuplicates={user?.role === 'Admin' || user?.role === 'Manager'} canDeleteCase={(user?.role === 'Admin' || user?.role === 'Manager') && !isAutomaticBillingCase(selected)} history={history} historyLoading={historyLoading} onStep={openStep} onPayment={openPayment} onHistory={showHistory} onToggleBlocked={toggleBlocked} onLinkIntervention={linkIntervention} onResolveDuplicate={openDuplicateResolution} onReassess={reassessCoverage} onDeleteCase={deleteCase} />}
      </Modal>

      <Modal isOpen={!!stepDialog} onClose={() => setStepDialog(null)} title={stepDialog ? STEP_META[stepDialog.type].label : ''} size="md">
        {stepDialog && <div className="space-y-4">
          {['purchase_order', 'delivery_note'].includes(stepDialog.type) && <label className="flex items-start gap-2 rounded-lg border border-savia-border bg-savia-surface-hover p-3 text-sm"><input type="checkbox" checked={stepForm.not_required} onChange={event => setStepForm(value => ({ ...value, not_required: event.target.checked, note: event.target.checked && !value.note.trim() ? 'Non applicable pour ce dossier' : value.note }))} /><span><span className="font-semibold">Étape non requise pour ce dossier</span><span className="mt-0.5 block text-xs text-savia-text-muted">Un motif est enregistré automatiquement et reste modifiable pour assurer la traçabilité.</span></span></label>}
          {!stepForm.not_required && <>
            <div><label className={LABEL}>Date effective *</label><input type="date" max={today()} className={INPUT} value={stepForm.effective_date} onChange={event => setStepForm(value => ({ ...value, effective_date: event.target.value }))} /></div>
            <div><label className={LABEL}>Référence du document</label><input className={INPUT} value={stepForm.reference} onChange={event => setStepForm(value => ({ ...value, reference: event.target.value }))} placeholder="Ex. DEV-2026-0042" /></div>
            <div><label className={LABEL}>Montant {stepDialog.type === 'delivery_note' ? '(optionnel)' : '*'}</label><input type="number" min="0" step="0.001" className={INPUT} value={stepForm.amount} onChange={event => setStepForm(value => ({ ...value, amount: event.target.value }))} /></div>
            {stepDialog.type === 'invoice' && <div><label className={LABEL}>Date d&apos;échéance *</label><input type="date" min={stepForm.effective_date} className={INPUT} value={stepForm.due_date} onChange={event => setStepForm(value => ({ ...value, due_date: event.target.value }))} /></div>}
          </>}
          <div><label className={LABEL}>{stepForm.not_required ? 'Motif *' : 'Note'}</label><textarea className={`${INPUT} min-h-20 resize-none`} value={stepForm.note} onChange={event => setStepForm(value => ({ ...value, note: event.target.value }))} /></div>
          {stepDialog.item.steps[stepDialog.type] && stepDialog.item.steps[stepDialog.type]?.created_by !== 'system-migration' && <div><label className={LABEL}>Motif de correction *</label><input className={INPUT} value={stepForm.change_reason} onChange={event => setStepForm(value => ({ ...value, change_reason: event.target.value }))} placeholder="Pourquoi cette information change-t-elle ?" /></div>}
          <div className="flex justify-end gap-2"><button onClick={() => setStepDialog(null)} className="rounded-lg border border-savia-border px-4 py-2 text-sm">Annuler</button><button disabled={saving} onClick={saveStep} className="flex items-center gap-2 rounded-lg bg-savia-accent px-4 py-2 text-sm font-bold text-savia-bg disabled:opacity-50">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Valider l&apos;étape</button></div>
        </div>}
      </Modal>

      <Modal isOpen={!!paymentCase} onClose={() => setPaymentCase(null)} title="Enregistrer un paiement" size="md">
        {paymentCase && <div className="space-y-4">
          <div className="rounded-lg border border-savia-border bg-savia-surface-hover p-3 text-sm"><span className="text-savia-text-muted">Reste à encaisser :</span> <strong className="text-yellow-300">{money(paymentCase.remaining_amount, paymentCase.currency)}</strong></div>
          <div><label className={LABEL}>Date de réception *</label><input type="date" max={today()} className={INPUT} value={paymentForm.effective_date} onChange={event => setPaymentForm(value => ({ ...value, effective_date: event.target.value }))} /></div>
          <div><label className={LABEL}>Montant reçu *</label><input type="number" min="0.001" max={paymentCase.remaining_amount} step="0.001" className={INPUT} value={paymentForm.amount} onChange={event => setPaymentForm(value => ({ ...value, amount: event.target.value }))} /></div>
          <div className="grid grid-cols-2 gap-3"><div><label className={LABEL}>Référence</label><input className={INPUT} value={paymentForm.reference} onChange={event => setPaymentForm(value => ({ ...value, reference: event.target.value }))} /></div><div><label className={LABEL}>Mode de paiement</label><select className={INPUT} value={paymentForm.payment_method} onChange={event => setPaymentForm(value => ({ ...value, payment_method: event.target.value }))}><option value="">Non précisé</option><option>Virement</option><option>Chèque</option><option>Espèces</option><option>Carte</option></select></div></div>
          <div><label className={LABEL}>Note</label><textarea className={`${INPUT} min-h-20 resize-none`} value={paymentForm.note} onChange={event => setPaymentForm(value => ({ ...value, note: event.target.value }))} /></div>
          <div className="flex justify-end gap-2"><button onClick={() => setPaymentCase(null)} className="rounded-lg border border-savia-border px-4 py-2 text-sm">Annuler</button><button disabled={saving} onClick={savePayment} className="flex items-center gap-2 rounded-lg bg-green-500 px-4 py-2 text-sm font-bold text-white disabled:opacity-50">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Banknote className="h-4 w-4" />} Enregistrer</button></div>
        </div>}
      </Modal>

      <Modal isOpen={newCaseOpen} onClose={() => setNewCaseOpen(false)} title="Nouveau dossier de facturation" size="md">
        <div className="space-y-4">
          <p className="text-sm text-savia-text-muted">Utilisez ce formulaire lorsqu&apos;un devis existe avant la création de l&apos;intervention SAV.</p>
          <div><label className={LABEL}>Client *</label><select className={INPUT} value={newCaseForm.client} onChange={event => selectClient(event.target.value)}><option value="">Sélectionner un client</option>{clients.map(client => <option key={client} value={client}>{client}</option>)}</select>{!clients.length && <p className="mt-1 text-xs text-amber-300">Aucun client disponible depuis l&apos;API.</p>}</div>
          <div><label className={LABEL}>Équipement</label><select className={INPUT} value={newCaseForm.equipment} disabled={!newCaseForm.client} onChange={event => setNewCaseForm(value => ({ ...value, equipment: event.target.value }))}><option value="">{newCaseForm.client ? (equipmentForSelectedClient.length ? 'Sélectionner un équipement' : 'Aucun équipement pour ce client') : 'Sélectionnez d’abord un client'}</option>{equipmentForSelectedClient.map(item => <option key={`${item.id}-${item.name}`} value={item.name}>{item.name}</option>)}</select></div>
          <div className="grid grid-cols-2 gap-3"><div><label className={LABEL}>Responsable</label><select className={INPUT} value={newCaseForm.owner_username} onChange={event => setNewCaseForm(value => ({ ...value, owner_username: event.target.value }))}><option value="">Non assigné</option>{responsibles.map(item => <option key={item.username} value={item.username}>{item.display_name} · {item.role}</option>)}</select></div><div><label className={LABEL}>Devise</label><input readOnly className={`${INPUT} cursor-not-allowed opacity-75`} value={newCaseForm.currency} title="Devise définie dans les paramètres" /><p className="mt-1 text-[11px] text-savia-text-dim">Synchronisée avec les paramètres</p></div></div>
          <div className="flex justify-end gap-2"><button onClick={() => setNewCaseOpen(false)} className="rounded-lg border border-savia-border px-4 py-2 text-sm">Annuler</button><button disabled={saving || !newCaseForm.client.trim()} onClick={createCase} className="flex items-center gap-2 rounded-lg bg-savia-accent px-4 py-2 text-sm font-bold text-savia-bg disabled:opacity-50">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Créer</button></div>
        </div>
      </Modal>

      {duplicateDialog && <DuplicateResolutionDialog value={duplicateDialog} saving={saving} onChange={setDuplicateDialog} onClose={() => setDuplicateDialog(null)} onConfirm={resolveDuplicate} />}
    </div>
  );
}

function DuplicateResolutionDialog({ value, saving, onChange, onClose, onConfirm }: {
  value: DuplicateResolutionState;
  saving: boolean;
  onChange: (value: DuplicateResolutionState) => void;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const choices = [value.first, value.second];
  const keepCase = choices.find(item => item.id === value.keepCaseId) || value.first;
  const discardedCase = choices.find(item => item.id !== keepCase.id) || value.second;
  const discardedActivity = billingActivityCount(discardedCase);
  const interventionChoices = choices.filter(item => item.intervention_id);
  const retainedInterventionCase = interventionChoices.find(item => item.id === value.interventionCaseId);
  const cancelledInterventionCase = interventionChoices.find(item => item.id !== retainedInterventionCase?.id);
  const cancelledHasVisibleWork = Boolean(cancelledInterventionCase && (
    cancelledInterventionCase.intervention_started_at
    || cancelledInterventionCase.intervention_closed_at
    || Number(cancelledInterventionCase.intervention_duration_minutes || 0) > 0
    || ['cours', 'atelier', 'clot', 'clôt', 'termin'].some(token => String(cancelledInterventionCase.intervention_status || '').toLocaleLowerCase('fr').includes(token))
  ));
  const blocked = discardedActivity > 0 || cancelledHasVisibleWork;

  return <Modal isOpen onClose={onClose} title="Résoudre le doublon" size="lg">
    <div className="space-y-5">
      <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-3 text-sm text-savia-text-muted">Cette opération conserve un dossier visible, archive l&apos;autre et annule uniquement l&apos;intervention accidentelle sans travail technicien.</div>

      <section><h3 className="mb-2 text-sm font-bold">1. Dossier de facturation à conserver</h3><div className="grid gap-3 md:grid-cols-2">{choices.map(candidate => {
        const activity = billingActivityCount(candidate);
        return <label key={candidate.id} className={`cursor-pointer rounded-xl border p-3 ${candidate.id === keepCase.id ? 'border-savia-accent bg-savia-accent/10' : 'border-savia-border'}`}><div className="flex items-start gap-2"><input type="radio" name="keep-case" checked={candidate.id === keepCase.id} onChange={() => onChange({ ...value, keepCaseId: candidate.id })} /><div><div className="font-bold">Dossier #{candidate.id}</div><div className="mt-1 text-xs text-savia-text-muted">Intervention #{candidate.intervention_id || '—'} · {activity} document/paiement</div><div className="mt-1 text-xs">{candidate.status_label}</div></div></div></label>;
      })}</div>{discardedActivity > 0 && <p className="mt-2 text-xs font-semibold text-red-300">Le dossier #{discardedCase.id} contient {discardedActivity} élément(s). Choisissez-le comme dossier à conserver.</p>}</section>

      {interventionChoices.length > 0 && <section><h3 className="mb-2 text-sm font-bold">2. Intervention réelle à conserver</h3><div className="grid gap-3 md:grid-cols-2">{interventionChoices.map(candidate => <label key={candidate.id} className={`cursor-pointer rounded-xl border p-3 ${candidate.id === value.interventionCaseId ? 'border-green-500/50 bg-green-500/10' : 'border-savia-border'}`}><div className="flex items-start gap-2"><input type="radio" name="keep-intervention" checked={candidate.id === value.interventionCaseId} onChange={() => onChange({ ...value, interventionCaseId: candidate.id })} /><div><div className="font-bold">Intervention #{candidate.intervention_id}</div><div className="mt-1 text-xs text-savia-text-muted">Dossier #{candidate.id} · {candidate.intervention_status || 'statut inconnu'}</div><div className="mt-1 text-xs">Début : {formatDateTime(candidate.intervention_started_at)}</div></div></div></label>)}</div>{cancelledHasVisibleWork && <p className="mt-2 text-xs font-semibold text-red-300">L&apos;intervention #{cancelledInterventionCase?.intervention_id} contient déjà du travail. Sélectionnez-la comme intervention à conserver.</p>}</section>}

      <div><label className={LABEL}>Motif de résolution</label><input className={INPUT} value={value.reason} onChange={event => onChange({ ...value, reason: event.target.value })} /></div>

      <div className="rounded-xl border border-savia-border bg-savia-surface-hover/50 p-3 text-xs text-savia-text-muted"><strong className="text-savia-text">Résultat :</strong> le dossier #{keepCase.id} restera visible. Le dossier #{discardedCase.id} sera archivé avec son historique. {cancelledInterventionCase?.intervention_id ? `L'intervention #${cancelledInterventionCase.intervention_id} sera annulée.` : ''}</div>
      <div className="flex justify-end gap-2"><button type="button" onClick={onClose} className="rounded-lg border border-savia-border px-4 py-2 text-sm">Annuler</button><button type="button" disabled={saving || blocked || !value.reason.trim()} onClick={onConfirm} className="flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-bold text-slate-950 disabled:opacity-40">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Confirmer la résolution</button></div>
    </div>
  </Modal>;
}

function Progress({ item }: { item: BillingCase }) {
  const nodes = [
    { key: 'quote', done: stepCompleted(item.steps.quote), title: 'Devis' },
    { key: 'purchase_order', done: stepCompleted(item.steps.purchase_order), title: 'BC' },
    { key: 'intervention', done: Boolean(item.intervention_closed_at), active: Boolean(item.intervention_started_at), title: 'Interv.' },
    // Une intervention non créée ou non clôturée ne permet pas encore de
    // déterminer si un BL sera nécessaire. Le BL n'est donc validé
    // automatiquement sans pièces qu'après la clôture.
    { key: 'delivery_note', done: Boolean(item.intervention_closed_at) && (!item.has_parts || stepCompleted(item.steps.delivery_note)), title: 'BL' },
    { key: 'invoice', done: stepCompleted(item.steps.invoice), title: 'Facture' },
    { key: 'payment', done: item.status === 'paid', active: item.paid_amount > 0, title: 'Paiement' },
  ];
  return <div className="flex min-w-[250px] items-start">{nodes.map((node, index) => <div key={node.key} className="flex flex-1 items-start"><div className="flex flex-col items-center"><div title={node.title} className={`flex h-6 w-6 items-center justify-center rounded-full border ${node.done ? 'border-green-400 bg-green-500/15 text-green-300' : node.active ? 'border-savia-accent bg-savia-accent/15 text-savia-accent' : 'border-savia-border text-savia-text-dim'}`}>{node.done ? <Check className="h-3.5 w-3.5" /> : <Circle className="h-2.5 w-2.5" />}</div><span className="mt-1 text-[9px] text-savia-text-dim">{node.title}</span></div>{index < nodes.length - 1 && <div className={`mt-3 h-px flex-1 ${node.done ? 'bg-green-500/50' : 'bg-savia-border'}`} />}</div>)}</div>;
}

function DocumentStepRow({ item, type, onStep }: { item: BillingCase; type: StepType; onStep: (item: BillingCase, type: StepType) => void }) {
  const meta = STEP_META[type];
  const step = item.steps[type];
  const Icon = meta.icon;
  const complete = stepCompleted(step);
  return <button onClick={() => onStep(item, type)} className="flex w-full items-center gap-3 rounded-xl border border-savia-border p-3 text-left hover:border-savia-accent/50 hover:bg-savia-surface-hover"><div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${complete ? 'bg-green-500/15 text-green-300' : 'bg-savia-surface-hover text-savia-text-dim'}`}>{complete ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}</div><div className="min-w-0 flex-1"><div className="font-semibold">{meta.label}</div><div className="mt-0.5 text-xs text-savia-text-muted">{complete ? (step?.not_required ? `Non requis · ${step.note}` : `${formatDate(step?.effective_date)} · ${step?.reference || 'sans référence'}${step?.amount !== null && step?.amount !== undefined ? ` · ${money(step.amount, item.currency)}` : ''}`) : 'À renseigner'}</div></div><ArrowRight className="h-4 w-4 text-savia-text-dim" /></button>;
}

const durationLabel = (minutes?: number) => {
  const total = Number(minutes || 0);
  if (!total) return '—';
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return [hours ? `${hours} h` : '', rest ? `${rest} min` : ''].filter(Boolean).join(' ');
};

function InterventionPreview({ item }: { item: BillingCase }) {
  const technicians = item.intervention_technicians || [];
  const diagnosticBlocks = [
    { label: 'Description', value: item.intervention_description, style: 'border-savia-border bg-savia-surface-hover/40' },
    { label: 'Problème signalé', value: item.intervention_problem, style: 'border-red-500/15 bg-red-500/5' },
    { label: 'Cause diagnostiquée', value: item.intervention_cause, style: 'border-orange-500/15 bg-orange-500/5' },
    { label: 'Solution apportée', value: item.intervention_solution, style: 'border-green-500/15 bg-green-500/5' },
  ].filter(block => Boolean(block.value));

  return <div className="mt-4 space-y-4 border-t border-savia-border/70 pt-4">
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
      {[
        ['Statut', item.intervention_status || '—'],
        ['Date', formatDate(item.intervention_date)],
        ['Type', item.intervention_type || '—'],
        ['Priorité', item.intervention_priority || '—'],
        ['Durée', durationLabel(item.intervention_duration_minutes)],
        ['Déplacement', durationLabel(item.intervention_travel_minutes)],
        ['Début déclaré', item.intervention_start_time || '—'],
        ['Fin déclarée', item.intervention_end_time || '—'],
      ].map(([label, value]) => <div key={label} className="rounded-lg bg-savia-surface-hover/60 p-2.5"><div className="text-[11px] text-savia-text-dim">{label}</div><div className="mt-1 text-sm font-semibold">{value}</div></div>)}
    </div>

    <div className="rounded-lg border border-savia-border p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-savia-text-muted"><Users className="h-3.5 w-3.5" /> Techniciens</div>
      {technicians.length > 0 ? <div className="space-y-2">{technicians.map((technician, index) => <div key={`${technician.name}-${index}`} className="flex flex-wrap items-center justify-between gap-2 text-sm"><span className="font-semibold">{technician.name}</span><span className="text-xs text-savia-text-muted">{technician.status || '—'} · travail {durationLabel(technician.duration_minutes)} · déplacement {durationLabel(technician.travel_minutes)}</span></div>)}</div> : <div className="text-sm font-semibold">{item.technicien || 'Non assigné'}</div>}
    </div>

    {diagnosticBlocks.length > 0 && <div><div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-savia-text-muted"><FileText className="h-3.5 w-3.5" /> Diagnostic et travaux</div><div className="grid gap-2 md:grid-cols-2">{diagnosticBlocks.map(block => <div key={block.label} className={`rounded-lg border p-3 ${block.style}`}><div className="text-[11px] font-semibold text-savia-text-muted">{block.label}</div><p className="mt-1 whitespace-pre-wrap text-sm">{block.value}</p></div>)}</div></div>}

    {(item.intervention_error_code || item.intervention_error_type) && <div className="rounded-lg border border-savia-border p-3 text-sm"><span className="text-savia-text-muted">Erreur : </span><strong className="font-mono text-savia-accent">{item.intervention_error_code || '—'}</strong>{item.intervention_error_type && <span className="ml-2 text-savia-text-muted">({item.intervention_error_type})</span>}</div>}
    {item.pieces_utilisees && <div className="rounded-lg border border-blue-500/15 bg-blue-500/5 p-3"><div className="text-[11px] font-semibold text-blue-300">Pièces utilisées</div><p className="mt-1 whitespace-pre-wrap text-sm">{item.pieces_utilisees}</p></div>}
    {item.intervention_notes && <div className="rounded-lg border border-savia-border p-3"><div className="text-[11px] font-semibold text-savia-text-muted">Notes</div><p className="mt-1 whitespace-pre-wrap text-sm">{item.intervention_notes}</p></div>}

  </div>;
}

function CaseDetail({ item, interventionOptions, duplicateCases, canResolveDuplicates, canDeleteCase, history, historyLoading, onStep, onPayment, onHistory, onToggleBlocked, onLinkIntervention, onResolveDuplicate, onReassess, onDeleteCase }: {
  item: BillingCase;
  interventionOptions: InterventionOption[];
  duplicateCases: BillingCase[];
  canResolveDuplicates: boolean;
  canDeleteCase: boolean;
  history: HistoryItem[];
  historyLoading: boolean;
  onStep: (item: BillingCase, type: StepType) => void;
  onPayment: (item: BillingCase) => void;
  onHistory: (item: BillingCase) => void;
  onToggleBlocked: (item: BillingCase) => void;
  onLinkIntervention: (item: BillingCase, interventionId: number) => void;
  onResolveDuplicate: (first: BillingCase, second: BillingCase) => void;
  onReassess: (item: BillingCase) => void;
  onDeleteCase: (item: BillingCase) => void;
}) {
  const [interventionPreviewOpen, setInterventionPreviewOpen] = useState(false);
  const matchingInterventions = interventionOptions.filter(option =>
    option.client.toLowerCase() === item.client.toLowerCase()
    && (!item.equipment || option.machine.toLowerCase() === item.equipment.toLowerCase())
  );
  const assignedTechnicians = [...new Set(
    (item.intervention_technicians || [])
      .map(technician => technician.name.trim())
      .filter(Boolean),
  )];
  const assignedTechnicianLabel = assignedTechnicians.join(', ') || item.technicien || 'non assigné';
  const coverageLocked = item.coverage_status === 'covered' || item.coverage_status === 'review';
  return <div className="max-h-[78vh] space-y-5 overflow-y-auto pr-1">
    {item.reused_existing_case && <div className="flex items-start gap-2 rounded-xl border border-blue-500/30 bg-blue-500/10 p-3 text-sm text-blue-200"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /><span>Ce dossier était déjà en cours pour cet équipement. Il a été ouvert à la place de créer un doublon.</span></div>}
    {canResolveDuplicates && duplicateCases.map(duplicate => <div key={duplicate.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3"><div><div className="text-sm font-bold text-amber-200">Doublon potentiel avec le dossier #{duplicate.id}</div><p className="mt-1 text-xs text-savia-text-muted">Même client et même équipement avec un cycle technique encore ouvert.</p></div><button type="button" onClick={() => onResolveDuplicate(item, duplicate)} className="rounded-lg bg-amber-500 px-3 py-2 text-xs font-bold text-slate-950 hover:bg-amber-400">Résoudre le doublon</button></div>)}
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-savia-border bg-savia-surface-hover/50 p-4"><div><div className="flex items-center gap-2 font-bold"><Building2 className="h-4 w-4 text-savia-accent" />{item.client}</div><div className="mt-1 text-sm text-savia-text-muted">{item.equipment || 'Équipement non renseigné'} {item.intervention_id && `· Intervention #${item.intervention_id}`}</div><div className="mt-1 text-xs text-savia-text-dim">Technicien assigné : {assignedTechnicianLabel}</div>{item.owner_username && <div className="mt-1 text-xs text-savia-text-dim">Responsable facturation : {item.owner_username}</div>}</div><div className="text-right"><span className={`inline-flex rounded-full border px-2 py-1 text-xs font-bold ${STATUS_STYLE[item.status]}`}>{item.status_label}</span>{item.block_reason && <div className="mt-2 max-w-xs text-xs text-red-300">{item.block_reason}</div>}</div></div>

    {item.intervention_closed_at && <section className={`rounded-xl border p-4 ${item.coverage_status === 'covered' ? 'border-emerald-500/30 bg-emerald-500/5' : item.coverage_status === 'review' ? 'border-fuchsia-500/30 bg-fuchsia-500/5' : 'border-amber-500/30 bg-amber-500/5'}`}><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2 font-bold">{item.coverage_status === 'review' ? <AlertTriangle className="h-4 w-4 text-fuchsia-300" /> : <CheckCircle2 className="h-4 w-4 text-emerald-300" />}{item.coverage_status_label}</div><div className="mt-1 text-xs text-savia-text-muted">{item.contract_id ? `Contrat #${item.contract_id}${item.contract_type ? ` · ${item.contract_type}` : ''}` : 'Aucun contrat applicable'}</div><p className="mt-2 text-sm">{item.coverage_reason || 'Décision contractuelle non renseignée.'}</p></div><button type="button" onClick={() => onReassess(item)} className="rounded-lg border border-savia-border px-3 py-2 text-xs font-bold text-savia-accent hover:bg-savia-surface-hover"><RefreshCw className="mr-1 inline h-3.5 w-3.5" /> Recalculer</button></div><div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">{[['Coût de revient MO', item.labor_amount || 0], ['Coût de revient pièces', item.parts_amount || 0], ['Coût MO hors couverture', item.uncovered_labor_cost || 0], ['Coût pièces hors couverture', item.uncovered_parts_cost || 0]].map(([label, value]) => <div key={String(label)} className="rounded-lg bg-savia-surface-hover/60 p-2.5"><div className="text-[11px] text-savia-text-muted">{label}</div><div className="mt-1 font-black">{money(Number(value), item.currency)}</div></div>)}</div><div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-savia-border/60 pt-3"><span className="text-sm font-semibold">Coût de revient hors couverture : {money(item.uncovered_total_cost || 0, item.currency)}</span><strong className="text-sm text-savia-accent">Prix client à renseigner dans le devis ou la facture</strong></div></section>}

    <div className="grid grid-cols-3 gap-3"><div className="rounded-xl border border-savia-border p-3"><div className="text-xs text-savia-text-muted">Montant facturé</div><div className="mt-1 font-black">{money(item.invoice_amount, item.currency)}</div></div><div className="rounded-xl border border-savia-border p-3"><div className="text-xs text-savia-text-muted">Reçu</div><div className="mt-1 font-black text-green-300">{money(item.paid_amount, item.currency)}</div></div><div className="rounded-xl border border-savia-border p-3"><div className="text-xs text-savia-text-muted">Reste</div><div className="mt-1 font-black text-yellow-300">{money(item.remaining_amount, item.currency)}</div></div></div>

    {!item.intervention_id && <div className="rounded-xl border border-blue-500/25 bg-blue-500/5 p-3"><div className="flex flex-wrap items-center justify-between gap-3"><div><div className="text-sm font-bold text-blue-200">Intervention à organiser</div><p className="mt-1 text-xs text-savia-text-muted">La demande sera associée à ce dossier et conservera le devis et le bon de commande déjà renseignés.</p></div><Link href={`/demandes?billing_case_id=${item.id}`} className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-3 py-2 text-xs font-bold text-white hover:bg-blue-400"><Send className="h-3.5 w-3.5" /> Créer la demande d&apos;intervention</Link></div><details className="mt-3 border-t border-blue-500/15 pt-3"><summary className="cursor-pointer text-xs font-semibold text-savia-text-muted">Correction : associer une intervention existante</summary><div className="mt-2"><select defaultValue="" onChange={event => { const id = Number(event.target.value); if (id) onLinkIntervention(item, id); }} className={INPUT}><option value="">Sélectionner une intervention compatible…</option>{matchingInterventions.map(option => <option key={option.id} value={option.id}>#{option.id} · {formatDate(option.date)} · {option.statut}</option>)}</select>{matchingInterventions.length === 0 && <p className="mt-2 text-xs text-savia-text-muted">Aucune intervention avec le même client et le même équipement.</p>}</div></details></div>}

    <section><h3 className="mb-3 flex items-center gap-2 text-sm font-bold"><Calendar className="h-4 w-4 text-savia-accent" /> Chronologie du dossier</h3><div className="space-y-2">
      {!coverageLocked && <DocumentStepRow item={item} type="quote" onStep={onStep} />}
      {!coverageLocked && <DocumentStepRow item={item} type="purchase_order" onStep={onStep} />}
      <div className={`rounded-xl border p-3 ${item.intervention_closed_at && ['delivery_note_pending', 'invoice_pending'].includes(item.status) ? 'border-orange-500/30 bg-orange-500/5' : 'border-savia-border'}`}><div className="flex items-center gap-3"><div className={`flex h-9 w-9 items-center justify-center rounded-full ${item.intervention_closed_at ? 'bg-green-500/15 text-green-300' : 'bg-violet-500/15 text-violet-300'}`}><Wrench className="h-4 w-4" /></div><div className="flex-1"><div className="font-semibold">Intervention SAV</div><div className="text-xs text-savia-text-muted">Début : {formatDateTime(item.intervention_started_at)} · Clôture : {formatDateTime(item.intervention_closed_at)}</div></div>{item.intervention_id && <button type="button" onClick={() => setInterventionPreviewOpen(value => !value)} className="inline-flex items-center gap-1.5 rounded-lg bg-teal-500/10 px-3 py-2 text-xs font-bold text-teal-300 hover:bg-teal-500/20"><Eye className="h-3.5 w-3.5" /> {interventionPreviewOpen ? 'Masquer' : 'Aperçu'}</button>}</div>{item.intervention_closed_at && ['delivery_note_pending', 'invoice_pending'].includes(item.status) && <p className="mt-2 text-xs font-semibold text-orange-300">Intervention clôturée : vérifiez son compte rendu avant de renseigner l&apos;envoi de la facture.</p>}{interventionPreviewOpen && <InterventionPreview item={item} />}</div>
      {!coverageLocked && item.has_parts && <DocumentStepRow item={item} type="delivery_note" onStep={onStep} />}
      {!coverageLocked && <DocumentStepRow item={item} type="invoice" onStep={onStep} />}
      {coverageLocked && <div className="rounded-lg border border-dashed border-savia-border p-3 text-center text-sm text-savia-text-muted">{item.coverage_status === 'covered' ? 'Aucune facture d’intervention n’est requise.' : 'La facturation est suspendue jusqu’à validation de la couverture.'}</div>}
    </div></section>

    <section><div className="mb-3 flex items-center justify-between"><h3 className="flex items-center gap-2 text-sm font-bold"><WalletCards className="h-4 w-4 text-green-300" /> Paiements reçus</h3>{item.remaining_amount > 0 && item.steps.invoice && <button onClick={() => onPayment(item)} className="rounded-lg bg-green-500/10 px-3 py-1.5 text-xs font-bold text-green-300"><Plus className="mr-1 inline h-3.5 w-3.5" /> Ajouter</button>}</div>{item.payments.length ? <div className="space-y-2">{item.payments.map(payment => <div key={payment.id} className="flex items-center justify-between rounded-lg border border-savia-border p-3"><div><div className="font-semibold text-green-300">{money(payment.amount, item.currency)}</div><div className="text-xs text-savia-text-muted">{formatDate(payment.effective_date)} · {payment.payment_method || 'mode non précisé'} · {payment.reference || 'sans référence'}</div></div><div className="text-xs text-savia-text-dim">par {payment.created_by}</div></div>)}</div> : <div className="rounded-lg border border-dashed border-savia-border p-4 text-center text-sm text-savia-text-muted">Aucun paiement enregistré</div>}</section>

    <section><h3 className="mb-3 flex items-center gap-2 text-sm font-bold"><Clock3 className="h-4 w-4 text-savia-accent" /> Délais mesurés</h3><div className="grid grid-cols-2 gap-2 md:grid-cols-3">{[['quote_to_order', 'Devis → BC'], ['order_to_start', 'BC → début'], ['start_to_close', 'Début → clôture'], ['close_to_invoice', 'Clôture → facture'], ['invoice_to_last_payment', 'Facture → paiement'], ['quote_to_last_payment', 'Cycle total']].map(([key, label]) => <div key={key} className="rounded-lg bg-savia-surface-hover p-2.5"><div className="text-[11px] text-savia-text-muted">{label}</div><div className="mt-1 font-bold">{item.lead_times[key] === null ? '—' : `${item.lead_times[key]} jour${item.lead_times[key] === 1 ? '' : 's'}`}</div></div>)}</div></section>

    <section><div className="mb-3 flex items-center justify-between"><h3 className="flex items-center gap-2 text-sm font-bold"><History className="h-4 w-4 text-savia-accent" /> Historique des opérations</h3><button onClick={() => onHistory(item)} className="text-xs font-semibold text-savia-accent">{history.length ? 'Actualiser' : 'Afficher'}</button></div>{historyLoading ? <Loader2 className="mx-auto h-5 w-5 animate-spin text-savia-accent" /> : history.length > 0 && <div className="max-h-52 space-y-2 overflow-y-auto">{history.map(event => <div key={event.id} className="rounded-lg border border-savia-border p-2.5 text-xs"><div className="flex justify-between gap-3"><strong>{historyLabel(event)}</strong><span className="text-savia-text-dim">{formatDateTime(event.occurred_at)}</span></div><div className="mt-1 text-savia-text-muted">{event.actor_username}{event.change_reason ? ` · ${event.change_reason}` : ''}</div></div>)}</div>}</section>

    <div className="flex flex-wrap justify-end gap-2 border-t border-savia-border pt-3">{canDeleteCase && <button onClick={() => onDeleteCase(item)} className="flex items-center gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs font-bold text-red-300 hover:bg-red-500/20"><Trash2 className="h-3.5 w-3.5" /> Supprimer le dossier</button>}<button onClick={() => onToggleBlocked(item)} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-bold ${item.case_state === 'blocked' ? 'bg-green-500/10 text-green-300' : 'bg-red-500/10 text-red-300'}`}>{item.case_state === 'blocked' ? <RefreshCw className="h-3.5 w-3.5" /> : <Ban className="h-3.5 w-3.5" />}{item.case_state === 'blocked' ? 'Remettre en activité' : 'Bloquer le dossier'}</button></div>
  </div>;
}
