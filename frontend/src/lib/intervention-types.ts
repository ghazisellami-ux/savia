/**
 * Types partagés par les interventions SAV et le planning de maintenance.
 * Les types personnalisés sont ajoutés par les pages via l'API dédiée.
 */
export const INTERVENTION_TYPES_BASE = [
  'Corrective',
  'Préventive',
  'Calibration',
  'Inspection',
  'Qualification',
  'Mise à jour logiciel',
  'Installation',
  'Formation',
  'Démo',
] as const;

export const mergeInterventionTypes = (...groups: Array<Iterable<string> | undefined>) => {
  const values = new Set<string>();
  for (const group of groups) {
    for (const value of group || []) {
      const normalized = String(value || '').trim();
      if (normalized) values.add(normalized);
    }
  }
  return Array.from(values);
};
