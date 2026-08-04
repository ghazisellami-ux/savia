'use client';

import { useEffect, useState } from 'react';
import { CloudOff, RefreshCw } from 'lucide-react';
import { listOfflineOutbox } from '@/lib/offline-db';
import { OFFLINE_EVENT, SYNC_EVENT, checkBackendReachability, hasPersistedOfflineState } from '@/lib/offline-sync';

export default function OfflineInterventionBanner({ interventionId }: { interventionId: number }) {
  const [online, setOnline] = useState<boolean | null>(null);
  const [pending, setPending] = useState(0);

  useEffect(() => {
    let active = true;
    let refreshSequence = 0;
    if (hasPersistedOfflineState()) setOnline(false);
    const refresh = async (forcedOffline = false) => {
      const sequence = ++refreshSequence;
      const items = await listOfflineOutbox().catch(() => []);
      const count = items.filter(item =>
        !item.blocked && item.path.startsWith(`/api/interventions/${interventionId}`),
      ).length;
      const token = localStorage.getItem('savia_site_token');
      const reachable = forcedOffline
        ? false
        : navigator.onLine && (token ? await checkBackendReachability() : true);
      if (active && sequence === refreshSequence) {
        setOnline(reachable);
        setPending(count);
      }
    };
    const offline = () => { void refresh(true); };
    const online = () => { void refresh(); };
    const changed = (event?: Event) => {
      const forcedOffline = Boolean((event as CustomEvent | undefined)?.detail?.offline);
      void refresh(forcedOffline);
    };

    window.addEventListener('offline', offline);
    window.addEventListener('online', online);
    window.addEventListener(OFFLINE_EVENT, changed);
    window.addEventListener(SYNC_EVENT, changed);
    void refresh();
    const probeTimer = window.setInterval(() => { void refresh(); }, 5000);
    return () => {
      active = false;
      window.removeEventListener('offline', offline);
      window.removeEventListener('online', online);
      window.removeEventListener(OFFLINE_EVENT, changed);
      window.removeEventListener(SYNC_EVENT, changed);
      window.clearInterval(probeTimer);
    };
  }, [interventionId]);

  // Never display "active" while the browser itself reports no network,
  // even if an older asynchronous probe finished after the offline event.
  const browserOnline = typeof navigator === 'undefined' || navigator.onLine;
  const isOnline = online === true && browserOnline;

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, padding: '12px 14px',
      borderRadius: 12,
      background: isOnline && pending === 0 ? '#F0FDF4' : '#FFF7ED',
      border: `1px solid ${isOnline && pending === 0 ? '#86EFAC' : '#FDBA74'}`,
      color: isOnline && pending === 0 ? '#166534' : '#9A3412',
      fontSize: '0.82rem', fontWeight: 700,
    }}>
      {isOnline && pending === 0 ? <RefreshCw size={18} /> : <CloudOff size={18} />}
      <span>
        {online === null
          ? 'Vérification de la connexion…'
          : isOnline && pending === 0
          ? 'Connexion active — synchronisation disponible'
          : isOnline
          ? `Modification${pending > 1 ? 's' : ''} en attente de synchronisation (${pending})`
          : `Hors connexion${pending ? ` — ${pending} action${pending > 1 ? 's' : ''} en attente ; synchronisation au retour du réseau` : ' — les modifications seront synchronisées au retour du réseau'}`}
      </span>
    </div>
  );
}
