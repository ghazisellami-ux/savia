'use client';
import { useState } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Plus, Search, FileText, AlertTriangle } from 'lucide-react';

const DEMO_CONTRATS = [
  { id: 'CTR-001', client: 'Clinique El Manar', type: 'Full Omnium', debut: '2024-01-01', fin: '2025-12-31', machines: 3, montant: 45000, statut: 'Actif' },
  { id: 'CTR-002', client: 'Hôpital Charles Nicolle', type: 'Pièces & MO', debut: '2024-06-01', fin: '2025-05-31', machines: 4, montant: 78000, statut: 'Actif' },
  { id: 'CTR-003', client: 'Centre Imagerie Lac', type: 'Maintenance Préventive', debut: '2024-03-15', fin: '2025-03-14', machines: 2, montant: 18000, statut: 'Expiration proche' },
  { id: 'CTR-004', client: 'Polyclinique Ennasr', type: 'Full Omnium', debut: '2023-09-01', fin: '2025-08-31', machines: 1, montant: 12000, statut: 'Actif' },
  { id: 'CTR-005', client: 'Clinique Les Oliviers', type: 'Pièces uniquement', debut: '2023-01-01', fin: '2024-12-31', machines: 2, montant: 8500, statut: 'Expiré' },
];

export default function ContratsPage() {
  const [search, setSearch] = useState('');
  const filtered = DEMO_CONTRATS.filter(c => !search || c.client.toLowerCase().includes(search.toLowerCase()) || c.id.toLowerCase().includes(search.toLowerCase()));
  const actifs = DEMO_CONTRATS.filter(c => c.statut === 'Actif').length;
  const totalRevenu = DEMO_CONTRATS.reduce((a, b) => a + b.montant, 0);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text">📄 Contrats de Maintenance</h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion des contrats SAV</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
          <Plus className="w-4 h-4" /> Nouveau contrat
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total contrats', value: DEMO_CONTRATS.length, color: 'text-savia-accent' },
          { label: 'Actifs', value: actifs, color: 'text-green-400' },
          { label: 'Expirations proches', value: DEMO_CONTRATS.filter(c => c.statut === 'Expiration proche').length, color: 'text-yellow-400' },
          { label: 'Revenu annuel', value: `${(totalRevenu/1000).toFixed(0)}K€`, color: 'text-savia-accent' },
        ].map(k => (
          <div key={k.label} className="glass rounded-xl p-4 text-center">
            <div className={`text-3xl font-black ${k.color}`}>{k.value}</div>
            <div className="text-xs text-savia-text-muted mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
        <input type="text" placeholder="Rechercher..." value={search} onChange={e => setSearch(e.target.value)} className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
      </div>

      <div className="space-y-3">
        {filtered.map(c => (
          <div key={c.id} className="glass rounded-xl p-4 hover:border-savia-accent/30 transition-all cursor-pointer">
            <div className="flex items-start justify-between mb-2">
              <div>
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-savia-accent" />
                  <span className="font-mono text-savia-accent font-bold">{c.id}</span>
                  <span className="font-semibold">{c.client}</span>
                </div>
                <p className="text-sm text-savia-text-muted mt-1">{c.type} — {c.machines} machine(s)</p>
              </div>
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${c.statut === 'Actif' ? 'bg-green-500/10 text-green-400' : c.statut === 'Expiration proche' ? 'bg-yellow-500/10 text-yellow-400' : 'bg-red-500/10 text-red-400'}`}>
                {c.statut}
              </span>
            </div>
            <div className="flex gap-4 text-xs text-savia-text-muted">
              <span>📅 {c.debut} → {c.fin}</span>
              <span>💰 {c.montant.toLocaleString()}€/an</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
