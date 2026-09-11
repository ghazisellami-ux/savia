'use client';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import {
  Plus, Search, Clock, Calendar, CheckCircle, AlertTriangle, X,
  Loader2, ClipboardList, User, Phone, Building2, Server,
  Zap, FileText, Tag, Edit, Send, UserCheck, Lock, Users, Trash2
} from 'lucide-react';
import { billing, demandes, equipements, techniciens as techApi, clients as clientsApi } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { KpiCard } from '@/components/ui/cards';

interface Demande {
  id: number;
  date: string;
  date_planifiee: string;
  machine: string;
  client: string;
  demandeur: string;
  priorite: string;
  type_intervention: string;
  statut: string;
  description: string;
  code_erreur: string;
  contact_nom: string;
  contact_tel: string;
  technicien_assigne: string;
  notes_traitement: string;
  intervention_id?: number | null;
  billing_case_id?: number | null;
}

interface EquipmentOption {
  id: string;
  name: string;
  manufacturer: string;
  model: string;
  serialNumber: string;
}

const toEquipmentOptions = (items: Array<Record<string, unknown>>): EquipmentOption[] => items
  .map((equipment, index) => ({
    id: String(equipment.id ?? `${equipment.Nom || equipment.nom || 'equipement'}-${index}`),
    name: String(equipment.Nom || equipment.nom || ''),
    manufacturer: String(equipment.Fabricant || equipment.fabricant || ''),
    model: String(equipment.Modele || equipment.modele || ''),
    serialNumber: String(equipment.NumSerie || equipment.Num_Serie || equipment.num_serie || ''),
  }))
  .filter(equipment => equipment.name);

const equipmentOptionLabel = (equipment: EquipmentOption): string => [
  equipment.name,
  equipment.manufacturer,
  equipment.model,
  equipment.serialNumber ? `SN: ${equipment.serialNumber}` : '',
].filter(Boolean).join(' · ');

// === 3 statuts officiels ===
const STATUTS = ['En attente', 'Assignée', 'Clôturée'] as const;
type Statut = typeof STATUTS[number];

/** Normalise les anciens statuts vers les 3 officiels */
function normalizeStatut(s: string): Statut {
  const normalized = String(s || '').toLocaleLowerCase('fr');
  if (['résol', 'resol', 'réalis', 'realis', 'clôt', 'clot', 'termin', 'annul'].some(token => normalized.includes(token))) return 'Clôturée';
  if (['planif', 'cours', 'assign'].some(token => normalized.includes(token))) return 'Assignée';
  return 'En attente'; // 'Nouvelle', '', undefined → En attente
}

const INPUT_CLS = "w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 focus:border-savia-accent/40 outline-none transition-all";

const URGENCE_COLORS: Record<string, string> = {
  'Critique': 'bg-red-500/15 text-red-400 border border-red-500/30',
  'Haute': 'bg-orange-500/15 text-orange-400 border border-orange-500/30',
  'Moyenne': 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30',
  'Basse': 'bg-green-500/15 text-green-400 border border-green-500/30',
};

const STATUT_COLORS: Record<string, string> = {
  'En attente': 'bg-red-500/10 text-red-400',
  'Assignée':   'bg-blue-500/10 text-blue-400',
  'Clôturée':   'bg-green-500/10 text-green-400',
};

const STATUT_ICONS: Record<string, React.ReactNode> = {
  'En attente': <AlertTriangle className="w-3 h-3 inline mr-1" />,
  'Assignée':   <UserCheck    className="w-3 h-3 inline mr-1" />,
  'Clôturée':   <Lock         className="w-3 h-3 inline mr-1" />,
};

// Format date-time: "2026-06-15 17:45:30" or "2026-06-15T17:45:30" → "15/06/2026  •  17:45"
const formatDateTime = (dateStr: string): string => {
  if (!dateStr || dateStr === 'N/A') return dateStr;
  try {
    // Handle both "2026-06-15 17:45:30" and "2026-06-15T17:45:30" formats
    const normalized = dateStr.replace('T', ' ');
    const parts = normalized.split(' ');
    if (parts.length >= 2) {
      const [year, month, day] = parts[0].split('-');
      const [hour, minute] = parts[1].split(':');
      return `${day}/${month}/${year}  •  ${hour}:${minute}`;
    }
  } catch (e) {
    return dateStr;
  }
  return dateStr;
};

const formatDateOnly = (dateStr: string): string => {
  if (!dateStr || dateStr === 'N/A') return dateStr;
  const [year, month, day] = dateStr.replace('T', ' ').split(' ')[0].split('-');
  return year && month && day ? `${day}/${month}/${year}` : dateStr;
};

const todayIso = (): string => {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

export default function DemandesPage() {
  const router = useRouter();
  const { user } = useAuth();
  const isLecteur = user?.role === 'Lecteur';
  const [billingSource, setBillingSource] = useState<{ id: number; client: string; equipment: string } | null>(null);
  const canCreate = Boolean(user?.role && (
    ['Admin', 'Manager', 'Responsable Technique', 'Lecteur'].includes(user.role)
    || (user.role === 'Gestionnaire' && billingSource)
  ));
  const canAssignTech = user?.role === 'Manager' || user?.role === 'Responsable Technique' || user?.role === 'Admin';
  const canDelete = user?.role === 'Admin' || user?.role === 'Manager';
  const clientNom = user?.client || '';
  const demandeurNom = user?.nom || '';

  const emptyForm = {
    demandeur: demandeurNom, // Pré-rempli avec le nom de l'utilisateur connecté
    client: isLecteur ? clientNom : '',
    equipement: '',
    type_intervention: 'Corrective',
    priorite: 'Moyenne',
    description: '',
    notes_traitement: '',
    code_erreur: '',
    contact_nom: isLecteur ? demandeurNom : '',
    contact_tel: '',
    technicien_assigne: '',
    date_planifiee: todayIso(),
  };

  const [search, setSearch] = useState('');
  const [filterStatut, setFilterStatut] = useState('Tous');
  const [data, setData] = useState<Demande[]>([]);

  const [allClients, setAllClients] = useState<string[]>([]);
  const [filteredEquips, setFilteredEquips] = useState<EquipmentOption[]>([]);
  const [selectedEquipmentId, setSelectedEquipmentId] = useState('');
  const [equipsLoading, setEquipsLoading] = useState(false);
  const [techs, setTechs] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const [showNewModal, setShowNewModal] = useState(false);
  const [form, setForm] = useState({ ...emptyForm });

  const [showUpdateModal, setShowUpdateModal] = useState(false);
  const [selectedDemande, setSelectedDemande] = useState<Demande | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<Demande | null>(null);
  const [updateForm, setUpdateForm] = useState({ statut: '', technicien_assigne: '', notes_traitement: '' });

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [res, techRes, clientRes] = await Promise.all([
        demandes.list(),
        techApi.list().catch(() => []),
        clientsApi.list().catch(() => []),
      ]);
      const mapped = (res as any[]).map((item: any) => ({
        id: Number(item.id || 0),
        date: item.date_demande ? String(item.date_demande).substring(0, 16) : (item.date || 'N/A'),
        date_planifiee: item.date_planifiee ? String(item.date_planifiee).substring(0, 10) : '',
        machine: item.equipement || item.machine || '',
        client: item.client || '',
        demandeur: item.demandeur || '',
        priorite: item.priorite || item.urgence || 'Moyenne',
        type_intervention: item.type_intervention || 'Corrective',
        statut: normalizeStatut(item.statut || ''),
        description: item.description || '',
        code_erreur: item.code_erreur || '',
        contact_nom: item.contact_nom || '',
        contact_tel: item.contact_tel || '',
        technicien_assigne: item.technicien_assigne || '',
        notes_traitement: item.notes_traitement || '',
        intervention_id: item.intervention_id ? Number(item.intervention_id) : null,
        billing_case_id: item.billing_case_id ? Number(item.billing_case_id) : null,
      }));
      setData(mapped);

      const clientNames = (clientRes as any[])
        .map((c: any) => c.nom || c.Nom || c.name || '')
        .filter(Boolean)
        .sort();
      setAllClients(clientNames);

      setTechs((techRes as any[]).map((t: any) => `${t.prenom || ''} ${t.nom || ''}`.trim()).filter(Boolean));
    } catch (err) {
      console.error('Failed to fetch demandes', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    const rawCaseId = new URLSearchParams(window.location.search).get('billing_case_id');
    const caseId = Number(rawCaseId);
    if (!Number.isInteger(caseId) || caseId <= 0) return;

    billing.get(caseId)
      .then((item: Record<string, unknown>) => {
        const source = {
          id: Number(item.id),
          client: String(item.client || ''),
          equipment: String(item.equipment || ''),
        };
        setBillingSource(source);
        setForm(value => ({
          ...value,
          client: source.client,
          equipement: source.equipment,
        }));
        setShowNewModal(true);
      })
      .catch((error) => {
        console.error('Failed to load billing case', error);
        alert("Impossible de charger le dossier de facturation demandé.");
      });
  }, []);

  useEffect(() => {
    if (!isLecteur) return;
    setEquipsLoading(true);
    equipements.list()
      .then((res: Array<Record<string, unknown>>) => {
        const options = toEquipmentOptions(res);
        setFilteredEquips(options);
        setSelectedEquipmentId(current => options.some(equipment => equipment.id === current) ? current : '');
      })
      .catch(() => {
        setFilteredEquips([]);
        setSelectedEquipmentId('');
      })
      .finally(() => setEquipsLoading(false));
  }, [isLecteur]);

  useEffect(() => {
    if (isLecteur) return;
    if (!form.client) {
      setFilteredEquips([]);
      setSelectedEquipmentId('');
      return;
    }
    setEquipsLoading(true);
    equipements.list(form.client)
      .then((res: Array<Record<string, unknown>>) => {
        const options = toEquipmentOptions(res);
        setFilteredEquips(options);
        setSelectedEquipmentId(current => {
          if (options.some(equipment => equipment.id === current)) return current;
          return options.find(equipment => equipment.name === billingSource?.equipment)?.id || '';
        });
      })
      .catch(() => {
        setFilteredEquips([]);
        setSelectedEquipmentId('');
      })
      .finally(() => setEquipsLoading(false));
  }, [billingSource?.equipment, form.client, isLecteur]);

  const duplicateRequest = useMemo(() => {
    const client = form.client.trim().toLocaleLowerCase('fr');
    const equipment = form.equipement.trim().toLocaleLowerCase('fr');
    if (!client || !equipment) return null;
    return data.find(item => (
      item.statut !== 'Clôturée'
      && item.client.trim().toLocaleLowerCase('fr') === client
      && item.machine.trim().toLocaleLowerCase('fr') === equipment
    )) || null;
  }, [data, form.client, form.equipement]);

  const openNewModal = () => {
    setBillingSource(null);
    setForm({ ...emptyForm });
    setSelectedEquipmentId('');
    setShowNewModal(true);
  };

  const closeNewModal = () => {
    setShowNewModal(false);
    if (billingSource) router.push(`/facturation?case_id=${billingSource.id}`);
  };

  const handleCreate = async () => {
    const formToSend = isLecteur
      ? { ...form, demandeur: demandeurNom || clientNom, client: clientNom }
      : form;
    if (!formToSend.equipement || !formToSend.description) {
      alert('Veuillez remplir les champs obligatoires : Équipement et Description');
      return;
    }
    if (!isLecteur && !formToSend.demandeur) {
      alert('Veuillez remplir le champ Demandeur');
      return;
    }
    const payload = {
      ...formToSend,
      date_planifiee: formToSend.date_planifiee || todayIso(),
      ...(billingSource ? { billing_case_id: billingSource.id } : {}),
    };
    setIsSaving(true);
    try {
      const created = await demandes.create(payload as any);
      setShowNewModal(false);
      if (billingSource) {
        router.push(`/facturation?case_id=${created.billing_case_id || billingSource.id}`);
      } else {
        await loadData();
      }
    } catch (err) {
      console.error(err);
      const message = err instanceof Error && err.message
        ? err.message
        : 'Erreur lors de la création de la demande';
      alert(message);
    } finally {
      setIsSaving(false);
    }
  };

  const openUpdate = (d: Demande) => {
    // Only Admin, Manager, Responsable Technique can update status (not Lecteur/clients)
    if (!user?.role || !['Admin', 'Manager', 'Responsable Technique'].includes(user.role)) return;
    setSelectedDemande(d);
    setUpdateForm({ statut: d.statut, technicien_assigne: d.technicien_assigne, notes_traitement: d.notes_traitement });
    setShowUpdateModal(true);
  };

  const handleUpdate = async () => {
    if (!selectedDemande) return;
    setIsSaving(true);
    try {
      await demandes.updateStatut(selectedDemande.id, updateForm as any);
      setShowUpdateModal(false);
      await loadData();
    } catch (err) {
      console.error(err);
      alert('Erreur lors de la mise à jour');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!canDelete || !deleteCandidate) return;
    setIsSaving(true);
    try {
      await demandes.delete(deleteCandidate.id);
      setDeleteCandidate(null);
      await loadData();
    } catch (err) {
      console.error(err);
      alert('Erreur lors de la suppression de la demande');
    } finally {
      setIsSaving(false);
    }
  };

  // KPI counters — 3 statuts seulement
  const nbAttente  = data.filter(d => d.statut === 'En attente').length;
  const nbAssignee = data.filter(d => d.statut === 'Assignée').length;
  const nbCloturee = data.filter(d => d.statut === 'Clôturée').length;

  const filtered = data.filter(d => {
    if (filterStatut !== 'Tous' && d.statut !== filterStatut) return false;
    if (search && !d.machine.toLowerCase().includes(search.toLowerCase()) &&
        !d.demandeur.toLowerCase().includes(search.toLowerCase()) &&
        !d.client.toLowerCase().includes(search.toLowerCase()) &&
        !String(d.id).includes(search)) return false;
    return true;
  });

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-savia-accent" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
            <ClipboardList className="w-7 h-7" /> Demandes d&apos;Intervention
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Suivi des demandes terrain</p>
        </div>
        <button
          onClick={openNewModal}
          disabled={!canCreate}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Plus className="w-4 h-4" /> Nouvelle demande
        </button>
      </div>

      {/* Lecteur info banner */}
      {isLecteur && (
        <div className="glass rounded-xl px-4 py-2.5 border border-savia-accent/20 flex items-center gap-2 text-sm text-savia-accent">
          <Building2 className="w-4 h-4" />
          Vos demandes sont liées au client : <strong>{clientNom}</strong>
        </div>
      )}

      {/* KPIs — 3 statuts */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiCard emphasis appearance="status-stripe" icon={<AlertTriangle className="h-5 w-5" />} value={String(nbAttente)} label="En attente" variant={nbAttente > 0 ? 'danger' : 'default'} />
        <KpiCard emphasis appearance="status-stripe" icon={<UserCheck className="h-5 w-5" />} value={String(nbAssignee)} label="Assignée" />
        <KpiCard emphasis appearance="status-stripe" icon={<Lock className="h-5 w-5" />} value={String(nbCloturee)} label="Clôturée" variant="success" />
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
          <input type="text" placeholder="Rechercher par machine, client, demandeur..." value={search} onChange={e => setSearch(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
        </div>
        <select value={filterStatut} onChange={e => setFilterStatut(e.target.value)}
          className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
          <option value="Tous">Tous les statuts</option>
          <option value="En attente">En attente</option>
          <option value="Assignée">Assignée</option>
          <option value="Clôturée">Clôturée</option>
        </select>
      </div>

      {/* List */}
      <div className="space-y-3">
        {filtered.length === 0 && (
          <div className="glass rounded-xl p-8 text-center text-savia-text-muted">
            <ClipboardList className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p>Aucune demande trouvée</p>
          </div>
        )}
        {filtered.map(d => (
          <div key={d.id} className="glass rounded-xl p-4 hover:border-savia-accent/30 transition-all">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="font-mono text-savia-accent font-bold text-sm">#{d.id}</span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${URGENCE_COLORS[d.priorite] || 'bg-gray-500/10 text-gray-400'}`}>
                  <Zap className="w-3 h-3 inline mr-1" />{d.priorite}
                </span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${STATUT_COLORS[d.statut] || 'bg-gray-500/10 text-gray-400'}`}>
                  {STATUT_ICONS[d.statut]}{d.statut}
                </span>
              </div>
              {user?.role && ['Admin', 'Manager', 'Responsable Technique'].includes(user.role) && (
                <button onClick={() => openUpdate(d)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-savia-accent/10 text-savia-accent hover:bg-savia-accent/20 transition-colors text-xs font-semibold cursor-pointer">
                  <Edit className="w-3.5 h-3.5" /> Mettre à jour
                </button>
              )}
              {canDelete && (
                <button onClick={() => setDeleteCandidate(d)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors text-xs font-semibold cursor-pointer">
                  <Trash2 className="w-3.5 h-3.5" /> Supprimer
                </button>
              )}
            </div>
            <p className="text-sm mb-3 text-savia-text">{d.description}</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-savia-text-muted">
              <span className="flex items-center gap-1"><Server className="w-3 h-3" />{d.machine || '—'}</span>
              <span className="flex items-center gap-1"><ClipboardList className="w-3 h-3" />{d.type_intervention}</span>
              <span className="flex items-center gap-1"><Building2 className="w-3 h-3" />{d.client || '—'}</span>
              <span className="flex items-center gap-1"><User className="w-3 h-3" />{d.demandeur || '—'}</span>
              <span className="flex items-center gap-1"><Clock className="w-3 h-3" />Demande : {formatDateTime(d.date)}</span>
              <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />Prévue : {d.date_planifiee ? formatDateOnly(d.date_planifiee) : '—'}</span>
            </div>
            {d.technicien_assigne && (
              <div className="mt-2 text-xs text-blue-400 flex items-center gap-1 flex-wrap">
                <UserCheck className="w-3 h-3" /> Technicien{d.technicien_assigne.includes(',') ? 's' : ''} :
                {d.technicien_assigne.split(',').map((t, i) => (
                  <span key={i} className="px-1.5 py-0.5 rounded bg-blue-500/10 border border-blue-500/20 font-semibold">{t.trim()}</span>
                ))}
              </div>
            )}
            {d.notes_traitement && (
              <div className="mt-1 text-xs text-savia-text-muted italic">{d.notes_traitement}</div>
            )}
          </div>
        ))}
      </div>

      {/* ========== MODAL: Nouvelle Demande ========== */}
      {showNewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
            <div className="flex items-center justify-between p-5 border-b border-savia-border">
              <h2 className="text-lg font-bold flex items-center gap-2">
                <Plus className="w-5 h-5 text-savia-accent" /> Nouvelle demande d&apos;intervention
                {isLecteur && <span className="ml-2 text-xs font-normal text-savia-accent bg-savia-accent/10 px-2 py-0.5 rounded-full">{clientNom}</span>}
                {billingSource && <span className="ml-2 text-xs font-normal text-blue-300 bg-blue-500/10 px-2 py-0.5 rounded-full">Dossier #{billingSource.id}</span>}
              </h2>
              <button onClick={closeNewModal} className="p-2 rounded-lg hover:bg-savia-surface-hover cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              {/* Urgence */}
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-yellow-400" /> Priorité de la demande *
                </label>
                <div className="flex gap-2 flex-wrap">
                  {['Basse', 'Moyenne', 'Haute', 'Critique'].map(u => (
                    <button key={u} onClick={() => setForm({...form, priorite: u})}
                      className={`px-4 py-2 rounded-lg text-sm font-semibold cursor-pointer transition-all ${form.priorite === u ? 'ring-2 ring-savia-accent bg-savia-accent/10' : 'bg-savia-bg/50 border border-savia-border hover:bg-savia-surface-hover'}`}>
                      {u}
                    </button>
                  ))}
                </div>
              </div>

              {/* Demandeur */}
              {canCreate && (
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <User className="w-3.5 h-3.5" /> Demandeur * (Pré-rempli avec votre nom)
                  </label>
                  <input className={INPUT_CLS} placeholder="Nom du demandeur" value={form.demandeur}
                    onChange={e => setForm({...form, demandeur: e.target.value})} 
                    disabled={isLecteur} />
                </div>
              )}

              {/* Client + Équipement */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Calendar className="w-3.5 h-3.5 text-savia-accent" /> Date prévue d&apos;intervention *
                  </label>
                  <input type="date" className={INPUT_CLS} value={form.date_planifiee}
                    min={todayIso()}
                    onChange={e => setForm({...form, date_planifiee: e.target.value})} />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <ClipboardList className="w-3.5 h-3.5 text-savia-accent" /> Type d&apos;intervention *
                  </label>
                  <select className={INPUT_CLS} value={form.type_intervention}
                    onChange={e => setForm({...form, type_intervention: e.target.value})}>
                    <option value="Corrective">Corrective</option>
                    <option value="Installation">Installation</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Building2 className="w-3.5 h-3.5" /> Client / Établissement
                  </label>
                  {isLecteur || billingSource ? (
                    <div className="px-4 py-2.5 rounded-lg bg-savia-bg/30 border border-savia-border text-savia-text-muted text-sm">{billingSource?.client || clientNom}</div>
                  ) : (
                    <select className={INPUT_CLS} value={form.client} onChange={e => {
                      setForm({ ...form, client: e.target.value, equipement: '' });
                      setSelectedEquipmentId('');
                    }}>
                      <option value="">— Sélectionner un client —</option>
                      {allClients.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Server className="w-3.5 h-3.5" /> Équipement concerné *
                    {equipsLoading && <Loader2 className="w-3 h-3 animate-spin text-savia-accent" />}
                  </label>
                  <select className={INPUT_CLS}
                    value={selectedEquipmentId || (billingSource?.equipment ? '__billing-equipment__' : '')}
                    onChange={e => {
                      const selectedId = e.target.value;
                      const selectedEquipment = filteredEquips.find(equipment => equipment.id === selectedId);
                      setSelectedEquipmentId(selectedId);
                      setForm({...form, equipement: selectedEquipment?.name || ''});
                    }}
                    disabled={Boolean(billingSource?.equipment) || (!isLecteur && !form.client) || equipsLoading}>
                    <option value="">
                      {equipsLoading ? 'Chargement...' : (!isLecteur && !form.client) ? "← Choisir un client d'abord" : '— Sélectionner un équipement —'}
                    </option>
                    {billingSource?.equipment && !filteredEquips.some(equipment => equipment.name === billingSource.equipment) && (
                      <option value="__billing-equipment__">{billingSource.equipment}</option>
                    )}
                    {filteredEquips.map(equipment => (
                      <option key={equipment.id} value={equipment.id}>{equipmentOptionLabel(equipment)}</option>
                    ))}
                  </select>
                  {!isLecteur && form.client && !equipsLoading && (
                    <p className="text-xs text-savia-text-muted mt-1 pl-1">
                      {filteredEquips.length} équipement{filteredEquips.length !== 1 ? 's' : ''} disponible{filteredEquips.length !== 1 ? 's' : ''}
                    </p>
                  )}
                </div>
              </div>

              {duplicateRequest && <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4"><div className="flex items-start gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-300" /><div className="flex-1"><div className="font-bold text-amber-200">Une demande active existe déjà</div><p className="mt-1 text-sm text-savia-text-muted">Demande #{duplicateRequest.id} · {duplicateRequest.statut}. Utilisez cette demande pour éviter de créer une seconde intervention pour le même équipement.</p>{duplicateRequest.billing_case_id && <button type="button" onClick={() => router.push(`/facturation?case_id=${duplicateRequest.billing_case_id}`)} className="mt-3 rounded-lg bg-amber-500 px-3 py-2 text-xs font-bold text-slate-950 hover:bg-amber-400">Ouvrir le dossier #{duplicateRequest.billing_case_id}</button>}</div></div></div>}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Tag className="w-3.5 h-3.5" /> Code erreur (facultatif)
                  </label>
                  <input className={INPUT_CLS} placeholder="Ex: E-301" value={form.code_erreur}
                    onChange={e => setForm({...form, code_erreur: e.target.value})} />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <User className="w-3.5 h-3.5" /> Personne à contacter
                  </label>
                  <input className={INPUT_CLS} placeholder="Nom du contact sur place" value={form.contact_nom}
                    onChange={e => setForm({...form, contact_nom: e.target.value})} />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Phone className="w-3.5 h-3.5" /> Téléphone contact
                  </label>
                  <input className={INPUT_CLS} placeholder="+216 XX XXX XXX" value={form.contact_tel}
                    onChange={e => setForm({...form, contact_tel: e.target.value})} />
                </div>
                {canAssignTech && (
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                      <Users className="w-3.5 h-3.5 text-blue-400" />
                      <span className="text-blue-400">Assigner des techniciens</span>
                      <span className="text-xs font-normal text-savia-text-muted">(facultatif, multi-sélection)</span>
                    </label>
                    {/* Selected techs chips */}
                    {form.technicien_assigne && (
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {form.technicien_assigne.split(',').filter(Boolean).map(t => (
                          <span key={t.trim()} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-500/15 border border-blue-500/30 text-blue-300 text-xs font-semibold">
                            <UserCheck className="w-3 h-3" /> {t.trim()}
                            <button type="button" onClick={() => {
                              const updated = form.technicien_assigne.split(',').map(s => s.trim()).filter(s => s !== t.trim()).join(', ');
                              setForm({...form, technicien_assigne: updated});
                            }} className="ml-0.5 hover:text-red-400 cursor-pointer"><X className="w-3 h-3" /></button>
                          </span>
                        ))}
                      </div>
                    )}
                    <select className={INPUT_CLS} value=""
                      onChange={e => {
                        if (!e.target.value) return;
                        const current = form.technicien_assigne ? form.technicien_assigne.split(',').map(s => s.trim()).filter(Boolean) : [];
                        if (!current.includes(e.target.value)) {
                          setForm({...form, technicien_assigne: [...current, e.target.value].join(', ')});
                        }
                      }}>
                      <option value="">— Ajouter un technicien —</option>
                      {techs.filter(t => !(form.technicien_assigne || '').split(',').map(s => s.trim()).includes(t)).map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <FileText className="w-3.5 h-3.5" /> Description du problème *
                </label>
                <textarea className={INPUT_CLS + ' resize-none'} rows={4}
                  placeholder="Décrivez le problème rencontré, les symptômes, depuis quand..."
                  value={form.description} onChange={e => setForm({...form, description: e.target.value})} />
              </div>
              <div>
                <label htmlFor="demande-note" className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <FileText className="w-3.5 h-3.5" /> Note (facultative)
                </label>
                <textarea id="demande-note" className={INPUT_CLS + ' resize-none'} rows={3}
                  value={form.notes_traitement} onChange={e => setForm({...form, notes_traitement: e.target.value})} />
              </div>
            </div>
            <div className="flex justify-end gap-3 p-5 border-t border-savia-border">
              <button onClick={closeNewModal}
                className="px-4 py-2 rounded-lg border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover cursor-pointer transition-colors">
                Annuler
              </button>
              <button onClick={handleCreate} disabled={isSaving || Boolean(duplicateRequest)}
                className="flex items-center gap-2 px-6 py-2 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 cursor-pointer transition-all">
                {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                Envoyer la demande
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========== MODAL: Mise à jour statut ========== */}
      {user?.role && ['Admin', 'Manager', 'Responsable Technique'].includes(user.role) && showUpdateModal && selectedDemande && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between p-5 border-b border-savia-border">
              <h2 className="text-lg font-bold flex items-center gap-2">
                <Edit className="w-5 h-5 text-blue-400" /> Mise à jour — #{selectedDemande.id}
              </h2>
              <button onClick={() => setShowUpdateModal(false)} className="p-2 rounded-lg hover:bg-savia-surface-hover cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">Statut</label>
                {/* 3 boutons visuels pour les 3 statuts */}
                <div className="grid grid-cols-3 gap-2">
                  {STATUTS.map(s => (
                    <button key={s} onClick={() => setUpdateForm({...updateForm, statut: s})}
                      className={`py-2.5 rounded-lg text-sm font-bold transition-all cursor-pointer border ${
                        updateForm.statut === s
                          ? s === 'En attente' ? 'bg-red-500/20 border-red-500/50 text-red-300'
                          : s === 'Assignée'   ? 'bg-blue-500/20 border-blue-500/50 text-blue-300'
                          :                      'bg-green-500/20 border-green-500/50 text-green-300'
                          : 'bg-savia-bg/50 border-savia-border text-savia-text-muted hover:bg-savia-surface-hover'
                      }`}>
                      {s === 'En attente' && <AlertTriangle className="w-4 h-4 inline mr-1 -mt-0.5" />}
                      {s === 'Assignée'   && <UserCheck    className="w-4 h-4 inline mr-1 -mt-0.5" />}
                      {s === 'Clôturée'   && <Lock         className="w-4 h-4 inline mr-1 -mt-0.5" />}
                      {s}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Users className="w-3.5 h-3.5 text-blue-400" /> Techniciens assignés
                </label>
                {/* Selected techs chips */}
                {updateForm.technicien_assigne && (
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {updateForm.technicien_assigne.split(',').filter(Boolean).map(t => (
                      <span key={t.trim()} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-blue-500/15 border border-blue-500/30 text-blue-300 text-xs font-semibold">
                        <UserCheck className="w-3 h-3" /> {t.trim()}
                        <button type="button" onClick={() => {
                          const updated = updateForm.technicien_assigne.split(',').map(s => s.trim()).filter(s => s !== t.trim()).join(', ');
                          setUpdateForm({...updateForm, technicien_assigne: updated});
                        }} className="ml-0.5 hover:text-red-400 cursor-pointer"><X className="w-3 h-3" /></button>
                      </span>
                    ))}
                  </div>
                )}
                <select className={INPUT_CLS} value=""
                  onChange={e => {
                    if (!e.target.value) return;
                    const current = updateForm.technicien_assigne ? updateForm.technicien_assigne.split(',').map(s => s.trim()).filter(Boolean) : [];
                    if (!current.includes(e.target.value)) {
                      setUpdateForm({...updateForm, technicien_assigne: [...current, e.target.value].join(', ')});
                    }
                  }}>
                  <option value="">— Ajouter un technicien —</option>
                  {techs.filter(t => !(updateForm.technicien_assigne || '').split(',').map(s => s.trim()).includes(t)).map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">Notes de traitement</label>
                <textarea className={INPUT_CLS + ' resize-none'} rows={3}
                  placeholder="Actions effectuées, remarques..."
                  value={updateForm.notes_traitement} onChange={e => setUpdateForm({...updateForm, notes_traitement: e.target.value})} />
              </div>
            </div>
            <div className="flex justify-end gap-3 p-5 border-t border-savia-border">
              <button onClick={() => setShowUpdateModal(false)}
                className="px-4 py-2 rounded-lg border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover cursor-pointer transition-colors">
                Annuler
              </button>
              <button onClick={handleUpdate} disabled={isSaving}
                className="flex items-center gap-2 px-6 py-2 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 cursor-pointer transition-all">
                {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                Enregistrer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========== MODAL: Confirmation suppression ========== */}
      {deleteCandidate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-savia-surface border border-red-500/30 rounded-2xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between p-5 border-b border-savia-border">
              <h2 className="text-lg font-bold flex items-center gap-2 text-red-400">
                <AlertTriangle className="w-5 h-5" /> Confirmer la suppression
              </h2>
              <button onClick={() => setDeleteCandidate(null)} className="p-2 rounded-lg hover:bg-savia-surface-hover cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-3">
              <p className="text-sm text-savia-text">
                Voulez-vous vraiment supprimer la demande <strong className="text-red-400">#{deleteCandidate.id}</strong> ?
              </p>
              <p className="text-xs text-savia-text-muted">Cette action est irréversible.</p>
            </div>
            <div className="flex justify-end gap-3 p-5 border-t border-savia-border">
              <button onClick={() => setDeleteCandidate(null)} disabled={isSaving}
                className="px-4 py-2 rounded-lg border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover cursor-pointer transition-colors disabled:opacity-50">
                Annuler
              </button>
              <button onClick={handleDelete} disabled={isSaving}
                className="flex items-center gap-2 px-5 py-2 rounded-lg font-bold text-white bg-red-600 hover:bg-red-500 disabled:opacity-50 cursor-pointer transition-colors">
                {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                Supprimer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
