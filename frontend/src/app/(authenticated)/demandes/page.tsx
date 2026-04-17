'use client';
import { useState, useEffect, useCallback } from 'react';
import {
  Plus, Search, Clock, CheckCircle, AlertTriangle, X,
  Loader2, ClipboardList, User, Phone, Building2, Server,
  Zap, FileText, Tag, Edit, Send, UserCheck
} from 'lucide-react';
import { demandes, equipements, techniciens as techApi, clients as clientsApi } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

interface Demande {
  id: number;
  date: string;
  machine: string;
  client: string;
  demandeur: string;
  urgence: string;
  statut: string;
  description: string;
  code_erreur: string;
  contact_nom: string;
  contact_tel: string;
  technicien_assigne: string;
  notes_traitement: string;
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
  'En cours': 'bg-yellow-500/10 text-yellow-400',
  'Assignée': 'bg-blue-500/10 text-blue-400',
  'Résolue': 'bg-green-500/10 text-green-400',
  'Clôturée': 'bg-gray-500/10 text-gray-400',
};

export default function DemandesPage() {
  const { user } = useAuth();
  const isLecteur = user?.role === 'Lecteur';
  // Manager et Responsable Technique peuvent assigner un technicien à la création
  const canAssignTech = user?.role === 'Manager' || user?.role === 'Responsable Technique' || user?.role === 'Admin';
  const clientNom = user?.client || '';
  const demandeurNom = user?.nom || '';

  const emptyForm = {
    demandeur: isLecteur ? demandeurNom : '',
    client: isLecteur ? clientNom : '',
    equipement: '',
    urgence: 'Moyenne',
    description: '',
    code_erreur: '',
    contact_nom: isLecteur ? demandeurNom : '',
    contact_tel: '',
    technicien_assigne: '',
  };

  const [search, setSearch] = useState('');
  const [filterStatut, setFilterStatut] = useState('Tous');
  const [data, setData] = useState<Demande[]>([]);

  // All clients list (for Admin/Manager/Resp. Tech.)
  const [allClients, setAllClients] = useState<string[]>([]);
  // Equipments for the selected client (loaded on client change via API)
  const [filteredEquips, setFilteredEquips] = useState<string[]>([]);
  const [equipsLoading, setEquipsLoading] = useState(false);
  const [techs, setTechs] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // New demande modal
  const [showNewModal, setShowNewModal] = useState(false);
  const [form, setForm] = useState({ ...emptyForm });

  // Update statut modal
  const [showUpdateModal, setShowUpdateModal] = useState(false);
  const [selectedDemande, setSelectedDemande] = useState<Demande | null>(null);
  const [updateForm, setUpdateForm] = useState({ statut: '', technicien_assigne: '', notes_traitement: '' });

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [res, eqRes, techRes, clientRes] = await Promise.all([
        demandes.list(),
        // For Lecteur: pre-load their client's equipment
        isLecteur ? equipements.list(clientNom) : equipements.list(),
        techApi.list().catch(() => []),
        clientsApi.list().catch(() => []),
      ]);
      const mapped = (res as any[]).map((item: any) => ({
        id: Number(item.id || 0),
        date: item.date_demande ? String(item.date_demande).substring(0, 10) : (item.date || 'N/A'),
        machine: item.equipement || item.machine || '',
        client: item.client || '',
        demandeur: item.demandeur || '',
        urgence: item.urgence || 'Moyenne',
        statut: item.statut || 'En attente',
        description: item.description || '',
        code_erreur: item.code_erreur || '',
        contact_nom: item.contact_nom || '',
        contact_tel: item.contact_tel || '',
        technicien_assigne: item.technicien_assigne || '',
        notes_traitement: item.notes_traitement || '',
      }));
      setData(mapped);

      // For Lecteur: set their pre-filtered equipment list
      if (isLecteur) {
        const lecteurEquips = (eqRes as any[]).map((e: any) => e.Nom || e.nom || '').filter(Boolean);
        setFilteredEquips(lecteurEquips);
      }

      // Parse clients list (for non-Lecteur dropdowns)
      const clientNames = (clientRes as any[])
        .map((c: any) => c.nom || c.Nom || c.name || '')
        .filter(Boolean)
        .sort();
      setAllClients(clientNames);

      // Parse technicians
      setTechs((techRes as any[]).map((t: any) => `${t.prenom || ''} ${t.nom || ''}`.trim()).filter(Boolean));
    } catch (err) {
      console.error('Failed to fetch demandes', err);
    } finally {
      setIsLoading(false);
    }
  }, [isLecteur, clientNom]);

  useEffect(() => { loadData(); }, [loadData]);

  // When selected client changes (non-Lecteur): load equipment from API for that client
  useEffect(() => {
    if (isLecteur || !form.client) {
      if (!isLecteur) setFilteredEquips([]);
      return;
    }
    setEquipsLoading(true);
    equipements.list(form.client)
      .then((res: any[]) => {
        setFilteredEquips(res.map((e: any) => e.Nom || e.nom || '').filter(Boolean));
      })
      .catch(() => setFilteredEquips([]))
      .finally(() => setEquipsLoading(false));
  }, [form.client, isLecteur]);

  const openNewModal = () => {
    setForm({ ...emptyForm });
    setShowNewModal(true);
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
    setIsSaving(true);
    try {
      await demandes.create(formToSend as any);
      setShowNewModal(false);
      await loadData();
    } catch (err) {
      console.error(err);
      alert('Erreur lors de la création de la demande');
    } finally {
      setIsSaving(false);
    }
  };

  const openUpdate = (d: Demande) => {
    if (isLecteur) return;
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

  const enAttente = data.filter(d => d.statut === 'En attente').length;
  const enCours = data.filter(d => d.statut === 'En cours' || d.statut === 'Assignée').length;
  const resolues = data.filter(d => d.statut === 'Résolue' || d.statut === 'Clôturée').length;

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
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer shadow-lg"
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

      {/* KPIs */}
      <div className="grid grid-cols-3 gap-4">
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2"><AlertTriangle className="w-5 h-5 text-red-400" /></div>
          <div className="text-3xl font-black text-red-400">{enAttente}</div>
          <div className="text-xs text-savia-text-muted mt-1">En attente</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2"><Clock className="w-5 h-5 text-yellow-400" /></div>
          <div className="text-3xl font-black text-yellow-400">{enCours}</div>
          <div className="text-xs text-savia-text-muted mt-1">En cours / Assignée</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2"><CheckCircle className="w-5 h-5 text-green-400" /></div>
          <div className="text-3xl font-black text-green-400">{resolues}</div>
          <div className="text-xs text-savia-text-muted mt-1">Résolues</div>
        </div>
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
          <option value="En cours">En cours</option>
          <option value="Assignée">Assignée</option>
          <option value="Résolue">Résolue</option>
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
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${URGENCE_COLORS[d.urgence] || 'bg-gray-500/10 text-gray-400'}`}>
                  <Zap className="w-3 h-3 inline mr-1" />{d.urgence}
                </span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${STATUT_COLORS[d.statut] || 'bg-gray-500/10 text-gray-400'}`}>
                  {d.statut}
                </span>
              </div>
              {!isLecteur && (
                <button onClick={() => openUpdate(d)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-savia-accent/10 text-savia-accent hover:bg-savia-accent/20 transition-colors text-xs font-semibold cursor-pointer">
                  <Edit className="w-3.5 h-3.5" /> Mettre à jour
                </button>
              )}
            </div>
            <p className="text-sm mb-3 text-savia-text">{d.description}</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs text-savia-text-muted">
              <span className="flex items-center gap-1"><Server className="w-3 h-3" />{d.machine || '—'}</span>
              <span className="flex items-center gap-1"><Building2 className="w-3 h-3" />{d.client || '—'}</span>
              <span className="flex items-center gap-1"><User className="w-3 h-3" />{d.demandeur || '—'}</span>
              <span className="flex items-center gap-1"><Tag className="w-3 h-3" />{d.date}</span>
            </div>
            {d.technicien_assigne && (
              <div className="mt-2 text-xs text-blue-400 flex items-center gap-1">
                <UserCheck className="w-3 h-3" /> Technicien : <strong>{d.technicien_assigne}</strong>
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
              </h2>
              <button onClick={() => setShowNewModal(false)} className="p-2 rounded-lg hover:bg-savia-surface-hover cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              {/* Urgence */}
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Zap className="w-3.5 h-3.5 text-yellow-400" /> Niveau d&apos;urgence *
                </label>
                <div className="flex gap-2 flex-wrap">
                  {['Basse', 'Moyenne', 'Haute', 'Critique'].map(u => (
                    <button key={u} onClick={() => setForm({...form, urgence: u})}
                      className={`px-4 py-2 rounded-lg text-sm font-semibold cursor-pointer transition-all ${form.urgence === u ? 'ring-2 ring-savia-accent bg-savia-accent/10' : 'bg-savia-bg/50 border border-savia-border hover:bg-savia-surface-hover'}`}>
                      {u}
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Demandeur — visible seulement pour non-Lecteur */}
                {!isLecteur && (
                  <div>
                    <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                      <User className="w-3.5 h-3.5" /> Demandeur *
                    </label>
                    <input className={INPUT_CLS} placeholder="Nom du demandeur" value={form.demandeur}
                      onChange={e => setForm({...form, demandeur: e.target.value})} />
                  </div>
                )}

                {/* Client — verrouillé pour Lecteur, liste déroulante pour les autres */}
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Building2 className="w-3.5 h-3.5" /> Client / Établissement
                    {isLecteur && <span className="text-xs text-savia-accent font-normal ml-1">🔒 {clientNom}</span>}
                  </label>
                  {isLecteur ? (
                    <div className="px-4 py-2.5 rounded-lg bg-savia-bg/30 border border-savia-border text-savia-text-muted text-sm">
                      {clientNom}
                    </div>
                  ) : (
                    <select
                      className={INPUT_CLS}
                      value={form.client}
                      onChange={e => setForm({ ...form, client: e.target.value, equipement: '' })}
                    >
                      <option value="">— Sélectionner un client —</option>
                      {allClients.map(c => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  )}
                </div>

                {/* Équipement — liste filtrée selon le client choisi */}
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Server className="w-3.5 h-3.5" /> Équipement concerné *
                    {equipsLoading && <Loader2 className="w-3 h-3 animate-spin text-savia-accent" />}
                  </label>
                  <select
                    className={INPUT_CLS}
                    value={form.equipement}
                    onChange={e => setForm({...form, equipement: e.target.value})}
                    disabled={(!isLecteur && !form.client) || equipsLoading}
                  >
                    <option value="">
                      {equipsLoading
                        ? 'Chargement...'
                        : (!isLecteur && !form.client)
                          ? '← Choisir un client d\'abord'
                          : '— Sélectionner un équipement —'}
                    </option>
                    {filteredEquips.map(e => (
                      <option key={e} value={e}>{e}</option>
                    ))}
                  </select>
                  {!isLecteur && form.client && !equipsLoading && (
                    <p className="text-xs text-savia-text-muted mt-1 pl-1">
                      {filteredEquips.length} équipement{filteredEquips.length !== 1 ? 's' : ''} disponible{filteredEquips.length !== 1 ? 's' : ''}
                    </p>
                  )}
                </div>

                {/* Code erreur */}
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Tag className="w-3.5 h-3.5" /> Code erreur (facultatif)
                  </label>
                  <input className={INPUT_CLS} placeholder="Ex: E-301" value={form.code_erreur}
                    onChange={e => setForm({...form, code_erreur: e.target.value})} />
                </div>

                {/* Contact nom */}
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <User className="w-3.5 h-3.5" /> Personne à contacter
                  </label>
                  <input className={INPUT_CLS} placeholder="Nom du contact sur place" value={form.contact_nom}
                    onChange={e => setForm({...form, contact_nom: e.target.value})} />
                </div>

                {/* Contact tel */}
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Phone className="w-3.5 h-3.5" /> Téléphone contact
                  </label>
                  <input className={INPUT_CLS} placeholder="+216 XX XXX XXX" value={form.contact_tel}
                    onChange={e => setForm({...form, contact_tel: e.target.value})} />
                </div>

                {/* Technicien assigné — visble uniquement pour Manager / Responsable Technique / Admin */}
                {canAssignTech && (
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                      <UserCheck className="w-3.5 h-3.5 text-blue-400" />
                      <span className="text-blue-400">Assigner un technicien</span>
                      <span className="text-xs font-normal text-savia-text-muted">(facultatif)</span>
                    </label>
                    <select
                      className={INPUT_CLS}
                      value={form.technicien_assigne}
                      onChange={e => setForm({...form, technicien_assigne: e.target.value})}
                    >
                      <option value="">— Non assigné pour l&apos;instant —</option>
                      {techs.map(t => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {/* Description */}
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <FileText className="w-3.5 h-3.5" /> Description du problème *
                </label>
                <textarea className={INPUT_CLS + ' resize-none'} rows={4}
                  placeholder="Décrivez le problème rencontré, les symptômes, depuis quand..."
                  value={form.description} onChange={e => setForm({...form, description: e.target.value})} />
              </div>
            </div>

            <div className="flex justify-end gap-3 p-5 border-t border-savia-border">
              <button onClick={() => setShowNewModal(false)}
                className="px-4 py-2 rounded-lg border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover cursor-pointer transition-colors">
                Annuler
              </button>
              <button onClick={handleCreate} disabled={isSaving}
                className="flex items-center gap-2 px-6 py-2 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 cursor-pointer transition-all">
                {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                Envoyer la demande
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========== MODAL: Mise à jour statut (non-Lecteur) ========== */}
      {!isLecteur && showUpdateModal && selectedDemande && (
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
                <select className={INPUT_CLS} value={updateForm.statut} onChange={e => setUpdateForm({...updateForm, statut: e.target.value})}>
                  <option value="En attente">En attente</option>
                  <option value="Assignée">Assignée</option>
                  <option value="En cours">En cours</option>
                  <option value="Résolue">Résolue</option>
                  <option value="Clôturée">Clôturée</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <UserCheck className="w-3.5 h-3.5 text-blue-400" /> Technicien assigné
                </label>
                <select className={INPUT_CLS} value={updateForm.technicien_assigne}
                  onChange={e => setUpdateForm({...updateForm, technicien_assigne: e.target.value})}>
                  <option value="">— Non assigné —</option>
                  {techs.map(t => <option key={t} value={t}>{t}</option>)}
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
    </div>
  );
}
