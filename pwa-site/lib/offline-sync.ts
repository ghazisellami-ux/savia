import {
  cacheResponse,
  enqueueOffline,
  getOfflineQueueStats,
  listOfflineOutbox,
  patchCachedIntervention,
  removeBlockedOfflineOutbox,
  removeOfflineOutbox,
  unblockOfflineOutbox,
  updateOfflineOutbox,
  type OfflineOutboxItem,
  type OfflineQueueStats,
} from './offline-db';

export const OFFLINE_EVENT = 'savia_offline_state_changed';
export const SYNC_EVENT = 'savia_offline_sync_complete';
const OFFLINE_STATE_KEY = 'savia_site_offline_state';
const NETWORK_TIMEOUT_MS = 12000;

export function newOperationId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `offline-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function emitOfflineEvent(offline = false) {
  if (typeof window !== 'undefined') {
    if (offline) localStorage.setItem(OFFLINE_STATE_KEY, 'offline');
    else localStorage.removeItem(OFFLINE_STATE_KEY);
    window.dispatchEvent(new CustomEvent(OFFLINE_EVENT, { detail: { offline } }));
  }
}

export function hasPersistedOfflineState() {
  return typeof window !== 'undefined' && localStorage.getItem(OFFLINE_STATE_KEY) === 'offline';
}

export function isTransientNetworkError(error: unknown) {
  const status = Number((error as any)?.status || 0);
  return error instanceof TypeError
    || (error as any)?.name === 'AbortError'
    || (error as any)?.name === 'NetworkError'
    || (typeof navigator !== 'undefined' && !navigator.onLine)
    || [408, 425, 429].includes(status)
    // Only gateway/service availability errors are safe to retry as offline
    // mutations. A generic 500 usually represents a backend validation or
    // database error and must remain visible to the technician.
    || [502, 503, 504].includes(status);
}

export function reportOfflineState(offline: boolean) {
  emitOfflineEvent(offline);
}

export async function checkBackendReachability() {
  if (typeof window === 'undefined' || !navigator.onLine) return false;
  const token = localStorage.getItem('savia_site_token');
  if (!token) return true;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 4000);
  try {
    // A client/server HTTP response proves that the network path is alive.
    // 5xx responses mean that the PWA cannot currently use the API, so they
    // must be treated like an offline state for the technician UI.
    const response = await fetch(`/api/notifications/count?offline_probe=${Date.now()}`, {
      method: 'GET',
      cache: 'no-store',
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    });
    const reachable = response.ok || response.status === 401 || response.status === 403;
    if (reachable) localStorage.removeItem(OFFLINE_STATE_KEY);
    return reachable;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeout);
  }
}

function isNetworkFailure(error: unknown) {
  return isTransientNetworkError(error);
}

function authHeaders() {
  const token = localStorage.getItem('savia_site_token') || '';
  const lang = localStorage.getItem('savia_site_lang') || localStorage.getItem('savia_lang') || 'fr';
  return {
    Authorization: `Bearer ${token}`,
    'X-SAVIA-Lang': lang,
  };
}

export async function queueJsonMutation(path: string, method: string, body: string, patch?: Record<string, unknown>, id = newOperationId()) {
  await enqueueOffline({
    id,
    operationId: id,
    method,
    path,
    body,
  });
  const match = path.match(/^\/api\/interventions\/(\d+)/);
  if (match && patch) {
    await patchCachedIntervention(Number(match[1]), patch).catch(() => undefined);
  }
  emitOfflineEvent(true);
  requestBackgroundSync();
  return { ok: true, queued: true, offline: true, operation_id: id };
}

export async function queuePhoto(path: string, file: File, id = newOperationId()) {
  await enqueueOffline({
    id,
    operationId: id,
    method: 'POST',
    path,
    file,
    fileName: file.name,
    contentType: file.type || 'application/octet-stream',
  });
  const match = path.match(/^\/api\/interventions\/(\d+)/);
  if (match) await patchCachedIntervention(Number(match[1]), {}).catch(() => undefined);
  emitOfflineEvent(true);
  requestBackgroundSync();
  return { ok: true, queued: true, offline: true, operation_id: id };
}

async function sendItem(item: OfflineOutboxItem) {
  const headers: Record<string, string> = {
    ...authHeaders(),
    'X-SAVIA-Operation-Id': item.operationId,
  };
  let body: BodyInit | undefined;
  if (item.file) {
    const form = new FormData();
    form.append('file', item.file, item.fileName || 'fiche');
    body = form;
  } else {
    headers['Content-Type'] = 'application/json';
    body = item.body || '{}';
  }

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), NETWORK_TIMEOUT_MS);
  const response = await fetch(item.path, {
    method: item.method,
    headers,
    body,
    signal: controller.signal,
  });
  window.clearTimeout(timeout);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload?.detail || detail;
    } catch { /* keep status text */ }
    const error = new Error(detail) as Error & { permanent?: boolean };
    error.permanent = ![408, 425, 429, 502, 503, 504].includes(response.status);
    throw error;
  }
  return response;
}

export async function syncOutbox(): Promise<OfflineQueueStats> {
  if (typeof window === 'undefined' || !navigator.onLine) return getOfflineQueueStats();
  // Do not announce a successful/empty synchronization while the API is
  // unreachable. This prevents a second sync pass from replacing the real
  // offline state with "active" when there is nothing queued.
  if (!(await checkBackendReachability())) {
    emitOfflineEvent(true);
    return getOfflineQueueStats();
  }
  const items = await listOfflineOutbox();
  let networkIssue = false;
  for (const item of items) {
    if (item.blocked) continue;
    try {
      await sendItem(item);
      await removeOfflineOutbox(item.id);
    } catch (error: any) {
      const updated = {
        ...item,
        attempts: item.attempts + 1,
        lastError: error?.message || 'Erreur de synchronisation',
        blocked: Boolean(error?.permanent),
      };
      await updateOfflineOutbox(updated);
      networkIssue = isNetworkFailure(error);
      emitOfflineEvent(networkIssue);
      // A network failure means the remaining operations should keep their
      // order and be retried when connectivity returns.
      if (!error?.permanent || isNetworkFailure(error)) break;
    }
  }
  const stats = await getOfflineQueueStats();
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(SYNC_EVENT));
  emitOfflineEvent(networkIssue);
  return stats;
}

export async function readOfflineStats() {
  return getOfflineQueueStats();
}

export async function retryBlockedOfflineOutbox() {
  await unblockOfflineOutbox();
  return syncOutbox();
}

export async function discardBlockedOfflineOutbox() {
  await removeBlockedOfflineOutbox();
  const stats = await getOfflineQueueStats();
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(SYNC_EVENT));
  return stats;
}

export function requestBackgroundSync() {
  if (typeof navigator === 'undefined' || !navigator.serviceWorker) return;
  navigator.serviceWorker.ready
    .then(registration => {
      const syncManager = (registration as ServiceWorkerRegistration & {
        sync?: { register: (tag: string) => Promise<void> };
      }).sync;
      return syncManager?.register('savia-outbox');
    })
    .catch(() => undefined);
}

export async function warmCache(path: string, data: unknown) {
  await cacheResponse(path, data);
}
