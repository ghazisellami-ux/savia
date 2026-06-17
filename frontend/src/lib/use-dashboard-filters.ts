import { useState, useEffect, useCallback } from 'react';
import { clients as clientsApi, dashboard } from '@/lib/api';

export interface FilterOptions {
  clients: string[];
  regions: string[];
  villes: string[];
  equipmentTypes: string[];
}

/**
 * Hook personnalisé pour charger les options de filtres dynamiquement
 * Utilise l'API pour récupérer les données existantes
 * Avec caching pour optimiser les performances
 */
export function useDashboardFilters() {
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    clients: [],
    regions: [],
    villes: [],
    equipmentTypes: [],
  });
  const [isLoadingFilters, setIsLoadingFilters] = useState(true);
  
  // Cache pour éviter les appels API répétés
  const [villesCache, setVillesCache] = useState<Record<string, string[]>>({});
  const [clientsCache, setClientsCache] = useState<Record<string, string[]>>({});
  const [equipmentTypesCache, setEquipmentTypesCache] = useState<Record<string, string[]>>({});

  // Charger les filtres au montage
  useEffect(() => {
    loadFilters();
  }, []);

  const loadFilters = useCallback(async () => {
    try {
      setIsLoadingFilters(true);
      
      // Récupérer les régions via l'API dédiée
      const regions = await fetch('/api/dashboard/regions')
        .then(r => r.json())
        .catch(() => []);

      // Filtrer les régions pour s'assurer que seules les 4 régions valides sont affichées
      const VALID_REGIONS = ['Sud', 'Centre', 'Nord', 'International'];
      const filteredRegions = Array.isArray(regions)
        ? regions.filter(r => VALID_REGIONS.includes(r))
        : [];

      // Récupérer tous les clients via l'API dédiée
      const clients = await fetch('/api/dashboard/clients-by-region')
        .then(r => r.json())
        .catch(() => []);

      // Récupérer les types d'équipement via l'API dédiée (sans filtres au démarrage)
      const equipmentTypes = await fetch('/api/dashboard/equipment-types')
        .then(r => r.json())
        .catch(() => []);

      setFilterOptions({
        clients,
        regions: filteredRegions,
        villes: [], // Villes vides au démarrage - chargées dynamiquement
        equipmentTypes: Array.isArray(equipmentTypes) ? equipmentTypes : [],
      });
    } catch (error) {
      console.error('Failed to load filter options:', error);
    } finally {
      setIsLoadingFilters(false);
    }
  }, []);

  /**
   * Récupérer les villes pour une région spécifique
   * Avec caching pour optimiser les performances
   */
  const getVillesForRegion = useCallback(async (region: string): Promise<string[]> => {
    try {
      // Vérifier le cache
      if (villesCache[region]) {
        return villesCache[region];
      }

      // Appel API avec paramètre region - IMPORTANT: region doit être spécifiée
      if (!region) {
        return [];
      }

      const villes = await fetch(`/api/dashboard/villes?region=${encodeURIComponent(region)}`)
        .then(r => r.json())
        .catch(() => []);

      // Filtrer les villes pour exclure les régions
      const filteredVilles = Array.isArray(villes) 
        ? villes.filter(v => v && typeof v === 'string' && !['Sud', 'Centre', 'Nord', 'International'].includes(v))
        : [];

      // Mettre en cache
      setVillesCache(prev => ({
        ...prev,
        [region]: filteredVilles,
      }));

      return filteredVilles;
    } catch (error) {
      console.error('Failed to load villes for region:', error);
      return [];
    }
  }, [villesCache]);

  /**
   * Récupérer les clients pour une région spécifique
   * Avec caching pour optimiser les performances
   */
  const getClientsForRegion = useCallback(async (region: string): Promise<string[]> => {
    try {
      // Vérifier le cache
      if (clientsCache[region]) {
        return clientsCache[region];
      }

      // Appel API avec paramètre region
      const clients = await fetch(`/api/dashboard/clients-by-region?region=${encodeURIComponent(region)}`)
        .then(r => r.json())
        .catch(() => []);

      // Mettre en cache
      setClientsCache(prev => ({
        ...prev,
        [region]: clients,
      }));

      return clients;
    } catch (error) {
      console.error('Failed to load clients for region:', error);
      return [];
    }
  }, [clientsCache]);

  /**
   * Récupérer les types d'équipement filtrés par client, région et ville
   * Avec caching pour optimiser les performances
   */
  const getEquipmentTypesForFilters = useCallback(async (
    client?: string,
    region?: string,
    ville?: string
  ): Promise<string[]> => {
    try {
      // Créer une clé de cache unique
      const cacheKey = `${client || ''}_${region || ''}_${ville || ''}`;
      
      // Vérifier le cache
      if (equipmentTypesCache[cacheKey]) {
        return equipmentTypesCache[cacheKey];
      }

      // Construire les paramètres de requête
      const params = new URLSearchParams();
      if (client) params.set('client', client);
      if (region) params.set('region', region);
      if (ville) params.set('ville', ville);

      // Appel API avec paramètres de filtrage
      const equipmentTypes = await fetch(`/api/dashboard/equipment-types?${params.toString()}`)
        .then(r => r.json())
        .catch(() => []);

      // Mettre en cache
      setEquipmentTypesCache(prev => ({
        ...prev,
        [cacheKey]: equipmentTypes,
      }));

      return Array.isArray(equipmentTypes) ? equipmentTypes : [];
    } catch (error) {
      console.error('Failed to load equipment types for filters:', error);
      return [];
    }
  }, [equipmentTypesCache]);

  return {
    filterOptions,
    isLoadingFilters,
    loadFilters,
    getVillesForRegion,
    getClientsForRegion,
    getEquipmentTypesForFilters,
  };
}
