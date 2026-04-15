'use client';
import { useState, useEffect } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Plus, Search, Clock, CheckCircle, AlertTriangle, Send, Loader2 } from 'lucide-react';
import { demandes } from '@/lib/api';

interface Demande {
  id: string;
  date: string;
  machine: string;
  client: string;
  demandeur: string;
  urgence: string;
  statut: string;
  description: string;
}

export default function DemandesPage() {
  const [search, setSearch] = useState('');
  const [data, setData] = useState<Demande[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const res = await demandes.list();
        const mapped = res.map((item: any) => ({
          id: String(item.id || item.Ref_Interne || ''),
          date: item.Date_Demande ? item.Date_Demande.substring(0, 10) : (item.date || 'N/A'),
          machine: item.Equipement || item.machine || 'Générique',
          client: item.Client || item.client || '',
          demandeur: item.Demandeur || 'Non renseigné',
          urgence: item.Urgence || 'Moyenne',
          statut: item.Statut || 'En attente',
          description: item.Description || item.probleme || '',
        }));
        setData(mapped);
      } catch (err) {
        console.error("Failed to fetch demandes", err);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, []);

  const enAttente = data.filter(d => d.statut === 'En attente' || d.statut.toLowerCase().includes('attente')).length;
  const enCours = data.filter(d => d.statut === 'En cours' || d.statut === 'Assignée' || d.statut.toLowerCase().includes('cours')).length;
  const resolues = data.filter(d => d.statut === 'Résolue' || d.statut.toLowerCase().includes('tur') || d.statut.toLowerCase().includes('termin')).length;

  const filtered = data.filter(d => !search || d.machine.toLowerCase().includes(search.toLowerCase()) || d.id.toLowerCase().includes(search.toLowerCase()));

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-savia-accent" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text">📝 Demandes d&apos;Intervention</h1>
          <p className="text-savia-text-muted text-sm mt-1">Suivi des demandes terrain</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-savia-text bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
          <Plus className="w-4 h-4" /> Nouvelle demande
        </button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-red-400">{enAttente}</div><div className="text-xs text-savia-text-muted mt-1">⏳ En attente</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-yellow-400">{enCours}</div><div className="text-xs text-savia-text-muted mt-1">🔄 En cours</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-green-400">{resolues}</div><div className="text-xs text-savia-text-muted mt-1">✅ Résolues</div></div>
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
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${d.urgence === 'Haute' || d.urgence === 'Critique' ? 'bg-red-500/10 text-red-400' : d.urgence === 'Moyenne' ? 'bg-yellow-500/10 text-yellow-400' : 'bg-green-500/10 text-green-400'}`}>
                  ⚡ {d.urgence}
                </span>
              </div>
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${d.statut === 'Résolue' || d.statut.toLowerCase().includes('termin') ? 'bg-green-500/10 text-green-400' : d.statut === 'En attente' ? 'bg-red-500/10 text-red-400' : 'bg-yellow-500/10 text-yellow-400'}`}>
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
