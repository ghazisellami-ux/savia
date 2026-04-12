'use client';
import { useState } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Plus, Search, Clock, CheckCircle, AlertTriangle, Send } from 'lucide-react';

const DEMO_DEMANDES = [
  { id: 'DEM-001', date: '2025-03-18', machine: 'Scanner CT-01', client: 'Clinique El Manar', demandeur: 'Dr. Ben Ali', urgence: 'Haute', statut: 'En attente', description: 'Tube RX instable — acquisitions interrompues' },
  { id: 'DEM-002', date: '2025-03-17', machine: 'Mammographe GE', client: 'Clinique El Manar', demandeur: 'Mme Trabelsi', urgence: 'Haute', statut: 'Assignée', description: 'Paddle compression ne maintient pas la pression' },
  { id: 'DEM-003', date: '2025-03-16', machine: 'IRM Siemens 3T', client: 'Hôpital Charles Nicolle', demandeur: 'Dr. Khelifi', urgence: 'Moyenne', statut: 'En cours', description: 'Niveau hélium en baisse continue' },
  { id: 'DEM-004', date: '2025-03-15', machine: 'Arceau C-Arm', client: 'Hôpital Charles Nicolle', demandeur: 'Dr. Mansouri', urgence: 'Basse', statut: 'Résolue', description: 'Bruit anormal moteur rotation' },
  { id: 'DEM-005', date: '2025-03-14', machine: 'Radio DR-200', client: 'Centre Imagerie Lac', demandeur: 'M. Bouazizi', urgence: 'Basse', statut: 'Résolue', description: 'Demande mise à jour firmware' },
];

export default function DemandesPage() {
  const [search, setSearch] = useState('');
  const enAttente = DEMO_DEMANDES.filter(d => d.statut === 'En attente').length;
  const enCours = DEMO_DEMANDES.filter(d => d.statut === 'En cours' || d.statut === 'Assignée').length;

  const filtered = DEMO_DEMANDES.filter(d => !search || d.machine.toLowerCase().includes(search.toLowerCase()) || d.id.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text">📝 Demandes d&apos;Intervention</h1>
          <p className="text-savia-text-muted text-sm mt-1">Suivi des demandes terrain</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
          <Plus className="w-4 h-4" /> Nouvelle demande
        </button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-red-400">{enAttente}</div><div className="text-xs text-savia-text-muted mt-1">⏳ En attente</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-yellow-400">{enCours}</div><div className="text-xs text-savia-text-muted mt-1">🔄 En cours</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-green-400">{DEMO_DEMANDES.filter(d => d.statut === 'Résolue').length}</div><div className="text-xs text-savia-text-muted mt-1">✅ Résolues</div></div>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
        <input type="text" placeholder="Rechercher..." value={search} onChange={e => setSearch(e.target.value)} className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
      </div>

      <div className="space-y-3">
        {filtered.map(d => (
          <div key={d.id} className="glass rounded-xl p-4 hover:border-savia-accent/30 transition-all cursor-pointer">
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-3">
                <span className="font-mono text-savia-accent font-bold">{d.id}</span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${d.urgence === 'Haute' ? 'bg-red-500/10 text-red-400' : d.urgence === 'Moyenne' ? 'bg-yellow-500/10 text-yellow-400' : 'bg-green-500/10 text-green-400'}`}>
                  ⚡ {d.urgence}
                </span>
              </div>
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${d.statut === 'Résolue' ? 'bg-green-500/10 text-green-400' : d.statut === 'En attente' ? 'bg-red-500/10 text-red-400' : 'bg-yellow-500/10 text-yellow-400'}`}>
                {d.statut}
              </span>
            </div>
            <p className="text-sm mb-2">{d.description}</p>
            <div className="flex gap-4 text-xs text-savia-text-muted">
              <span>🏥 {d.machine}</span><span>🏢 {d.client}</span><span>👤 {d.demandeur}</span><span>📅 {d.date}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
