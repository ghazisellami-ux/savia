import { ADDITIONAL_PHRASES, PHRASES } from '@/lib/i18n-phrases';

export type Lang = 'fr' | 'en';

const ALL_PHRASES = [...PHRASES, ...ADDITIONAL_PHRASES];
const EXPANDED_PHRASES = ALL_PHRASES.flatMap(([from, to]) =>
  phraseVariants(from).map(variant => [variant, to] as [string, string])
);
const EXACT = (() => {
  const map = new Map<string, string>();
  for (const [from, to] of EXPANDED_PHRASES) {
    const key = normalizeExactKey(from);
    if (!map.has(key)) map.set(key, to);
  }
  return map;
})();
const REPLACEMENTS = [...EXPANDED_PHRASES].sort((a, b) => b[0].length - a[0].length);
export const ATTRS = ['placeholder', 'title', 'aria-label'];
export const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'CODE', 'PRE']);

export function normalizeLang(value: unknown): Lang {
  return String(value || '').toLowerCase().startsWith('en') ? 'en' : 'fr';
}

export function normalizeCurrencyCode(value: unknown): string {
  return String(value || 'TND').trim().toUpperCase() || 'TND';
}

export function applySelectedCurrency(value: string, currency: string): string {
  const code = normalizeCurrencyCode(currency);
  if (code === 'TND') return value;
  return value
    .replace(/\(\s*TND\s*\)/g, `(${code})`)
    .replace(/(\b\d[\d\s.,\u00a0\u202f]*(?:[Kk])?\s*)TND\b/g, `$1${code}`);
}

function repairMojibake(value: string): string {
  let current = value;
  for (let i = 0; i < 2 && /[ÃÂâ]/.test(current); i += 1) {
    try {
      const next = decodeURIComponent(escape(current));
      if (next === current) break;
      current = next;
    } catch {
      break;
    }
  }
  return current;
}

function stripDiacritics(value: string): string {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function normalizePunctuation(value: string): string {
  return value
    .replace(/[’‘`´ʻʼ]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, '-')
    .replace(/\u00a0/g, ' ');
}

function normalizeExactKey(value: string): string {
  return stripDiacritics(normalizePunctuation(repairMojibake(value)))
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function translateDynamicCurrencyLabels(value: string): string {
  return value
    .replace(/\bRevenu\s*\(([^)]+)\)/g, 'Revenue ($1)')
    .replace(/\bCo(?:û|u)ts\s*\(([^)]+)\)/g, 'Costs ($1)')
    .replace(/\bMarge\s*\(([^)]+)\)/g, 'Margin ($1)')
    .replace(/\bCo(?:û|u)t\s*\(([^)]+)\)/g, 'Cost ($1)')
    .replace(/\bValeur stock\s*\(([^)]+)\)/g, 'Stock value ($1)')
    .replace(/Analyse comparative des co(?:û|u)ts\s*\(([^)]+)\)\./g, 'Comparative cost analysis ($1).');
}

function phraseVariants(value: string): string[] {
  const repaired = repairMojibake(value);
  const normalized = normalizePunctuation(repaired);
  const variants = [
    value,
    repaired,
    normalized,
    stripDiacritics(value),
    stripDiacritics(repaired),
    stripDiacritics(normalized),
  ];
  return Array.from(new Set(variants.filter(Boolean)));
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function isWordLike(value: string): boolean {
  return /^[\p{L}\p{N}_]+$/u.test(value);
}

function replacePhrase(text: string, from: string, to: string): string {
  if (!from || !text.includes(from)) return text;
  if (!isWordLike(from)) return text.split(from).join(to);
  const pattern = new RegExp(`(^|[^\\p{L}\\p{N}_])${escapeRegExp(from)}(?=$|[^\\p{L}\\p{N}_])`, 'gu');
  return text.replace(pattern, (_match, prefix: string) => `${prefix}${to}`);
}

function findExact(value: string): string | undefined {
  return EXACT.get(normalizeExactKey(value));
}

export function translateText(value: string, currency = 'TND'): string {
  if (!value.trim()) return value;
  const leading = value.match(/^\s*/)?.[0] || '';
  const trailing = value.match(/\s*$/)?.[0] || '';
  const core = value.slice(leading.length, value.length - trailing.length);
  const repairedCore = repairMojibake(core);
  const compact = repairedCore.replace(/\s+/g, ' ').trim();
  let translated = findExact(compact);
  if (!translated) {
    const dynamic = translateDynamicCurrencyLabels(repairedCore);
    if (dynamic !== repairedCore) translated = dynamic;
  }
  if (!translated) {
    translated = repairedCore;
    for (const [from, to] of REPLACEMENTS) {
      translated = replacePhrase(translated, from, to);
    }
    translated = translateDynamicCurrencyLabels(translated);
    translated = findExact(translated) || translated;
  }
  return `${leading}${applySelectedCurrency(translated, currency)}${trailing}`;
}
