'use client';
import { useState, useEffect } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Plus, Search, FileText, AlertTriangle, Loader2 } from 'lucide-react';
import { contrats } from '@/lib/api';

interface Contrat {
  id: string;
  client: string;
  type: string;
  debut: string;
  fin: string;
  machines: number;
  montant: number;
  statut: string;
}

export default function ContratsPage() {
  const [search, setSearch] = useState('');
  const [data, setData] = useState<Contrat[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const res = await contrats.list();
        const mapped = res.map((item: any) => ({
          id: String(item.id || item.Ref_Contrat || ''),
          client: item.Client || '',
          type: item.Type_Contrat || 'Standard',
          debut: item.Date_Debut ? item.Date_Debut.substring(0, 10) : 'N/A',
          fin: item.Date_Fin ? item.Date_Fin.substring(0, 10) : 'N/A',
          machines: item.nb_machines || item.equipement || 1, // Fallback if nb_machines is missing
          montant: item.Montant_Annuel || item.montant || 0,
          statut: item.Statut || 'Actif',
        }));
        setData(mapped);
      } catch (err) {
        console.error("Failed to fetch contrats", err);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, []);

  const filtered = data.filter(c => !search || c.client.toLowerCase().includes(search.toLowerCase()) || c.id.toLowerCase().includes(search.toLowerCase()));
  const actifs = data.filter(c => c.statut === 'Actif' || c.statut.toLowerCase().includes('actif')).length;
  const expirations = data.filter(c => c.statut.toLowerCase().includes('expiration') || c.statut.toLowerCase().includes('proche')).length;
  const totalRevenu = data.reduce((a, b) => a + b.montant, 0);

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
          <h1 className="text-2xl font-black gradient-text">📄 Contrats de Maintenance</h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion des contrats SAV</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
          <Plus className="w-4 h-4" /> Nouveau contrat
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total contrats', value: data.length, color: 'text-savia-accent' },
          { label: 'Actifs', value: actifs, color: 'text-green-400' },
          { label: 'Expirations proches', value: expirations, color: 'text-yellow-400' },
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
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${c.statut.toLowerCase().includes('actif') ? 'bg-green-500/10 text-green-400' : c.statut.toLowerCase().includes('proche') ? 'bg-yellow-500/10 text-yellow-400' : 'bg-red-500/10 text-red-400'}`}>
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
