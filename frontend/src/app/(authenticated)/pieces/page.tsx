'use client';
import { useState } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Plus, Search, Package, AlertTriangle } from 'lucide-react';

const DEMO_PIECES = [
  { ref: 'SCA-HV-CAP-01', nom: 'Module condensateur HV Generator', machine: 'Scanner CT', stock: 2, seuil: 1, prix: 1200, fournisseur: 'Siemens', delai: '5-7 jours' },
  { ref: 'GE-MAMMO-PAD-02', nom: 'Ensemble paddle compression', machine: 'Mammographe', stock: 0, seuil: 1, prix: 2800, fournisseur: 'GE Healthcare', delai: '10-14 jours' },
  { ref: 'SKF-6205', nom: 'Roulement à billes C-Arm', machine: 'Arceau', stock: 4, seuil: 2, prix: 85, fournisseur: 'SKF', delai: '2-3 jours' },
  { ref: 'PHI-US-PROB-03', nom: 'Sonde échographique C5-1', machine: 'Échographe', stock: 1, seuil: 1, prix: 4500, fournisseur: 'Philips', delai: '15-20 jours' },
  { ref: 'SIE-IRM-COLD-01', nom: 'Joint coldhead IRM', machine: 'IRM', stock: 3, seuil: 2, prix: 350, fournisseur: 'Siemens', delai: '7-10 jours' },
  { ref: 'GE-DR-FPD-04', nom: 'Détecteur flat panel DR', machine: 'Radiographie', stock: 0, seuil: 1, prix: 15000, fournisseur: 'GE Healthcare', delai: '30+ jours' },
  { ref: 'SIE-CT-TUBE-01', nom: 'Tube RX Scanner CT', machine: 'Scanner CT', stock: 1, seuil: 1, prix: 45000, fournisseur: 'Siemens', delai: '20-30 jours' },
];

export default function PiecesPage() {
  const [search, setSearch] = useState('');
  const filtered = DEMO_PIECES.filter(p => !search || p.ref.toLowerCase().includes(search.toLowerCase()) || p.nom.toLowerCase().includes(search.toLowerCase()));
  const ruptures = DEMO_PIECES.filter(p => p.stock === 0).length;
  const seuilBas = DEMO_PIECES.filter(p => p.stock > 0 && p.stock <= p.seuil).length;
  const totalValeur = DEMO_PIECES.reduce((a, p) => a + p.prix * p.stock, 0);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text">🔩 Pièces Détachées</h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion du stock de pièces SAV</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
          <Plus className="w-4 h-4" /> Ajouter pièce
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-savia-accent">{DEMO_PIECES.length}</div><div className="text-xs text-savia-text-muted mt-1">Références</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-red-400">{ruptures}</div><div className="text-xs text-savia-text-muted mt-1">🔴 Ruptures</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-yellow-400">{seuilBas}</div><div className="text-xs text-savia-text-muted mt-1">🟡 Stock bas</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-green-400">{(totalValeur/1000).toFixed(0)}K€</div><div className="text-xs text-savia-text-muted mt-1">Valeur stock</div></div>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
        <input type="text" placeholder="Rechercher par réf. ou nom..." value={search} onChange={e => setSearch(e.target.value)} className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
      </div>

      <SectionCard title="📦 Inventaire">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-savia-border">
                <th className="text-left py-2 px-3 text-savia-text-muted">Réf.</th>
                <th className="text-left py-2 px-3 text-savia-text-muted">Désignation</th>
                <th className="text-center py-2 px-3 text-savia-text-muted">Stock</th>
                <th className="text-right py-2 px-3 text-savia-text-muted">Prix</th>
                <th className="text-left py-2 px-3 text-savia-text-muted">Fournisseur</th>
                <th className="text-center py-2 px-3 text-savia-text-muted">Délai</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(p => (
                <tr key={p.ref} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                  <td className="py-2.5 px-3 font-mono text-savia-accent font-bold text-xs">{p.ref}</td>
                  <td className="py-2.5 px-3">
                    <div className="font-semibold text-sm">{p.nom}</div>
                    <div className="text-xs text-savia-text-dim">{p.machine}</div>
                  </td>
                  <td className="py-2.5 px-3 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${p.stock === 0 ? 'bg-red-500/10 text-red-400' : p.stock <= p.seuil ? 'bg-yellow-500/10 text-yellow-400' : 'bg-green-500/10 text-green-400'}`}>
                      {p.stock}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-right font-mono">{p.prix.toLocaleString()}€</td>
                  <td className="py-2.5 px-3 text-sm">{p.fournisseur}</td>
                  <td className="py-2.5 px-3 text-center text-xs text-savia-text-muted">{p.delai}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
