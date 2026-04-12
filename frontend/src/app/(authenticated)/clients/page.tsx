'use client';
import { SectionCard } from '@/components/ui/cards';
import { Search, Building2, Users, Wrench } from 'lucide-react';
import { useState } from 'react';

const DEMO_CLIENTS = [
  { nom: 'Clinique El Manar', ville: 'Tunis', contact: 'Dr. Ben Ali', tel: '+216 71 888 000', machines: 3, contrat: 'Full Omnium', interventions: 15, healthMoyen: 75 },
  { nom: 'Hôpital Charles Nicolle', ville: 'Tunis', contact: 'Dr. Mansouri', tel: '+216 71 578 000', machines: 4, contrat: 'Pièces & MO', interventions: 22, healthMoyen: 82 },
  { nom: 'Centre Imagerie Lac', ville: 'Les Berges du Lac', contact: 'M. Bouazizi', tel: '+216 71 960 000', machines: 2, contrat: 'Maint. Préventive', interventions: 8, healthMoyen: 91 },
  { nom: 'Polyclinique Ennasr', ville: 'Ariana', contact: 'Mme Gharbi', tel: '+216 71 750 000', machines: 1, contrat: 'Full Omnium', interventions: 4, healthMoyen: 98 },
];

export default function ClientsPage() {
  const [search, setSearch] = useState('');
  const filtered = DEMO_CLIENTS.filter(c => !search || c.nom.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-black gradient-text">🏢 Clients SAVIA</h1>
        <p className="text-savia-text-muted text-sm mt-1">Gestion des établissements clients</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-savia-accent">{DEMO_CLIENTS.length}</div><div className="text-xs text-savia-text-muted mt-1">Clients actifs</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-blue-400">{DEMO_CLIENTS.reduce((a, c) => a + c.machines, 0)}</div><div className="text-xs text-savia-text-muted mt-1">Machines gérées</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-green-400">{DEMO_CLIENTS.reduce((a, c) => a + c.interventions, 0)}</div><div className="text-xs text-savia-text-muted mt-1">Interventions totales</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-yellow-400">{Math.round(DEMO_CLIENTS.reduce((a, c) => a + c.healthMoyen, 0) / DEMO_CLIENTS.length)}%</div><div className="text-xs text-savia-text-muted mt-1">Santé moyenne</div></div>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
        <input type="text" placeholder="Rechercher un client..." value={search} onChange={e => setSearch(e.target.value)} className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filtered.map(c => (
          <div key={c.nom} className="glass rounded-xl p-5 hover:border-savia-accent/30 transition-all cursor-pointer">
            <div className="flex items-start gap-3 mb-3">
              <div className="w-10 h-10 rounded-lg bg-savia-accent/10 flex items-center justify-center"><Building2 className="w-5 h-5 text-savia-accent" /></div>
              <div>
                <h3 className="font-bold">{c.nom}</h3>
                <p className="text-xs text-savia-text-muted">📍 {c.ville} — 📞 {c.tel}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm mb-3">
              <div><span className="text-savia-text-dim">👤</span> {c.contact}</div>
              <div><span className="text-savia-text-dim">📄</span> {c.contrat}</div>
              <div><span className="text-savia-text-dim">🏥</span> {c.machines} machines</div>
              <div><span className="text-savia-text-dim">🔧</span> {c.interventions} interv.</div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-savia-text-dim">Santé parc:</span>
              <div className="flex-1 h-2 bg-savia-bg rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${c.healthMoyen >= 85 ? 'bg-green-500' : c.healthMoyen >= 65 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${c.healthMoyen}%` }} />
              </div>
              <span className={`text-sm font-bold ${c.healthMoyen >= 85 ? 'text-green-400' : c.healthMoyen >= 65 ? 'text-yellow-400' : 'text-red-400'}`}>{c.healthMoyen}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
