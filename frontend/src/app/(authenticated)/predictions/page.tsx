'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { SectionCard } from '@/components/ui/cards';
import {
  Activity, AlertTriangle, Brain, Calendar, CheckCircle2, ClipboardList,
  DollarSign, History, Loader2, RefreshCw, ShieldCheck, Sparkles, Target,
  ThumbsDown, ThumbsUp, Wrench,
} from 'lucide-react';
import { ai as aiApi, dashboard, interventions, predictionFeedback } from '@/lib/api';

interface PredictionItem {
  equipmentId: number; machine: string; client: string; type: string; fabricant: string;
  modele: string; statut: string; risque: number; horizonDays: number; dateCalcul: string;
  composant: string; fiabilite: number; score: number; modelePrediction: string;
  facteurs: string[]; features: Record<string, number>;
  diagnostics: Array<Record<string, string>>;
  protectedComponents: string[];
  feedback: { total: number; correct: number; faux_positif: number; decale: number; precision: number | null };
}

interface FeedbackEntry { machine: string; client?: string; type: 'correct' | 'faux_positif' | 'decale'; vraiDate?: string; timestamp: string; }

const RISK_THRESHOLD = 20;

const toPrediction = (item: Record<string, unknown>): PredictionItem => ({
  equipmentId: Number(item.equipment_id || 0), machine: String(item.machine || ''), client: String(item.client || ''),
  type: String(item.type || ''), fabricant: String(item.fabricant || ''), modele: String(item.modele || ''),
  statut: String(item.statut || ''), risque: Number(item.risque_pct || 0), horizonDays: Number(item.horizon_jours || 30),
  dateCalcul: String(item.date_calcul || ''), composant: String(item.composant_a_risque || 'Pièce à déterminer'),
  fiabilite: Number(item.fiabilite_donnees_pct || 0), score: Number(item.score_sante || 0),
  modelePrediction: String(item.modele || ''), facteurs: Array.isArray(item.facteurs) ? item.facteurs.map(String) : [],
  features: (item.features || {}) as Record<string, number>,
  diagnostics: (item.diagnostics || []) as Array<Record<string, string>>,
  protectedComponents: Array.isArray(item.composants_proteges) ? item.composants_proteges.map(String) : [],
  feedback: (item.feedback || { total: 0, correct: 0, faux_positif: 0, decale: 0, precision: null }) as PredictionItem['feedback'],
});

const toFeedback = (entry: Record<string, unknown>): FeedbackEntry => ({
  machine: String(entry.machine || ''), client: String(entry.client || ''), type: entry.resultat as FeedbackEntry['type'],
  vraiDate: entry.date_reelle ? String(entry.date_reelle) : undefined, timestamp: String(entry.timestamp || new Date().toISOString()),
});

export default function PredictionsPage() {
  const [predictions, setPredictions] = useState<PredictionItem[]>([]);
  const [predictionMeta, setPredictionMeta] = useState<Record<string, unknown>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [aiAnalysis, setAiAnalysis] = useState<any>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [selectedFeedbackMachine, setSelectedFeedbackMachine] = useState('');
  const [feedbackHistory, setFeedbackHistory] = useState<FeedbackEntry[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [decaleDate, setDecaleDate] = useState('');
  const [feedbackSuccess, setFeedbackSuccess] = useState('');

  const loadData = useCallback(async () => {
    try {
      const [result, history] = await Promise.all([dashboard.predictions({ horizon_days: 30 }), predictionFeedback.list().catch(() => [])]);
      setPredictions(result.items.map(toPrediction));
      setPredictionMeta(result.meta || {});
      setFeedbackHistory(history.map(toFeedback));
    } catch (error) { console.error('Erreur chargement prédictions:', error); }
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const riskPredictions = useMemo(() => predictions.filter(p => p.risque >= RISK_THRESHOLD || /panne|hors service/i.test(p.statut)), [predictions]);
  const critiques = riskPredictions.filter(p => p.risque >= 50 || /panne|hors service/i.test(p.statut)).length;
  const attention = riskPredictions.filter(p => p.risque >= RISK_THRESHOLD && p.risque < 50).length;
  const avgFiabilite = riskPredictions.length ? Math.round(riskPredictions.reduce((sum, item) => sum + item.fiabilite, 0) / riskPredictions.length) : 0;
  const validation = (predictionMeta.validation || {}) as Record<string, unknown>;
  const selectedPrediction = riskPredictions.find(item => equipmentLabel(item) === selectedFeedbackMachine);
  const priorityPrediction = riskPredictions[0];

  function equipmentLabel(item: PredictionItem): string { return `${item.machine}${item.client ? ` (${item.client})` : ''}`; }
  function labelEquipmentMentions(value: unknown): string {
    let text = String(value || '');
    [...predictions].filter(item => item.client).sort((a, b) => b.machine.length - a.machine.length).forEach(item => {
      const escaped = item.machine.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      text = text.replace(new RegExp(`${escaped}(?!\\s*\\()`, 'gi'), equipmentLabel(item));
    });
    return text;
  }
  function listValues(value: unknown): string[] {
    if (Array.isArray(value)) return value.map(item => typeof item === 'string' ? item : item?.texte || item?.action || item?.recommandation || JSON.stringify(item));
    return value ? [String(value)] : [];
  }
  function money(value: unknown): string { if (value === null || value === undefined || value === '') return 'Non calculable'; const amount = Number(value); return `${Number.isFinite(amount) ? amount.toLocaleString('fr-FR') : 'Non calculable'} TND`; }
  function formatRisk(value: unknown): string { const text = String(value ?? '—'); return text.includes('%') || text === '—' ? text : `${text}%`; }

  const handleAiAnalysis = async () => {
    setAiLoading(true); setAiAnalysis(null);
    try {
      const [realKpis, allInterventions] = await Promise.all([dashboard.kpis().catch(() => ({})), interventions.list().catch(() => [])]);
      const correctives = allInterventions.filter((item: any) => item.type_intervention === 'Corrective').length;
      const preventives = allInterventions.filter((item: any) => /préventive|preventive/i.test(item.type_intervention || '')).length;
      const kpis = {
        ...realKpis, interventions_correctives: correctives, interventions_preventives: preventives,
        total_machines_surveillees: riskPredictions.length, machines_critiques: critiques, machines_attention: attention,
        precision_ia_moyenne: avgFiabilite, modele_prediction: predictionMeta.model || 'bayesian_hazard', validation_modele: validation,
        top_risques: riskPredictions.slice(0, 8).map(item => ({ machine: equipmentLabel(item), client: item.client, type: item.type, risque_panne_pct: item.risque, horizon_jours: item.horizonDays, composant_a_risque: item.composant, composants_proteges: item.protectedComponents, fiabilite_donnees_pct: item.fiabilite, score_sante: item.score, facteurs: item.facteurs, diagnostics: item.diagnostics })),
        contexte: 'Prévision de panne corrective basée sur l’historique réel, horizon de 30 jours. Fournir causes, actions, recommandations et gains estimés; ne pas inventer une date exacte de panne.',
      };
      const devise = typeof window !== 'undefined' ? localStorage.getItem('savia_devise') || 'USD' : 'USD';
      const response = await aiApi.analyzePerformance(kpis, devise);
      setAiAnalysis(response?.ok && response.result ? response.result : { _fallback: true });
    } catch { setAiAnalysis({ _fallback: true }); }
    finally { setAiLoading(false); }
  };

  function fallbackAnalysis(): string {
    const first = riskPredictions[0];
    return `Diagnostic prédictif SAVIA\n\nRisque d’au moins une panne corrective dans les ${first?.horizonDays || 30} prochains jours.\n\nPriorité : ${first ? equipmentLabel(first) : 'aucune'}\nRisque : ${first?.risque || 0}%\nFiabilité des données : ${first?.fiabilite || 0}%\nFacteurs : ${first?.facteurs.join(', ') || 'aucun facteur dominant identifié'}`;
  }

  const submitFeedback = async (type: FeedbackEntry['type'], vraiDate?: string) => {
    if (!selectedPrediction) return;
    try {
      await predictionFeedback.create({ equipment_id: selectedPrediction.equipmentId, machine: selectedPrediction.machine, client: selectedPrediction.client, resultat: type, date_predite: selectedPrediction.dateCalcul, date_reelle: vraiDate || '', horizon_jours: selectedPrediction.horizonDays, risque_pct: selectedPrediction.risque, modele_version: selectedPrediction.modelePrediction, features: selectedPrediction.features });
      setFeedbackHistory(history => [{ machine: selectedPrediction.machine, client: selectedPrediction.client, type, vraiDate, timestamp: new Date().toISOString() }, ...history]);
      setFeedbackSuccess(type === 'correct' ? 'Feedback enregistré : prédiction correcte' : type === 'faux_positif' ? 'Feedback enregistré : faux positif' : `Date réelle enregistrée : ${vraiDate}`);
      setShowDatePicker(false); setDecaleDate(''); setTimeout(() => setFeedbackSuccess(''), 4000);
    } catch { setFeedbackSuccess('Impossible d’enregistrer le feedback.'); }
  };

  if (isLoading) return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;

  return (
    <div className="space-y-6 animate-fade-in">
      <div><h1 className="text-2xl font-black gradient-text flex items-center gap-3"><Brain className="w-7 h-7" /> Prédictions & Maintenance Préventive</h1><p className="text-savia-text-muted text-sm mt-1">Probabilité d’une panne corrective dans un horizon de {String(predictionMeta.horizon_jours || 30)} jours</p></div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">{[
        { label: 'Critiques', value: critiques, color: 'text-red-400', icon: <AlertTriangle className="w-5 h-5" /> },
        { label: 'À surveiller', value: attention, color: 'text-yellow-400', icon: <Activity className="w-5 h-5" /> },
        { label: 'Fiabilité données', value: `${avgFiabilite}%`, color: 'text-savia-accent', icon: <Target className="w-5 h-5" /> },
        { label: 'Horizon', value: `${String(predictionMeta.horizon_jours || 30)} j`, color: 'text-green-400', icon: <Calendar className="w-5 h-5" /> },
      ].map(kpi => <div key={kpi.label} className="glass rounded-xl p-4 text-center"><div className={`flex justify-center mb-2 ${kpi.color}`}>{kpi.icon}</div><div className={`text-3xl font-black ${kpi.color}`}>{kpi.value}</div><div className="text-xs text-savia-text-muted mt-1">{kpi.label}</div></div>)}</div>

      <SectionCard title={<span className="flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-red-400" /> Risques de panne par machine</span>}>
        {riskPredictions.length === 0 ? <div className="text-center p-6 text-savia-text-muted text-sm"><CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-green-400" /><p className="font-semibold">Aucun équipement au-dessus du seuil de risque ({RISK_THRESHOLD}%).</p><p className="text-xs mt-2">Le modèle utilise une probabilité sur {String(predictionMeta.horizon_jours || 30)} jours.</p></div> : <div className="overflow-x-auto max-h-[520px] overflow-y-auto"><table className="w-full text-sm"><thead><tr className="text-left text-xs text-savia-text-dim uppercase tracking-wider border-b border-savia-border/50"><th className="py-2.5 px-3">Niveau</th><th className="py-2.5 px-3">Machine / client</th><th className="py-2.5 px-3">Pièce observée</th><th className="py-2.5 px-3">Horizon</th><th className="py-2.5 px-3">Risque</th><th className="py-2.5 px-3 text-center">Fiabilité</th></tr></thead><tbody>{riskPredictions.map(item => <tr key={`${item.equipmentId}-${item.machine}-${item.client}`} className="border-b border-savia-border/20 hover:bg-savia-surface-hover/20"><td className="py-3 px-3"><div className={`w-9 h-9 rounded-lg flex items-center justify-center ${item.risque >= 50 ? 'bg-red-500/10' : 'bg-yellow-500/10'}`}>{item.risque >= 50 ? <AlertTriangle className="w-4 h-4 text-red-500" /> : <Activity className="w-4 h-4 text-yellow-400" />}</div></td><td className="py-3 px-3"><div className="font-bold">{equipmentLabel(item)}</div><div className="text-xs text-savia-text-dim">{item.type || item.modele || 'Type non renseigné'} · {item.statut || 'Statut non renseigné'}</div><div className="text-[11px] text-savia-text-dim mt-1">{item.facteurs.slice(0, 2).join(' · ')}</div></td><td className="py-3 px-3"><span className="px-2 py-1 rounded-lg bg-savia-bg text-xs font-semibold">{item.composant}</span></td><td className="py-3 px-3"><span className="inline-flex items-center gap-1.5 font-semibold text-blue-400"><Calendar className="w-3.5 h-3.5" /> {item.horizonDays} jours</span></td><td className="py-3 px-3"><div className="w-28"><div className="flex justify-between text-xs mb-1"><span className="text-savia-text-dim">Probabilité</span><span className={`font-bold ${item.risque >= 50 ? 'text-red-400' : 'text-yellow-400'}`}>{item.risque}%</span></div><div className="w-full h-2 bg-savia-bg rounded-full overflow-hidden"><div className={`h-full rounded-full ${item.risque >= 50 ? 'bg-red-500' : 'bg-yellow-500'}`} style={{ width: `${item.risque}%` }} /></div></div></td><td className="py-3 px-3 text-center"><span className="text-xs px-2.5 py-1 rounded-full bg-blue-500/10 text-blue-400 font-semibold inline-flex items-center gap-1"><Target className="w-3 h-3" /> {item.fiabilite}%</span></td></tr>)}</tbody></table></div>}
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-savia-text-muted"><div className="rounded-lg bg-savia-bg/50 p-3"><span className="font-semibold text-savia-text">Modèle :</span> {String(predictionMeta.model || 'bayesian_hazard')} · version {String(predictionMeta.model_version || '—')}</div><div className="rounded-lg bg-savia-bg/50 p-3"><span className="font-semibold text-savia-text">Validation :</span> {validation.n ? `${String(validation.n)} cas · précision ${String(validation.precision || 0)}% · rappel ${String(validation.rappel || 0)}% · Brier ${String(validation.brier || '—')}` : 'Historique insuffisant pour valider le modèle.'}</div></div>
      </SectionCard>

      <SectionCard title={<span className="flex items-center gap-2"><Brain className="w-4 h-4 text-savia-accent" /> Analyse IA prédictive</span>}>
        <p className="text-savia-text-muted text-sm mb-4">L&apos;IA explique les probabilités calculées, les causes issues des diagnostics techniciens, les actions préventives et l’économie potentielle. Les montants sont des estimations à valider par le responsable technique.</p>
        <button onClick={handleAiAnalysis} disabled={aiLoading} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-savia-text bg-gradient-to-r from-purple-600 to-blue-600 hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer mb-5">{aiLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}{aiLoading ? 'Analyse en cours...' : 'Lancer l’analyse IA'}</button>
        {aiAnalysis && <div className="space-y-5">
          {aiAnalysis._fallback && <div className="rounded-lg border border-yellow-500/30 bg-savia-surface p-3 text-xs text-yellow-200">Rapport detail genere a partir des donnees serveur; le fournisseur IA n&apos;a pas renvoye son rapport.</div>}
          <div className="flex items-center gap-2 text-purple-400 font-semibold text-sm"><ClipboardList className="w-4 h-4" /> Rapport détaillé de l’analyse</div>

          {priorityPrediction && aiAnalysis._fallback && !aiAnalysis.alertes_critiques?.length && <div className="rounded-xl border border-purple-500/20 bg-gradient-to-br from-purple-500/10 via-savia-surface to-savia-bg p-5 space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-wider text-savia-text-muted">Priorité actuelle</p>
                <h3 className="mt-1 text-lg font-black text-savia-text">{equipmentLabel(priorityPrediction)}</h3>
                <p className="mt-1 text-xs text-savia-text-muted">{priorityPrediction.type || priorityPrediction.modele || 'Type non renseigné'} · {priorityPrediction.statut || 'Statut non renseigné'}</p>
              </div>
              <span className={priorityPrediction.risque >= 50 ? 'rounded-full px-3 py-1 text-xs font-bold bg-red-500/15 text-red-300' : 'rounded-full px-3 py-1 text-xs font-bold bg-yellow-500/15 text-yellow-300'}>
                {priorityPrediction.risque >= 50 ? 'Risque élevé' : 'À surveiller'}
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-lg bg-savia-bg/60 p-3"><p className="text-xs text-savia-text-muted">Probabilité sur {priorityPrediction.horizonDays} jours</p><p className="mt-1 text-2xl font-black text-red-300">{priorityPrediction.risque}%</p><div className="mt-2 h-2 overflow-hidden rounded-full bg-savia-border/50"><div className="h-full rounded-full bg-red-400" style={{ width: String(Math.min(100, priorityPrediction.risque)) + '%' }} /></div></div>
              <div className="rounded-lg bg-savia-bg/60 p-3"><p className="text-xs text-savia-text-muted">Fiabilité des données</p><p className="mt-1 text-2xl font-black text-blue-300">{priorityPrediction.fiabilite}%</p><p className="mt-1 text-[11px] text-savia-text-dim">Qualité de l’historique utilisé, pas une garantie de panne.</p></div>
              <div className="rounded-lg bg-savia-bg/60 p-3"><p className="text-xs text-savia-text-muted">Score de santé</p><p className="mt-1 text-2xl font-black text-savia-accent">{priorityPrediction.score}%</p><p className="mt-1 text-[11px] text-savia-text-dim">Indicateur inverse du risque calculé.</p></div>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <p className="mb-2 text-xs font-bold uppercase tracking-wider text-savia-text-muted">Facteurs observés</p>
                <ul className="space-y-2 text-sm text-savia-text">{(priorityPrediction.facteurs.length ? priorityPrediction.facteurs : ['Aucun facteur dominant identifié']).map((factor, index) => <li key={factor + '-' + index} className="flex gap-2"><span className="text-purple-300">•</span><span>{factor}</span></li>)}</ul>
              </div>
              <div>
                <p className="mb-2 text-xs font-bold uppercase tracking-wider text-savia-text-muted">Lecture recommandée</p>
                <p className="text-sm leading-relaxed text-savia-text-muted">Cette valeur estime la probabilité d’au moins une panne corrective dans l’horizon indiqué. Elle ne prédit ni la date exacte ni une panne certaine. Avec une fiabilité de {priorityPrediction.fiabilite}%, les résultats doivent être confirmés par l’historique terrain et une inspection technique.</p>
              </div>
            </div>
            <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3 text-sm text-yellow-100"><strong>Actions immédiates suggérées :</strong> vérifier les maintenances préventives en retard, consulter les diagnostics liés aux facteurs ci-dessus et planifier une inspection ciblée de {priorityPrediction.composant || 'la pièce à déterminer'}.</div>
          </div>}
          {aiAnalysis._fallback && <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/5 p-3 text-xs text-yellow-100">Résumé automatique du moteur prédictif : le rapport détaillé de l’IA n’a pas été retourné.</div>}

          {aiAnalysis.alertes_critiques?.length > 0 && <div className="bg-red-500/5 rounded-xl p-5 border border-red-500/20"><div className="flex items-center gap-2 mb-3 text-red-400 font-bold"><AlertTriangle className="w-4 h-4" /> Prédictions et causes prioritaires</div><div className="space-y-4">{aiAnalysis.alertes_critiques.map((alert: any, index: number) => <div key={index} className="bg-savia-bg/60 rounded-lg p-4 border-l-4 border-red-500"><div className="font-bold text-sm">{index + 1}. {labelEquipmentMentions(alert.machine)}</div><div className="flex flex-wrap gap-2 mt-2 text-xs"><span className="px-2 py-1 rounded bg-red-500/10 text-red-300">Risque : {alert.risque_panne_pct ?? alert.risque ?? '—'}%</span><span className="px-2 py-1 rounded bg-blue-500/10 text-blue-300">Horizon : {alert.horizon_jours ?? alert.jours_avant_panne ?? '—'} jours</span><span className="px-2 py-1 rounded bg-savia-surface text-savia-text-muted">Score santé : {alert.score_sante ?? '—'}%</span></div>{alert.cause && <p className="text-sm mt-3"><strong className="text-orange-300">Cause probable :</strong> {labelEquipmentMentions(alert.cause)}</p>}{alert.risque && typeof alert.risque === 'string' && <p className="text-sm mt-2"><strong className="text-red-300">Risque opérationnel :</strong> {labelEquipmentMentions(alert.risque)}</p>}{listValues(alert.facteurs || alert.facteurs_risque).length > 0 && <div className="mt-3"><strong className="text-xs text-savia-text-muted uppercase">Facteurs observés</strong><ul className="list-disc list-inside text-sm text-savia-text-muted mt-1">{listValues(alert.facteurs || alert.facteurs_risque).map((factor, factorIndex) => <li key={factorIndex}>{labelEquipmentMentions(factor)}</li>)}</ul></div>}{alert.action_immediate && <div className="mt-3 p-3 rounded bg-yellow-500/5 border border-yellow-500/20 text-sm"><Wrench className="w-4 h-4 inline mr-1 text-yellow-300" /><strong className="text-yellow-300">Action immédiate :</strong> {labelEquipmentMentions(alert.action_immediate)}</div>}{listValues(alert.recommandations).length > 0 && <div className="mt-3"><strong className="text-xs text-savia-text-muted uppercase">Recommandations pour cette machine</strong><ul className="list-disc list-inside text-sm text-savia-text-muted mt-1">{listValues(alert.recommandations).map((recommendation, recommendationIndex) => <li key={recommendationIndex}>{labelEquipmentMentions(recommendation)}</li>)}</ul></div>}{(alert.gain_potentiel || alert.cout_panne_evite) && <div className="mt-3 text-sm text-green-300"><DollarSign className="w-4 h-4 inline mr-1" />Gain estimé : {money(alert.gain_potentiel || alert.cout_panne_evite)}</div>}</div>)}</div></div>}

          {aiAnalysis.recommandations_prioritaires?.length > 0 && <div className="bg-blue-500/5 rounded-xl p-5 border border-blue-500/20"><div className="flex items-center gap-2 mb-3 text-blue-300 font-bold"><Wrench className="w-4 h-4" /> Recommandations prioritaires et gains attendus</div><div className="space-y-3">{aiAnalysis.recommandations_prioritaires.map((recommendation: any, index: number) => <div key={index} className="bg-savia-bg/60 rounded-lg p-4"><div className="flex flex-wrap justify-between gap-2"><strong>{index + 1}. {labelEquipmentMentions(recommendation.machine || recommendation.cible || 'Parc')}</strong><span className="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-300">Priorité {recommendation.priorite || index + 1}</span></div>{recommendation.cause && <p className="text-sm text-orange-300 mt-2"><strong>Cause :</strong> {labelEquipmentMentions(recommendation.cause)}</p>}<p className="text-sm text-savia-text mt-2"><strong>Action :</strong> {labelEquipmentMentions(recommendation.recommandation || recommendation.action || recommendation.texte || '')}</p><div className="flex flex-wrap gap-3 mt-3 text-xs text-savia-text-muted">{recommendation.cout_estime != null && <span>Coût estimé : <strong className="text-savia-text">{money(recommendation.cout_estime)}</strong></span>}{recommendation.gain_estime != null && <span>Gain estimé : <strong className="text-green-300">{money(recommendation.gain_estime)}</strong></span>}{recommendation.delai && <span>Délai : {recommendation.delai}</span>}</div></div>)}</div></div>}

          {aiAnalysis.plan_maintenance?.length > 0 && <div className="bg-cyan-500/5 rounded-xl p-5 border border-cyan-500/20"><div className="flex items-center gap-2 mb-3 text-cyan-300 font-bold"><Calendar className="w-4 h-4" /> Plan de maintenance recommandé</div><div className="grid grid-cols-1 md:grid-cols-3 gap-3">{aiAnalysis.plan_maintenance.map((plan: any, index: number) => <div key={index} className="bg-savia-bg/60 rounded-lg p-3"><div className="font-bold text-sm text-cyan-200">{plan.jour || `Étape ${index + 1}`}</div><div className="text-sm mt-2"><strong>Cibles :</strong> {labelEquipmentMentions(plan.cibles || '—')}</div><div className="text-sm text-savia-text-muted mt-1"><strong>Action :</strong> {labelEquipmentMentions(plan.action || '—')}</div></div>)}</div></div>}

          {aiAnalysis.estimation_couts && <div className="bg-green-500/5 rounded-xl p-5 border border-green-500/20"><div className="flex items-center gap-2 mb-3 text-green-300 font-bold"><DollarSign className="w-4 h-4" /> Gains potentiels des recommandations</div><div className="grid grid-cols-2 md:grid-cols-4 gap-3"><div className="bg-savia-bg/60 rounded-lg p-3 text-center"><div className="text-xs text-savia-text-dim">Curatif historique</div><div className="text-lg font-bold text-red-300">{money(aiAnalysis.estimation_couts.cout_curatif_historique)}</div></div><div className="bg-savia-bg/60 rounded-lg p-3 text-center"><div className="text-xs text-savia-text-dim">Préventif proposé</div><div className="text-lg font-bold text-yellow-300">{money(aiAnalysis.estimation_couts.cout_preventif_propose)}</div></div><div className="bg-savia-bg/60 rounded-lg p-3 text-center"><div className="text-xs text-savia-text-dim">Coût de pannes évité</div><div className="text-lg font-bold text-blue-300">{money(aiAnalysis.estimation_couts.cout_pannes_evitees || aiAnalysis.estimation_couts.cout_evite)}</div></div><div className="bg-savia-bg/60 rounded-lg p-3 text-center"><div className="text-xs text-savia-text-dim">Gain potentiel net</div><div className="text-lg font-bold text-green-300">{money(aiAnalysis.estimation_couts.gain_potentiel)}</div></div></div>{aiAnalysis.estimation_couts.detail_preventif && <p className="text-sm text-savia-text-muted mt-3">{labelEquipmentMentions(aiAnalysis.estimation_couts.detail_preventif)}</p>}{aiAnalysis.estimation_couts.hypotheses && <p className="text-xs text-savia-text-dim mt-2"><strong>Hypothèses :</strong> {labelEquipmentMentions(aiAnalysis.estimation_couts.hypotheses)}</p>}{aiAnalysis.estimation_couts.ratio && <p className="text-sm text-green-200 mt-2 font-semibold">{labelEquipmentMentions(aiAnalysis.estimation_couts.ratio)}</p>}</div>}

          {aiAnalysis.tendances?.length > 0 && <div className="bg-purple-500/5 rounded-xl p-5 border border-purple-500/20"><div className="flex items-center gap-2 mb-3 text-purple-300 font-bold"><Sparkles className="w-4 h-4" /> Tendances et recommandations de fond</div><ul className="space-y-2">{aiAnalysis.tendances.map((trend: string, index: number) => <li key={index} className="text-sm text-savia-text-muted"><span className="text-purple-300 font-semibold mr-2">{index + 1}.</span>{labelEquipmentMentions(trend)}</li>)}</ul></div>}
          {aiAnalysis.analyse && <div className="bg-savia-bg/50 rounded-xl p-5 border border-savia-border/50 text-sm text-savia-text whitespace-pre-wrap">{labelEquipmentMentions(aiAnalysis.analyse)}</div>}
          {aiAnalysis.conclusion && <div className="bg-savia-bg/50 rounded-xl p-4 border border-savia-border/50 text-sm font-semibold text-savia-accent"><ShieldCheck className="w-4 h-4 inline mr-1" />Conclusion : {labelEquipmentMentions(aiAnalysis.conclusion)}</div>}
        </div>}
      </SectionCard>

      <SectionCard title={<span className="flex items-center gap-2"><RefreshCw className="w-4 h-4 text-savia-accent" /> Feedback — validez les prédictions</span>}>
        <p className="text-savia-text-muted text-sm mb-4">Les feedbacks sont enregistrés côté serveur avec l’équipement, le client, l’horizon et les variables utilisées.</p>
        <div className="mb-4"><label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2"><ClipboardList className="w-3.5 h-3.5 inline mr-2" />Sélectionner une machine</label><select value={selectedFeedbackMachine} onChange={event => { setSelectedFeedbackMachine(event.target.value); setShowDatePicker(false); setFeedbackSuccess(''); }} className="w-full md:w-96 bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text"><option value="">— Choisir une machine —</option>{riskPredictions.map(item => <option key={`${item.equipmentId}-${item.machine}-${item.client}`} value={equipmentLabel(item)}>{equipmentLabel(item)} (Risque : {item.risque}%)</option>)}</select></div>
        {selectedPrediction && <div className="flex flex-wrap gap-3"><button onClick={() => submitFeedback('correct')} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-green-400 bg-green-500/10 border border-green-500/20 cursor-pointer"><ThumbsUp className="w-4 h-4" />Correct</button><button onClick={() => submitFeedback('faux_positif')} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-red-400 bg-red-500/10 border border-red-500/20 cursor-pointer"><ThumbsDown className="w-4 h-4" />Faux positif</button><button onClick={() => setShowDatePicker(value => !value)} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-yellow-400 bg-yellow-500/10 border border-yellow-500/20 cursor-pointer"><Calendar className="w-4 h-4" />Décalé</button><button onClick={() => setShowHistory(value => !value)} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-savia-text-muted bg-savia-surface border border-savia-border cursor-pointer"><History className="w-4 h-4" />Historique</button></div>}
        {showDatePicker && selectedPrediction && <div className="flex items-center gap-3 p-4 mt-4 rounded-lg bg-yellow-500/5 border border-yellow-500/20"><Calendar className="w-5 h-5 text-yellow-400" /><span className="text-sm text-savia-text-muted">Date réelle :</span><input type="date" value={decaleDate} onChange={event => setDecaleDate(event.target.value)} className="bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-savia-text" /><button onClick={() => decaleDate && submitFeedback('decale', decaleDate)} disabled={!decaleDate} className="px-4 py-2 rounded-lg font-semibold text-white bg-yellow-600 disabled:opacity-50 cursor-pointer">Valider</button></div>}
        {feedbackSuccess && <div className="flex items-center gap-2 p-3 mt-4 rounded-lg bg-green-500/10 text-green-400 text-sm font-semibold"><ShieldCheck className="w-4 h-4" />{feedbackSuccess}</div>}
        {showHistory && <div className="mt-4 space-y-2"><h4 className="text-sm font-bold text-savia-text-muted flex items-center gap-2"><History className="w-4 h-4" />Historique ({feedbackHistory.length})</h4>{feedbackHistory.length ? feedbackHistory.map((entry, index) => <div key={`${entry.timestamp}-${index}`} className="flex items-center gap-3 p-3 rounded-lg bg-savia-bg/50 text-sm"><div className="flex-1"><span className="font-semibold">{entry.machine}{entry.client ? ` (${entry.client})` : ''}</span><span className="text-savia-text-dim ml-2">— {entry.type === 'correct' ? 'Correct' : entry.type === 'faux_positif' ? 'Faux positif' : `Décalé → ${entry.vraiDate || '—'}`}</span></div><span className="text-xs text-savia-text-dim">{new Date(entry.timestamp).toLocaleDateString('fr-FR')}</span></div>) : <div className="text-center p-6 text-savia-text-muted text-sm">Aucun feedback enregistré.</div>}</div>}
      </SectionCard>
    </div>
  );
}
