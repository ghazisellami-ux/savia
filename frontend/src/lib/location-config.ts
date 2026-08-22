// ISO codes are used for built-in countries; CUSTOM_* codes are generated for
// countries added manually in Administration.
export type CountryCode = string;

export interface CountryDefinition {
  code: CountryCode;
  name: string;
  flag: string;
  center: [number, number];
  zoom: number;
  cities: Record<string, [number, number]>;
}

// The city catalogue is intentionally kept in the frontend so the client
// form and the map use the same spelling and coordinates without a geocoder.
export const COUNTRIES: CountryDefinition[] = [
  {
    code: 'TN', name: 'Tunisie', flag: '🇹🇳', center: [34.0, 9.0], zoom: 7,
    cities: {
      Tunis: [36.8065, 10.1815], Ariana: [36.8601, 10.1956], 'Ben Arous': [36.7533, 10.2281], Manouba: [36.81, 10.0987],
      Nabeul: [36.4561, 10.7376], Zaghouan: [36.4028, 10.1428], Bizerte: [37.2744, 9.8739], Béja: [36.7256, 9.1817],
      Jendouba: [36.5011, 8.7803], Kef: [36.1676, 8.7049], Siliana: [36.0847, 9.3711], Sousse: [35.8254, 10.6369],
      Monastir: [35.7643, 10.8113], Mahdia: [35.5047, 11.0622], Sfax: [34.7404, 10.7602], Kairouan: [35.6804, 10.0963],
      Kasserine: [35.1672, 8.8365], 'Sidi Bouzid': [35.038, 9.4849], Gabès: [33.8819, 10.0982], Médenine: [33.354, 10.505],
      Tataouine: [32.9297, 10.4518], Gafsa: [34.425, 8.7842], Tozeur: [33.9197, 8.1339], Kébili: [33.7041, 8.9711],
      Hammamet: [36.4, 10.6167], Tabarka: [36.9541, 8.758], Djerba: [33.8076, 10.8451], Grombalia: [36.6017, 10.5042],
      'La Marsa': [36.8783, 10.3252], Carthage: [36.8528, 10.3233],
    },
  },
  {
    code: 'DZ', name: 'Algérie', flag: '🇩🇿', center: [28.0, 2.5], zoom: 5,
    cities: { Alger: [36.7538, 3.0588], Oran: [35.6971, -0.6308], Constantine: [36.365, 6.6147], Annaba: [36.9, 7.7667], Blida: [36.47, 2.83], Sétif: [36.19, 5.41], Tlemcen: [34.88, -1.32], Béjaïa: [36.75, 5.06], Batna: [35.56, 6.17], Ouargla: [31.95, 5.33] },
  },
  {
    code: 'MA', name: 'Maroc', flag: '🇲🇦', center: [31.8, -6.0], zoom: 5,
    cities: { Rabat: [34.0209, -6.8416], Casablanca: [33.5731, -7.5898], Marrakech: [31.6295, -7.9811], Fès: [34.0331, -5.0003], Tanger: [35.7595, -5.834], Agadir: [30.4278, -9.5981], Oujda: [34.6814, -1.9086], Meknès: [33.8935, -5.5473], Tétouan: [35.5889, -5.3626], Safi: [32.2994, -9.2372] },
  },
  {
    code: 'SN', name: 'Sénégal', flag: '🇸🇳', center: [14.5, -14.5], zoom: 6,
    cities: { Dakar: [14.7167, -17.4677], Thiès: [14.7886, -16.926], 'Saint-Louis': [16.0326, -16.4818], Kaolack: [14.151, -16.0726], Ziguinchor: [12.5833, -16.2719], Touba: [14.85, -15.8833] },
  },
  {
    code: 'FR', name: 'France', flag: '🇫🇷', center: [46.6, 2.2], zoom: 5,
    cities: { Paris: [48.8566, 2.3522], Marseille: [43.2965, 5.3698], Lyon: [45.764, 4.8357], Toulouse: [43.6047, 1.4442], Nice: [43.7102, 7.262], Nantes: [47.2184, -1.5536], Strasbourg: [48.5734, 7.7521], Bordeaux: [44.8378, -0.5792], Lille: [50.6292, 3.0573], Montpellier: [43.6108, 3.8767] },
  },
  {
    code: 'US', name: 'États-Unis', flag: '🇺🇸', center: [39.8, -98.6], zoom: 4,
    cities: { 'New York': [40.7128, -74.006], 'Los Angeles': [34.0522, -118.2437], Chicago: [41.8781, -87.6298], Houston: [29.7604, -95.3698], Miami: [25.7617, -80.1918], Boston: [42.3601, -71.0589], Atlanta: [33.749, -84.388], Dallas: [32.7767, -96.797] },
  },
  {
    code: 'QA', name: 'Qatar', flag: '🇶🇦', center: [25.3, 51.2], zoom: 8,
    cities: { Doha: [25.2854, 51.531], 'Al Rayyan': [25.2919, 51.4244], 'Al Wakrah': [25.1659, 51.5976], 'Al Khor': [25.6804, 51.5058] },
  },
  {
    code: 'SA', name: 'Arabie saoudite', flag: '🇸🇦', center: [24.0, 45.0], zoom: 5,
    cities: { Riyad: [24.7136, 46.6753], Jeddah: [21.5433, 39.1728], Dammam: [26.4207, 50.0888], Médine: [24.5247, 39.5692], 'La Mecque': [21.3891, 39.8579], Abha: [18.2465, 42.5117] },
  },
  { code: 'OTHER', name: 'Autre pays', flag: '🌍', center: [20, 0], zoom: 2, cities: {} },
];

export const DEFAULT_COUNTRY: CountryCode = 'TN';

export function parseCountrySelection(value: unknown, fallback: CountryCode = DEFAULT_COUNTRY): CountryCode[] {
  const rawValues: unknown[] = Array.isArray(value)
    ? value
    : typeof value === 'string' && value.trim().startsWith('[')
      ? (() => {
          try {
            const parsed: unknown = JSON.parse(value);
            return Array.isArray(parsed) ? parsed : [];
          } catch { return []; }
        })()
      : String(value || '').split(',');
  const countries = rawValues
    .map(item => String(item || '').trim())
    .filter(Boolean)
    .filter((item, index, items) => items.indexOf(item) === index);
  return countries.length > 0 ? countries : [fallback];
}

export function findStaticCountry(value: unknown): CountryDefinition | undefined {
  return COUNTRIES.find(country => country.code === value || country.name === value);
}

export function getCountry(value: unknown): CountryDefinition {
  return findStaticCountry(value) || COUNTRIES[0];
}

const CUSTOM_COUNTRY_CENTERS: Array<{ names: string[]; center: [number, number]; zoom: number }> = [
  { names: ['italie', 'italia', 'italy'], center: [41.8719, 12.5674], zoom: 5 },
  { names: ['espagne', 'spain', 'espana'], center: [40.4637, -3.7492], zoom: 5 },
  { names: ['allemagne', 'germany'], center: [51.1657, 10.4515], zoom: 5 },
  { names: ['portugal'], center: [39.3999, -8.2245], zoom: 6 },
  { names: ['belgique', 'belgium'], center: [50.5039, 4.4699], zoom: 7 },
];

export function customCountryCenter(value: unknown): { center: [number, number]; zoom: number } | null {
  const normalized = normalize(String(value || ''));
  const match = CUSTOM_COUNTRY_CENTERS.find(item => item.names.some(name => normalize(name) === normalized));
  return match ? { center: match.center, zoom: match.zoom } : null;
}

export function countryCities(value: unknown): string[] {
  return Object.keys(findStaticCountry(value)?.cities || {});
}

function normalize(value: string): string {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

export function cityCoordinates(countryValue: unknown, cityValue?: string): [number, number] | null {
  if (!cityValue) return null;
  const city = normalize(cityValue);
  const definition = findStaticCountry(countryValue);
  if (!definition) return null;
  const match = Object.entries(definition.cities).find(([name]) => {
    const normalizedName = normalize(name);
    return city === normalizedName || city.includes(normalizedName) || normalizedName.includes(city);
  });
  return match ? match[1] : null;
}
