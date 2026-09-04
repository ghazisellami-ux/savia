/** Time helpers for values rendered in the user's computer timezone. */

export function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function getLocalDateISO(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Database timestamps historically arrived without an offset. They are
 * stored as UTC values, so explicitly mark them as UTC before converting to
 * the browser's local timezone. Offset-aware values remain untouched.
 */
export function parseServerTimestamp(value: string | null | undefined): Date {
  const raw = String(value || '').trim();
  if (!raw) return new Date(NaN);
  const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  return new Date(hasTimezone ? normalized : `${normalized}Z`);
}

