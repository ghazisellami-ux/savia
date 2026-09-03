const DB_NAME = 'savia-site-offline';
const DB_VERSION = 2;
const CACHE_STORE = 'responses';
const OUTBOX_STORE = 'outbox';
const SESSION_STORE = 'session';

export type OfflineOutboxItem = {
  id: string;
  operationId: string;
  owner: string;
  method: string;
  path: string;
  body?: string;
  file?: Blob;
  fileName?: string;
  contentType?: string;
  createdAt: number;
  attempts: number;
  lastError?: string;
  blocked?: boolean;
};

export type OfflineQueueStats = {
  pending: number;
  failed: number;
  total: number;
};

type CachedResponse = {
  key: string;
  owner: string;
  path: string;
  data: unknown;
  updatedAt: number;
};

function browserAvailable() {
  return typeof window !== 'undefined' && 'indexedDB' in window;
}

function currentOwner() {
  if (!browserAvailable()) return 'anonymous';
  try {
    const raw = window.localStorage.getItem('savia_site_user');
    const user = raw ? JSON.parse(raw) : null;
    return String(user?.username || user?.nom || 'anonymous');
  } catch {
    return 'anonymous';
  }
}

function openDatabase() {
  if (!browserAvailable()) {
    return Promise.reject(new Error('IndexedDB indisponible dans ce navigateur'));
  }
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = window.indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(CACHE_STORE)) {
        const store = db.createObjectStore(CACHE_STORE, { keyPath: 'key' });
        store.createIndex('owner', 'owner', { unique: false });
      }
      if (!db.objectStoreNames.contains(OUTBOX_STORE)) {
        const store = db.createObjectStore(OUTBOX_STORE, { keyPath: 'id' });
        store.createIndex('owner', 'owner', { unique: false });
        store.createIndex('createdAt', 'createdAt', { unique: false });
      }
      if (!db.objectStoreNames.contains(SESSION_STORE)) {
        db.createObjectStore(SESSION_STORE, { keyPath: 'key' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('Impossible d’ouvrir IndexedDB'));
  });
}

async function transaction<T>(
  storeName: string,
  mode: IDBTransactionMode,
  callback: (store: IDBObjectStore) => IDBRequest<T> | void,
) {
  const db = await openDatabase();
  return new Promise<T | undefined>((resolve, reject) => {
    const tx = db.transaction(storeName, mode);
    const store = tx.objectStore(storeName);
    let resultRequest: IDBRequest<T> | void;
    try {
      resultRequest = callback(store);
    } catch (error) {
      reject(error);
      return;
    }
    let result: T | undefined;
    if (resultRequest) {
      resultRequest.onsuccess = () => { result = resultRequest?.result; };
      resultRequest.onerror = () => reject(resultRequest?.error || new Error('IndexedDB request failed'));
    }
    tx.oncomplete = () => { db.close(); resolve(result); };
    tx.onerror = () => { db.close(); reject(tx.error || new Error('IndexedDB transaction failed')); };
    tx.onabort = () => { db.close(); reject(tx.error || new Error('IndexedDB transaction aborted')); };
  });
}

export async function cacheResponse(path: string, data: unknown) {
  const owner = currentOwner();
  const record: CachedResponse = {
    key: `${owner}:${path}`,
    owner,
    path,
    data,
    updatedAt: Date.now(),
  };
  await transaction(CACHE_STORE, 'readwrite', store => store.put(record));
}

export async function syncOfflineSession() {
  if (!browserAvailable()) return;
  const token = window.localStorage.getItem('savia_site_token') || '';
  const lang = window.localStorage.getItem('savia_site_lang') || window.localStorage.getItem('savia_lang') || 'fr';
  if (!token) {
    await transaction(SESSION_STORE, 'readwrite', store => store.delete('current'));
    return;
  }
  await transaction(SESSION_STORE, 'readwrite', store => store.put({
    key: 'current', token, lang, owner: currentOwner(), updatedAt: Date.now(),
  }));
}

export async function readCachedResponse(path: string): Promise<unknown | null> {
  const owner = currentOwner();
  const exact = await transaction<CachedResponse>(CACHE_STORE, 'readonly', store =>
    store.get(`${owner}:${path}`),
  );
  if (exact) return exact.data;

  // A detail page can be opened offline after the technician has only loaded
  // the filtered list. Reuse that list as a safe, already scoped fallback.
  if (path.startsWith('/api/interventions')) {
    const records = await transaction<CachedResponse[]>(CACHE_STORE, 'readonly', store =>
      store.index('owner').getAll(owner),
    );
    const candidate = (records || [])
      .filter(record => record.path.startsWith('/api/interventions'))
      .sort((a, b) => b.updatedAt - a.updatedAt)[0];
    if (candidate) return candidate.data;
  }
  return null;
}

export async function enqueueOffline(item: Omit<OfflineOutboxItem, 'owner' | 'createdAt' | 'attempts'>) {
  const record: OfflineOutboxItem = {
    ...item,
    owner: currentOwner(),
    createdAt: Date.now(),
    attempts: 0,
  };
  await transaction(OUTBOX_STORE, 'readwrite', store => store.put(record));
  return record;
}

export async function listOfflineOutbox() {
  const owner = currentOwner();
  const records = await transaction<OfflineOutboxItem[]>(OUTBOX_STORE, 'readonly', store =>
    store.index('owner').getAll(owner),
  );
  return (records || []).sort((a, b) => a.createdAt - b.createdAt);
}

export async function updateOfflineOutbox(item: OfflineOutboxItem) {
  await transaction(OUTBOX_STORE, 'readwrite', store => store.put(item));
}

export async function unblockOfflineOutbox() {
  const items = await listOfflineOutbox();
  for (const item of items) {
    if (item.blocked) await updateOfflineOutbox({ ...item, blocked: false, lastError: undefined });
  }
}

export async function removeOfflineOutbox(id: string) {
  await transaction(OUTBOX_STORE, 'readwrite', store => store.delete(id));
}

export async function removeBlockedOfflineOutbox() {
  const items = await listOfflineOutbox();
  const blockedItems = items.filter(item => item.blocked);
  await Promise.all(blockedItems.map(item => removeOfflineOutbox(item.id)));
  return blockedItems.length;
}

export async function getOfflineQueueStats(): Promise<OfflineQueueStats> {
  const items = await listOfflineOutbox();
  return {
    pending: items.filter(item => !item.blocked).length,
    failed: items.filter(item => item.blocked).length,
    total: items.length,
  };
}

export function getOfflineOwner() {
  return currentOwner();
}

export async function patchCachedIntervention(interventionId: number, patch: Record<string, unknown>) {
  const owner = currentOwner();
  await transaction(CACHE_STORE, 'readwrite', store => {
    const request = store.index('owner').openCursor(owner);
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return;
      const record = cursor.value as CachedResponse;
      if (record.path.startsWith('/api/interventions') && Array.isArray(record.data)) {
        const data = (record.data as any[]).map(item =>
          Number(item?.id) === interventionId ? { ...item, ...patch, offline_pending: true } : item,
        );
        cursor.update({ ...record, data, updatedAt: Date.now() });
      }
      cursor.continue();
    };
  });
}
