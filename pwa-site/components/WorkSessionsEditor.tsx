'use client';
import { CalendarDays, Car, Clock, Plus, Trash2 } from 'lucide-react';
import TimeScrollPicker from './TimeScrollPicker';

export type WorkSessionDraft = { entry_uuid: string; work_date: string; start_time: string; end_time: string; travel_minutes: number };
type Props = { sessions: WorkSessionDraft[]; onChange: (sessions: WorkSessionDraft[]) => void; disabled?: boolean };
const newId = () => typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
export const newWorkSession = (workDate: string): WorkSessionDraft => ({ entry_uuid: newId(), work_date: workDate, start_time: '08:00', end_time: '09:00', travel_minutes: 0 });
export const sessionDuration = (session: WorkSessionDraft) => { const [sh, sm] = session.start_time.split(':').map(Number); const [eh, em] = session.end_time.split(':').map(Number); let value = eh * 60 + em - sh * 60 - sm; if (value <= 0) value += 1440; return value };
const timeMinutes = (value: string) => { const [hour, minute] = value.split(':').map(Number); return hour * 60 + minute };
const formatMinutes = (value: number) => `${String(Math.floor((value % 1440) / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
const nextDate = (value: string) => { const date = new Date(`${value}T12:00:00`); date.setDate(date.getDate() + 1); const pad = (part: number) => String(part).padStart(2, '0'); return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` };
export const validateSessionDrafts = (sessions: WorkSessionDraft[]): string => {
  if (!sessions.length) return 'Ajoutez au moins un créneau de travail.';
  if (sessions.some(session => !session.work_date)) return 'Renseignez la date de chaque créneau.';
  const intervals = sessions.map(session => {
    const start = new Date(`${session.work_date}T${session.start_time}:00`);
    const end = new Date(start.getTime() + sessionDuration(session) * 60000);
    return { start, end };
  });
  for (let first = 0; first < intervals.length; first += 1) {
    for (let second = first + 1; second < intervals.length; second += 1) {
      if (intervals[first].start < intervals[second].end && intervals[first].end > intervals[second].start) return 'Deux créneaux de travail se chevauchent.';
    }
  }
  return '';
};

export default function WorkSessionsEditor({ sessions, onChange, disabled = false }: Props) {
  const update = (index: number, patch: Partial<WorkSessionDraft>) => onChange(sessions.map((session, current) => current === index ? { ...session, ...patch } : session));
  const total = sessions.reduce((sum, session) => sum + sessionDuration(session), 0);
  return <div>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 12 }}>
      <div><div style={{ fontSize: '.85rem', fontWeight: 800, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '.5px' }}><Clock size={16} style={{ verticalAlign: '-3px', marginRight: 6 }} />Temps de travail</div><div style={{ marginTop: 3, fontSize: '.74rem', color: 'var(--text-muted)' }}>Total : {(total / 60).toFixed(2)} h</div></div>
      <button type="button" disabled={disabled} onClick={() => onChange([...sessions, newWorkSession(sessions.length ? nextDate(sessions.at(-1)!.work_date) : new Date().toISOString().slice(0, 10))])} style={{ border: 0, borderRadius: 9, padding: '9px 11px', background: 'var(--teal)', color: '#fff', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 5 }}><Plus size={16} /> Ajouter un créneau</button>
    </div>
    <div style={{ display: 'grid', gap: 12 }}>{sessions.map((session, index) => <div key={session.entry_uuid} style={{ padding: 12, border: '1px solid var(--border)', borderRadius: 12, background: 'rgba(86,124,141,.035)' }}>
      <div style={{ display: 'flex', alignItems: 'end', gap: 8, marginBottom: 10 }}>
        <label style={{ flex: 1, fontSize: '.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}><span style={{ display: 'block', marginBottom: 6 }}><CalendarDays size={14} style={{ verticalAlign: '-2px', marginRight: 4 }} />Date</span><input type="date" disabled={disabled} value={session.work_date} onChange={event => update(index, { work_date: event.target.value })} style={{ width: '100%', minHeight: 44, padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 10, background: '#fff', font: 'inherit' }} /></label>
        {sessions.length > 1 && <button type="button" disabled={disabled} aria-label="Supprimer ce créneau" onClick={() => onChange(sessions.filter((_, current) => current !== index))} style={{ width: 44, height: 44, border: '1px solid rgba(239,68,68,.25)', borderRadius: 10, background: 'rgba(239,68,68,.08)', color: '#dc2626' }}><Trash2 size={18} /></button>}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}><TimeScrollPicker label="Début" value={session.start_time} defaultValue="08:00" disabled={disabled} onChange={value => update(index, { start_time: value, end_time: formatMinutes(timeMinutes(value) + sessionDuration(session)) })} /><TimeScrollPicker label="Fin" value={session.end_time} defaultValue="09:00" disabled={disabled} onChange={value => update(index, { end_time: value })} /></div>
      <label style={{ display: 'block', marginTop: 10, fontSize: '.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}><span style={{ display: 'block', marginBottom: 6 }}><Car size={14} style={{ verticalAlign: '-2px', marginRight: 4 }} />Déplacement (heures)</span><input type="number" min={0} step={0.25} disabled={disabled} value={session.travel_minutes ? session.travel_minutes / 60 : 0} onChange={event => update(index, { travel_minutes: Math.round((Number(event.target.value) || 0) * 60) })} style={{ width: '100%', minHeight: 44, padding: '8px 10px', border: '1px solid var(--border)', borderRadius: 10, background: '#fff', font: 'inherit' }} /></label>
      <div style={{ marginTop: 8, textAlign: 'right', fontSize: '.75rem', fontWeight: 700, color: 'var(--teal)' }}>Durée : {(sessionDuration(session) / 60).toFixed(2)} h</div>
    </div>)}</div>
  </div>;
}
