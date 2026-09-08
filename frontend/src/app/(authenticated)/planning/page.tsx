'use client';
import { useState, useEffect, useMemo, useCallback } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Modal } from '@/components/ui/modal';
import {
  Plus, ChevronLeft, ChevronRight, Loader2, Save, AlertTriangle,
  Calendar, Building2, Server, User, RefreshCw, FileText, StickyNote,
  Wrench, CheckCircle, Trash2, X, Scan, Activity, Microscope, Wind,
  ChevronDown, Check, Download, MapPin, Stethoscope, BarChart3
} from 'lucide-react';
import { planning, equipements, clients as clientsApi, paysCustom as paysCustomApi, techniciens as techApi, typesIntervention } from '@/lib/api';
import { downloadBlob } from '@/lib/download';
import { exportComparateurToCSV, exportComparateurToJSON, exportComparateurToPDF, getComparateurSummary } from '@/lib/export';
import { useAuth } from '@/lib/auth-context';
import { INTERVENTION_TYPES_BASE, mergeInterventionTypes } from '@/lib/intervention-types';
import { DEFAULT_COUNTRY, getCountry, parseCountrySelection, type CountryCode } from '@/lib/location-config';

// Import domaines API
import { domaines_custom } from '@/lib/api';

const INPUT_CLS = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all";

// ─── Domaines médicaux ────────────────────────────────────────────────
const DOMAINES_MEDICAUX = ['Radiologie', 'POC / Soins Intensifs', 'Laboratoire', 'Anesthésie / Bloc Op.'] as const;
const DOMAINE_ICONS_MAP: Record<string, React.ReactNode> = {
  'Radiologie':            <Scan       className="w-4 h-4" />,
  'POC / Soins Intensifs': <Activity   className="w-4 h-4" />,
  'Laboratoire':           <Microscope className="w-4 h-4" />,
  'Anesthésie / Bloc Op.': <Wind       className="w-4 h-4" />,
};
const DOMAINE_ACTIVE_CLS: Record<string, string> = {
  'Radiologie':            'bg-blue-600/40   border-blue-400/70   text-white',
  'POC / Soins Intensifs': 'bg-orange-600/40 border-orange-400/70 text-white',
  'Laboratoire':           'bg-purple-600/40 border-purple-400/70 text-white',
  'Anesthésie / Bloc Op.': 'bg-teal-600/40   border-teal-400/70   text-white',
};
// ────────────────────────────────────────────────────────────────────
const MONTHS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];
const DAYS_SHORT = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];
const STATUT_COLORS: Record<string, { cell: string; badge: string; dot: string }> = {
  'Planifiée':  { cell: 'bg-blue-500/20 border-blue-500 text-blue-300',    badge: 'bg-blue-500/15 text-blue-400',    dot: 'bg-blue-400' },
  'En cours':   { cell: 'bg-yellow-500/20 border-yellow-500 text-yellow-300', badge: 'bg-yellow-500/15 text-yellow-400', dot: 'bg-yellow-400' },
  'Réalisée':   { cell: 'bg-green-500/20 border-green-500 text-green-300',  badge: 'bg-green-500/15 text-green-400',  dot: 'bg-green-400' },
  'Cloturee':   { cell: 'bg-green-500/20 border-green-500 text-green-300',  badge: 'bg-green-500/15 text-green-400',  dot: 'bg-green-400' },
  'En retard':  { cell: 'bg-red-500/20 border-red-500 text-red-300',        badge: 'bg-red-500/15 text-red-400',      dot: 'bg-red-400' },
  'Décalé':     { cell: 'bg-gray-500/20 border-gray-500 text-gray-400',     badge: 'bg-gray-500/15 text-gray-500',    dot: 'bg-gray-400' },
};
const getStatutColor = (statut: string, isOverdue: boolean) => {
  if (isOverdue) return STATUT_COLORS['En retard'];
  return STATUT_COLORS[statut] || { cell: 'bg-blue-500/20 border-blue-500 text-blue-300', badge: 'bg-blue-500/15 text-blue-400', dot: 'bg-blue-400' };
};

// Les maintenances démarrent automatiquement le jour prévu. Une demande
// d'intervention, elle, attend l'acceptation explicite d'un technicien.
const getAutomaticStatus = (datePlanifiee: string, storedStatus: string, notes = ''): string => {
  if (!datePlanifiee) return storedStatus;

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  
  const plannedDate = new Date(datePlanifiee);
  plannedDate.setHours(0, 0, 0, 0);
  
  // If already completed/terminated/closed, keep that status
  if (storedStatus === 'Réalisée' || storedStatus === 'Annulée' || storedStatus === 'Cloturee') {
    return storedStatus;
  }

  // If status is "Décalé" (ghost entry), keep it as is
  if (storedStatus === 'Décalé') {
    return 'Décalé';
  }

  const isPendingInterventionRequest = /^Demande\s+#\d+/i.test(notes.trim())
    && storedStatus === 'Planifiée';
  if (isPendingInterventionRequest && plannedDate >= today) {
    return 'Planifiée';
  }
  
  // If planned date is in the future (> today), it's "Planifiée"
  if (plannedDate > today) {
    return 'Planifiée';
  }
  
  // If planned date is today, it's "En cours"
  if (plannedDate.getTime() === today.getTime()) {
    return 'En cours';
  }
  
  // If planned date is in the past (< today), it's "En retard"
  if (plannedDate < today) {
    return 'En retard';
  }
  
  return storedStatus;
};

const RECURRENCES = ['Aucune', 'Hebdomadaire', 'Mensuelle', 'Trimestrielle', 'Semestrielle', 'Annuelle'];
interface PlanItem {
  id: number;
  date_planifiee: string;
  machine: string;
  client: string;
  description: string;
  technicien: string;
  statut: string;
  type_maintenance: string;
  recurrence: string;
  notes: string;
  contrat_id?: number | null;
  is_ghost?: boolean;
  original_planning_id?: number | null;
}

const CLOSED_PLANNING_STATUSES = new Set(['Réalisée', 'Cloturee', 'Annulée']);
const HISTORICAL_ANCHOR_MARKER = '[Ancre historique SAVIA]';
const isHistoricalAnchor = (item: Pick<PlanItem, 'notes'>) =>
  item.notes?.includes(HISTORICAL_ANCHOR_MARKER);
const canReschedule = (item: PlanItem) =>
  !item.is_ghost &&
  !CLOSED_PLANNING_STATUSES.has(item.statut) &&
  !CLOSED_PLANNING_STATUSES.has(getAutomaticStatus(item.date_planifiee, item.statut, item.notes));

const emptyForm = {
  domaine: 'Radiologie' as string,
  client: '',
  machine: '',
  type_maintenance: 'Préventive',
  recurrence: 'Aucune',
  date_planifiee: '',
  technicien_assigne: '',
  description: '',
  notes: '',
};

export default function PlanningPage() {
  const { user } = useAuth();
  const isLecteur = user?.role === 'Lecteur';
  const canCreate = user?.role && ['Admin', 'Manager', 'Responsable Technique'].includes(user.role);
  const now = new Date();
  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

  const [currentMonth, setCurrentMonth] = useState(now.getMonth());
  const [currentYear, setCurrentYear] = useState(now.getFullYear());
  const [data, setData] = useState<PlanItem[]>([]);
  const [clientsList, setClientsList] = useState<string[]>([]);
  const [equipsAll, setEquipsAll] = useState<{nom: string; client: string; domaine: string}[]>([]);
  const [techsList, setTechsList] = useState<string[]>([]);
  const [domainesCustom, setDomainesCustom] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedDay, setSelectedDay] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [customMaintenanceTypes, setCustomMaintenanceTypes] = useState<string[]>([]);
  const [customTypeMode, setCustomTypeMode] = useState(false);
  const [customTypeValue, setCustomTypeValue] = useState('');
  const [error, setError] = useState('');
  // Day-detail popup
  const [dayDetailDate, setDayDetailDate] = useState<string | null>(null);
  const [dayDetailEvents, setDayDetailEvents] = useState<PlanItem[]>([]);
  const [techDropdownOpen, setTechDropdownOpen] = useState(false);
  
  // Reschedule modal
  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [selectedIntervention, setSelectedIntervention] = useState<PlanItem | null>(null);
  const [rescheduleForm, setRescheduleForm] = useState({ newDate: '', newTechs: '', reason: '' });
  const [rescheduleError, setRescheduleError] = useState('');
  const [isRescheduling, setIsRescheduling] = useState(false);
  const [rescheduleDropdownOpen, setRescheduleDropdownOpen] = useState(false);
  const [planningToDelete, setPlanningToDelete] = useState<PlanItem | null>(null);
  const [isDeletingPlanning, setIsDeletingPlanning] = useState(false);
  const [deletePlanningError, setDeletePlanningError] = useState('');

  const maintenanceTypes = useMemo(() => mergeInterventionTypes(
    INTERVENTION_TYPES_BASE,
    customMaintenanceTypes,
    data.map(item => item.type_maintenance),
  ), [customMaintenanceTypes, data]);

  useEffect(() => {
    typesIntervention.list()
      .then(types => setCustomMaintenanceTypes(types.map(type => type.nom).filter(Boolean)))
      .catch(() => {});
  }, []);

  // Comparateur export modal
  const [showComparateurModal, setShowComparateurModal] = useState(false);
  const [selectedForComparateur, setSelectedForComparateur] = useState<PlanItem | null>(null);
  const [comparateurData, setComparateurData] = useState<any>(null);
  const [isLoadingComparateur, setIsLoadingComparateur] = useState(false);
  const [comparateurError, setComparateurError] = useState('');

  // Comparateur période modal
  const [showComparateurPeriodeModal, setShowComparateurPeriodeModal] = useState(false);
  const [comparateurPeriodeForm, setComparateurPeriodeForm] = useState({ dateDebut: '', dateFin: '' });
  const [comparateurPeriodeData, setComparateurPeriodeData] = useState<any>(null);
  const [isLoadingComparateurPeriode, setIsLoadingComparateurPeriode] = useState(false);
  const [comparateurPeriodeError, setComparateurPeriodeError] = useState('');

  // Table filters — Toutes les Maintenances
  const [filterClient,  setFilterClient]  = useState('Tous');
  const [filterEquip,   setFilterEquip]   = useState('Tous');
  const [filterTech,    setFilterTech]    = useState('Tous');
  const [filterStatut,  setFilterStatut]  = useState('Tous');
  const [filterRegion,  setFilterRegion]  = useState('Tous');
  const [filterVille,   setFilterVille]   = useState('Tous');
  const [filterCountry, setFilterCountry] = useState('Tous');
  const [selectedCountries, setSelectedCountries] = useState<CountryCode[]>(() => (typeof window !== 'undefined' ? parseCountrySelection(localStorage.getItem('savia_pays_selectionnes') || localStorage.getItem('savia_pays')) : [DEFAULT_COUNTRY]));
  const [customCountries, setCustomCountries] = useState<Array<{ code: string; nom: string; flag?: string }>>([]);
  const [clientsFullData, setClientsFullData] = useState<any[]>([]);
  
  // PDF date filters
  const [pdfDateFrom, setPdfDateFrom] = useState(() => {
    const d = new Date(); d.setMonth(d.getMonth() - 1);
    return d.toISOString().substring(0, 10);
  });
  const [pdfDateTo, setPdfDateTo] = useState(() => new Date().toISOString().substring(0, 10));

  // Combine default domains with custom domains
  const allDomaines = useMemo(() => {
    const defaults = Array.from(DOMAINES_MEDICAUX);
    const combined = [...new Set([...defaults, ...domainesCustom])];
    return combined;
  }, [domainesCustom]);

  // Filtrage en cascade : domaine → client → équipement
  const equipsForDomaine = useMemo(() => {
    if (!form.domaine) return equipsAll;
    // Match domain case-insensitively and only include equipment with matching domain
    return equipsAll.filter(e => {
      if (!e.domaine) return false; // Exclude equipment without a domain
      return e.domaine.toLowerCase() === form.domaine.toLowerCase();
    });
  }, [equipsAll, form.domaine]);

  const clientsForDomaine = useMemo(() => {
    // Filter clients to show only those with equipment in the selected domain
    if (!form.domaine) return clientsList;
    
    // Get unique clients that have equipment in the selected domain
    const clientsWithEquipInDomain = new Set(
      equipsForDomaine.map(e => e.client).filter(Boolean)
    );
    
    return Array.from(clientsWithEquipInDomain).sort();
  }, [equipsForDomaine, form.domaine, clientsList]);

  const filteredEquips = useMemo(() => {
    if (!form.client) return equipsForDomaine.map(e => e.nom);
    return equipsForDomaine.filter(e => e.client === form.client).map(e => e.nom);
  }, [equipsForDomaine, form.client]);

  const loadData = useCallback(async () => {
    try {
      const [planRes, eqRes, clRes, techRes, domainesRes] = await Promise.all([
        planning.list(),
        equipements.list().catch(() => []),
        clientsApi.list().catch(() => []),
        techApi.list().catch(() => []),
        domaines_custom.list().catch(() => []),
      ]);

      const mapped = (planRes as any[]).map((item: any) => ({
        id: item.id || 0,
        // La colonne BD s'appelle date_prevue, pas date_planifiee
        date_planifiee: item.date_prevue || item.date_planifiee || item.Date || '',
        machine: item.machine || '',
        client: item.client || '',
        description: item.description || '',
        technicien: item.technicien_assigne || item.technicien || '',
        statut: item.statut || 'Planifiée',
        type_maintenance: item.type_maintenance || 'Préventive',
        recurrence: item.recurrence || 'Aucune',
        notes: item.notes || '',
        contrat_id: item.contrat_id ?? null,
        is_ghost: item.is_ghost === true || item.is_ghost === 1 || item.is_ghost === 'true',
        original_planning_id: item.original_planning_id ?? null,
      }));
      setData(mapped);

      const equipsFlat = (eqRes as any[]).map((e: any) => ({
        nom: e.Nom || e.nom || '',
        client: e.Client || e.client || '',
        domaine: e.domaine || e.Domaine || '', // Don't default to Radiologie - keep empty if not set
      })).filter(e => e.nom);
      setEquipsAll(equipsFlat);

      // Load custom domains
      const customDomainNames = (domainesRes as any[]).map((d: any) => d.nom || d.name || '').filter(Boolean);
      setDomainesCustom(customDomainNames);

      const uniqueClients = [...new Set([
        ...(clRes as any[]).map((c: any) => c.nom || c.Nom || c.client || c.Client || ''),
        ...equipsFlat.map(e => e.client),
      ])].filter(Boolean).sort();
      setClientsList(uniqueClients);

      const techNames = (techRes as any[]).map((t: any) =>
        `${t.prenom || ''} ${t.nom || ''}`.trim()
      ).filter(Boolean);
      setTechsList(techNames);
      setClientsFullData(clRes as any[]);
    } catch (err) {
      console.error('Failed to fetch planning', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    const loadCountrySelection = async () => {
      try {
        const response = await fetch('/api/settings/public', { credentials: 'same-origin' });
        const settings = response.ok ? await response.json() : {};
        setSelectedCountries(parseCountrySelection(settings.pays || localStorage.getItem('savia_pays_selectionnes') || localStorage.getItem('savia_pays')));
        setCustomCountries(await paysCustomApi.list().catch(() => []));
      } catch { /* local storage fallback is already loaded */ }
    };
    void loadCountrySelection();
  }, []);


  // Calendar grid
  const calendarDays = useMemo(() => {
    const firstDay = new Date(currentYear, currentMonth, 1);
    const lastDay = new Date(currentYear, currentMonth + 1, 0);
    const startDow = (firstDay.getDay() + 6) % 7;
    const days: { day: number; inMonth: boolean; date: string }[] = [];

    const prevLastDay = new Date(currentYear, currentMonth, 0).getDate();
    for (let i = startDow - 1; i >= 0; i--) {
      const d = prevLastDay - i;
      const m = currentMonth === 0 ? 12 : currentMonth;
      const y = currentMonth === 0 ? currentYear - 1 : currentYear;
      days.push({ day: d, inMonth: false, date: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}` });
    }
    for (let d = 1; d <= lastDay.getDate(); d++) {
      days.push({ day: d, inMonth: true, date: `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}` });
    }
    const remaining = 42 - days.length;
    for (let d = 1; d <= remaining; d++) {
      const m = currentMonth === 11 ? 1 : currentMonth + 2;
      const y = currentMonth === 11 ? currentYear + 1 : currentYear;
      days.push({ day: d, inMonth: false, date: `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}` });
    }
    return days;
  }, [currentMonth, currentYear]);

  const eventsForDate = useCallback((dateStr: string) =>
    data.filter(d => (d.date_planifiee || '').substring(0, 10) === dateStr),
  [data]);

  const monthEvents = data.filter(d => {
    if (d.is_ghost || isHistoricalAnchor(d)) return false;
    const dt = new Date(d.date_planifiee);
    return dt.getMonth() === currentMonth && dt.getFullYear() === currentYear;
  });
  const overdueCount = data.filter(d => {
    if (d.is_ghost || isHistoricalAnchor(d)) return false;
    const automaticStatus = getAutomaticStatus(d.date_planifiee, d.statut, d.notes);
    // Only count as overdue if automatic status is "En retard"
    return automaticStatus === 'En retard';
  }).length;
  const realPlanningCount = data.filter(d => !d.is_ghost && !isHistoricalAnchor(d)).length;

  const handleSave = async () => {
    setError('');
    if (!form.machine.trim()) { setError('Veuillez sélectionner un équipement.'); return; }
    if (!form.date_planifiee) { setError('Veuillez choisir une date prévue.'); return; }
    setIsSaving(true);
    try {
      await planning.create({
        machine: form.machine,
        client: form.client,
        type_maintenance: form.type_maintenance,
        recurrence: form.recurrence,
        date_prevue: form.date_planifiee,
        technicien_assigne: form.technicien_assigne,
        description: form.description,
        notes: form.notes,
        statut: 'Planifiée',
      } as any);
      setShowAddModal(false);
      setForm(emptyForm);
      setCustomTypeMode(false);
      setCustomTypeValue('');
      await loadData();
    } catch (err) {
      console.error(err);
      setError('Erreur lors de la création. Veuillez réessayer.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleOpenReschedule = (intervention: PlanItem) => {
    setSelectedIntervention(intervention);
    setRescheduleForm({
      newDate: intervention.date_planifiee,
      newTechs: intervention.technicien,
      reason: '',
    });
    setRescheduleError('');
    setShowRescheduleModal(true);
  };

  const handleReschedule = async () => {
    setRescheduleError('');
    if (!selectedIntervention) return;
    
    if (!rescheduleForm.newDate) {
      setRescheduleError('Veuillez sélectionner une nouvelle date.');
      return;
    }
    
    setIsRescheduling(true);
    try {
      await planning.reschedule(selectedIntervention.id, {
        date_planifiee: rescheduleForm.newDate,
        technicien_assigne: rescheduleForm.newTechs,
        reason: rescheduleForm.reason,
      });
      setShowRescheduleModal(false);
      setSelectedIntervention(null);
      setRescheduleForm({ newDate: '', newTechs: '', reason: '' });
      await loadData();
    } catch (err: any) {
      console.error(err);
      setRescheduleError(err.message || 'Erreur lors du décalage. Veuillez réessayer.');
    } finally {
      setIsRescheduling(false);
    }
  };

  const handleDeletePlanning = async () => {
    if (!planningToDelete) return;

    setIsDeletingPlanning(true);
    setDeletePlanningError('');
    try {
      await planning.delete(planningToDelete.id);
      setPlanningToDelete(null);
      setDayDetailDate(null);
      setDayDetailEvents([]);
      await loadData();
    } catch (err: any) {
      console.error('Planning deletion failed', err);
      setDeletePlanningError(err?.message || 'Impossible de supprimer cette intervention du planning.');
    } finally {
      setIsDeletingPlanning(false);
    }
  };

  const handleOpenComparateur = async (intervention: PlanItem) => {
    setSelectedForComparateur(intervention);
    setComparateurError('');
    setComparateurData(null);
    setIsLoadingComparateur(true);
    setShowComparateurModal(true);
    
    try {
      const data = await planning.comparateur(intervention.id);
      setComparateurData(data);
    } catch (err: any) {
      console.error('Comparateur error:', err);
      setComparateurError(err.message || 'Erreur lors du chargement du comparateur');
    } finally {
      setIsLoadingComparateur(false);
    }
  };

  const handleExportComparateur = async (format: 'csv' | 'pdf' | 'json') => {
    if (!comparateurData) return;
    
    try {
      const timestamp = new Date().toISOString().slice(0, 10);
      const machine = comparateurData.machine || 'intervention';
      const filename = `comparateur_${machine}_${timestamp}`;
      
      switch (format) {
        case 'csv':
          exportComparateurToCSV(comparateurData, `${filename}.csv`);
          break;
        case 'json':
          exportComparateurToJSON(comparateurData, `${filename}.json`);
          break;
        case 'pdf':
          await exportComparateurToPDF(comparateurData, `${filename}.pdf`);
          break;
      }
    } catch (err: any) {
      console.error('Export error:', err);
      alert(`Erreur export ${format.toUpperCase()}: ${err.message || 'Erreur'}`);
    }
  };

  const handleOpenComparateurPeriode = () => {
    setComparateurPeriodeError('');
    setComparateurPeriodeData(null);
    setComparateurPeriodeForm({ dateDebut: '', dateFin: '' });
    setShowComparateurPeriodeModal(true);
  };

  const handleFetchComparateurPeriode = async () => {
    setComparateurPeriodeError('');
    
    if (!comparateurPeriodeForm.dateDebut || !comparateurPeriodeForm.dateFin) {
      setComparateurPeriodeError('Veuillez sélectionner les deux dates');
      return;
    }

    setIsLoadingComparateurPeriode(true);
    try {
      const data = await planning.comparateurPeriode(comparateurPeriodeForm.dateDebut, comparateurPeriodeForm.dateFin);
      setComparateurPeriodeData(data);
    } catch (err: any) {
      console.error('Comparateur période error:', err);
      setComparateurPeriodeError(err.message || 'Erreur lors du chargement');
    } finally {
      setIsLoadingComparateurPeriode(false);
    }
  };

  const handleExportComparateurPeriode = async (format: 'csv' | 'pdf' | 'json') => {
    if (!comparateurPeriodeData?.comparisons) return;
    
    try {
      const timestamp = new Date().toISOString().slice(0, 10);
      const filename = `comparateur-periode_${timestamp}`;
      
      // PDF export removed - keeping only modal display
    } catch (err: any) {
      console.error('Export error:', err);
      alert(`Erreur export ${format.toUpperCase()}: ${err.message || 'Erreur'}`);
    }
  };

  const prevMonth = () => {
    if (currentMonth === 0) { setCurrentMonth(11); setCurrentYear(y => y - 1); }
    else setCurrentMonth(m => m - 1);
  };
  const nextMonth = () => {
    if (currentMonth === 11) { setCurrentMonth(0); setCurrentYear(y => y + 1); }
    else setCurrentMonth(m => m + 1);
  };

  if (isLoading) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
            <Calendar className="w-7 h-7" /> Planning Maintenance
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Planification et suivi des maintenances préventives</p>
        </div>
        {canCreate && (
        <button onClick={() => { setForm({...emptyForm, date_planifiee: todayStr}); setError(''); setShowAddModal(true); }}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer shadow-lg disabled:opacity-50 disabled:cursor-not-allowed">
          <Plus className="w-4 h-4" /> Planifier une maintenance
        </button>
        )}
        <button onClick={handleOpenComparateurPeriode}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-purple-600 to-purple-500 hover:opacity-90 transition-all cursor-pointer shadow-lg">
          <BarChart3 className="w-4 h-4" /> Comparateur Période
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total planifié', value: realPlanningCount, color: 'text-savia-accent', icon: <Calendar className="w-5 h-5" /> },
          { label: 'Ce mois', value: monthEvents.length, color: 'text-blue-400', icon: <Calendar className="w-5 h-5" /> },
          { label: 'Réalisées', value: data.filter(d => !d.is_ghost && !isHistoricalAnchor(d) && (d.statut === 'Réalisée' || d.statut === 'Cloturee')).length, color: 'text-green-400', icon: <CheckCircle className="w-5 h-5" /> },
          { label: 'En retard', value: overdueCount, color: overdueCount > 0 ? 'text-red-400' : 'text-green-400', icon: <AlertTriangle className="w-5 h-5" /> },
        ].map(kpi => (
          <div key={kpi.label} className="glass rounded-xl p-4 text-center">
            <div className={`flex justify-center mb-2 ${kpi.color}`}>{kpi.icon}</div>
            <div className={`text-3xl font-black ${kpi.color}`}>{kpi.value}</div>
            <div className="text-xs text-savia-text-muted mt-1">{kpi.label}</div>
          </div>
        ))}
      </div>

      {overdueCount > 0 && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-4 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0" />
          <span className="text-red-400 font-bold">{overdueCount} maintenance(s) en retard !</span>
          <span className="text-xs text-savia-text-muted">Des maintenances planifiées n&apos;ont pas encore été réalisées.</span>
        </div>
      )}

      {/* Calendar */}
      <SectionCard title="">
        <div className="flex items-center justify-between mb-6">
          <button onClick={prevMonth} className="flex items-center gap-1 px-3 py-2 rounded-lg bg-savia-surface-hover hover:bg-savia-border text-savia-text transition-colors cursor-pointer">
            <ChevronLeft className="w-4 h-4" /> Précédent
          </button>
          <h2 className="text-xl font-black gradient-text">{MONTHS[currentMonth]} {currentYear}</h2>
          <button onClick={nextMonth} className="flex items-center gap-1 px-3 py-2 rounded-lg bg-savia-surface-hover hover:bg-savia-border text-savia-text transition-colors cursor-pointer">
            Suivant <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        <div className="grid grid-cols-7 gap-1 mb-2">
          {DAYS_SHORT.map(d => <div key={d} className="text-center text-xs font-bold text-savia-text-muted py-2">{d}</div>)}
        </div>

        <div className="grid grid-cols-7 gap-1">
          {calendarDays.map((cell, i) => {
            const events = eventsForDate(cell.date);
            const isToday = cell.date === todayStr;
            const isPast = new Date(cell.date) < now && !isToday;
            return (
              <div key={i}
                onClick={() => {
                  if (!cell.inMonth) return;
                  const evs = eventsForDate(cell.date);
                  if (evs.length > 0) {
                    // Ouvrir la popup détails (tous les rôles peuvent consulter)
                    setDayDetailDate(cell.date);
                    setDayDetailEvents(evs);
                  } else if (canCreate) {
                    // Ouvrir la modale ajout (seulement pour create roles)
                    setSelectedDay(cell.day);
                    setForm({...emptyForm, date_planifiee: cell.date});
                    setError('');
                    setShowAddModal(true);
                  }
                }}
                className={`min-h-[80px] rounded-lg p-1 border transition-all cursor-pointer ${
                  !cell.inMonth ? 'opacity-30 border-transparent' :
                  isToday ? 'border-cyan-400 bg-cyan-400/5' :
                  selectedDay === cell.day ? 'border-blue-400 bg-blue-400/5' :
                  'border-savia-border/30 hover:border-savia-border hover:bg-savia-surface-hover/30'
                }`}
              >
                <div className={`text-xs font-bold mb-1 ${isToday ? 'text-cyan-400' : cell.inMonth ? 'text-savia-text' : 'text-slate-600'}`}>{cell.day}</div>
                <div className="space-y-0.5">
                  {events.slice(0, 3).map((ev, j) => {
                    const automaticStatus = getAutomaticStatus(ev.date_planifiee, ev.statut, ev.notes);
                    const colors = getStatutColor(automaticStatus, false);
                    return (
                      <div key={j} className={`text-[10px] leading-tight px-1 py-0.5 rounded border-l-2 truncate ${colors.cell}`}
                        title={`[${automaticStatus}] ${ev.machine} — ${ev.technicien}`}>
                        {ev.machine.substring(0, 14)}
                      </div>
                    );
                  })}
                  {events.length > 3 && <div className="text-[10px] text-savia-text-dim px-1">+{events.length - 3}</div>}
                </div>
              </div>
            );
          })}
        </div>
      </SectionCard>

      {/* Status Legend */}
      <div className="glass rounded-xl px-5 py-3 flex flex-wrap items-center gap-4">
        <span className="text-xs font-bold text-savia-text-muted uppercase tracking-wider">Légende :</span>
        {[
          { label: 'Planifiée',  dot: 'bg-blue-400',   text: 'text-blue-400'   },
          { label: 'En cours',   dot: 'bg-yellow-400', text: 'text-yellow-400' },
          { label: 'Cloturee',   dot: 'bg-green-400',  text: 'text-green-400'  },
          { label: 'En retard',  dot: 'bg-red-400',    text: 'text-red-400'    },
          { label: 'Décalé',     dot: 'bg-gray-400',   text: 'text-gray-400'   },
        ].map(s => (
          <div key={s.label} className="flex items-center gap-2">
            <span className={`w-3 h-3 rounded-sm border-l-2 ${s.dot} opacity-80`} />
            <span className={`text-xs font-semibold ${s.text}`}>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Upcoming list */}
      {/* ── Filter options derived from data ── */}
      {(() => {
        const fClients  = ['Tous', ...Array.from(new Set(data.map(d => d.client).filter(Boolean))).sort()];
        // Derive region/ville from clients data
        const clientRegionMap = new Map<string, string>();
        const clientVilleMap = new Map<string, string>();
        const clientCountryMap = new Map<string, string>();
        clientsFullData.forEach((c: any) => {
          const name = c.nom || c.Nom || '';
          if (c.region) clientRegionMap.set(name, c.region);
          if (c.ville) clientVilleMap.set(name, c.ville);
          clientCountryMap.set(name, c.country_code || DEFAULT_COUNTRY);
        });
        const getRegion = (client: string) => clientRegionMap.get(client) || '';
        const getVille = (client: string) => clientVilleMap.get(client) || '';
        const getCountryCode = (client: string) => clientCountryMap.get(client) || DEFAULT_COUNTRY;

        const fRegions  = ['Tous', ...Array.from(new Set(data.map(d => getRegion(d.client)).filter(Boolean))).sort()];
        const fVilles   = ['Tous', ...Array.from(new Set(
          data.filter(d => (filterCountry === 'Tous' || getCountryCode(d.client) === filterCountry) && (filterRegion === 'Tous' || getRegion(d.client) === filterRegion))
            .map(d => getVille(d.client)).filter(Boolean)
        )).sort()];
        const fCountries = ['Tous', ...selectedCountries];
        const fEquips   = ['Tous', ...Array.from(new Set(
          data.filter(d => filterClient === 'Tous' || d.client === filterClient).map(d => d.machine).filter(Boolean)
        )).sort()];
        const fTechs    = ['Tous', ...Array.from(new Set(data.map(d => d.technicien).filter(Boolean))).sort()];
        const fStatuts  = ['Tous', 'Planifiée', 'En cours', 'Cloturee', 'En retard', 'Décalé'];
        const filteredData = data
          .filter(d => filterCountry === 'Tous' || getCountryCode(d.client) === filterCountry)
          .filter(d => filterRegion === 'Tous' || getRegion(d.client) === filterRegion)
          .filter(d => filterVille  === 'Tous' || getVille(d.client) === filterVille)
          .filter(d => filterClient === 'Tous' || d.client === filterClient)
          .filter(d => filterEquip  === 'Tous' || d.machine === filterEquip)
          .filter(d => filterTech   === 'Tous' || d.technicien === filterTech)
          .filter(d => {
            if (filterStatut === 'Tous') return true;
            const automaticStatus = getAutomaticStatus(d.date_planifiee, d.statut, d.notes);
            return automaticStatus === filterStatut;
          })
          .filter(d => {
            // Un ghost est une trace d'audit du décalage : il doit rester
            // visible même si sa date originale est hors de la période active.
            if (d.is_ghost) return true;
            const dateStr = (d.date_planifiee || '').substring(0, 10);
            if (!dateStr) return false;
            return dateStr >= pdfDateFrom && dateStr <= pdfDateTo;
          });
        const realFilteredData = filteredData.filter(d => !d.is_ghost && !isHistoricalAnchor(d));
        const historicalFilteredCount = filteredData.filter(d => !d.is_ghost && isHistoricalAnchor(d)).length;
        const ghostFilteredCount = filteredData.filter(d => d.is_ghost).length;
        const selCls = "bg-savia-surface-hover border border-savia-border rounded-lg px-3 py-1.5 text-savia-text text-xs focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all min-w-[130px]";
        return (
      <SectionCard title={"Toutes les Maintenances (" + realFilteredData.length + (realFilteredData.length !== realPlanningCount ? " / " + realPlanningCount : "") + ")" + (historicalFilteredCount > 0 ? " · " + historicalFilteredCount + " maintenance(s) historique(s)" : "") + (ghostFilteredCount > 0 ? " · " + ghostFilteredCount + " trace(s) de décalage" : "")}>
        {/* Filter bar */}
        <div className="flex flex-wrap gap-3 mb-3 pb-3 border-b border-savia-border/40">
          {/* Région */}
          {selectedCountries.length > 1 && (
          <div className="flex items-center gap-2">
            <MapPin className="w-3.5 h-3.5 text-cyan-400 flex-shrink-0" />
            <select value={filterCountry} onChange={e => { setFilterCountry(e.target.value); setFilterRegion('Tous'); setFilterVille('Tous'); setFilterClient('Tous'); setFilterEquip('Tous'); }} className={selCls}>
              {fCountries.map(code => {
                if (code === 'Tous') return <option key={code} value={code}>Tous les pays</option>;
                const custom = customCountries.find(item => item.code === code);
                const builtIn = getCountry(code);
                return <option key={code} value={code}>{custom?.flag || builtIn.flag} {custom?.nom || builtIn.name}</option>;
              })}
            </select>
          </div>
          )}
          {/* Région */}
          <div className="flex items-center gap-2">
            <MapPin className="w-3.5 h-3.5 text-savia-accent flex-shrink-0" />
            <select value={filterRegion} onChange={e => { setFilterRegion(e.target.value); setFilterVille('Tous'); setFilterClient('Tous'); setFilterEquip('Tous'); }} className={selCls}>
              {fRegions.map(r => <option key={r} value={r}>{r === 'Tous' ? 'Toutes les régions' : r}</option>)}
            </select>
          </div>
          {/* Ville */}
          <div className="flex items-center gap-2">
            <MapPin className="w-3.5 h-3.5 text-orange-400 flex-shrink-0" />
            <select value={filterVille} onChange={e => { setFilterVille(e.target.value); setFilterClient('Tous'); setFilterEquip('Tous'); }} className={selCls}>
              {fVilles.map(v => <option key={v} value={v}>{v === 'Tous' ? 'Toutes les villes' : v}</option>)}
            </select>
          </div>
          {/* Client */}
          <div className="flex items-center gap-2">
            <Building2 className="w-3.5 h-3.5 text-savia-accent flex-shrink-0" />
            <select value={filterClient} onChange={e => { setFilterClient(e.target.value); setFilterEquip('Tous'); }} className={selCls}>
              {fClients.map(c => <option key={c} value={c}>{c === 'Tous' ? 'Tous les clients' : c}</option>)}
            </select>
          </div>
          {/* Équipement */}
          <div className="flex items-center gap-2">
            <Server className="w-3.5 h-3.5 text-savia-accent flex-shrink-0" />
            <select value={filterEquip} onChange={e => setFilterEquip(e.target.value)} className={selCls}>
              {fEquips.map(e => <option key={e} value={e}>{e === 'Tous' ? 'Tous les équipements' : e}</option>)}
            </select>
          </div>
          {/* Technicien */}
          <div className="flex items-center gap-2">
            <User className="w-3.5 h-3.5 text-savia-accent flex-shrink-0" />
            <select value={filterTech} onChange={e => setFilterTech(e.target.value)} className={selCls}>
              {fTechs.map(t => <option key={t} value={t}>{t === 'Tous' ? 'Tous les techniciens' : t}</option>)}
            </select>
          </div>
          {/* Statut */}
          <div className="flex items-center gap-2">
            <CheckCircle className="w-3.5 h-3.5 text-savia-accent flex-shrink-0" />
            <select value={filterStatut} onChange={e => setFilterStatut(e.target.value)} className={selCls}>
              {fStatuts.map(s => <option key={s} value={s}>{s === 'Tous' ? 'Tous les statuts' : s}</option>)}
            </select>
          </div>
        </div>

        {/* Second filter row: Date range for PDF */}
        <div className="flex flex-wrap gap-3 mb-3 pb-3 border-b border-savia-border/40">
          <div className="flex items-center gap-2">
            <Calendar className="w-3.5 h-3.5 text-savia-accent flex-shrink-0" />
            <label className="text-xs font-semibold text-savia-text-muted uppercase tracking-wider">Période :</label>
            <input 
              type="date" 
              value={pdfDateFrom} 
              onChange={e => setPdfDateFrom(e.target.value)} 
              title="Date début"
              className="bg-savia-surface-hover border border-savia-border rounded-lg px-3 py-1.5 text-savia-text text-xs focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all"
            />
            <span className="text-xs text-savia-text-muted">à</span>
            <input 
              type="date" 
              value={pdfDateTo} 
              onChange={e => setPdfDateTo(e.target.value)} 
              title="Date fin"
              className="bg-savia-surface-hover border border-savia-border rounded-lg px-3 py-1.5 text-savia-text text-xs focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all"
            />
          </div>
          {/* Reset */}
          {(filterCountry !== 'Tous' || filterClient !== 'Tous' || filterEquip !== 'Tous' || filterTech !== 'Tous' || filterStatut !== 'Tous' || filterRegion !== 'Tous' || filterVille !== 'Tous') && (
            <button onClick={() => { setFilterCountry('Tous'); setFilterClient('Tous'); setFilterEquip('Tous'); setFilterTech('Tous'); setFilterStatut('Tous'); setFilterRegion('Tous'); setFilterVille('Tous'); }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-red-400 hover:bg-red-500/10 border border-red-500/20 transition-all cursor-pointer">
              <X className="w-3 h-3" /> Réinitialiser
            </button>
          )}
          {/* Comparateur Export */}
          <button
            onClick={() => {
              if (filteredData.length === 0) {
                alert('Sélectionnez une maintenance à comparer');
                return;
              }
              // For now, show first intervention in filtered list
              if (filteredData.length > 0) {
                handleOpenComparateur(filteredData[0]);
              }
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-cyan-400 hover:bg-cyan-400/10 border border-cyan-400/30 transition-all cursor-pointer"
          >
            <BarChart3 className="w-3.5 h-3.5" /> Comparateur
          </button>
          {/* PDF Download */}
          <button
            onClick={async () => {
              try {
                const printData = filteredData
                  .sort((a, b) => (a.date_planifiee || '').localeCompare(b.date_planifiee || ''));
                
                const filterLabel = filterClient !== 'Tous' ? filterClient : filterRegion !== 'Tous' ? `Région: ${filterRegion}` : filterVille !== 'Tous' ? `Ville: ${filterVille}` : filterTech !== 'Tous' ? `Technicien: ${filterTech}` : 'Tous les clients';
                const cn = localStorage.getItem('savia_company') || 'SAVIA';
                const cl = localStorage.getItem('savia_logo') || '';
                
                const res = await fetch('/api/planning/pdf', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  credentials: 'same-origin',
                  body: JSON.stringify({ 
                    rows: printData, 
                    filter_label: filterLabel, 
                    company_name: cn, 
                    company_logo: cl
                  }),
                });
                if (!res.ok) throw new Error('Erreur ' + res.status);
                const blob = await res.blob();
                downloadBlob(blob, `planning_maintenance_${pdfDateFrom}_${pdfDateTo}.pdf`);
              } catch (err: any) { alert('Erreur PDF: ' + (err.message || 'Inconnue')); }
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-savia-accent hover:bg-savia-accent/10 border border-savia-accent/30 transition-all cursor-pointer ml-auto"
          >
            <Download className="w-3.5 h-3.5" /> Télécharger PDF
          </button>
        </div>
        <div className="overflow-x-auto">
          <div className="overflow-y-auto" style={{maxHeight: '400px'}}>
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-savia-surface z-10">
                <tr className="border-b border-savia-border">
                  {['#ID', 'Date prévue', 'Client', 'Équipement', 'Technicien', 'Type', 'Récurrence', 'Statut', 'Actions'].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredData.length === 0 ? (
                  <tr><td colSpan={9} className="text-center py-8 text-savia-text-muted text-sm">Aucune maintenance ne correspond aux filtres sélectionnés.</td></tr>
                ) : filteredData
                  .slice()
                  .sort((a, b) => {
                    // Items avec date en premier, triés chronologiquement
                    if (!a.date_planifiee && !b.date_planifiee) return 0;
                    if (!a.date_planifiee) return 1;
                    if (!b.date_planifiee) return -1;
                    return a.date_planifiee.localeCompare(b.date_planifiee);
                  })
                  .map(ev => {
                    const hasDate = !!ev.date_planifiee;
                    const automaticStatus = getAutomaticStatus(ev.date_planifiee, ev.statut, ev.notes);
                    const colors = getStatutColor(automaticStatus, false);
                    const isOverdue = automaticStatus === 'En retard';
                    const historicalAnchor = isHistoricalAnchor(ev);
                    return (
                      <tr key={ev.id} className={`border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors ${isOverdue ? 'bg-red-500/5' : ''}`}>
                        <td className="py-2 px-3 text-xs font-mono whitespace-nowrap text-savia-text-muted">#{ev.id}</td>
                        <td className="py-2 px-3 text-xs font-mono whitespace-nowrap">
                          {hasDate ? ev.date_planifiee.substring(0, 10) : <span className="text-savia-text-dim italic">Sans date</span>}
                        </td>
                        <td className="py-2 px-3 text-xs text-savia-text-muted">{ev.client || '—'}</td>
                        <td className="py-2 px-3 font-semibold text-sm">{ev.machine}</td>
                        <td className="py-2 px-3 text-xs">{ev.technicien || '—'}</td>
                        <td className="py-2 px-3 text-xs whitespace-nowrap">
                          {ev.type_maintenance}
                          {historicalAnchor && <span className="ml-1 rounded border border-slate-700 bg-slate-700 px-1.5 py-0.5 text-[10px] font-bold text-white">Historique</span>}
                        </td>
                        <td className="py-2 px-3 text-xs text-savia-text-muted">{ev.recurrence && ev.recurrence !== 'Aucune' ? ev.recurrence : '—'}</td>
                        <td className="py-2 px-3">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${colors.badge}`}>
                            {automaticStatus}
                          </span>
                        </td>
                        <td className="py-2 px-3">
                          {canCreate && !ev.contrat_id && !ev.is_ghost && !historicalAnchor ? (
                            <button
                              onClick={() => { setPlanningToDelete(ev); setDeletePlanningError(''); }}
                              className="inline-flex items-center gap-1 rounded-lg border border-red-500/30 bg-red-500/10 px-2 py-1 text-xs font-semibold text-red-400 transition-colors hover:bg-red-500/20"
                              title="Supprimer du planning"
                            >
                              <Trash2 className="h-3.5 w-3.5" /> Supprimer
                            </button>
                          ) : <span className="text-savia-text-dim">—</span>}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      </SectionCard>
        );
      })()}

      {/* ADD MODAL */}
      <Modal isOpen={showAddModal} onClose={() => { setShowAddModal(false); setSelectedDay(null); }} title={`Planifier une Maintenance${selectedDay ? ` — ${String(selectedDay).padStart(2,'0')}/${String(currentMonth+1).padStart(2,'0')}/${currentYear}` : ''}`}>
        <div className="space-y-5">

          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-red-400 text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
            </div>
          )}

          {/* ── Domaine médical ── */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
              <Scan className="w-3.5 h-3.5 text-savia-accent" /> Domaine médical *
            </label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {/* All domains (default + custom) */}
              {allDomaines.map(d => (
                <button key={d} type="button"
                  onClick={() => setForm({...form, domaine: d, client: '', machine: ''})}
                  className={`flex flex-col items-center gap-1.5 py-3 px-2 rounded-xl text-xs font-semibold transition-all cursor-pointer border ${
                    form.domaine === d
                      ? DOMAINE_ACTIVE_CLS[d] || 'bg-indigo-600/40 border-indigo-400/70 text-white'
                      : 'bg-savia-bg/50 border-savia-border text-savia-text-muted hover:bg-savia-surface-hover'
                  }`}
                >
                  <div className="scale-110">{DOMAINE_ICONS_MAP[d] || <Server className="w-4 h-4" />}</div>
                  <span className="text-center leading-tight">
                    {d === 'POC / Soins Intensifs' ? 'POC / Soins' : d === 'Anesthésie / Bloc Op.' ? 'Anesthésie' : d.length > 12 ? d.substring(0, 12) + '...' : d}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Client + Type */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                <Building2 className="w-3.5 h-3.5 text-savia-accent" /> Client *
                {clientsForDomaine.length > 0 && (
                  <span className="text-savia-text-dim font-normal normal-case text-[11px]">({clientsForDomaine.length} client{clientsForDomaine.length > 1 ? 's' : ''})</span>
                )}
              </label>
              <select className={INPUT_CLS} value={form.client}
                onChange={e => setForm({...form, client: e.target.value, machine: ''})}>
                <option value="">— Sélectionner un client —</option>
                {clientsForDomaine.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
              {form.domaine && clientsForDomaine.length === 0 && (
                <p className="text-xs text-amber-400/70 mt-1">Aucun client avec des équipements dans ce domaine.</p>
              )}
            </div>
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                <Wrench className="w-3.5 h-3.5 text-savia-accent" /> Type de maintenance *
              </label>
              {customTypeMode ? (
                <div className="flex gap-2">
                  <input
                    className={INPUT_CLS}
                    placeholder="Saisir le type..."
                    value={customTypeValue}
                    onChange={e => setCustomTypeValue(e.target.value)}
                    autoFocus
                  />
                  <button type="button" onClick={async () => {
                    const value = customTypeValue.trim();
                    if (!value) return;
                    try {
                      await typesIntervention.create(value);
                      setCustomMaintenanceTypes(prev => mergeInterventionTypes(prev, [value]));
                      setForm(prev => ({ ...prev, type_maintenance: value }));
                      setCustomTypeMode(false);
                      setCustomTypeValue('');
                    } catch {
                      setError('Impossible d’enregistrer ce type.');
                    }
                  }} className="px-3 py-1 rounded-lg bg-savia-accent text-white font-bold text-sm hover:opacity-90 cursor-pointer">
                    <Check className="w-4 h-4" />
                  </button>
                  <button type="button" onClick={() => { setCustomTypeMode(false); setCustomTypeValue(''); }} className="px-3 py-1 rounded-lg bg-savia-surface-hover text-savia-text-muted text-sm hover:opacity-90 cursor-pointer">
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <select className={INPUT_CLS} value={form.type_maintenance}
                  onChange={e => {
                    if (e.target.value === '__autre__') {
                      setCustomTypeMode(true);
                      return;
                    }
                    setForm({...form, type_maintenance: e.target.value});
                  }}>
                  {maintenanceTypes.map(t => <option key={t} value={t}>{t}</option>)}
                  <option value="__autre__">✏️ Autre (saisie manuelle)</option>
                </select>
              )}
            </div>
          </div>

          {/* Équipement (filtré par domaine puis client) */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
              <Server className="w-3.5 h-3.5 text-savia-accent" /> Équipement *
              {filteredEquips.length > 0 && <span className="text-savia-text-dim font-normal normal-case text-[11px]">({filteredEquips.length} disponible{filteredEquips.length > 1 ? 's' : ''})</span>}
            </label>
            <select className={INPUT_CLS} value={form.machine}
              onChange={e => setForm({...form, machine: e.target.value})}>
              <option value="">— Sélectionner un équipement —</option>
              {filteredEquips.map(e => <option key={e} value={e}>{e}</option>)}
              {filteredEquips.length === 0 && form.client && (
                <option disabled>Aucun équipement pour ce client dans ce domaine</option>
              )}
            </select>
            {!form.client && (
              <p className="text-xs text-savia-text-dim mt-1">Sélectionnez d&apos;abord un client pour filtrer les équipements.</p>
            )}
          </div>

          {/* Date + Récurrence */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                <Calendar className="w-3.5 h-3.5 text-savia-accent" /> Date prévue *
              </label>
              <input type="date" className={INPUT_CLS} value={form.date_planifiee}
                onChange={e => setForm({...form, date_planifiee: e.target.value})} />
            </div>
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                <RefreshCw className="w-3.5 h-3.5 text-savia-accent" /> Récurrence
              </label>
              <select className={INPUT_CLS} value={form.recurrence}
                onChange={e => setForm({...form, recurrence: e.target.value})}>
                {RECURRENCES.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
          </div>

          {/* Techniciens assignés */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
              <User className="w-3.5 h-3.5 text-savia-accent" /> Techniciens assignés
            </label>
            {/* Chips for selected techs */}
            {form.technicien_assigne && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {form.technicien_assigne.split(', ').filter(Boolean).map(t => (
                  <span key={t} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-savia-accent/15 text-savia-accent border border-savia-accent/30">
                    {t}
                    <button type="button" onClick={() => {
                      const updated = form.technicien_assigne.split(', ').filter(x => x !== t).join(', ');
                      setForm({...form, technicien_assigne: updated});
                    }} className="hover:text-red-400 cursor-pointer ml-0.5"><X className="w-3 h-3" /></button>
                  </span>
                ))}
              </div>
            )}
            {/* Dropdown */}
            <div className="relative">
              <button type="button" onClick={() => setTechDropdownOpen(!techDropdownOpen)}
                className={INPUT_CLS + ' flex items-center justify-between cursor-pointer text-left'}>
                <span className={form.technicien_assigne ? 'text-savia-text' : 'text-savia-text-dim'}>
                  {form.technicien_assigne ? `${form.technicien_assigne.split(', ').length} technicien(s)` : '— Sélectionner —'}
                </span>
                <ChevronDown className={`w-4 h-4 transition-transform ${techDropdownOpen ? 'rotate-180' : ''}`} />
              </button>
              {techDropdownOpen && (
                <div className="absolute z-30 mt-1 w-full bg-savia-surface border border-savia-border rounded-lg shadow-xl max-h-48 overflow-y-auto">
                  {techsList.map(t => {
                    const selected = form.technicien_assigne.split(', ').filter(Boolean).includes(t);
                    return (
                      <button key={t} type="button" onClick={() => {
                        const current = form.technicien_assigne.split(', ').filter(Boolean);
                        const updated = selected ? current.filter(x => x !== t) : [...current, t];
                        setForm({...form, technicien_assigne: updated.join(', ')});
                      }}
                        className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:bg-savia-surface-hover transition-colors cursor-pointer ${
                          selected ? 'text-savia-accent font-semibold' : 'text-savia-text'
                        }`}>
                        <div className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
                          selected ? 'bg-savia-accent border-savia-accent' : 'border-savia-border'
                        }`}>
                          {selected && <Check className="w-3 h-3 text-white" />}
                        </div>
                        {t}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
              <FileText className="w-3.5 h-3.5 text-savia-accent" /> Description
            </label>
            <textarea className={INPUT_CLS + ' resize-none'} rows={3}
              placeholder="Détails de la maintenance à effectuer..."
              value={form.description} onChange={e => setForm({...form, description: e.target.value})} />
          </div>

          {/* Notes */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
              <StickyNote className="w-3.5 h-3.5 text-savia-accent" /> Notes internes
            </label>
            <textarea className={INPUT_CLS + ' resize-none'} rows={2}
              placeholder="Notes internes, remarques, matériel nécessaire..."
              value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} />
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-savia-border/50">
          <button onClick={() => { setShowAddModal(false); setSelectedDay(null); }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover cursor-pointer transition-colors">
            <X className="w-4 h-4" /> Annuler
          </button>
          <button onClick={handleSave} disabled={isSaving}
            className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 cursor-pointer transition-all">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Planifier
          </button>
        </div>
      </Modal>

      {/* ═══════════ DAY DETAIL POPUP ═══════════ */}
      {dayDetailDate && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 backdrop-blur-sm overflow-y-auto py-10 px-4" onClick={() => setDayDetailDate(null)}>
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-lg shadow-2xl animate-fade-in" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-savia-border">
              <h2 className="text-base font-black gradient-text flex items-center gap-2">
                <Calendar className="w-5 h-5 text-savia-accent" />
                Maintenances — {dayDetailDate}
              </h2>
              <div className="flex items-center gap-2">
                {canCreate && (
                <button
                  onClick={() => {
                    const day = Number(dayDetailDate!.split('-')[2]);
                    setDayDetailDate(null);
                    setSelectedDay(day);
                    setForm({...emptyForm, date_planifiee: dayDetailDate!});
                    setError('');
                    setShowAddModal(true);
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-savia-accent hover:opacity-90 cursor-pointer transition-all"
                >
                  <Plus className="w-3.5 h-3.5" /> Ajouter
                </button>
                )}
                <button onClick={() => setDayDetailDate(null)} className="p-1.5 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted cursor-pointer">
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Events */}
            <div className="px-6 py-4 space-y-3 max-h-[70vh] overflow-y-auto">
              {dayDetailEvents.map((ev, i) => {
                const automaticStatus = getAutomaticStatus(ev.date_planifiee, ev.statut, ev.notes);
                const colors = getStatutColor(automaticStatus, false);
                return (
                  <div key={i} className={`rounded-xl border border-savia-border border-l-4 p-4 space-y-2 bg-savia-surface-hover/40 ${colors.dot.replace('bg-', 'border-l-').replace('bg-savia', 'border-l-savia')}`}
                    style={{ borderLeftColor: colors.dot === 'bg-blue-400' ? '#60a5fa' : colors.dot === 'bg-yellow-400' ? '#facc15' : colors.dot === 'bg-green-400' ? '#4ade80' : '#f87171' }}>
                    {/* Machine + statut */}
                    <div className="flex items-start justify-between gap-2">
                      <span className="flex items-center gap-2 font-black text-sm text-savia-text">
                        <Server className="w-4 h-4 flex-shrink-0 text-savia-text-muted" /> {ev.machine}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold whitespace-nowrap ${colors.badge}`}>
                        {automaticStatus}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-savia-text">
                      {ev.client && (
                        <div className="flex items-center gap-1.5">
                          <Building2 className="w-3.5 h-3.5 text-savia-text-muted" />
                          <span className="text-savia-text-muted">Client :</span>
                          <span className="font-semibold text-savia-text">{ev.client}</span>
                        </div>
                      )}
                      {ev.technicien && (
                        <div className="flex items-center gap-1.5">
                          <User className="w-3.5 h-3.5 text-savia-text-muted" />
                          <span className="text-savia-text-muted">Tech :</span>
                          <span className="font-semibold text-savia-text">{ev.technicien}</span>
                        </div>
                      )}
                      <div className="flex items-center gap-1.5">
                        <Wrench className="w-3.5 h-3.5 text-savia-text-muted" />
                        <span className="text-savia-text-muted">Type :</span>
                        <span className="font-semibold text-savia-text">{ev.type_maintenance}</span>
                      </div>
                      {ev.recurrence && ev.recurrence !== 'Aucune' && (
                        <div className="flex items-center gap-1.5">
                          <RefreshCw className="w-3.5 h-3.5 text-savia-text-muted" />
                          <span className="text-savia-text-muted">Récurrence :</span>
                          <span className="font-semibold text-savia-text">{ev.recurrence}</span>
                        </div>
                      )}
                    </div>

                    {ev.description && (
                      <div className="flex items-start gap-1.5 text-xs pt-1 border-t border-savia-border">
                        <FileText className="w-3.5 h-3.5 text-savia-text-muted flex-shrink-0 mt-0.5" />
                        <p className="text-savia-text">{ev.description}</p>
                      </div>
                    )}
                    {ev.notes && (
                      <div className="flex items-start gap-1.5 text-xs">
                        <StickyNote className="w-3.5 h-3.5 text-savia-text-muted flex-shrink-0 mt-0.5" />
                        <p className="italic text-savia-text-muted">{ev.notes}</p>
                      </div>
                    )}
                    
                    {/* Action buttons for planning managers */}
                    {(((user?.role === 'Admin' || user?.role === 'Manager') && canReschedule(ev)) || (canCreate && !ev.contrat_id && !ev.is_ghost && !isHistoricalAnchor(ev))) && (
                      <div className="flex items-center gap-2 pt-2 border-t border-savia-border">
                        {(user?.role === 'Admin' || user?.role === 'Manager') && canReschedule(ev) && (
                          <button
                            onClick={() => handleOpenReschedule(ev)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-savia-accent bg-savia-accent/10 hover:bg-savia-accent/20 border border-savia-accent/30 transition-all cursor-pointer flex-1"
                          >
                            <RefreshCw className="w-3.5 h-3.5" /> Décaler et assigner
                          </button>
                        )}
                        {canCreate && !ev.contrat_id && !ev.is_ghost && !isHistoricalAnchor(ev) && (
                          <button
                            onClick={() => { setPlanningToDelete(ev); setDeletePlanningError(''); }}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-red-400 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 transition-all cursor-pointer"
                          >
                            <Trash2 className="w-3.5 h-3.5" /> Supprimer
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <Modal
        isOpen={!!planningToDelete}
        onClose={() => { if (!isDeletingPlanning) setPlanningToDelete(null); }}
        title="Confirmer la suppression"
      >
        {planningToDelete && (
          <div className="space-y-5">
            <div className="flex gap-3 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-800">
              <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-700" />
              <div>
                <p className="font-bold">Supprimer cette intervention du planning ?</p>
                <p className="mt-1 text-red-700">Cette action supprimera aussi les éventuelles interventions liées.</p>
              </div>
            </div>
            <div className="rounded-lg bg-savia-surface-hover/60 p-3 text-sm">
              <p className="font-semibold text-savia-text">{planningToDelete.machine}</p>
              <p className="mt-1 text-savia-text-muted">{planningToDelete.client || 'Client non renseigné'} · {planningToDelete.date_planifiee.substring(0, 10)}</p>
              {planningToDelete.recurrence && planningToDelete.recurrence !== 'Aucune' && (
                <p className="mt-2 text-amber-300">Récurrence {planningToDelete.recurrence} : toutes les occurrences associées à cet équipement seront supprimées.</p>
              )}
            </div>
            {deletePlanningError && <p className="text-sm text-red-400">{deletePlanningError}</p>}
            <div className="flex justify-end gap-3 border-t border-savia-border/50 pt-4">
              <button
                onClick={() => setPlanningToDelete(null)}
                disabled={isDeletingPlanning}
                className="rounded-lg border border-savia-border px-4 py-2 text-sm font-semibold text-savia-text-muted transition-colors hover:bg-savia-surface-hover disabled:opacity-50"
              >
                Annuler
              </button>
              <button
                onClick={handleDeletePlanning}
                disabled={isDeletingPlanning}
                className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-red-500 disabled:opacity-50"
              >
                {isDeletingPlanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                Supprimer définitivement
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* Reschedule Modal */}
      {showRescheduleModal && selectedIntervention && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={() => setShowRescheduleModal(false)}>
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-lg shadow-2xl animate-fade-in" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-savia-border">
              <h2 className="text-base font-black gradient-text flex items-center gap-2">
                <RefreshCw className="w-5 h-5 text-savia-accent" />
                Décaler l&apos;intervention
              </h2>
              <button onClick={() => setShowRescheduleModal(false)} className="p-1.5 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="px-6 py-4 space-y-4">
              {/* Current info */}
              <div className="bg-savia-surface-hover/50 rounded-lg p-3 space-y-2">
                <div className="text-xs font-semibold text-savia-text-muted uppercase tracking-wider">Intervention actuelle</div>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span className="text-savia-text-muted">Équipement :</span>
                    <p className="font-semibold text-savia-text">{selectedIntervention.machine}</p>
                  </div>
                  <div>
                    <span className="text-savia-text-muted">Client :</span>
                    <p className="font-semibold text-savia-text">{selectedIntervention.client}</p>
                  </div>
                  <div>
                    <span className="text-savia-text-muted">Date prévue :</span>
                    <p className="font-semibold text-savia-text">{selectedIntervention.date_planifiee}</p>
                  </div>
                  <div>
                    <span className="text-savia-text-muted">Technicien(s) :</span>
                    <p className="font-semibold text-savia-text text-xs">{selectedIntervention.technicien || '—'}</p>
                  </div>
                </div>
              </div>

              {/* Error message */}
              {rescheduleError && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-red-400 text-sm flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {rescheduleError}
                </div>
              )}

              {/* New date */}
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Calendar className="w-3.5 h-3.5 text-savia-accent" /> Nouvelle date prévue *
                </label>
                <input
                  type="date"
                  className={INPUT_CLS}
                  value={rescheduleForm.newDate}
                  onChange={e => setRescheduleForm({...rescheduleForm, newDate: e.target.value})}
                />
              </div>

              {/* New technicians */}
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <User className="w-3.5 h-3.5 text-savia-accent" /> Techniciens assignés
                </label>
                {/* Chips for selected techs */}
                {rescheduleForm.newTechs && (
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {rescheduleForm.newTechs.split(', ').filter(Boolean).map(t => (
                      <span key={t} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-savia-accent/15 text-savia-accent border border-savia-accent/30">
                        {t}
                        <button type="button" onClick={() => {
                          const updated = rescheduleForm.newTechs.split(', ').filter(x => x !== t).join(', ');
                          setRescheduleForm({...rescheduleForm, newTechs: updated});
                        }} className="hover:text-red-400 cursor-pointer ml-0.5"><X className="w-3 h-3" /></button>
                      </span>
                    ))}
                  </div>
                )}
                {/* Dropdown */}
                <div className="relative">
                  <button type="button" onClick={() => setRescheduleDropdownOpen(!rescheduleDropdownOpen)}
                    className={INPUT_CLS + ' flex items-center justify-between cursor-pointer text-left'}>
                    <span className={rescheduleForm.newTechs ? 'text-savia-text' : 'text-savia-text-dim'}>
                      {rescheduleForm.newTechs ? `${rescheduleForm.newTechs.split(', ').length} technicien(s)` : '— Sélectionner —'}
                    </span>
                    <ChevronDown className={`w-4 h-4 transition-transform ${rescheduleDropdownOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {rescheduleDropdownOpen && (
                    <div className="absolute z-30 mt-1 w-full bg-savia-surface border border-savia-border rounded-lg shadow-xl max-h-48 overflow-y-auto">
                      {techsList.map(t => {
                        const selected = rescheduleForm.newTechs.split(', ').filter(Boolean).includes(t);
                        return (
                          <button key={t} type="button" onClick={() => {
                            const current = rescheduleForm.newTechs.split(', ').filter(Boolean);
                            const updated = selected ? current.filter(x => x !== t) : [...current, t];
                            setRescheduleForm({...rescheduleForm, newTechs: updated.join(', ')});
                          }}
                            className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:bg-savia-surface-hover transition-colors cursor-pointer ${
                              selected ? 'text-savia-accent font-semibold' : 'text-savia-text'
                            }`}>
                            <div className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
                              selected ? 'bg-savia-accent border-savia-accent' : 'border-savia-border'
                            }`}>
                              {selected && <Check className="w-3 h-3 text-white" />}
                            </div>
                            {t}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* Raison du décalage */}
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <StickyNote className="w-3.5 h-3.5 text-savia-accent" /> Raison du décalage (optionnel)
                </label>
                <textarea
                  placeholder="Ex: Client indisponible, pièce non disponible, urgence prioritaire..."
                  className={INPUT_CLS + ' resize-none min-h-20 py-2'}
                  value={rescheduleForm.reason}
                  onChange={e => setRescheduleForm({...rescheduleForm, reason: e.target.value})}
                />
              </div>
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-savia-border/50">
              <button onClick={() => setShowRescheduleModal(false)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover cursor-pointer transition-colors">
                <X className="w-4 h-4" /> Annuler
              </button>
              <button onClick={handleReschedule} disabled={isRescheduling}
                className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 cursor-pointer transition-all">
                {isRescheduling ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                Décaler
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Comparateur Modal */}
      {showComparateurModal && selectedForComparateur && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={() => setShowComparateurModal(false)}>
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-2xl shadow-2xl animate-fade-in" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-savia-border/50">
              <h2 className="text-lg font-black gradient-text flex items-center gap-2">
                <BarChart3 className="w-5 h-5" /> Comparateur Planning
              </h2>
              <button onClick={() => setShowComparateurModal(false)} className="p-1.5 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="px-6 py-4 space-y-4 max-h-[60vh] overflow-y-auto">
              {isLoadingComparateur ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-savia-accent" />
                </div>
              ) : comparateurError ? (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
                  Erreur: {comparateurError}
                </div>
              ) : comparateurData && !comparateurData.has_ghost ? (
                <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 text-blue-400">
                  Aucun décalage trouvé pour cette intervention. Il n'y a pas de ghost entry.
                </div>
              ) : comparateurData ? (
                <>
                  {/* Summary */}
                  <div className="bg-savia-surface-hover rounded-lg p-4 border border-savia-border/30">
                    <div className="text-sm font-semibold text-savia-accent mb-2">Résumé</div>
                    <div className="text-sm text-savia-text">{getComparateurSummary(comparateurData)}</div>
                  </div>

                  {/* Equipment Info */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="text-xs font-semibold text-savia-text-muted mb-1">Machine</div>
                      <div className="text-sm text-savia-text">{comparateurData.machine}</div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-savia-text-muted mb-1">Client</div>
                      <div className="text-sm text-savia-text">{comparateurData.client}</div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-savia-text-muted mb-1">Type</div>
                      <div className="text-sm text-savia-text">{comparateurData.type_maintenance}</div>
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-savia-text-muted mb-1">Description</div>
                      <div className="text-sm text-savia-text truncate">{comparateurData.description}</div>
                    </div>
                  </div>

                  {/* Comparison */}
                  <div className="grid grid-cols-2 gap-3">
                    {/* Planning Réel */}
                    <div className="bg-green-500/5 border border-green-500/30 rounded-lg p-3">
                      <div className="text-xs font-semibold text-green-400 mb-2">Planning Réel (Nouvelle date)</div>
                      <div className="space-y-1.5 text-xs">
                        <div><span className="text-savia-text-muted">Date:</span> <span className="text-savia-text font-semibold">{comparateurData.real?.date}</span></div>
                        <div><span className="text-savia-text-muted">Technicien:</span> <span className="text-savia-text font-semibold">{comparateurData.real?.technicien || 'Non assigné'}</span></div>
                        <div><span className="text-savia-text-muted">Statut:</span> <span className="text-savia-text font-semibold">{comparateurData.real?.statut}</span></div>
                      </div>
                    </div>

                    {/* Planning Décalé */}
                    {comparateurData.ghost && (
                      <div className="bg-gray-500/5 border border-gray-500/30 rounded-lg p-3">
                        <div className="text-xs font-semibold text-gray-400 mb-2">Planning Décalé (Date originale)</div>
                        <div className="space-y-1.5 text-xs">
                          <div><span className="text-savia-text-muted">Date:</span> <span className="text-savia-text font-semibold">{comparateurData.ghost.date}</span></div>
                          <div><span className="text-savia-text-muted">Technicien:</span> <span className="text-savia-text font-semibold">{comparateurData.ghost.technicien || 'Non assigné'}</span></div>
                          <div><span className="text-savia-text-muted">Statut:</span> <span className="text-savia-text font-semibold">{comparateurData.ghost.statut}</span></div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Reasons */}
                  {comparateurData.reasons && comparateurData.reasons.length > 0 && (
                    <div className="bg-savia-surface-hover rounded-lg p-3 border border-savia-border/30">
                      <div className="text-xs font-semibold text-savia-accent mb-2">Raisons du décalage</div>
                      <div className="space-y-1 text-xs text-savia-text">
                        {comparateurData.reasons.map((reason: string, idx: number) => (
                          <div key={idx} className="flex gap-2">
                            <span className="text-savia-text-muted">{idx + 1}.</span>
                            <span>{reason}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : null}
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-savia-border/50">
              <button onClick={() => setShowComparateurModal(false)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover cursor-pointer transition-colors">
                <X className="w-4 h-4" /> Fermer
              </button>
              {comparateurData && (
                <>
                  <button onClick={() => handleExportComparateur('csv')} disabled={isLoadingComparateur}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-white bg-blue-600/40 hover:bg-blue-600/60 disabled:opacity-50 cursor-pointer transition-all">
                    <Download className="w-4 h-4" /> CSV
                  </button>
                  <button onClick={() => handleExportComparateur('json')} disabled={isLoadingComparateur}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-white bg-purple-600/40 hover:bg-purple-600/60 disabled:opacity-50 cursor-pointer transition-all">
                    <Download className="w-4 h-4" /> JSON
                  </button>
                  <button onClick={() => handleExportComparateur('pdf')} disabled={isLoadingComparateur}
                    className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 cursor-pointer transition-all">
                    <Download className="w-4 h-4" /> PDF
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Comparateur Période Modal */}
      {showComparateurPeriodeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={() => setShowComparateurPeriodeModal(false)}>
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-4xl shadow-2xl animate-fade-in max-h-[90vh] overflow-auto" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-savia-border sticky top-0 bg-savia-surface">
              <h2 className="text-lg font-black gradient-text flex items-center gap-2">
                <BarChart3 className="w-5 h-5" /> Comparateur Périod</h2>
              <button onClick={() => setShowComparateurPeriodeModal(false)} className="p-1.5 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="px-6 py-6 space-y-4">
              {/* Date Selection */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-semibold text-savia-text-muted mb-2 block">Date début</label>
                  <input type="date" value={comparateurPeriodeForm.dateDebut} onChange={e => setComparateurPeriodeForm({...comparateurPeriodeForm, dateDebut: e.target.value})} 
                    className="w-full bg-savia-surface-hover border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-savia-text-muted mb-2 block">Date fin</label>
                  <input type="date" value={comparateurPeriodeForm.dateFin} onChange={e => setComparateurPeriodeForm({...comparateurPeriodeForm, dateFin: e.target.value})}
                    className="w-full bg-savia-surface-hover border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all" />
                </div>
              </div>

              {/* Search Button */}
              <button onClick={handleFetchComparateurPeriode} disabled={isLoadingComparateurPeriode}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer">
                {isLoadingComparateurPeriode ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />}
                {isLoadingComparateurPeriode ? 'Chargement...' : 'Charger les comparaisons'}
              </button>

              {/* Error */}
              {comparateurPeriodeError && (
                <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400 text-sm">
                  {comparateurPeriodeError}
                </div>
              )}

              {/* Results Table */}
              {comparateurPeriodeData && comparateurPeriodeData.comparisons && comparateurPeriodeData.comparisons.length > 0 ? (
                <div className="overflow-x-auto">
                  <div className="text-sm font-semibold text-savia-text-muted mb-3">
                    {comparateurPeriodeData.total} décalage(s) trouvé(s)
                  </div>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-savia-border">
                        <th className="text-left px-3 py-2 font-semibold text-savia-accent">Machine</th>
                        <th className="text-left px-3 py-2 font-semibold text-savia-accent">Client</th>
                        <th className="text-left px-3 py-2 font-semibold text-savia-accent">Type</th>
                        <th className="text-left px-3 py-2 font-semibold text-savia-accent">Date Original</th>
                        <th className="text-left px-3 py-2 font-semibold text-savia-accent">Date Décalée</th>
                        <th className="text-center px-3 py-2 font-semibold text-savia-accent">Décalage (j)</th>
                        <th className="text-left px-3 py-2 font-semibold text-savia-accent">Raisons</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparateurPeriodeData.comparisons.map((c: any, idx: number) => (
                        <tr key={idx} className="border-b border-savia-border/30 hover:bg-savia-surface-hover/30">
                          <td className="px-3 py-2 text-savia-text">{c.machine}</td>
                          <td className="px-3 py-2 text-savia-text-muted">{c.client}</td>
                          <td className="px-3 py-2 text-savia-text-muted text-xs">{c.type_maintenance}</td>
                          <td className="px-3 py-2 text-savia-text">{c.old_date}</td>
                          <td className="px-3 py-2 text-savia-text">{c.new_date}</td>
                          <td className="px-3 py-2 text-center font-semibold" style={{color: c.days_difference > 0 ? '#ef4444' : '#10b981'}}>
                            {c.days_difference > 0 ? `+${c.days_difference}` : c.days_difference}
                          </td>
                          <td className="px-3 py-2 text-savia-text-muted text-xs max-w-xs truncate">{c.reasons.join('; ') || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : comparateurPeriodeData && comparateurPeriodeData.comparisons?.length === 0 ? (
                <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 text-blue-400 text-sm text-center">
                  Aucun décalage trouvé pour cette période
                </div>
              ) : null}
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-savia-border/50 sticky bottom-0 bg-savia-surface">
              <button onClick={() => setShowComparateurPeriodeModal(false)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border border-savia-border text-savia-text-muted hover:bg-savia-surface-hover cursor-pointer transition-colors">
                <X className="w-4 h-4" /> Fermer
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
