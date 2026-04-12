'use client';
import { SectionCard } from '@/components/ui/cards';
import { FileText, Download, Eye } from 'lucide-react';

const DEMO_REPORTS = [
  { id: 'RPT-001', titre: 'Rapport Mensuel Mars 2025', type: 'Mensuel', date: '2025-03-31', client: 'Global', pages: 12, statut: 'Généré' },
  { id: 'RPT-002', titre: 'Diagnostic IA — Scanner CT-01', type: 'Diagnostic', date: '2025-03-15', client: 'Clinique El Manar', pages: 5, statut: 'Généré' },
  { id: 'RPT-003', titre: 'Conformité Q1 2025', type: 'Conformité', date: '2025-03-30', client: 'Global', pages: 8, statut: 'En cours' },
  { id: 'RPT-004', titre: 'Bilan Interventions Février', type: 'Mensuel', date: '2025-02-28', client: 'Global', pages: 15, statut: 'Généré' },
  { id: 'RPT-005', titre: 'Analyse Prédictive Parc', type: 'Prédictif', date: '2025-03-20', client: 'Hôpital Ch. Nicolle', pages: 7, statut: 'Généré' },
];

export default function ReportsPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-black gradient-text">📊 Rapports & Exports</h1>
        <p className="text-savia-text-muted text-sm mt-1">Génération de rapports PDF et exports de données</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-savia-accent">{DEMO_REPORTS.length}</div><div className="text-xs text-savia-text-muted mt-1">Total rapports</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-green-400">{DEMO_REPORTS.filter(r => r.statut === 'Généré').length}</div><div className="text-xs text-savia-text-muted mt-1">✅ Générés</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-yellow-400">{DEMO_REPORTS.filter(r => r.statut === 'En cours').length}</div><div className="text-xs text-savia-text-muted mt-1">🔄 En cours</div></div>
        <div className="glass rounded-xl p-4 text-center">
          <button className="w-full py-2 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer text-sm">
            + Générer rapport
          </button>
        </div>
      </div>

      <SectionCard title="📄 Rapports récents">
        <div className="space-y-3">
          {DEMO_REPORTS.map(r => (
            <div key={r.id} className="flex items-center gap-4 p-3 rounded-lg bg-savia-bg/50 hover:bg-savia-surface-hover/30 transition-colors cursor-pointer group">
              <div className="w-10 h-10 rounded-lg bg-savia-surface flex items-center justify-center"><FileText className="w-5 h-5 text-savia-accent" /></div>
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm">{r.titre}</div>
                <div className="text-xs text-savia-text-muted">{r.client} — {r.date} — {r.pages} pages</div>
              </div>
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${r.type === 'Mensuel' ? 'bg-blue-500/10 text-blue-400' : r.type === 'Diagnostic' ? 'bg-purple-500/10 text-purple-400' : r.type === 'Conformité' ? 'bg-green-500/10 text-green-400' : 'bg-yellow-500/10 text-yellow-400'}`}>{r.type}</span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${r.statut === 'Généré' ? 'bg-green-500/10 text-green-400' : 'bg-yellow-500/10 text-yellow-400'}`}>{r.statut}</span>
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 cursor-pointer"><Eye className="w-3.5 h-3.5" /></button>
                <button className="p-1.5 rounded-lg bg-green-500/10 text-green-400 hover:bg-green-500/20 cursor-pointer"><Download className="w-3.5 h-3.5" /></button>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
