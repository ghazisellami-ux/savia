'use client';
// ==========================================
// 🗺️ Carte Géographique — Sites Clients
// ==========================================
import { useState, useEffect, useCallback, useRef } from 'react';
import { SectionCard, KpiCard } from '@/components/ui/cards';
import {
  MapPin, Building2, Loader2, Wrench, Heart, Calendar,
  Edit3, Save, X, Search, AlertTriangle, Cpu,
} from 'lucide-react';
import { mapApi, paysCustom as paysCustomApi, villesCustom as villesCustomApi } from '@/lib/api';
import { DEFAULT_COUNTRY, cityCoordinates, customCountryCenter, findStaticCountry, getCountry, parseCountrySelection, type CountryCode } from '@/lib/location-config';

interface Site {
  client: string;
  nb_equipements: number;
  latitude: number | null;
  longitude: number | null;
  adresse: string;
  ville: string;
  score_sante: number;
  nb_interventions: number;
  prochaine_maintenance: string | null;
  equipements: Array<{ nom: string; type: string; statut: string }>;
}

export default function CartePage() {
  const [sites, setSites] = useState<Site[]>([]);
  const [country, setCountry] = useState<CountryCode>(() => (typeof window !== 'undefined' ? (localStorage.getItem('savia_pays') as CountryCode) || DEFAULT_COUNTRY : DEFAULT_COUNTRY));
  const [selectedCountries, setSelectedCountries] = useState<CountryCode[]>(() => (typeof window !== 'undefined' ? parseCountrySelection(localStorage.getItem('savia_pays_selectionnes') || localStorage.getItem('savia_pays')) : [DEFAULT_COUNTRY]));
  const [customCountries, setCustomCountries] = useState<Array<{ id: number; code: string; nom: string; flag?: string; latitude?: number | null; longitude?: number | null }>>([]);
  const [customCities, setCustomCities] = useState<Array<{ nom: string; latitude?: number | null; longitude?: number | null }>>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedSite, setSelectedSite] = useState<Site | null>(null);
  const [editingSite, setEditingSite] = useState<string | null>(null);
  const [editLat, setEditLat] = useState('');
  const [editLng, setEditLng] = useState('');
  const [editAddr, setEditAddr] = useState('');
  const [search, setSearch] = useState('');
  const [mapLoaded, setMapLoaded] = useState(false);
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const selectedCountryName = customCountries.find(item => item.code === country)?.nom || getCountry(country).name;
  const selectedCountryNames = selectedCountries.map(code => customCountries.find(item => item.code === code)?.nom || getCountry(code).name).join(', ');

  const load = useCallback(async () => {
    try {
      const settingsResponse = await fetch('/api/settings/public', { credentials: 'same-origin' });
      const settings = settingsResponse.ok ? await settingsResponse.json() : {};
      const selectedCountriesFromSettings = parseCountrySelection(settings.pays || localStorage.getItem('savia_pays_selectionnes') || localStorage.getItem('savia_pays'));
      const [countryList, cityLists] = await Promise.all([
        paysCustomApi.list().catch(() => []),
        Promise.all(selectedCountriesFromSettings.map(code => villesCustomApi.list(code).catch(() => []))),
      ]);
      const selectedCountry = selectedCountriesFromSettings[0] as CountryCode;
      setCustomCountries(countryList);
      setCustomCities(cityLists.flat());
      setSelectedCountries(selectedCountriesFromSettings);
      setCountry(selectedCountry);
      localStorage.setItem('savia_pays', selectedCountry);
      localStorage.setItem('savia_pays_selectionnes', selectedCountriesFromSettings.join(','));
      const data = (await mapApi.sites(selectedCountriesFromSettings.join(','))) as unknown as Site[];
      // Preserve precise coordinates saved for a client. Only use the city
      // centre when a site genuinely has no location yet.
      const enriched = data.map(s => {
        if (s.latitude != null && s.longitude != null) return s;
        const guess = selectedCountriesFromSettings.reduce<[number, number] | null>((found, selectedCode) => found || cityCoordinates(selectedCode, s.ville) || cityCoordinates(selectedCode, s.client), null);
        if (guess) return { ...s, latitude: guess[0], longitude: guess[1] };
        return { ...s, latitude: null, longitude: null };
      });
      setSites(enriched);
    } catch (err) {
      console.error('Failed to load map sites', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const onCountryChanged = () => { void load(); };
    window.addEventListener('savia_country_changed', onCountryChanged);
    window.addEventListener('savia_settings_changed', onCountryChanged);
    return () => {
      window.removeEventListener('savia_country_changed', onCountryChanged);
      window.removeEventListener('savia_settings_changed', onCountryChanged);
    };
  }, [load]);

  // Load Leaflet dynamically
  useEffect(() => {
    if (typeof window === 'undefined') return;

    // Add Leaflet CSS
    if (!document.getElementById('leaflet-css')) {
      const link = document.createElement('link');
      link.id = 'leaflet-css';
      link.rel = 'stylesheet';
      link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(link);
    }

    // Add Leaflet JS
    if (!(window as any).L) {
      const script = document.createElement('script');
      script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      script.onload = () => setMapLoaded(true);
      document.head.appendChild(script);
    } else {
      setMapLoaded(true);
    }
  }, []);

  // Initialize map when ready
  useEffect(() => {
    if (!mapLoaded || !mapRef.current || isLoading) return;
    const L = (window as any).L;
    if (!L) return;

    // Destroy previous map
    if (mapInstanceRef.current) {
      mapInstanceRef.current.remove();
    }

    const staticCountries = selectedCountries.map(code => findStaticCountry(code)).filter(Boolean);
    const customCountryOptions = selectedCountries.map(code => customCountries.find(item => item.code === code)).filter(Boolean);
    const knownCustomCenters = customCountryOptions.map(item => customCountryCenter(item?.nom)).filter(Boolean);
    const customCityEntries = customCities
      .filter(city => city.latitude != null && city.longitude != null)
      .map(city => [city.nom, [Number(city.latitude), Number(city.longitude)] as [number, number]] as [string, [number, number]]);
    const cityEntries = new Map<string, [number, number]>([
      ...staticCountries.flatMap(item => Object.entries(item!.cities)),
      ...customCityEntries,
    ]);
    const cityCoordinatesForBounds = Array.from(cityEntries.values());
    const countryCenters = [
      ...staticCountries.map(item => item!.center),
      ...customCountryOptions.filter(item => item?.latitude != null && item?.longitude != null).map(item => [Number(item!.latitude), Number(item!.longitude)] as [number, number]),
      ...knownCustomCenters.map(item => item!.center),
    ];
    const customCenter = countryCenters.length > 0
      ? countryCenters.reduce((center, point) => [center[0] + point[0], center[1] + point[1]], [0, 0]).map(value => value / countryCenters.length) as [number, number]
      : cityCoordinatesForBounds.length > 0
      ? cityCoordinatesForBounds.reduce((center, point) => [center[0] + point[0], center[1] + point[1]], [0, 0]).map(value => value / cityCoordinatesForBounds.length) as [number, number]
      : [20, 0] as [number, number];
    const mapCenter = customCenter;
    const mapZoom = selectedCountries.length === 1
      ? (staticCountries[0]?.zoom ?? knownCustomCenters[0]?.zoom ?? (cityCoordinatesForBounds.length > 0 ? 6 : 2))
      : (cityCoordinatesForBounds.length > 0 ? 3 : 2);
    const map = L.map(mapRef.current).setView(mapCenter, mapZoom);
    mapInstanceRef.current = map;

    L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
      attribution: '&copy; <a href="https://www.esri.com/" target="_blank" rel="noopener noreferrer">Esri</a>',
      maxZoom: 19,
    }).addTo(map);

    // Clear old markers
    markersRef.current = [];

    // Always show the cities of the selected country, even when no client is
    // registered there yet. Client sites are rendered above these reference markers.
    Array.from(cityEntries.entries()).forEach(([city, coordinates]) => {
      const cityMarker = L.circleMarker(coordinates, {
        radius: 4,
        color: '#38bdf8',
        weight: 1,
        fillColor: '#38bdf8',
        fillOpacity: 0.65,
      }).addTo(map);
      cityMarker.bindTooltip(city, { direction: 'top', offset: [0, -4], opacity: 0.9 });
      markersRef.current.push(cityMarker);
    });

    // Add markers
    const sitesAtSameCoordinates = new Map<string, number[]>();
    sites.forEach((site, index) => {
      if (site.latitude == null || site.longitude == null) return;
      const key = `${Number(site.latitude).toFixed(6)},${Number(site.longitude).toFixed(6)}`;
      const indexes = sitesAtSameCoordinates.get(key) || [];
      indexes.push(index);
      sitesAtSameCoordinates.set(key, indexes);
    });

    const markerCoordinates = (site: Site, index: number): [number, number] => {
      const latitude = Number(site.latitude);
      const longitude = Number(site.longitude);
      const key = `${latitude.toFixed(6)},${longitude.toFixed(6)}`;
      const collocatedIndexes = sitesAtSameCoordinates.get(key) || [];
      if (collocatedIndexes.length < 2) return [latitude, longitude];

      // Spread only perfectly overlapping pins around their shared location.
      // This keeps precise client coordinates intact while making every client
      // in a city individually selectable after zooming in.
      const position = collocatedIndexes.indexOf(index);
      const ring = Math.floor(position / 8);
      const radius = 0.006 + ring * 0.003;
      const angle = (2 * Math.PI * (position % 8)) / Math.min(collocatedIndexes.length, 8);
      const latitudeOffset = Math.sin(angle) * radius;
      const longitudeOffset = (Math.cos(angle) * radius) / Math.max(Math.cos(latitude * Math.PI / 180), 0.2);
      return [latitude + latitudeOffset, longitude + longitudeOffset];
    };

    sites.forEach((site, index) => {
      if (site.latitude == null || site.longitude == null) return;
      const [markerLatitude, markerLongitude] = markerCoordinates(site, index);

      const score = site.score_sante;
      const color = score >= 80 ? '#22c55e' : score >= 50 ? '#f59e0b' : '#ef4444';
      const pulse = score < 50 ? 'animation: pulse 2s infinite;' : '';

      const icon = L.divIcon({
        className: 'custom-marker',
        html: `<div style="
          width: 32px; height: 32px; border-radius: 50%; 
          background: ${color}; border: 3px solid white;
          box-shadow: 0 2px 8px rgba(0,0,0,0.4), 0 0 12px ${color}40;
          display: flex; align-items: center; justify-content: center;
          color: white; font-weight: 900; font-size: 11px;
          ${pulse}
        ">${site.nb_equipements}</div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
      });

      const marker = L.marker([markerLatitude, markerLongitude], { icon }).addTo(map);

      const popupContent = `
        <div style="min-width: 200px; font-family: system-ui;">
          <div style="font-weight: 800; font-size: 14px; margin-bottom: 4px; color: #0f172a;">${site.client}</div>
          <div style="display: flex; gap: 8px; margin-bottom: 6px;">
            <span style="background: ${color}15; color: ${color}; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700;">
              Santé: ${score}%
            </span>
            <span style="background: #3b82f610; color: #3b82f6; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700;">
              ${site.nb_equipements} équip.
            </span>
          </div>
          <div style="font-size: 11px; color: #64748b;">
            📍 ${site.ville || site.adresse || 'Adresse non renseignée'}<br/>
            🔧 ${site.nb_interventions} interventions<br/>
            ${site.prochaine_maintenance ? `📅 Prochaine: ${site.prochaine_maintenance}` : ''}
          </div>
        </div>
      `;

      marker.bindPopup(popupContent);
      marker.on('click', () => setSelectedSite(site));
      markersRef.current.push(marker);
    });

    // Fit to the country catalogue so the complete selected country remains visible.
    if (cityCoordinatesForBounds.length > 1) {
      const bounds = L.latLngBounds(cityCoordinatesForBounds);
      map.fitBounds(bounds, { padding: [30, 30] });
    } else if (mapCenter) {
      map.setView(mapCenter, mapZoom);
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, [country, selectedCountries, customCities, customCountries, mapLoaded, sites, isLoading]);

  const handleSaveCoords = async (clientName: string) => {
    try {
      await mapApi.updateCoordinates(clientName, {
        latitude: parseFloat(editLat),
        longitude: parseFloat(editLng),
        adresse: editAddr,
      });
      setEditingSite(null);
      await load();
    } catch (err) {
      console.error('Failed to update coordinates', err);
    }
  };

  const filteredSites = sites.filter(s =>
    !search || s.client.toLowerCase().includes(search.toLowerCase())
  ).sort((a, b) => a.score_sante - b.score_sante);

  // Summary KPIs
  const totalEquip = sites.reduce((a, s) => a + s.nb_equipements, 0);
  const avgScore = sites.length > 0 ? Math.round(sites.reduce((a, s) => a + s.score_sante, 0) / sites.length) : 100;
  const sitesAlerte = sites.filter(s => s.score_sante < 50).length;

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-savia-accent" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
          <MapPin className="w-7 h-7" /> Carte du Parc Client — {selectedCountryNames || selectedCountryName}
        </h1>
        <p className="text-savia-text-muted text-sm mt-1">Visualisation géographique de vos sites, équipements et villes du pays sélectionné</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Sites Clients', value: sites.length, color: 'text-savia-accent', icon: <Building2 className="w-5 h-5" /> },
          { label: 'Équipements', value: totalEquip, color: 'text-blue-400', icon: <Cpu className="w-5 h-5" /> },
          { label: 'Score Moyen', value: `${avgScore}%`, color: avgScore >= 70 ? 'text-green-400' : 'text-yellow-400', icon: <Heart className="w-5 h-5" /> },
          { label: 'Sites en alerte', value: sitesAlerte, color: 'text-red-400', icon: <AlertTriangle className="w-5 h-5" /> },
        ].map(k => (
          <KpiCard key={k.label} emphasis appearance="status-stripe" icon={k.icon} value={String(k.value)} label={k.label}
            variant={k.label === 'Sites en alerte' ? (sitesAlerte > 0 ? 'danger' : 'success') : k.label === 'Score Moyen' ? (avgScore >= 70 ? 'success' : 'warning') : 'default'} />
        ))}
      </div>

      {/* Map */}
      <SectionCard title={<span className="flex items-center gap-2"><MapPin className="w-4 h-4 text-savia-accent" /> Carte de {selectedCountryNames || selectedCountryName}</span>}>
        <div className="relative">
          <div ref={mapRef} className="w-full rounded-xl overflow-hidden" style={{ height: 480 }} />
          {/* Legend */}
          <div className="absolute bottom-3 left-3 glass rounded-lg p-3 z-[1000] text-xs space-y-1">
            <div className="font-bold text-savia-text-muted mb-1">Légende</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-green-500" /> Bon (&gt;80%)</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-yellow-500" /> Attention (50-80%)</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-red-500" /> Critique (&lt;50%)</div>
          </div>
        </div>
      </SectionCard>

      {/* Sites List */}
      <SectionCard title={<span className="flex items-center gap-2"><Building2 className="w-4 h-4 text-savia-accent" /> Liste des Sites ({sites.length})</span>}>
        {/* Search */}
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
          <input type="text" placeholder="Rechercher un site..." value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-savia-bg/50 border border-savia-border rounded-lg pl-10 pr-4 py-2 text-savia-text focus:ring-2 focus:ring-savia-accent/40 outline-none text-sm" />
        </div>

        <div className="space-y-3 max-h-[500px] overflow-y-auto">
          {filteredSites.map(site => {
            const score = site.score_sante;
            const isEditing = editingSite === site.client;
            return (
              <div key={site.client} className={`glass rounded-xl p-4 transition-all ${
                score < 50 ? 'border-red-500/50 bg-red-500/5 hover:border-red-500/70' :
                score < 80 ? 'border-yellow-500/30 hover:border-yellow-500/50' :
                'hover:border-savia-accent/30'
              }`}>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <Building2 className="w-4 h-4 text-savia-accent" />
                      <span className="font-bold">{site.client}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                        score >= 80 ? 'bg-green-500/10 text-green-400' :
                        score >= 50 ? 'bg-yellow-500/10 text-yellow-400' :
                        'bg-red-500/10 text-red-400'
                      }`}>{score}%</span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-savia-text-muted flex-wrap">
                      <span className="flex items-center gap-1"><Cpu className="w-3 h-3" /> {site.nb_equipements} équipements</span>
                      <span className="flex items-center gap-1"><Wrench className="w-3 h-3" /> {site.nb_interventions} interventions</span>
                      {site.prochaine_maintenance && (
                        <span className="flex items-center gap-1"><Calendar className="w-3 h-3" /> Prochaine: {site.prochaine_maintenance}</span>
                      )}
                      <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {site.ville || site.adresse || `${site.latitude?.toFixed(3)}, ${site.longitude?.toFixed(3)}`}</span>
                    </div>
                    {/* Equipment list */}
                    <div className="flex flex-wrap gap-1 mt-2">
                      {site.equipements.map((eq, index) => (
                        <span key={`${eq.nom}-${eq.statut}-${index}`} className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                          eq.statut === 'Hors Service' ? 'bg-red-500/10 text-red-400' :
                          eq.statut === 'Critique' ? 'bg-yellow-500/10 text-yellow-400' :
                          'bg-green-500/10 text-green-400'
                        }`}>{eq.nom}</span>
                      ))}
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      if (isEditing) { setEditingSite(null); }
                      else {
                        setEditingSite(site.client);
                        setEditLat(String(site.latitude || ''));
                        setEditLng(String(site.longitude || ''));
                        setEditAddr(site.adresse || '');
                      }
                    }}
                    className="p-2 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted hover:text-savia-accent transition-all cursor-pointer"
                  >
                    {isEditing ? <X className="w-4 h-4" /> : <Edit3 className="w-4 h-4" />}
                  </button>
                </div>

                {/* Edit coordinates form */}
                {isEditing && (
                  <div className="mt-3 pt-3 border-t border-savia-border/40 grid grid-cols-1 sm:grid-cols-4 gap-3">
                    <div>
                      <label className="block text-[10px] font-bold text-savia-text-dim uppercase mb-1">Latitude</label>
                      <input type="number" step="0.0001" value={editLat} onChange={e => setEditLat(e.target.value)}
                        className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-1.5 text-sm text-savia-text outline-none focus:ring-1 focus:ring-savia-accent/40" />
                    </div>
                    <div>
                      <label className="block text-[10px] font-bold text-savia-text-dim uppercase mb-1">Longitude</label>
                      <input type="number" step="0.0001" value={editLng} onChange={e => setEditLng(e.target.value)}
                        className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-1.5 text-sm text-savia-text outline-none focus:ring-1 focus:ring-savia-accent/40" />
                    </div>
                    <div>
                      <label className="block text-[10px] font-bold text-savia-text-dim uppercase mb-1">Adresse</label>
                      <input type="text" value={editAddr} onChange={e => setEditAddr(e.target.value)} placeholder="Rue, Ville..."
                        className="w-full bg-savia-bg border border-savia-border rounded-lg px-3 py-1.5 text-sm text-savia-text outline-none focus:ring-1 focus:ring-savia-accent/40" />
                    </div>
                    <div className="flex items-end">
                      <button onClick={() => handleSaveCoords(site.client)}
                        className="flex items-center gap-1 px-4 py-1.5 rounded-lg text-sm font-bold text-white bg-savia-accent hover:opacity-90 transition-all cursor-pointer">
                        <Save className="w-3.5 h-3.5" /> Sauvegarder
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </SectionCard>
    </div>
  );
}
