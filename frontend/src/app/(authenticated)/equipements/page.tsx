'use client';
// ==========================================
// 🏥 PAGE PARC ÉQUIPEMENTS — SAVIA
// ==========================================
import { useState, useMemo } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Plus, Search, Edit2, Trash2, ChevronDown, ChevronUp, Filter } from 'lucide-react';

interface Equipment {
  id: string;
  nom: string;
  type: string;
  marque: string;
  modele: string;
  numSerie: string;
  client: string;
  localisation: string;
  dateMiseEnService: string;
  derniereMaintenance: string;
  prochaineMaintenance: string;
  healthScore: number;
  statut: 'Opérationnel' | 'En maintenance' | 'Hors service' | 'En attente pièce';
}

const DEMO_EQUIPEMENTS: Equipment[] = [
  { id: '1', nom: 'Scanner CT-01', type: 'Scanner CT', marque: 'Siemens', modele: 'SOMATOM go.Up', numSerie: 'SN-CT-2024-001', client: 'Clinique El Manar', localisation: 'Salle R-101', dateMiseEnService: '2022-03-15', derniereMaintenance: '2025-01-10', prochaineMaintenance: '2025-07-10', healthScore: 72, statut: 'Opérationnel' },
  { id: '2', nom: 'IRM Siemens 3T', type: 'IRM', marque: 'Siemens', modele: 'MAGNETOM Vida', numSerie: 'SN-IRM-2023-002', client: 'Hôpital Charles Nicolle', localisation: 'Salle IM-201', dateMiseEnService: '2021-09-20', derniereMaintenance: '2025-02-15', prochaineMaintenance: '2025-08-15', healthScore: 85, statut: 'Opérationnel' },
  { id: '3', nom: 'Radio DR-200', type: 'Radiographie', marque: 'GE Healthcare', modele: 'Optima XR240', numSerie: 'SN-DR-2024-003', client: 'Centre Imagerie Lac', localisation: 'Salle R-301', dateMiseEnService: '2023-06-10', derniereMaintenance: '2025-03-01', prochaineMaintenance: '2025-09-01', healthScore: 94, statut: 'Opérationnel' },
  { id: '4', nom: 'Mammographe GE', type: 'Mammographie', marque: 'GE Healthcare', modele: 'Senographe Pristina', numSerie: 'SN-MM-2023-004', client: 'Clinique El Manar', localisation: 'Salle M-102', dateMiseEnService: '2022-11-05', derniereMaintenance: '2024-12-20', prochaineMaintenance: '2025-06-20', healthScore: 58, statut: 'En maintenance' },
  { id: '5', nom: 'Échographe P500', type: 'Échographie', marque: 'Philips', modele: 'EPIQ Elite', numSerie: 'SN-US-2024-005', client: 'Polyclinique Ennasr', localisation: 'Salle E-401', dateMiseEnService: '2024-01-15', derniereMaintenance: '2025-03-10', prochaineMaintenance: '2025-09-10', healthScore: 98, statut: 'Opérationnel' },
  { id: '6', nom: 'Arceau C-Arm', type: 'Fluoroscopie', marque: 'Philips', modele: 'Veradius Unity', numSerie: 'SN-CA-2023-006', client: 'Hôpital Charles Nicolle', localisation: 'Bloc Op-501', dateMiseEnService: '2023-04-20', derniereMaintenance: '2025-01-25', prochaineMaintenance: '2025-07-25', healthScore: 76, statut: 'Opérationnel' },
  { id: '7', nom: 'Panoramique Dentaire', type: 'Radiographie', marque: 'Carestream', modele: 'CS 8200', numSerie: 'SN-PD-2024-007', client: 'Centre Imagerie Lac', localisation: 'Salle D-601', dateMiseEnService: '2024-05-01', derniereMaintenance: '2025-02-28', prochaineMaintenance: '2025-08-28', healthScore: 91, statut: 'Opérationnel' },
  { id: '8', nom: 'Angiographe Biplan', type: 'Angiographie', marque: 'Siemens', modele: 'Artis zee', numSerie: 'SN-AG-2022-008', client: 'Hôpital Charles Nicolle', localisation: 'Cath Lab-701', dateMiseEnService: '2020-08-12', derniereMaintenance: '2024-11-15', prochaineMaintenance: '2025-05-15', healthScore: 65, statut: 'En attente pièce' },
];

const TYPES = ['Tous', 'Scanner CT', 'IRM', 'Radiographie', 'Mammographie', 'Échographie', 'Fluoroscopie', 'Angiographie'];
const CLIENTS = ['Tous', 'Clinique El Manar', 'Hôpital Charles Nicolle', 'Centre Imagerie Lac', 'Polyclinique Ennasr'];

function getHealthColor(score: number) {
  if (score >= 85) return 'text-green-400 bg-green-500/10 border-green-500/20';
  if (score >= 65) return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20';
  return 'text-red-400 bg-red-500/10 border-red-500/20';
}

function getStatutBadge(statut: Equipment['statut']) {
  switch (statut) {
    case 'Opérationnel': return 'bg-green-500/10 text-green-400 border-green-500/20';
    case 'En maintenance': return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20';
    case 'Hors service': return 'bg-red-500/10 text-red-400 border-red-500/20';
    case 'En attente pièce': return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
  }
}

export default function EquipementsPage() {
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('Tous');
  const [filterClient, setFilterClient] = useState('Tous');
  const [showAddForm, setShowAddForm] = useState(false);

  const filtered = useMemo(() => {
    return DEMO_EQUIPEMENTS.filter(eq => {
      if (filterType !== 'Tous' && eq.type !== filterType) return false;
      if (filterClient !== 'Tous' && eq.client !== filterClient) return false;
      if (search && !eq.nom.toLowerCase().includes(search.toLowerCase()) &&
          !eq.numSerie.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [search, filterType, filterClient]);

  const totalEquip = DEMO_EQUIPEMENTS.length;
  const operationnel = DEMO_EQUIPEMENTS.filter(e => e.statut === 'Opérationnel').length;
  const maintenance = DEMO_EQUIPEMENTS.filter(e => e.statut !== 'Opérationnel').length;
  const avgHealth = Math.round(DEMO_EQUIPEMENTS.reduce((a, b) => a + b.healthScore, 0) / totalEquip);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text">🏥 Parc Équipements</h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion du parc d&apos;équipements de radiologie</p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer"
        >
          <Plus className="w-4 h-4" /> Ajouter
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Équipements', value: totalEquip, color: 'text-savia-accent' },
          { label: 'Opérationnels', value: operationnel, color: 'text-green-400' },
          { label: 'En arrêt', value: maintenance, color: 'text-red-400' },
          { label: 'Santé Moy.', value: `${avgHealth}%`, color: avgHealth >= 80 ? 'text-green-400' : 'text-yellow-400' },
        ].map(kpi => (
          <div key={kpi.label} className="glass rounded-xl p-4 text-center">
            <div className={`text-3xl font-black ${kpi.color}`}>{kpi.value}</div>
            <div className="text-xs text-savia-text-muted mt-1">{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
          <input
            type="text"
            placeholder="Rechercher par nom ou N° série..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim"
          />
        </div>
        <select value={filterType} onChange={e => setFilterType(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
          {TYPES.map(t => <option key={t} value={t}>{t === 'Tous' ? '📁 Tous les types' : t}</option>)}
        </select>
        <select value={filterClient} onChange={e => setFilterClient(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
          {CLIENTS.map(c => <option key={c} value={c}>{c === 'Tous' ? '🏢 Tous les clients' : c}</option>)}
        </select>
      </div>

      {/* Equipment Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filtered.map(eq => (
          <div key={eq.id} className="glass rounded-xl p-5 hover:border-savia-accent/30 transition-all group">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-bold text-lg">{eq.nom}</h3>
                <p className="text-savia-text-muted text-sm">{eq.marque} — {eq.modele}</p>
              </div>
              <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getStatutBadge(eq.statut)}`}>
                {eq.statut}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm mb-3">
              <div><span className="text-savia-text-dim">🏢</span> {eq.client}</div>
              <div><span className="text-savia-text-dim">📍</span> {eq.localisation}</div>
              <div><span className="text-savia-text-dim">🔢</span> <code className="text-xs">{eq.numSerie}</code></div>
              <div><span className="text-savia-text-dim">📅</span> Maint: {eq.prochaineMaintenance}</div>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs text-savia-text-dim">Santé:</span>
                <div className="w-24 h-2 bg-savia-bg rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${eq.healthScore >= 85 ? 'bg-green-500' : eq.healthScore >= 65 ? 'bg-yellow-500' : 'bg-red-500'}`}
                    style={{ width: `${eq.healthScore}%` }}
                  />
                </div>
                <span className={`text-sm font-bold ${eq.healthScore >= 85 ? 'text-green-400' : eq.healthScore >= 65 ? 'text-yellow-400' : 'text-red-400'}`}>
                  {eq.healthScore}%
                </span>
              </div>
              <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 cursor-pointer"><Edit2 className="w-3.5 h-3.5" /></button>
                <button className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="glass rounded-xl p-8 text-center">
          <p className="text-savia-text-muted">Aucun équipement trouvé pour ces filtres.</p>
        </div>
      )}
    </div>
  );
}
