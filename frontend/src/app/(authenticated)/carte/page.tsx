'use client';
// ==========================================
// 🗺️ Carte Géographique — Sites Clients
// ==========================================
import { useState, useEffect, useCallback, useRef } from 'react';
import { SectionCard } from '@/components/ui/cards';
import {
  MapPin, Building2, Loader2, Wrench, Heart, Calendar,
  Edit3, Save, X, Search, AlertTriangle, Cpu,
} from 'lucide-react';
import { mapApi } from '@/lib/api';

// Tunisian cities with approximate GPS coordinates for auto-population
const TUNISIAN_CITIES: Record<string, [number, number]> = {
  'tunis': [36.8065, 10.1815], 'ariana': [36.8601, 10.1956], 'ben arous': [36.7533, 10.2281],
  'manouba': [36.8100, 10.0987], 'nabeul': [36.4561, 10.7376], 'zaghouan': [36.4028, 10.1428],
  'bizerte': [37.2744, 9.8739], 'beja': [36.7256, 9.1817], 'jendouba': [36.5011, 8.7803],
  'kef': [36.1676, 8.7049], 'siliana': [36.0847, 9.3711], 'sousse': [35.8254, 10.6369],
  'monastir': [35.7643, 10.8113], 'mahdia': [35.5047, 11.0622], 'sfax': [34.7404, 10.7602],
  'kairouan': [35.6804, 10.0963], 'kasserine': [35.1672, 8.8365], 'sidi bouzid': [35.0380, 9.4849],
  'gabes': [33.8819, 10.0982], 'medenine': [33.3540, 10.5050], 'tataouine': [32.9297, 10.4518],
  'gafsa': [34.4250, 8.7842], 'tozeur': [33.9197, 8.1339], 'kebili': [33.7041, 8.9711],
  'hammamet': [36.4000, 10.6167], 'tabarka': [36.9541, 8.7580], 'djerba': [33.8076, 10.8451],
  'grombalia': [36.6017, 10.5042], 'la marsa': [36.8783, 10.3252], 'carthage': [36.8528, 10.3233],
};

function guessCoordinates(clientName: string): [number, number] | null {
  const lower = clientName.toLowerCase();
  for (const [city, coords] of Object.entries(TUNISIAN_CITIES)) {
    if (lower.includes(city)) return coords;
  }
  // Default: random position in Tunisia for demo
  return [
    34.5 + Math.random() * 3.5,
    8.5 + Math.random() * 2.5,
  ];
}

interface Site {
  client: string;
  nb_equipements: number;
  latitude: number | null;
  longitude: number | null;
  adresse: string;
  score_sante: number;
  nb_interventions: number;
  prochaine_maintenance: string | null;
  equipements: Array<{ nom: string; type: string; statut: string }>;
}

export default function CartePage() {
  const [sites, setSites] = useState<Site[]>([]);
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

  const load = useCallback(async () => {
    try {
      const data = (await mapApi.sites()) as unknown as Site[];
      // Auto-assign coordinates to sites without them
      const enriched = data.map(s => {
        if (s.latitude && s.longitude) return s;
        const guess = guessCoordinates(s.client);
        return { ...s, latitude: guess ? guess[0] : null, longitude: guess ? guess[1] : null };
      });
      setSites(enriched);
    } catch (err) {
      console.error('Failed to load map sites', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

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

    const map = L.map(mapRef.current).setView([35.5, 9.5], 7);
    mapInstanceRef.current = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap',
      maxZoom: 18,
    }).addTo(map);

    // Clear old markers
    markersRef.current = [];

    // Add markers
    sites.forEach(site => {
      if (!site.latitude || !site.longitude) return;

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

      const marker = L.marker([site.latitude, site.longitude], { icon }).addTo(map);

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
            📍 ${site.adresse || 'Adresse non renseignée'}<br/>
            🔧 ${site.nb_interventions} interventions<br/>
            ${site.prochaine_maintenance ? `📅 Prochaine: ${site.prochaine_maintenance}` : ''}
          </div>
        </div>
      `;

      marker.bindPopup(popupContent);
      marker.on('click', () => setSelectedSite(site));
      markersRef.current.push(marker);
    });

    // Fit bounds
    const validSites = sites.filter(s => s.latitude && s.longitude);
    if (validSites.length > 1) {
      const bounds = L.latLngBounds(validSites.map((s: Site) => [s.latitude!, s.longitude!]));
      map.fitBounds(bounds, { padding: [30, 30] });
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, [mapLoaded, sites, isLoading]);

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
  );

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
          <MapPin className="w-7 h-7" /> Carte du Parc Client
        </h1>
        <p className="text-savia-text-muted text-sm mt-1">Visualisation géographique de vos sites et équipements</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Sites Clients', value: sites.length, color: 'text-savia-accent', icon: <Building2 className="w-5 h-5" /> },
          { label: 'Équipements', value: totalEquip, color: 'text-blue-400', icon: <Cpu className="w-5 h-5" /> },
          { label: 'Score Moyen', value: `${avgScore}%`, color: avgScore >= 70 ? 'text-green-400' : 'text-yellow-400', icon: <Heart className="w-5 h-5" /> },
          { label: 'Sites en alerte', value: sitesAlerte, color: sitesAlerte > 0 ? 'text-red-400' : 'text-green-400', icon: <AlertTriangle className="w-5 h-5" /> },
        ].map(k => (
          <div key={k.label} className="glass rounded-xl p-4 text-center">
            <div className={`${k.color} mx-auto mb-1 flex justify-center`}>{k.icon}</div>
            <div className={`text-3xl font-black ${k.color}`}>{k.value}</div>
            <div className="text-xs text-savia-text-muted mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Map */}
      <SectionCard title={<span className="flex items-center gap-2"><MapPin className="w-4 h-4 text-savia-accent" /> Carte Interactive</span>}>
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
              <div key={site.client} className="glass rounded-xl p-4 hover:border-savia-accent/30 transition-all">
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
                      <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {site.adresse || `${site.latitude?.toFixed(3)}, ${site.longitude?.toFixed(3)}`}</span>
                    </div>
                    {/* Equipment list */}
                    <div className="flex flex-wrap gap-1 mt-2">
                      {site.equipements.map(eq => (
                        <span key={eq.nom} className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
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
