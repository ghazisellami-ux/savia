'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, CalendarClock, Check, CheckCircle2, ChevronRight, Circle,
  ClipboardCheck, FileCheck2, FileSignature, FileText, History, Landmark, Loader2, PackageCheck,
  Plus, RefreshCw, Search, ShieldCheck, X,
} from 'lucide-react';
import { clients as clientsApi, publicMarkets } from '@/lib/api';
import { Modal } from '@/components/ui/modal';
import { useAuth } from '@/lib/auth-context';
import { useRoleGuard } from '@/lib/use-role-guard';
import { KpiCard } from '@/components/ui/cards';

type CaseState = 'active' | 'blocked' | 'cancelled';
type StepType = 'signature' | 'equipment_reception' | 'delivery_note' | 'invoice' | 'provisional_acceptance' | 'final_acceptance';

interface MarketAlert {
  type: 'execution' | 'warranty';
  label: string;
  due_date: string;
  days_remaining: number;
  severity: 'warning' | 'critical' | 'overdue';
}

interface PublicMarketCase {
  id: number;
  client: string;
  market_number: string;
  market_object: string;
  owner_username: string;
  signature_date?: string | null;
  execution_delay_days?: number | null;
  execution_deadline?: string | null;
  equipment_reception_date?: string | null;
  equipment_reception_note: string;
  delivery_note_date?: string | null;
  delivery_note_reference: string;
  invoice_date?: string | null;
  invoice_reference: string;
  provisional_acceptance_date?: string | null;
  provisional_acceptance_reference: string;
  warranty_retention_days?: number | null;
  warranty_deadline?: string | null;
  final_acceptance_date?: string | null;
  final_acceptance_reference: string;
  case_state: CaseState;
  block_reason: string;
  notes: string;
  status: string;
  status_label: string;
  next_step?: StepType | null;
  progress_completed: number;
  progress_total: number;
  alert?: MarketAlert | null;
  updated_at: string;
}

interface ResponsibleOption {
  username: string;
  display_name: string;
  role: string;
}

interface MarketHistoryItem {
  id: number;
  action: string;
  actor_username: string;
  occurred_at: string;
  before_data?: Record<string, unknown> | null;
  after_data?: Record<string, unknown> | null;
}

interface MarketForm {
  client: string;
  market_number: string;
  market_object: string;
  owner_username: string;
  signature_date: string;
  execution_delay_days: string;
  equipment_reception_date: string;
  equipment_reception_note: string;
  delivery_note_date: string;
  delivery_note_reference: string;
  invoice_date: string;
  invoice_reference: string;
  provisional_acceptance_date: string;
  provisional_acceptance_reference: string;
  warranty_retention_days: string;
  final_acceptance_date: string;
  final_acceptance_reference: string;
  case_state: CaseState;
  block_reason: string;
  notes: string;
}

const INPUT = 'w-full rounded-lg border border-savia-border bg-savia-surface-hover px-3 py-2.5 text-sm text-savia-text outline-none transition focus:ring-2 focus:ring-savia-accent/40';
const LABEL = 'mb-1 block text-xs font-semibold uppercase tracking-wider text-savia-text-muted';

const STEPS: Array<{ key: StepType; field: keyof PublicMarketCase; label: string; shortLabel: string }> = [
  { key: 'signature', field: 'signature_date', label: 'Signature du marché', shortLabel: 'Signature' },
  { key: 'equipment_reception', field: 'equipment_reception_date', label: 'Réception matériel / équipement', shortLabel: 'Réception' },
  { key: 'delivery_note', field: 'delivery_note_date', label: 'Bon de livraison', shortLabel: 'BL' },
  { key: 'invoice', field: 'invoice_date', label: 'Facture', shortLabel: 'Facture' },
  { key: 'provisional_acceptance', field: 'provisional_acceptance_date', label: 'PV provisoire', shortLabel: 'PV provisoire' },
  { key: 'final_acceptance', field: 'final_acceptance_date', label: 'PV définitif', shortLabel: 'PV définitif' },
];

const STEP_ACTION: Record<StepType, string> = {
  signature: 'Renseigner la signature',
  equipment_reception: 'Confirmer la réception',
  delivery_note: 'Renseigner le BL',
  invoice: 'Renseigner la facture',
  provisional_acceptance: 'Renseigner le PV provisoire',
  final_acceptance: 'Renseigner le PV définitif',
};

const STATUS_STYLE: Record<string, string> = {
  signature_pending: 'border-slate-500/25 bg-slate-500/15 text-slate-300',
  equipment_reception_pending: 'border-blue-500/25 bg-blue-500/15 text-blue-300',
  delivery_note_pending: 'border-cyan-500/25 bg-cyan-500/15 text-cyan-300',
  invoice_pending: 'border-amber-500/25 bg-amber-500/15 text-amber-300',
  provisional_acceptance_pending: 'border-amber-500/25 bg-amber-500/15 text-amber-300',
  warranty_in_progress: 'border-violet-500/25 bg-violet-500/15 text-violet-300',
  warranty_expiring: 'border-orange-500/25 bg-orange-500/15 text-orange-300',
  final_acceptance_pending: 'border-red-500/25 bg-red-500/15 text-red-300',
  completed: 'border-green-500/25 bg-green-500/15 text-green-300',
  blocked: 'border-red-500/25 bg-red-500/15 text-red-300',
  cancelled: 'border-slate-500/25 bg-slate-500/15 text-slate-400',
};

const emptyForm = (): MarketForm => ({
  client: '', market_number: '', market_object: '', owner_username: '',
  signature_date: '', execution_delay_days: '', equipment_reception_date: '',
  equipment_reception_note: '', delivery_note_date: '', delivery_note_reference: '',
  invoice_date: '', invoice_reference: '',
  provisional_acceptance_date: '', provisional_acceptance_reference: '',
  warranty_retention_days: '', final_acceptance_date: '', final_acceptance_reference: '',
  case_state: 'active', block_reason: '', notes: '',
});

const formFromCase = (item: PublicMarketCase): MarketForm => ({
  client: item.client || '', market_number: item.market_number || '', market_object: item.market_object || '',
  owner_username: item.owner_username || '', signature_date: item.signature_date?.slice(0, 10) || '',
  execution_delay_days: item.execution_delay_days?.toString() || '',
  equipment_reception_date: item.equipment_reception_date?.slice(0, 10) || '',
  equipment_reception_note: item.equipment_reception_note || '',
  delivery_note_date: item.delivery_note_date?.slice(0, 10) || '',
  delivery_note_reference: item.delivery_note_reference || '',
  invoice_date: item.invoice_date?.slice(0, 10) || '',
  invoice_reference: item.invoice_reference || '',
  provisional_acceptance_date: item.provisional_acceptance_date?.slice(0, 10) || '',
  provisional_acceptance_reference: item.provisional_acceptance_reference || '',
  warranty_retention_days: item.warranty_retention_days?.toString() || '',
  final_acceptance_date: item.final_acceptance_date?.slice(0, 10) || '',
  final_acceptance_reference: item.final_acceptance_reference || '',
  case_state: item.case_state || 'active', block_reason: item.block_reason || '', notes: item.notes || '',
});

const formatDate = (value?: string | null) => value
  ? new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString('fr-FR')
  : '—';
const formatDateTime = (value?: string | null) => value ? new Date(value).toLocaleString('fr-FR') : '—';

const HISTORY_ACTION_LABELS: Record<string, string> = {
  CREATE_CASE: 'Dossier créé',
  IMPORT_CASE: 'Dossier existant repris dans l’historique',
  SET_SIGNATURE: 'Signature du marché renseignée',
  UPDATE_SIGNATURE: 'Date de signature modifiée',
  CLEAR_SIGNATURE: 'Date de signature supprimée',
  SET_EQUIPMENT_RECEPTION: 'Réception du matériel enregistrée',
  UPDATE_EQUIPMENT_RECEPTION: 'Réception du matériel modifiée',
  CLEAR_EQUIPMENT_RECEPTION: 'Réception du matériel supprimée',
  SET_DELIVERY_NOTE: 'Bon de livraison renseigné',
  UPDATE_DELIVERY_NOTE: 'Bon de livraison modifié',
  CLEAR_DELIVERY_NOTE: 'Bon de livraison supprimé',
  SET_INVOICE: 'Facture renseignée',
  UPDATE_INVOICE: 'Facture modifiée',
  CLEAR_INVOICE: 'Facture supprimée',
  SET_PROVISIONAL_ACCEPTANCE: 'PV provisoire renseigné',
  UPDATE_PROVISIONAL_ACCEPTANCE: 'PV provisoire modifié',
  CLEAR_PROVISIONAL_ACCEPTANCE: 'PV provisoire supprimé',
  SET_FINAL_ACCEPTANCE: 'PV définitif renseigné',
  UPDATE_FINAL_ACCEPTANCE: 'PV définitif modifié',
  CLEAR_FINAL_ACCEPTANCE: 'PV définitif supprimé',
  BLOCK_CASE: 'Dossier bloqué',
  CANCEL_CASE: 'Dossier annulé',
  REACTIVATE_CASE: 'Dossier réactivé',
  UPDATE_CASE: 'Dossier modifié',
};

const historyActionLabel = (event: MarketHistoryItem) => {
  if (event.action !== 'UPDATE_CASE') return HISTORY_ACTION_LABELS[event.action] || event.action.replaceAll('_', ' ');
  const changedFields = Array.isArray(event.after_data?.changed_fields)
    ? event.after_data.changed_fields.map(String)
    : [];
  const fieldLabels: Record<string, string> = {
    client: 'client', market_number: 'numéro du marché', market_object: 'objet du marché',
    owner_username: 'responsable', signature_date: 'signature', execution_delay_days: 'délai d’exécution',
    equipment_reception_date: 'réception', equipment_reception_note: 'détail de réception',
    delivery_note_date: 'date du BL', delivery_note_reference: 'référence du BL',
    invoice_date: 'date de facture', invoice_reference: 'référence de facture',
    provisional_acceptance_date: 'date du PV provisoire', provisional_acceptance_reference: 'référence du PV provisoire',
    warranty_retention_days: 'retenue de garantie', final_acceptance_date: 'date du PV définitif',
    final_acceptance_reference: 'référence du PV définitif', notes: 'notes', block_reason: 'motif',
  };
  const labels = changedFields.map(field => fieldLabels[field] || field).slice(0, 3);
  if (!labels.length) return 'Dossier modifié';
  return `Modification : ${labels.join(', ')}${changedFields.length > 3 ? '…' : ''}`;
};

const addDays = (value: string, days: string) => {
  if (!value || days === '') return null;
  const parsed = Number(days);
  if (!Number.isFinite(parsed)) return null;
  const result = new Date(`${value}T00:00:00`);
  result.setDate(result.getDate() + parsed);
  return result.toISOString().slice(0, 10);
};

const errorMessage = (error: unknown, fallback: string) => error instanceof Error ? error.message : fallback;

function Progress({ item }: { item: PublicMarketCase }) {
  return (
    <div className="min-w-[285px]">
      <div className="flex items-center">
        {STEPS.map((step, index) => {
          const complete = Boolean(item[step.field]);
          const active = item.next_step === step.key;
          return (
            <div key={step.key} className="flex flex-1 items-center last:flex-none" title={`${step.label} : ${formatDate(item[step.field] as string | null)}`}>
              <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${complete ? 'border-green-400/40 bg-green-500/20 text-green-300' : active ? 'border-savia-accent bg-savia-accent/15 text-savia-accent' : 'border-savia-border text-savia-text-dim'}`}>
                {complete ? <Check className="h-3.5 w-3.5" /> : <Circle className="h-2.5 w-2.5" />}
              </span>
              {index < STEPS.length - 1 && <span className={`h-0.5 flex-1 ${complete ? 'bg-green-500/40' : 'bg-savia-border'}`} />}
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] text-savia-text-dim">
        <span>Signature</span><span>Réception</span><span>BL</span><span>Facture</span><span>PV prov.</span><span>PV déf.</span>
      </div>
    </div>
  );
}

function AlertLabel({ alert }: { alert: MarketAlert }) {
  const overdue = alert.days_remaining < 0;
  return (
    <div className={`mt-1.5 flex items-start gap-1 text-[11px] font-bold ${alert.severity === 'warning' ? 'text-orange-300' : 'text-red-300'}`}>
      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
      <span>{alert.label} · {overdue ? `${Math.abs(alert.days_remaining)} j de retard` : alert.days_remaining === 0 ? "aujourd’hui" : `J-${alert.days_remaining}`}</span>
    </div>
  );
}

export default function PublicMarketsPage() {
  useRoleGuard('marches');
  const { user } = useAuth();
  const [cases, setCases] = useState<PublicMarketCase[]>([]);
  const [clients, setClients] = useState<string[]>([]);
  const [clientsLoading, setClientsLoading] = useState(true);
  const [clientsError, setClientsError] = useState('');
  const [responsibles, setResponsibles] = useState<ResponsibleOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');
  const [clientFilter, setClientFilter] = useState('');
  const [equipmentFilter, setEquipmentFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [editing, setEditing] = useState<PublicMarketCase | null | 'new'>(null);
  const [form, setForm] = useState<MarketForm>(emptyForm());
  const [history, setHistory] = useState<MarketHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setCases(await publicMarkets.list() as unknown as PublicMarketCase[]);
    } catch (err: unknown) {
      setError(errorMessage(err, 'Impossible de charger le suivi des marchés.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    clientsApi.list()
      .then(data => setClients([...new Set((data as Array<Record<string, unknown>>)
        .map(item => String(item.nom || item.client || '').trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'fr'))))
      .catch(() => setClientsError('La liste des clients n’a pas pu être chargée.'))
      .finally(() => setClientsLoading(false));
    publicMarkets.responsibles()
      .then(data => setResponsibles((data as Array<Record<string, unknown>>).map(item => ({
        username: String(item.username || ''),
        display_name: String(item.display_name || item.username || ''),
        role: String(item.role || ''),
      }))))
      .catch(() => {});
  }, []);

  const loadHistory = useCallback(async (item: PublicMarketCase) => {
    setHistoryLoading(true);
    setHistoryError('');
    try {
      setHistory(await publicMarkets.history(item.id) as unknown as MarketHistoryItem[]);
    } catch (err: unknown) {
      setHistory([]);
      setHistoryError(errorMessage(err, 'Impossible de charger l’historique.'));
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const openNew = () => {
    const responsible = responsibles.find(item => item.username === user?.username) || responsibles[0];
    setForm({ ...emptyForm(), owner_username: responsible?.username || user?.username || '' });
    setHistory([]);
    setHistoryError('');
    setEditing('new');
  };

  const openEdit = (item: PublicMarketCase) => {
    setForm(formFromCase(item));
    setHistory([]);
    setHistoryError('');
    setEditing(item);
    void loadHistory(item);
  };

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const payload = {
        ...form,
        execution_delay_days: form.execution_delay_days === '' ? null : Number(form.execution_delay_days),
        warranty_retention_days: form.warranty_retention_days === '' ? null : Number(form.warranty_retention_days),
      };
      const result = editing === 'new'
        ? await publicMarkets.create(payload)
        : await publicMarkets.update((editing as PublicMarketCase).id, payload);
      const saved = result as unknown as PublicMarketCase;
      setCases(previous => editing === 'new'
        ? [saved, ...previous]
        : previous.map(item => item.id === saved.id ? saved : item));
      setNotice(editing === 'new' ? `Le marché n° ${saved.market_number} a été créé.` : `Le marché n° ${saved.market_number} a été mis à jour.`);
      setEditing(null);
    } catch (err: unknown) {
      setError(errorMessage(err, 'Impossible d’enregistrer le dossier.'));
    } finally {
      setSaving(false);
    }
  };

  const availableEquipmentFilters = useMemo(() => {
    const selectedClient = clientFilter.toLocaleLowerCase('fr');
    const equipmentNames = cases
      .filter(item => !selectedClient || item.client.toLocaleLowerCase('fr') === selectedClient)
      .map(item => item.equipment_reception_note.trim())
      .filter(Boolean);
    return [...new Set(equipmentNames)].sort((a, b) => a.localeCompare(b, 'fr'));
  }, [cases, clientFilter]);

  const filteredCases = useMemo(() => cases.filter(item => {
    const needle = search.trim().toLocaleLowerCase('fr');
    const matchesSearch = !needle || [item.id, item.client, item.market_number, item.market_object, item.equipment_reception_note, item.owner_username]
      .join(' ').toLocaleLowerCase('fr').includes(needle);
    const matchesClient = !clientFilter || item.client === clientFilter;
    const matchesEquipment = !equipmentFilter || item.equipment_reception_note === equipmentFilter;
    const matchesStatus = !statusFilter || (statusFilter === 'alert' ? Boolean(item.alert) : item.status === statusFilter);
    return matchesSearch && matchesClient && matchesEquipment && matchesStatus;
  }), [cases, clientFilter, equipmentFilter, search, statusFilter]);

  const kpis = useMemo(() => ({
    total: cases.length,
    active: cases.filter(item => !['completed', 'cancelled'].includes(item.status)).length,
    alerts: cases.filter(item => item.alert).length,
    completed: cases.filter(item => item.status === 'completed').length,
  }), [cases]);

  const executionDeadline = addDays(form.signature_date, form.execution_delay_days);
  const warrantyDeadline = addDays(form.provisional_acceptance_date, form.warranty_retention_days);
  const formClientOptions = useMemo(() => {
    const values = [...clients];
    if (editing !== 'new' && form.client && !values.includes(form.client)) values.push(form.client);
    return values.sort((a, b) => a.localeCompare(b, 'fr'));
  }, [clients, editing, form.client]);

  if (loading) return <div className="flex h-64 items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-savia-accent" /></div>;

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-black gradient-text"><Landmark className="h-7 w-7" /> Suivi des marchés</h1>
          <p className="mt-1 text-sm text-savia-text-muted">Pilotage des marchés publics, de la signature au PV définitif</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => void load()} className="rounded-lg border border-savia-border p-2.5 text-savia-text-muted hover:text-savia-accent" title="Actualiser"><RefreshCw className="h-4 w-4" /></button>
          <button onClick={openNew} className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-savia-accent to-savia-accent-blue px-4 py-2.5 text-sm font-bold text-white"><Plus className="h-4 w-4" /> Nouveau dossier</button>
        </div>
      </div>

      {error && <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300"><AlertTriangle className="h-4 w-4 shrink-0" />{error}<button onClick={() => setError('')} className="ml-auto"><X className="h-4 w-4" /></button></div>}
      {notice && <div className="flex items-center gap-2 rounded-xl border border-blue-500/30 bg-blue-500/10 px-4 py-3 text-sm text-blue-200"><CheckCircle2 className="h-4 w-4 shrink-0" />{notice}<button onClick={() => setNotice('')} className="ml-auto"><X className="h-4 w-4" /></button></div>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { label: 'Total des marchés', value: kpis.total, icon: Landmark, color: 'text-savia-accent', filter: '' },
          { label: 'Dossiers en cours', value: kpis.active, icon: CalendarClock, color: 'text-blue-300', filter: '' },
          { label: 'Alertes à traiter', value: kpis.alerts, icon: AlertTriangle, color: 'text-red-300', filter: 'alert' },
          { label: 'Marchés achevés', value: kpis.completed, icon: CheckCircle2, color: 'text-green-300', filter: 'completed' },
        ].map(card => {
          const Icon = card.icon;
          return <KpiCard key={card.label} className={card.filter && statusFilter === card.filter ? 'ring-2 ring-savia-accent' : undefined}
            appearance="status-stripe" icon={<Icon className="h-5 w-5" />} value={String(card.value)} label={card.label}
            variant={card.label === 'Alertes à traiter' ? (card.value > 0 ? 'danger' : 'success') : card.label === 'Marchés achevés' ? 'success' : card.label === 'Dossiers en cours' ? 'warning' : 'default'}
            onClick={card.filter ? () => setStatusFilter(value => value === card.filter ? '' : card.filter) : undefined} />;
        })}
      </div>

      <div className="glass grid grid-cols-1 gap-3 rounded-xl p-3 xl:grid-cols-[minmax(260px,1fr)_minmax(180px,0.55fr)_minmax(180px,0.55fr)_minmax(210px,0.65fr)_auto]">
        <div className="relative min-w-0"><Search className="absolute left-3 top-2.5 h-4 w-4 text-savia-text-dim" /><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Client, équipement, numéro, objet du marché…" className={`${INPUT} pl-9`} /></div>
        <select value={clientFilter} onChange={event => { setClientFilter(event.target.value); setEquipmentFilter(''); }} className={`${INPUT} min-w-0`}><option value="">Tous les clients</option>{[...new Set([...clients, ...cases.map(item => item.client)])].filter(Boolean).sort().map(client => <option key={client}>{client}</option>)}</select>
        <select value={equipmentFilter} onChange={event => setEquipmentFilter(event.target.value)} disabled={availableEquipmentFilters.length === 0} className={`${INPUT} min-w-0 disabled:cursor-not-allowed disabled:opacity-50`}><option value="">Tous les équipements</option>{availableEquipmentFilters.map(equipment => <option key={equipment}>{equipment}</option>)}</select>
        <select value={statusFilter} onChange={event => setStatusFilter(event.target.value)} className={`${INPUT} min-w-0`}><option value="">Tous les statuts</option><option value="alert">Avec alerte</option>{[...new Map(cases.map(item => [item.status, item.status_label])).entries()].map(([status, label]) => <option key={status} value={status}>{label}</option>)}</select>
        {(search || clientFilter || equipmentFilter || statusFilter) && <button onClick={() => { setSearch(''); setClientFilter(''); setEquipmentFilter(''); setStatusFilter(''); }} className="text-xs font-semibold text-savia-accent">Réinitialiser</button>}
      </div>

      <div className="glass overflow-hidden rounded-xl">
        <div className="border-b border-savia-border px-4 py-3 text-sm font-semibold">{filteredCases.length} dossier{filteredCases.length > 1 ? 's' : ''}</div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1180px] text-sm">
            <thead className="bg-savia-surface-hover/70 text-left text-xs text-savia-text-muted"><tr><th className="px-3 py-3">Dossier</th><th className="px-3 py-3">Client / marché</th><th className="px-3 py-3">Progression</th><th className="px-3 py-3">Délais</th><th className="px-3 py-3">Statut</th><th className="px-3 py-3">Action suivante</th><th className="px-3 py-3" /></tr></thead>
            <tbody>
              {filteredCases.map(item => <tr key={item.id} className={`border-t border-savia-border/40 hover:bg-savia-surface-hover/40 ${item.alert?.severity === 'overdue' ? 'bg-red-500/5' : ''}`}>
                <td className="px-3 py-3"><button onClick={() => openEdit(item)} className="font-mono font-bold text-savia-accent">#{item.id}</button><div className="mt-1 text-[11px] text-savia-text-dim">Mis à jour {formatDate(item.updated_at)}</div></td>
                <td className="max-w-[260px] px-3 py-3"><div className="font-semibold">{item.client}</div><div className="mt-0.5 text-xs font-medium text-savia-text-muted">Marché n° {item.market_number}</div><div className="mt-0.5 truncate text-[11px] text-savia-text-dim">{item.market_object || 'Objet non renseigné'}</div></td>
                <td className="px-3 py-3"><Progress item={item} /></td>
                <td className="px-3 py-3 text-xs"><div><span className="text-savia-text-muted">Exécution :</span> <strong>{formatDate(item.execution_deadline)}</strong></div><div className="mt-1"><span className="text-savia-text-muted">Garantie :</span> <strong>{formatDate(item.warranty_deadline)}</strong></div></td>
                <td className="px-3 py-3"><span className={`inline-flex rounded-full border px-2 py-1 text-xs font-bold ${STATUS_STYLE[item.status] || STATUS_STYLE.signature_pending}`}>{item.status_label}</span>{item.alert && <AlertLabel alert={item.alert} />}</td>
                <td className="px-3 py-3">{item.next_step ? <button onClick={() => openEdit(item)} className="inline-flex items-center gap-1.5 rounded-lg bg-savia-accent/10 px-3 py-2 text-xs font-bold text-savia-accent hover:bg-savia-accent/20">{STEP_ACTION[item.next_step]}<ChevronRight className="h-3.5 w-3.5" /></button> : <span className="text-xs font-semibold text-green-300">Dossier terminé</span>}</td>
                <td className="px-3 py-3 text-right"><button onClick={() => openEdit(item)} className="rounded-lg border border-savia-border px-2.5 py-1.5 text-xs font-semibold text-savia-text-muted hover:text-savia-accent">Détails</button></td>
              </tr>)}
              {!filteredCases.length && <tr><td colSpan={7} className="py-12 text-center text-savia-text-muted"><Landmark className="mx-auto mb-2 h-8 w-8 opacity-30" />Aucun dossier ne correspond aux filtres.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <Modal isOpen={editing !== null} onClose={() => setEditing(null)} title={editing === 'new' ? 'Nouveau dossier de marché' : `Dossier de marché #${(editing as PublicMarketCase | null)?.id || ''}`} size="xl">
        <form onSubmit={event => { event.preventDefault(); void save(); }} className="space-y-5">
          <section className="rounded-xl border border-savia-border p-4">
            <div className="mb-3 flex items-center gap-2 font-bold"><Landmark className="h-4 w-4 text-savia-accent" /> Identification du marché</div>
            <div className="grid gap-3 md:grid-cols-2">
              <label>
                <span className={LABEL}>Client *</span>
                <select required disabled={clientsLoading} value={form.client} onChange={event => setForm(value => ({ ...value, client: event.target.value }))} className={INPUT}>
                  <option value="">{clientsLoading ? 'Chargement des clients…' : 'Sélectionner un client'}</option>
                  {formClientOptions.map(client => <option key={client} value={client}>{client}</option>)}
                </select>
                {clientsError && <span className="mt-1 block text-xs text-red-300">{clientsError}</span>}
                {!clientsLoading && !clientsError && clients.length === 0 && <span className="mt-1 block text-xs text-amber-300">Aucun client disponible dans la base clients.</span>}
              </label>
              <label><span className={LABEL}>Numéro du marché *</span><input required value={form.market_number} onChange={event => setForm(value => ({ ...value, market_number: event.target.value }))} className={INPUT} placeholder="Ex. MP-2026-014" /></label>
              <label className="md:col-span-2"><span className={LABEL}>Objet du marché</span><input value={form.market_object} onChange={event => setForm(value => ({ ...value, market_object: event.target.value }))} className={INPUT} placeholder="Fourniture, installation ou prestation concernée" /></label>
              <label><span className={LABEL}>Responsable</span><select value={form.owner_username} onChange={event => setForm(value => ({ ...value, owner_username: event.target.value }))} className={INPUT}><option value="">Non assigné</option>{responsibles.map(item => <option key={item.username} value={item.username}>{item.display_name} · {item.role}</option>)}</select></label>
              <label><span className={LABEL}>État administratif</span><select value={form.case_state} onChange={event => setForm(value => ({ ...value, case_state: event.target.value as CaseState }))} className={INPUT}><option value="active">Actif</option><option value="blocked">Bloqué</option><option value="cancelled">Annulé</option></select></label>
              {form.case_state !== 'active' && <label className="md:col-span-2"><span className={LABEL}>Motif *</span><input required value={form.block_reason} onChange={event => setForm(value => ({ ...value, block_reason: event.target.value }))} className={INPUT} /></label>}
            </div>
          </section>

          <section className="rounded-xl border border-savia-border p-4">
            <div className="mb-4 flex items-center gap-2 font-bold"><CalendarClock className="h-4 w-4 text-blue-300" /> Progression et délais</div>
            <div className="space-y-4">
              <div className="grid gap-3 rounded-lg bg-savia-surface-hover/50 p-3 md:grid-cols-3"><div className="flex items-center gap-2 text-sm font-semibold"><FileSignature className="h-4 w-4 text-blue-300" /> Signature</div><label><span className={LABEL}>Date de signature</span><input type="date" value={form.signature_date} onChange={event => setForm(value => ({ ...value, signature_date: event.target.value }))} className={INPUT} /></label><label><span className={LABEL}>Délai d’exécution (jours)</span><input type="number" min="0" value={form.execution_delay_days} onChange={event => setForm(value => ({ ...value, execution_delay_days: event.target.value }))} className={INPUT} /></label>{executionDeadline && <div className="md:col-start-2 md:col-span-2 text-xs text-blue-200">Échéance d’exécution calculée : <strong>{formatDate(executionDeadline)}</strong> · rappels à J‑30 et J‑15</div>}</div>
              <div className="grid gap-3 rounded-lg bg-savia-surface-hover/50 p-3 md:grid-cols-3"><div className="flex items-center gap-2 text-sm font-semibold"><PackageCheck className="h-4 w-4 text-cyan-300" /> Réception</div><label><span className={LABEL}>Date de réception</span><input type="date" value={form.equipment_reception_date} onChange={event => setForm(value => ({ ...value, equipment_reception_date: event.target.value }))} className={INPUT} /></label><label><span className={LABEL}>Matériel / équipement reçu</span><input value={form.equipment_reception_note} onChange={event => setForm(value => ({ ...value, equipment_reception_note: event.target.value }))} className={INPUT} placeholder="Détail ou observation" /></label></div>
              <div className="grid gap-3 rounded-lg bg-savia-surface-hover/50 p-3 md:grid-cols-3"><div className="flex items-center gap-2 text-sm font-semibold"><FileCheck2 className="h-4 w-4 text-amber-300" /> Bon de livraison</div><label><span className={LABEL}>Date du BL</span><input type="date" value={form.delivery_note_date} onChange={event => setForm(value => ({ ...value, delivery_note_date: event.target.value }))} className={INPUT} /></label><label><span className={LABEL}>Référence du BL</span><input value={form.delivery_note_reference} onChange={event => setForm(value => ({ ...value, delivery_note_reference: event.target.value }))} className={INPUT} /></label></div>
              <div className="grid gap-3 rounded-lg bg-savia-surface-hover/50 p-3 md:grid-cols-3"><div className="flex items-center gap-2 text-sm font-semibold"><FileText className="h-4 w-4 text-orange-300" /> Facture</div><label><span className={LABEL}>Date de facture</span><input type="date" value={form.invoice_date} onChange={event => setForm(value => ({ ...value, invoice_date: event.target.value }))} className={INPUT} /></label><label><span className={LABEL}>Référence de facture</span><input value={form.invoice_reference} onChange={event => setForm(value => ({ ...value, invoice_reference: event.target.value }))} className={INPUT} /></label></div>
              <div className="grid gap-3 rounded-lg bg-savia-surface-hover/50 p-3 md:grid-cols-3"><div className="flex items-center gap-2 text-sm font-semibold"><ClipboardCheck className="h-4 w-4 text-violet-300" /> PV provisoire</div><label><span className={LABEL}>Date du PV provisoire</span><input type="date" value={form.provisional_acceptance_date} onChange={event => setForm(value => ({ ...value, provisional_acceptance_date: event.target.value }))} className={INPUT} /></label><label><span className={LABEL}>Référence</span><input value={form.provisional_acceptance_reference} onChange={event => setForm(value => ({ ...value, provisional_acceptance_reference: event.target.value }))} className={INPUT} /></label><label className="md:col-start-2"><span className={LABEL}>Retenue de garantie (jours)</span><input type="number" min="0" value={form.warranty_retention_days} onChange={event => setForm(value => ({ ...value, warranty_retention_days: event.target.value }))} className={INPUT} /></label>{warrantyDeadline && <div className="self-end pb-3 text-xs text-violet-200">Fin de garantie : <strong>{formatDate(warrantyDeadline)}</strong> · rappel à J‑30</div>}</div>
              <div className="grid gap-3 rounded-lg bg-savia-surface-hover/50 p-3 md:grid-cols-3"><div className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck className="h-4 w-4 text-green-300" /> PV définitif</div><label><span className={LABEL}>Date du PV définitif</span><input type="date" value={form.final_acceptance_date} onChange={event => setForm(value => ({ ...value, final_acceptance_date: event.target.value }))} className={INPUT} /></label><label><span className={LABEL}>Référence</span><input value={form.final_acceptance_reference} onChange={event => setForm(value => ({ ...value, final_acceptance_reference: event.target.value }))} className={INPUT} /></label></div>
            </div>
          </section>

          <label><span className={LABEL}>Notes</span><textarea rows={3} value={form.notes} onChange={event => setForm(value => ({ ...value, notes: event.target.value }))} className={INPUT} placeholder="Observations, réserves ou éléments de suivi…" /></label>

          {editing !== 'new' && <section className="rounded-xl border border-savia-border p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="flex items-center gap-2 text-sm font-bold"><History className="h-4 w-4 text-savia-accent" /> Historique des actions</h3>
              <button type="button" onClick={() => void loadHistory(editing as PublicMarketCase)} disabled={historyLoading} className="text-xs font-semibold text-savia-accent disabled:opacity-50">Actualiser</button>
            </div>
            {historyLoading && <div className="flex justify-center py-4"><Loader2 className="h-5 w-5 animate-spin text-savia-accent" /></div>}
            {historyError && <div className="rounded-lg border border-red-500/25 bg-red-500/10 p-3 text-xs text-red-300">{historyError}</div>}
            {!historyLoading && !historyError && history.length === 0 && <div className="py-3 text-center text-xs text-savia-text-muted">Aucune action enregistrée.</div>}
            {!historyLoading && history.length > 0 && <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
              {history.map(event => <div key={event.id} className="rounded-lg border border-savia-border bg-savia-surface-hover/40 p-3 text-xs">
                <div className="flex flex-wrap items-start justify-between gap-2"><strong>{historyActionLabel(event)}</strong><span className="whitespace-nowrap text-savia-text-dim">{formatDateTime(event.occurred_at)}</span></div>
                <div className="mt-1 text-savia-text-muted">Effectué par <span className="font-semibold text-savia-text">{event.actor_username}</span></div>
              </div>)}
            </div>}
          </section>}

          <div className="flex justify-end gap-2 border-t border-savia-border pt-4"><button type="button" onClick={() => setEditing(null)} className="rounded-lg border border-savia-border px-4 py-2.5 text-sm font-semibold text-savia-text-muted">Annuler</button><button disabled={saving || clientsLoading || !form.client} className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-savia-accent to-savia-accent-blue px-5 py-2.5 text-sm font-bold text-white disabled:opacity-50">{saving && <Loader2 className="h-4 w-4 animate-spin" />}{editing === 'new' ? 'Créer le dossier' : 'Enregistrer'}</button></div>
        </form>
      </Modal>
    </div>
  );
}
