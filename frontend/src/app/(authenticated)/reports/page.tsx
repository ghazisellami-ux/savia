'use client';
import { useState, useEffect, useMemo, useCallback } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { FileText, Download, Loader2, Sparkles, BarChart3, Users, Star, AlertTriangle } from 'lucide-react';
import { interventions, equipements, ai, contrats } from '@/lib/api';

const TAB_CLS = "px-4 py-2.5 text-sm font-semibold rounded-t-lg transition-all cursor-pointer border-b-2";
const TAB_ACTIVE = "border-cyan-400 text-cyan-400 bg-cyan-400/5";
const TAB_INACTIVE = "border-transparent text-slate-400 hover:text-white hover:border-slate-500";
const INPUT_CLS = "w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-white placeholder:text-slate-500 focus:ring-2 focus:ring-cyan-500/40 outline-none transition-all";

export default function ReportsPage() {
  const [activeTab, setActiveTab] = useState(0);
  const [data, setData] = useState<any[]>([]);
  const [equips, setEquips] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [aiReport, setAiReport] = useState('');

  // Monthly report
  const now = new Date();
  const [selMois, setSelMois] = useState(now.getMonth() + 1);
  const [selAnnee, setSelAnnee] = useState(now.getFullYear());

  // Client report
  const [selClient, setSelClient] = useState('');
  const [selClientMois, setSelClientMois] = useState(now.getMonth() + 1);
  const [selClientAnnee, setSelClientAnnee] = useState(now.getFullYear());

  // IA report
  const [iaClient, setIaClient] = useState('Tous les clients');
  const [iaPeriode, setIaPeriode] = useState('Mensuel');
  const [iaMois, setIaMois] = useState(now.getMonth() + 1);
  const [iaAnnee, setIaAnnee] = useState(now.getFullYear());

  // Compare
  const [compareMode, setCompareMode] = useState('Client');

  const loadData = useCallback(async () => {
    try {
      const [intv, eqs] = await Promise.all([interventions.list(), equipements.list()]);
      setData(intv);
      setEquips(eqs);
      // Set default client
      const clients = [...new Set((eqs as any[]).map((e: any) => e.Client).filter(Boolean))].sort();
      if (clients.length > 0) setSelClient(clients[0] as string);
    } catch (err) { console.error(err); }
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const clients = useMemo(() => [...new Set((equips as any[]).map((e: any) => e.Client).filter(Boolean))].sort() as string[], [equips]);

  const machineToClient = useMemo(() => {
    const map: Record<string, string> = {};
    (equips as any[]).forEach((e: any) => { if (e.Nom && e.Client) map[e.Nom] = e.Client; });
    return map;
  }, [equips]);

  // Filter data by period
  const filterByPeriod = (d: any[], mois: number | null, annee: number) => {
    return d.filter((i: any) => {
      const dt = new Date(i.date);
      if (isNaN(dt.getTime())) return false;
      if (mois !== null && dt.getMonth() + 1 !== mois) return false;
      if (dt.getFullYear() !== annee) return false;
      return true;
    });
  };

  const filterByClient = (d: any[], client: string) => {
    if (client === 'Tous les clients') return d;
    const machines = (equips as any[]).filter((e: any) => e.Client === client).map((e: any) => e.Nom);
    return d.filter((i: any) => machines.includes(i.machine));
  };

  // AI Report generation
  const handleAiReport = async () => {
    setIsGenerating(true);
    setAiReport('');
    try {
      let periodeData = iaPeriode === 'Mensuel' ? filterByPeriod(data, iaMois, iaAnnee) : filterByPeriod(data, null, iaAnnee);
      periodeData = filterByClient(periodeData, iaClient);

      const nb = periodeData.length;
      const nbClot = periodeData.filter((i: any) => (i.statut || '').toLowerCase().includes('tur')).length;
      const types: Record<string, number> = {};
      const machinesTop: Record<string, number> = {};
      periodeData.forEach((i: any) => {
        const t = i.type_intervention || 'Autre';
        types[t] = (types[t] || 0) + 1;
        const m = `${i.machine} (${machineToClient[i.machine] || '?'})`;
        machinesTop[m] = (machinesTop[m] || 0) + 1;
      });
      const dureeMoy = nb > 0 ? Math.round(periodeData.reduce((a: number, b: any) => a + (b.duree_minutes || 0), 0) / nb) : 0;
      const coutTotal = periodeData.reduce((a: number, b: any) => a + (b.cout || 0), 0);

      const periodeLabel = iaPeriode === 'Mensuel' ? `${iaMois}/${iaAnnee}` : `Année ${iaAnnee}`;
      const clientLabel = iaClient;

      const kpis = {
        prompt_override: `Agis en tant qu'Auditeur Qualité Sénior et Directeur des Opérations pour un réseau de maintenance d'imagerie médicale.
Analyse ces données ${iaPeriode.toLowerCase()} et génère un rapport qualitatif.

Données pour ${clientLabel} — Période : ${periodeLabel}
- ${nb} interventions (${nbClot} clôturées)
- Types : ${JSON.stringify(types)}
- Top machines en panne : ${JSON.stringify(machinesTop)}
- Durée moyenne : ${dureeMoy} min
- Coût total : ${coutTotal.toLocaleString('fr')} TND

Génère un rapport structuré avec ces sections EXACTES :
📊 RÉSUMÉ EXÉCUTIF
📈 TENDANCES & PANNES FRÉQUENTES
⚠️ POINTS DE VULNÉRABILITÉ
✅ PLAN D'ACTION
💰 RENTABILITÉ & ANALYSE FINANCIÈRE
📋 SCORE DE PERFORMANCE (note /100)`
      };

      const res = await ai.analyzePerformance(kpis as any, 'TND');
      if (res.ok && res.result) {
        setAiReport(typeof res.result === 'string' ? res.result : JSON.stringify(res.result, null, 2));
      } else {
        setAiReport("L'IA n'a pas pu générer le rapport.");
      }
    } catch (err: any) {
      setAiReport(`Erreur: ${err?.message || 'Indisponible'}`);
    } finally { setIsGenerating(false); }
  };

  const tabs = [
    { icon: '📄', label: 'Rapport Mensuel' },
    { icon: '🏢', label: 'Rapport Client' },
    { icon: '🤖', label: 'Rapport IA' },
    { icon: '📊', label: 'Comparaison' },
    { icon: '⭐', label: 'Fiabilité' },
  ];

  if (isLoading) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-black gradient-text">📊 Rapports & Exports</h1>
        <p className="text-savia-text-muted text-sm mt-1">Génération de rapports PDF, analyses IA et comparaisons</p>
      </div>

      <div className="flex gap-1 border-b border-savia-border overflow-x-auto">
        {tabs.map((tab, i) => (
          <button key={i} onClick={() => setActiveTab(i)} className={`${TAB_CLS} ${activeTab === i ? TAB_ACTIVE : TAB_INACTIVE} whitespace-nowrap`}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 0: RAPPORT MENSUEL */}
      {activeTab === 0 && (
        <div className="space-y-6">
          <SectionCard title="📄 Rapport Mensuel Global">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
              <div><label className="block text-sm text-slate-400 mb-1">Mois</label>
                <select className={INPUT_CLS} value={selMois} onChange={e => setSelMois(Number(e.target.value))}>
                  {Array.from({length: 12}, (_, i) => <option key={i+1} value={i+1}>{i+1}</option>)}
                </select></div>
              <div><label className="block text-sm text-slate-400 mb-1">Année</label>
                <input type="number" className={INPUT_CLS} value={selAnnee} min={2020} max={2030} onChange={e => setSelAnnee(Number(e.target.value))} /></div>
              <button className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer">
                <FileText className="w-4 h-4" /> Générer le Rapport
              </button>
            </div>
          </SectionCard>

          {/* Preview */}
          {(() => {
            const monthData = filterByPeriod(data, selMois, selAnnee);
            const nbIntv = monthData.length;
            const nbClot = monthData.filter((i: any) => (i.statut || '').toLowerCase().includes('tur')).length;
            const cout = monthData.reduce((a: number, b: any) => a + (b.cout || 0), 0);
            return (
              <div className="grid grid-cols-3 gap-4">
                <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-savia-accent">{nbIntv}</div><div className="text-xs text-slate-400 mt-1">Interventions</div></div>
                <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-green-400">{nbClot}</div><div className="text-xs text-slate-400 mt-1">Clôturées</div></div>
                <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-red-400">{cout.toLocaleString('fr')}</div><div className="text-xs text-slate-400 mt-1">Coût total (TND)</div></div>
              </div>
            );
          })()}
        </div>
      )}

      {/* TAB 1: RAPPORT CLIENT */}
      {activeTab === 1 && (
        <div className="space-y-6">
          <SectionCard title="🏢 Rapport Client Mensuel">
            <p className="text-sm text-slate-400 mb-4">Générez un rapport PDF par client avec interventions, coûts et disponibilité.</p>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div><label className="block text-sm text-slate-400 mb-1">Client</label>
                <select className={INPUT_CLS} value={selClient} onChange={e => setSelClient(e.target.value)}>
                  {clients.map(c => <option key={c} value={c}>{c}</option>)}
                </select></div>
              <div><label className="block text-sm text-slate-400 mb-1">Mois</label>
                <select className={INPUT_CLS} value={selClientMois} onChange={e => setSelClientMois(Number(e.target.value))}>
                  {Array.from({length: 12}, (_, i) => <option key={i+1} value={i+1}>{i+1}</option>)}
                </select></div>
              <div><label className="block text-sm text-slate-400 mb-1">Année</label>
                <input type="number" className={INPUT_CLS} value={selClientAnnee} min={2020} max={2030} onChange={e => setSelClientAnnee(Number(e.target.value))} /></div>
              <button className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer">
                <FileText className="w-4 h-4" /> Générer Rapport Client
              </button>
            </div>
          </SectionCard>

          {/* Client preview */}
          {selClient && (() => {
            const clientMachines = (equips as any[]).filter((e: any) => e.Client === selClient).map((e: any) => e.Nom);
            const clientData = data.filter((i: any) => clientMachines.includes(i.machine)).filter((i: any) => {
              const dt = new Date(i.date);
              return dt.getMonth() + 1 === selClientMois && dt.getFullYear() === selClientAnnee;
            });
            const nbIntv = clientData.length;
            const coutIntv = clientData.reduce((a: number, b: any) => a + (b.cout || 0), 0);
            const coutPieces = clientData.reduce((a: number, b: any) => a + (b.cout_pieces || 0), 0);
            return nbIntv > 0 ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="glass rounded-xl p-4 text-center border border-blue-500/20"><div className="text-sm text-blue-400 font-bold mb-1">📥 Interventions</div><div className="text-2xl font-black text-blue-400">{nbIntv}</div></div>
                  <div className="glass rounded-xl p-4 text-center border border-purple-500/20"><div className="text-sm text-purple-400 font-bold mb-1">📤 Coût</div><div className="text-2xl font-black text-purple-400">{coutIntv.toLocaleString('fr')} TND</div></div>
                  <div className="glass rounded-xl p-4 text-center border border-cyan-500/20"><div className="text-sm text-cyan-400 font-bold mb-1">🔩 Pièces</div><div className="text-2xl font-black text-cyan-400">{coutPieces.toLocaleString('fr')} TND</div></div>
                </div>
                <SectionCard title="Détail des interventions">
                  <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-slate-900">
                        <tr className="border-b border-savia-border">
                          {['Date', 'Machine', 'Type', 'Technicien', 'Statut', 'Coût'].map(h => (
                            <th key={h} className="text-left py-2 px-2 text-savia-text-muted">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {clientData.map((i: any) => (
                          <tr key={i.id} className="border-b border-savia-border/30">
                            <td className="py-1.5 px-2">{(i.date || '').substring(0, 10)}</td>
                            <td className="py-1.5 px-2 font-semibold">{i.machine}</td>
                            <td className="py-1.5 px-2">{i.type_intervention}</td>
                            <td className="py-1.5 px-2">{i.technicien}</td>
                            <td className="py-1.5 px-2">{i.statut}</td>
                            <td className="py-1.5 px-2 font-mono">{(i.cout || 0).toLocaleString('fr')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </SectionCard>
              </div>
            ) : <div className="glass rounded-xl p-6 text-center text-slate-400">Aucune intervention pour {selClient} en {selClientMois}/{selClientAnnee}.</div>;
          })()}
        </div>
      )}

      {/* TAB 2: RAPPORT IA */}
      {activeTab === 2 && (
        <div className="space-y-6">
          <SectionCard title="🤖 Rapport IA (Gemini)">
            <p className="text-sm text-slate-400 mb-4">Gemini analyse vos données et génère un rapport avec tendances, risques et recommandations.</p>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div><label className="block text-sm text-slate-400 mb-1">📆 Période</label>
                <select className={INPUT_CLS} value={iaPeriode} onChange={e => setIaPeriode(e.target.value)}>
                  <option>Mensuel</option><option>Annuel</option>
                </select></div>
              {iaPeriode === 'Mensuel' && <div><label className="block text-sm text-slate-400 mb-1">Mois</label>
                <select className={INPUT_CLS} value={iaMois} onChange={e => setIaMois(Number(e.target.value))}>
                  {Array.from({length: 12}, (_, i) => <option key={i+1} value={i+1}>{i+1}</option>)}
                </select></div>}
              <div><label className="block text-sm text-slate-400 mb-1">Année</label>
                <input type="number" className={INPUT_CLS} value={iaAnnee} min={2020} max={2030} onChange={e => setIaAnnee(Number(e.target.value))} /></div>
              <div><label className="block text-sm text-slate-400 mb-1">🏢 Client</label>
                <select className={INPUT_CLS} value={iaClient} onChange={e => setIaClient(e.target.value)}>
                  <option>Tous les clients</option>
                  {clients.map(c => <option key={c} value={c}>{c}</option>)}
                </select></div>
            </div>
            <button onClick={handleAiReport} disabled={isGenerating} className="flex items-center justify-center gap-2 px-6 py-3 rounded-lg font-bold text-white bg-gradient-to-r from-purple-600 to-pink-500 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-purple-500/20 w-full mt-4 disabled:opacity-50">
              {isGenerating ? <Loader2 className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
              {isGenerating ? '🧠 Gemini analyse vos données...' : '🧠 Générer le Rapport IA'}
            </button>
          </SectionCard>

          {aiReport && (
            <div className="space-y-4">
              {/* Parse into styled sections */}
              {(() => {
                const sections: {key: string, color: string, icon: string, content: string}[] = [];
                const sectionMap: Record<string, {color: string, icon: string}> = {
                  'RÉSUMÉ': {color: '#3b82f6', icon: '📊'},
                  'TENDANCES': {color: '#8b5cf6', icon: '📈'},
                  'VULNÉRABILITÉ': {color: '#ef4444', icon: '⚠️'},
                  'PLAN': {color: '#10b981', icon: '✅'},
                  'RECOMMANDATIONS': {color: '#10b981', icon: '✅'},
                  'RENTABILITÉ': {color: '#f59e0b', icon: '💰'},
                  'ANALYSE': {color: '#f59e0b', icon: '💰'},
                  'SCORE': {color: '#06b6d4', icon: '📋'},
                };
                let currentKey = '';
                let currentContent = '';
                const reportText = typeof aiReport === 'string' ? aiReport : JSON.stringify(aiReport, null, 2);
                reportText.split('\n').forEach(line => {
                  const clean = line.replace(/[#*]/g, '').trim().toUpperCase();
                  let found = false;
                  for (const [key, val] of Object.entries(sectionMap)) {
                    if (clean.includes(key) && clean.length < 80) {
                      if (currentKey) sections.push({key: currentKey, ...sectionMap[currentKey] || {color: '#64748b', icon: '📌'}, content: currentContent.trim()});
                      currentKey = key;
                      currentContent = '';
                      found = true;
                      break;
                    }
                  }
                  if (!found && currentKey) currentContent += line + '\n';
                });
                if (currentKey) sections.push({key: currentKey, ...sectionMap[currentKey] || {color: '#64748b', icon: '📌'}, content: currentContent.trim()});

                if (sections.length === 0) {
                  return <div className="glass rounded-xl p-5 whitespace-pre-wrap text-sm text-slate-300">{reportText}</div>;
                }

                return sections.map((sec, i) => (
                  <div key={i} className="rounded-xl p-5" style={{ background: `${sec.color}08`, borderLeft: `4px solid ${sec.color}` }}>
                    <h4 className="font-bold text-sm uppercase tracking-wider mb-3" style={{ color: sec.color }}>{sec.icon} {sec.key}</h4>
                    <div className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">{sec.content}</div>
                  </div>
                ));
              })()}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: COMPARAISON */}
      {activeTab === 3 && (
        <div className="space-y-6">
          <SectionCard title="📊 Comparaison Inter-Clients / Inter-Équipements">
            <div className="flex gap-4 mb-4">
              {['Client', 'Équipement'].map(m => (
                <button key={m} onClick={() => setCompareMode(m)}
                  className={`px-4 py-2 rounded-lg text-sm font-bold transition-all cursor-pointer ${compareMode === m ? 'bg-savia-accent text-black' : 'bg-slate-800 text-slate-400 hover:text-white'}`}>
                  {m}
                </button>
              ))}
            </div>

            {(() => {
              const groupKey = compareMode === 'Client' ? 'client' : 'machine';
              const groups: Record<string, {nb: number, duree: number, corrective: number}> = {};
              data.forEach((i: any) => {
                const key = groupKey === 'client' ? (machineToClient[i.machine] || 'Non spécifié') : (i.machine || 'Inconnu');
                if (!groups[key]) groups[key] = {nb: 0, duree: 0, corrective: 0};
                groups[key].nb++;
                groups[key].duree += (i.duree_minutes || 0);
                if ((i.type_intervention || '').toLowerCase().includes('correct')) groups[key].corrective++;
              });
              const sorted = Object.entries(groups).sort((a, b) => b[1].nb - a[1].nb);

              return (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-savia-border">
                        <th className="text-left py-2 px-3 text-savia-text-muted">{compareMode}</th>
                        <th className="text-center py-2 px-3 text-savia-text-muted">🔧 Interventions</th>
                        <th className="text-center py-2 px-3 text-savia-text-muted">⚠️ Correctives</th>
                        <th className="text-center py-2 px-3 text-savia-text-muted">⏱️ Heures</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sorted.map(([key, stats]) => (
                        <tr key={key} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50">
                          <td className="py-2.5 px-3 font-bold">{key}</td>
                          <td className="py-2.5 px-3 text-center font-mono">{stats.nb}</td>
                          <td className="py-2.5 px-3 text-center font-mono text-red-400">{stats.corrective}</td>
                          <td className="py-2.5 px-3 text-center font-mono">{(stats.duree / 60).toFixed(1)}h</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {/* Visual bar representation */}
                  <div className="mt-4 space-y-2">
                    {sorted.slice(0, 10).map(([key, stats]) => {
                      const maxNb = Math.max(...sorted.map(s => s[1].nb));
                      return (
                        <div key={key} className="flex items-center gap-3">
                          <div className="w-32 text-xs text-slate-400 truncate text-right">{key}</div>
                          <div className="flex-1 bg-slate-800 rounded-full h-4 overflow-hidden">
                            <div className="bg-gradient-to-r from-cyan-500 to-blue-500 h-full rounded-full" style={{ width: `${(stats.nb / maxNb * 100)}%` }} />
                          </div>
                          <div className="w-8 text-xs font-mono text-slate-400">{stats.nb}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}
          </SectionCard>
        </div>
      )}

      {/* TAB 4: FIABILITÉ */}
      {activeTab === 4 && (
        <div className="space-y-6">
          <SectionCard title="⭐ Fiabilité des Équipements">
            {(() => {
              const machineStats: Record<string, {pannes: number, mttr: number, count: number, lastPanne: string}> = {};
              data.forEach((i: any) => {
                const m = i.machine || 'Inconnu';
                if (!machineStats[m]) machineStats[m] = {pannes: 0, mttr: 0, count: 0, lastPanne: ''};
                machineStats[m].pannes++;
                machineStats[m].mttr += (i.duree_minutes || 0);
                machineStats[m].count++;
                const d = i.date || '';
                if (d > (machineStats[m].lastPanne || '')) machineStats[m].lastPanne = d;
              });
              const fiab = Object.entries(machineStats).map(([machine, stats]) => {
                const mttr = stats.count > 0 ? Math.round(stats.mttr / stats.count / 60 * 10) / 10 : 0;
                const score = Math.max(0, Math.min(100, 100 - stats.pannes * 10));
                return { machine, pannes: stats.pannes, mttr, score, client: machineToClient[machine] || '?', lastPanne: stats.lastPanne.substring(0, 10) };
              }).sort((a, b) => a.score - b.score);

              return (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-savia-border">
                        {['Équipement', 'Client', 'Score', 'Pannes', 'MTTR', 'Dernière panne'].map(h => (
                          <th key={h} className="text-left py-2 px-3 text-savia-text-muted">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {fiab.map(f => (
                        <tr key={f.machine} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50">
                          <td className="py-2.5 px-3 font-bold">{f.machine}</td>
                          <td className="py-2.5 px-3 text-sm text-slate-400">{f.client}</td>
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-2">
                              <div className="w-16 bg-slate-800 rounded-full h-2 overflow-hidden">
                                <div className={`h-full rounded-full ${f.score >= 60 ? 'bg-green-400' : f.score >= 30 ? 'bg-yellow-400' : 'bg-red-400'}`} style={{ width: `${f.score}%` }} />
                              </div>
                              <span className={`text-xs font-bold ${f.score >= 60 ? 'text-green-400' : f.score >= 30 ? 'text-yellow-400' : 'text-red-400'}`}>{f.score}%</span>
                            </div>
                          </td>
                          <td className="py-2.5 px-3 font-mono text-red-400">{f.pannes}</td>
                          <td className="py-2.5 px-3 font-mono">{f.mttr}h</td>
                          <td className="py-2.5 px-3 text-xs text-slate-400">{f.lastPanne}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })()}
          </SectionCard>
        </div>
      )}
    </div>
  );
}
