'use client';
import { useState } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid } from 'recharts';
import { Brain, TrendingUp, AlertTriangle, Clock } from 'lucide-react';

const PREDICTION_DATA = [
  { machine: 'Scanner CT-01', risque: 78, joursAvantPanne: 12, composant: 'Tube RX', confiance: 85 },
  { machine: 'Mammographe GE', risque: 92, joursAvantPanne: 5, composant: 'Paddle compression', confiance: 91 },
  { machine: 'Arceau C-Arm', risque: 45, joursAvantPanne: 45, composant: 'Moteur rotation', confiance: 72 },
  { machine: 'IRM Siemens 3T', risque: 35, joursAvantPanne: 60, composant: 'Compresseur Hélium', confiance: 68 },
  { machine: 'Angiographe Biplan', risque: 65, joursAvantPanne: 22, composant: 'Détecteur flat panel', confiance: 79 },
];

const TREND_DATA = [
  { mois: 'Oct', pannes: 3, preventives: 8 },
  { mois: 'Nov', pannes: 5, preventives: 7 },
  { mois: 'Dec', pannes: 2, preventives: 9 },
  { mois: 'Jan', pannes: 4, preventives: 10 },
  { mois: 'Fev', pannes: 1, preventives: 11 },
  { mois: 'Mar', pannes: 3, preventives: 12 },
];

export default function PredictionsPage() {
  const critiques = PREDICTION_DATA.filter(p => p.risque >= 70).length;
  const attention = PREDICTION_DATA.filter(p => p.risque >= 40 && p.risque < 70).length;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-black gradient-text">🔮 Prédictions & Maintenance Préventive</h1>
        <p className="text-savia-text-muted text-sm mt-1">Analyse prédictive IA des pannes et recommandations</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: '🔴 Critiques', value: critiques, color: 'text-red-400' },
          { label: '🟡 Attention', value: attention, color: 'text-yellow-400' },
          { label: '📊 Précision IA', value: '84%', color: 'text-savia-accent' },
          { label: '💰 Économies', value: '32K€', color: 'text-green-400' },
        ].map(k => (
          <div key={k.label} className="glass rounded-xl p-4 text-center">
            <div className={`text-3xl font-black ${k.color}`}>{k.value}</div>
            <div className="text-xs text-savia-text-muted mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      <SectionCard title="⚠️ Risques de Panne par Machine">
        <div className="space-y-3">
          {PREDICTION_DATA.sort((a, b) => b.risque - a.risque).map(p => (
            <div key={p.machine} className="flex items-center gap-4 p-3 rounded-lg bg-savia-bg/50 hover:bg-savia-surface-hover/30 transition-colors">
              <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-savia-surface">
                {p.risque >= 70 ? '🔴' : p.risque >= 40 ? '🟡' : '🟢'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-bold text-sm">{p.machine}</div>
                <div className="text-xs text-savia-text-muted">{p.composant} — {p.joursAvantPanne}j avant panne estimée</div>
              </div>
              <div className="w-32">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-savia-text-dim">Risque</span>
                  <span className={`font-bold ${p.risque >= 70 ? 'text-red-400' : p.risque >= 40 ? 'text-yellow-400' : 'text-green-400'}`}>{p.risque}%</span>
                </div>
                <div className="w-full h-2 bg-savia-bg rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${p.risque >= 70 ? 'bg-red-500' : p.risque >= 40 ? 'bg-yellow-500' : 'bg-green-500'}`} style={{ width: `${p.risque}%` }} />
                </div>
              </div>
              <span className="text-xs px-2 py-1 rounded-full bg-blue-500/10 text-blue-400 font-semibold">
                🎯 {p.confiance}%
              </span>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="📈 Tendance Pannes vs Préventives (6 mois)">
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={TREND_DATA}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(45,212,191,0.1)" />
            <XAxis dataKey="mois" stroke="#64748b" fontSize={12} />
            <YAxis stroke="#64748b" fontSize={12} />
            <Tooltip contentStyle={{ background: '#0f1729', border: '1px solid rgba(45,212,191,0.2)', borderRadius: 8, color: '#f1f5f9' }} />
            <Bar dataKey="pannes" fill="#ef4444" radius={[4, 4, 0, 0]} name="Pannes" />
            <Bar dataKey="preventives" fill="#2dd4bf" radius={[4, 4, 0, 0]} name="Préventives" />
          </BarChart>
        </ResponsiveContainer>
      </SectionCard>
    </div>
  );
}
