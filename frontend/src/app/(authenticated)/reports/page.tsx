'use client';
import { useState, useEffect, useMemo, useCallback } from 'react';
import { SectionCard } from '@/components/ui/cards';
import {
  FileText, Download, Loader2, Sparkles, BarChart3, Building2, Star,
  AlertTriangle, Calendar, Wrench, TrendingUp, DollarSign, CheckCircle2,
  ClipboardList, Target, Activity, ShieldCheck, Bot, ChevronRight
} from 'lucide-react';
import { interventions, equipements, ai, finances, contrats, pieces, settings } from '@/lib/api';
import { TrendingDown, PieChart as PieChartIcon } from 'lucide-react';

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

  // --- Rapport Financier state ---
  const [finClient, setFinClient] = useState('');
  const [finMois, setFinMois] = useState(now.getMonth() + 1);
  const [finAnnee, setFinAnnee] = useState(now.getFullYear());
  const [finAnnuel, setFinAnnuel] = useState(false);
  const [finData, setFinData] = useState<any>(null);
  const [finTco, setFinTco] = useState<any[]>([]);
  const [finLoading, setFinLoading] = useState(false);
  const [currency, setCurrency] = useState(() => (typeof window !== 'undefined' ? localStorage.getItem('savia_devise') || 'TND' : 'TND'));
  const [tauxHoraire, setTauxHoraire] = useState(0);

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

  useEffect(() => {
    settings.get()
      .then((settingsData) => {
        setTauxHoraire(Number(settingsData.taux_horaire_technicien) || 0);
      })
      .catch(() => setTauxHoraire(0));
  }, []);

  useEffect(() => {
    const refreshCurrency = () => setCurrency(localStorage.getItem('savia_devise') || 'TND');
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'savia_devise') refreshCurrency();
    };
    window.addEventListener('savia_settings_changed', refreshCurrency);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('savia_settings_changed', refreshCurrency);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

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

  const getClientReportData = useCallback((client: string, month: number, year: number) => {
    const clientMachines = (equips as any[])
      .filter((e: any) => e.Client === client)
      .map((e: any) => e.Nom);

    return data.filter((i: any) => {
      if (!clientMachines.includes(i.machine)) return false;
      const dt = new Date(i.date);
      return !isNaN(dt.getTime()) && dt.getMonth() + 1 === month && dt.getFullYear() === year;
    });
  }, [data, equips]);

  const getClientLaborCost = useCallback((intervention: any) => {
    const parentMinutes = Number(intervention.duree_minutes) || 0;
    const detailMinutes = Array.isArray(intervention.techniciens_detail)
      ? intervention.techniciens_detail.reduce(
          (total: number, detail: any) => total + (Number(detail.duree_minutes) || 0),
          0,
        )
      : 0;
    const minutes = parentMinutes > 0 ? parentMinutes : detailMinutes;

    if (tauxHoraire > 0 && minutes > 0) return (minutes / 60) * tauxHoraire;
    return Number(intervention.cout) || 0;
  }, [tauxHoraire]);

  // --- PDF generation via backend (server-side, direct download) ---
  const generatePdf = async (docTitle: string, pdfData: Record<string, any>) => {
    setIsPdfGenerating(true);
    try {
      const token = localStorage.getItem('savia_token') || '';
      const cn = localStorage.getItem('savia_company') || 'SAVIA';
      const cl = localStorage.getItem('savia_logo') || '';
      const res = await fetch('/api/reports/generate-pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify(Object.assign({}, pdfData, { company_name: cn, company_logo: cl })),
      });
      if (!res.ok) throw new Error('Erreur serveur: ' + res.status);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = (pdfData.filename || 'rapport') + '.pdf';
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url);
      setPdfSuccess('PDF téléchargé !'); setTimeout(() => setPdfSuccess(''), 3000);
    } catch (err: any) {
      console.error(err); alert('Erreur PDF: ' + err.message);
    } finally { setIsPdfGenerating(false); }
  };

  const handlePdfMensuel = async () => {
    const monthData = filterByPeriod(data, selMois, selAnnee);
    const nbIntv = monthData.length;
    const nbClot = monthData.filter((i: any) => (i.statut || '').toLowerCase().includes('tur')).length;
    const cout = monthData.reduce((a: number, b: any) => a + (b.cout || 0), 0);
    const types: Record<string, number> = {};
    monthData.forEach((i: any) => { const t = i.type_intervention || 'Autre'; types[t] = (types[t] || 0) + 1; });
    const rows = monthData.slice(0, 30).map((i: any) =>
      `<tr><td>${(i.date||'').substring(0,10)}</td><td>${i.machine||''}</td><td>${i.type_intervention||''}</td><td>${i.technicien||''}</td><td>${i.statut||''}</td><td>${money(i.cout || 0)}</td></tr>`
    ).join('');
    const label = MOIS_LABELS[selMois-1] + ' ' + selAnnee;
    const padM = String(selMois).padStart(2,'0');
    const costStr = Math.round(cout).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '\u202f');
    const tauxStr = nbIntv > 0 ? Math.round(nbClot/nbIntv*100) + '%' : '0%';
    await generatePdf('Rapport Mensuel ' + label, {
      title: 'Rapport Mensuel \u2014 ' + label,
      subtitle: 'Période : ' + label,
      filename: 'rapport_mensuel_' + selAnnee + '_' + padM,
      kpis: [
        { label: 'Interventions', val: String(nbIntv), color: [15,118,110] },
        { label: 'Clôturées',     val: String(nbClot), color: [22,163,74] },
        { label: 'Taux rés.',     val: tauxStr, color: [234,179,8] },
      ],
      type_data: Object.entries(types).map(function(e) { return [e[0], String(e[1])]; }),
      head: ['Date','Machine','Type','Technicien','Statut'],
      table_title: 'Détail \u2014 ' + label,
      rows: monthData.slice(0,100).map(function(i: any) { return [
        (i.date||'').substring(0,10), i.machine||'', i.type_intervention||i.type||'',
        i.technicien||'', i.statut||'',
      ]; }),
    });
  };

  const handlePdfClient = async () => {
    const clientData = getClientReportData(selClient, selClientMois, selClientAnnee);
    const nbIntv = clientData.length;
    const cout = clientData.reduce((a: number, b: any) => a + getClientLaborCost(b), 0);
    const coutPieces = clientData.reduce((a: number, b: any) => a + (b.cout_pieces || 0), 0);
    const lbl2 = MOIS_LABELS[selClientMois-1] + ' ' + selClientAnnee;
    const padC = String(selClientMois).padStart(2,'0');
    const fnameC = 'rapport_client_' + selClient.replace(/\s+/g,'_') + '_' + selClientAnnee + '_' + padC;
    const moStr = money(Math.round(cout));
    const pcStr = money(Math.round(coutPieces));
    await generatePdf('Rapport Client ' + selClient + ' \u2014 ' + lbl2, {
      title: 'Rapport Client \u2014 ' + selClient,
      subtitle: 'Période : ' + lbl2,
      filename: fnameC,
      kpis: [
        { label: 'Interventions', val: String(nbIntv), color: [15,118,110] },
        { label: 'Coût M.O.',     val: moStr, color: [22,163,74] },
        { label: 'Coût Pièces',   val: pcStr, color: [234,179,8] },
      ],
      head: ['Date','Machine','Type','Technicien','Statut',`Coût (${currencyCode})`],
      table_title: 'Interventions \u2014 ' + selClient + ' \u2014 ' + lbl2,
      rows: clientData.map(function(i: any) { return [
        (i.date||'').substring(0,10), i.machine||'', i.type_intervention||i.type||'',
        i.technicien||'', i.statut||'', Math.round(getClientLaborCost(i)),
      ]; }),
    });
  };

  // --- AI PDF download ---
  const handleAiPdf = async () => {
    if (!aiReport) { alert("Veuillez generer l'analyse IA d'abord."); return; }
    const summ: any = (aiReport as any)?.summary;
    if (typeof summ === "string" && (summ.startsWith("Erreur") || summ.includes("pas pu"))) {
      alert("L'analyse IA a echoue. Relancez l'analyse avant de telecharger.");
      return;
    }
    const m = MOIS_LABELS[iaMois - 1];
    const periodeLabel = iaPeriode === 'Mensuel' ? (m + ' ' + iaAnnee) : ('Année ' + iaAnnee);
    await generatePdf('Rapport IA \u2014 ' + periodeLabel, {
      title: 'Rapport IA \u2014 Analyse Intelligente',
      subtitle: 'Période : ' + periodeLabel + '  |  Client : ' + iaClient,
      filename: 'rapport_ia_' + iaAnnee,
      is_ai_report: true,
      ai_content: JSON.stringify(aiReport),
    });
  };

  // --- AI Report using dedicated endpoint ---
  const handleAiReport = async () => {
    setIsGenerating(true);
    setAiReport(null);
    try {
      let periodeData = iaPeriode === 'Mensuel' ? filterByPeriod(data, iaMois, iaAnnee) : filterByPeriod(data, null, iaAnnee);
      periodeData = filterByClient(periodeData, iaClient);
      const [contractsData, partsData] = await Promise.all([
        contrats.list(iaClient === 'Tous les clients' ? undefined : iaClient).catch(() => []),
        pieces.list().catch(() => []),
      ]);
      const selectedEquipments = (equips as any[]).filter((equipment: any) =>
        iaClient === 'Tous les clients' || equipment.Client === iaClient,
      );
      const selectedMachines = new Set(selectedEquipments.map((equipment: any) => equipment.Nom || equipment.nom).filter(Boolean));
      const selectedEquipmentTypes = new Set(selectedEquipments.map((equipment: any) => equipment.Type || equipment.type).filter(Boolean));
      const nb = periodeData.length;
      const nbClot = periodeData.filter((i: any) => (i.statut || '').toLowerCase().includes('tur')).length;
      const types: Record<string, number> = {};
      const machinesTop: Record<string, number> = {};
      const errorsByCode: Record<string, number> = {};
      const causes: Record<string, number> = {};
      const techniciens: Record<string, { interventions: number; minutes: number; cloturees: number; cout: number }> = {};
      periodeData.forEach((i: any) => {
        const t = i.type_intervention || 'Autre';
        types[t] = (types[t] || 0) + 1;
        const m = `${i.machine} (${machineToClient[i.machine] || '?'})`;
        machinesTop[m] = (machinesTop[m] || 0) + 1;
        const code = String(i.code_erreur || i.code || '').trim();
        if (code) errorsByCode[code] = (errorsByCode[code] || 0) + 1;
        const cause = String(i.cause || '').trim();
        if (cause) causes[cause] = (causes[cause] || 0) + 1;
        const technician = String(i.technicien || 'Non renseigné');
        const current = techniciens[technician] || { interventions: 0, minutes: 0, cloturees: 0, cout: 0 };
        current.interventions += 1;
        current.minutes += Number(i.duree_minutes) || 0;
        current.cloturees += (i.statut || '').toLowerCase().includes('tur') ? 1 : 0;
        current.cout += getClientLaborCost(i) + (Number(i.cout_pieces) || 0);
        techniciens[technician] = current;
      });
      const dureeMoy = nb > 0 ? Math.round(periodeData.reduce((a: number, b: any) => a + (b.duree_minutes || 0), 0) / nb) : 0;
      const coutMainOeuvre = periodeData.reduce((total: number, item: any) => total + getClientLaborCost(item), 0);
      const coutPieces = periodeData.reduce((total: number, item: any) => total + (Number(item.cout_pieces) || 0), 0);
      const coutTotal = coutMainOeuvre + coutPieces;
      const periodeLabel = iaPeriode === 'Mensuel' ? `${MOIS_LABELS[iaMois-1]} ${iaAnnee}` : `Année ${iaAnnee}`;
      const machineDetails = Array.from(selectedMachines).map((machine) => {
        const machineInterventions = periodeData.filter((item: any) => item.machine === machine);
        const equipment = selectedEquipments.find((item: any) => (item.Nom || item.nom) === machine) || {};
        return {
          machine,
          client: equipment.Client || equipment.client || machineToClient[machine] || '',
          type: equipment.Type || equipment.type || '',
          statut: equipment.Statut || equipment.statut || '',
          score_sante: equipment.Score_Sante ?? equipment.score_sante ?? null,
          interventions: machineInterventions.length,
          correctives: machineInterventions.filter((item: any) => String(item.type_intervention || '').toLowerCase().includes('correct')).length,
          cout_total: machineInterventions.reduce((total: number, item: any) => total + getClientLaborCost(item) + (Number(item.cout_pieces) || 0), 0),
          dernier_diagnostic: machineInterventions.find((item: any) => item.probleme || item.cause || item.solution) || null,
        };
      }).filter((item) => item.interventions > 0 || item.statut);
      const scopedParts = (partsData as any[]).filter((part: any) =>
        iaClient === 'Tous les clients' || selectedEquipmentTypes.has(part.equipement_type || part.Equipement_Type),
      ).map((part: any) => ({
        reference: part.reference || part.Reference,
        designation: part.designation || part.Designation,
        equipement_type: part.equipement_type || part.Equipement_Type,
        stock_actuel: Number(part.stock_actuel ?? part.Stock_Actuel ?? 0),
        stock_minimum: Number(part.stock_minimum ?? part.Seuil_Critique ?? 0),
        prix_unitaire: Number(part.prix_unitaire ?? part.Prix_Unitaire ?? 0),
        fournisseur: part.fournisseur || part.Fournisseur || '',
      }));

      const res = await ai.analyzeSav({
        client: iaClient,
        periode: periodeLabel,
        nb_interventions: nb,
        nb_cloturees: nbClot,
        types_interventions: types,
        top_machines: machinesTop,
        duree_moyenne_min: dureeMoy,
        cout_main_oeuvre: coutMainOeuvre,
        cout_pieces: coutPieces,
        cout_total: coutTotal,
        nb_equipements: selectedEquipments.length,
        taux_cloture_pct: nb > 0 ? Math.round(nbClot / nb * 100) : 0,
        interventions_detail: periodeData.slice(0, 100).map((item: any) => ({
          date: item.date, machine: item.machine, client: machineToClient[item.machine] || '', type: item.type_intervention || '',
          statut: item.statut || '', technicien: item.technicien || '', duree_minutes: Number(item.duree_minutes) || 0,
          cout_main_oeuvre: getClientLaborCost(item), cout_pieces: Number(item.cout_pieces) || 0,
          code_erreur: item.code_erreur || item.code || '', probleme: item.probleme || '', cause: item.cause || '', solution: item.solution || '',
        })),
        machines_detail: machineDetails,
        erreurs_recurrentes: Object.entries(errorsByCode).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([code, occurrences]) => ({ code, occurrences })),
        causes_recurrentes: Object.entries(causes).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([cause, occurrences]) => ({ cause, occurrences })),
        tech_details: Object.entries(techniciens).map(([technicien, stats]) => ({ technicien, ...stats, taux_cloture_pct: stats.interventions ? Math.round(stats.cloturees / stats.interventions * 100) : 0 })),
        equipements_detail: selectedEquipments.map((equipment: any) => ({ nom: equipment.Nom || equipment.nom, client: equipment.Client || equipment.client, type: equipment.Type || equipment.type, statut: equipment.Statut || equipment.statut, score_sante: equipment.Score_Sante ?? equipment.score_sante ?? null })),
        contrats_detail: (contractsData as any[]).map((contract: any) => ({ client: contract.client || contract.Client, equipement: contract.equipement || contract.Equipement, type: contract.type_contrat || contract.Type_Contrat, statut: contract.statut || contract.Statut, avec_pieces: Boolean(contract.avec_pieces), date_fin: contract.date_fin || contract.Date_Fin })),
        stock_detail: scopedParts,
      }, currencyCode);

      if (res.ok && res.result) {
        setAiReport(res.result);
      } else {
        setAiReport({ summary: "L'IA n'a pas pu générer le rapport." });
      }
    } catch (err: any) {
      console.error('AI analyze error:', err);
      alert('Erreur analyse IA: ' + (err?.message || 'Service indisponible') + '\nVeuillez reessayer.');
      setAiReport(null);
    } finally { setIsGenerating(false); }
  };

  // --- Load finance data for preview ---
  const loadFinancePreview = useCallback(async () => {
    setFinLoading(true);
    try {
      const cl = finClient || undefined;
      const [dash, tco] = await Promise.all([finances.dashboard(cl), finances.tco(cl)]);
      setFinData(dash);
      setFinTco(tco as any[]);
    } catch (err) { console.error('Finance preview error:', err); }
    finally { setFinLoading(false); }
  }, [finClient]);

  useEffect(() => { if (activeTab === 5) loadFinancePreview(); }, [activeTab, finClient, loadFinancePreview]);

  const FMT = (n: number) => n.toLocaleString('fr-FR');
  const FMTK = (n: number) => {
    if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1).replace('.0', '') + 'M';
    if (Math.abs(n) >= 10_000) return Math.round(n / 1_000).toLocaleString('fr-FR') + 'K';
    return n.toLocaleString('fr-FR');
  };
  const currencyCode = currency || 'TND';
  const money = (n: number) => `${FMT(n)} ${currencyCode}`;
  const moneyK = (n: number) => `${FMTK(n)} ${currencyCode}`;

  const handlePdfFinancier = async () => {
    if (!finData) { alert('Chargement des données en cours...'); return; }
    const kpis = finData.kpis || {};
    const clientsList = (finData.clients || []) as any[];
    const lang = typeof window !== 'undefined' && localStorage.getItem('savia_lang') === 'en' ? 'en' : 'fr';
    const pdfLabels = lang === 'en'
      ? {
          reportTitle: 'Financial Report',
          period: 'Period',
          client: 'Client',
          allClients: 'All clients',
          year: 'Year',
          months: ['January','February','March','April','May','June','July','August','September','October','November','December'],
          contractRevenue: 'Contract Revenue',
          totalCosts: 'Total Costs',
          globalMargin: 'Global Margin',
          marginRate: 'Margin Rate',
          tableTitle: 'Client profitability',
          head: ['Client', 'Equip.', `Revenue (${currencyCode})`, `Costs (${currencyCode})`, `Margin (${currencyCode})`, 'Margin %', 'Interventions'],
        }
      : {
          reportTitle: 'Rapport Financier',
          period: 'Période',
          client: 'Client',
          allClients: 'Tous les clients',
          year: 'Année',
          months: MOIS_LABELS,
          contractRevenue: 'Revenu Contrats',
          totalCosts: 'Coûts Totaux',
          globalMargin: 'Marge Globale',
          marginRate: 'Taux de Marge',
          tableTitle: 'Rentabilité par Client',
          head: ['Client', 'Équip.', `Revenu (${currencyCode})`, `Coûts (${currencyCode})`, `Marge (${currencyCode})`, 'Marge %', 'Interventions'],
        };
    const periodeLabel = finAnnuel ? `${pdfLabels.year} ${finAnnee}` : `${pdfLabels.months[finMois - 1]} ${finAnnee}`;
    const clientLabel = finClient || pdfLabels.allClients;
    const padM = String(finMois).padStart(2, '0');
    const fname = `rapport_financier_${finAnnuel ? finAnnee : finAnnee + '_' + padM}${finClient ? '_' + finClient.replace(/\s+/g, '_') : ''}`;

    await generatePdf(`${pdfLabels.reportTitle} - ${periodeLabel}`, {
      title: pdfLabels.reportTitle,
      subtitle: `${pdfLabels.period}: ${periodeLabel}  |  ${pdfLabels.client}: ${clientLabel}`,
      filename: fname,
      kpis: [
        { label: pdfLabels.contractRevenue, val: moneyK(kpis.revenu_total || 0), color: [22, 163, 74] },
        { label: pdfLabels.totalCosts, val: moneyK(kpis.cout_total || 0), color: [239, 68, 68] },
        { label: pdfLabels.globalMargin, val: moneyK(kpis.marge_globale || 0), color: (kpis.marge_globale || 0) >= 0 ? [22, 163, 74] : [239, 68, 68] },
        { label: pdfLabels.marginRate, val: (kpis.marge_pct || 0) + '%', color: [59, 130, 246] },
      ],
      head: pdfLabels.head,
      table_title: `${pdfLabels.tableTitle} - ${periodeLabel}`,
      rows: clientsList.map((c: any) => [
        c.client || '',
        c.nb_equipements || 0,
        FMT(c.revenu_contrats || 0),
        FMT(c.cout_total || 0),
        FMT(c.marge || 0),
        (c.marge_pct || 0) + '%',
        c.nb_interventions || 0,
      ]),
    });
  };

  const tabs = [
    { icon: <FileText className="w-4 h-4" />, label: 'Rapport Mensuel' },
    { icon: <Building2 className="w-4 h-4" />, label: 'Rapport Client' },
    { icon: <Bot className="w-4 h-4" />, label: 'Rapport IA' },
    { icon: <BarChart3 className="w-4 h-4" />, label: 'Comparaison' },
    { icon: <Star className="w-4 h-4" />, label: 'Fiabilité' },
    { icon: <DollarSign className="w-4 h-4" />, label: 'Rapport Financier' },
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
                <div className="grid grid-cols-2 gap-4">
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
            const clientData = getClientReportData(selClient, selClientMois, selClientAnnee);
            const nbIntv = clientData.length;
            const cout = clientData.reduce((a: number, b: any) => a + getClientLaborCost(b), 0);
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
                    <div className="text-2xl font-black text-purple-400">{money(cout)}</div>
                  </div>
                  <div className="glass rounded-xl p-4 text-center border border-cyan-500/20">
                    <Wrench className="w-5 h-5 text-cyan-400 mx-auto mb-1" />
                    <div className="text-sm text-cyan-400 font-bold">Coût Pièces</div>
                    <div className="text-2xl font-black text-cyan-400">{money(coutPieces)}</div>
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
                            <td className="py-1.5 px-2 font-mono">{Math.round(getClientLaborCost(i)).toLocaleString('fr')}</td>
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
          <SectionCard title={<span className="flex items-center gap-2"><Bot className="w-4 h-4 text-purple-400" /> Rapport IA</span>}>
            <p className="text-sm text-savia-text-muted mb-4">L&apos;IA analyse les interventions, le parc, les coûts, les contrats et le stock réellement disponibles pour générer un rapport détaillé.</p>
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
            {aiReport && (
              <div className="flex justify-end mt-3 mb-2">
                <button
                  onClick={handleAiPdf}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-purple-600 to-pink-500 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-purple-500/20 disabled:opacity-50 text-sm"
                >
                  <Download className="w-4 h-4" />
                  {isPdfGenerating ? 'Génération...' : 'Télécharger PDF'}
                </button>
              </div>
            )}
            <button onClick={handleAiReport} disabled={isGenerating} className="flex items-center justify-center gap-2 px-6 py-3 rounded-lg font-bold text-white bg-gradient-to-r from-purple-600 to-pink-500 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-purple-500/20 w-full mt-4 disabled:opacity-50">
              {isGenerating ? <Loader2 className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
              {isGenerating ? 'L’IA analyse vos données...' : 'Générer le Rapport IA'}
            </button>
          </SectionCard>

          {aiReport && (
            <div className="ai-analysis space-y-4">
              {aiReport.donnees_exploitees && (
                <div className="p-4 rounded-xl bg-indigo-500/10 border-l-4 border-indigo-500">
                  <h4 className="font-bold text-sm text-indigo-300 uppercase tracking-wider mb-3 flex items-center gap-2"><Activity className="w-4 h-4" /> Données réelles exploitées</h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                    {[
                      ['Interventions', aiReport.donnees_exploitees.interventions], ['Équipements', aiReport.donnees_exploitees.equipements],
                      ['Machines analysées', aiReport.donnees_exploitees.machines_analysees], ['Techniciens', aiReport.donnees_exploitees.techniciens_analyses],
                      ['Codes erreurs', aiReport.donnees_exploitees.codes_erreurs], ['Causes récurrentes', aiReport.donnees_exploitees.causes_recurrentes],
                      ['Contrats', aiReport.donnees_exploitees.contrats], ['Références stock', aiReport.donnees_exploitees.references_stock],
                    ].map(([label, value]) => <div key={String(label)} className="p-2 rounded-lg bg-savia-bg/40"><div className="font-black text-indigo-300">{value ?? 0}</div><div className="text-[11px] text-savia-text-muted">{label}</div></div>)}
                  </div>
                </div>
              )}
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
              {aiReport.analyse_parc?.length > 0 && (
                <div className="p-4 rounded-xl bg-cyan-500/10 border-l-4 border-cyan-500">
                  <h4 className="font-bold text-sm text-cyan-300 uppercase tracking-wider mb-3 flex items-center gap-2"><Wrench className="w-4 h-4" /> Analyse du parc par machine</h4>
                  <div className="space-y-3">
                    {aiReport.analyse_parc.map((item: any, index: number) => <div key={`${item.machine}-${index}`} className="p-3 rounded-lg bg-savia-bg/40 border border-savia-border/50"><div className="flex justify-between gap-2 flex-wrap"><span className="font-semibold text-sm">{item.machine}</span><span className="text-xs font-bold text-cyan-300">{item.priorite || 'À évaluer'}</span></div><p className="text-xs text-savia-text-muted mt-1">{item.constat}</p><p className="text-xs text-cyan-200 mt-2"><span className="font-semibold">Action :</span> {item.action}</p></div>)}
                  </div>
                </div>
              )}
              {aiReport.risques_stock?.length > 0 && (
                <div className="p-4 rounded-xl bg-orange-500/10 border-l-4 border-orange-500">
                  <h4 className="font-bold text-sm text-orange-300 uppercase tracking-wider mb-3 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> Risques de stock</h4>
                  <div className="space-y-2">{aiReport.risques_stock.map((item: any, index: number) => <div key={`${item.reference}-${index}`} className="p-3 rounded-lg bg-savia-bg/40 text-xs"><span className="font-semibold text-savia-text">{item.reference}</span> — {item.constat}<div className="mt-1 text-orange-200"><span className="font-semibold">Action :</span> {item.action}</div></div>)}</div>
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
              {aiReport.performance_equipe?.length > 0 && (
                <div className="p-4 rounded-xl bg-savia-surface-hover/60">
                  <h4 className="font-bold text-sm text-savia-text-muted uppercase tracking-wider mb-3 flex items-center gap-2"><Building2 className="w-4 h-4" /> Performance de l&apos;équipe</h4>
                  <div className="space-y-2">{aiReport.performance_equipe.map((item: any, index: number) => <div key={`${item.technicien}-${index}`} className="flex justify-between gap-3 p-2 rounded-lg bg-savia-bg/40 text-sm"><span className="font-semibold">{item.technicien}</span><span className="text-savia-text-muted">{item.evaluation} — {item.commentaire}</span></div>)}</div>
                </div>
              )}
              {aiReport.analyse_couts && (
                <div className="p-4 rounded-xl bg-orange-500/10 border-l-4 border-orange-500">
                  <h4 className="font-bold text-sm text-orange-300 uppercase tracking-wider mb-2 flex items-center gap-2"><DollarSign className="w-4 h-4" /> Analyse des coûts</h4>
                  <p className="text-sm text-savia-text"><span className="font-semibold">{aiReport.analyse_couts.verdict || 'À évaluer'} :</span> {aiReport.analyse_couts.detail}</p>
                  {aiReport.analyse_couts.economie_possible && <p className="text-xs text-orange-200 mt-2">Économie possible : {aiReport.analyse_couts.economie_possible}</p>}
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
                    <div className="text-center p-3 rounded-lg bg-red-500/10"><div className="text-lg font-black text-red-400">{money(aiReport.estimation_couts.cout_curatif_historique || 0)}</div><div className="text-xs text-savia-text-muted">Coût curatif</div></div>
                    <div className="text-center p-3 rounded-lg bg-green-500/10"><div className="text-lg font-black text-green-400">{money(aiReport.estimation_couts.cout_preventif_propose || 0)}</div><div className="text-xs text-savia-text-muted">Préventif proposé</div></div>
                    <div className="text-center p-3 rounded-lg bg-blue-500/10"><div className="text-lg font-black text-blue-400">{money(aiReport.estimation_couts.gain_potentiel || 0)}</div><div className="text-xs text-savia-text-muted">Gain potentiel</div></div>
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
              {aiReport.priorites_immediates?.length > 0 && (
                <div className="p-4 rounded-xl bg-red-500/10 border-l-4 border-red-500">
                  <h4 className="font-bold text-sm text-red-300 uppercase tracking-wider mb-2 flex items-center gap-2"><Target className="w-4 h-4" /> Priorités immédiates</h4>
                  <div className="space-y-1">{aiReport.priorites_immediates.map((item: string, index: number) => <div key={index} className="text-sm text-savia-text flex gap-2"><span className="text-red-300 font-bold">{index + 1}.</span>{item}</div>)}</div>
                </div>
              )}
              {aiReport.donnees_a_completer?.length > 0 && (
                <div className="p-4 rounded-xl bg-yellow-500/10 border-l-4 border-yellow-500">
                  <h4 className="font-bold text-sm text-yellow-300 uppercase tracking-wider mb-2 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> Données à compléter</h4>
                  <div className="space-y-1">{aiReport.donnees_a_completer.map((item: string, index: number) => <div key={index} className="text-sm text-savia-text-muted">• {item}</div>)}</div>
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
          <div className="flex gap-3 items-center">
            {['Client', 'Équipement'].map(m => (
              <button key={m} onClick={() => setCompareMode(m)}
                className={`px-4 py-2 rounded-lg text-sm font-bold transition-all cursor-pointer ${compareMode === m ? 'bg-savia-accent text-white shadow-lg shadow-cyan-500/20' : 'bg-savia-surface-hover text-savia-text-muted hover:text-savia-text'}`}>
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
            const sorted = Object.entries(groups).sort((a, b) => b[1].nb - a[1].nb).slice(0, 12);
            const maxNb = Math.max(...sorted.map(s => s[1].nb), 1);
            const maxDuree = Math.max(...sorted.map(s => s[1].duree), 1);

            // SVG bar chart renderer
            const BarChart = ({ items, getValue, getColor, label, unit }: {
              items: [string, any][],
              getValue: (v: any) => number,
              getColor: (v: any, max: number) => string,
              label: string,
              unit: string
            }) => {
              const W = 600; const H = 200; const PAD_L = 140; const PAD_B = 36; const PAD_T = 16; const PAD_R = 20;
              const chartW = W - PAD_L - PAD_R;
              const chartH = H - PAD_B - PAD_T;
              const max = Math.max(...items.map(([, v]) => getValue(v)), 1);
              const barW = Math.floor(chartW / items.length) - 4;
              return (
                <div className="glass rounded-xl p-4">
                  <div className="text-xs font-bold text-savia-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                    <BarChart3 className="w-3.5 h-3.5 text-savia-accent" /> {label}
                  </div>
                  <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{height: 200}}>
                    {/* Y grid lines */}
                    {[0, 0.25, 0.5, 0.75, 1].map(pct => {
                      const y = PAD_T + chartH * (1 - pct);
                      const val = Math.round(max * pct);
                      return (
                        <g key={pct}>
                          <line x1={PAD_L} y1={y} x2={W - PAD_R} y2={y} stroke="rgba(100,116,139,0.15)" strokeWidth="1" />
                          <text x={PAD_L - 6} y={y + 4} textAnchor="end" fontSize="9" fill="#64748b">
                            {val >= 60 ? `${(val/60).toFixed(1)}h` : `${val}${unit}`}
                          </text>
                        </g>
                      );
                    })}
                    {/* Bars */}
                    {items.map(([key, stats], idx) => {
                      const val = getValue(stats);
                      const bh = Math.max((val / max) * chartH, 1);
                      const x = PAD_L + idx * (chartW / items.length) + 2;
                      const y = PAD_T + chartH - bh;
                      const color = getColor(stats, max);
                      const label2 = key.length > 14 ? key.substring(0, 13) + '…' : key;
                      return (
                        <g key={key}>
                          <rect x={x} y={y} width={barW} height={bh} rx="3" fill={color} opacity="0.85" />
                          <text x={x + barW / 2} y={PAD_T + chartH + 14} textAnchor="middle" fontSize="8" fill="#94a3b8"
                            transform={`rotate(-30, ${x + barW / 2}, ${PAD_T + chartH + 14})`}>
                            {label2}
                          </text>
                          <text x={x + barW / 2} y={y - 3} textAnchor="middle" fontSize="9" fill="#e2e8f0" fontWeight="bold">
                            {unit === '' ? val : val >= 60 ? `${(val/60).toFixed(1)}h` : `${val}${unit}`}
                          </text>
                        </g>
                      );
                    })}
                    {/* X axis */}
                    <line x1={PAD_L} y1={PAD_T + chartH} x2={W - PAD_R} y2={PAD_T + chartH} stroke="rgba(100,116,139,0.4)" strokeWidth="1" />
                  </svg>
                </div>
              );
            };

            return (
              <div className="space-y-4">
                {/* Chart 1: Nombre d'interventions */}
                <BarChart
                  items={sorted}
                  getValue={v => v.nb}
                  getColor={(v, max) => {
                    const pct = v.nb / max;
                    return pct > 0.7 ? '#06b6d4' : pct > 0.4 ? '#3b82f6' : '#8b5cf6';
                  }}
                  label={`Nombre d'interventions par ${compareMode.toLowerCase()}`}
                  unit=""
                />
                {/* Chart 2: Durée totale */}
                <BarChart
                  items={sorted}
                  getValue={v => v.duree}
                  getColor={(v, max) => {
                    const pct = v.duree / max;
                    return pct > 0.7 ? '#f59e0b' : pct > 0.4 ? '#10b981' : '#06b6d4';
                  }}
                  label={`Durée totale des interventions par ${compareMode.toLowerCase()}`}
                  unit=" min"
                />

                {/* Table */}
                <SectionCard title={<span className="flex items-center gap-2"><Wrench className="w-4 h-4 text-savia-accent" /> Détail</span>}>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-savia-border">
                          <th className="text-left py-2 px-3 text-savia-text-muted">{compareMode}</th>
                          <th className="text-center py-2 px-3 text-savia-text-muted">Interventions</th>
                          <th className="text-center py-2 px-3 text-savia-text-muted">Correctives</th>
                          <th className="text-center py-2 px-3 text-savia-text-muted">% Correct.</th>
                          <th className="text-center py-2 px-3 text-savia-text-muted">Durée totale</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(groups).sort((a,b) => b[1].nb - a[1].nb).map(([key, stats]) => (
                          <tr key={key} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50">
                            <td className="py-2.5 px-3 font-bold">{key}</td>
                            <td className="py-2.5 px-3 text-center font-mono">{stats.nb}</td>
                            <td className="py-2.5 px-3 text-center font-mono text-red-400">{stats.corrective}</td>
                            <td className="py-2.5 px-3 text-center">
                              <span className={`text-xs font-bold ${stats.nb > 0 && stats.corrective/stats.nb > 0.6 ? 'text-red-400' : stats.nb > 0 && stats.corrective/stats.nb > 0.3 ? 'text-yellow-400' : 'text-green-400'}`}>
                                {stats.nb > 0 ? Math.round(stats.corrective/stats.nb*100) : 0}%
                              </span>
                            </td>
                            <td className="py-2.5 px-3 text-center font-mono">{(stats.duree / 60).toFixed(1)}h</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </SectionCard>
              </div>
            );
          })()}
        </div>
      )}

      {/* TAB 4: FIABILITÉ */}
      {activeTab === 4 && (
        <div className="space-y-6">
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

            const top12 = fiab.slice(0, 12);

            // Horizontal bar chart for reliability
            const barHeight = 28;
            const gap = 6;
            const PAD_L = 160;
            const PAD_R = 60;
            const svgW = 700;
            const svgH = top12.length * (barHeight + gap) + 20;

            return (
              <>
                {/* Chart: Score de fiabilité */}
                <SectionCard title={<span className="flex items-center gap-2"><Activity className="w-4 h-4 text-savia-accent" /> Score de Fiabilité par Équipement</span>}>
                  <div className="mb-3 flex items-center gap-6 text-xs">
                    <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded-sm bg-green-400"></span> Fiable ≥ 60%</span>
                    <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded-sm bg-yellow-400"></span> Moyen 30–60%</span>
                    <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded-sm bg-red-400"></span> Critique &lt; 30%</span>
                  </div>
                  <svg viewBox={`0 0 ${svgW} ${svgH}`} className="w-full" style={{height: svgH}}>
                    {top12.map((f, idx) => {
                      const y = idx * (barHeight + gap) + 10;
                      const bw = Math.max(((f.score / 100) * (svgW - PAD_L - PAD_R)), 2);
                      const color = f.score >= 60 ? '#4ade80' : f.score >= 30 ? '#facc15' : '#f87171';
                      const shortName = f.machine.length > 22 ? f.machine.substring(0, 21) + '…' : f.machine;
                      return (
                        <g key={f.machine}>
                          <text x={PAD_L - 8} y={y + barHeight / 2 + 4} textAnchor="end" fontSize="10" fill="#94a3b8">{shortName}</text>
                          {/* BG track */}
                          <rect x={PAD_L} y={y} width={svgW - PAD_L - PAD_R} height={barHeight} rx="4" fill="rgba(100,116,139,0.1)" />
                          {/* Score bar */}
                          <rect x={PAD_L} y={y} width={bw} height={barHeight} rx="4" fill={color} opacity="0.8" />
                          {/* Score label */}
                          <text x={PAD_L + bw + 6} y={y + barHeight / 2 + 4} fontSize="11" fill={color} fontWeight="bold">{f.score}%</text>
                          {/* Pannes badge */}
                          <text x={svgW - PAD_R + 4} y={y + barHeight / 2 + 4} fontSize="10" fill="#f87171">{f.pannes} 🔧</text>
                        </g>
                      );
                    })}
                  </svg>
                  {fiab.length > 12 && (
                    <p className="text-xs text-savia-text-muted mt-2 text-center">Affichage des 12 premiers sur {fiab.length} équipements</p>
                  )}
                </SectionCard>

                {/* Donut-style summary */}
                <div className="grid grid-cols-3 gap-4">
                  {[
                    { label: 'Fiables', count: fiab.filter(f => f.score >= 60).length, color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/20' },
                    { label: 'Moyens', count: fiab.filter(f => f.score >= 30 && f.score < 60).length, color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/20' },
                    { label: 'Critiques', count: fiab.filter(f => f.score < 30).length, color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/20' },
                  ].map(s => (
                    <div key={s.label} className={`${s.bg} ${s.border} border rounded-xl p-4 text-center`}>
                      <div className={`text-4xl font-black ${s.color}`}>{s.count}</div>
                      <div className="text-xs text-savia-text-muted mt-1">{s.label}</div>
                    </div>
                  ))}
                </div>

                {/* Detail table */}
                <SectionCard title={<span className="flex items-center gap-2"><Star className="w-4 h-4 text-yellow-400" /> Détail de la Fiabilité</span>}>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-savia-border">
                          {['Équipement', 'Client', 'Score', 'Pannes', 'MTTR moy.', 'Dernière panne'].map(h => (
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
                </SectionCard>
              </>
            );
          })()}
        </div>
      )}

      {/* TAB 5: RAPPORT FINANCIER */}
      {activeTab === 5 && (
        <div className="space-y-6">
          <SectionCard title={<span className="flex items-center gap-2"><DollarSign className="w-4 h-4 text-green-400" /> Rapport Financier</span>}>
            <p className="text-sm text-savia-text-muted mb-4">Générez un rapport PDF financier basé sur les revenus des contrats, coûts d'interventions et rentabilité par client.</p>
            <div className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
              <div><label className="block text-sm text-savia-text-muted mb-1">Client</label>
                <select className={INPUT_CLS} value={finClient} onChange={e => setFinClient(e.target.value)}>
                  <option value="">Tous les clients</option>
                  {clients.map(c => <option key={c} value={c}>{c}</option>)}
                </select></div>
              <div><label className="block text-sm text-savia-text-muted mb-1">Période</label>
                <select className={INPUT_CLS} value={finAnnuel ? 'annuel' : 'mensuel'} onChange={e => setFinAnnuel(e.target.value === 'annuel')}>
                  <option value="mensuel">Mensuel</option>
                  <option value="annuel">Annuel</option>
                </select></div>
              {!finAnnuel && <div><label className="block text-sm text-savia-text-muted mb-1">Mois</label>
                <select className={INPUT_CLS} value={finMois} onChange={e => setFinMois(Number(e.target.value))}>
                  {MOIS_LABELS.map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
                </select></div>}
              <div><label className="block text-sm text-savia-text-muted mb-1">Année</label>
                <input type="number" className={INPUT_CLS} value={finAnnee} min={2020} max={2030} onChange={e => setFinAnnee(Number(e.target.value))} /></div>
              <button onClick={handlePdfFinancier} disabled={isPdfGenerating || finLoading || !finData}
                className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-green-600 to-emerald-500 hover:opacity-90 transition-all cursor-pointer disabled:opacity-50">
                {isPdfGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />} Générer Rapport PDF
              </button>
            </div>
          </SectionCard>

          {finLoading && (
            <div className="flex justify-center items-center h-32"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>
          )}

          {finData && !finLoading && (() => {
            const kpis = finData.kpis || {};
            const clientsList = (finData.clients || []) as any[];
            const rentables = clientsList.filter((c: any) => c.rentable);
            const deficitaires = clientsList.filter((c: any) => !c.rentable && (c.revenu_contrats > 0 || c.cout_total > 0));
            return (
              <div className="space-y-4">
                {/* KPI cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
                  {[
                    { icon: <TrendingUp className="w-5 h-5 text-green-400" />, val: moneyK(kpis.revenu_total || 0), label: 'Revenu Contrats', cls: 'border-green-500/20 bg-green-500/5' },
                    { icon: <TrendingDown className="w-5 h-5 text-red-400" />, val: moneyK(kpis.cout_total || 0), label: 'Coûts Totaux', cls: 'border-red-500/20 bg-red-500/5' },
                    { icon: <DollarSign className="w-5 h-5" style={{ color: (kpis.marge_globale || 0) >= 0 ? '#22c55e' : '#ef4444' }} />, val: moneyK(kpis.marge_globale || 0), label: 'Marge Globale', cls: (kpis.marge_globale || 0) >= 0 ? 'border-green-500/20 bg-green-500/5' : 'border-red-500/20 bg-red-500/5' },
                    { icon: <PieChartIcon className="w-5 h-5 text-blue-400" />, val: (kpis.marge_pct || 0) + '%', label: 'Taux de Marge', cls: 'border-blue-500/20 bg-blue-500/5' },
                    { icon: <Building2 className="w-5 h-5 text-cyan-400" />, val: String(kpis.nb_clients || 0), label: 'Clients', cls: 'border-cyan-500/20 bg-cyan-500/5' },
                    { icon: <CheckCircle2 className="w-5 h-5 text-green-400" />, val: String(kpis.nb_rentables || 0), label: 'Rentables', cls: 'border-green-500/20 bg-green-500/5' },
                    { icon: <AlertTriangle className="w-5 h-5 text-red-400" />, val: String(kpis.nb_deficitaires || 0), label: 'Déficitaires', cls: 'border-red-500/20 bg-red-500/5' },
                  ].map((kpi, i) => (
                    <div key={i} className={`rounded-xl border p-4 text-center ${kpi.cls}`}>
                      <div className="flex justify-center mb-2">{kpi.icon}</div>
                      <div className="text-lg font-black text-savia-text">{kpi.val}</div>
                      <div className="text-xs text-savia-text-muted mt-1">{kpi.label}</div>
                    </div>
                  ))}
                </div>

                {/* Rentabilité par client */}
                {clientsList.length > 0 && (
                  <SectionCard title={<span className="flex items-center gap-2"><BarChart3 className="w-4 h-4 text-savia-accent" /> Rentabilité par Client</span>}>
                    <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                      <table className="w-full text-sm">
                        <thead className="sticky top-0 bg-savia-surface z-10">
                          <tr className="border-b border-savia-border">
                            {['Client', 'Équip.', `Revenu (${currencyCode})`, `Coûts (${currencyCode})`, `Marge (${currencyCode})`, 'Marge %', 'Interventions', 'Statut'].map(h => (
                              <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {clientsList.filter((c: any) => c.revenu_contrats > 0 || c.cout_total > 0).map((c: any, idx: number) => (
                            <tr key={idx} className="border-b border-savia-border/30 hover:bg-savia-surface-hover/50">
                              <td className="py-2 px-3 font-bold text-sm">{c.client}</td>
                              <td className="py-2 px-3 font-mono text-center">{c.nb_equipements}</td>
                              <td className="py-2 px-3 font-mono text-green-400">{FMT(c.revenu_contrats || 0)}</td>
                              <td className="py-2 px-3 font-mono text-red-400">{FMT(c.cout_total || 0)}</td>
                              <td className={`py-2 px-3 font-mono font-bold ${(c.marge || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>{FMT(c.marge || 0)}</td>
                              <td className="py-2 px-3 font-mono">{c.marge_pct || 0}%</td>
                              <td className="py-2 px-3 font-mono text-center">{c.nb_interventions}</td>
                              <td className="py-2 px-3">
                                <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${c.rentable ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                                  {c.rentable ? '✓ Rentable' : '✗ Déficitaire'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </SectionCard>
                )}

                {/* TCO summary */}
                {finTco.length > 0 && (
                  <SectionCard title={<span className="flex items-center gap-2"><Wrench className="w-4 h-4 text-yellow-400" /> Top 10 TCO Équipements</span>}>
                    <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
                      <table className="w-full text-sm">
                        <thead className="sticky top-0 bg-savia-surface z-10">
                          <tr className="border-b border-savia-border">
                            {['Équipement', 'Client', 'Interventions', 'Coût Interv.', 'Coût Pièces', 'Coût M.O.', 'TCO Total'].map(h => (
                              <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {(finTco as any[]).slice(0, 10).map((t: any, idx: number) => (
                            <tr key={idx} className="border-b border-savia-border/30 hover:bg-savia-surface-hover/50">
                              <td className="py-2 px-3 font-bold text-sm">{t.equipement}</td>
                              <td className="py-2 px-3 text-savia-text-muted text-xs">{t.client}</td>
                              <td className="py-2 px-3 font-mono text-center">{t.nb_interventions}</td>
                              <td className="py-2 px-3 font-mono text-red-400">{FMT(t.cout_interventions || 0)}</td>
                              <td className="py-2 px-3 font-mono text-yellow-400">{FMT(t.cout_pieces || 0)}</td>
                              <td className="py-2 px-3 font-mono text-blue-400">{FMT(t.cout_main_oeuvre || 0)}</td>
                              <td className="py-2 px-3 font-mono font-bold">{FMT(t.tco_total || 0)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </SectionCard>
                )}
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

