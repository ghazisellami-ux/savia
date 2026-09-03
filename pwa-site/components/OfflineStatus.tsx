'use client';

import { useEffect, useState } from 'react';
import { CloudOff, RefreshCw, Trash2, Wifi } from 'lucide-react';
import { syncOfflineSession } from '@/lib/offline-db';
import { OFFLINE_EVENT, SYNC_EVENT, checkBackendReachability, discardBlockedOfflineOutbox, readOfflineStats, reportOfflineState, retryBlockedOfflineOutbox, syncOutbox } from '@/lib/offline-sync';

type State = {
  online: boolean;
  syncing: boolean;
  pending: number;
  failed: number;
};

export default function OfflineStatus() {
  const [state, setState] = useState<State>({
    online: true,
    syncing: false,
    pending: 0,
    failed: 0,
  });

  const retryFailed = async () => {
    setState(current => ({ ...current, syncing: true }));
    const stats = await retryBlockedOfflineOutbox().catch(() => null);
    if (stats) {
      setState(current => ({ ...current, online: navigator.onLine, syncing: false, ...stats }));
    } else {
      setState(current => ({ ...current, syncing: false }));
    }
  };

  const discardFailed = async () => {
    const confirmed = window.confirm(
      `Retirer ${state.failed} action${state.failed > 1 ? 's' : ''} en erreur ?\n\n` +
      `Elles ne seront plus renvoyées au serveur. Cette opération est irréversible.`,
    );
    if (!confirmed) return;
    const stats = await discardBlockedOfflineOutbox().catch(() => null);
    if (stats) setState(current => ({ ...current, ...stats }));
  };

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      const stats = await readOfflineStats().catch(() => ({ pending: 0, failed: 0, total: 0 }));
      if (active) setState(current => ({ ...current, online: navigator.onLine, ...stats }));
    };
    const sync = async () => {
      if (!navigator.onLine) return;
      const reachable = await checkBackendReachability();
      if (!reachable) {
        reportOfflineState(true);
        if (active) setState(current => ({ ...current, online: false, syncing: false }));
        return;
      }
      if (active) setState(current => ({ ...current, online: true, syncing: true }));
      await syncOutbox().catch(() => undefined);
      if (active) {
        const stats = await readOfflineStats().catch(() => ({ pending: 0, failed: 0, total: 0 }));
        setState({ online: reachable && navigator.onLine, syncing: false, ...stats });
      }
    };
    const goOffline = () => setState(current => ({ ...current, online: false }));
    const goOnline = () => { void sync(); };
    const sessionChanged = () => {
      void syncOfflineSession();
      void retryBlockedOfflineOutbox();
    };
    const probe = async () => {
      const reachable = await checkBackendReachability();
      reportOfflineState(!reachable);
      if (reachable) await refresh();
    };
    const visibilityChanged = () => {
      if (document.visibilityState === 'visible') void probe();
    };
    const changed = (event?: Event) => {
      const offline = Boolean((event as CustomEvent | undefined)?.detail?.offline);
      void readOfflineStats().then(stats => {
        if (active) setState(current => ({ ...current, online: offline ? false : navigator.onLine, ...stats }));
      }).catch(() => undefined);
    };
    const message = (event: MessageEvent) => {
      if (event.data?.type === 'SAVIA_SYNC_REQUEST') void sync();
    };

    window.addEventListener('offline', goOffline);
    window.addEventListener('online', goOnline);
    window.addEventListener(OFFLINE_EVENT, changed);
    window.addEventListener(SYNC_EVENT, changed);
    window.addEventListener('savia_site_session_changed', sessionChanged);
    document.addEventListener('visibilitychange', visibilityChanged);
    navigator.serviceWorker?.addEventListener('message', message);
    navigator.serviceWorker?.register('/sw.js', { scope: '/' }).catch(() => undefined);
    void syncOfflineSession();
    void refresh();
    if (navigator.onLine) void sync();
    const probeTimer = window.setInterval(() => { void probe(); }, 10000);

    return () => {
      active = false;
      window.removeEventListener('offline', goOffline);
      window.removeEventListener('online', goOnline);
      window.removeEventListener(OFFLINE_EVENT, changed);
      window.removeEventListener(SYNC_EVENT, changed);
      window.removeEventListener('savia_site_session_changed', sessionChanged);
      document.removeEventListener('visibilitychange', visibilityChanged);
      window.clearInterval(probeTimer);
      navigator.serviceWorker?.removeEventListener('message', message);
    };
  }, []);

  if (state.online && !state.pending && !state.failed && !state.syncing) return null;

  const hasProblem = !state.online || state.failed > 0;
  return (
    <div style={{
      position: 'fixed', left: 12, right: 12, top: 'calc(var(--header-h, 60px) + 8px)', zIndex: 50,
      display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', borderRadius: 12,
      background: hasProblem ? '#FFF7ED' : '#EFF6FF',
      color: hasProblem ? '#9A3412' : '#1D4ED8',
      border: `1px solid ${hasProblem ? '#FDBA74' : '#93C5FD'}`,
      boxShadow: '0 8px 24px rgba(47,65,86,0.14)', fontSize: '0.78rem', fontWeight: 700,
    }}>
      {hasProblem ? <CloudOff size={17} /> : state.syncing ? <RefreshCw size={17} className="animate-spin" /> : <Wifi size={17} />}
      <span style={{ flex: 1 }}>
        {!state.online
          ? `Hors connexion${state.pending ? ` — ${state.pending} action(s) en attente` : ''}`
          : state.failed
            ? `${state.failed} action(s) à vérifier — synchronisation interrompue`
            : state.syncing
              ? `Synchronisation${state.pending ? ` — ${state.pending} action(s)` : ''}…`
              : `${state.pending} action(s) en attente de synchronisation`}
      </span>
      {state.failed > 0 && (
        <button type="button" onClick={() => void discardFailed()} disabled={state.syncing} aria-label="Retirer les actions en erreur" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, border: 0, background: 'transparent', color: 'inherit', fontWeight: 800, cursor: state.syncing ? 'wait' : 'pointer' }}>
          <Trash2 size={15} /> Retirer
        </button>
      )}
      {state.online && (state.pending || state.failed) > 0 && (
        <button type="button" onClick={() => void retryFailed()} disabled={state.syncing} style={{ border: 0, background: 'transparent', color: 'inherit', fontWeight: 800, cursor: state.syncing ? 'wait' : 'pointer' }}>
          Réessayer
        </button>
      )}
    </div>
  );
}
