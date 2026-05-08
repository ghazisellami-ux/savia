'use client';
// ==========================================
// 💰 Finances — Rentabilité & TCO Dashboard
// ==========================================
import { useState, useEffect, useCallback, useMemo } from 'react';
import { SectionCard, KpiCard } from '@/components/ui/cards';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, Legend,
} from 'recharts';
import {
  DollarSign, TrendingUp, TrendingDown, AlertTriangle, CheckCircle2,
  Building2, Wrench, Cpu, Loader2, Filter, ArrowUpDown, ChevronDown, ChevronUp,
  PieChart as PieChartIcon, BarChart3, Clock, Package, Sparkles, Brain,
} from 'lucide-react';
import { finances, clients as clientsApi, ai } from '@/lib/api';
import { useCanSeeCosts } from '@/lib/use-role-guard';

const FMT = (n: number) => n.toLocaleString('fr-FR');
const FMTK = (n: number) => {
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1).replace('.0', '') + 'M';
  if (Math.abs(n) >= 10_000) return Math.round(n / 1_000).toLocaleString('fr-FR') + 'K';
  return n.toLocaleString('fr-FR');
};
const COLORS = {
  green: '#22c55e', red: '#ef4444', blue: '#3b82f6',
  teal: '#2dd4bf', yellow: '#f59e0b', purple: '#8b5cf6', orange: '#f97316',
};
const PIE_COLORS = [COLORS.teal, COLORS.blue, COLORS.orange, COLORS.purple, COLORS.yellow];

export default function FinancesPage() {
  const canSeeCosts = useCanSeeCosts();
  const [data, setData] = useState<any>(null);
  const [tcoData, setTcoData] = useState<any[]>([]);
  const [clientList, setClientList] = useState<string[]>([]);
  const [selectedClient, setSelectedClient] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [tab, setTab] = useState<'clients' | 'tco'>('clients');
  const [sortCol, setSortCol] = useState('marge');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [aiRecos, setAiRecos] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      // Load finances data independently so one failure doesn't block others
      const [fin, tco] = await Promise.all([
        finances.dashboard(selectedClient || undefined),
        finances.tco(selectedClient || undefined),
      ]);
      setData(fin);
      setTcoData(tco as any[]);
    } catch (err) {
      console.error('Failed to load finances', err);
    }
    // Client list for filter dropdown - separate call
    try {
      const cls = await clientsApi.list();
      const names = (cls as any[]).map((c: any) => c.nom || c.client || '').filter(Boolean);
      setClientList(names);
    } catch {
      // Fallback: extract client names from finance data
      if (data?.clients) {
        setClientList((data.clients as any[]).map((c: any) => c.client).filter(Boolean));
      }
    }
    setIsLoading(false);
  }, [selectedClient]);

  useEffect(() => { load(); }, [load]);

  const kpis = data?.kpis || {};
  const clientsData = useMemo(() => {
    const arr = (data?.clients || []) as any[];
    return [...arr].sort((a, b) => {
      const va = a[sortCol] ?? 0;
      const vb = b[sortCol] ?? 0;
      return sortDir === 'asc' ? va - vb : vb - va;
    });
  }, [data, sortCol, sortDir]);

  const handleSort = (col: string) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('desc'); }
  };

  const SortIcon = ({ col }: { col: string }) => (
    sortCol === col
      ? sortDir === 'asc' ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />
      : <ArrowUpDown className="w-3 h-3 opacity-30" />
  );

  // Cost breakdown for chart
  const costBreakdown = useMemo(() => {
    if (!clientsData.length) return [];
    const totInterv = clientsData.reduce((a: number, c: any) => a + (c.cout_interventions || 0), 0);
    const totPieces = clientsData.reduce((a: number, c: any) => a + (c.cout_pieces || 0), 0);
    const totMO = clientsData.reduce((a: number, c: any) => a + (c.cout_main_oeuvre || 0), 0);
    return [
      { name: 'Interventions', value: totInterv, color: COLORS.red },
      { name: 'Pièces', value: totPieces, color: COLORS.orange },
      { name: 'Main d\'œuvre', value: totMO, color: COLORS.blue },
    ].filter(d => d.value > 0);
  }, [clientsData]);

  // Revenue vs Cost bar chart
  const revenueCostChart = useMemo(() => {
    return clientsData.map((c: any) => ({
      name: (c.client || '').length > 12 ? (c.client || '').substring(0, 12) + '…' : c.client,
      revenu: c.revenu_contrats || 0,
      cout: c.cout_total || 0,
      marge: c.marge || 0,
    }));
  }, [clientsData]);

  // AI Cost Recommendation
  const analyzeAiCosts = useCallback(async () => {
    if (aiLoading || clientsData.length === 0) return;
    setAiLoading(true);
    setAiError('');
    setAiRecos(null);
    try {
      const avgCout = clientsData.reduce((a: number, c: any) => a + (c.cout_total || 0), 0) / clientsData.length;
      const clientSummary = clientsData.map((c: any) => {
        const ecart = avgCout > 0 ? Math.round(((c.cout_total || 0) - avgCout) / avgCout * 100) : 0;
        return `${c.client}: revenu=${FMT(c.revenu_contrats || 0)} TND, coûts=${FMT(c.cout_total || 0)} TND, marge=${c.marge_pct || 0}%, interv=${c.nb_interventions || 0}, equip=${c.nb_equipements || 0}, écart_vs_moy=${ecart > 0 ? '+' : ''}${ecart}%`;
      }).join('\n');

      const prompt = `Analyse financière des clients SAVIA — recommandations de coûts:

Coût moyen par client: ${FMT(Math.round(avgCout))} TND
Marge globale: ${kpis.marge_pct || 0}%
Clients rentables: ${kpis.nb_rentables || 0} / ${kpis.nb_clients || 0}

Détails par client:
${clientSummary}

Donne-moi:
1. Les clients qui coûtent significativement plus que la moyenne (avec le % d'écart)
2. Les causes probables (nombre d'interventions élevé, coût pièces, etc.)
3. Des suggestions d'optimisation concrètes pour réduire les coûts
4. Les clients les plus rentables et pourquoi
5. Des recommandations stratégiques (renégociation contrats, maintenance préventive, etc.)

Formate avec des titres clairs et des puces •. Sois précis avec les chiffres.`;

      const res = await ai.chat(prompt);
      setAiRecos(res.response);
    } catch (err: any) {
      const msg = err.message || '';
      if (msg.includes('503') || msg.includes('429') || msg.includes('Quota') || msg.includes('UNAVAILABLE')) {
        setAiError('⏳ Quota IA atteint. Réessayez dans 1 minute.');
      } else {
        setAiError(`Erreur: ${msg}`);
      }
    } finally {
      setAiLoading(false);
    }
  }, [aiLoading, clientsData, kpis]);

  if (!canSeeCosts) {
    return (
      <div className="flex flex-col items-center justify-center h-64">
        <DollarSign className="w-12 h-12 text-savia-text-dim mb-4" />
        <p className="text-savia-text-muted">Vous n&apos;avez pas accès au module financier.</p>
      </div>
    );
  }

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
            <DollarSign className="w-7 h-7" /> Tableau de Bord Financier
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Rentabilité par client · TCO par équipement · Marges</p>
        </div>
      </div>

      {/* Client Filter */}
      <div className="glass rounded-xl p-4">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-savia-text-muted uppercase tracking-wider">
            <Filter className="w-3.5 h-3.5" /> Filtrer
          </div>
          <select
            value={selectedClient}
            onChange={e => setSelectedClient(e.target.value)}
            className="bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2 text-savia-text focus:ring-2 focus:ring-savia-accent/40 outline-none text-sm"
          >
            <option value="">Tous les clients</option>
            {clientList.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {/* Global KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
        <KpiCard icon={<TrendingUp className="w-6 h-6 text-green-400" />} value={`${FMTK(kpis.revenu_total || 0)} TND`} label="Revenu Contrats" variant="success" />
        <KpiCard icon={<TrendingDown className="w-6 h-6 text-red-400" />} value={`${FMTK(kpis.cout_total || 0)} TND`} label="Coûts Totaux" variant="danger" />
        <KpiCard
          icon={<DollarSign className="w-6 h-6" style={{ color: (kpis.marge_globale || 0) >= 0 ? COLORS.green : COLORS.red }} />}
          value={`${FMTK(kpis.marge_globale || 0)} TND`}
          label="Marge Globale"
          variant={(kpis.marge_globale || 0) >= 0 ? 'success' : 'danger'}
        />
        <KpiCard icon={<PieChartIcon className="w-6 h-6 text-blue-400" />} value={`${kpis.marge_pct || 0}%`} label="Taux de Marge" />
        <KpiCard icon={<Building2 className="w-6 h-6 text-savia-accent" />} value={String(kpis.nb_clients || 0)} label="Clients" />
        <KpiCard icon={<CheckCircle2 className="w-6 h-6 text-green-400" />} value={String(kpis.nb_rentables || 0)} label="Rentables" variant="success" />
        <KpiCard icon={<AlertTriangle className="w-6 h-6 text-red-400" />} value={String(kpis.nb_deficitaires || 0)} label="Déficitaires" variant="danger" />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Revenue vs Cost */}
        <SectionCard title={<span className="flex items-center gap-2"><BarChart3 className="w-4 h-4 text-savia-accent" /> Revenu vs Coûts par Client</span>}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={revenueCostChart} barGap={2}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(45,212,191,0.08)" />
              <XAxis dataKey="name" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} />
              <Tooltip
                contentStyle={{ background: '#0f1729', border: '1px solid rgba(45,212,191,0.2)', borderRadius: 8, color: '#f1f5f9' }}
                formatter={(value: any) => [`${FMT(Number(value))} TND`]}
              />
              <Bar dataKey="revenu" name="Revenu" fill={COLORS.green} radius={[4, 4, 0, 0]} />
              <Bar dataKey="cout" name="Coûts" fill={COLORS.red} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>

        {/* Cost Breakdown Pie */}
        <SectionCard title={<span className="flex items-center gap-2"><PieChartIcon className="w-4 h-4 text-orange-400" /> Répartition des Coûts</span>}>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={costBreakdown} cx="50%" cy="50%" innerRadius={60} outerRadius={95} paddingAngle={3} dataKey="value" stroke="none">
                {costBreakdown.map((d, i) => <Cell key={i} fill={d.color} />)}
              </Pie>
              <Tooltip
                contentStyle={{ background: '#0f1729', border: '1px solid rgba(45,212,191,0.2)', borderRadius: 8, color: '#f1f5f9' }}
                formatter={(value: any) => [`${FMT(Number(value))} TND`]}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: '#94a3b8' }} />
            </PieChart>
          </ResponsiveContainer>
        </SectionCard>
      </div>

      {/* 💰 AI Cost Recommendations */}
      <SectionCard title={
        <span className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-amber-500" />
          <span>Recommandations IA de Coûts</span>
        </span>
      }>
        {!aiRecos && !aiLoading && !aiError && (
          <div className="flex flex-col items-center py-8 gap-4">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, rgba(86,124,141,0.1), rgba(47,65,86,0.1))' }}>
              <Brain className="w-7 h-7 text-savia-accent" />
            </div>
            <div className="text-center max-w-md">
              <p className="text-savia-text font-semibold text-sm">Analyse IA des coûts par client</p>
              <p className="text-savia-text-muted text-xs mt-1">
                L&apos;IA analysera vos données financières pour identifier les clients qui coûtent plus que la moyenne et proposer des optimisations concrètes.
              </p>
            </div>
            <button
              onClick={analyzeAiCosts}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold text-white transition-all hover:opacity-90 cursor-pointer"
              style={{ background: 'linear-gradient(135deg, #567C8D, #2F4156)' }}
            >
              <Sparkles className="w-4 h-4" />
              Analyser les coûts
            </button>
          </div>
        )}

        {aiLoading && (
          <div className="flex flex-col items-center py-10 gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-savia-accent" />
            <p className="text-sm text-savia-text-muted">Analyse des données financières en cours...</p>
          </div>
        )}

        {aiError && (
          <div className="flex flex-col items-center py-6 gap-3">
            <p className="text-sm text-amber-600 font-medium">{aiError}</p>
            <button
              onClick={analyzeAiCosts}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold text-white cursor-pointer"
              style={{ background: 'linear-gradient(135deg, #567C8D, #2F4156)' }}
            >
              <Sparkles className="w-3.5 h-3.5" />
              Réessayer
            </button>
          </div>
        )}

        {aiRecos && (
          <div className="space-y-3">
            <div className="rounded-xl p-5 text-sm leading-relaxed text-savia-text" style={{ background: '#EEF3F6', boxShadow: 'inset 2px 2px 4px #e3dac7, inset -2px -2px 4px #ffffff' }}>
              {aiRecos.split('\n').map((line, i) => {
                // Bold titles
                if (line.match(/^\d+\.|^#+|^[A-Z\u00C0-\u017F].*:$/)) {
                  return <p key={i} className={`font-bold text-savia-accent-blue ${i > 0 ? 'mt-3' : ''}`}>{line}</p>;
                }
                // Bullet points
                if (line.trim().startsWith('•') || line.trim().startsWith('-') || line.trim().startsWith('*')) {
                  return <p key={i} className="ml-3 mt-1">{line}</p>;
                }
                if (!line.trim()) return <br key={i} />;
                return <p key={i} className={i > 0 ? 'mt-1' : ''}>{line}</p>;
              })}
            </div>
            <div className="flex justify-end">
              <button
                onClick={analyzeAiCosts}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-savia-text-muted hover:text-savia-accent transition-colors cursor-pointer"
              >
                <Sparkles className="w-3 h-3" />
                Relancer l&apos;analyse
              </button>
            </div>
          </div>
        )}
      </SectionCard>

      {/* Tab Toggle */}
      <div className="flex rounded-lg overflow-hidden border border-savia-border w-fit">
        <button onClick={() => setTab('clients')} className={`px-5 py-2.5 text-sm font-bold transition-all cursor-pointer ${tab === 'clients' ? 'bg-savia-accent text-white' : 'bg-savia-bg/50 text-savia-text-muted hover:bg-savia-surface-hover/30'}`}>
          <Building2 className="w-4 h-4 inline mr-2" />Rentabilité Clients
        </button>
        <button onClick={() => setTab('tco')} className={`px-5 py-2.5 text-sm font-bold transition-all cursor-pointer ${tab === 'tco' ? 'bg-blue-600 text-white' : 'bg-savia-bg/50 text-savia-text-muted hover:bg-savia-surface-hover/30'}`}>
          <Cpu className="w-4 h-4 inline mr-2" />TCO Équipements
        </button>
      </div>

      {/* Clients Profitability Table */}
      {tab === 'clients' && (
        <SectionCard title={<span className="flex items-center gap-2"><Building2 className="w-4 h-4 text-savia-accent" /> Rentabilité par Client</span>}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-savia-text-dim uppercase tracking-wider border-b border-savia-border/50">
                  <th className="py-3 px-3">Client</th>
                  <th className="py-3 px-2 text-center cursor-pointer hover:text-savia-accent" onClick={() => handleSort('nb_equipements')}>Équip. <SortIcon col="nb_equipements" /></th>
                  <th className="py-3 px-2 text-right cursor-pointer hover:text-savia-accent" onClick={() => handleSort('revenu_contrats')}>Revenu <SortIcon col="revenu_contrats" /></th>
                  <th className="py-3 px-2 text-right cursor-pointer hover:text-savia-accent" onClick={() => handleSort('cout_total')}>Coûts <SortIcon col="cout_total" /></th>
                  <th className="py-3 px-2 text-right cursor-pointer hover:text-savia-accent" onClick={() => handleSort('marge')}>Marge <SortIcon col="marge" /></th>
                  <th className="py-3 px-2 text-center cursor-pointer hover:text-savia-accent" onClick={() => handleSort('marge_pct')}>% <SortIcon col="marge_pct" /></th>
                  <th className="py-3 px-2 text-center">Interv.</th>
                  <th className="py-3 px-2 text-center">Statut</th>
                </tr>
              </thead>
              <tbody>
                {clientsData.map((c: any) => (
                  <tr key={c.client} className="border-b border-savia-border/20 hover:bg-savia-surface-hover/20 transition-colors">
                    <td className="py-3 px-3 font-bold">{c.client}</td>
                    <td className="py-3 px-2 text-center">{c.nb_equipements}</td>
                    <td className="py-3 px-2 text-right text-green-400 font-mono">{FMT(c.revenu_contrats)}</td>
                    <td className="py-3 px-2 text-right text-red-400 font-mono">{FMT(c.cout_total)}</td>
                    <td className={`py-3 px-2 text-right font-bold font-mono ${c.marge >= 0 ? 'text-green-400' : 'text-red-400'}`}>{FMT(c.marge)}</td>
                    <td className={`py-3 px-2 text-center font-bold ${c.marge_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>{c.marge_pct}%</td>
                    <td className="py-3 px-2 text-center">{c.nb_interventions}</td>
                    <td className="py-3 px-2 text-center">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${c.rentable ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                        {c.rentable ? '✓ Rentable' : '✗ Déficit'}
                      </span>
                    </td>
                  </tr>
                ))}
                {clientsData.length === 0 && (
                  <tr><td colSpan={8} className="py-8 text-center text-savia-text-muted">Aucune donnée financière disponible</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {/* TCO Table */}
      {tab === 'tco' && (
        <SectionCard title={<span className="flex items-center gap-2"><Cpu className="w-4 h-4 text-blue-400" /> TCO — Total Cost of Ownership</span>}>
          <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-savia-bg z-10">
                <tr className="text-left text-xs text-savia-text-dim uppercase tracking-wider border-b border-savia-border/50">
                  <th className="py-3 px-3">Équipement</th>
                  <th className="py-3 px-2">Client</th>
                  <th className="py-3 px-2">Type</th>
                  <th className="py-3 px-2 text-center">Interv.</th>
                  <th className="py-3 px-2 text-right">Coût Int.</th>
                  <th className="py-3 px-2 text-right">Coût Pièces</th>
                  <th className="py-3 px-2 text-right">Coût MO</th>
                  <th className="py-3 px-2 text-right font-bold">TCO Total</th>
                  <th className="py-3 px-2 text-right">TCO/mois</th>
                </tr>
              </thead>
              <tbody>
                {(tcoData || []).map((t: any, i: number) => (
                  <tr key={`${t.equipement}-${i}`} className="border-b border-savia-border/20 hover:bg-savia-surface-hover/20 transition-colors">
                    <td className="py-3 px-3">
                      <div className="font-bold">{t.equipement}</div>
                      {t.age_jours > 0 && <div className="text-[10px] text-savia-text-dim">{Math.round(t.age_jours / 365)}a {Math.round((t.age_jours % 365) / 30)}m</div>}
                    </td>
                    <td className="py-3 px-2 text-xs text-savia-text-muted">{t.client}</td>
                    <td className="py-3 px-2 text-xs">{t.type}</td>
                    <td className="py-3 px-2 text-center">
                      <span className="text-xs">{t.nb_correctives}c</span>
                      <span className="text-savia-text-dim mx-0.5">/</span>
                      <span className="text-xs text-green-400">{t.nb_preventives}p</span>
                    </td>
                    <td className="py-3 px-2 text-right font-mono text-red-400">{FMT(t.cout_interventions)}</td>
                    <td className="py-3 px-2 text-right font-mono text-orange-400">{FMT(t.cout_pieces)}</td>
                    <td className="py-3 px-2 text-right font-mono text-blue-400">{FMT(t.cout_main_oeuvre)}</td>
                    <td className="py-3 px-2 text-right font-bold font-mono text-savia-accent">{FMT(t.tco_total)}</td>
                    <td className="py-3 px-2 text-right text-xs text-savia-text-muted">{FMT(t.tco_mensuel)}/m</td>
                  </tr>
                ))}
                {(tcoData || []).length === 0 && (
                  <tr><td colSpan={9} className="py-8 text-center text-savia-text-muted">Aucune donnée TCO</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
