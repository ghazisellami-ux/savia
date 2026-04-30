'use client';
// ==========================================
// 📅 SLA Tracking — Suivi Temps Réel
// ==========================================
import { useState, useEffect, useCallback } from 'react';
import { SectionCard, KpiCard } from '@/components/ui/cards';
import {
  Clock, AlertTriangle, CheckCircle2, XCircle, Shield,
  Loader2, Filter, Building2, Wrench, Zap, Timer,
  TrendingUp, RefreshCcw, ChevronDown,
} from 'lucide-react';
import { sla, clients as clientsApi } from '@/lib/api';

function formatDuration(hours: number): string {
  if (hours < 1) return `${Math.round(hours * 60)}min`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  const days = Math.floor(hours / 24);
  const h = Math.round(hours % 24);
  return `${days}j ${h}h`;
}

interface SlaItem {
  id: string | number;
  machine: string;
  client: string;
  technicien: string;
  type_intervention: string;
  statut: string;
  date_debut: string;
  sla_h: number;
  elapsed_h: number;
  remaining_h: number;
  pct_used: number;
  breached: boolean;
  priorite: string;
}

export default function SlaPage() {
  const [data, setData] = useState<{ kpis: any; items: SlaItem[] }>({ kpis: {}, items: [] });
  const [clientList, setClientList] = useState<string[]>([]);
  const [selectedClient, setSelectedClient] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<'all' | 'breached' | 'danger' | 'ok'>('all');
  const [now, setNow] = useState(Date.now());

  const load = useCallback(async () => {
    try {
      const [slaData, cls] = await Promise.all([
        sla.status(selectedClient || undefined),
        clientsApi.list(),
      ]);
      setData(slaData as any);
      const names = (cls as any[]).map((c: any) => c.nom).filter(Boolean);
      setClientList(names);
    } catch (err) {
      console.error('Failed to load SLA data', err);
    } finally {
      setIsLoading(false);
    }
  }, [selectedClient]);

  useEffect(() => { load(); }, [load]);

  // Live timer: update every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setNow(Date.now());
      load();
    }, 30000);
    return () => clearInterval(interval);
  }, [load]);

  const kpis = data.kpis || {};
  const items = data.items || [];

  const filteredItems = items.filter(item => {
    if (filterStatus === 'breached') return item.breached;
    if (filterStatus === 'danger') return !item.breached && item.pct_used >= 75;
    if (filterStatus === 'ok') return !item.breached && item.pct_used < 75;
    return true;
  });

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-savia-accent" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
            <Shield className="w-7 h-7" /> Suivi SLA
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Suivi temps réel des engagements contractuels</p>
        </div>
        <button onClick={() => { setIsLoading(true); load(); }} className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold text-savia-accent border border-savia-accent/20 hover:bg-savia-accent/10 transition-all cursor-pointer">
          <RefreshCcw className="w-4 h-4" /> Rafraîchir
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KpiCard
          icon={<Timer className="w-6 h-6 text-savia-accent" />}
          value={String(kpis.total_active || 0)}
          label="Interventions actives"
        />
        <KpiCard
          icon={<CheckCircle2 className="w-6 h-6 text-green-400" />}
          value={String(kpis.nb_ok || 0)}
          label="Dans les délais"
          variant="success"
        />
        <KpiCard
          icon={<AlertTriangle className="w-6 h-6 text-yellow-400" />}
          value={String(kpis.nb_danger || 0)}
          label="En danger (>75%)"
          variant="warning"
        />
        <KpiCard
          icon={<XCircle className="w-6 h-6 text-red-400" />}
          value={String(kpis.nb_breached || 0)}
          label="SLA dépassé"
          variant="danger"
        />
        <KpiCard
          icon={<TrendingUp className="w-6 h-6 text-blue-400" />}
          value={`${kpis.compliance_pct || 100}%`}
          label="Taux de conformité"
          variant={(kpis.compliance_pct || 100) >= 90 ? 'success' : (kpis.compliance_pct || 100) >= 70 ? 'warning' : 'danger'}
        />
      </div>

      {/* Compliance visual bar */}
      <SectionCard title={<span className="flex items-center gap-2"><Shield className="w-4 h-4 text-savia-accent" /> Conformité SLA Globale</span>}>
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <div className="h-4 rounded-full bg-savia-surface-hover overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-1000"
                style={{
                  width: `${kpis.compliance_pct || 100}%`,
                  background: (kpis.compliance_pct || 100) >= 90
                    ? 'linear-gradient(90deg, #22c55e, #2dd4bf)'
                    : (kpis.compliance_pct || 100) >= 70
                    ? 'linear-gradient(90deg, #f59e0b, #eab308)'
                    : 'linear-gradient(90deg, #ef4444, #f97316)',
                }}
              />
            </div>
            <div className="flex justify-between mt-1 text-xs text-savia-text-dim">
              <span>0%</span>
              <span className="font-bold text-savia-text">{kpis.compliance_pct || 100}% des interventions respectent le SLA</span>
              <span>100%</span>
            </div>
          </div>
        </div>
      </SectionCard>

      {/* Filters */}
      <div className="glass rounded-xl p-4 flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2 text-xs font-semibold text-savia-text-muted uppercase tracking-wider">
          <Filter className="w-3.5 h-3.5" /> Filtres
        </div>
        <select
          value={selectedClient}
          onChange={e => setSelectedClient(e.target.value)}
          className="bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2 text-savia-text focus:ring-2 focus:ring-savia-accent/40 outline-none text-sm"
        >
          <option value="">Tous les clients</option>
          {clientList.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <div className="flex rounded-lg overflow-hidden border border-savia-border">
          {[
            { key: 'all', label: 'Tous', count: items.length },
            { key: 'ok', label: 'OK', count: kpis.nb_ok || 0, color: 'text-green-400' },
            { key: 'danger', label: 'Danger', count: kpis.nb_danger || 0, color: 'text-yellow-400' },
            { key: 'breached', label: 'Dépassé', count: kpis.nb_breached || 0, color: 'text-red-400' },
          ].map(f => (
            <button
              key={f.key}
              onClick={() => setFilterStatus(f.key as any)}
              className={`px-3 py-1.5 text-xs font-bold transition-all cursor-pointer ${
                filterStatus === f.key
                  ? 'bg-savia-accent text-white'
                  : 'bg-savia-bg/50 text-savia-text-muted hover:bg-savia-surface-hover/30'
              }`}
            >
              {f.label} ({f.count})
            </button>
          ))}
        </div>
      </div>

      {/* SLA Items */}
      <div className="space-y-3">
        {filteredItems.length === 0 && (
          <div className="glass rounded-xl p-12 text-center">
            <CheckCircle2 className="w-12 h-12 mx-auto mb-3 text-green-400 opacity-30" />
            <p className="text-savia-text-muted">
              {filterStatus === 'all' ? 'Aucune intervention active' : `Aucune intervention dans la catégorie "${filterStatus}"`}
            </p>
          </div>
        )}
        {filteredItems.map(item => {
          const pct = item.pct_used;
          const barColor = item.breached
            ? 'bg-gradient-to-r from-red-500 to-red-600'
            : pct >= 75
            ? 'bg-gradient-to-r from-yellow-500 to-orange-500'
            : pct >= 50
            ? 'bg-gradient-to-r from-blue-500 to-cyan-500'
            : 'bg-gradient-to-r from-green-500 to-teal-500';

          const statusBadge = item.breached
            ? 'bg-red-500/15 text-red-400 border-red-500/20'
            : pct >= 75
            ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/20'
            : 'bg-green-500/15 text-green-400 border-green-500/20';

          const statusText = item.breached
            ? '🚨 SLA DÉPASSÉ'
            : pct >= 75
            ? '⚠️ En danger'
            : '✓ Dans les délais';

          return (
            <div
              key={item.id}
              className={`glass rounded-xl p-4 transition-all hover:border-savia-accent/20 ${
                item.breached ? 'border-l-4 border-l-red-500' : pct >= 75 ? 'border-l-4 border-l-yellow-500' : ''
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-xs text-savia-accent font-bold">#{item.id}</span>
                    <span className="font-bold">{item.machine}</span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${statusBadge}`}>
                      {statusText}
                    </span>
                    {item.priorite && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-500/10 text-purple-400">
                        {item.priorite}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-savia-text-muted flex-wrap">
                    <span className="flex items-center gap-1"><Building2 className="w-3 h-3" /> {item.client}</span>
                    <span className="flex items-center gap-1"><Wrench className="w-3 h-3" /> {item.type_intervention}</span>
                    {item.technicien && <span className="flex items-center gap-1"><Zap className="w-3 h-3" /> {item.technicien}</span>}
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> Depuis: {item.date_debut}</span>
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-xs text-savia-text-dim">SLA: {item.sla_h}h</div>
                  <div className={`text-lg font-black ${item.breached ? 'text-red-400' : pct >= 75 ? 'text-yellow-400' : 'text-green-400'}`}>
                    {item.breached
                      ? `+${formatDuration(item.elapsed_h - item.sla_h)}`
                      : formatDuration(item.remaining_h)
                    }
                  </div>
                  <div className="text-[10px] text-savia-text-dim">
                    {item.breached ? 'dépassement' : 'restant'}
                  </div>
                </div>
              </div>

              {/* Progress bar */}
              <div className="relative">
                <div className="h-2.5 rounded-full bg-savia-surface-hover overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                    style={{ width: `${Math.min(pct, 100)}%` }}
                  />
                </div>
                <div className="flex justify-between mt-1 text-[10px] text-savia-text-dim">
                  <span>Écoulé: {formatDuration(item.elapsed_h)}</span>
                  <span className="font-bold">{pct.toFixed(0)}%</span>
                  <span>Limite: {item.sla_h}h</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
