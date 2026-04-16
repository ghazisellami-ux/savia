'use client';
import { useState, useEffect, useMemo, useCallback } from 'react';
import { SectionCard } from '@/components/ui/cards';
import {
  FileText, Download, Loader2, Sparkles, BarChart3, Building2, Star,
  AlertTriangle, Calendar, Wrench, TrendingUp, DollarSign, CheckCircle2,
  ClipboardList, Target, Activity, ShieldCheck, Bot, ChevronRight
} from 'lucide-react';
import { interventions, equipements, ai } from '@/lib/api';

const TAB_CLS = "px-4 py-2.5 text-sm font-semibold rounded-t-lg transition-all cursor-pointer border-b-2";
const TAB_ACTIVE = "border-cyan-400 text-cyan-400 bg-cyan-400/5";
const TAB_INACTIVE = "border-transparent text-savia-text-muted hover:text-savia-text hover:border-slate-500";
const INPUT_CLS = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all";

const MOIS_LABELS = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];

export default function ReportsPage() {
  const [activeTab, setActiveTab] = useState(0);
  const [data, setData] = useState<any[]>([]);
  const [equips, setEquips] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isPdfGenerating, setIsPdfGenerating] = useState(false);
  const [aiReport, setAiReport] = useState<any>(null);
  const [pdfSuccess, setPdfSuccess] = useState('');

  const now = new Date();
  const [selMois, setSelMois] = useState(now.getMonth() + 1);
  const [selAnnee, setSelAnnee] = useState(now.getFullYear());
  const [selClient, setSelClient] = useState('');
  const [selClientMois, setSelClientMois] = useState(now.getMonth() + 1);
  const [selClientAnnee, setSelClientAnnee] = useState(now.getFullYear());
  const [iaClient, setIaClient] = useState('Tous les clients');
  const [iaPeriode, setIaPeriode] = useState('Mensuel');
  const [iaMois, setIaMois] = useState(now.getMonth() + 1);
  const [iaAnnee, setIaAnnee] = useState(now.getFullYear());
  const [compareMode, setCompareMode] = useState('Client');

  const loadData = useCallback(async () => {
    try {
      const [intv, eqs] = await Promise.all([interventions.list(), equipements.list()]);
      setData(intv);
      setEquips(eqs);
      const cls = [...new Set((eqs as any[]).map((e: any) => e.Client).filter(Boolean))].sort();
      if (cls.length > 0) setSelClient(cls[0] as string);
    } catch (err) { console.error(err); }
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const clients = useMemo(() =>
    [...new Set((equips as any[]).map((e: any) => e.Client).filter(Boolean))].sort() as string[], [equips]);

  const machineToClient = useMemo(() => {
    const map: Record<string, string> = {};
    (equips as any[]).forEach((e: any) => { if (e.Nom && e.Client) map[e.Nom] = e.Client; });
    return map;
  }, [equips]);

  const filterByPeriod = (d: any[], mois: number | null, annee: number) =>
    d.filter((i: any) => {
      const dt = new Date(i.date);
      if (isNaN(dt.getTime())) return false;
      if (mois !== null && dt.getMonth() + 1 !== mois) return false;
      return dt.getFullYear() === annee;
    });

  const filterByClient = (d: any[], client: string) => {
    if (client === 'Tous les clients') return d;
    const machines = (equips as any[]).filter((e: any) => e.Client === client).map((e: any) => e.Nom);
    return d.filter((i: any) => machines.includes(i.machine));
  };

  // --- PDF generation (browser print) ---
  const generatePdf = (title: string, htmlContent: string) => {
    setIsPdfGenerating(true);
    const win = window.open('', '_blank');
    if (!win) { setIsPdfGenerating(false); return; }
    win.document.write(`<!DOCTYPE html><html><head>
      <meta charset="utf-8"><title>${title}</title>
      <style>
        body{font-family:Arial,sans-serif;padding:32px;color:#1e293b;background:#fff}
        h1{color:#0891b2;font-size:24px;border-bottom:2px solid #0891b2;padding-bottom:8px}
        h2{color:#334155;font-size:16px;margin-top:20px}
        table{width:100%;border-collapse:collapse;margin-top:12px}
        th{background:#f1f5f9;padding:8px;text-align:left;font-size:12px;border-bottom:2px solid #e2e8f0}
        td{padding:7px 8px;font-size:12px;border-bottom:1px solid #f1f5f9}
        .kpi-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}
        .kpi{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;text-align:center}
        .kpi-val{font-size:28px;font-weight:900;color:#0891b2}
        .kpi-label{font-size:11px;color:#64748b;margin-top:4px}
        .footer{margin-top:40px;border-top:1px solid #e2e8f0;padding-top:12px;font-size:11px;color:#94a3b8}
      </style>
    </head><body>${htmlContent}<div class="footer">Généré par SAVIA — ${new Date().toLocaleString('fr-FR')} — SIC Radiologie</div></body></html>`);
    win.document.close();
    setTimeout(() => { win.print(); setIsPdfGenerating(false); setPdfSuccess('Rapport prêt à imprimer'); setTimeout(() => setPdfSuccess(''), 3000); }, 600);
  };

  const handlePdfMensuel = () => {
    const monthData = filterByPeriod(data, selMois, selAnnee);
    const nbIntv = monthData.length;
    const nbClot = monthData.filter((i: any) => (i.statut || '').toLowerCase().includes('tur')).length;
    const cout = monthData.reduce((a: number, b: any) => a + (b.cout || 0), 0);
    const types: Record<string, number> = {};
    monthData.forEach((i: any) => { const t = i.type_intervention || 'Autre'; types[t] = (types[t] || 0) + 1; });
    const rows = monthData.slice(0, 30).map((i: any) =>
      `<tr><td>${(i.date||'').substring(0,10)}</td><td>${i.machine||''}</td><td>${i.type_intervention||''}</td><td>${i.technicien||''}</td><td>${i.statut||''}</td><td>${(i.cout||0).toLocaleString('fr')} TND</td></tr>`
    ).join('');
    generatePdf(`Rapport Mensuel ${MOIS_LABELS[selMois-1]} ${selAnnee}`, `
      <h1>Rapport Mensuel — ${MOIS_LABELS[selMois-1]} ${selAnnee}</h1>
      <div class="kpi-grid">
        <div class="kpi"><div class="kpi-val">${nbIntv}</div><div class="kpi-label">Interventions</div></div>
        <div class="kpi"><div class="kpi-val">${nbClot}</div><div class="kpi-label">Clôturées</div></div>
        <div class="kpi"><div class="kpi-val">${cout.toLocaleString('fr')}</div><div class="kpi-label">Coût total (TND)</div></div>
      </div>
      <h2>Répartition par type</h2>
      <table><thead><tr><th>Type</th><th>Nombre</th></tr></thead><tbody>
      ${Object.entries(types).map(([t,n]) => `<tr><td>${t}</td><td>${n}</td></tr>`).join('')}
      </tbody></table>
      <h2>Détail des interventions (30 premières)</h2>
      <table><thead><tr><th>Date</th><th>Machine</th><th>Type</th><th>Technicien</th><th>Statut</th><th>Coût</th></tr></thead><tbody>${rows}</tbody></table>
    `);
  };

  const handlePdfClient = () => {
    const clientMachines = (equips as any[]).filter((e: any) => e.Client === selClient).map((e: any) => e.Nom);
    const clientData = data.filter((i: any) => clientMachines.includes(i.machine)).filter((i: any) => {
      const dt = new Date(i.date);
      return dt.getMonth() + 1 === selClientMois && dt.getFullYear() === selClientAnnee;
    });
    const nbIntv = clientData.length;
    const cout = clientData.reduce((a: number, b: any) => a + (b.cout || 0), 0);
    const coutPieces = clientData.reduce((a: number, b: any) => a + (b.cout_pieces || 0), 0);
    const rows = clientData.map((i: any) =>
      `<tr><td>${(i.date||'').substring(0,10)}</td><td>${i.machine||''}</td><td>${i.type_intervention||''}</td><td>${i.technicien||''}</td><td>${i.statut||''}</td><td>${(i.cout||0).toLocaleString('fr')} TND</td></tr>`
    ).join('');
    generatePdf(`Rapport Client ${selClient} — ${MOIS_LABELS[selClientMois-1]} ${selClientAnnee}`, `
      <h1>Rapport Client — ${selClient}</h1>
      <p>Période : ${MOIS_LABELS[selClientMois-1]} ${selClientAnnee}</p>
      <div class="kpi-grid">
        <div class="kpi"><div class="kpi-val">${nbIntv}</div><div class="kpi-label">Interventions</div></div>
        <div class="kpi"><div class="kpi-val">${cout.toLocaleString('fr')}</div><div class="kpi-label">Coût main d'œuvre (TND)</div></div>
        <div class="kpi"><div class="kpi-val">${coutPieces.toLocaleString('fr')}</div><div class="kpi-label">Coût pièces (TND)</div></div>
      </div>
      <h2>Détail des interventions</h2>
      <table><thead><tr><th>Date</th><th>Machine</th><th>Type</th><th>Technicien</th><th>Statut</th><th>Coût</th></tr></thead><tbody>${rows || '<tr><td colspan="6">Aucune intervention</td></tr>'}</tbody></table>
    `);
  };

  // --- AI Report using dedicated endpoint ---
  const handleAiReport = async () => {
    setIsGenerating(true);
    setAiReport(null);
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
      const periodeLabel = iaPeriode === 'Mensuel' ? `${MOIS_LABELS[iaMois-1]} ${iaAnnee}` : `Année ${iaAnnee}`;

      // Use analyzeSav which has its own prompt logic
      const res = await ai.analyzeSav({
        client: iaClient,
        periode: periodeLabel,
        nb_interventions: nb,
        nb_cloturees: nbClot,
        types_interventions: types,
        top_machines: machinesTop,
        duree_moyenne_min: dureeMoy,
        cout_total_tnd: coutTotal,
        nb_equipements: equips.length,
        taux_cloture_pct: nb > 0 ? Math.round(nbClot / nb * 100) : 0,
      }, 'TND');

      if (res.ok && res.result) {
        setAiReport(res.result);
      } else {
        setAiReport({ summary: "L'IA n'a pas pu générer le rapport." });
      }
    } catch (err: any) {
      setAiReport({ summary: `Erreur: ${err?.message || 'Indisponible'}` });
    } finally { setIsGenerating(false); }
  };

  const tabs = [
    { icon: <FileText className="w-4 h-4" />, label: 'Rapport Mensuel' },
    { icon: <Building2 className="w-4 h-4" />, label: 'Rapport Client' },
    { icon: <Bot className="w-4 h-4" />, label: 'Rapport IA' },
    { icon: <BarChart3 className="w-4 h-4" />, label: 'Comparaison' },
    { icon: <Star className="w-4 h-4" />, label: 'Fiabilité' },
  ];

  if (isLoading) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-black gradient-text flex items-center gap-2">
          <BarChart3 className="w-7 h-7 text-savia-accent" /> Rapports &amp; Exports
        </h1>
        <p className="text-savia-text-muted text-sm mt-1">Génération de rapports PDF, analyses IA et comparaisons</p>
      </div>

      {pdfSuccess && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-green-500/10 text-green-400 text-sm font-semibold">
          <CheckCircle2 className="w-4 h-4" /> {pdfSuccess}
        </div>
      )}

      <div className="flex gap-1 border-b border-savia-border overflow-x-auto">
        {tabs.map((tab, i) => (
          <button key={i} onClick={() => setActiveTab(i)} className={`${TAB_CLS} ${activeTab === i ? TAB_ACTIVE : TAB_INACTIVE} whitespace-nowrap flex items-center gap-2`}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 0: RAPPORT MENSUEL */}
      {activeTab === 0 && (
        <div className="space-y-6">
          <SectionCard title={<span className="flex items-center gap-2"><FileText className="w-4 h-4 text-savia-accent" /> Rapport Mensuel Global</span>}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
              <div><label className="block text-sm text-savia-text-muted mb-1">Mois</label>
                <select className={INPUT_CLS} value={selMois} onChange={e => setSelMois(Number(e.target.value))}>
                  {MOIS_LABELS.map((m, i) => <option key={i+1} value={i+1}>{m}</option>)}
                </select></div>
              <div><label className="block text-sm text-savia-text-muted mb-1">Année</label>
                <input type="number" className={INPUT_CLS} value={selAnnee} min={2020} max={2030} onChange={e => setSelAnnee(Number(e.target.value))} /></div>
              <button onClick={handlePdfMensuel} disabled={isPdfGenerating} className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer disabled:opacity-50">
                {isPdfGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />} Générer le Rapport PDF
              </button>
            </div>
          </SectionCard>

          {(() => {
            const monthData = filterByPeriod(data, selMois, selAnnee);
            const nbIntv = monthData.length;
            const nbClot = monthData.filter((i: any) => (i.statut || '').toLowerCase().includes('tur')).length;
            const cout = monthData.reduce((a: number, b: any) => a + (b.cout || 0), 0);
            const types: Record<string, number> = {};
            monthData.forEach((i: any) => { const t = i.type_intervention || 'Autre'; types[t] = (types[t] || 0) + 1; });
            return (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="glass rounded-xl p-4 text-center">
                    <Activity className="w-5 h-5 text-savia-accent mx-auto mb-1" />
                    <div className="text-3xl font-black text-savia-accent">{nbIntv}</div>
                    <div className="text-xs text-savia-text-muted mt-1">Interventions</div>
                  </div>
                  <div className="glass rounded-xl p-4 text-center">
                    <CheckCircle2 className="w-5 h-5 text-green-400 mx-auto mb-1" />
                    <div className="text-3xl font-black text-green-400">{nbClot}</div>
                    <div className="text-xs text-savia-text-muted mt-1">Clôturées</div>
                  </div>
                  <div className="glass rounded-xl p-4 text-center">
                    <DollarSign className="w-5 h-5 text-red-400 mx-auto mb-1" />
                    <div className="text-3xl font-black text-red-400">{cout.toLocaleString('fr')}</div>
                    <div className="text-xs text-savia-text-muted mt-1">Coût total (TND)</div>
                  </div>
                </div>
                {Object.keys(types).length > 0 && (
                  <div className="glass rounded-xl p-4">
                    <h3 className="text-sm font-bold text-savia-text-muted mb-3 flex items-center gap-2"><TrendingUp className="w-4 h-4" /> Répartition par type</h3>
                    <div className="space-y-2">
                      {Object.entries(types).sort((a,b)=>b[1]-a[1]).map(([t, n]) => (
                        <div key={t} className="flex items-center gap-3">
                          <div className="w-36 text-xs text-savia-text-muted truncate">{t}</div>
                          <div className="flex-1 bg-savia-surface-hover rounded-full h-3 overflow-hidden">
                            <div className="bg-gradient-to-r from-cyan-500 to-blue-500 h-full rounded-full" style={{ width: `${(n / nbIntv * 100)}%` }} />
                          </div>
                          <span className="text-xs font-mono font-bold w-6 text-right">{n}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}
        </div>
      )}

      {/* TAB 1: RAPPORT CLIENT */}
      {activeTab === 1 && (
        <div className="space-y-6">
          <SectionCard title={<span className="flex items-center gap-2"><Building2 className="w-4 h-4 text-savia-accent" /> Rapport Client Mensuel</span>}>
            <p className="text-sm text-savia-text-muted mb-4">Générez un rapport PDF par client avec interventions, coûts et disponibilité.</p>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div><label className="block text-sm text-savia-text-muted mb-1">Client</label>
                <select className={INPUT_CLS} value={selClient} onChange={e => setSelClient(e.target.value)}>
                  {clients.map(c => <option key={c} value={c}>{c}</option>)}
                </select></div>
              <div><label className="block text-sm text-savia-text-muted mb-1">Mois</label>
                <select className={INPUT_CLS} value={selClientMois} onChange={e => setSelClientMois(Number(e.target.value))}>
                  {MOIS_LABELS.map((m, i) => <option key={i+1} value={i+1}>{m}</option>)}
                </select></div>
              <div><label className="block text-sm text-savia-text-muted mb-1">Année</label>
                <input type="number" className={INPUT_CLS} value={selClientAnnee} min={2020} max={2030} onChange={e => setSelClientAnnee(Number(e.target.value))} /></div>
              <button onClick={handlePdfClient} disabled={isPdfGenerating || !selClient} className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer disabled:opacity-50">
                {isPdfGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />} Générer Rapport Client
              </button>
            </div>
          </SectionCard>

          {selClient && (() => {
            const clientMachines = (equips as any[]).filter((e: any) => e.Client === selClient).map((e: any) => e.Nom);
            const clientData = data.filter((i: any) => clientMachines.includes(i.machine) &&
              (() => { const dt = new Date(i.date); return dt.getMonth()+1 === selClientMois && dt.getFullYear() === selClientAnnee; })()
            );
            const nbIntv = clientData.length;
            const cout = clientData.reduce((a: number, b: any) => a + (b.cout || 0), 0);
            const coutPieces = clientData.reduce((a: number, b: any) => a + (b.cout_pieces || 0), 0);
            return nbIntv > 0 ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div className="glass rounded-xl p-4 text-center border border-blue-500/20">
                    <Activity className="w-5 h-5 text-blue-400 mx-auto mb-1" />
                    <div className="text-sm text-blue-400 font-bold">Interventions</div>
                    <div className="text-2xl font-black text-blue-400">{nbIntv}</div>
                  </div>
                  <div className="glass rounded-xl p-4 text-center border border-purple-500/20">
                    <DollarSign className="w-5 h-5 text-purple-400 mx-auto mb-1" />
                    <div className="text-sm text-purple-400 font-bold">Coût M.O.</div>
                    <div className="text-2xl font-black text-purple-400">{cout.toLocaleString('fr')} TND</div>
                  </div>
                  <div className="glass rounded-xl p-4 text-center border border-cyan-500/20">
                    <Wrench className="w-5 h-5 text-cyan-400 mx-auto mb-1" />
                    <div className="text-sm text-cyan-400 font-bold">Coût Pièces</div>
                    <div className="text-2xl font-black text-cyan-400">{coutPieces.toLocaleString('fr')} TND</div>
                  </div>
                </div>
                <SectionCard title="Détail des interventions">
                  <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-savia-surface">
                        <tr className="border-b border-savia-border">
                          {['Date','Machine','Type','Technicien','Statut','Coût'].map(h => (
                            <th key={h} className="text-left py-2 px-2 text-savia-text-muted">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {clientData.map((i: any) => (
                          <tr key={i.id} className="border-b border-savia-border/30 hover:bg-savia-surface-hover/50">
                            <td className="py-1.5 px-2">{(i.date||'').substring(0,10)}</td>
                            <td className="py-1.5 px-2 font-semibold">{i.machine}</td>
                            <td className="py-1.5 px-2">{i.type_intervention}</td>
                            <td className="py-1.5 px-2">{i.technicien}</td>
                            <td className="py-1.5 px-2">{i.statut}</td>
                            <td className="py-1.5 px-2 font-mono">{(i.cout||0).toLocaleString('fr')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </SectionCard>
              </div>
            ) : <div className="glass rounded-xl p-6 text-center text-savia-text-muted">Aucune intervention pour {selClient} en {MOIS_LABELS[selClientMois-1]} {selClientAnnee}.</div>;
          })()}
        </div>
      )}

      {/* TAB 2: RAPPORT IA */}
      {activeTab === 2 && (
        <div className="space-y-6">
          <SectionCard title={<span className="flex items-center gap-2"><Bot className="w-4 h-4 text-purple-400" /> Rapport IA (Gemini)</span>}>
            <p className="text-sm text-savia-text-muted mb-4">Gemini analyse vos données et génère un rapport avec tendances, risques et recommandations.</p>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> Période</label>
                <select className={INPUT_CLS} value={iaPeriode} onChange={e => setIaPeriode(e.target.value)}>
                  <option>Mensuel</option><option>Annuel</option>
                </select></div>
              {iaPeriode === 'Mensuel' && <div><label className="block text-sm text-savia-text-muted mb-1">Mois</label>
                <select className={INPUT_CLS} value={iaMois} onChange={e => setIaMois(Number(e.target.value))}>
                  {MOIS_LABELS.map((m, i) => <option key={i+1} value={i+1}>{m}</option>)}
                </select></div>}
              <div><label className="block text-sm text-savia-text-muted mb-1">Année</label>
                <input type="number" className={INPUT_CLS} value={iaAnnee} min={2020} max={2030} onChange={e => setIaAnnee(Number(e.target.value))} /></div>
              <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Building2 className="w-3.5 h-3.5" /> Client</label>
                <select className={INPUT_CLS} value={iaClient} onChange={e => setIaClient(e.target.value)}>
                  <option>Tous les clients</option>
                  {clients.map(c => <option key={c} value={c}>{c}</option>)}
                </select></div>
            </div>
            <button onClick={handleAiReport} disabled={isGenerating} className="flex items-center justify-center gap-2 px-6 py-3 rounded-lg font-bold text-white bg-gradient-to-r from-purple-600 to-pink-500 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-purple-500/20 w-full mt-4 disabled:opacity-50">
              {isGenerating ? <Loader2 className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
              {isGenerating ? 'Gemini analyse vos données...' : 'Générer le Rapport IA'}
            </button>
          </SectionCard>

          {aiReport && (
            <div className="space-y-4">
              {/* analyze-performance format */}
              {aiReport.alertes_critiques?.length > 0 && (
                <div className="p-4 rounded-xl bg-red-500/10 border-l-4 border-red-500">
                  <h4 className="font-bold text-sm text-red-400 uppercase tracking-wider mb-3 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> Alertes Critiques</h4>
                  <div className="space-y-3">
                    {aiReport.alertes_critiques.map((a: any, i: number) => (
                      <div key={i} className="p-3 rounded-lg bg-red-500/10 space-y-1">
                        <div className="flex items-center justify-between flex-wrap gap-2">
                          <span className="font-semibold text-sm">{a.machine}</span>
                          <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 font-bold">Score: {a.score_sante}% · Panne dans {a.jours_avant_panne}j</span>
                        </div>
                        <p className="text-xs text-savia-text-muted">{a.risque}</p>
                        <p className="text-xs text-red-400 flex items-center gap-1"><ChevronRight className="w-3 h-3" />{a.action_immediate}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {/* analyze-sav format */}
              {(aiReport.analyse || aiReport.score_global !== undefined) && (
                <div className="p-4 rounded-xl bg-blue-500/10 border-l-4 border-blue-500">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-bold text-sm text-blue-400 uppercase tracking-wider flex items-center gap-2"><ClipboardList className="w-4 h-4" /> Résumé Exécutif</h4>
                    {aiReport.score_global !== undefined && (
                      <span className={`px-3 py-1 rounded-full text-sm font-black ${aiReport.score_global >= 70 ? 'bg-green-500/20 text-green-400' : aiReport.score_global >= 40 ? 'bg-yellow-500/20 text-yellow-400' : 'bg-red-500/20 text-red-400'}`}>
                        Score: {aiReport.score_global}/100
                      </span>
                    )}
                  </div>
                  {aiReport.analyse && <p className="text-sm text-savia-text leading-relaxed">{aiReport.analyse}</p>}
                </div>
              )}
              {aiReport.points_forts?.length > 0 && (
                <div className="p-4 rounded-xl bg-green-500/10 border-l-4 border-green-500">
                  <h4 className="font-bold text-sm text-green-400 uppercase tracking-wider mb-3 flex items-center gap-2"><ShieldCheck className="w-4 h-4" /> Points Forts</h4>
                  <div className="space-y-1">
                    {aiReport.points_forts.map((p: string, i: number) => (
                      <div key={i} className="flex items-start gap-2 text-sm text-savia-text">
                        <CheckCircle2 className="w-4 h-4 text-green-400 mt-0.5 shrink-0" />{p}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {aiReport.points_faibles?.length > 0 && (
                <div className="p-4 rounded-xl bg-red-500/10 border-l-4 border-red-500">
                  <h4 className="font-bold text-sm text-red-400 uppercase tracking-wider mb-3 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> Points Faibles</h4>
                  <div className="space-y-1">
                    {aiReport.points_faibles.map((p: string, i: number) => (
                      <div key={i} className="flex items-start gap-2 text-sm text-savia-text">
                        <ChevronRight className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />{p}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {aiReport.recommandations?.length > 0 && !aiReport.recommandations[0]?.piece && (
                <div className="p-4 rounded-xl bg-yellow-500/10 border-l-4 border-yellow-500">
                  <h4 className="font-bold text-sm text-yellow-400 uppercase tracking-wider mb-3 flex items-center gap-2"><Target className="w-4 h-4" /> Recommandations</h4>
                  <div className="space-y-2">
                    {aiReport.recommandations.map((r: any, i: number) => (
                      <div key={i} className={`p-3 rounded-lg bg-yellow-500/5 border ${r.impact === 'HAUT' ? 'border-red-500/20' : r.impact === 'MOYEN' ? 'border-yellow-500/20' : 'border-savia-border'}`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-semibold text-sm">{r.titre}</span>
                          <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${r.impact === 'HAUT' ? 'bg-red-500/20 text-red-400' : r.impact === 'MOYEN' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'}`}>{r.impact}</span>
                        </div>
                        <p className="text-xs text-savia-text-muted">{r.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {/* Shared: machines_stables, plan_maintenance, estimation_couts, tendances, conclusion */}
              {aiReport.machines_stables?.length > 0 && (
                <div className="p-4 rounded-xl bg-green-500/10 border-l-4 border-green-500">
                  <h4 className="font-bold text-sm text-green-400 uppercase tracking-wider mb-3 flex items-center gap-2"><ShieldCheck className="w-4 h-4" /> Machines Stables</h4>
                  <div className="space-y-2">
                    {aiReport.machines_stables.map((m: any, i: number) => (
                      <div key={i} className="flex items-center justify-between p-2 rounded-lg bg-green-500/5">
                        <span className="font-semibold text-sm">{m.machine}</span>
                        <div className="flex items-center gap-3 text-xs">
                          <span className="text-green-400 font-bold">Score: {m.score_sante}%</span>
                          <span className="text-savia-text-muted">{m.commentaire}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {aiReport.plan_maintenance?.length > 0 && (
                <div className="p-4 rounded-xl bg-blue-500/10 border-l-4 border-blue-500">
                  <h4 className="font-bold text-sm text-blue-400 uppercase tracking-wider mb-3 flex items-center gap-2"><Calendar className="w-4 h-4" /> Plan de Maintenance</h4>
                  <div className="space-y-2">
                    {aiReport.plan_maintenance.map((p: any, i: number) => (
                      <div key={i} className="flex items-start justify-between p-2 rounded-lg bg-blue-500/5 flex-wrap gap-2">
                        <span className="font-bold text-sm text-blue-300 w-28">{p.jour}</span>
                        <div className="flex-1"><div className="text-xs font-semibold">{p.cibles}</div><div className="text-xs text-savia-text-muted">{p.action}</div></div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {aiReport.estimation_couts && (
                <div className="p-4 rounded-xl bg-yellow-500/10 border-l-4 border-yellow-500">
                  <h4 className="font-bold text-sm text-yellow-400 uppercase tracking-wider mb-3 flex items-center gap-2"><DollarSign className="w-4 h-4" /> Estimation des Coûts</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="text-center p-3 rounded-lg bg-red-500/10"><div className="text-lg font-black text-red-400">{aiReport.estimation_couts.cout_curatif_historique?.toLocaleString('fr')} TND</div><div className="text-xs text-savia-text-muted">Coût curatif</div></div>
                    <div className="text-center p-3 rounded-lg bg-green-500/10"><div className="text-lg font-black text-green-400">{aiReport.estimation_couts.cout_preventif_propose?.toLocaleString('fr')} TND</div><div className="text-xs text-savia-text-muted">Préventif proposé</div></div>
                    <div className="text-center p-3 rounded-lg bg-blue-500/10"><div className="text-lg font-black text-blue-400">{aiReport.estimation_couts.gain_potentiel?.toLocaleString('fr')} TND</div><div className="text-xs text-savia-text-muted">Gain potentiel</div></div>
                    <div className="text-center p-3 rounded-lg bg-purple-500/10"><div className="text-sm font-bold text-purple-400 leading-tight">{aiReport.estimation_couts.ratio}</div><div className="text-xs text-savia-text-muted mt-1">Ratio ROI</div></div>
                  </div>
                </div>
              )}
              {aiReport.tendances?.length > 0 && (
                <div className="p-4 rounded-xl bg-purple-500/10 border-l-4 border-purple-500">
                  <h4 className="font-bold text-sm text-purple-400 uppercase tracking-wider mb-3 flex items-center gap-2"><TrendingUp className="w-4 h-4" /> Tendances</h4>
                  <div className="space-y-1">
                    {aiReport.tendances.map((t: string, i: number) => (
                      <div key={i} className="flex items-start gap-2 text-sm text-savia-text">
                        <ChevronRight className="w-4 h-4 text-purple-400 mt-0.5 shrink-0" />{t}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {aiReport.conclusion && (
                <div className="p-4 rounded-xl bg-savia-surface-hover/60">
                  <h4 className="font-bold text-sm text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2"><ClipboardList className="w-4 h-4" /> Conclusion</h4>
                  <p className="text-sm text-savia-text leading-relaxed">{aiReport.conclusion}</p>
                </div>
              )}
              {/* Fallback: show raw text */}
              {!aiReport.alertes_critiques && !aiReport.analyse && !aiReport.points_forts && !aiReport.tendances && (
                <div className="glass rounded-xl p-5 whitespace-pre-wrap text-sm text-savia-text leading-relaxed">
                  {typeof aiReport === 'string' ? aiReport : JSON.stringify(aiReport, null, 2)}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: COMPARAISON */}
      {activeTab === 3 && (
        <div className="space-y-6">
          <SectionCard title={<span className="flex items-center gap-2"><BarChart3 className="w-4 h-4 text-savia-accent" /> Comparaison Inter-Clients / Inter-Équipements</span>}>
            <div className="flex gap-4 mb-4">
              {['Client', 'Équipement'].map(m => (
                <button key={m} onClick={() => setCompareMode(m)}
                  className={`px-4 py-2 rounded-lg text-sm font-bold transition-all cursor-pointer ${compareMode === m ? 'bg-savia-accent text-white' : 'bg-savia-surface-hover text-savia-text-muted hover:text-savia-text'}`}>
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
                <div className="space-y-4">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-savia-border">
                          <th className="text-left py-2 px-3 text-savia-text-muted">{compareMode}</th>
                          <th className="text-center py-2 px-3 text-savia-text-muted flex items-center gap-1 justify-center"><Wrench className="w-3.5 h-3.5" /> Interventions</th>
                          <th className="text-center py-2 px-3 text-savia-text-muted"><AlertTriangle className="w-3.5 h-3.5 inline mr-1" />Correctives</th>
                          <th className="text-center py-2 px-3 text-savia-text-muted">Heures</th>
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
                  </div>
                  <div className="space-y-2">
                    {sorted.slice(0, 10).map(([key, stats]) => {
                      const maxNb = Math.max(...sorted.map(s => s[1].nb));
                      return (
                        <div key={key} className="flex items-center gap-3">
                          <div className="w-32 text-xs text-savia-text-muted truncate text-right">{key}</div>
                          <div className="flex-1 bg-savia-surface-hover rounded-full h-4 overflow-hidden">
                            <div className="bg-gradient-to-r from-cyan-500 to-blue-500 h-full rounded-full" style={{ width: `${(stats.nb / maxNb * 100)}%` }} />
                          </div>
                          <div className="w-8 text-xs font-mono text-savia-text-muted">{stats.nb}</div>
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
          <SectionCard title={<span className="flex items-center gap-2"><Star className="w-4 h-4 text-yellow-400" /> Fiabilité des Équipements</span>}>
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
                          <td className="py-2.5 px-3 text-sm text-savia-text-muted">{f.client}</td>
                          <td className="py-2.5 px-3">
                            <div className="flex items-center gap-2">
                              <div className="w-16 bg-savia-surface-hover rounded-full h-2 overflow-hidden">
                                <div className={`h-full rounded-full ${f.score >= 60 ? 'bg-green-400' : f.score >= 30 ? 'bg-yellow-400' : 'bg-red-400'}`} style={{ width: `${f.score}%` }} />
                              </div>
                              <span className={`text-xs font-bold ${f.score >= 60 ? 'text-green-400' : f.score >= 30 ? 'text-yellow-400' : 'text-red-400'}`}>{f.score}%</span>
                            </div>
                          </td>
                          <td className="py-2.5 px-3 font-mono text-red-400">{f.pannes}</td>
                          <td className="py-2.5 px-3 font-mono">{f.mttr}h</td>
                          <td className="py-2.5 px-3 text-xs text-savia-text-muted">{f.lastPanne}</td>
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
