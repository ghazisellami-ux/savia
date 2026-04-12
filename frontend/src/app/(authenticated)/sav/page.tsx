'use client';
import { useState } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Plus, Search, Wrench, Clock, CheckCircle, AlertTriangle } from 'lucide-react';

interface Intervention {
  id: string;
  date: string;
  machine: string;
  client: string;
  type: 'Corrective' | 'Préventive' | 'Installation';
  technicien: string;
  duree: number;
  statut: 'Terminée' | 'En cours' | 'Planifiée';
  description: string;
  coutPieces: number;
}

const DEMO_INTERVENTIONS: Intervention[] = [
  { id: 'INT-001', date: '2025-03-15', machine: 'Scanner CT-01', client: 'Clinique El Manar', type: 'Corrective', technicien: 'Ahmed B.', duree: 4, statut: 'Terminée', description: 'Remplacement condensateur HV Generator', coutPieces: 1200 },
  { id: 'INT-002', date: '2025-03-12', machine: 'IRM Siemens 3T', client: 'Hôpital Charles Nicolle', type: 'Préventive', technicien: 'Mehdi S.', duree: 3, statut: 'Terminée', description: 'Vérification niveau hélium + calibration gradient', coutPieces: 0 },
  { id: 'INT-003', date: '2025-03-18', machine: 'Mammographe GE', client: 'Clinique El Manar', type: 'Corrective', technicien: 'Ahmed B.', duree: 5, statut: 'En cours', description: 'Remplacement paddle compression + calibration AEC', coutPieces: 2800 },
  { id: 'INT-004', date: '2025-03-20', machine: 'Radio DR-200', client: 'Centre Imagerie Lac', type: 'Préventive', technicien: 'Sami K.', duree: 2, statut: 'Planifiée', description: 'Mise à jour firmware v2.4.1 + calibration détecteur', coutPieces: 0 },
  { id: 'INT-005', date: '2025-03-10', machine: 'Arceau C-Arm', client: 'Hôpital Charles Nicolle', type: 'Corrective', technicien: 'Mehdi S.', duree: 6, statut: 'Terminée', description: 'Réparation moteur rotation bras + remplacement filtre huile', coutPieces: 950 },
  { id: 'INT-006', date: '2025-03-22', machine: 'Angiographe Biplan', client: 'Hôpital Charles Nicolle', type: 'Corrective', technicien: 'Ahmed B.', duree: 8, statut: 'Planifiée', description: 'Remplacement détecteur flat panel', coutPieces: 15000 },
];

export default function SavPage() {
  const [search, setSearch] = useState('');
  const [filterStatut, setFilterStatut] = useState('Tous');
  const [filterType, setFilterType] = useState('Tous');

  const filtered = DEMO_INTERVENTIONS.filter(i => {
    if (filterStatut !== 'Tous' && i.statut !== filterStatut) return false;
    if (filterType !== 'Tous' && i.type !== filterType) return false;
    if (search && !i.machine.toLowerCase().includes(search.toLowerCase()) && !i.id.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const totalInterv = DEMO_INTERVENTIONS.length;
  const terminees = DEMO_INTERVENTIONS.filter(i => i.statut === 'Terminée').length;
  const enCours = DEMO_INTERVENTIONS.filter(i => i.statut === 'En cours').length;
  const totalCout = DEMO_INTERVENTIONS.reduce((a, b) => a + b.coutPieces, 0);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text">🔧 SAV & Interventions</h1>
          <p className="text-savia-text-muted text-sm mt-1">Suivi des interventions techniques</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
          <Plus className="w-4 h-4" /> Nouvelle intervention
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total', value: totalInterv, icon: <Wrench className="w-4 h-4" />, color: 'text-savia-accent' },
          { label: 'Terminées', value: terminees, icon: <CheckCircle className="w-4 h-4" />, color: 'text-green-400' },
          { label: 'En cours', value: enCours, icon: <Clock className="w-4 h-4" />, color: 'text-yellow-400' },
          { label: 'Coût pièces', value: `${(totalCout/1000).toFixed(1)}K€`, icon: <AlertTriangle className="w-4 h-4" />, color: 'text-red-400' },
        ].map(k => (
          <div key={k.label} className="glass rounded-xl p-4 text-center">
            <div className={`text-3xl font-black ${k.color}`}>{k.value}</div>
            <div className="text-xs text-savia-text-muted mt-1 flex items-center justify-center gap-1">{k.icon} {k.label}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
          <input type="text" placeholder="Rechercher..." value={search} onChange={e => setSearch(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
        </div>
        <select value={filterStatut} onChange={e => setFilterStatut(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
          <option value="Tous">Tous les statuts</option>
          <option value="Terminée">✅ Terminée</option>
          <option value="En cours">🔄 En cours</option>
          <option value="Planifiée">📅 Planifiée</option>
        </select>
        <select value={filterType} onChange={e => setFilterType(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
          <option value="Tous">Tous les types</option>
          <option value="Corrective">🔴 Corrective</option>
          <option value="Préventive">🟢 Préventive</option>
          <option value="Installation">🔵 Installation</option>
        </select>
      </div>

      <SectionCard title="📋 Liste des interventions">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-savia-border">
                <th className="text-left py-2 px-3 text-savia-text-muted">ID</th>
                <th className="text-left py-2 px-3 text-savia-text-muted">Date</th>
                <th className="text-left py-2 px-3 text-savia-text-muted">Machine</th>
                <th className="text-left py-2 px-3 text-savia-text-muted">Type</th>
                <th className="text-left py-2 px-3 text-savia-text-muted">Technicien</th>
                <th className="text-center py-2 px-3 text-savia-text-muted">Durée</th>
                <th className="text-center py-2 px-3 text-savia-text-muted">Statut</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(i => (
                <tr key={i.id} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors cursor-pointer">
                  <td className="py-2.5 px-3 font-mono text-savia-accent font-bold">{i.id}</td>
                  <td className="py-2.5 px-3">{i.date}</td>
                  <td className="py-2.5 px-3 font-semibold">{i.machine}</td>
                  <td className="py-2.5 px-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${i.type === 'Corrective' ? 'bg-red-500/10 text-red-400' : i.type === 'Préventive' ? 'bg-green-500/10 text-green-400' : 'bg-blue-500/10 text-blue-400'}`}>
                      {i.type}
                    </span>
                  </td>
                  <td className="py-2.5 px-3">{i.technicien}</td>
                  <td className="py-2.5 px-3 text-center font-mono">{i.duree}h</td>
                  <td className="py-2.5 px-3 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${i.statut === 'Terminée' ? 'bg-green-500/10 text-green-400' : i.statut === 'En cours' ? 'bg-yellow-500/10 text-yellow-400' : 'bg-blue-500/10 text-blue-400'}`}>
                      {i.statut}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
