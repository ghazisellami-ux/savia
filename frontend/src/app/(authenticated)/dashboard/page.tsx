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
  interventions_ouvertes: number;
  interventions_retard: number;
  preventives_retard: number;
  preventives_7j: number;
  preventives_30j: number;
  sla_respect_pct: number;
  sla_hors_delai: number;
  sla_suivies: number;
  cout_correctif_moyen: number;
}

interface HealthScore {
  machine: string;
  score: number;
  tendance: string;
  pannes: number;
  client?: string;
}

const clientKey = (client: string) => client.trim().toLocaleLowerCase();

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
  const canSeeCosts = useCanSeeCosts() && user?.role !== 'Technicien';
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
    nb_equipements: 0, nb_critiques: 0, disponibilite: 100, mtbf: 0, mttr: 0, cout_total: 0, nb_interventions: 0, nb_clients: 0, taux_resolution: 0,
    interventions_ouvertes: 0, interventions_retard: 0, preventives_retard: 0, preventives_7j: 0, preventives_30j: 0,
    sla_respect_pct: 100, sla_hors_delai: 0, sla_suivies: 0, cout_correctif_moyen: 0,
  });
  const [clientEquipmentCounts, setClientEquipmentCounts] = useState<Record<string, number>>({});
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

  // Preload each client's real fleet size. Changing the client then uses data
  // already in memory rather than a new network request or a de-duplicated
  // health-score count.
  useEffect(() => {
    let isCurrentRequest = true;
    clientsApi.list()
      .then((clients) => {
        if (!isCurrentRequest) return;
        const counts = clients.reduce<Record<string, number>>((result, client) => {
          const name = String(client.nom || '').trim();
          if (name) {
            result[clientKey(name)] = Number(client.nb_equipements) || 0;
          }
          return result;
        }, {});
        setClientEquipmentCounts(counts);
      })
      .catch((err) => {
        if (isCurrentRequest) {
          console.error("Failed to preload client equipment counts", err);
        }
      });

    return () => {
      isCurrentRequest = false;
    };
  }, []);

  const selectedClientEquipmentCount = selectedClient
    ? clientEquipmentCounts[clientKey(selectedClient)]
    : undefined;

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
    const cacheKey = `dashboard_kpi_cache:${dateRange.date_start}:${dateRange.date_end}`;
    let hasCachedData = false;
    try {
      const cached = localStorage.getItem(cacheKey);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed?.kpis && Array.isArray(parsed.healthScores)) {
          setFullData({ kpis: parsed.kpis, healthScores: parsed.healthScores, interventions: [] });
          setIsInitialLoading(false);
          hasCachedData = true;
        }
      }
    } catch (err) {
      console.warn('Unable to read dashboard KPI cache', err);
    }
    
    const loadFullData = async () => {
      if (!hasCachedData) setIsInitialLoading(true);
      
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

        try {
          localStorage.setItem(cacheKey, JSON.stringify({
            kpis: kpiData,
            healthScores: healthData,
            cachedAt: new Date().toISOString(),
          }));
        } catch (err) {
          console.warn('Unable to write dashboard KPI cache', err);
        }
        
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

    // A client filter is resolved by the API so all operational KPI rules stay consistent.
    if (selectedClient && !selectedEquipType) {
      setIsLoading(true);
      // Fetch the scoped dashboard from the API so operational KPIs (planning
      // and SLA) use the same server-side rules as the unfiltered view.
      const loadClientData = async () => {
        try {
          const params = { client: selectedClient, date_start: dateRange.date_start, date_end: dateRange.date_end };
          const [kpiData, healthData, intervData] = await Promise.all([
            dashboard.kpis(params), dashboard.healthScores(params), interventionsApi.list(),
          ]);
          setKpis(kpiData as unknown as KpiData);
          setHealthScores(healthData);
          const machines = new Set(healthData.map((h: any) => h.machine));
          const scopedInterventions = (intervData || []).filter((i: any) => machines.has(i.machine));
          setAllInterventions(scopedInterventions);
          setRecentInterv(
            scopedInterventions
              .filter((i: any) => String(i.date || '').substring(0, 10) >= dateRange.date_start && String(i.date || '').substring(0, 10) <= dateRange.date_end)
              .sort((a: any, b: any) => String(b.date || '').localeCompare(String(a.date || '')))
              .slice(0, 10),
          );
        } catch (err) {
          console.error("Failed to load client dashboard", err);
        } finally {
          setIsLoading(false);
        }
      };
      loadClientData();
      return;
    }

    // If no filters or equipment type filter, use full data or call API
    if (!selectedClient && !selectedEquipType) {
      // No filters - use full data but filter by date range
      setIsLoading(true);
      try {
        setKpis(fullData!.kpis);
        setHealthScores(fullData!.healthScores);
        setAllInterventions(fullData!.interventions);
        
        // Filter interventions by date range for display
        const dateFilteredInterv = fullData!.interventions.filter((i: any) => {
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
          credentials: 'same-origin',
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
  const showKpiLoading = !fullData || isInitialLoading;

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
        <KpiCard emphasis appearance="status-stripe" loading={showKpiLoading} icon={<Building2 className="w-6 h-6 text-purple-400" />} value={String(kpis.nb_clients)} label="Clients" />
        <KpiCard emphasis appearance="status-stripe" loading={showKpiLoading} icon={<Cpu className="w-6 h-6 text-savia-accent" />} value={selectedClient ? (selectedClientEquipmentCount === undefined ? '—' : String(selectedClientEquipmentCount)) : String(kpis.nb_equipements)} label="Équipements" />
        <KpiCard emphasis appearance="status-stripe" loading={showKpiLoading} icon={<CircleAlert className="w-6 h-6 text-red-400" />} value={String(kpis.nb_critiques)} label="Équipements en état critique" variant={kpis.nb_critiques > 0 ? 'danger' : 'default'} tooltip="Équipements actuellement hors service, critiques ou en panne." />
        <KpiCard emphasis appearance="status-stripe" loading={showKpiLoading} icon={<CircleCheck className="w-6 h-6 text-green-400" />} value={`${kpis.disponibilite}%`} label="Disponibilité" variant="success" />
      </div>

      {/* KPIs Row - Opérationnels */}
      <div className={`grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-4 transition-opacity duration-300 ${isLoading ? 'opacity-60' : 'opacity-100'}`}>
        <KpiCard emphasis appearance="status-stripe" loading={showKpiLoading} icon={<Wrench className="w-6 h-6 text-orange-400" />} value={String(kpis.interventions_ouvertes)} label="Interventions ouvertes" detail={`${kpis.interventions_retard} en retard`} variant={kpis.interventions_retard > 0 ? 'danger' : 'default'} tooltip="Interventions non clôturées ; le sous-indicateur précise celles dont l'échéance est dépassée." />
        <KpiCard emphasis appearance="status-stripe" loading={showKpiLoading} icon={<Calendar className="w-6 h-6 text-yellow-400" />} value={String(kpis.preventives_retard)} label="Préventives en retard" detail={`À 7 j : ${kpis.preventives_7j} · 8–30 j : ${kpis.preventives_30j}`} variant={kpis.preventives_retard > 0 ? 'warning' : 'success'} tooltip="Préventives en retard, puis préventives à réaliser dans les 7 et 30 prochains jours." />
        <KpiCard emphasis appearance="status-stripe" loading={showKpiLoading} icon={<Target className="w-6 h-6 text-emerald-400" />} value={`${kpis.sla_respect_pct}%`} label="Respect SLA" detail={`${kpis.sla_hors_delai} hors SLA · ${kpis.sla_suivies} suivies`} variant={kpis.sla_hors_delai > 0 ? 'warning' : 'success'} tooltip="Part des interventions couvertes par un contrat et traitées dans le délai prévu." />
        <KpiCard emphasis appearance="status-stripe" loading={showKpiLoading} icon={<Timer className="w-6 h-6 text-blue-400" />} value={`${kpis.mttr.toFixed(1)} h`} label="MTTR" tooltip="Durée moyenne de réparation des interventions correctives clôturées." />
      </div>

      {/* KPI de qualité et de pilotage */}
      <div className={`grid gap-4 grid-cols-2 md:grid-cols-3 ${isLoading ? 'opacity-60' : 'opacity-100'}`}>
        <KpiCard emphasis appearance="status-stripe" loading={showKpiLoading} icon={<Timer className="w-6 h-6 text-blue-400" />} value={mtbfStr} label="MTBF correctif" tooltip="Intervalle moyen entre pannes correctives, calculé équipement par équipement." />
        <KpiCard emphasis appearance="status-stripe" loading={showKpiLoading} icon={<Target className="w-6 h-6 text-emerald-400" />} value={`${kpis.taux_resolution}%`} label="Taux de résolution" variant={kpis.taux_resolution >= 80 ? 'success' : kpis.taux_resolution >= 60 ? 'default' : 'danger'} tooltip="Pourcentage d'interventions clôturées sur la période sélectionnée." />
        {canSeeCosts && (
          <KpiCard emphasis appearance="status-stripe" loading={showKpiLoading} icon={<DollarSign className="w-6 h-6 text-yellow-400" />} value={`${kpis.cout_correctif_moyen.toLocaleString('fr-FR', { maximumFractionDigits: 0 })} TND`} label="Coût moyen correctif" tooltip="Coût moyen par intervention corrective (main-d'œuvre et pièces). Réservé aux responsables." />
        )}
      </div>

      {/* 🚨 Anomalies Detected */}
      {healthScores.filter(h => h.score < 30).length > 0 && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-xl overflow-hidden">
          <button onClick={() => setShowAnomalies(!showAnomalies)} className="w-full flex items-center justify-between p-4 cursor-pointer hover:bg-red-500/5 transition-colors">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-400" />
              <span className="font-bold text-red-400">{healthScores.filter(h => h.score < 30).length} anomalie(s) santé critique(s)</span>
            </div>
            {showAnomalies ? <ChevronUp className="w-4 h-4 text-savia-text-muted" /> : <ChevronDown className="w-4 h-4 text-savia-text-muted" />}
          </button>
          {showAnomalies && (
            <div className="px-4 pb-4 space-y-2">
              {healthScores.filter(h => h.score < 30).map(h => (
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
