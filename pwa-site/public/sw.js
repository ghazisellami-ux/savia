const CACHE_NAME = 'savia-site-shell-v2';
const DB_NAME = 'savia-site-offline';
const DB_VERSION = 2;
const OUTBOX_STORE = 'outbox';
const SESSION_STORE = 'session';
const SHELL_URLS = [
  '/',
  '/login',
  '/interventions',
  '/notifications',
  '/manifest.json',
  '/logo-savia.png',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => Promise.all(SHELL_URLS.map(url => cache.add(url).catch(() => undefined))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key)),
      ))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy)).catch(() => undefined);
          return response;
        })
        .catch(() => caches.match(request).then(cached => cached || caches.match('/interventions'))),
    );
    return;
  }

  // Runtime-cache Next.js chunks, styles and images after the first online use.
  event.respondWith(
    fetch(request)
      .then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy)).catch(() => undefined);
        }
        return response;
      })
      .catch(() => caches.match(request)),
  );
});

self.addEventListener('sync', event => {
  if (event.tag !== 'savia-outbox') return;
  event.waitUntil(processOutbox());
});

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function readStore(storeName, mode, callback) {
  return openDatabase().then(db => new Promise((resolve, reject) => {
    const transaction = db.transaction(storeName, mode);
    const request = callback(transaction.objectStore(storeName));
    let result;
    if (request) request.onsuccess = () => { result = request.result; };
    transaction.oncomplete = () => { db.close(); resolve(result); };
    transaction.onerror = () => { db.close(); reject(transaction.error); };
  }));
}

async function processOutbox() {
  try {
    const openClients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    if (openClients.length) {
      openClients.forEach(client => client.postMessage({ type: 'SAVIA_SYNC_REQUEST' }));
      return;
    }
    const session = await readStore(SESSION_STORE, 'readonly', store => store.get('current'));
    if (!session?.token) return;
    const items = await readStore(OUTBOX_STORE, 'readonly', store => store.index('owner').getAll(session.owner));
    for (const item of (items || []).sort((a, b) => a.createdAt - b.createdAt)) {
      if (item.blocked) continue;
      const headers = {
        Authorization: `Bearer ${session.token}`,
        'X-SAVIA-Lang': session.lang || 'fr',
        'X-SAVIA-Operation-Id': item.operationId,
      };
      let body = item.body || '{}';
      if (item.file) {
        const form = new FormData();
        form.append('file', item.file, item.fileName || 'fiche');
        body = form;
      } else {
        headers['Content-Type'] = 'application/json';
      }
      const response = await fetch(item.path, { method: item.method, headers, body });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await readStore(OUTBOX_STORE, 'readwrite', store => store.delete(item.id));
    }
  } catch {
    // Keep the item in IndexedDB. The browser will retry the Background Sync
    // registration, and the foreground sync will display any final failure.
  }
}
