'use client';
import { useState, useEffect, useMemo, useCallback } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Modal } from '@/components/ui/modal';
import { Plus, ChevronLeft, ChevronRight, Loader2, Save, AlertTriangle, Calendar, Clock } from 'lucide-react';
import { planning, equipements } from '@/lib/api';

const INPUT_CLS = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all";
const MONTHS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];
const DAYS_SHORT = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const EVENT_COLORS = [
  'bg-green-500/20 border-green-500 text-green-300',
  'bg-red-500/20 border-red-500 text-red-300',
  'bg-blue-500/20 border-blue-500 text-blue-300',
  'bg-purple-500/20 border-purple-500 text-purple-300',
  'bg-cyan-500/20 border-cyan-500 text-cyan-300',
  'bg-yellow-500/20 border-yellow-500 text-yellow-300',
  'bg-pink-500/20 border-pink-500 text-pink-300',
  'bg-orange-500/20 border-orange-500 text-orange-300',
];

interface PlanItem {
  id: number;
  date_planifiee: string;
  machine: string;
  description: string;
  technicien: string;
  statut: string;
  type_maintenance: string;
  duree_minutes: number;
  client: string;
}

export default function PlanningPage() {
  const now = new Date();
  const [currentMonth, setCurrentMonth] = useState(now.getMonth());
  const [currentYear, setCurrentYear] = useState(now.getFullYear());
  const [data, setData] = useState<PlanItem[]>([]);
  const [equips, setEquips] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const emptyForm = { date_planifiee: '', machine: '', description: '', technicien: '', type_maintenance: 'Préventive', duree_minutes: '120' };
  const [form, setForm] = useState(emptyForm);

  const loadData = useCallback(async () => {
    try {
      const [planRes, eqRes] = await Promise.all([planning.list(), equipements.list()]);
      const mapped = planRes.map((item: any) => ({
        id: item.id || 0,
        date_planifiee: item.date_planifiee || item.Date || '',
        machine: item.machine || item.Machine || '',
        description: item.description || item.Description || '',
        technicien: item.technicien || item.Technicien || 'Non assigné',
        statut: item.statut || item.Statut || 'Planifiée',
        type_maintenance: item.type_maintenance || item.Type || 'Préventive',
        duree_minutes: item.duree_minutes || 120,
        client: item.client || '',
      }));
      setData(mapped);
      setEquips(eqRes);
    } catch (err) { console.error("Failed to fetch planning", err); }
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Machine color mapping for calendar
  const machineColors = useMemo(() => {
    const map: Record<string, string> = {};
    const uniqueMachines = [...new Set(data.map(d => d.machine))];
    uniqueMachines.forEach((m, i) => { map[m] = EVENT_COLORS[i % EVENT_COLORS.length]; });
    return map;
  }, [data]);

  // Calendar grid calculation
  const calendarDays = useMemo(() => {
    const firstDay = new Date(currentYear, currentMonth, 1);
    const lastDay = new Date(currentYear, currentMonth + 1, 0);
    const startDow = (firstDay.getDay() + 6) % 7; // Mon=0
    const totalDays = lastDay.getDate();

    const days: {day: number, inMonth: boolean, date: string}[] = [];

    // Previous month padding
    const prevLastDay = new Date(currentYear, currentMonth, 0).getDate();
    for (let i = startDow - 1; i >= 0; i--) {
      const d = prevLastDay - i;
      const m = currentMonth === 0 ? 12 : currentMonth;
      const y = currentMonth === 0 ? currentYear - 1 : currentYear;
      days.push({ day: d, inMonth: false, date: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}` });
    }

    // Current month
    for (let d = 1; d <= totalDays; d++) {
      const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      days.push({ day: d, inMonth: true, date: dateStr });
    }

    // Next month padding (fill to 42 cells = 6 rows)
    const remaining = 42 - days.length;
    for (let d = 1; d <= remaining; d++) {
      const m = currentMonth === 11 ? 1 : currentMonth + 2;
      const y = currentMonth === 11 ? currentYear + 1 : currentYear;
      days.push({ day: d, inMonth: false, date: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}` });
    }

    return days;
  }, [currentMonth, currentYear]);

  // Events for a given date
  const eventsForDate = useCallback((dateStr: string) => {
    return data.filter(d => {
      const planDate = (d.date_planifiee || '').substring(0, 10);
      return planDate === dateStr;
    });
  }, [data]);

  // Stats
  const monthEvents = data.filter(d => {
    const dt = new Date(d.date_planifiee);
    return dt.getMonth() === currentMonth && dt.getFullYear() === currentYear;
  });

  const overdueCount = data.filter(d => {
    const dt = new Date(d.date_planifiee);
    return dt < now && d.statut !== 'Réalisée' && d.statut !== 'Annulée';
  }).length;

  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

  const handleSave = async () => {
    if (!form.machine.trim()) return;
    setIsSaving(true);
    try {
      // TODO: call planning.create when API available
      // For now, just close the modal
      setShowAddModal(false);
      setForm(emptyForm);
    } catch (err) { console.error(err); }
    finally { setIsSaving(false); }
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
          <h1 className="text-2xl font-black gradient-text">📅 Planning Maintenance</h1>
          <p className="text-savia-text-muted text-sm mt-1">Planification et suivi des maintenances préventives</p>
        </div>
        <button onClick={() => {
          setForm({...emptyForm, date_planifiee: todayStr});
          setShowAddModal(true);
        }} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-savia-text bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
          <Plus className="w-4 h-4" /> Planifier une maintenance
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 text-center">
          <div className="text-3xl font-black text-savia-accent">{data.length}</div>
          <div className="text-xs text-savia-text-muted mt-1">📅 Total planifié</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="text-3xl font-black text-blue-400">{monthEvents.length}</div>
          <div className="text-xs text-savia-text-muted mt-1">📊 Ce mois</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="text-3xl font-black text-green-400">{data.filter(d => d.statut === 'Réalisée').length}</div>
          <div className="text-xs text-savia-text-muted mt-1">✅ Réalisées</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className={`text-3xl font-black ${overdueCount > 0 ? 'text-red-400' : 'text-green-400'}`}>{overdueCount}</div>
          <div className="text-xs text-savia-text-muted mt-1">⚠️ En retard</div>
        </div>
      </div>

      {/* Overdue alert */}
      {overdueCount > 0 && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-4 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <span className="text-red-400 font-bold">🚨 {overdueCount} maintenance(s) en retard !</span>
          <span className="text-xs text-savia-text-muted">Des maintenances planifiées n&apos;ont pas encore été réalisées.</span>
        </div>
      )}

      {/* Calendar */}
      <SectionCard title="">
        {/* Month navigation */}
        <div className="flex items-center justify-between mb-6">
          <button onClick={prevMonth} className="flex items-center gap-1 px-3 py-2 rounded-lg bg-savia-surface-hover hover:bg-savia-border text-savia-text transition-colors cursor-pointer">
            <ChevronLeft className="w-4 h-4" /> Précédent
          </button>
          <h2 className="text-xl font-black gradient-text">
            {MONTHS[currentMonth]} {currentYear}
          </h2>
          <button onClick={nextMonth} className="flex items-center gap-1 px-3 py-2 rounded-lg bg-savia-surface-hover hover:bg-savia-border text-savia-text transition-colors cursor-pointer">
            Suivant <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        {/* Day headers */}
        <div className="grid grid-cols-7 gap-1 mb-2">
          {DAYS_SHORT.map(d => (
            <div key={d} className="text-center text-xs font-bold text-savia-text-muted py-2">{d}</div>
          ))}
        </div>

        {/* Calendar grid */}
        <div className="grid grid-cols-7 gap-1">
          {calendarDays.map((cell, i) => {
            const events = eventsForDate(cell.date);
            const isToday = cell.date === todayStr;
            const isPast = new Date(cell.date) < now && !isToday;

            return (
              <div key={i}
                onClick={() => {
                  if (cell.inMonth) {
                    setSelectedDay(cell.day);
                    setForm({...emptyForm, date_planifiee: cell.date});
                  }
                }}
                className={`min-h-[80px] rounded-lg p-1 border transition-all cursor-pointer ${
                  !cell.inMonth ? 'opacity-30 border-transparent' :
                  isToday ? 'border-cyan-400 bg-cyan-400/5' :
                  selectedDay === cell.day ? 'border-blue-400 bg-blue-400/5' :
                  'border-savia-border/30 hover:border-savia-border hover:bg-savia-surface-hover/30'
                }`}
              >
                <div className={`text-xs font-bold mb-1 ${isToday ? 'text-cyan-400' : cell.inMonth ? 'text-savia-text' : 'text-slate-600'}`}>
                  {cell.day}
                </div>
                <div className="space-y-0.5">
                  {events.slice(0, 3).map((ev, j) => {
                    const colorCls = machineColors[ev.machine] || EVENT_COLORS[0];
                    const isOverdue = isPast && ev.statut !== 'Réalisée';
                    return (
                      <div key={j} className={`text-[10px] leading-tight px-1 py-0.5 rounded border-l-2 truncate ${isOverdue ? 'bg-red-500/20 border-red-500 text-red-300' : colorCls}`} title={`${ev.machine} — ${ev.technicien}`}>
                        {ev.machine.substring(0, 15)}
                      </div>
                    );
                  })}
                  {events.length > 3 && (
                    <div className="text-[10px] text-savia-text-dim px-1">+{events.length - 3}</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </SectionCard>

      {/* Selected day events */}
      {selectedDay !== null && (() => {
        const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(selectedDay).padStart(2, '0')}`;
        const dayEvents = eventsForDate(dateStr);
        return dayEvents.length > 0 ? (
          <SectionCard title={`📋 ${selectedDay} ${MONTHS[currentMonth]} — ${dayEvents.length} maintenance(s)`}>
            <div className="space-y-3">
              {dayEvents.map(ev => {
                const isOverdue = new Date(ev.date_planifiee) < now && ev.statut !== 'Réalisée';
                return (
                  <div key={ev.id} className={`glass rounded-xl p-4 border ${isOverdue ? 'border-red-500/30' : 'border-savia-border/30'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <div className="font-bold">{ev.machine}</div>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                        ev.statut === 'Réalisée' ? 'bg-green-500/10 text-green-400' :
                        isOverdue ? 'bg-red-500/10 text-red-400' :
                        'bg-blue-500/10 text-blue-400'
                      }`}>
                        {isOverdue ? '⚠️ En retard' : ev.statut}
                      </span>
                    </div>
                    <div className="text-sm text-savia-text-muted space-y-1">
                      <div>👤 {ev.technicien}</div>
                      <div>📝 {ev.description || 'Maintenance préventive'}</div>
                      <div>⏱️ {Math.round(ev.duree_minutes / 60)}h — {ev.type_maintenance}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </SectionCard>
        ) : null;
      })()}

      {/* Legend */}
      <SectionCard title="🎨 Légende — Machines">
        <div className="flex flex-wrap gap-2">
          {Object.entries(machineColors).map(([machine, color]) => (
            <span key={machine} className={`px-3 py-1 rounded-full text-xs font-semibold border-l-2 ${color}`}>
              {machine}
            </span>
          ))}
        </div>
      </SectionCard>

      {/* Upcoming list */}
      <SectionCard title="📋 Prochaines Maintenances">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-savia-border">
                {['Date', 'Machine', 'Technicien', 'Type', 'Durée', 'Statut'].map(h => (
                  <th key={h} className="text-left py-2 px-3 text-savia-text-muted">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.sort((a, b) => a.date_planifiee.localeCompare(b.date_planifiee)).slice(0, 20).map(ev => {
                const isOverdue = new Date(ev.date_planifiee) < now && ev.statut !== 'Réalisée';
                return (
                  <tr key={ev.id} className={`border-b border-savia-border/50 hover:bg-savia-surface-hover/50 ${isOverdue ? 'bg-red-500/5' : ''}`}>
                    <td className="py-2 px-3 text-xs">{ev.date_planifiee.substring(0, 10)}</td>
                    <td className="py-2 px-3 font-semibold">{ev.machine}</td>
                    <td className="py-2 px-3">{ev.technicien}</td>
                    <td className="py-2 px-3 text-xs">{ev.type_maintenance}</td>
                    <td className="py-2 px-3 font-mono text-xs">{Math.round(ev.duree_minutes / 60)}h</td>
                    <td className="py-2 px-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                        ev.statut === 'Réalisée' ? 'bg-green-500/10 text-green-400' :
                        isOverdue ? 'bg-red-500/10 text-red-400' :
                        'bg-blue-500/10 text-blue-400'
                      }`}>{isOverdue ? '⚠️ Retard' : ev.statut}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </SectionCard>

      {/* Add Modal */}
      <Modal isOpen={showAddModal} onClose={() => setShowAddModal(false)} title="📅 Planifier une Maintenance" size="lg">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><label className="block text-sm text-savia-text-muted mb-1">Date</label><input type="date" className={INPUT_CLS} value={form.date_planifiee} onChange={e => setForm({...form, date_planifiee: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Machine *</label><input className={INPUT_CLS} placeholder="Ex: Scanner CT-01" value={form.machine} onChange={e => setForm({...form, machine: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Technicien</label><input className={INPUT_CLS} placeholder="Ex: Ahmed" value={form.technicien} onChange={e => setForm({...form, technicien: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Type</label>
            <select className={INPUT_CLS} value={form.type_maintenance} onChange={e => setForm({...form, type_maintenance: e.target.value})}>
              <option>Préventive</option><option>Corrective</option><option>Calibration</option><option>Inspection</option>
            </select></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Durée estimée (min)</label><input type="number" className={INPUT_CLS} value={form.duree_minutes} onChange={e => setForm({...form, duree_minutes: e.target.value})} /></div>
          <div className="md:col-span-2"><label className="block text-sm text-savia-text-muted mb-1">Description</label><textarea className={INPUT_CLS + " h-20 resize-none"} placeholder="Détails de la maintenance..." value={form.description} onChange={e => setForm({...form, description: e.target.value})} /></div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-white/5">
          <button onClick={() => setShowAddModal(false)} className="px-4 py-2 rounded-lg text-savia-text-muted hover:text-savia-text cursor-pointer">Annuler</button>
          <button onClick={handleSave} disabled={isSaving} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-savia-text bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-90 disabled:opacity-50 cursor-pointer">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Planifier
          </button>
        </div>
      </Modal>
    </div>
  );
}
