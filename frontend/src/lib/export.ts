import { downloadBlob } from './download';

/**
 * Export comparateur data to CSV format
 */
export function exportComparateurToCSV(data: any, filename: string = 'comparateur.csv'): void {
  const rows: string[] = [];
  
  // Header
  rows.push('COMPARATEUR PLANNING');
  rows.push(`Machine,${data.machine || ''}`);
  rows.push(`Client,${data.client || ''}`);
  rows.push(`Type,${data.type_maintenance || ''}`);
  rows.push(`Description,${data.description || ''}`);
  rows.push('');
  
  // Comparaison
  rows.push('PLANNING RÉEL (Nouvelle date)');
  rows.push(`Date,${data.real?.date || ''}`);
  rows.push(`Technicien,${data.real?.technicien || ''}`);
  rows.push(`Statut,${data.real?.statut || ''}`);
  rows.push('');
  
  if (data.ghost) {
    rows.push('PLANNING DÉCALÉ (Date originale)');
    rows.push(`Date,${data.ghost.date || ''}`);
    rows.push(`Technicien,${data.ghost.technicien || ''}`);
    rows.push(`Statut,${data.ghost.statut || ''}`);
    rows.push('');
  }
  
  // Differences
  rows.push('CHANGEMENTS');
  if (data.differences?.date_changed) {
    rows.push(`Date modifiée,"${data.differences.old_date} → ${data.differences.new_date}"`);
  }
  if (data.differences?.technicien_changed) {
    rows.push(`Technicien modifié,"${data.differences.old_technicien || 'Non assigné'} → ${data.differences.new_technicien || 'Non assigné'}"`);
  }
  rows.push('');
  
  // Reasons
  if (data.reasons && data.reasons.length > 0) {
    rows.push('RAISONS DU DÉCALAGE');
    data.reasons.forEach((reason: string, idx: number) => {
      rows.push(`Raison ${idx + 1},"${reason}"`);
    });
  }
  
  const csv = rows.join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  downloadBlob(blob, filename);
}

/**
 * Export comparateur data to JSON format
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
 * Export comparateur data to PDF format (via backend)
 */
export async function exportComparateurToPDF(data: any, filename: string = 'comparateur.pdf'): Promise<void> {
  try {
    const token = typeof window !== 'undefined' ? localStorage.getItem('savia_token') || '' : '';
    
    const res = await fetch('/api/planning/comparateur/pdf', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    });
    
    if (!res.ok) {
      throw new Error(`Erreur PDF: ${res.status}`);
    }
    
    const blob = await res.blob();
    downloadBlob(blob, filename);
  } catch (error) {
    console.error('PDF export error:', error);
    throw error;
  }
}

/**
 * Format date for display
 */
export function formatDateFR(dateStr: string): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('fr-FR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/**
 * Generate summary text for comparateur
 */
export function getComparateurSummary(data: any): string {
  if (!data.has_ghost) {
    return 'Aucun décalage trouvé pour cette intervention';
  }
  
  const summary: string[] = [];
  
  if (data.differences?.date_changed) {
    summary.push(`Date décalée: ${formatDateFR(data.differences.old_date)} → ${formatDateFR(data.differences.new_date)}`);
  }
  
  if (data.differences?.technicien_changed) {
    summary.push(`Technicien changé: ${data.differences.old_technicien || 'Non assigné'} → ${data.differences.new_technicien || 'Non assigné'}`);
  }
  
  if (data.reasons && data.reasons.length > 0) {
    summary.push(`Raisons: ${data.reasons.join(', ')}`);
  }
  
  return summary.length > 0 ? summary.join(' | ') : 'Décalage enregistré';
}
