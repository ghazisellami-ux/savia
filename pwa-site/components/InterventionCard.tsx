'use client';
import { useRouter } from 'next/navigation';

const STATUT_STYLES: Record<string, { bg: string; color: string }> = {
  'En cours':           { bg: 'rgba(86,124,141,0.12)',  color: 'var(--teal)'    },
  'En attente de piece':{ bg: 'rgba(245,158,11,0.12)',  color: '#B45309'        },
  'Cloturee':           { bg: 'rgba(34,197,94,0.12)',   color: '#15803D'        },
  'Assignée':           { bg: 'rgba(168,85,247,0.12)',  color: '#7C3AED'        },
};

interface InterventionCardProps {
  id: number;
  machine: string;
  client: string;
  statut: string;
  type: string;
  date: string;
  technicien?: string;
  priorite?: string;
  offline?: boolean;
}

export default function InterventionCard({ id, machine, client, statut, type, date, technicien, priorite, offline }: InterventionCardProps) {
  const router = useRouter();
  const s = STATUT_STYLES[statut] || { bg: 'rgba(47,65,86,0.08)', color: 'var(--navy)' };

  return (
    <div
      onClick={() => router.push(`/interventions/${id}`)}
      className="animate-fade-up"
      style={{
        background: '#fff', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
        padding: '16px', cursor: 'pointer', transition: 'border-color 0.2s, transform 0.15s',
        borderLeft: `4px solid ${s.color}`,
      }}
      onTouchStart={e => (e.currentTarget.style.transform = 'scale(0.98)')}
      onTouchEnd={e => (e.currentTarget.style.transform = 'scale(1)')}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
        <div>
          <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--navy)' }}>{machine}</span>
          {offline && (
            <span style={{ marginLeft: '6px', background: 'rgba(245,158,11,0.15)', color: '#B45309', fontSize: '0.65rem', fontWeight: 700, padding: '2px 6px', borderRadius: '4px' }}>OFFLINE</span>
          )}
        </div>
        <span style={{ ...s, fontSize: '0.7rem', fontWeight: 700, padding: '3px 10px', borderRadius: '20px', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
          {statut}
        </span>
      </div>

      {/* Infos */}
      <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', gap: '3px' }}>
        <span>🏢 {client}</span>
        {technicien && <span>👤 {technicien}</span>}
        <span>🔧 {type}</span>
        {priorite && priorite !== '' && (
          <span style={{ color: priorite === 'Haute' ? 'var(--danger)' : 'var(--warning)', fontWeight: 600 }}>
            🚨 Priorité {priorite}
          </span>
        )}
      </div>

      {/* Footer */}
      <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px solid var(--border)', fontSize: '0.75rem', color: 'var(--text-dim)' }}>
        📅 {date ? new Date(date).toLocaleDateString('fr-FR') : '—'}
        <span style={{ float: 'right', color: 'var(--teal)', fontWeight: 600 }}>Voir →</span>
      </div>
    </div>
  );
}
