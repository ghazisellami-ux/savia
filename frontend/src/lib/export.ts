import { downloadBlob } from './download';

type ExportLang = 'fr' | 'en';

function getExportLang(): ExportLang {
  if (typeof window === 'undefined') return 'fr';
  return localStorage.getItem('savia_lang') === 'en' ? 'en' : 'fr';
}

function label(fr: string, en: string, lang: ExportLang = getExportLang()): string {
  return lang === 'en' ? en : fr;
}

function translateStatus(value: unknown, lang: ExportLang): string {
  const text = String(value || '');
  if (lang !== 'en') return text;
  const statuses: Record<string, string> = {
    'En cours': 'In progress',
    'Cloturee': 'Closed',
    'Clôturée': 'Closed',
    'En attente de piece': 'Waiting for part',
    'En attente de pièce': 'Waiting for part',
    'Planifiee': 'Scheduled',
    'Planifiée': 'Scheduled',
    'Realisee': 'Completed',
    'Réalisée': 'Completed',
    'Non assigne': 'Unassigned',
    'Non assigné': 'Unassigned',
  };
  return statuses[text] || text;
}

/**
 * Export comparateur data to CSV format.
 */
export function exportComparateurToCSV(data: any, filename: string = 'comparateur.csv'): void {
  const lang = getExportLang();
  const rows: string[] = [];

  rows.push(label('COMPARATEUR PLANNING', 'SCHEDULE COMPARATOR', lang));
  rows.push(`${label('Machine', 'Machine', lang)},${data.machine || ''}`);
  rows.push(`${label('Client', 'Client', lang)},${data.client || ''}`);
  rows.push(`${label('Type', 'Type', lang)},${data.type_maintenance || ''}`);
  rows.push(`${label('Description', 'Description', lang)},${data.description || ''}`);
  rows.push('');

  rows.push(label('PLANNING REEL (Nouvelle date)', 'REAL SCHEDULE (New date)', lang));
  rows.push(`${label('Date', 'Date', lang)},${data.real?.date || ''}`);
  rows.push(`${label('Technicien', 'Technician', lang)},${data.real?.technicien || ''}`);
  rows.push(`${label('Statut', 'Status', lang)},${translateStatus(data.real?.statut, lang)}`);
  rows.push('');

  if (data.ghost) {
    rows.push(label('PLANNING DECALE (Date originale)', 'SHIFTED SCHEDULE (Original date)', lang));
    rows.push(`${label('Date', 'Date', lang)},${data.ghost.date || ''}`);
    rows.push(`${label('Technicien', 'Technician', lang)},${data.ghost.technicien || ''}`);
    rows.push(`${label('Statut', 'Status', lang)},${translateStatus(data.ghost.statut, lang)}`);
    rows.push('');
  }

  rows.push(label('CHANGEMENTS', 'CHANGES', lang));
  if (data.differences?.date_changed) {
    rows.push(`${label('Date modifiee', 'Changed date', lang)},"${data.differences.old_date} -> ${data.differences.new_date}"`);
  }
  if (data.differences?.technicien_changed) {
    const oldTech = data.differences.old_technicien || label('Non assigne', 'Unassigned', lang);
    const newTech = data.differences.new_technicien || label('Non assigne', 'Unassigned', lang);
    rows.push(`${label('Technicien modifie', 'Changed technician', lang)},"${oldTech} -> ${newTech}"`);
  }
  rows.push('');

  if (data.reasons && data.reasons.length > 0) {
    rows.push(label('RAISONS DU DECALAGE', 'SHIFT REASONS', lang));
    data.reasons.forEach((reason: string, idx: number) => {
      rows.push(`${label('Raison', 'Reason', lang)} ${idx + 1},"${reason}"`);
    });
  }

  const csv = rows.join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  downloadBlob(blob, filename);
}

/**
 * Export comparateur data to JSON format.
 */
export function exportComparateurToJSON(data: any, filename: string = 'comparateur.json'): void {
  const output = {
    timestamp: new Date().toISOString(),
    planning_id: data.planning_id,
    machine: data.machine,
    client: data.client,
    type_maintenance: data.type_maintenance,
    description: data.description,
    real_planning: data.real,
    ghost_planning: data.ghost || null,
    differences: data.differences,
    reschedule_reasons: data.reasons || [],
    has_ghost: data.has_ghost,
  };

  const json = JSON.stringify(output, null, 2);
  const blob = new Blob([json], { type: 'application/json;charset=utf-8;' });
  downloadBlob(blob, filename);
}

/**
 * Export comparateur data to PDF format (via backend).
 */
export async function exportComparateurToPDF(data: any, filename: string = 'comparateur.pdf'): Promise<void> {
  try {
    const lang = getExportLang();

    const res = await fetch('/api/planning/comparateur/pdf', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-SAVIA-Lang': lang,
      },
      credentials: 'same-origin',
      body: JSON.stringify({ ...data, lang }),
    });

    if (!res.ok) {
      throw new Error(`${label('Erreur PDF', 'PDF error', lang)}: ${res.status}`);
    }

    const blob = await res.blob();
    downloadBlob(blob, filename);
  } catch (error) {
    console.error('PDF export error:', error);
    throw error;
  }
}

/**
 * Format date for display.
 */
export function formatDateFR(dateStr: string): string {
  if (!dateStr) return '';
  const lang = getExportLang();
  const date = new Date(dateStr);
  return date.toLocaleDateString(lang === 'en' ? 'en-US' : 'fr-FR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/**
 * Generate summary text for comparateur.
 */
export function getComparateurSummary(data: any): string {
  const lang = getExportLang();

  if (!data.has_ghost) {
    return label('Aucun decalage trouve pour cette intervention', 'No schedule shift found for this intervention', lang);
  }

  const summary: string[] = [];

  if (data.differences?.date_changed) {
    summary.push(
      `${label('Date decalee', 'Shifted date', lang)}: ${formatDateFR(data.differences.old_date)} -> ${formatDateFR(data.differences.new_date)}`
    );
  }

  if (data.differences?.technicien_changed) {
    const oldTech = data.differences.old_technicien || label('Non assigne', 'Unassigned', lang);
    const newTech = data.differences.new_technicien || label('Non assigne', 'Unassigned', lang);
    summary.push(`${label('Technicien change', 'Changed technician', lang)}: ${oldTech} -> ${newTech}`);
  }

  if (data.reasons && data.reasons.length > 0) {
    summary.push(`${label('Raisons', 'Reasons', lang)}: ${data.reasons.join(', ')}`);
  }

  return summary.length > 0 ? summary.join(' | ') : label('Decalage enregistre', 'Schedule shift saved', lang);
}
