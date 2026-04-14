'use client';
import { useState, useEffect } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { CheckCircle, XCircle, AlertTriangle, Clock, Loader2 } from 'lucide-react';
import { conformite } from '@/lib/api';

interface ConformiteItem {
  machine: string;
  client: string;
  dernierControle: string;
  prochainControle: string;
  statut: string;
  score: number;
  items: { label: string; ok: boolean }[];
}

export default function ConformitePage() {
  const [data, setData] = useState<ConformiteItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const res = await conformite.list();
        const mapped = res.map((item: any) => {
          const score = item.Score_Conformite || item.score || 0;
          return {
            machine: item.Equipement || item.machine || 'Générique',
            client: item.Client || item.client || '',
            dernierControle: item.Date_Dernier_Controle ? item.Date_Dernier_Controle.substring(0, 10) : 'N/A',
            prochainControle: item.Date_Prochain_Controle ? item.Date_Prochain_Controle.substring(0, 10) : 'N/A',
            statut: item.Statut || (score >= 80 ? 'Conforme' : 'Non conforme'),
            score: score,
            items: item.items || [
              { label: 'Dosimétrie', ok: score > 70 },
              { label: 'Sécurité électrique', ok: score > 50 },
              { label: 'Radioprotection', ok: score > 85 },
              { label: 'CQ image', ok: score > 90 }
            ],
          };
        });
        setData(mapped);
      } catch (err) {
        console.error("Failed to fetch conformite data", err);
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, []);

  const conformes = data.filter(c => c.statut === 'Conforme' || c.statut.toLowerCase().includes('conforme')).length;
  const nonConformes = data.length - conformes;
  const avgScore = data.length > 0 ? Math.round(data.reduce((a, b) => a + b.score, 0) / data.length) : 0;

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-savia-accent" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-black gradient-text">✅ Conformité Réglementaire</h1>
        <p className="text-savia-text-muted text-sm mt-1">Suivi des contrôles qualité et conformité</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-savia-accent">{data.length}</div><div className="text-xs text-savia-text-muted mt-1">Équipements suivis</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-green-400">{conformes}</div><div className="text-xs text-savia-text-muted mt-1">✅ Conformes</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-red-400">{nonConformes}</div><div className="text-xs text-savia-text-muted mt-1">❌ Non conformes</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className={`text-3xl font-black ${avgScore >= 80 ? 'text-green-400' : 'text-yellow-400'}`}>{avgScore}%</div><div className="text-xs text-savia-text-muted mt-1">Score moyen</div></div>
      </div>

      <div className="space-y-4">
        {data.map(c => (
          <div key={c.machine + c.client} className={`glass rounded-xl p-5 border-l-4 ${(c.statut === 'Conforme' || c.statut.toLowerCase().includes('conforme')) ? 'border-l-green-500' : 'border-l-red-500'}`}>
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-bold text-lg">{c.machine}</h3>
                <p className="text-savia-text-muted text-sm">🏢 {c.client}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-2xl font-black ${c.score >= 80 ? 'text-green-400' : c.score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>{c.score}%</span>
                {(c.statut === 'Conforme' || c.statut.toLowerCase().includes('conforme')) ? <CheckCircle className="w-5 h-5 text-green-400" /> : <XCircle className="w-5 h-5 text-red-400" />}
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
              {c.items.map(item => (
                <div key={item.label} className={`rounded-lg p-2 text-center text-xs font-semibold ${item.ok ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                  {item.ok ? '✅' : '❌'} {item.label}
                </div>
              ))}
            </div>
            <div className="flex gap-4 text-xs text-savia-text-muted">
              <span>📅 Dernier: {c.dernierControle}</span>
              <span>⏭️ Prochain: {c.prochainControle}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
