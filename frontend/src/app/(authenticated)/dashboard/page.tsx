'use client';
// ==========================================
// 📊 Dashboard Page — SAVIA
// ==========================================
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { KpiCard, HealthBadge, SectionCard } from '@/components/ui/cards';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, RadialBarChart, RadialBar, Legend,
  AreaChart, Area,
} from 'recharts';
import { dashboard, interventions as interventionsApi } from '@/lib/api';
import { Loader2, AlertTriangle, ChevronDown, ChevronUp, Clock } from 'lucide-react';

// --- Types ---
interface KpiData {
  nb_equipements: number;
  nb_critiques: number;
  disponibilite: number;
  mtbf: number;
  mttr: number;
  cout_total: number;
  nb_interventions: number;
}

interface HealthScore {
  machine: string;
  score: number;
  tendance: string;
  pannes: number;
}

const DEMO_MONTHLY = [
  { mois: 'Jan', corrective: 5, preventive: 3 },
  { mois: 'Fév', corrective: 3, preventive: 4 },
  { mois: 'Mar', corrective: 7, preventive: 2 },
  { mois: 'Avr', corrective: 4, preventive: 5 },
  { mois: 'Mai', corrective: 2, preventive: 6 },
  { mois: 'Jun', corrective: 6, preventive: 3 },
];

const DEMO_TYPES = [
  { name: 'Hardware', value: 35, color: '#ef4444' },
  { name: 'Software', value: 25, color: '#3b82f6' },
  { name: 'Calibration', value: 20, color: '#f59e0b' },
  { name: 'Power', value: 12, color: '#8b5cf6' },
  { name: 'Autre', value: 8, color: '#64748b' },
];

// --- Chart theme ---
const CHART_STYLE = {
  bg: '#1e293b',
  grid: '#334155',
  text: '#94a3b8',
  accent: '#2dd4bf',
  blue: '#3b82f6',
};

export default function DashboardPage() {
  const { user } = useAuth();
  const [kpis, setKpis] = useState<KpiData>({
    nb_equipements: 0, nb_critiques: 0, disponibilite: 100, mtbf: 0, mttr: 0, cout_total: 0, nb_interventions: 0
  });
  const [healthScores, setHealthScores] = useState<HealthScore[]>([]);
  const [recentInterv, setRecentInterv] = useState<any[]>([]);
  const [showAnomalies, setShowAnomalies] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [kpiData, healthData, intervData] = await Promise.all([
          dashboard.kpis(),
          dashboard.healthScores(),
          interventionsApi.list(),
        ]);
        setKpis(kpiData as any);
        setHealthScores(healthData);
        setRecentInterv((intervData || []).sort((a: any, b: any) => (b.date || '').localeCompare(a.date || '')).slice(0, 10));
      } catch (err) {
        console.error("Failed to load dashboard data", err);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, []);

  // Computed values
  const scoreGlobal = useMemo(() => {
    if (!healthScores.length) return 100;
    return Math.round(healthScores.reduce((s, h) => s + h.score, 0) / healthScores.length);
  }, [healthScores]);

  const nbCritique = healthScores.filter(h => h.score < 30).length;
  const nbAttention = healthScores.filter(h => h.score >= 30 && h.score < 60).length;
  const nbBon = healthScores.filter(h => h.score >= 60).length;

  const mtbfStr = kpis.mtbf >= 24
    ? `${Math.floor(kpis.mtbf / 24)}j ${Math.round(kpis.mtbf % 24)}h`
    : `${kpis.mtbf.toFixed(0)}h`;

  // Gauge data for RadialBarChart
  const gaugeData = [{ name: 'Santé', value: scoreGlobal, fill: scoreGlobal >= 60 ? '#2dd4bf' : scoreGlobal >= 30 ? '#f59e0b' : '#ef4444' }];

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
          <h1 className="text-2xl font-black gradient-text">📊 Dashboard</h1>
          <p className="text-savia-text-muted text-sm mt-1">
            Vue d&apos;ensemble — Maintenance Prédictive
          </p>
        </div>
        <div className="text-right text-xs text-savia-text-dim">
          👤 {user?.nom} · {user?.role}
        </div>
      </div>

      {/* KPIs Row */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard icon="🖥️" value={String(kpis.nb_equipements)} label="Équipements" />
        <KpiCard icon="🔴" value={String(kpis.nb_critiques)} label="Alertes Critiques" variant={kpis.nb_critiques > 0 ? 'danger' : 'default'} />
        <KpiCard icon="✅" value={`${kpis.disponibilite}%`} label="Disponibilité" variant="success" />
        <KpiCard icon="⏱️" value={mtbfStr} label="MTBF" tooltip="Temps moyen entre pannes" />
        <KpiCard icon="🔧" value={`${kpis.mttr.toFixed(1)}h`} label="MTTR" tooltip="Temps moyen de réparation" />
        <KpiCard icon="💰" value={`${kpis.cout_total.toLocaleString('fr')} EUR`} label="Coût Maintenance" />
      </div>

      {/* Score Santé + Gamification */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Score Santé du Jour */}
        <SectionCard title="📊 Score Santé du Jour">
          <div className="text-center">
            <div className={`text-5xl font-black ${scoreGlobal >= 60 ? 'text-savia-success' : scoreGlobal >= 30 ? 'text-savia-warning' : 'text-savia-danger'}`}>
              {scoreGlobal >= 60 ? '🟢' : scoreGlobal >= 30 ? '🟡' : '🔴'} {scoreGlobal}%
            </div>
            <div className="text-savia-text-muted text-sm mt-2">→ stable</div>
            <div className="w-full bg-savia-bg rounded-full h-2 mt-4 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-1000 ${scoreGlobal >= 60 ? 'bg-savia-success' : scoreGlobal >= 30 ? 'bg-savia-warning' : 'bg-savia-danger'}`}
                style={{ width: `${scoreGlobal}%` }}
              />
            </div>
          </div>
        </SectionCard>

        {/* Gamification */}
        <SectionCard title="🏆 Gamification — Équipe">
          <div className="text-center">
            <div className="text-5xl font-black text-savia-warning">
              {kpis.nb_interventions} <span className="text-lg">interventions</span>
            </div>
            <div className="text-savia-warning text-sm font-semibold mt-2">
              🥇 Niveau : Pro
            </div>
            <div className="text-savia-text-dim text-xs mt-1">
              📊 Total réalisé: {kpis.nb_interventions} | 🔥 Belle performance !
            </div>
          </div>
        </SectionCard>
      </div>

      {/* 🚨 Anomalies Detected */}
      {healthScores.filter(h => h.score < 40).length > 0 && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-xl overflow-hidden">
          <button onClick={() => setShowAnomalies(!showAnomalies)} className="w-full flex items-center justify-between p-4 cursor-pointer hover:bg-red-500/5 transition-colors">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-400" />
              <span className="font-bold text-red-400">🚨 {healthScores.filter(h => h.score < 40).length} anomalie(s) détectée(s)</span>
            </div>
            {showAnomalies ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
          </button>
          {showAnomalies && (
            <div className="px-4 pb-4 space-y-2">
              {healthScores.filter(h => h.score < 40).map(h => (
                <div key={h.machine} className="flex items-center justify-between p-3 rounded-lg bg-red-500/5 border-l-4 border-red-500">
                  <div>
                    <span className="font-bold text-sm">{h.machine}</span>
                    <span className="text-xs text-slate-400 ml-2">Score: {h.score}% — {h.pannes} pannes</span>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-red-500/20 text-red-400">
                    {h.score < 15 ? '🔴 Critique' : '🟠 Dégradé'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 📅 Timeline des Interventions Récentes */}
      <SectionCard title="📅 Timeline des Interventions Récentes">
        {recentInterv.length === 0 ? (
          <div className="text-center text-slate-400 py-4">Aucune intervention récente</div>
        ) : (
          <div className="relative pl-6">
            <div className="absolute left-3 top-0 bottom-0 w-0.5 bg-gradient-to-b from-savia-accent via-blue-500 to-purple-500" />
            {recentInterv.map((interv: any, i: number) => {
              const isCompleted = (interv.statut || '').toLowerCase().includes('tur');
              return (
                <div key={interv.id || i} className="relative mb-4 ml-4">
                  <div className={`absolute -left-[22px] top-1 w-3 h-3 rounded-full border-2 ${isCompleted ? 'bg-green-400 border-green-300' : 'bg-yellow-400 border-yellow-300'}`} />
                  <div className="glass rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-sm">{interv.machine}</span>
                      <span className="text-xs text-slate-400">{(interv.date || '').substring(0, 10)}</span>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${(interv.type_intervention || '').toLowerCase().includes('correct') ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}>{interv.type_intervention}</span>
                      <span className="text-xs text-slate-400">👤 {interv.technicien || 'N/A'}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${isCompleted ? 'bg-green-500/10 text-green-400' : 'bg-yellow-500/10 text-yellow-400'}`}>{interv.statut}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </SectionCard>


      {/* Health Animation Banner */}
      <div className="glass rounded-xl p-4 flex items-center gap-5">
        <div className="relative w-14 h-14 flex-shrink-0">
          <div className="absolute inset-0 rounded-full border-2 border-savia-accent animate-ping opacity-20" />
          <div className="absolute inset-2 rounded-full bg-gradient-to-br from-savia-accent to-savia-success animate-pulse shadow-lg shadow-savia-accent/30" />
        </div>
        <div>
          <div className="text-lg font-extrabold gradient-text">🫀 Santé du Parc d&apos;Équipements</div>
          <div className="text-savia-text-muted text-sm">📡 Monitoring en temps réel — Analyse prédictive active</div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Interventions par mois */}
        <SectionCard title="📈 Interventions / Mois" className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={DEMO_MONTHLY} barGap={4}>
              <XAxis dataKey="mois" stroke={CHART_STYLE.text} fontSize={12} />
              <YAxis stroke={CHART_STYLE.text} fontSize={12} />
              <Tooltip
                contentStyle={{ background: CHART_STYLE.bg, border: `1px solid ${CHART_STYLE.grid}`, borderRadius: 8, color: '#f1f5f9' }}
              />
              <Bar dataKey="corrective" name="Corrective" fill="#ef4444" radius={[4, 4, 0, 0]} />
              <Bar dataKey="preventive" name="Préventive" fill={CHART_STYLE.accent} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>

        {/* Répartition types erreurs */}
        <SectionCard title="🎯 Types d'Erreurs">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={DEMO_TYPES}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                paddingAngle={3}
                dataKey="value"
                stroke="none"
              >
                {DEMO_TYPES.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: CHART_STYLE.bg, border: `1px solid ${CHART_STYLE.grid}`, borderRadius: 8, color: '#f1f5f9' }}
              />
              <Legend
                wrapperStyle={{ fontSize: 11, color: CHART_STYLE.text }}
              />
            </PieChart>
          </ResponsiveContainer>
        </SectionCard>
      </div>

      {/* Health Scores Table + Gauge */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Table Santé */}
        <SectionCard title="🫀 Score de Santé" className="lg:col-span-2">
          {/* Mini KPIs */}
          <div className="flex gap-3 mb-4">
            <div className="flex-1 text-center p-3 rounded-lg bg-red-500/10 border border-red-500/20">
              <div className="text-2xl font-black text-savia-danger">{nbCritique}</div>
              <div className="text-xs text-red-300">🔴 Critique</div>
            </div>
            <div className="flex-1 text-center p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
              <div className="text-2xl font-black text-savia-warning">{nbAttention}</div>
              <div className="text-xs text-yellow-300">🟡 Attention</div>
            </div>
            <div className="flex-1 text-center p-3 rounded-lg bg-green-500/10 border border-green-500/20">
              <div className="text-2xl font-black text-savia-success">{nbBon}</div>
              <div className="text-xs text-green-300">🟢 Bon</div>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-savia-border">
                  <th className="text-left py-2 px-3 text-savia-text-muted font-semibold">Équipement</th>
                  <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">Santé</th>
                  <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">Tendance</th>
                  <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">Pannes</th>
                </tr>
              </thead>
              <tbody>
                {[...healthScores].sort((a, b) => a.score - b.score).map((h) => (
                  <tr key={h.machine} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                    <td className="py-2.5 px-3 font-medium">{h.machine}</td>
                    <td className="py-2.5 px-3 text-center">
                      <HealthBadge score={h.score} size="sm" />
                    </td>
                    <td className="py-2.5 px-3 text-center text-xs">
                      {h.tendance === 'hausse' ? '📈 Hausse' : h.tendance === 'baisse' ? '📉 Baisse' : '➡️ Stable'}
                    </td>
                    <td className="py-2.5 px-3 text-center font-mono">{h.pannes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>

        {/* Gauge Santé Globale */}
        <SectionCard title="🎯 Jauge Santé Globale">
          <ResponsiveContainer width="100%" height={280}>
            <RadialBarChart
              cx="50%"
              cy="50%"
              innerRadius="60%"
              outerRadius="90%"
              data={gaugeData}
              startAngle={180}
              endAngle={0}
              barSize={16}
            >
              <RadialBar
                dataKey="value"
                cornerRadius={8}
                background={{ fill: '#1e293b' }}
              />
              <text x="50%" y="55%" textAnchor="middle" fill="#f1f5f9" fontSize="32" fontWeight="800">
                {scoreGlobal}%
              </text>
              <text x="50%" y="68%" textAnchor="middle" fill="#94a3b8" fontSize="12">
                Santé Globale
              </text>
            </RadialBarChart>
          </ResponsiveContainer>
        </SectionCard>
      </div>

      {/* Disponibilité Trend */}
      <SectionCard title="📈 Tendance Disponibilité (6 mois)">
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={[
            { mois: 'Jan', dispo: 97.2 }, { mois: 'Fév', dispo: 96.5 },
            { mois: 'Mar', dispo: 95.8 }, { mois: 'Avr', dispo: 97.1 },
            { mois: 'Mai', dispo: 98.0 }, { mois: 'Jun', dispo: 96.8 },
          ]}>
            <defs>
              <linearGradient id="dispoGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={CHART_STYLE.accent} stopOpacity={0.3} />
                <stop offset="95%" stopColor={CHART_STYLE.accent} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="mois" stroke={CHART_STYLE.text} fontSize={12} />
            <YAxis domain={[94, 100]} stroke={CHART_STYLE.text} fontSize={12} />
            <Tooltip
              contentStyle={{ background: CHART_STYLE.bg, border: `1px solid ${CHART_STYLE.grid}`, borderRadius: 8, color: '#f1f5f9' }}
              formatter={(value) => [`${value}%`, 'Disponibilité']}
            />
            <Area type="monotone" dataKey="dispo" stroke={CHART_STYLE.accent} fill="url(#dispoGrad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </SectionCard>

      {/* Footer */}
      <div className="text-center py-4 border-t border-savia-border/50">
        <span className="gradient-text font-bold text-sm">SAVIA</span>
        <span className="text-savia-text-dim text-xs ml-2">
          Powered by SIC Radiologie • Maintenance Prédictive
        </span>
      </div>
    </div>
  );
}
