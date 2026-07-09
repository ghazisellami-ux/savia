'use client';
// ==========================================
// 📊 Dashboard Page — SAVIA
// With client + period (monthly/annual) filters
// ==========================================
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useCanSeeCosts } from '@/lib/use-role-guard';
import { useDashboardFilters } from '@/lib/use-dashboard-filters';
import { KpiCard, HealthBadge, SectionCard } from '@/components/ui/cards';
import {
  XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
  AreaChart, Area, PieChart, Pie, Cell,
} from 'recharts';
import dynamic from 'next/dynamic';
const ApexChart = dynamic(() => import('react-apexcharts'), { ssr: false });
import { dashboard, interventions as interventionsApi, clients as clientsApi, equipements } from '@/lib/api';
import { Loader2, AlertTriangle, ChevronDown, ChevronUp, Clock, Building2, Calendar, Filter, Activity, Heart, Target, TrendingUp, Trophy, Cpu, CircleAlert, CircleCheck, Timer, Wrench, DollarSign, BarChart3, Crosshair, User, Satellite, MapPin, Server } from 'lucide-react';

// --- Types ---
interface KpiData {
  nb_equipements: number;
  nb_critiques: number;
  disponibilite: number;
  mtbf: number;
  mttr: number;
  cout_total: number;
  nb_interventions: number;
  nb_clients: number;
  taux_resolution: number;
}

interface HealthScore {
  machine: string;
  score: number;
  tendance: string;
  pannes: number;
  client?: string;
}

// --- Chart theme ---
const CHART_STYLE = {
  bg: '#1e293b',
  grid: '#334155',
  text: '#94a3b8',
  accent: '#2dd4bf',
  blue: '#3b82f6',
};

const MONTH_NAMES = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];
const MONTH_ABBR = {
  fr: ['Jan', 'Fev', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Aou', 'Sep', 'Oct', 'Nov', 'Dec'],
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
} as const;
type UiLang = keyof typeof MONTH_ABBR;

function getUiLang(): UiLang {
  if (typeof window === 'undefined') return 'fr';
  return localStorage.getItem('savia_lang') === 'en' ? 'en' : 'fr';
}

// Color palette for error types
const ERROR_TYPE_COLORS: Record<string, string> = {
  'Hardware': '#ef4444',
  'Software': '#3b82f6',
  'Calibration': '#f59e0b',
  'Power': '#8b5cf6',
  'Électrique': '#fbbf24',
  'Mécanique': '#ec4899',
  'Pneumatique': '#06b6d4',
  'Hydraulique': '#8b5cf6',
  'Autre': '#64748b',
};

// --- Helpers ---
function getDateRange(mode: 'mensuel' | 'annuel', month: number, year: number) {
  if (mode === 'mensuel') {
    // Use string formatting to avoid timezone issues with Date objects
    const monthStr = String(month).padStart(2, '0');
    const date_start = `${year}-${monthStr}-01`;
    
    // Calculate last day of month without timezone conversion
    const lastDay = new Date(year, month, 0).getDate();
    const date_end = `${year}-${monthStr}-${String(lastDay).padStart(2, '0')}`;
    
    return {
      date_start,
      date_end,
      label: `${monthStr}/${year}`,
      rangeLabel: `01/${monthStr}/${year} → ${String(lastDay).padStart(2, '0')}/${monthStr}/${year} (${lastDay}j)`,
    };
  } else {
    return {
      date_start: `${year}-01-01`,
      date_end: `${year}-12-31`,
      label: `${year}`,
      rangeLabel: `01/01/${year} → 31/12/${year} (365j)`,
    };
  }
}

function getLast6Months(month: number, year: number, lang: UiLang) {
  const months = [];
  for (let i = 5; i >= 0; i--) {
    let m = month - i;
    let y = year;
    while (m <= 0) { m += 12; y--; }
    months.push({ mois: MONTH_ABBR[lang][m - 1], month: m, year: y });
  }
  return months;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { filterOptions, isLoadingFilters, getEquipmentTypesForFilters } = useDashboardFilters();

  // --- Filter state ---
  const now = new Date();
  const isLecteur = user?.role === 'Lecteur';
  const canSeeCosts = useCanSeeCosts();
  const [selectedClient, setSelectedClient] = useState(user?.role === 'Lecteur' ? (user?.client || '') : '');
  const [selectedEquipType, setSelectedEquipType] = useState('');
  const [periodMode, setPeriodMode] = useState<'mensuel' | 'annuel'>('annuel');
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1);
  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [uiLang, setUiLang] = useState<UiLang>(() => getUiLang());

  // --- Dynamic equipment types for current client ---
  const [equipmentTypesForFilters, setEquipmentTypesForFilters] = useState<string[]>([]);

  // --- Data state ---
  const [kpis, setKpis] = useState<KpiData>({
    nb_equipements: 0, nb_critiques: 0, disponibilite: 100, mtbf: 0, mttr: 0, cout_total: 0, nb_interventions: 0, nb_clients: 0, taux_resolution: 0
  });
  const [healthScores, setHealthScores] = useState<HealthScore[]>([]);
  const [allInterventions, setAllInterventions] = useState<any[]>([]);
  const [recentInterv, setRecentInterv] = useState<any[]>([]);
  const [showAnomalies, setShowAnomalies] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [trendData, setTrendData] = useState<any[]>([]);

  useEffect(() => {
    const syncLang = () => setUiLang(getUiLang());
    window.addEventListener('savia_language_changed', syncLang);
    window.addEventListener('storage', syncLang);
    return () => {
      window.removeEventListener('savia_language_changed', syncLang);
      window.removeEventListener('storage', syncLang);
    };
  }, []);

  // --- Charger les types d'équipement filtrés quand le client change ---
  useEffect(() => {
    getEquipmentTypesForFilters(selectedClient, undefined, undefined).then(types => {
      setEquipmentTypesForFilters(types);
      // Reset selectedEquipType si le type sélectionné n'est plus disponible
      if (selectedEquipType && !types.includes(selectedEquipType)) {
        setSelectedEquipType('');
      }
    });
  }, [selectedClient, getEquipmentTypesForFilters]);

  // --- Computed date range ---
  const dateRange = useMemo(() => getDateRange(periodMode, selectedMonth, selectedYear), [periodMode, selectedMonth, selectedYear]);

  // --- Cache for full unfiltered data (loaded once per date range) ---
  const [fullData, setFullData] = useState<{
    kpis: any;
    healthScores: any;
    interventions: any;
  } | null>(null);
  const [isInitialLoading, setIsInitialLoading] = useState(true);

  // --- Load cached KPI data on mount ---
  useEffect(() => {
    // Note: Cache is removed to ensure fresh data when date range changes
    // This was causing stale data to be displayed when switching months/years
    setIsInitialLoading(false);
  }, []);

  // --- Load full unfiltered data once when date range changes ---
  useEffect(() => {
    // Clear cache when date range changes to force fresh data
    localStorage.removeItem('dashboard_kpi_cache');
    
    const loadFullData = async () => {
      setIsInitialLoading(true);
      
      try {
        // ALWAYS load with date range parameters, even without filters
        const [kpiData, healthData] = await Promise.all([
          dashboard.kpis({ date_start: dateRange.date_start, date_end: dateRange.date_end }),
          dashboard.healthScores({ date_start: dateRange.date_start, date_end: dateRange.date_end }),
        ]);
        
        const newData = {
          kpis: kpiData,
          healthScores: healthData,
          interventions: [],
        };
        
        // Set data immediately with empty interventions
        setFullData(newData);
        setIsInitialLoading(false);
        
        // Load interventions in background (can be slow)
        try {
          const intervData = await interventionsApi.list();
          setFullData(prev => prev ? {
            ...prev,
            interventions: intervData || [],
          } : null);
        } catch (err) {
          console.error("Failed to load interventions", err);
        }
      } catch (err) {
        console.error("Failed to load KPIs and health scores", err);
        setIsInitialLoading(false);
      }
    };
    loadFullData();
  }, [dateRange.date_start, dateRange.date_end, dashboard, interventionsApi]);

  // --- Filter cached data when filters change (instant update) ---
  useEffect(() => {
    if (!fullData) return;

    // If only client filter is applied, filter client-side (instant)
    if (selectedClient && !selectedEquipType) {
      setIsLoading(true);
      try {
        // Filter health scores by client
        const filteredHealth = fullData.healthScores.filter((h: any) => h.client === selectedClient);

        // Filter interventions by client machines
        const validMachines = filteredHealth.map((h: any) => h.machine);
        let filteredInterv = fullData.interventions;
        if (validMachines.length > 0) {
          filteredInterv = filteredInterv.filter((i: any) => validMachines.includes(i.machine));
        } else {
          filteredInterv = [];
        }

        const dateFilteredInterv = filteredInterv.filter((i: any) => {
          const dateToCheck = i.date ? i.date.substring(0, 10) : '';
          return dateToCheck >= dateRange.date_start && dateToCheck <= dateRange.date_end;
        });

        const activityAvailability = (() => {
          const start = new Date(`${dateRange.date_start}T00:00:00`);
          const end = new Date(`${dateRange.date_end}T00:00:00`);
          if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 100;

          const monthlyValues: number[] = [];
          const cursor = new Date(start.getFullYear(), start.getMonth(), 1);
          const endMonth = new Date(end.getFullYear(), end.getMonth(), 1);

          while (cursor <= endMonth) {
            const monthKey = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}`;
            const monthInterv = dateFilteredInterv.filter((i: any) => (i.date || '').substring(0, 7) === monthKey);
            const unfinished = monthInterv.filter((i: any) => String(i.statut || '').toLowerCase() !== 'terminée').length;
            monthlyValues.push(Math.max(0, 100 - unfinished * 2));
            cursor.setMonth(cursor.getMonth() + 1);
          }

          return monthlyValues.length > 0
            ? Math.round((monthlyValues.reduce((a, b) => a + b, 0) / monthlyValues.length) * 10) / 10
            : 100;
        })();

        // Compute ALL KPIs from filtered data
        const nb_eq = filteredHealth.length;
        const nb_critiques = filteredHealth.filter((h: any) => h.score < 30).length;
        const statusAvailability = nb_eq > 0 ? Math.round(((nb_eq - nb_critiques) / nb_eq) * 100) : 100;
        const disponibilite = Math.min(statusAvailability, activityAvailability);
        const nb_interventions = dateFilteredInterv.length;
        const nb_cloturees = dateFilteredInterv.filter((i: any) => (i.statut || '').toLowerCase().includes('clotur')).length;
        const taux_resolution = nb_interventions > 0 ? Math.round((nb_cloturees / nb_interventions) * 100) : 0;

        // Calculate MTBF and MTTR from filtered interventions
        let mtbf = 0, mttr = 0;
        if (dateFilteredInterv.length > 0) {
          const durations = dateFilteredInterv
            .filter((i: any) => i.duree_intervention)
            .map((i: any) => parseFloat(i.duree_intervention) || 0);
          if (durations.length > 0) {
            mttr = durations.reduce((a: number, b: number) => a + b, 0) / durations.length;
          }
          // MTBF = average time between failures (simplified: total days / number of interventions)
          if (dateFilteredInterv.length > 1) {
            const dates = dateFilteredInterv
              .map((i: any) => new Date(i.date).getTime())
              .sort((a: number, b: number) => a - b);
            const daysBetween = [];
            for (let i = 1; i < dates.length; i++) {
              daysBetween.push((dates[i] - dates[i - 1]) / (1000 * 60 * 60 * 24));
            }
            if (daysBetween.length > 0) {
              mtbf = daysBetween.reduce((a: number, b: number) => a + b, 0) / daysBetween.length * 24; // convert to hours
            }
          }
        }

        setKpis({
          nb_equipements: nb_eq,
          nb_critiques: nb_critiques,
          disponibilite: disponibilite,
          mtbf: mtbf,
          mttr: mttr,
          cout_total: 0, // Can't calculate from client-side data
          nb_interventions: nb_interventions,
          nb_clients: 1, // Only 1 client selected
          taux_resolution: taux_resolution,
        });
        setHealthScores(filteredHealth);
        setAllInterventions(filteredInterv);

        setRecentInterv(
          dateFilteredInterv.sort((a: any, b: any) => (b.date || '').localeCompare(a.date || '')).slice(0, 10)
        );
      } catch (err) {
        console.error("Failed to filter data", err);
      } finally {
        setIsLoading(false);
      }
      return;
    }

    // If no filters or equipment type filter, use full data or call API
    if (!selectedClient && !selectedEquipType) {
      // No filters - use full data but filter by date range
      setIsLoading(true);
      try {
        setKpis(fullData.kpis);
        setHealthScores(fullData.healthScores);
        setAllInterventions(fullData.interventions);
        
        // Filter interventions by date range for display
        const dateFilteredInterv = fullData.interventions.filter((i: any) => {
          const dateToCheck = i.date ? i.date.substring(0, 10) : '';
          return dateToCheck >= dateRange.date_start && dateToCheck <= dateRange.date_end;
        });
        
        setRecentInterv(
          dateFilteredInterv.sort((a: any, b: any) => (b.date || '').localeCompare(a.date || '')).slice(0, 10)
        );
      } finally {
        setIsLoading(false);
      }
      return;
    }

    // Equipment type filter - call API
    setIsLoading(true);
    const loadFilteredData = async () => {
      try {
        const params: any = {
          date_start: dateRange.date_start,
          date_end: dateRange.date_end,
        };
        if (selectedClient) params.client = selectedClient;
        if (selectedEquipType) params.equipment_type = selectedEquipType;

        const [kpiData, healthData, intervData] = await Promise.all([
          dashboard.kpis(params),
          dashboard.healthScores(params),
          interventionsApi.list(),
        ]);

        setKpis(kpiData as any);
        setHealthScores(healthData);
        setAllInterventions(intervData || []);

        // Filter interventions for timeline display by date range AND by machines
        let filtered = (intervData || []);
        const validMachines = healthData.map((h: any) => h.machine);

        if (validMachines.length > 0) {
          filtered = filtered.filter((i: any) => validMachines.includes(i.machine));
        } else {
          filtered = [];
        }
        
        // Filter by date range
        filtered = filtered.filter((i: any) => {
          const dateToCheck = i.date ? i.date.substring(0, 10) : '';
          return dateToCheck >= dateRange.date_start && dateToCheck <= dateRange.date_end;
        });

        setRecentInterv(
          filtered.sort((a: any, b: any) => (b.date || '').localeCompare(a.date || '')).slice(0, 10)
        );
      } catch (err) {
        console.error("Failed to load filtered data", err);
      } finally {
        setIsLoading(false);
      }
    };
    loadFilteredData();
  }, [selectedClient, selectedEquipType, fullData, dateRange, dashboard, interventionsApi]);

  // --- Load availability trend data ---
  useEffect(() => {
    const loadTrendData = async () => {
      try {
        const params: any = {};
        if (selectedClient) params.client = selectedClient;
        if (selectedEquipType) params.equipment_type = selectedEquipType;
        
        const response = await fetch(`/api/dashboard/availability-trend?${new URLSearchParams(params).toString()}`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('savia_token') || ''}`,
          },
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data.trend) {
            setTrendData(data.trend);
          }
        }
      } catch (err) {
        console.error("Failed to load trend data", err);
      }
    };
    
    loadTrendData();
  }, [selectedClient, selectedEquipType]);

  // --- Computed values ---
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

  // Monthly bar chart data — compute from real interventions
  const monthlyChartData = useMemo(() => {
    const months = getLast6Months(selectedMonth, selectedYear, uiLang);
    return months.map(m => {
      const filtered = allInterventions.filter((i: any) => {
        const d = new Date(i.date);
        return d.getMonth() + 1 === m.month && d.getFullYear() === m.year;
      });
      return {
        mois: m.mois,
        corrective: filtered.filter((i: any) => (i.type_intervention || '').toLowerCase().includes('correct')).length,
        preventive: filtered.filter((i: any) => (i.type_intervention || '').toLowerCase().includes('prevent') || (i.type_intervention || '').toLowerCase().includes('prévent')).length,
      };
    });
  }, [allInterventions, selectedMonth, selectedYear, uiLang]);

  // Compute error types distribution from real interventions
  const errorTypesData = useMemo(() => {
    if (!allInterventions || allInterventions.length === 0) {
      // Return empty array if no interventions
      return [];
    }

    // Count error types from interventions
    const errorTypeCount: Record<string, number> = {};
    let totalWithErrorType = 0;

    allInterventions.forEach((interv: any) => {
      // Check if intervention is within date range
      // Use date_cloture for closed interventions, date for others
      const dateToCheck = (interv.statut || '').toLowerCase().includes('clotur') 
        ? (interv.date_cloture || interv.date)
        : interv.date;
      
      if (dateToCheck) {
        const d = dateToCheck.substring(0, 10);
        if (d < dateRange.date_start || d > dateRange.date_end) {
          return; // Skip if outside date range
        }
      }

      // Get error type from type_erreur field
      const errorType = (interv.type_erreur || '').trim();
      if (errorType) {
        errorTypeCount[errorType] = (errorTypeCount[errorType] || 0) + 1;
        totalWithErrorType++;
      }
    });

    // If no error types found, return empty
    if (totalWithErrorType === 0) {
      return [];
    }

    // Convert to percentage and create chart data
    return Object.entries(errorTypeCount)
      .map(([name, count]) => ({
        name,
        value: Math.round((count / totalWithErrorType) * 100),
        color: ERROR_TYPE_COLORS[name] || '#64748b',
      }))
      .sort((a, b) => b.value - a.value); // Sort by percentage descending
  }, [allInterventions, dateRange]);

  // Gauge data for RadialBarChart
  const gaugeData = [{ name: 'Santé', value: scoreGlobal, fill: scoreGlobal >= 60 ? '#2dd4bf' : scoreGlobal >= 30 ? '#f59e0b' : '#ef4444' }];

  // Available years
  const yearOptions = Array.from({ length: 5 }, (_, i) => now.getFullYear() - 2 + i);

  if (isLoadingFilters) {
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

      {/* ===== FILTER BAR ===== */}
      <div className={`glass rounded-xl p-4 space-y-4 transition-opacity duration-300 ${isLoading ? 'opacity-60' : 'opacity-100'}`}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 items-end">
          {/* Client Filter — masqué pour Lecteur (données auto-filtrées) */}
          {!isLecteur && (
            <div>
              <label className="flex items-center gap-2 text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
                <Building2 className="w-3.5 h-3.5" /> Client
              </label>
              <select
                value={selectedClient}
                onChange={e => setSelectedClient(e.target.value)}
                className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 outline-none"
              >
                <option value="">Tous les clients</option>
                {filterOptions.clients.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}

          {/* Equipment Type Filter */}
          <div>
            <label className="flex items-center gap-2 text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
              <Server className="w-3.5 h-3.5" /> Type Équip.
            </label>
            <select
              value={selectedEquipType}
              onChange={e => setSelectedEquipType(e.target.value)}
              className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 outline-none"
            >
              <option value="">Tous les types</option>
              {equipmentTypesForFilters && equipmentTypesForFilters.length > 0 ? (
                equipmentTypesForFilters.map(t => <option key={t} value={t}>{t}</option>)
              ) : (
                <option disabled>Aucun type disponible</option>
              )}
            </select>
          </div>

          {/* Period Mode Toggle */}
          <div>
            <label className="flex items-center gap-2 text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
              <Calendar className="w-3.5 h-3.5" /> Période
            </label>
            <div className="flex rounded-lg overflow-hidden border border-savia-border">
              <button
                onClick={() => setPeriodMode('mensuel')}
                className={`flex-1 py-2.5 text-sm font-bold transition-all cursor-pointer ${
                  periodMode === 'mensuel'
                    ? 'bg-savia-accent text-white shadow-inner'
                    : 'bg-savia-bg/50 text-savia-text-muted hover:bg-savia-surface-hover/30'
                }`}
              >
                📅 Mensuel
              </button>
              <button
                onClick={() => setPeriodMode('annuel')}
                className={`flex-1 py-2.5 text-sm font-bold transition-all cursor-pointer ${
                  periodMode === 'annuel'
                    ? 'bg-savia-accent-blue text-white shadow-inner'
                    : 'bg-savia-bg/50 text-savia-text-muted hover:bg-savia-surface-hover/30'
                }`}
              >
                📆 Annuel
              </button>
            </div>
          </div>

          {/* Month Selector (only visible in mensuel mode) */}
          {periodMode === 'mensuel' && (
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
                Mois
              </label>
              <select
                value={selectedMonth}
                onChange={e => setSelectedMonth(Number(e.target.value))}
                className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 outline-none"
              >
                {MONTH_NAMES.map((name, i) => (
                  <option key={i + 1} value={i + 1}>{i + 1} — {name}</option>
                ))}
              </select>
            </div>
          )}

          {/* Year Selector */}
          <div>
            <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
              Année
            </label>
            <select
              value={selectedYear}
              onChange={e => setSelectedYear(Number(e.target.value))}
              className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 outline-none"
            >
              {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
        </div>

        {/* Period Summary */}
        <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-savia-accent/5 border border-savia-accent/20 flex-wrap">
          <Filter className="w-4 h-4 text-savia-accent" />
          {isLoading && <Loader2 className="w-3 h-3 animate-spin text-savia-accent" />}
          <span className="text-sm font-semibold text-savia-accent">
            Période : {dateRange.label}
          </span>
          <span className="text-xs text-savia-text-muted">
            | {dateRange.rangeLabel}
          </span>
          {selectedClient && (
            <span className="ml-2 px-2 py-0.5 rounded-full text-xs font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
              Client: {selectedClient}
            </span>
          )}
          {selectedEquipType && (
            <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-orange-500/10 text-orange-400 border border-orange-500/20">
              Type: {selectedEquipType}
            </span>
          )}
        </div>
      </div>

      {/* KPIs Row - Top 4 */}
      <div className={`grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-4 transition-opacity duration-300 ${isLoading ? 'opacity-60' : 'opacity-100'}`}>
        <KpiCard icon={<Building2 className="w-6 h-6 text-purple-400" />} value={String(kpis.nb_clients)} label="Clients" />
        <KpiCard icon={<Cpu className="w-6 h-6 text-savia-accent" />} value={String(kpis.nb_equipements)} label="Équipements" />
        <KpiCard icon={<CircleAlert className="w-6 h-6 text-red-400" />} value={String(healthScores.filter(h => h.score < 40).length)} label="Alertes Critiques" variant={kpis.nb_critiques > 0 ? 'danger' : 'default'} />
        <KpiCard icon={<CircleCheck className="w-6 h-6 text-green-400" />} value={`${kpis.disponibilite}%`} label="Disponibilité" variant="success" />
      </div>

      {/* KPIs Row - Bottom 4 */}
      <div className={`grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-4 transition-opacity duration-300 ${isLoading ? 'opacity-60' : 'opacity-100'}`}>
        <KpiCard icon={<Wrench className="w-6 h-6 text-orange-400" />} value={String(kpis.nb_interventions)} label="Interventions" />
        <KpiCard icon={<Target className="w-6 h-6 text-emerald-400" />} value={`${kpis.taux_resolution}%`} label="Taux Résolution" variant={kpis.taux_resolution >= 80 ? 'success' : kpis.taux_resolution >= 60 ? 'default' : 'danger'} tooltip="% interventions clôturées" />
        <KpiCard icon={<Timer className="w-6 h-6 text-blue-400" />} value={mtbfStr} label="MTBF" tooltip="Temps moyen entre pannes" />
        {canSeeCosts && (
          <KpiCard icon={<DollarSign className="w-6 h-6 text-yellow-400" />} value={`${kpis.cout_total.toLocaleString('fr')} TND`} label="Coût Maintenance" />
        )}
        {!canSeeCosts && (
          <KpiCard icon={<Wrench className="w-6 h-6 text-orange-400" />} value={`${kpis.mttr.toFixed(1)}h`} label="MTTR" tooltip="Temps moyen de réparation" />
        )}
      </div>

      {/* Score Santé + Gamification */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Score Santé du Jour */}
        <SectionCard title={<span className="flex items-center gap-2"><Activity className="w-5 h-5 text-savia-accent" /> Score Santé du Jour</span>}>
          <div className="text-center">
            <div className={`text-5xl font-black ${scoreGlobal >= 60 ? 'text-savia-success' : scoreGlobal >= 30 ? 'text-savia-warning' : 'text-savia-danger'}`}>
              {scoreGlobal}%
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
        <SectionCard title={<span className="flex items-center gap-2"><Trophy className="w-5 h-5 text-yellow-400" /> Gamification — Équipe</span>}>
          <div className="text-center">
            <div className="text-5xl font-black text-savia-warning">
              {kpis.nb_interventions} <span className="text-lg">interventions</span>
            </div>
            <div className="text-savia-warning text-sm font-semibold mt-2">
              ■ Niveau : Pro
            </div>
            <div className="text-savia-text-dim text-xs mt-1">
              Total réalisé: {kpis.nb_interventions} | Belle performance !
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
              <span className="font-bold text-red-400">{healthScores.filter(h => h.score < 40).length} anomalie(s) détectée(s)</span>
            </div>
            {showAnomalies ? <ChevronUp className="w-4 h-4 text-savia-text-muted" /> : <ChevronDown className="w-4 h-4 text-savia-text-muted" />}
          </button>
          {showAnomalies && (
            <div className="px-4 pb-4 space-y-2">
              {healthScores.filter(h => h.score < 40).map(h => (
                <div key={`${h.machine}-${h.client || ""}`} className="flex items-center justify-between p-3 rounded-lg bg-red-500/5 border-l-4 border-red-500">
                  <div>
                    <span className="font-bold text-sm">{h.machine}</span>
                    {h.client && <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-500/10 text-blue-400">{h.client}</span>}
                    <span className="text-xs text-savia-text-muted ml-2">Score: {h.score}% — {h.pannes} pannes</span>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-xs font-bold bg-red-500/20 text-red-400">
                    {h.score < 15 ? 'Critique' : 'Dégradé'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 📅 Timeline des Interventions Récentes */}
      <SectionCard title={<span className="flex items-center gap-2"><Clock className="w-5 h-5 text-blue-400" /> Interventions Récentes — {dateRange.label}</span>}>
        {recentInterv.length === 0 ? (
          <div className="text-center text-savia-text-muted py-4">Aucune intervention sur cette période</div>
        ) : (
          <div className="relative pl-6 max-h-[320px] overflow-y-auto">
            <div className="absolute left-3 top-0 bottom-0 w-0.5 bg-gradient-to-b from-savia-accent via-blue-500 to-purple-500" />
            {recentInterv.map((interv: any, i: number) => {
              const isCompleted = (interv.statut || '').toLowerCase().includes('tur');
              return (
                <div key={interv.id || i} className="relative mb-4 ml-4">
                  <div className={`absolute -left-[22px] top-1 w-3 h-3 rounded-full border-2 ${isCompleted ? 'bg-green-400 border-green-300' : 'bg-yellow-400 border-yellow-300'}`} />
                  <div className="glass rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-bold text-sm">{interv.machine}</span>
                      <span className="text-xs text-savia-text-muted">{(interv.date || '').substring(0, 10)}</span>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${(interv.type_intervention || '').toLowerCase().includes('correct') ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}>{interv.type_intervention}</span>
                      <span className="text-xs text-savia-text-muted flex items-center gap-1"><User className="w-3 h-3" /> {interv.technicien || 'N/A'}</span>
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
        <div className="w-12 h-12 flex-shrink-0 rounded-xl bg-gradient-to-br from-savia-accent/20 to-savia-success/20 flex items-center justify-center">
          <Activity className="w-6 h-6 text-savia-accent" />
        </div>
        <div>
          <div className="text-lg font-extrabold gradient-text flex items-center gap-2"><Heart className="w-5 h-5 text-red-400" /> Santé du Parc d&apos;Équipements</div>
          <div className="text-savia-text-muted text-sm flex items-center gap-1"><Satellite className="w-3.5 h-3.5" /> Monitoring en temps réel — Analyse prédictive active</div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Interventions par mois */}
        <SectionCard title={<span className="flex items-center gap-2"><BarChart3 className="w-5 h-5 text-savia-accent" /> Interventions / Mois</span>} className="lg:col-span-2">
          <ApexChart
            type="bar"
            height={280}
            series={[
              { name: 'Corrective', data: monthlyChartData.map((d: any) => d.corrective) },
              { name: uiLang === 'en' ? 'Preventive' : 'Préventive', data: monthlyChartData.map((d: any) => d.preventive) },
            ]}
            options={{
              chart: {
                toolbar: { show: false },
                fontFamily: 'Inter, sans-serif',
                background: 'transparent',
                animations: { enabled: true, speed: 600 },
              },
              plotOptions: {
                bar: { borderRadius: 5, columnWidth: '55%', borderRadiusApplication: 'end' },
              },
              colors: ['#ef4444', '#2dd4bf'],
              dataLabels: { enabled: false },
              xaxis: {
                categories: monthlyChartData.map((d: any) => d.mois),
                labels: { style: { colors: '#64748b', fontSize: '12px' } },
                axisBorder: { show: false },
                axisTicks: { show: false },
              },
              yaxis: {
                labels: { style: { colors: '#64748b', fontSize: '12px' } },
              },
              grid: {
                borderColor: 'rgba(45,212,191,0.08)',
                strokeDashArray: 3,
                xaxis: { lines: { show: false } },
              },
              tooltip: {
                theme: 'dark',
                style: { fontSize: '12px' },
              },
              legend: {
                labels: { colors: '#94a3b8' },
                fontSize: '12px',
                markers: { size: 6, shape: 'circle' as const },
              },
              theme: { mode: 'dark' },
            }}
          />
        </SectionCard>

        {/* Répartition types erreurs */}
        <SectionCard title={<span className="flex items-center gap-2"><Crosshair className="w-5 h-5 text-purple-400" /> Types d&apos;Erreurs</span>}>
          {errorTypesData.length === 0 ? (
            <div className="flex items-center justify-center h-[280px] text-savia-text-muted">
              <div className="text-center">
                <Crosshair className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">Aucun type d&apos;erreur enregistré</p>
              </div>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <PieChart>
                <Pie
                  data={errorTypesData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={90}
                  paddingAngle={3}
                  dataKey="value"
                  stroke="none"
                >
                  {errorTypesData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: CHART_STYLE.bg, border: `1px solid ${CHART_STYLE.grid}`, borderRadius: 8, color: '#f1f5f9' }}
                  formatter={(value: any) => `${value}%`}
                />
                <Legend
                  wrapperStyle={{ fontSize: 11, color: CHART_STYLE.text }}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </SectionCard>
      </div>

      {/* Health Scores Table + Gauge */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Table Santé */}
        <SectionCard title={<span className="flex items-center gap-2"><Heart className="w-5 h-5 text-red-400" /> Score de Santé</span>} className="lg:col-span-2">
          {/* Mini KPIs */}
          <div className="flex gap-3 mb-4">
            <div className="flex-1 text-center p-3 rounded-lg bg-red-500/10 border border-red-500/20">
              <div className="text-2xl font-black text-savia-danger">{nbCritique}</div>
              <div className="text-xs text-red-300">Critique</div>
            </div>
            <div className="flex-1 text-center p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
              <div className="text-2xl font-black text-savia-warning">{nbAttention}</div>
              <div className="text-xs text-yellow-300">Attention</div>
            </div>
            <div className="flex-1 text-center p-3 rounded-lg bg-green-500/10 border border-green-500/20">
              <div className="text-2xl font-black text-savia-success">{nbBon}</div>
              <div className="text-xs text-green-300">Bon</div>
            </div>
          </div>

          {/* Table */}
          <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-savia-bg z-10">
                <tr className="border-b border-savia-border">
                  <th className="text-left py-2 px-3 text-savia-text-muted font-semibold">Équipement</th>
                  <th className="text-left py-2 px-3 text-savia-text-muted font-semibold">Client</th>
                  <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">Santé</th>
                  <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">Tendance</th>
                  <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">Pannes</th>
                </tr>
              </thead>
              <tbody>
                {[...healthScores].sort((a, b) => a.score - b.score).map((h) => (
                  <tr key={h.machine} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                    <td className="py-2.5 px-3 font-medium">{h.machine}</td>
                    <td className="py-2.5 px-3 text-xs text-savia-text-muted">{h.client || '—'}</td>
                    <td className="py-2.5 px-3 text-center">
                      <HealthBadge score={h.score} size="sm" />
                    </td>
                    <td className="py-2.5 px-3 text-center text-xs">
                      {h.tendance === 'hausse' ? '▲ Hausse' : h.tendance === 'baisse' ? '▼ Baisse' : '— Stable'}
                    </td>
                    <td className="py-2.5 px-3 text-center font-mono">{h.pannes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>

        {/* Indicateur Santé Globale — Cercle SVG animé */}
        <SectionCard title={<span className="flex items-center gap-2"><Target className="w-5 h-5 text-savia-accent" /> Indicateur Santé Globale</span>}>
          {(() => {
            const size = 200;
            const strokeWidth = 14;
            const radius = (size - strokeWidth) / 2;
            const circumference = 2 * Math.PI * radius;
            const offset = circumference - (scoreGlobal / 100) * circumference;
            const color = scoreGlobal >= 60 ? '#2dd4bf' : scoreGlobal >= 30 ? '#f59e0b' : '#ef4444';
            const label = scoreGlobal >= 60 ? 'Bon' : scoreGlobal >= 30 ? 'Attention' : 'Critique';
            return (
              <div className="flex flex-col items-center justify-center py-4">
                <div className="relative" style={{ width: size, height: size }}>
                  <svg width={size} height={size} className="-rotate-90">
                    {/* Background circle */}
                    <circle
                      cx={size / 2} cy={size / 2} r={radius}
                      fill="none" stroke="#1e293b" strokeWidth={strokeWidth}
                    />
                    {/* Glow filter */}
                    <defs>
                      <filter id="glow">
                        <feGaussianBlur stdDeviation="3" result="blur" />
                        <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
                      </filter>
                    </defs>
                    {/* Progress circle */}
                    <circle
                      cx={size / 2} cy={size / 2} r={radius}
                      fill="none" stroke={color} strokeWidth={strokeWidth}
                      strokeLinecap="round"
                      strokeDasharray={circumference}
                      strokeDashoffset={offset}
                      filter="url(#glow)"
                      style={{ transition: 'stroke-dashoffset 1.5s ease-out, stroke 0.5s ease' }}
                    />
                  </svg>
                  {/* Center text */}
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-4xl font-black" style={{ color }}>{scoreGlobal}%</span>
                    <span className="text-xs font-semibold mt-1" style={{ color, opacity: 0.8 }}>{label}</span>
                  </div>
                </div>
                <div className="text-xs text-savia-text-muted mt-3">Santé Globale du Parc</div>
              </div>
            );
          })()}
        </SectionCard>
      </div>

      {/* Disponibilité Trend */}
      <SectionCard title={<span className="flex items-center gap-2"><TrendingUp className="w-5 h-5 text-green-400" /> Tendance Disponibilité (6 mois)</span>}>
        {trendData.length === 0 ? (
          <div className="h-[200px] flex items-center justify-center text-savia-text-muted">
            Chargement des données...
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={trendData}>
              <defs>
                <linearGradient id="dispoGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={CHART_STYLE.accent} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={CHART_STYLE.accent} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="mois" stroke={CHART_STYLE.text} fontSize={12} />
              <YAxis domain={[0, 100]} stroke={CHART_STYLE.text} fontSize={12} />
              <Tooltip
                contentStyle={{ background: CHART_STYLE.bg, border: `1px solid ${CHART_STYLE.grid}`, borderRadius: 8, color: '#f1f5f9' }}
                formatter={(value) => [`${value}%`, 'Disponibilité']}
              />
              <Area type="monotone" dataKey="dispo" stroke={CHART_STYLE.accent} fill="url(#dispoGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </SectionCard>

      {/* Footer */}
      <div className="text-center py-4 border-t border-savia-border/50">
        <span className="gradient-text font-bold text-sm">SAVIA</span>
        <span className="text-savia-text-dim text-xs ml-2">
          Powered by SIC • Maintenance Prédictive
        </span>
      </div>
    </div>
  );
}
