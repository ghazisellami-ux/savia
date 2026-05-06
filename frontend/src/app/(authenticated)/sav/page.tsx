'use client';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Modal } from '@/components/ui/modal';
import {
  Plus, Search, Wrench, Clock, CheckCircle, AlertTriangle, Loader2, Save,
  Sparkles, FileText, Download, Users, DollarSign, XCircle, ChevronDown,
  ChevronUp, Edit, Calendar, BarChart3, Timer, Wallet, Activity, Target,
  ArrowUpRight, ArrowDownRight, Zap, Shield, TrendingUp, Gauge, Briefcase,
  ClipboardList, Brain, Lightbulb, ThumbsUp, ThumbsDown, Server, Building2,
  Filter, CalendarDays, CalendarRange, Camera, Eye, ImageOff, Upload,
  Receipt, CircleDot, AlertOctagon, CheckCircle2, Ban, Check, X
} from 'lucide-react';
import { interventions, ai, equipements, techniciens as techApi, contrats as contratsApi, clients as clientsApi, typesIntervention } from '@/lib/api';
import { FichesSigneesTab } from './FichesSigneesTab';
import { useAuth } from '@/lib/auth-context';

interface Intervention {
  id: number;
  date: string;
  machine: string;
  client: string;
  type: string;
  technicien: string;
  duree: number;
  duree_minutes: number;
  deplacement: number;
  statut: string;
  description: string;
  probleme: string;
  cause: string;
  solution: string;
  code_erreur: string;
  type_erreur: string;
  priorite: string;
  pieces_utilisees: string;
  coutPieces: number;
  cout: number;
}

const INPUT_CLS = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all";

const TYPES_ERREUR = ["Hardware", "Software", "Réseau", "Calibration", "Mécanique", "Électrique", "Autre"];
const PRIORITES = ["Haute", "Moyenne", "Basse"];

const MONTHS = [
  { value: 0, label: 'Janvier' }, { value: 1, label: 'Février' }, { value: 2, label: 'Mars' },
  { value: 3, label: 'Avril' }, { value: 4, label: 'Mai' }, { value: 5, label: 'Juin' },
  { value: 6, label: 'Juillet' }, { value: 7, label: 'Août' }, { value: 8, label: 'Septembre' },
  { value: 9, label: 'Octobre' }, { value: 10, label: 'Novembre' }, { value: 11, label: 'Décembre' },
];

export default function SavPage() {
  const { user } = useAuth();
  const isTechnicien = user?.role === 'Technicien';

  const [activeTab, setActiveTab] = useState(0);
  const [ficheFile, setFicheFile] = useState<File | null>(null);
  const [fiches, setFiches] = useState<any[]>([]);
  const [allPieces, setAllPieces] = useState<any[]>([]);
  const [rupturePieces, setRupturePieces] = useState<any[]>([]); // pièces sélectionnées en rupture
  const [equipementsData, setEquipementsData] = useState<any[]>([]);
  const [clientsData, setClientsData] = useState<any[]>([]);
  const [contratsData, setContratsData] = useState<any[]>([]);
  const [intervDetailItem, setIntervDetailItem] = useState<any>(null);
  const [lichboxId, setLightboxId] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  // Technicien: voir par défaut seulement ses interventions "En cours"
  const [filterStatut, setFilterStatut] = useState(isTechnicien ? 'En cours' : 'Tous');
  const [filterType, setFilterType] = useState('Tous');
  const [filterClient, setFilterClient] = useState('Tous');
  const [filterEquip, setFilterEquip] = useState('Tous');
  const [periodMode, setPeriodMode] = useState<'mensuel' | 'annuel'>('annuel');
  const [filterMonth, setFilterMonth] = useState(new Date().getMonth());
  const [filterYear, setFilterYear] = useState(new Date().getFullYear());
  const [data, setData] = useState<Intervention[]>([]);
  const [techniciens, setTechniciens] = useState<{nom: string, prenom: string}[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [selectedIntervention, setSelectedIntervention] = useState<Intervention | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [aiResult, setAiResult] = useState<any>(null);
  const [aiError, setAiError] = useState('');
  const [isPdfGenerating, setIsPdfGenerating] = useState(false);
  const [facturationData, setFacturationData] = useState<any[]>([]);
  const [factFilter, setFactFilter] = useState<'all' | 'pending' | 'done' | 'overdue'>('all');
  const [factDetailItem, setFactDetailItem] = useState<any>(null);
  const [savTechDropdownOpen, setSavTechDropdownOpen] = useState(false);
  const [pdfDateFrom, setPdfDateFrom] = useState(() => {
    const d = new Date(); d.setMonth(d.getMonth() - 1);
    return d.toISOString().substring(0, 10);
  });
  const [pdfDateTo, setPdfDateTo] = useState(() => new Date().toISOString().substring(0, 10));

  const emptyForm = { date: new Date().toISOString().substring(0, 10), client: '', machine: '', technicien: '', type_intervention: 'Corrective', probleme: '', description: '', statut: 'En cours', duree_minutes: '60', cout_pieces: '0', code_erreur: '', type_erreur: 'Hardware', priorite: 'Moyenne', pieces_utilisees: '' };
  const [form, setForm] = useState(emptyForm);
  const [statusForm, setStatusForm] = useState({ statut: '', probleme: '', cause: '', solution: '', duree_minutes: '' });

  // Custom intervention types ("Autre" pattern)
  const TYPES_INTERVENTION_BASE = ['Corrective', 'Préventive', 'Installation', 'Formation', 'Démo'];
  const [customInterventionTypes, setCustomInterventionTypes] = useState<string[]>([]);
  const [customTypeMode, setCustomTypeMode] = useState(false);
  const [customTypeValue, setCustomTypeValue] = useState('');

  // Load custom types from database on mount
  useEffect(() => {
    typesIntervention.list()
      .then((res) => setCustomInterventionTypes(res.map(t => t.nom)))
      .catch(() => {});
  }, []);

  const allInterventionTypes = useMemo(() => {
    const merged = [...TYPES_INTERVENTION_BASE];
    for (const ct of customInterventionTypes) {
      if (!merged.includes(ct)) merged.push(ct);
    }
    return merged;
  }, [customInterventionTypes]);

  // Derived filter options
  const dynamicClients = useMemo(() => ['Tous', ...Array.from(new Set(data.map(d => d.client).filter(Boolean)))], [data]);
  const dynamicEquip = useMemo(() => ['Tous', ...Array.from(new Set(data.map(d => d.machine).filter(Boolean)))], [data]);
  const availableYears = useMemo(() => {
    const years = new Set(data.map(d => new Date(d.date).getFullYear()).filter(y => !isNaN(y)));
    years.add(new Date().getFullYear());
    return Array.from(years).sort((a, b) => b - a);
  }, [data]);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [res, techRes] = await Promise.all([
        interventions.list(),
        techApi.list().catch(() => [])
      ]);
      setTechniciens(techRes as any);
      const normalizeStatut = (s: string): string => {
        if (!s) return 'En cours';
        const low = s.toLowerCase();
        if (low.includes('tur') || low.includes('termin') || low.includes('clotur')) return 'Cloturee';
        if (low.includes('cours')) return 'En cours';
        if (low.includes('planif')) return 'Planifiee';
        return s;
      };
      const mapped = res.map((item: any) => ({
        id: Number(item.id || 0),
        date: item.date || 'N/A',
        machine: item.machine || '',
        client: item.client || '',
        type: item.type_intervention || 'Corrective',
        technicien: item.technicien || 'Non assign\u00e9',
        duree: Math.round((item.duree_minutes || 0) / 60),
        duree_minutes: item.duree_minutes || 0,
        deplacement: item.deplacement || 0,
        statut: normalizeStatut(item.statut || ''),
        description: item.description || '',
        probleme: item.probleme || '',
        cause: item.cause || '',
        solution: item.solution || '',
        code_erreur: item.code_erreur || '',
        type_erreur: item.type_erreur || '',
        priorite: item.priorite || 'Moyenne',
        pieces_utilisees: item.pieces_utilisees || '',
        coutPieces: item.cout_pieces || 0,
        cout: item.cout || 0,
      }));
      setData(mapped);
    } catch (err) {
      console.error("Failed to fetch interventions", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    interventions.listFiches().then(setFiches).catch(() => {});
    interventions.listFacturation().then(setFacturationData).catch(() => {});
    // Charger toutes les pièces pour le sélecteur rupture
    import('@/lib/api').then(({ pieces: piecesApi }) => {
      piecesApi.list().then((data: any) => setAllPieces(data || [])).catch(() => {});
    });
    // Charger équipements + contrats pour la fiche PDF
    equipements.list().then((res: any) => setEquipementsData(res || [])).catch(() => {});
    clientsApi.list().then((res: any) => setClientsData(res || [])).catch(() => {});
    contratsApi.list().then((res: any) => setContratsData(res || [])).catch(() => {});
  }, []);


  const handleSave = async () => {
    if (!form.machine.trim()) return;
    setIsSaving(true);
    try {
      await interventions.create({
        ...form,
        duree_minutes: Number(form.duree_minutes),
        cout_pieces: Number(form.cout_pieces),
      });
      setForm(emptyForm);
      setShowAddModal(false);
      await loadData();
    } catch (err) {
      console.error("Save failed", err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleStatusChange = async () => {
    if (!selectedIntervention) return;
    setIsSaving(true);
    try {
      const payload: any = {
        statut: statusForm.statut,
        probleme: statusForm.probleme,
        cause: statusForm.cause,
        solution: statusForm.solution,
        duree_minutes: Number(statusForm.duree_minutes) || selectedIntervention.duree_minutes,
      };
      // Envoyer les pièces en rupture sélectionnées pour générer des notifications
      if (statusForm.statut.toLowerCase().includes('attente') && statusForm.statut.toLowerCase().includes('pi')) {
        payload.pieces_rupture = rupturePieces.map((p: any) => ({
          reference: p.reference || '',
          designation: p.designation || p.nom || '',
          ref: p.reference || '',
        }));
      }
      await interventions.update(selectedIntervention.id, payload);
      // Upload fiche photo si clôture + fichier sélectionné
      if (statusForm.statut.toLowerCase().includes('tur') && ficheFile) {
        try {
          await interventions.uploadFiche(selectedIntervention.id, ficheFile);
        } catch (fe) {
          console.error('Erreur upload fiche:', fe);
        }
      }
      setFicheFile(null);
      setRupturePieces([]);
      setShowStatusModal(false);
      setSelectedIntervention(null);
      await loadData();
      // Rafraîchir les fiches
      interventions.listFiches().then(setFiches).catch(() => {});
    } catch (err) {
      console.error("Status update failed", err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleAiAnalyze = async () => {
    setIsAnalyzing(true);
    setAiError('');
    setAiResult(null);
    setActiveTab(4); // Switch to AI tab
    try {
      const allInterv = data;
      const nb_total = allInterv.length;
      const nb_cloturees = allInterv.filter(i => i.statut.toLowerCase().includes('tur') || i.statut.toLowerCase().includes('termin')).length;
      const nb_en_cours = allInterv.filter(i => i.statut.toLowerCase().includes('cours')).length;
      const nb_correctives = allInterv.filter(i => i.type.toLowerCase().includes('correct')).length;
      const nb_preventives = allInterv.filter(i => i.type.toLowerCase().includes('ventive')).length;
      const nb_installations = allInterv.filter(i => i.type.toLowerCase().includes('install')).length;
      const totalCoutInterv = allInterv.reduce((a, b) => a + (b.cout || 0), 0);
      const totalCoutPieces = allInterv.reduce((a, b) => a + (b.coutPieces || 0), 0);
      const totalDureeMin = allInterv.reduce((a, b) => a + b.duree_minutes, 0);
      const tauxRes = nb_total > 0 ? Math.round((nb_cloturees / nb_total) * 100) : 0;
      const mttrH = nb_cloturees > 0 ? Math.round(allInterv.filter(i => i.statut.toLowerCase().includes('tur')).reduce((a, b) => a + b.duree_minutes, 0) / nb_cloturees / 60 * 10) / 10 : 0;

      // Build tech details string
      const techMap = new Map<string, {nb: number, clot: number, duree: number, cout: number}>();
      allInterv.forEach(i => {
        const t = i.technicien || 'Inconnu';
        const prev = techMap.get(t) || {nb: 0, clot: 0, duree: 0, cout: 0};
        prev.nb++;
        if (i.statut.toLowerCase().includes('tur')) prev.clot++;
        prev.duree += i.duree_minutes;
        prev.cout += (i.cout || i.coutPieces);
        techMap.set(t, prev);
      });
      let tech_details = '';
      techMap.forEach((s, nom) => {
        const taux = s.nb > 0 ? Math.round((s.clot / s.nb) * 100) : 0;
        const mttr = s.clot > 0 ? Math.round(s.duree / s.clot / 60 * 10) / 10 : 0;
        tech_details += `- ${nom}: ${s.nb} interventions, ${s.clot} clôturées, taux=${taux}%, MTTR=${mttr}h, coût=${s.cout} TND\n`;
      });

      // Build machine details
      const machineMap = new Map<string, number>();
      allInterv.forEach(i => machineMap.set(i.machine, (machineMap.get(i.machine) || 0) + 1));
      let machines_detail = '';
      Array.from(machineMap.entries()).sort((a, b) => b[1] - a[1]).slice(0, 15).forEach(([m, nb]) => {
        machines_detail += `- ${m}: ${nb} interventions\n`;
      });

      // Client details
      const clientMap = new Map<string, number>();
      allInterv.forEach(i => { if (i.client) clientMap.set(i.client, (clientMap.get(i.client) || 0) + 1); });
      let clients_detail = '';
      Array.from(clientMap.entries()).sort((a, b) => b[1] - a[1]).forEach(([c, nb]) => {
        clients_detail += `- ${c}: ${nb} interventions\n`;
      });

      // Recent interventions
      let interventions_detail = '';
      allInterv.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()).slice(0, 20).forEach(i => {
        interventions_detail += `- ${i.date.substring(0,10)} | ${i.machine} | ${i.technicien} | ${i.type} | ${i.statut} | ${i.duree}h | ${i.cout || i.coutPieces} TND | ${i.probleme || '-'}\n`;
      });

      const sav_data = {
        nb_total, nb_cloturees, nb_en_cours, taux_resolution: tauxRes, mttr_h: mttrH,
        duree_totale_h: Math.round(totalDureeMin / 60),
        nb_correctives, nb_preventives, nb_installations,
        ratio_correctif_pct: nb_total > 0 ? Math.round((nb_correctives / nb_total) * 100) : 0,
        cout_interventions: totalCoutInterv, cout_pieces: totalCoutPieces,
        cout_total: totalCoutInterv + totalCoutPieces,
        cout_moyen: nb_total > 0 ? Math.round((totalCoutInterv + totalCoutPieces) / nb_total) : 0,
        tech_details, machines_detail, clients_detail, interventions_detail,
      };

      const res = await ai.analyzeSav(sav_data, 'TND');
      if (res.ok && res.result) {
        setAiResult(typeof res.result === 'string' ? JSON.parse(res.result) : res.result);
      } else {
        setAiError("L'IA n'a pas pu générer d'analyse.");
      }
    } catch (err: any) {
      setAiError(err?.message || "Erreur lors de l'analyse IA.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  // PDF Generation
  const handleGeneratePdf = async () => {
    setIsPdfGenerating(true);
    try {
      const token = localStorage.getItem('savia_token') || '';
      const cn    = localStorage.getItem('savia_company') || 'SAVIA';
      const cl    = localStorage.getItem('savia_logo') || '';

      const pdfFiltered = data.filter(i => {
        const d = new Date(i.date);
        return d >= new Date(pdfDateFrom) && d <= new Date(pdfDateTo + 'T23:59:59');
      }).sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

      const cloturees = pdfFiltered.filter(i => i.statut.toLowerCase().includes('tur')).length;
      const coutT     = pdfFiltered.reduce((acc, b) => acc + (b.cout || b.coutPieces || 0), 0);
      const tauxRes   = pdfFiltered.length > 0 ? Math.round((cloturees / pdfFiltered.length) * 100) : 0;

      const payload = {
        title: 'Rapport SAV — Interventions',
        subtitle: `Période : ${pdfDateFrom} au ${pdfDateTo}`,
        filename: 'rapport_sav_interventions',
        company_name: cn,
        company_logo: cl,
        is_ai_report: false,
        kpis: [
          { label: 'Interventions', val: String(pdfFiltered.length), color: '#01B4BC' },
          { label: 'Clôturées',      val: String(cloturees),         color: '#5FA55A' },
          { label: 'Taux résolution', val: tauxRes + '%',               color: '#FA8925' },
          { label: 'Coût total (TND)', val: coutT.toLocaleString('fr'), color: '#5FA55A' },
        ],
        tables: [{
          title: 'Détail des interventions',
          head: ['Date', 'Machine', 'Client', 'Technicien', 'Type', 'Statut', 'Durée', 'Coût (TND)'],
          rows: pdfFiltered.map(i => [
            i.date.substring(0, 10),
            i.machine || '-',
            i.client  || '-',
            i.technicien || '-',
            i.type    || '-',
            i.statut  || '-',
            (i.duree  || 0) + 'h',
            (i.cout   || i.coutPieces || 0).toLocaleString('fr'),
          ]),
        }],
      };

      const res = await fetch('/api/reports/generate-pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Erreur ' + res.status);
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href = url;
      a.download = `rapport_sav_${pdfDateFrom}_${pdfDateTo}.pdf`;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url);
    } catch (err: any) {
      alert('Erreur PDF: ' + err.message);
    } finally {
      setIsPdfGenerating(false);
    }
  }
  // ---- AI PDF download (SAV analysis) ----
  const handleSavAiPdf = async () => {
    if (!aiResult) return;
    setIsPdfGenerating(true);
    try {
      const token = localStorage.getItem('savia_token') || '';
      const cn = localStorage.getItem('savia_company') || 'SAVIA';
      const cl = localStorage.getItem('savia_logo') || '';
      const res = await fetch('/api/reports/generate-pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify({
          title: 'Analyse IA - Interventions SAV',
          subtitle: 'Rapport d\'analyse IA complet',
          filename: 'analyse_ia_sav',
          company_name: cn, company_logo: cl,
          is_ai_report: true,
          ai_content: JSON.stringify(aiResult),
        }),
      });
      if (!res.ok) throw new Error('Erreur ' + res.status);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'analyse_ia_sav.pdf';
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url);
    } catch(err: any) { alert('Erreur PDF: ' + err.message); }
    finally { setIsPdfGenerating(false); }
  };

  // ===== PDF Fiche d'intervention (backend FPDF) =====
  const handleDownloadFicheIntervention = async (interv: any) => {
    try {
      const token = localStorage.getItem('savia_token') || '';
      const cn = localStorage.getItem('savia_company') || 'SAVIA';
      const cl = localStorage.getItem('savia_logo') || '';
      const res = await fetch(`/api/interventions/${interv.id}/fiche-pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
        body: JSON.stringify({ company_name: cn, company_logo: cl }),
      });
      if (!res.ok) throw new Error('Erreur ' + res.status);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `fiche_intervention_${interv.id}.pdf`;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url);
    } catch (err: any) { alert('Erreur PDF: ' + err.message); }
  };

  // ===== FILTERING with period mode (mensuel/annuel) + client + equipment + status =====
  const filtered = useMemo(() => {
    return data.filter(i => {
      // Period filter
      const d = new Date(i.date);
      if (!isNaN(d.getTime())) {
        if (d.getFullYear() !== filterYear) return false;
        if (periodMode === 'mensuel' && d.getMonth() !== filterMonth) return false;
      }
      if (filterStatut !== 'Tous' && i.statut !== filterStatut) return false;
      if (filterType !== 'Tous' && !i.type.toLowerCase().includes(filterType.toLowerCase())) return false;
      if (filterClient !== 'Tous' && i.client !== filterClient) return false;
      if (filterEquip !== 'Tous' && i.machine !== filterEquip) return false;
      if (search && !i.machine.toLowerCase().includes(search.toLowerCase()) && !String(i.id).includes(search) && !i.technicien.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [search, filterStatut, filterType, filterClient, filterEquip, periodMode, filterMonth, filterYear, data]);

  // ===== KPI CALCULATIONS (based on filtered data) =====
  const totalInterv = filtered.length;
  const terminees = filtered.filter(i => i.statut.toLowerCase().includes('tur') || i.statut.toLowerCase().includes('termin')).length;
  const enCours = filtered.filter(i => i.statut.toLowerCase().includes('cours')).length;
  const totalCout = filtered.reduce((a, b) => a + (b.cout || b.coutPieces), 0);
  const totalDureeH = Math.round(filtered.reduce((a, b) => a + b.duree_minutes, 0) / 60);
  const tauxResolution = totalInterv > 0 ? Math.round((terminees / totalInterv) * 100) : 0;
  const mttr = terminees > 0 ? Math.round(filtered.filter(i => i.statut.toLowerCase().includes('tur')).reduce((a, b) => a + b.duree_minutes, 0) / terminees / 60 * 10) / 10 : 0;
  const correctifs = filtered.filter(i => i.type.toLowerCase().includes('correct')).length;
  const preventifs = filtered.filter(i => i.type.toLowerCase().includes('ventive') || i.type.toLowerCase().includes('préventive')).length;

  // Tech performance
  const techStats = useMemo(() => {
    const map = new Map<string, {nb: number, clot: number, duree: number, cout: number}>();
    filtered.forEach(i => {
      const t = i.technicien || 'Inconnu';
      const prev = map.get(t) || {nb: 0, clot: 0, duree: 0, cout: 0};
      prev.nb++;
      if (i.statut.toLowerCase().includes('tur')) prev.clot++;
      prev.duree += i.duree_minutes;
      prev.cout += (i.cout || i.coutPieces);
      map.set(t, prev);
    });
    return Array.from(map.entries()).map(([nom, s]) => ({
      nom, nb: s.nb, clot: s.clot,
      taux: s.nb > 0 ? Math.round((s.clot / s.nb) * 100) : 0,
      mttr: s.clot > 0 ? Math.round(s.duree / s.clot / 60 * 10) / 10 : 0,
      cout: s.cout,
    })).sort((a, b) => b.taux - a.taux);
  }, [filtered]);

  // Financial summary
  const coutPieces = filtered.reduce((a, b) => a + (b.coutPieces || 0), 0);
  const coutInterventions = filtered.reduce((a, b) => a + (b.cout || 0), 0);

  const tabs = [
    { icon: <Wrench className="w-4 h-4" />, label: 'Interventions' },
    { icon: <Users className="w-4 h-4" />, label: 'Performance Équipe' },
    { icon: <Wallet className="w-4 h-4" />, label: 'Charge Financière' },
    { icon: <FileText className="w-4 h-4" />, label: 'Rapport PDF' },
    { icon: <Sparkles className="w-4 h-4" />, label: 'Analyse IA' },
    { icon: <Camera className="w-4 h-4" />, label: 'Fiches Signées' },
    { icon: <Receipt className="w-4 h-4" />, label: 'Suivi Facturation' },
  ];

  // Facturation helpers
  const handleMarkFactured = async (id: number) => {
    try {
      await interventions.markFactured(id);
      const updated = await interventions.listFacturation();
      setFacturationData(updated);
    } catch (e) { console.error('Mark factured failed', e); }
  };
  const filteredFacturation = useMemo(() => {
    return facturationData.filter((f: any) => {
      if (factFilter === 'done') return f.facture_envoyee;
      if (factFilter === 'pending') return !f.facture_envoyee && !f.en_retard;
      if (factFilter === 'overdue') return f.en_retard;
      return true;
    });
  }, [facturationData, factFilter]);

  if (isLoading) {
    return (<div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>);
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
            <Wrench className="w-7 h-7" /> SAV &amp; Interventions
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Suivi complet des interventions techniques</p>
        </div>
        {!isTechnicien && (
          <button onClick={() => setShowAddModal(true)} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer shadow-lg">
            <Plus className="w-4 h-4" /> Nouvelle intervention
          </button>
        )}
      </div>

      {/* Bandeau Technicien */}
      {isTechnicien && (
        <div className="glass rounded-xl px-4 py-3 border border-savia-accent/20 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 text-sm text-savia-accent">
            <Wrench className="w-4 h-4" />
            <span>Vos interventions assignées —
              <strong className="ml-1">{data.filter(i => i.statut.toLowerCase().includes('cours')).length} en cours</strong>
            </span>
          </div>
          <div className="flex gap-2">
            <button onClick={() => setFilterStatut('En cours')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold cursor-pointer transition-all ${
                filterStatut === 'En cours' ? 'bg-savia-accent text-white' : 'bg-savia-surface border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover'
              }`}>En cours</button>
            <button onClick={() => setFilterStatut('Tous')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold cursor-pointer transition-all ${
                filterStatut === 'Tous' ? 'bg-savia-accent text-white' : 'bg-savia-surface border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover'
              }`}>Tout l&apos;historique</button>
          </div>
        </div>
      )}

      {/* Period Filter Bar — masqué pour Technicien */}
      {!isTechnicien && <div className="glass rounded-xl p-4 space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
          {/* Period Mode Toggle */}
          <div>
            <label className="flex items-center gap-2 text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
              <Calendar className="w-3.5 h-3.5" /> Période
            </label>
            <div className="flex rounded-lg overflow-hidden border border-savia-border">
              <button
                onClick={() => setPeriodMode('mensuel')}
                className={`flex-1 py-2.5 text-sm font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
                  periodMode === 'mensuel'
                    ? 'bg-savia-accent text-white'
                    : 'bg-savia-bg/50 text-savia-text-muted hover:bg-savia-surface-hover/30'
                }`}
              >
                <CalendarDays className="w-3.5 h-3.5" /> Mensuel
              </button>
              <button
                onClick={() => setPeriodMode('annuel')}
                className={`flex-1 py-2.5 text-sm font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
                  periodMode === 'annuel'
                    ? 'bg-savia-accent text-white'
                    : 'bg-savia-bg/50 text-savia-text-muted hover:bg-savia-surface-hover/30'
                }`}
              >
                <CalendarRange className="w-3.5 h-3.5" /> Annuel
              </button>
            </div>
          </div>

          {/* Month Selector (only in mensuel mode) */}
          {periodMode === 'mensuel' && (
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">Mois</label>
              <select
                value={filterMonth}
                onChange={e => setFilterMonth(Number(e.target.value))}
                className="w-full bg-savia-surface border border-savia-border rounded-lg px-3 py-2.5 text-sm text-savia-text"
              >
                {MONTHS.map(m => (
                  <option key={m.value} value={m.value}>{m.value + 1} — {m.label}</option>
                ))}
              </select>
            </div>
          )}

          {/* Year Selector */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">Année</label>
            <select
              value={filterYear}
              onChange={e => setFilterYear(Number(e.target.value))}
              className="w-full bg-savia-surface border border-savia-border rounded-lg px-3 py-2.5 text-sm text-savia-text"
            >
              {availableYears.map(y => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Period Summary */}
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-savia-accent/5 border border-savia-accent/20">
          <Filter className="w-4 h-4 text-savia-accent" />
          <span className="text-sm font-semibold text-savia-accent">
            Période : {periodMode === 'mensuel' ? `${MONTHS[filterMonth]?.label} ${filterYear}` : `Année ${filterYear}`}
          </span>
          <span className="text-xs text-savia-text-muted">
            | {filtered.length} intervention{filtered.length > 1 ? 's' : ''}
          </span>
        </div>
      </div>}

      {/* KPIs Row */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {[
          { label: 'Total', value: totalInterv, icon: <Wrench className="w-5 h-5" />, color: 'text-savia-accent' },
          { label: 'Clôturées', value: terminees, icon: <CheckCircle className="w-5 h-5" />, color: 'text-green-400' },
          { label: 'En cours', value: enCours, icon: <Clock className="w-5 h-5" />, color: 'text-yellow-400' },
          { label: 'Taux résol.', value: `${tauxResolution}%`, icon: <Target className="w-5 h-5" />, color: 'text-blue-400' },
          { label: 'MTTR', value: `${mttr}h`, icon: <Timer className="w-5 h-5" />, color: 'text-purple-400' },
          { label: 'Coût total', value: `${(totalCout/1000).toFixed(0)}K`, icon: <DollarSign className="w-5 h-5" />, color: 'text-red-400' },
        ].map(k => (
          <div key={k.label} className="glass rounded-xl p-3 text-center">
            <div className={`flex justify-center mb-1 ${k.color}`}>{k.icon}</div>
            <div className={`text-2xl font-black ${k.color}`}>{k.value}</div>
            <div className="text-xs text-savia-text-muted mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 glass rounded-xl p-1 overflow-x-auto">
        {tabs.map((tab, i) => (
          <button key={i} onClick={() => setActiveTab(i)}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-all cursor-pointer whitespace-nowrap ${
              activeTab === i
                ? 'bg-gradient-to-r from-savia-accent to-savia-accent-blue text-white shadow-md'
                : 'text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover'
            }`}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* ===== TAB 0: INTERVENTIONS TABLE ===== */}
      {activeTab === 0 && (
        <>
          {/* Filters Row */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
              <input type="text" placeholder="Rechercher..." value={search} onChange={e => setSearch(e.target.value)}
                className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
            </div>
            <select value={filterStatut} onChange={e => setFilterStatut(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              <option value="Tous">Tous les statuts</option>
              <option value="Cloturee">Cloturee</option>
              <option value="En cours">En cours</option>
              <option value="Planifiee">Planifiee</option>
            </select>
            <select value={filterType} onChange={e => setFilterType(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              <option value="Tous">Tous les types</option>
              <option value="Corrective">Corrective</option>
              <option value="Préventive">Préventive</option>
              <option value="Installation">Installation</option>
            </select>
            <select value={filterClient} onChange={e => setFilterClient(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              {dynamicClients.map(c => <option key={c} value={c}>{c === 'Tous' ? 'Tous les clients' : c}</option>)}
            </select>
            <select value={filterEquip} onChange={e => setFilterEquip(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
              {dynamicEquip.map(e => <option key={e} value={e}>{e === 'Tous' ? 'Tous les équipements' : e}</option>)}
            </select>
          </div>

          <div className="glass rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-savia-border/50 flex items-center gap-2">
              <ClipboardList className="w-4 h-4 text-savia-accent" />
              <span className="font-semibold text-sm">{filtered.length} intervention{filtered.length > 1 ? 's' : ''}</span>
            </div>
            {/* Table with max 5 visible rows + scroll */}
            <div className="overflow-x-auto max-h-[310px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10 bg-savia-surface-hover/80 backdrop-blur-sm">
                  <tr className="border-b border-savia-border">
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs whitespace-nowrap">
                      <div className="flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" /> Date</div>
                    </th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs whitespace-nowrap">
                      <div className="flex items-center gap-1.5"><Server className="w-3.5 h-3.5" /> Machine</div>
                    </th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs whitespace-nowrap">
                      <div className="flex items-center gap-1.5"><Building2 className="w-3.5 h-3.5" /> Client</div>
                    </th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs whitespace-nowrap">
                      <div className="flex items-center gap-1.5"><Users className="w-3.5 h-3.5" /> Technicien</div>
                    </th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs whitespace-nowrap">
                      <div className="flex items-center gap-1.5"><Wrench className="w-3.5 h-3.5" /> Type</div>
                    </th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs whitespace-nowrap">
                      <div className="flex items-center gap-1.5"><Activity className="w-3.5 h-3.5" /> Statut</div>
                    </th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs whitespace-nowrap">
                      <div className="flex items-center gap-1.5"><Zap className="w-3.5 h-3.5" /> Code</div>
                    </th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs whitespace-nowrap">
                      <div className="flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5" /> Priorité</div>
                    </th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs whitespace-nowrap">
                      <div className="flex items-center gap-1.5"><Timer className="w-3.5 h-3.5" /> Durée</div>
                    </th>
                    <th className="py-2.5 px-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()).map(i => (
                    <tr key={i.id} className="border-b border-savia-border/30 hover:bg-savia-surface-hover/50 transition-colors">
                      <td className="py-2.5 px-3 text-xs">{i.date.substring(0, 10)}</td>
                      <td className="py-2.5 px-3 font-semibold text-sm">{i.machine}</td>
                      <td className="py-2.5 px-3 text-sm text-savia-text-muted">{i.client || '—'}</td>
                      <td className="py-2.5 px-3 text-sm">{i.technicien}</td>
                      <td className="py-2.5 px-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${i.type.toLowerCase().includes('correct') ? 'bg-red-500/10 text-red-400' : i.type.toLowerCase().includes('ventive') ? 'bg-green-500/10 text-green-400' : 'bg-blue-500/10 text-blue-400'}`}>{i.type}</span>
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${(i.statut.toLowerCase().includes('tur') || i.statut.toLowerCase().includes('termin')) ? 'bg-green-500/10 text-green-400' : i.statut.toLowerCase().includes('cours') ? 'bg-yellow-500/10 text-yellow-400' : 'bg-blue-500/10 text-blue-400'}`}>{i.statut}</span>
                      </td>
                      <td className="py-2.5 px-3 font-mono text-xs text-savia-accent">{i.code_erreur || '—'}</td>
                      <td className="py-2.5 px-3">
                        {i.priorite && <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${i.priorite === 'Haute' ? 'bg-red-500/10 text-red-400' : i.priorite === 'Basse' ? 'bg-green-500/10 text-green-400' : 'bg-yellow-500/10 text-yellow-400'}`}>{i.priorite}</span>}
                      </td>
                      <td className="py-2.5 px-3 font-mono text-xs">{i.duree}h</td>
                      <td className="py-2.5 px-3">
                        <div className="flex items-center gap-1">
                          <button onClick={() => {
                            setSelectedIntervention(i);
                            setStatusForm({ statut: i.statut, probleme: i.probleme, cause: i.cause, solution: i.solution, duree_minutes: String(i.duree_minutes) });
                            setShowStatusModal(true);
                          }} className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 cursor-pointer transition-colors">
                            <Edit className="w-3.5 h-3.5" />
                          </button>
                          <button onClick={() => setIntervDetailItem(i)}
                            title="Voir les détails"
                            className="p-1.5 rounded-lg bg-teal-500/10 text-teal-400 hover:bg-teal-500/20 cursor-pointer transition-colors">
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                          {(i.statut.toLowerCase().includes('tur') || i.statut.toLowerCase().includes('termin')) && (
                            <button onClick={() => handleDownloadFicheIntervention(i)}
                              title="Télécharger fiche PDF"
                              className="p-1.5 rounded-lg bg-green-500/10 text-green-400 hover:bg-green-500/20 cursor-pointer transition-colors">
                              <Download className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {filtered.length === 0 && (
                    <tr><td colSpan={10} className="text-center py-8 text-savia-text-dim">
                      <Wrench className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      Aucune intervention trouvée pour cette période.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ===== TAB 1: PERFORMANCE EQUIPE ===== */}
      {activeTab === 1 && (
        <div className="space-y-6">
          {/* Score global */}
          <div className="glass rounded-xl p-6 text-center">
            <div className="text-sm text-savia-text-muted mb-2 uppercase tracking-wider font-bold flex items-center justify-center gap-2">
              <Gauge className="w-4 h-4 text-savia-accent" /> Score de Performance Global
            </div>
            <div className={`text-6xl font-black ${tauxResolution >= 70 ? 'text-green-400' : tauxResolution >= 40 ? 'text-yellow-400' : 'text-red-400'}`}>
              {Math.min(100, Math.round(tauxResolution * 0.4 + (mttr > 0 && mttr < 2 ? 30 : mttr > 0 ? Math.max(0, 30 - (mttr - 2) * 5) : 15) + (100 - (totalInterv > 0 ? correctifs / totalInterv * 100 : 0)) * 0.3))}/100
            </div>
            <div className="w-full bg-savia-surface-hover rounded-full h-3 mt-4 overflow-hidden max-w-md mx-auto">
              <div className={`h-full rounded-full transition-all duration-1000 ${tauxResolution >= 70 ? 'bg-green-400' : tauxResolution >= 40 ? 'bg-yellow-400' : 'bg-red-400'}`}
                style={{ width: `${Math.min(100, tauxResolution)}%` }} />
            </div>
          </div>

          {/* Summary KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="glass rounded-xl p-4 text-center"><div className="flex justify-center mb-1"><Wrench className="w-5 h-5 text-savia-accent" /></div><div className="text-3xl font-black text-savia-accent">{totalInterv}</div><div className="text-xs text-savia-text-muted mt-1">Interventions totales</div></div>
            <div className="glass rounded-xl p-4 text-center"><div className="flex justify-center mb-1"><Target className="w-5 h-5 text-green-400" /></div><div className="text-3xl font-black text-green-400">{tauxResolution}%</div><div className="text-xs text-savia-text-muted mt-1">Taux résolution</div></div>
            <div className="glass rounded-xl p-4 text-center"><div className="flex justify-center mb-1"><Timer className="w-5 h-5 text-purple-400" /></div><div className="text-3xl font-black text-purple-400">{mttr}h</div><div className="text-xs text-savia-text-muted mt-1">MTTR moyen</div></div>
            <div className="glass rounded-xl p-4 text-center"><div className="flex justify-center mb-1"><Clock className="w-5 h-5 text-yellow-400" /></div><div className="text-3xl font-black text-yellow-400">{totalDureeH}h</div><div className="text-xs text-savia-text-muted mt-1">Durée totale</div></div>
          </div>

          {/* Ratio correctif/préventif */}
          <div className="glass rounded-xl p-5">
            <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-4 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-savia-accent" /> Ratio Correctif / Préventif
            </h3>
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-red-400 font-bold flex items-center gap-1"><XCircle className="w-3.5 h-3.5" /> Corrective: {correctifs}</span>
                  <span className="text-green-400 font-bold flex items-center gap-1"><Shield className="w-3.5 h-3.5" /> Préventive: {preventifs}</span>
                </div>
                <div className="w-full bg-savia-surface-hover rounded-full h-4 overflow-hidden flex">
                  <div className="bg-red-400 h-full transition-all" style={{ width: `${totalInterv > 0 ? (correctifs / totalInterv * 100) : 50}%` }} />
                  <div className="bg-green-400 h-full transition-all" style={{ width: `${totalInterv > 0 ? (preventifs / totalInterv * 100) : 50}%` }} />
                </div>
              </div>
            </div>
          </div>

          {/* Tech performance table */}
          <div className="glass rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-savia-border/50 flex items-center gap-2">
              <Users className="w-4 h-4 text-savia-accent" />
              <span className="font-semibold text-sm">Performance par Technicien</span>
            </div>
            <div className="overflow-x-auto max-h-[310px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10 bg-savia-surface-hover/80 backdrop-blur-sm">
                  <tr className="border-b border-savia-border">
                    {['Technicien', 'Interventions', 'Clôturées', 'Taux résol.', 'MTTR', 'Coût'].map(h => (
                      <th key={h} className="text-left py-2 px-3 text-savia-text-muted">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {techStats.map(t => (
                    <tr key={t.nom} className="border-b border-savia-border/30 hover:bg-savia-surface-hover/50">
                      <td className="py-2.5 px-3 font-bold">{t.nom}</td>
                      <td className="py-2.5 px-3 font-mono">{t.nb}</td>
                      <td className="py-2.5 px-3 font-mono text-green-400">{t.clot}</td>
                      <td className="py-2.5 px-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${t.taux >= 80 ? 'bg-green-500/10 text-green-400' : t.taux >= 50 ? 'bg-yellow-500/10 text-yellow-400' : 'bg-red-500/10 text-red-400'}`}>{t.taux}%</span>
                      </td>
                      <td className="py-2.5 px-3 font-mono">{t.mttr}h</td>
                      <td className="py-2.5 px-3 font-mono">{t.cout.toLocaleString('fr')} TND</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ===== TAB 2: CHARGE FINANCIÈRE ===== */}
      {activeTab === 2 && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="glass rounded-xl p-6 text-center border border-blue-500/20">
              <div className="flex justify-center mb-2"><DollarSign className="w-6 h-6 text-blue-400" /></div>
              <div className="text-sm text-blue-400 font-bold uppercase tracking-wider mb-2">Coût Interventions</div>
              <div className="text-4xl font-black text-blue-400">{coutInterventions.toLocaleString('fr')} TND</div>
              <div className="text-xs text-savia-text-muted mt-2">Charge technique (main d&apos;œuvre)</div>
            </div>
            <div className="glass rounded-xl p-6 text-center border border-purple-500/20">
              <div className="flex justify-center mb-2"><Wrench className="w-6 h-6 text-purple-400" /></div>
              <div className="text-sm text-purple-400 font-bold uppercase tracking-wider mb-2">Coût Pièces</div>
              <div className="text-4xl font-black text-purple-400">{coutPieces.toLocaleString('fr')} TND</div>
              <div className="text-xs text-savia-text-muted mt-2">Pièces de rechange utilisées</div>
            </div>
            <div className="glass rounded-xl p-6 text-center border border-cyan-500/20">
              <div className="flex justify-center mb-2"><TrendingUp className="w-6 h-6 text-cyan-400" /></div>
              <div className="text-sm text-cyan-400 font-bold uppercase tracking-wider mb-2">Coût Total</div>
              <div className="text-4xl font-black text-cyan-400">{(coutInterventions + coutPieces).toLocaleString('fr')} TND</div>
              <div className="text-xs text-savia-text-muted mt-2">Dépenses totales maintenance</div>
            </div>
          </div>

          {/* Cost per technicien */}
          <div className="glass rounded-xl p-5">
            <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-4 flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-savia-accent" /> Coût par Technicien
            </h3>
            <div className="space-y-3">
              {techStats.map(t => {
                const pct = totalCout > 0 ? (t.cout / totalCout * 100) : 0;
                return (
                  <div key={t.nom} className="flex items-center gap-4">
                    <div className="w-40 font-semibold text-sm truncate">{t.nom}</div>
                    <div className="flex-1 bg-savia-surface-hover rounded-full h-3 overflow-hidden">
                      <div className="bg-gradient-to-r from-cyan-500 to-blue-500 h-full rounded-full transition-all" style={{ width: `${Math.min(100, pct)}%` }} />
                    </div>
                    <div className="w-32 text-right font-mono text-sm text-savia-text">{t.cout.toLocaleString('fr')} TND</div>
                    <div className="w-12 text-right text-xs text-savia-text-dim">{pct.toFixed(0)}%</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Cost by intervention type */}
          <div className="glass rounded-xl p-5">
            <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-4 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-savia-accent" /> Répartition par Type
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {['Corrective', 'Préventive', 'Installation'].map(type => {
                const typeData = filtered.filter(i => i.type.toLowerCase().includes(type.toLowerCase().substring(0, 5)));
                const typeCout = typeData.reduce((a, b) => a + (b.cout || b.coutPieces), 0);
                const color = type === 'Corrective' ? 'red' : type === 'Préventive' ? 'green' : 'blue';
                const Icon = type === 'Corrective' ? XCircle : type === 'Préventive' ? Shield : Wrench;
                return (
                  <div key={type} className={`glass rounded-xl p-4 border border-${color}-500/20`}>
                    <div className={`text-sm font-bold text-${color}-400 mb-2 flex items-center gap-2`}><Icon className="w-4 h-4" /> {type}</div>
                    <div className="text-2xl font-black text-savia-text">{typeData.length} <span className="text-sm text-savia-text-muted">interventions</span></div>
                    <div className="text-sm text-savia-text-muted mt-1">Coût: {typeCout.toLocaleString('fr')} TND</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* ===== TAB 3: RAPPORT PDF ===== */}
      {activeTab === 3 && (
        <div className="space-y-6">
          <div className="glass rounded-xl p-5">
            <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-4 flex items-center gap-2">
              <FileText className="w-4 h-4 text-savia-accent" /> Rapport PDF des Interventions
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
              <div>
                <label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><CalendarDays className="w-3.5 h-3.5" /> Du</label>
                <input type="date" className={INPUT_CLS} value={pdfDateFrom} onChange={e => setPdfDateFrom(e.target.value)} />
              </div>
              <div>
                <label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><CalendarDays className="w-3.5 h-3.5" /> Au</label>
                <input type="date" className={INPUT_CLS} value={pdfDateTo} onChange={e => setPdfDateTo(e.target.value)} />
              </div>
              <button onClick={handleGeneratePdf} disabled={isPdfGenerating} className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer">
                {isPdfGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />} Générer PDF
              </button>
            </div>
          </div>

          {/* Filtered interventions preview */}
          <div className="glass rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-savia-border/50 flex items-center gap-2">
              <ClipboardList className="w-4 h-4 text-savia-accent" />
              <span className="font-semibold text-sm">Aperçu des données</span>
            </div>
            {(() => {
              const pdfFiltered = data.filter(i => {
                const d = new Date(i.date);
                return d >= new Date(pdfDateFrom) && d <= new Date(pdfDateTo + 'T23:59:59');
              });
              return (
                <div className="p-4">
                  <div className="flex gap-4 mb-4">
                    <div className="glass rounded-lg p-3 text-center flex-1"><div className="flex justify-center mb-1"><Wrench className="w-4 h-4 text-savia-accent" /></div><div className="text-xl font-bold text-savia-accent">{pdfFiltered.length}</div><div className="text-xs text-savia-text-muted">Interventions</div></div>
                    <div className="glass rounded-lg p-3 text-center flex-1"><div className="flex justify-center mb-1"><CheckCircle className="w-4 h-4 text-green-400" /></div><div className="text-xl font-bold text-green-400">{pdfFiltered.filter(i => i.statut.toLowerCase().includes('tur')).length}</div><div className="text-xs text-savia-text-muted">Clôturées</div></div>
                    <div className="glass rounded-lg p-3 text-center flex-1"><div className="flex justify-center mb-1"><DollarSign className="w-4 h-4 text-red-400" /></div><div className="text-xl font-bold text-red-400">{pdfFiltered.reduce((a, b) => a + (b.cout || b.coutPieces), 0).toLocaleString('fr')} TND</div><div className="text-xs text-savia-text-muted">Coût total</div></div>
                  </div>
                  <div className="overflow-x-auto max-h-[250px] overflow-y-auto">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-savia-surface-hover/80 backdrop-blur-sm">
                        <tr className="border-b border-savia-border">
                          {['Date', 'Machine', 'Technicien', 'Type', 'Statut', 'Durée', 'Coût'].map(h => (
                            <th key={h} className="text-left py-2 px-2 text-savia-text-muted">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {pdfFiltered.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()).map(i => (
                          <tr key={i.id} className="border-b border-savia-border/30">
                            <td className="py-1.5 px-2">{i.date.substring(0, 10)}</td>
                            <td className="py-1.5 px-2 font-semibold">{i.machine}</td>
                            <td className="py-1.5 px-2">{i.technicien}</td>
                            <td className="py-1.5 px-2">{i.type}</td>
                            <td className="py-1.5 px-2">{i.statut}</td>
                            <td className="py-1.5 px-2 font-mono">{i.duree}h</td>
                            <td className="py-1.5 px-2 font-mono">{(i.cout || i.coutPieces).toLocaleString('fr')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* ===== TAB 4: ANALYSE IA COMPLÈTE ===== */}
      {activeTab === 4 && (
        <div className="space-y-6">
          {/* Launch button */}
          <div className="glass rounded-xl p-6 text-center">
            <Brain className="w-10 h-10 text-purple-400 mx-auto mb-3" />
            <h3 className="text-lg font-bold text-savia-text mb-2">Analyse IA Complète — SAV</h3>
            <p className="text-sm text-savia-text-muted mb-4">Gemini analysera l&apos;ensemble de vos données SAV : performance équipe, coûts, tendances, et recommandations</p>
            <button onClick={handleAiAnalyze} disabled={isAnalyzing} className="flex items-center justify-center gap-2 px-8 py-3 rounded-lg font-bold text-white bg-gradient-to-r from-purple-600 to-pink-500 hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer shadow-lg shadow-purple-500/20 mx-auto">
              {isAnalyzing ? <><Loader2 className="w-5 h-5 animate-spin" /> Analyse en cours...</> : <><Sparkles className="w-5 h-5" /> Lancer l&apos;analyse complète</>}
            </button>
          </div>

          {/* Loading state */}
          {isAnalyzing && (
            <div className="glass rounded-xl p-12 text-center">
              <div className="relative mx-auto w-16 h-16 mb-4"><Loader2 className="w-16 h-16 animate-spin text-purple-400" /><Sparkles className="w-6 h-6 text-pink-400 absolute -top-1 -right-1 animate-pulse" /></div>
              <p className="text-savia-text font-semibold">Gemini analyse vos données SAV...</p>
              <p className="text-xs text-savia-text-dim mt-1">Cela peut prendre jusqu&apos;à 30 secondes</p>
            </div>
          )}

          {/* Error */}
          {aiError && (
            <div className="glass rounded-xl p-6 text-center border border-red-500/20">
              <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-3" />
              <p className="text-red-400 font-semibold">{aiError}</p>
            </div>
          )}

          {/* Results */}
          {aiResult && (
            <div className="space-y-5">
              {/* Score + Résumé */}
              <div className="glass rounded-xl p-6 border border-purple-500/20">
                <div className="flex items-start gap-4">
                  {aiResult.score_global && (
                    <div className="flex-shrink-0 w-20 h-20 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center">
                      <span className="text-2xl font-black text-white">{aiResult.score_global}</span>
                    </div>
                  )}
                  <div className="flex-1">
                    <h3 className="text-sm font-bold text-purple-400 uppercase tracking-wider mb-2 flex items-center gap-2"><BarChart3 className="w-4 h-4" /> Résumé Exécutif</h3>
                    <p className="text-sm text-savia-text leading-relaxed">{aiResult.analyse || 'N/A'}</p>
                  </div>
                </div>
              </div>

              {/* Points Forts / Faibles */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="glass rounded-xl p-5 border border-green-500/20">
                  <h3 className="text-sm font-bold text-green-400 uppercase tracking-wider mb-3 flex items-center gap-2"><ThumbsUp className="w-4 h-4" /> Points Forts</h3>
                  <ul className="space-y-2">
                    {(aiResult.points_forts || []).map((pt: string, i: number) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-savia-text"><CheckCircle className="w-3.5 h-3.5 text-green-400 mt-0.5 flex-shrink-0" /> {pt}</li>
                    ))}
                  </ul>
                </div>
                <div className="glass rounded-xl p-5 border border-red-500/20">
                  <h3 className="text-sm font-bold text-red-400 uppercase tracking-wider mb-3 flex items-center gap-2"><ThumbsDown className="w-4 h-4" /> Points Faibles</h3>
                  <ul className="space-y-2">
                    {(aiResult.points_faibles || []).map((pt: string, i: number) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-savia-text"><AlertTriangle className="w-3.5 h-3.5 text-red-400 mt-0.5 flex-shrink-0" /> {pt}</li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Performance Équipe */}
              {aiResult.performance_equipe && aiResult.performance_equipe.length > 0 && (
                <div className="glass rounded-xl p-5 border border-blue-500/20">
                  <h3 className="text-sm font-bold text-blue-400 uppercase tracking-wider mb-3 flex items-center gap-2"><Users className="w-4 h-4" /> Évaluation de l&apos;Équipe</h3>
                  <div className="space-y-3">
                    {aiResult.performance_equipe.map((pe: any, i: number) => (
                      <div key={i} className="flex items-start gap-3 bg-savia-surface-hover/30 rounded-lg p-3">
                        <div className={`px-2.5 py-1 rounded-full text-xs font-bold flex-shrink-0 ${
                          pe.evaluation?.toLowerCase().includes('excellent') ? 'bg-green-500/15 text-green-400' :
                          pe.evaluation?.toLowerCase().includes('bon') ? 'bg-blue-500/15 text-blue-400' :
                          'bg-yellow-500/15 text-yellow-400'
                        }`}>{pe.evaluation}</div>
                        <div>
                          <div className="font-bold text-sm text-savia-text">{pe.technicien}</div>
                          <p className="text-xs text-savia-text-muted mt-0.5">{pe.commentaire}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Analyse Coûts */}
              {aiResult.analyse_couts && (
                <div className="glass rounded-xl p-5 border border-yellow-500/20">
                  <h3 className="text-sm font-bold text-yellow-400 uppercase tracking-wider mb-3 flex items-center gap-2"><DollarSign className="w-4 h-4" /> Analyse des Coûts</h3>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                        aiResult.analyse_couts.verdict?.toLowerCase().includes('maîtris') ? 'bg-green-500/15 text-green-400' :
                        aiResult.analyse_couts.verdict?.toLowerCase().includes('critiq') ? 'bg-red-500/15 text-red-400' :
                        'bg-yellow-500/15 text-yellow-400'
                      }`}>{aiResult.analyse_couts.verdict}</span>
                    </div>
                    <p className="text-sm text-savia-text">{aiResult.analyse_couts.detail}</p>
                    {aiResult.analyse_couts.economie_possible && (
                      <p className="text-sm text-green-400 font-semibold flex items-center gap-1"><TrendingUp className="w-3.5 h-3.5" /> {aiResult.analyse_couts.economie_possible}</p>
                    )}
                  </div>
                </div>
              )}

              {/* Recommandations */}
              <div className="glass rounded-xl p-5 border border-cyan-500/20">
                <h3 className="text-sm font-bold text-cyan-400 uppercase tracking-wider mb-3 flex items-center gap-2"><Lightbulb className="w-4 h-4" /> Recommandations</h3>
                <div className="space-y-3">
                  {(aiResult.recommandations || []).map((rec: any, i: number) => (
                    <div key={i} className="bg-savia-surface-hover/50 rounded-lg p-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-bold text-sm text-savia-text">{rec.titre}</span>
                        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${rec.impact === 'HAUT' ? 'bg-red-500/20 text-red-400' : rec.impact === 'MOYEN' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'}`}>{rec.impact}</span>
                      </div>
                      <p className="text-xs text-savia-text-muted">{rec.description}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Tendances + Priorités */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {aiResult.tendances && aiResult.tendances.length > 0 && (
                  <div className="glass rounded-xl p-5 border border-indigo-500/20">
                    <h3 className="text-sm font-bold text-indigo-400 uppercase tracking-wider mb-3 flex items-center gap-2"><TrendingUp className="w-4 h-4" /> Tendances Observées</h3>
                    <ul className="space-y-2">
                      {aiResult.tendances.map((t: string, i: number) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-savia-text"><Activity className="w-3.5 h-3.5 text-indigo-400 mt-0.5 flex-shrink-0" /> {t}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {aiResult.priorites_immediates && aiResult.priorites_immediates.length > 0 && (
                  <div className="glass rounded-xl p-5 border border-orange-500/20">
                    <h3 className="text-sm font-bold text-orange-400 uppercase tracking-wider mb-3 flex items-center gap-2"><Zap className="w-4 h-4" /> Priorités Immédiates</h3>
                    <ul className="space-y-2">
                      {aiResult.priorites_immediates.map((p: string, i: number) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-savia-text"><AlertTriangle className="w-3.5 h-3.5 text-orange-400 mt-0.5 flex-shrink-0" /> {p}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            {/* ---- Télécharger PDF ---- */}
            <div className="flex justify-end pt-4 mb-1">
              <button
                onClick={handleSavAiPdf}
                disabled={isPdfGenerating}
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-purple-600 to-pink-500 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-purple-500/20 disabled:opacity-50 text-sm"
              >
                <Download className="w-4 h-4" />
                {isPdfGenerating ? "G\u00e9n\u00e9ration..." : "T\u00e9l\u00e9charger PDF"}
              </button>
            </div>
          </div>
          )}
        </div>
      )}

      {/* Add Intervention Modal */}
      <Modal isOpen={showAddModal} onClose={() => setShowAddModal(false)} title="Nouvelle Intervention" size="lg">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> Date</label><input type="date" className={INPUT_CLS} value={form.date} onChange={e => setForm({...form, date: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Building2 className="w-3.5 h-3.5" /> Client *</label>
            <select className={INPUT_CLS} value={form.client} onChange={e => setForm({...form, client: e.target.value, machine: ''})}>
              <option value="">— Sélectionner un client —</option>
              {clientsData.map((c: any) => <option key={c.id || c.nom} value={c.nom}>{c.nom}</option>)}
            </select>
          </div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Server className="w-3.5 h-3.5" /> Équipement *</label>
            <select className={INPUT_CLS} value={form.machine} onChange={e => setForm({...form, machine: e.target.value})} disabled={!form.client}>
              <option value="">{form.client ? '— Sélectionner un équipement —' : '← Choisir un client d\'abord'}</option>
              {equipementsData
                .filter((eq: any) => (eq.Client || eq.client || '') === form.client)
                .map((eq: any) => <option key={eq.id || eq.Nom || eq.nom} value={eq.Nom || eq.nom}>{eq.Nom || eq.nom}</option>)}
            </select>
          </div>
          <div className="md:col-span-2"><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Users className="w-3.5 h-3.5" /> Techniciens</label>
            {/* Chips */}
            {form.technicien && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {form.technicien.split(', ').filter(Boolean).map(t => (
                  <span key={t} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-savia-accent/15 text-savia-accent border border-savia-accent/30">
                    {t}
                    <button type="button" onClick={() => {
                      const updated = form.technicien.split(', ').filter(x => x !== t).join(', ');
                      setForm({...form, technicien: updated});
                    }} className="hover:text-red-400 cursor-pointer ml-0.5"><X className="w-3 h-3" /></button>
                  </span>
                ))}
              </div>
            )}
            {/* Dropdown */}
            <div className="relative">
              <button type="button" onClick={() => setSavTechDropdownOpen(!savTechDropdownOpen)}
                className={INPUT_CLS + ' flex items-center justify-between cursor-pointer text-left'}>
                <span className={form.technicien ? 'text-savia-text' : 'text-savia-text-dim'}>
                  {form.technicien ? `${form.technicien.split(', ').length} technicien(s)` : '-- Sélectionnez --'}
                </span>
                <ChevronDown className={`w-4 h-4 transition-transform ${savTechDropdownOpen ? 'rotate-180' : ''}`} />
              </button>
              {savTechDropdownOpen && (
                <div className="absolute z-30 mt-1 w-full bg-savia-surface border border-savia-border rounded-lg shadow-xl max-h-48 overflow-y-auto">
                  {techniciens.map(t => {
                    const fullName = `${t.prenom} ${t.nom}`;
                    const selected = form.technicien.split(', ').filter(Boolean).includes(fullName);
                    return (
                      <button key={t.nom} type="button" onClick={() => {
                        const current = form.technicien.split(', ').filter(Boolean);
                        const updated = selected ? current.filter(x => x !== fullName) : [...current, fullName];
                        setForm({...form, technicien: updated.join(', ')});
                      }}
                        className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:bg-savia-surface-hover transition-colors cursor-pointer ${
                          selected ? 'text-savia-accent font-semibold' : 'text-savia-text'
                        }`}>
                        <div className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
                          selected ? 'bg-savia-accent border-savia-accent' : 'border-savia-border'
                        }`}>
                          {selected && <Check className="w-3 h-3 text-white" />}
                        </div>
                        {fullName}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Wrench className="w-3.5 h-3.5" /> Type</label>
            {customTypeMode ? (
              <div className="flex gap-2">
                <input className={INPUT_CLS} placeholder="Saisir le type..." value={customTypeValue} onChange={e => setCustomTypeValue(e.target.value)} autoFocus />
                <button type="button" onClick={async () => {
                  const val = customTypeValue.trim();
                  if (val) {
                    try {
                      await typesIntervention.create(val);
                      setCustomInterventionTypes(prev => [...prev, val]);
                      setForm({...form, type_intervention: val});
                    } catch { /* ignore duplicate */ }
                  }
                  setCustomTypeMode(false);
                  setCustomTypeValue('');
                }} className="px-3 py-1 rounded-lg bg-savia-accent text-white font-bold text-sm hover:opacity-90 cursor-pointer"><Check className="w-4 h-4" /></button>
                <button type="button" onClick={() => { setCustomTypeMode(false); setCustomTypeValue(''); }} className="px-3 py-1 rounded-lg bg-savia-surface-hover text-savia-text-muted text-sm hover:opacity-90 cursor-pointer"><X className="w-4 h-4" /></button>
              </div>
            ) : (
              <select className={INPUT_CLS} value={form.type_intervention} onChange={e => {
                if (e.target.value === '__autre__') {
                  setCustomTypeMode(true);
                } else {
                  setForm({...form, type_intervention: e.target.value});
                }
              }}>
                {allInterventionTypes.map(t => <option key={t} value={t}>{t}</option>)}
                <option value="__autre__">✏️ Autre (saisie manuelle)</option>
              </select>
            )}
          </div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Zap className="w-3.5 h-3.5" /> Code erreur</label><input className={INPUT_CLS} placeholder="Ex: E147" value={form.code_erreur} onChange={e => setForm({...form, code_erreur: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Type erreur</label>
            <select className={INPUT_CLS} value={form.type_erreur} onChange={e => setForm({...form, type_erreur: e.target.value})}>
              {TYPES_ERREUR.map(t => <option key={t}>{t}</option>)}
            </select></div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Activity className="w-3.5 h-3.5" /> Priorité</label>
            <select className={INPUT_CLS} value={form.priorite} onChange={e => setForm({...form, priorite: e.target.value})}>
              {PRIORITES.map(p => <option key={p}>{p}</option>)}
            </select></div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Timer className="w-3.5 h-3.5" /> Durée (min)</label><input type="number" className={INPUT_CLS} value={form.duree_minutes} onChange={e => setForm({...form, duree_minutes: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><DollarSign className="w-3.5 h-3.5" /> Coût pièces (TND)</label><input type="number" className={INPUT_CLS} value={form.cout_pieces} onChange={e => setForm({...form, cout_pieces: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Wrench className="w-3.5 h-3.5" /> Pièces utilisées</label><input className={INPUT_CLS} placeholder="Ex: Tube RX, Câble" value={form.pieces_utilisees} onChange={e => setForm({...form, pieces_utilisees: e.target.value})} /></div>
          <div className="md:col-span-2"><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><ClipboardList className="w-3.5 h-3.5" /> Description</label><textarea className={INPUT_CLS + " h-20 resize-none"} placeholder="Décrivez le problème..." value={form.probleme} onChange={e => setForm({...form, probleme: e.target.value})} /></div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-savia-border/30">
          <button onClick={() => setShowAddModal(false)} className="px-4 py-2 rounded-lg text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover transition-colors cursor-pointer">Annuler</button>
          <button onClick={handleSave} disabled={isSaving || !form.machine.trim()} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Sauvegarder
          </button>
        </div>
      </Modal>

      {/* Status Change Modal */}
      <Modal isOpen={showStatusModal} onClose={() => setShowStatusModal(false)} title={`Modifier — ${selectedIntervention?.machine || ''}`} size="lg">
        <div className="space-y-4">
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Activity className="w-3.5 h-3.5" /> Statut</label>
            <select className={INPUT_CLS} value={statusForm.statut} onChange={e => {
              setStatusForm({...statusForm, statut: e.target.value});
              setRupturePieces([]); // reset pièces sélectionnées si on change de statut
            }}>
              <option>En cours</option>
              <option>En attente de pièce</option>
              <option>Clôturée</option>
              <option>Planifiée</option>
            </select></div>
          {/* Sélecteur pièces en rupture si statut = En attente de pièce */}
          {statusForm.statut === 'En attente de pièce' && (() => {
            const piecesRupture = allPieces.filter((p: any) => Number(p.stock_actuel ?? 0) <= 0);
            return (
              <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-3">
                <label className="block text-sm font-semibold text-orange-400 mb-2 flex items-center gap-1.5">
                  <span>⚠️</span> Pièces en rupture de stock requises
                  <span className="text-xs font-normal text-savia-text-muted ml-1">(sélectionnez celles qu'il vous faut)</span>
                </label>
                {piecesRupture.length === 0 ? (
                  <p className="text-xs text-savia-text-muted italic">Aucune pièce en rupture de stock actuellement.</p>
                ) : (
                  <div className="space-y-1.5 max-h-40 overflow-y-auto">
                    {piecesRupture.map((p: any) => {
                      const isSelected = rupturePieces.some((r: any) => r.reference === p.reference);
                      return (
                        <label key={p.reference} className={`flex items-center gap-2 cursor-pointer p-2 rounded-lg transition-colors ${
                          isSelected ? 'bg-orange-500/20 border border-orange-500/50' : 'hover:bg-savia-surface-hover'
                        }`}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={e => {
                              if (e.target.checked) {
                                setRupturePieces(prev => [...prev, p]);
                              } else {
                                setRupturePieces(prev => prev.filter((r: any) => r.reference !== p.reference));
                              }
                            }}
                            className="accent-orange-500"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium text-savia-text truncate">{p.designation || p.nom}</div>
                            <div className="text-xs text-savia-text-muted">{p.reference} · Stock: <span className="text-red-400 font-bold">{p.stock_actuel ?? 0}</span></div>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                )}
                {rupturePieces.length > 0 && (
                  <div className="mt-2 text-xs text-orange-300 font-medium">
                    ✅ {rupturePieces.length} pièce(s) sélectionnée(s) → notification envoyée au gestionnaire
                  </div>
                )}
              </div>
            );
          })()}
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" /> Problème identifié</label><textarea className={INPUT_CLS + " h-16 resize-none"} value={statusForm.probleme} onChange={e => setStatusForm({...statusForm, probleme: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Search className="w-3.5 h-3.5" /> Cause</label><textarea className={INPUT_CLS + " h-16 resize-none"} value={statusForm.cause} onChange={e => setStatusForm({...statusForm, cause: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><CheckCircle className="w-3.5 h-3.5" /> Solution apportée</label><textarea className={INPUT_CLS + " h-16 resize-none"} value={statusForm.solution} onChange={e => setStatusForm({...statusForm, solution: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Timer className="w-3.5 h-3.5" /> Durée (min)</label><input type="number" className={INPUT_CLS} value={statusForm.duree_minutes} onChange={e => setStatusForm({...statusForm, duree_minutes: e.target.value})} /></div>
          {statusForm.statut.toLowerCase().includes('tur') && (
            <div>
              <label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1">
                <Camera className="w-3.5 h-3.5" /> Photo fiche signée <span className="text-xs opacity-60">(optionnel)</span>
              </label>
              <div className="border-2 border-dashed border-savia-border/50 rounded-lg p-4 text-center cursor-pointer hover:border-savia-accent/50 transition-colors"
                onClick={() => document.getElementById('fiche-upload-modal')?.click()}>
                {ficheFile ? (
                  <div className="flex items-center justify-center gap-2 text-green-400">
                    <CheckCircle className="w-4 h-4" />
                    <span className="text-sm font-medium">{ficheFile.name}</span>
                    <button onClick={e => { e.stopPropagation(); setFicheFile(null); }} className="ml-2 text-red-400 hover:text-red-300">
                      <XCircle className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <div className="text-savia-text-muted">
                    <Upload className="w-6 h-6 mx-auto mb-1 opacity-50" />
                    <p className="text-xs">Cliquez pour sélectionner une photo (JPG, PNG, PDF)</p>
                  </div>
                )}
              </div>
              <input id="fiche-upload-modal" type="file" accept="image/*,.pdf" className="hidden"
                onChange={e => setFicheFile(e.target.files?.[0] || null)} />
            </div>
          )}
          {/* Upload fiche signée si clôture */}
          {statusForm.statut.toLowerCase().includes('tur') && (
            <div>
              <label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1">
                <Camera className="w-3.5 h-3.5" /> Photo fiche signée <span className="text-xs text-savia-text-muted/60">(optionnel)</span>
              </label>
              <div
                className="border-2 border-dashed border-savia-border/50 rounded-lg p-4 text-center cursor-pointer hover:border-savia-accent/50 transition-colors"
                onClick={() => document.getElementById('fiche-upload')?.click()}
              >
                {ficheFile ? (
                  <div className="flex items-center justify-center gap-2 text-green-400">
                    <CheckCircle className="w-4 h-4" />
                    <span className="text-sm font-medium">{ficheFile.name}</span>
                    <button onClick={e => { e.stopPropagation(); setFicheFile(null); }} className="ml-2 text-red-400 hover:text-red-300">
                      <XCircle className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <div className="text-savia-text-muted">
                    <Upload className="w-6 h-6 mx-auto mb-1 opacity-50" />
                    <p className="text-xs">Cliquez pour sélectionner une photo (JPG, PNG, PDF)</p>
                  </div>
                )}
              </div>
              <input id="fiche-upload" type="file" accept="image/*,.pdf" className="hidden"
                onChange={e => setFicheFile(e.target.files?.[0] || null)} />
            </div>
          )}
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-savia-border/30">
          <button onClick={() => setShowStatusModal(false)} className="px-4 py-2 rounded-lg text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover transition-colors cursor-pointer">Annuler</button>
          <button onClick={handleStatusChange} disabled={isSaving} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Enregistrer
          </button>
        </div>
      </Modal>
      {/* === ONGLET 5 : FICHES SIGNÉES === */}
      {activeTab === 5 && (
        <FichesSigneesTab fiches={fiches} setFiches={setFiches} />
      )}

      {/* === ONGLET 6 : SUIVI FACTURATION === */}
      {activeTab === 6 && (
        <div className="space-y-4">
          {/* KPIs facturation */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: 'Total clôturées', value: facturationData.length, icon: <ClipboardList className="w-5 h-5" />, color: 'text-savia-accent', filter: 'all' as const },
              { label: 'Non facturées', value: facturationData.filter((f: any) => !f.facture_envoyee && !f.en_retard).length, icon: <CircleDot className="w-5 h-5" />, color: 'text-yellow-400', filter: 'pending' as const },
              { label: 'En retard', value: facturationData.filter((f: any) => f.en_retard).length, icon: <AlertOctagon className="w-5 h-5" />, color: 'text-red-400', filter: 'overdue' as const },
              { label: 'Facturées', value: facturationData.filter((f: any) => f.facture_envoyee).length, icon: <CheckCircle2 className="w-5 h-5" />, color: 'text-green-400', filter: 'done' as const },
            ].map(k => (
              <button key={k.label} onClick={() => setFactFilter(k.filter)}
                className={`glass rounded-xl p-4 text-center cursor-pointer transition-all hover:scale-[1.02] ${
                  factFilter === k.filter ? 'ring-2 ring-savia-accent shadow-lg' : ''
                }`}>
                <div className={`flex justify-center mb-1 ${k.color}`}>{k.icon}</div>
                <div className={`text-3xl font-black ${k.color}`}>{k.value}</div>
                <div className="text-xs text-savia-text-muted mt-1">{k.label}</div>
              </button>
            ))}
          </div>

          {/* Table facturation */}
          <div className="glass rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-savia-border/50 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Receipt className="w-4 h-4 text-savia-accent" />
                <span className="font-semibold text-sm">{filteredFacturation.length} intervention{filteredFacturation.length > 1 ? 's' : ''}</span>
              </div>
              {factFilter !== 'all' && (
                <button onClick={() => setFactFilter('all')} className="text-xs text-savia-accent hover:underline cursor-pointer">Voir tout</button>
              )}
            </div>
            <div className="overflow-x-auto max-h-[450px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10 bg-savia-surface-hover/80 backdrop-blur-sm">
                  <tr className="border-b border-savia-border">
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs">ID</th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs">Machine</th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs">Client</th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs">Technicien</th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs">Date clôture</th>
                    <th className="text-center py-2.5 px-3 text-savia-text-muted text-xs">Compteur</th>
                    <th className="text-center py-2.5 px-3 text-savia-text-muted text-xs">Deadline</th>
                    <th className="text-left py-2.5 px-3 text-savia-text-muted text-xs">Pièces</th>
                    <th className="text-center py-2.5 px-3 text-savia-text-muted text-xs">Statut</th>
                    <th className="py-2.5 px-3 text-center text-savia-text-muted text-xs">Détails</th>
                    <th className="py-2.5 px-3"></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredFacturation.map((f: any) => {
                    const progress = Math.min(100, Math.max(0, ((10 - f.jours_restants) / 10) * 100));
                    return (
                      <tr key={f.id} className={`border-b border-savia-border/30 hover:bg-savia-surface-hover/50 transition-colors ${
                        f.en_retard ? 'bg-red-500/5' : f.facture_envoyee ? 'bg-green-500/5' : ''
                      }`}>
                        <td className="py-2.5 px-3 font-mono text-xs text-savia-accent">#{f.id}</td>
                        <td className="py-2.5 px-3 font-semibold text-sm">{f.machine}</td>
                        <td className="py-2.5 px-3 text-sm text-savia-text-muted">{f.client || '—'}</td>
                        <td className="py-2.5 px-3 text-sm">{f.technicien}</td>
                        <td className="py-2.5 px-3 text-xs">{f.date_cloture}</td>
                        <td className="py-2.5 px-3">
                          <div className="flex flex-col items-center gap-1">
                            <span className={`text-xs font-bold ${
                              f.facture_envoyee ? 'text-green-400' :
                              f.jours_restants <= 0 ? 'text-red-400' :
                              f.jours_restants <= 2 ? 'text-orange-400' : 'text-savia-text'
                            }`}>
                              {f.facture_envoyee ? '✓' : `J+${f.jours_depuis_cloture}`}
                            </span>
                            {!f.facture_envoyee && (
                              <div className="w-16 bg-savia-surface-hover rounded-full h-1.5 overflow-hidden">
                                <div className={`h-full rounded-full transition-all ${
                                  f.jours_restants <= 0 ? 'bg-red-400' :
                                  f.jours_restants <= 2 ? 'bg-orange-400' :
                                  f.jours_restants <= 5 ? 'bg-yellow-400' : 'bg-green-400'
                                }`} style={{ width: `${progress}%` }} />
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <span className={`text-xs font-semibold ${
                            f.facture_envoyee ? 'text-green-400' :
                            f.jours_restants <= 0 ? 'text-red-400 animate-pulse' :
                            f.jours_restants <= 2 ? 'text-orange-400' : 'text-savia-text-muted'
                          }`}>
                            {f.facture_envoyee ? 'Facturée' :
                             f.jours_restants <= 0 ? `${Math.abs(f.jours_restants)}j de retard` :
                             `${f.jours_restants}j restants`}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-xs text-savia-text-muted max-w-[150px] truncate">{f.pieces_utilisees || '—'}</td>
                        <td className="py-2.5 px-3 text-center">
                          {f.facture_envoyee ? (
                            <span className="px-2 py-1 rounded-full text-xs font-bold bg-green-500/15 text-green-400">✓ Facturée</span>
                          ) : f.en_retard ? (
                            <span className="px-2 py-1 rounded-full text-xs font-bold bg-red-500/15 text-red-400 animate-pulse">⚠ Retard</span>
                          ) : (
                            <span className="px-2 py-1 rounded-full text-xs font-bold bg-yellow-500/15 text-yellow-400">En attente</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <button onClick={() => setFactDetailItem(f)}
                            className="p-1.5 rounded-lg text-savia-text-muted hover:text-savia-accent hover:bg-savia-accent/10 cursor-pointer transition-colors"
                            title="Voir les détails"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                        </td>
                        <td className="py-2.5 px-3">
                          {!f.facture_envoyee && (
                            <button onClick={() => handleMarkFactured(f.id)}
                              className="px-3 py-1.5 rounded-lg text-xs font-bold bg-green-500/10 text-green-400 hover:bg-green-500/20 cursor-pointer transition-colors whitespace-nowrap"
                            >
                              ✓ Facturer
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {filteredFacturation.length === 0 && (
                    <tr><td colSpan={10} className="text-center py-8 text-savia-text-dim">
                      <Receipt className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      Aucune intervention dans cette catégorie.
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Modal détail intervention */}
          {factDetailItem && (
            <Modal isOpen={!!factDetailItem} onClose={() => setFactDetailItem(null)} title={`Intervention #${factDetailItem?.id}`} size="lg">
              <div className="space-y-4 max-h-[75vh] overflow-y-auto">
                <div className="flex items-center justify-between border-b border-savia-border pb-3">
                  <h2 className="text-lg font-black gradient-text flex items-center gap-2">
                    <ClipboardList className="w-5 h-5" /> Intervention #{factDetailItem.id}
                  </h2>
                  <span className={`px-2 py-1 rounded-full text-xs font-bold ${
                    factDetailItem.facture_envoyee ? 'bg-green-500/15 text-green-400' :
                    factDetailItem.en_retard ? 'bg-red-500/15 text-red-400' :
                    'bg-yellow-500/15 text-yellow-400'
                  }`}>
                    {factDetailItem.facture_envoyee ? 'Facturée' : factDetailItem.en_retard ? 'En retard' : 'En attente'}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {[
                    { icon: <Wrench className="w-3.5 h-3.5" />, label: 'Machine', value: factDetailItem.machine },
                    { icon: <Users className="w-3.5 h-3.5" />, label: 'Technicien', value: factDetailItem.technicien },
                    { icon: <Building2 className="w-3.5 h-3.5" />, label: 'Client', value: factDetailItem.client || '—' },
                    { icon: <Briefcase className="w-3.5 h-3.5" />, label: 'Type', value: factDetailItem.type_intervention || '—' },
                    { icon: <Calendar className="w-3.5 h-3.5" />, label: 'Date intervention', value: factDetailItem.date_intervention || '—' },
                    { icon: <Calendar className="w-3.5 h-3.5" />, label: 'Date clôture', value: factDetailItem.date_cloture },
                    { icon: <Timer className="w-3.5 h-3.5" />, label: 'Durée (h)', value: factDetailItem.duree_minutes ? `${+(factDetailItem.duree_minutes / 60).toFixed(2)}h` : '—' },
                    { icon: <Clock className="w-3.5 h-3.5" />, label: 'Déplacement (h)', value: factDetailItem.deplacement ? `${factDetailItem.deplacement}h` : '—' },
                    { icon: <Gauge className="w-3.5 h-3.5" />, label: 'Priorité', value: factDetailItem.priorite || '—' },
                  ].map((item, i) => (
                    <div key={i} className="bg-savia-bg/50 rounded-lg p-2.5 border border-savia-border/50">
                      <div className="flex items-center gap-1.5 text-savia-text-muted text-xs mb-0.5">{item.icon} {item.label}</div>
                      <div className="text-sm font-semibold text-savia-text">{item.value}</div>
                    </div>
                  ))}
                </div>

                {(factDetailItem.description || factDetailItem.probleme) && (
                  <div className="space-y-2">
                    {factDetailItem.description && (
                      <div className="bg-savia-bg/50 rounded-lg p-3 border border-savia-border/50">
                        <div className="text-xs text-savia-text-muted mb-1 flex items-center gap-1.5"><FileText className="w-3.5 h-3.5" /> Description</div>
                        <p className="text-sm text-savia-text">{factDetailItem.description}</p>
                      </div>
                    )}
                    {factDetailItem.probleme && (
                      <div className="bg-savia-bg/50 rounded-lg p-3 border border-savia-border/50">
                        <div className="text-xs text-savia-text-muted mb-1 flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5 text-orange-400" /> Problème</div>
                        <p className="text-sm text-savia-text">{factDetailItem.probleme}</p>
                      </div>
                    )}
                  </div>
                )}

                {(factDetailItem.cause || factDetailItem.solution) && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {factDetailItem.cause && (
                      <div className="bg-orange-500/5 rounded-lg p-3 border border-orange-500/20">
                        <div className="text-xs text-orange-400 mb-1 flex items-center gap-1.5"><Target className="w-3.5 h-3.5" /> Cause</div>
                        <p className="text-sm text-savia-text">{factDetailItem.cause}</p>
                      </div>
                    )}
                    {factDetailItem.solution && (
                      <div className="bg-green-500/5 rounded-lg p-3 border border-green-500/20">
                        <div className="text-xs text-green-400 mb-1 flex items-center gap-1.5"><CheckCircle className="w-3.5 h-3.5" /> Solution</div>
                        <p className="text-sm text-savia-text">{factDetailItem.solution}</p>
                      </div>
                    )}
                  </div>
                )}

                {factDetailItem.pieces_utilisees && (
                  <div className="bg-blue-500/5 rounded-lg p-3 border border-blue-500/20">
                    <div className="text-xs text-blue-400 mb-1 flex items-center gap-1.5"><Server className="w-3.5 h-3.5" /> Pièces de rechange</div>
                    <p className="text-sm text-savia-text">{factDetailItem.pieces_utilisees}</p>
                  </div>
                )}



                {factDetailItem.code_erreur && (
                  <div className="bg-savia-bg/50 rounded-lg p-2.5 border border-savia-border/50">
                    <span className="text-xs text-savia-text-muted">Code erreur :</span>{' '}
                    <span className="font-mono text-sm text-savia-accent">{factDetailItem.code_erreur}</span>
                    {factDetailItem.type_erreur && <span className="text-xs text-savia-text-dim ml-2">({factDetailItem.type_erreur})</span>}
                  </div>
                )}

                <div className="flex justify-end gap-2 pt-2">
                  <button onClick={() => handleDownloadFicheIntervention(factDetailItem)}
                    className="px-4 py-2 rounded-lg text-sm font-bold bg-teal-500/10 text-teal-400 hover:bg-teal-500/20 cursor-pointer transition-colors"
                  >
                    <Download className="w-4 h-4 inline mr-1" /> Télécharger PDF
                  </button>
                  {!factDetailItem.facture_envoyee && (
                    <button onClick={() => { handleMarkFactured(factDetailItem.id); setFactDetailItem(null); }}
                      className="px-4 py-2 rounded-lg text-sm font-bold bg-green-500/10 text-green-400 hover:bg-green-500/20 cursor-pointer transition-colors"
                    >
                      <Check className="w-4 h-4 inline mr-1" /> Marquer facturée
                    </button>
                  )}
                  <button onClick={() => setFactDetailItem(null)}
                    className="px-4 py-2 rounded-lg text-sm font-bold bg-savia-surface-hover text-savia-text hover:bg-savia-border cursor-pointer transition-colors"
                  >
                    Fermer
                  </button>
                </div>
              </div>
            </Modal>
          )}
        </div>
      )}
      {/* Modal Détails Intervention */}
      {intervDetailItem && (
        <Modal isOpen={!!intervDetailItem} onClose={() => setIntervDetailItem(null)} title={`Intervention #${intervDetailItem?.id}`} size="lg">
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 rounded-lg bg-savia-surface-hover/50 border border-savia-border/50">
                  <span className="text-sm text-savia-text-muted flex items-center gap-2">
                    <ClipboardList className="w-4 h-4" /> Statut
                  </span>
                  <span className={`px-2 py-1 rounded-full text-xs font-bold ${(intervDetailItem.statut.toLowerCase().includes('tur') || intervDetailItem.statut.toLowerCase().includes('termin')) ? 'bg-green-500/15 text-green-400' : intervDetailItem.statut.toLowerCase().includes('cours') ? 'bg-yellow-500/15 text-yellow-400' : 'bg-blue-500/15 text-blue-400'}`}>
                    {intervDetailItem.statut}
                  </span>
                </div>
                
                {[
                  { icon: <Wrench className="w-3.5 h-3.5" />, label: 'Machine', value: intervDetailItem.machine },
                  { icon: <Users className="w-3.5 h-3.5" />, label: 'Technicien', value: intervDetailItem.technicien },
                  { icon: <Building2 className="w-3.5 h-3.5" />, label: 'Client', value: intervDetailItem.client || '—' },
                  { icon: <Briefcase className="w-3.5 h-3.5" />, label: 'Type', value: intervDetailItem.type || '—' }
                ].map((item, idx) => (
                  <div key={idx} className="flex flex-col">
                    <span className="text-xs text-savia-text-dim flex items-center gap-1.5 mb-1">{item.icon} {item.label}</span>
                    <span className="text-sm font-medium">{item.value}</span>
                  </div>
                ))}
              </div>

              <div className="space-y-3">
                {[
                  { icon: <Calendar className="w-3.5 h-3.5" />, label: 'Date', value: intervDetailItem.date.substring(0,10) },
                  { icon: <Timer className="w-3.5 h-3.5" />, label: 'Durée (h)', value: intervDetailItem.duree_minutes ? `${+(intervDetailItem.duree_minutes / 60).toFixed(2)}h` : `${intervDetailItem.duree}h` },
                  { icon: <Clock className="w-3.5 h-3.5" />, label: 'Déplacement (h)', value: intervDetailItem.deplacement ? `${intervDetailItem.deplacement}h` : '—' },
                  { icon: <Gauge className="w-3.5 h-3.5" />, label: 'Priorité', value: intervDetailItem.priorite || '—' }
                ].map((item, idx) => (
                  <div key={idx} className="flex flex-col">
                    <span className="text-xs text-savia-text-dim flex items-center gap-1.5 mb-1">{item.icon} {item.label}</span>
                    <span className="text-sm font-medium">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="w-full h-px bg-savia-border/30"></div>

            <div className="space-y-4">
              <h4 className="text-sm font-bold text-savia-text flex items-center gap-2">
                <FileText className="w-4 h-4 text-savia-accent" /> Diagnostic et Travaux
              </h4>
              
              {(intervDetailItem.description || intervDetailItem.probleme) && (
                <div className="grid grid-cols-2 gap-4">
                  {intervDetailItem.description && (
                    <div className="p-3 rounded-lg bg-savia-surface-hover/30 border border-savia-border/30">
                      <span className="text-xs text-savia-text-dim block mb-1">Description</span>
                      <p className="text-sm text-savia-text">{intervDetailItem.description}</p>
                    </div>
                  )}
                  {intervDetailItem.probleme && (
                    <div className="p-3 rounded-lg bg-red-500/5 border border-red-500/10">
                      <span className="text-xs text-red-400 block mb-1">Problème signalé</span>
                      <p className="text-sm text-savia-text">{intervDetailItem.probleme}</p>
                    </div>
                  )}
                </div>
              )}

              {(intervDetailItem.cause || intervDetailItem.solution) && (
                <div className="grid grid-cols-2 gap-4">
                  {intervDetailItem.cause && (
                    <div className="p-3 rounded-lg bg-orange-500/5 border border-orange-500/10">
                      <span className="text-xs text-orange-400 block mb-1">Cause diagnostiquée</span>
                      <p className="text-sm text-savia-text">{intervDetailItem.cause}</p>
                    </div>
                  )}
                  {intervDetailItem.solution && (
                    <div className="p-3 rounded-lg bg-green-500/5 border border-green-500/10">
                      <span className="text-xs text-green-400 block mb-1">Solution apportée</span>
                      <p className="text-sm text-savia-text">{intervDetailItem.solution}</p>
                    </div>
                  )}
                </div>
              )}

              {intervDetailItem.pieces_utilisees && (
                <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/10">
                  <span className="text-xs text-blue-400 block mb-1 flex items-center gap-1.5"><Server className="w-3 h-3"/> Pièces utilisées</span>
                  <p className="text-sm text-savia-text">{intervDetailItem.pieces_utilisees}</p>
                </div>
              )}

              {intervDetailItem.code_erreur && (
                <div className="flex items-center gap-2 p-2 rounded bg-savia-surface border border-savia-border">
                  <span className="text-xs text-savia-text-dim">Code erreur:</span>
                  <span className="font-mono text-sm text-savia-accent">{intervDetailItem.code_erreur}</span>
                  {intervDetailItem.type_erreur && <span className="text-xs text-savia-text-dim ml-2">({intervDetailItem.type_erreur})</span>}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button onClick={() => handleDownloadFicheIntervention(intervDetailItem)}
                className="px-4 py-2 rounded-lg text-sm font-bold bg-teal-500/10 text-teal-400 hover:bg-teal-500/20 cursor-pointer transition-colors"
              >
                <Download className="w-4 h-4 inline mr-1" /> Télécharger PDF
              </button>
              <button onClick={() => setIntervDetailItem(null)}
                className="px-4 py-2 rounded-lg text-sm font-bold bg-savia-surface-hover text-savia-text hover:bg-savia-border cursor-pointer transition-colors"
              >
                Fermer
              </button>
            </div>
          </div>
        </Modal>
      )}

    </div>
  );
}
