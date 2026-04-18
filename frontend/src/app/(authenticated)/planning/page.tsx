'use client';
import { useState, useEffect, useMemo, useCallback } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Modal } from '@/components/ui/modal';
import {
  Plus, ChevronLeft, ChevronRight, Loader2, Save, AlertTriangle,
  Calendar, Building2, Server, User, RefreshCw, FileText, StickyNote,
  Wrench, CheckCircle, Trash2, X
} from 'lucide-react';
import { planning, equipements, clients as clientsApi, techniciens as techApi } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

const INPUT_CLS = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all";
const MONTHS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];
const DAYS_SHORT = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const STATUT_COLORS: Record<string, { cell: string; badge: string; dot: string }> = {
  'Planifiée':  { cell: 'bg-blue-500/20 border-blue-500 text-blue-300',    badge: 'bg-blue-500/15 text-blue-400',    dot: 'bg-blue-400' },
  'En cours':   { cell: 'bg-yellow-500/20 border-yellow-500 text-yellow-300', badge: 'bg-yellow-500/15 text-yellow-400', dot: 'bg-yellow-400' },
  'Terminée':   { cell: 'bg-green-500/20 border-green-500 text-green-300',  badge: 'bg-green-500/15 text-green-400',  dot: 'bg-green-400' },
  'Réalisée':   { cell: 'bg-green-500/20 border-green-500 text-green-300',  badge: 'bg-green-500/15 text-green-400',  dot: 'bg-green-400' },
  'En retard':  { cell: 'bg-red-500/20 border-red-500 text-red-300',        badge: 'bg-red-500/15 text-red-400',      dot: 'bg-red-400' },
};
const getStatutColor = (statut: string, isOverdue: boolean) => {
  if (isOverdue) return STATUT_COLORS['En retard'];
  return STATUT_COLORS[statut] || { cell: 'bg-blue-500/20 border-blue-500 text-blue-300', badge: 'bg-blue-500/15 text-blue-400', dot: 'bg-blue-400' };
};
const RECURRENCES = ['Aucune', 'Hebdomadaire', 'Mensuelle', 'Trimestrielle', 'Semestrielle', 'Annuelle'];
const TYPES_MAINTENANCE = ['Préventive', 'Corrective', 'Calibration', 'Inspection', 'Qualification', 'Mise à jour logiciel'];

interface PlanItem {
  id: number;
  date_planifiee: string;
  machine: string;
  client: string;
  description: string;
  technicien: string;
  statut: string;
  type_maintenance: string;
  recurrence: string;
  notes: string;
}

const emptyForm = {
  client: '',
  machine: '',
  type_maintenance: 'Préventive',
  recurrence: 'Aucune',
  date_planifiee: '',
  technicien_assigne: '',
  description: '',
  notes: '',
};

export default function PlanningPage() {
  const { user } = useAuth();
  const isLecteur = user?.role === 'Lecteur';
  const now = new Date();
  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

  const [currentMonth, setCurrentMonth] = useState(now.getMonth());
  const [currentYear, setCurrentYear] = useState(now.getFullYear());
  const [data, setData] = useState<PlanItem[]>([]);
  const [clientsList, setClientsList] = useState<string[]>([]);
  const [equipsAll, setEquipsAll] = useState<{nom: string; client: string}[]>([]);
  const [techsList, setTechsList] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState('');
  // Day-detail popup
  const [dayDetailDate, setDayDetailDate] = useState<string | null>(null);
  const [dayDetailEvents, setDayDetailEvents] = useState<PlanItem[]>([]);

  // Equipements filtered by selected client
  const filteredEquips = useMemo(() => {
    if (!form.client) return equipsAll.map(e => e.nom);
    return equipsAll.filter(e => e.client === form.client).map(e => e.nom);
  }, [equipsAll, form.client]);

  const loadData = useCallback(async () => {
    try {
      const [planRes, eqRes, clRes, techRes] = await Promise.all([
        planning.list(),
        equipements.list().catch(() => []),
        clientsApi.list().catch(() => []),
        techApi.list().catch(() => []),
      ]);

      const mapped = (planRes as any[]).map((item: any) => ({
        id: item.id || 0,
        // La colonne BD s'appelle date_prevue, pas date_planifiee
        date_planifiee: item.date_prevue || item.date_planifiee || item.Date || '',
        machine: item.machine || '',
        client: item.client || '',
        description: item.description || '',
        technicien: item.technicien_assigne || item.technicien || '',
        statut: item.statut || 'Planifiée',
        type_maintenance: item.type_maintenance || 'Préventive',
        recurrence: item.recurrence || 'Aucune',
        notes: item.notes || '',
      }));
      setData(mapped);

      const equipsFlat = (eqRes as any[]).map((e: any) => ({
        nom: e.Nom || e.nom || '',
        client: e.Client || e.client || '',
      })).filter(e => e.nom);
      setEquipsAll(equipsFlat);

      const uniqueClients = [...new Set([
        ...(clRes as any[]).map((c: any) => c.nom || c.Nom || c.client || c.Client || ''),
        ...equipsFlat.map(e => e.client),
      ])].filter(Boolean).sort();
      setClientsList(uniqueClients);

      const techNames = (techRes as any[]).map((t: any) =>
        `${t.prenom || ''} ${t.nom || ''}`.trim()
      ).filter(Boolean);
      setTechsList(techNames);
    } catch (err) {
      console.error('Failed to fetch planning', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);


  // Calendar grid
  const calendarDays = useMemo(() => {
    const firstDay = new Date(currentYear, currentMonth, 1);
    const lastDay = new Date(currentYear, currentMonth + 1, 0);
    const startDow = (firstDay.getDay() + 6) % 7;
    const days: { day: number; inMonth: boolean; date: string }[] = [];

    const prevLastDay = new Date(currentYear, currentMonth, 0).getDate();
    for (let i = startDow - 1; i >= 0; i--) {
      const d = prevLastDay - i;
      const m = currentMonth === 0 ? 12 : currentMonth;
      const y = currentMonth === 0 ? currentYear - 1 : currentYear;
      days.push({ day: d, inMonth: false, date: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}` });
    }
    for (let d = 1; d <= lastDay.getDate(); d++) {
      days.push({ day: d, inMonth: true, date: `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}` });
    }
    const remaining = 42 - days.length;
    for (let d = 1; d <= remaining; d++) {
      const m = currentMonth === 11 ? 1 : currentMonth + 2;
      const y = currentMonth === 11 ? currentYear + 1 : currentYear;
      days.push({ day: d, inMonth: false, date: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}` });
    }
    return days;
  }, [currentMonth, currentYear]);

  const eventsForDate = useCallback((dateStr: string) =>
    data.filter(d => (d.date_planifiee || '').substring(0, 10) === dateStr),
  [data]);

  const monthEvents = data.filter(d => {
    const dt = new Date(d.date_planifiee);
    return dt.getMonth() === currentMonth && dt.getFullYear() === currentYear;
  });
  const overdueCount = data.filter(d => {
    const dt = new Date(d.date_planifiee);
    return dt < now && d.statut !== 'Réalisée' && d.statut !== 'Annulée';
  }).length;

  const handleSave = async () => {
    setError('');
    if (!form.machine.trim()) { setError('Veuillez sélectionner un équipement.'); return; }
    if (!form.date_planifiee) { setError('Veuillez choisir une date prévue.'); return; }
    setIsSaving(true);
    try {
      await planning.create({
        machine: form.machine,
        client: form.client,
        type_maintenance: form.type_maintenance,
        recurrence: form.recurrence,
        date_prevue: form.date_planifiee,
        technicien_assigne: form.technicien_assigne,
        description: form.description,
        notes: form.notes,
        statut: 'Planifiée',
      } as any);
      setShowAddModal(false);
      setForm(emptyForm);
      await loadData();
    } catch (err) {
      console.error(err);
      setError('Erreur lors de la création. Veuillez réessayer.');
    } finally {
      setIsSaving(false);
    }
  };

  const prevMonth = () => {
    if (currentMonth === 0) { setCurrentMonth(11); setCurrentYear(y => y - 1); }
    else setCurrentMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (currentMonth === 11) { setCurrentMonth(0); setCurrentYear(y => y + 1); }
    else setCurrentMonth(m => m + 1);
  };

  if (isLoading) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
            <Calendar className="w-7 h-7" /> Planning Maintenance
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Planification et suivi des maintenances préventives</p>
        </div>
        {!isLecteur && (
        <button onClick={() => { setForm({...emptyForm, date_planifiee: todayStr}); setError(''); setShowAddModal(true); }}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer shadow-lg">
          <Plus className="w-4 h-4" /> Planifier une maintenance
        </button>
        )}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total planifié', value: data.length, color: 'text-savia-accent', icon: <Calendar className="w-5 h-5" /> },
          { label: 'Ce mois', value: monthEvents.length, color: 'text-blue-400', icon: <Calendar className="w-5 h-5" /> },
          { label: 'Réalisées', value: data.filter(d => d.statut === 'Réalisée').length, color: 'text-green-400', icon: <CheckCircle className="w-5 h-5" /> },
          { label: 'En retard', value: overdueCount, color: overdueCount > 0 ? 'text-red-400' : 'text-green-400', icon: <AlertTriangle className="w-5 h-5" /> },
        ].map(kpi => (
          <div key={kpi.label} className="glass rounded-xl p-4 text-center">
            <div className={`flex justify-center mb-2 ${kpi.color}`}>{kpi.icon}</div>
            <div className={`text-3xl font-black ${kpi.color}`}>{kpi.value}</div>
            <div className="text-xs text-savia-text-muted mt-1">{kpi.label}</div>
          </div>
        ))}
      </div>

      {overdueCount > 0 && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-4 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <span className="text-red-400 font-bold">{overdueCount} maintenance(s) en retard !</span>
          <span className="text-xs text-savia-text-muted">Des maintenances planifiées n&apos;ont pas encore été réalisées.</span>
        </div>
      )}

      {/* Calendar */}
      <SectionCard title="">
        <div className="flex items-center justify-between mb-6">
          <button onClick={prevMonth} className="flex items-center gap-1 px-3 py-2 rounded-lg bg-savia-surface-hover hover:bg-savia-border text-savia-text transition-colors cursor-pointer">
            <ChevronLeft className="w-4 h-4" /> Précédent
          </button>
          <h2 className="text-xl font-black gradient-text">{MONTHS[currentMonth]} {currentYear}</h2>
          <button onClick={nextMonth} className="flex items-center gap-1 px-3 py-2 rounded-lg bg-savia-surface-hover hover:bg-savia-border text-savia-text transition-colors cursor-pointer">
            Suivant <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        <div className="grid grid-cols-7 gap-1 mb-2">
          {DAYS_SHORT.map(d => <div key={d} className="text-center text-xs font-bold text-savia-text-muted py-2">{d}</div>)}
        </div>

        <div className="grid grid-cols-7 gap-1">
          {calendarDays.map((cell, i) => {
            const events = eventsForDate(cell.date);
            const isToday = cell.date === todayStr;
            const isPast = new Date(cell.date) < now && !isToday;
            return (
              <div key={i}
                onClick={() => {
                  if (!cell.inMonth) return;
                  const evs = eventsForDate(cell.date);
                  if (evs.length > 0) {
                    // Ouvrir la popup détails
                    setDayDetailDate(cell.date);
                    setDayDetailEvents(evs);
                  } else {
                    // Ouvrir la modale ajout
                    setSelectedDay(cell.day);
                    setForm({...emptyForm, date_planifiee: cell.date});
                    setError('');
                    setShowAddModal(true);
                  }
                }}
                className={`min-h-[80px] rounded-lg p-1 border transition-all cursor-pointer ${
                  !cell.inMonth ? 'opacity-30 border-transparent' :
                  isToday ? 'border-cyan-400 bg-cyan-400/5' :
                  selectedDay === cell.day ? 'border-blue-400 bg-blue-400/5' :
                  'border-savia-border/30 hover:border-savia-border hover:bg-savia-surface-hover/30'
                }`}
              >
                <div className={`text-xs font-bold mb-1 ${isToday ? 'text-cyan-400' : cell.inMonth ? 'text-savia-text' : 'text-slate-600'}`}>{cell.day}</div>
                <div className="space-y-0.5">
                  {events.slice(0, 3).map((ev, j) => {
                    const isOverdue = isPast && ev.statut !== 'Réalisée' && ev.statut !== 'Terminée' && ev.statut !== 'Annulée';
                    const colors = getStatutColor(ev.statut, isOverdue);
                    return (
                      <div key={j} className={`text-[10px] leading-tight px-1 py-0.5 rounded border-l-2 truncate ${colors.cell}`}
                        title={`[${isOverdue ? 'En retard' : ev.statut}] ${ev.machine} — ${ev.technicien}`}>
                        {ev.machine.substring(0, 14)}
                      </div>
                    );
                  })}
                  {events.length > 3 && <div className="text-[10px] text-savia-text-dim px-1">+{events.length - 3}</div>}
                </div>
              </div>
            );
          })}
        </div>
      </SectionCard>

      {/* Status Legend */}
      <div className="glass rounded-xl px-5 py-3 flex flex-wrap items-center gap-4">
        <span className="text-xs font-bold text-savia-text-muted uppercase tracking-wider">Légende :</span>
        {[
          { label: 'Planifiée',  dot: 'bg-blue-400',   text: 'text-blue-400'   },
          { label: 'En cours',   dot: 'bg-yellow-400', text: 'text-yellow-400' },
          { label: 'Terminée',   dot: 'bg-green-400',  text: 'text-green-400'  },
          { label: 'En retard',  dot: 'bg-red-400',    text: 'text-red-400'    },
        ].map(s => (
          <div key={s.label} className="flex items-center gap-2">
            <span className={`w-3 h-3 rounded-sm border-l-2 ${s.dot} opacity-80`} />
            <span className={`text-xs font-semibold ${s.text}`}>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Upcoming list */}
      <SectionCard title={`Toutes les Maintenances (${data.length})`}>
        <div className="overflow-x-auto">
          <div className="overflow-y-auto" style={{maxHeight: '420px'}}>
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-savia-surface z-10">
                <tr className="border-b border-savia-border">
                  {['Date prévue', 'Client', 'Équipement', 'Technicien', 'Type', 'Récurrence', 'Statut'].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data
                  .slice()
                  .sort((a, b) => {
                    // Items avec date en premier, triés chronologiquement
                    if (!a.date_planifiee && !b.date_planifiee) return 0;
                    if (!a.date_planifiee) return 1;
                    if (!b.date_planifiee) return -1;
                    return a.date_planifiee.localeCompare(b.date_planifiee);
                  })
                  .map(ev => {
                    const hasDate = !!ev.date_planifiee;
                    const isOverdue = hasDate && new Date(ev.date_planifiee) < now && ev.statut !== 'Réalisée' && ev.statut !== 'Terminée' && ev.statut !== 'Annulée';
                    const colors = getStatutColor(ev.statut, isOverdue);
                    return (
                      <tr key={ev.id} className={`border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors ${isOverdue ? 'bg-red-500/5' : ''}`}>
                        <td className="py-2 px-3 text-xs font-mono whitespace-nowrap">
                          {hasDate ? ev.date_planifiee.substring(0, 10) : <span className="text-savia-text-dim italic">Sans date</span>}
                        </td>
                        <td className="py-2 px-3 text-xs text-savia-text-muted">{ev.client || '—'}</td>
                        <td className="py-2 px-3 font-semibold text-sm">{ev.machine}</td>
                        <td className="py-2 px-3 text-xs">{ev.technicien || '—'}</td>
                        <td className="py-2 px-3 text-xs whitespace-nowrap">{ev.type_maintenance}</td>
                        <td className="py-2 px-3 text-xs text-savia-text-muted">{ev.recurrence && ev.recurrence !== 'Aucune' ? ev.recurrence : '—'}</td>
                        <td className="py-2 px-3">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${colors.badge}`}>
                            {isOverdue ? 'En retard' : ev.statut}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      </SectionCard>

      {/* ADD MODAL */}
      <Modal isOpen={showAddModal} onClose={() => { setShowAddModal(false); setSelectedDay(null); }} title={`Planifier une Maintenance${selectedDay ? ` — ${String(selectedDay).padStart(2,'0')}/${String(currentMonth+1).padStart(2,'0')}/${currentYear}` : ''}`}>
        <div className="space-y-5">

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-red-400 text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
            </div>
          )}

          {/* Client + Type */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                <Building2 className="w-3.5 h-3.5 text-savia-accent" /> Client *
              </label>
              <select className={INPUT_CLS} value={form.client}
                onChange={e => setForm({...form, client: e.target.value, machine: ''})}>
                <option value="">— Sélectionner un client —</option>
                {clientsList.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                <Wrench className="w-3.5 h-3.5 text-savia-accent" /> Type de maintenance *
              </label>
              <select className={INPUT_CLS} value={form.type_maintenance}
                onChange={e => setForm({...form, type_maintenance: e.target.value})}>
                {TYPES_MAINTENANCE.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>

          {/* Équipement (filtré par client) */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
              <Server className="w-3.5 h-3.5 text-savia-accent" /> Équipement *
              {form.client && <span className="text-savia-text-dim font-normal normal-case text-[11px]">({filteredEquips.length} disponible{filteredEquips.length > 1 ? 's' : ''})</span>}
            </label>
            <select className={INPUT_CLS} value={form.machine}
              onChange={e => setForm({...form, machine: e.target.value})}>
              <option value="">— Sélectionner un équipement —</option>
              {filteredEquips.map(e => <option key={e} value={e}>{e}</option>)}
              {filteredEquips.length === 0 && form.client && (
                <option disabled>Aucun équipement pour ce client</option>
              )}
            </select>
            {!form.client && (
              <p className="text-xs text-savia-text-dim mt-1">Sélectionnez d&apos;abord un client pour filtrer les équipements.</p>
            )}
          </div>

          {/* Date + Récurrence */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                <Calendar className="w-3.5 h-3.5 text-savia-accent" /> Date prévue *
              </label>
              <input type="date" className={INPUT_CLS} value={form.date_planifiee}
                onChange={e => setForm({...form, date_planifiee: e.target.value})} />
            </div>
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                <RefreshCw className="w-3.5 h-3.5 text-savia-accent" /> Récurrence
              </label>
              <select className={INPUT_CLS} value={form.recurrence}
                onChange={e => setForm({...form, recurrence: e.target.value})}>
                {RECURRENCES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          </div>

          {/* Technicien */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
              <User className="w-3.5 h-3.5 text-savia-accent" /> Technicien assigné
            </label>
            <select className={INPUT_CLS} value={form.technicien_assigne}
              onChange={e => setForm({...form, technicien_assigne: e.target.value})}>
              <option value="">— Non assigné —</option>
              {techsList.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
              <FileText className="w-3.5 h-3.5 text-savia-accent" /> Description
            </label>
            <textarea className={INPUT_CLS + ' resize-none'} rows={3}
              placeholder="Détails de la maintenance à effectuer..."
              value={form.description} onChange={e => setForm({...form, description: e.target.value})} />
          </div>

          {/* Notes */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
              <StickyNote className="w-3.5 h-3.5 text-savia-accent" /> Notes internes
            </label>
            <textarea className={INPUT_CLS + ' resize-none'} rows={2}
              placeholder="Notes internes, remarques, matériel nécessaire..."
              value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} />
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-savia-border/50">
          <button onClick={() => { setShowAddModal(false); setSelectedDay(null); }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover cursor-pointer transition-colors">
            <X className="w-4 h-4" /> Annuler
          </button>
          <button onClick={handleSave} disabled={isSaving}
            className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 cursor-pointer transition-all">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Planifier
          </button>
        </div>
      </Modal>

      {/* ═══════════ DAY DETAIL POPUP ═══════════ */}
      {dayDetailDate && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 backdrop-blur-sm overflow-y-auto py-10 px-4" onClick={() => setDayDetailDate(null)}>
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-lg shadow-2xl animate-fade-in" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-savia-border">
              <h2 className="text-base font-black gradient-text flex items-center gap-2">
                <Calendar className="w-5 h-5 text-savia-accent" />
                Maintenances — {dayDetailDate}
              </h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    const day = Number(dayDetailDate!.split('-')[2]);
                    setDayDetailDate(null);
                    setSelectedDay(day);
                    setForm({...emptyForm, date_planifiee: dayDetailDate!});
                    setError('');
                    setShowAddModal(true);
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-savia-accent hover:opacity-90 cursor-pointer transition-all"
                >
                  <Plus className="w-3.5 h-3.5" /> Ajouter
                </button>
                <button onClick={() => setDayDetailDate(null)} className="p-1.5 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted cursor-pointer">
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Events */}
            <div className="px-6 py-4 space-y-3 max-h-[70vh] overflow-y-auto">
              {dayDetailEvents.map((ev, i) => {
                const isPast = new Date(ev.date_planifiee) < now;
                const isOverdue = isPast && ev.statut !== 'Réalisée' && ev.statut !== 'Terminée' && ev.statut !== 'Annulée';
                const colors = getStatutColor(ev.statut, isOverdue);
                return (
                  <div key={i} className={`rounded-xl border border-savia-border border-l-4 p-4 space-y-2 bg-savia-surface-hover/40 ${colors.dot.replace('bg-', 'border-l-').replace('bg-savia', 'border-l-savia')}`}
                    style={{ borderLeftColor: colors.dot === 'bg-blue-400' ? '#60a5fa' : colors.dot === 'bg-yellow-400' ? '#facc15' : colors.dot === 'bg-green-400' ? '#4ade80' : '#f87171' }}>
                    {/* Machine + statut */}
                    <div className="flex items-start justify-between gap-2">
                      <span className="flex items-center gap-2 font-black text-sm text-savia-text">
                        <Server className="w-4 h-4 flex-shrink-0 text-savia-text-muted" /> {ev.machine}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold whitespace-nowrap ${colors.badge}`}>
                        {isOverdue ? 'En retard' : ev.statut}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-savia-text">
                      {ev.client && (
                        <div className="flex items-center gap-1.5">
                          <Building2 className="w-3.5 h-3.5 text-savia-text-muted" />
                          <span className="text-savia-text-muted">Client :</span>
                          <span className="font-semibold text-savia-text">{ev.client}</span>
                        </div>
                      )}
                      {ev.technicien && (
                        <div className="flex items-center gap-1.5">
                          <User className="w-3.5 h-3.5 text-savia-text-muted" />
                          <span className="text-savia-text-muted">Tech :</span>
                          <span className="font-semibold text-savia-text">{ev.technicien}</span>
                        </div>
                      )}
                      <div className="flex items-center gap-1.5">
                        <Wrench className="w-3.5 h-3.5 text-savia-text-muted" />
                        <span className="text-savia-text-muted">Type :</span>
                        <span className="font-semibold text-savia-text">{ev.type_maintenance}</span>
                      </div>
                      {ev.recurrence && ev.recurrence !== 'Aucune' && (
                        <div className="flex items-center gap-1.5">
                          <RefreshCw className="w-3.5 h-3.5 text-savia-text-muted" />
                          <span className="text-savia-text-muted">Récurrence :</span>
                          <span className="font-semibold text-savia-text">{ev.recurrence}</span>
                        </div>
                      )}
                    </div>

                    {ev.description && (
                      <div className="flex items-start gap-1.5 text-xs pt-1 border-t border-savia-border">
                        <FileText className="w-3.5 h-3.5 text-savia-text-muted flex-shrink-0 mt-0.5" />
                        <p className="text-savia-text">{ev.description}</p>
                      </div>
                    )}
                    {ev.notes && (
                      <div className="flex items-start gap-1.5 text-xs">
                        <StickyNote className="w-3.5 h-3.5 text-savia-text-muted flex-shrink-0 mt-0.5" />
                        <p className="italic text-savia-text-muted">{ev.notes}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
