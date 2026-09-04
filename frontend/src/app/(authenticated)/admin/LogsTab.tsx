'use client';
import { useState, useEffect } from 'react';
import { SectionCard } from '@/components/ui/cards';
import {
  Download, Search, Loader2, Calendar, User, Activity, Network,
  Filter, X, FileDown, AlertCircle,
} from 'lucide-react';
import { getBrowserTimezone, getLocalDateISO, parseServerTimestamp } from '@/lib/timezone';

interface AuditLog {
  id: number;
  timestamp: string;
  username: string;
  action: string;
  details: string;
  page: string;
  ip_address: string;
}

const INPUT = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-3 py-2 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all text-sm";
const LABEL = "block text-xs font-semibold text-savia-text-muted mb-1 uppercase tracking-wider";

// Action color mapping
const getActionColor = (action: string) => {
  if (action.startsWith('CREATE_')) return 'bg-green-500/10 text-green-400 border-green-500/30';
  if (action.startsWith('UPDATE_') || action.includes('UPDATE')) return 'bg-blue-500/10 text-blue-400 border-blue-500/30';
  if (action.startsWith('DELETE_') || action === 'DELETE') return 'bg-red-500/10 text-red-400 border-red-500/30';
  if (action.includes('LOGIN')) return 'bg-purple-500/10 text-purple-400 border-purple-500/30';
  return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
};

const getActionIcon = (action: string) => {
  if (action.startsWith('CREATE_')) return '➕';
  if (action.startsWith('UPDATE_') || action.includes('UPDATE')) return '✏️';
  if (action.startsWith('DELETE_') || action === 'DELETE') return '🗑️';
  if (action.includes('LOGIN')) return '🔐';
  return '⚙️';
};

export default function LogsTab() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  
  // Filters
  const [limit, setLimit] = useState(1000);
  const [username, setUsername] = useState('');
  const [action, setAction] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [searchText, setSearchText] = useState('');
  
  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 25;
  
  // Unique values for dropdowns
  const [uniqueUsers, setUniqueUsers] = useState<string[]>([]);
  const [uniqueActions, setUniqueActions] = useState<string[]>([]);

  // Load logs
  const loadLogs = async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      params.append('limit', limit.toString());
      if (username) params.append('username', username);
      if (action) params.append('action', action);
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);
      params.append('timezone', getBrowserTimezone());
      
      const res = await fetch(`/api/admin/audit-logs?${params}`, {
        credentials: 'same-origin',
      });
      
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as AuditLog[];
      
      setLogs(data || []);
      
      // Extract unique values for filters
      const users = [...new Set(data.map((l) => l.username))];
      const actions = [...new Set(data.map((l) => l.action))];
      setUniqueUsers(users.sort());
      setUniqueActions(actions.sort());
    } catch (err) {
      console.error('Error loading audit logs:', err);
      setLogs([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, [limit, username, action, dateFrom, dateTo]);

  // Filter logs by search text
  const filteredLogs = logs.filter(log =>
    !searchText ||
    log.username.toLowerCase().includes(searchText.toLowerCase()) ||
    log.action.toLowerCase().includes(searchText.toLowerCase()) ||
    log.details.toLowerCase().includes(searchText.toLowerCase()) ||
    log.page.toLowerCase().includes(searchText.toLowerCase()) ||
    log.ip_address.toLowerCase().includes(searchText.toLowerCase())
  );

  // Pagination
  const totalPages = Math.ceil(filteredLogs.length / itemsPerPage);
  const paginatedLogs = filteredLogs.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // Export to PDF
  const exportToPDF = async () => {
    setIsExporting(true);
    try {
      const res = await fetch('/api/admin/audit-logs/export-pdf', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          limit,
          username,
          action,
          date_from: dateFrom,
          date_to: dateTo,
          timezone: getBrowserTimezone(),
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      // Download PDF
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-logs-${getLocalDateISO()}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Error exporting PDF:', err);
      alert('Erreur lors de l\'export PDF');
    } finally {
      setIsExporting(false);
    }
  };

  const clearFilters = () => {
    setUsername('');
    setAction('');
    setDateFrom('');
    setDateTo('');
    setSearchText('');
    setCurrentPage(1);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-savia-text flex items-center gap-2">
            <Activity className="w-5 h-5 text-savia-accent" /> Journal d'Audit
          </h2>
          <p className="text-xs text-savia-text-muted mt-1">
            {logs.length} log(s) chargé(s) • {filteredLogs.length} affichés
          </p>
        </div>
        <button
          onClick={exportToPDF}
          disabled={isExporting || logs.length === 0}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-cyan-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isExporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />}
          {isExporting ? 'Export...' : 'Export PDF'}
        </button>
      </div>

      {/* Filters */}
      <SectionCard title={<span className="flex items-center gap-2"><Filter className="w-4 h-4 text-savia-accent" /> Filtres</span>}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-4">
          {/* Limit */}
          <div>
            <label className={LABEL}>Max logs</label>
            <input
              type="number"
              min={10}
              max={5000}
              value={limit}
              onChange={(e) => setLimit(Math.min(5000, Math.max(10, parseInt(e.target.value) || 100)))}
              className={INPUT}
            />
          </div>

          {/* Username */}
          <div>
            <label className={LABEL}>Utilisateur</label>
            <select
              value={username}
              onChange={(e) => { setUsername(e.target.value); setCurrentPage(1); }}
              className={INPUT}
            >
              <option value="">Tous les utilisateurs</option>
              {uniqueUsers.map(u => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </div>

          {/* Action */}
          <div>
            <label className={LABEL}>Type d'action</label>
            <select
              value={action}
              onChange={(e) => { setAction(e.target.value); setCurrentPage(1); }}
              className={INPUT}
            >
              <option value="">Toutes les actions</option>
              {uniqueActions.map(a => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>

          {/* Date From */}
          <div>
            <label className={LABEL}>Du</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setCurrentPage(1); }}
              className={INPUT}
            />
          </div>

          {/* Date To */}
          <div>
            <label className={LABEL}>Au</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setCurrentPage(1); }}
              className={INPUT}
            />
          </div>
        </div>

        {/* Search & Clear */}
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-muted pointer-events-none" />
            <input
              type="text"
              placeholder="Rechercher dans les logs..."
              value={searchText}
              onChange={(e) => { setSearchText(e.target.value); setCurrentPage(1); }}
              className={INPUT + " pl-9"}
            />
          </div>
          {(username || action || dateFrom || dateTo || searchText) && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-savia-surface-hover border border-savia-border hover:bg-savia-surface-hover/80 transition-all"
              title="Réinitialiser les filtres"
            >
              <X className="w-4 h-4" /> Réinitialiser
            </button>
          )}
        </div>
      </SectionCard>

      {/* Logs Table */}
      <SectionCard title={<span className="flex items-center gap-2"><Activity className="w-4 h-4 text-savia-accent" /> Logs ({filteredLogs.length})</span>}>
        {isLoading ? (
          <div className="flex justify-center items-center h-32">
            <Loader2 className="w-6 h-6 animate-spin text-savia-accent" />
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="flex items-center justify-center h-32 gap-2 text-savia-text-muted">
            <AlertCircle className="w-5 h-5" />
            <span>Aucun log correspondant aux filtres</span>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-savia-border">
                    {['Date/Heure', 'Utilisateur', 'Action', 'Détails', 'Page', 'IP'].map(h => (
                      <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs font-semibold">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paginatedLogs.map(log => {
                    const timestamp = parseServerTimestamp(log.timestamp);
                    const actionColor = getActionColor(log.action);
                    const actionIcon = getActionIcon(log.action);
                    let details = '';
                    try {
                      const parsed = JSON.parse(log.details || '{}');
                      details = Object.entries(parsed)
                        .map(([k, v]) => `${k}: ${String(v).slice(0, 30)}`)
                        .join(' | ');
                    } catch {
                      details = log.details.slice(0, 50);
                    }

                    return (
                      <tr key={log.id} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                        <td className="py-2.5 px-3 text-xs text-savia-text-muted font-mono">
                          {timestamp.toLocaleString('fr-FR')}
                        </td>
                        <td className="py-2.5 px-3 font-semibold text-savia-accent">
                          <User className="w-3.5 h-3.5 inline mr-1" />
                          {log.username}
                        </td>
                        <td className="py-2.5 px-3">
                          <span className={`px-2 py-0.5 rounded-lg text-xs font-bold border ${actionColor}`}>
                            {actionIcon} {log.action}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-xs text-savia-text-muted max-w-xs truncate" title={log.details}>
                          {details || '—'}
                        </td>
                        <td className="py-2.5 px-3 text-xs text-savia-text-muted">
                          {log.page || '—'}
                        </td>
                        <td className="py-2.5 px-3 text-xs font-mono text-savia-text-muted flex items-center gap-1">
                          <Network className="w-3.5 h-3.5" />
                          {log.ip_address || '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t border-savia-border">
                <div className="text-xs text-savia-text-muted">
                  Page {currentPage} sur {totalPages} • {paginatedLogs.length} logs affichés
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="px-2 py-1 rounded-lg bg-savia-surface-hover border border-savia-border disabled:opacity-50 disabled:cursor-not-allowed hover:bg-savia-surface-hover/80 transition-all"
                  >
                    ← Précédent
                  </button>
                  {Array.from({ length: Math.min(5, totalPages) }).map((_, i) => {
                    const pageNum = currentPage <= 3 ? i + 1 : currentPage - 2 + i;
                    if (pageNum > totalPages) return null;
                    return (
                      <button
                        key={pageNum}
                        onClick={() => setCurrentPage(pageNum)}
                        className={`px-2 py-1 rounded-lg border transition-all ${
                          pageNum === currentPage
                            ? 'bg-savia-accent text-savia-surface border-savia-accent'
                            : 'bg-savia-surface-hover border-savia-border hover:bg-savia-surface-hover/80'
                        }`}
                      >
                        {pageNum}
                      </button>
                    );
                  })}
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="px-2 py-1 rounded-lg bg-savia-surface-hover border border-savia-border disabled:opacity-50 disabled:cursor-not-allowed hover:bg-savia-surface-hover/80 transition-all"
                  >
                    Suivant →
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </SectionCard>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Logins', value: logs.filter(l => l.action.includes('LOGIN')).length, icon: '🔐' },
          { label: 'Créations', value: logs.filter(l => l.action.startsWith('CREATE_')).length, icon: '➕' },
          { label: 'Modifications', value: logs.filter(l => l.action.startsWith('UPDATE_')).length, icon: '✏️' },
          { label: 'Suppressions', value: logs.filter(l => l.action.startsWith('DELETE_')).length, icon: '🗑️' },
        ].map(s => (
          <div key={s.label} className="glass rounded-xl p-3 text-center">
            <div className="text-2xl mb-1">{s.icon}</div>
            <div className="text-lg font-black text-savia-accent">{s.value}</div>
            <div className="text-xs text-savia-text-muted mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
