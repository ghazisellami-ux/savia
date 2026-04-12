'use client';
import { SectionCard } from '@/components/ui/cards';
import { CheckCircle, XCircle, AlertTriangle, Clock } from 'lucide-react';

const CONFORMITE_DATA = [
  { machine: 'Scanner CT-01', client: 'Clinique El Manar', dernierControle: '2024-11-15', prochainControle: '2025-05-15', statut: 'Conforme', score: 95, items: [{ label: 'Dosimétrie', ok: true }, { label: 'Sécurité électrique', ok: true }, { label: 'Radioprotection', ok: true }, { label: 'CQ image', ok: false }] },
  { machine: 'IRM Siemens 3T', client: 'Hôpital Charles Nicolle', dernierControle: '2024-10-20', prochainControle: '2025-04-20', statut: 'Conforme', score: 100, items: [{ label: 'Champ magnétique', ok: true }, { label: 'Sécurité électrique', ok: true }, { label: 'CQ image', ok: true }, { label: 'Niveau hélium', ok: true }] },
  { machine: 'Mammographe GE', client: 'Clinique El Manar', dernierControle: '2024-09-10', prochainControle: '2025-03-10', statut: 'Non conforme', score: 60, items: [{ label: 'Compression', ok: false }, { label: 'Dosimétrie', ok: true }, { label: 'CQ image', ok: false }, { label: 'Sécurité', ok: true }] },
  { machine: 'Radio DR-200', client: 'Centre Imagerie Lac', dernierControle: '2025-01-05', prochainControle: '2025-07-05', statut: 'Conforme', score: 88, items: [{ label: 'Dosimétrie', ok: true }, { label: 'CQ image', ok: true }, { label: 'Sécurité', ok: true }, { label: 'Firmware', ok: false }] },
];

export default function ConformitePage() {
  const conformes = CONFORMITE_DATA.filter(c => c.statut === 'Conforme').length;
  const nonConformes = CONFORMITE_DATA.filter(c => c.statut === 'Non conforme').length;
  const avgScore = Math.round(CONFORMITE_DATA.reduce((a, b) => a + b.score, 0) / CONFORMITE_DATA.length);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-black gradient-text">✅ Conformité Réglementaire</h1>
        <p className="text-savia-text-muted text-sm mt-1">Suivi des contrôles qualité et conformité</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-savia-accent">{CONFORMITE_DATA.length}</div><div className="text-xs text-savia-text-muted mt-1">Équipements suivis</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-green-400">{conformes}</div><div className="text-xs text-savia-text-muted mt-1">✅ Conformes</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-red-400">{nonConformes}</div><div className="text-xs text-savia-text-muted mt-1">❌ Non conformes</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className={`text-3xl font-black ${avgScore >= 80 ? 'text-green-400' : 'text-yellow-400'}`}>{avgScore}%</div><div className="text-xs text-savia-text-muted mt-1">Score moyen</div></div>
      </div>

      <div className="space-y-4">
        {CONFORMITE_DATA.map(c => (
          <div key={c.machine} className={`glass rounded-xl p-5 border-l-4 ${c.statut === 'Conforme' ? 'border-l-green-500' : 'border-l-red-500'}`}>
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-bold text-lg">{c.machine}</h3>
                <p className="text-savia-text-muted text-sm">🏢 {c.client}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-2xl font-black ${c.score >= 80 ? 'text-green-400' : c.score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>{c.score}%</span>
                {c.statut === 'Conforme' ? <CheckCircle className="w-5 h-5 text-green-400" /> : <XCircle className="w-5 h-5 text-red-400" />}
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
              {c.items.map(item => (
                <div key={item.label} className={`rounded-lg p-2 text-center text-xs font-semibold ${item.ok ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                  {item.ok ? '✅' : '❌'} {item.label}
                </div>
              ))}
            </div>
            <div className="flex gap-4 text-xs text-savia-text-muted">
              <span>📅 Dernier: {c.dernierControle}</span>
              <span>⏭️ Prochain: {c.prochainControle}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
