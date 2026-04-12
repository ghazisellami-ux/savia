// ==========================================
// ⚡ Service Worker — Cache + Background Sync
// ==========================================

const CACHE_NAME = 'sic-terrain-v14';
const ASSETS = [
    './',
    './index.html',
    './manifest.json',
    './css/app.css',
    './js/config.js',
    './js/db.js',
    './js/api.js',
    './js/sync.js',
    './js/auth.js',
    './js/app.js',
    './icons/icon.svg',
];

// --- Install: cache les assets ---
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(ASSETS))
            .then(() => self.skipWaiting())
    );
});

// --- Activate: supprime les vieux caches ---
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
            )
        ).then(() => self.clients.claim())
    );
});

// --- Fetch: Network First pour TOUT (API + assets) ---
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // API calls: network only (pas de cache)
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request).catch(() => {
                return new Response(
                    JSON.stringify({ error: 'Hors ligne' }),
                    { status: 503, headers: { 'Content-Type': 'application/json' } }
                );
            })
        );
        return;
    }

    // Assets: Network first, fallback cache
    event.respondWith(
        fetch(event.request).then(response => {
            // Mettre en cache la réponse fraîche
            if (response.status === 200) {
                const clone = response.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
            }
            return response;
        }).catch(() => {
            // Offline → servir depuis le cache
            return caches.match(event.request).then(cached => {
                if (cached) return cached;
                // Fallback SPA routing
                if (event.request.mode === 'navigate') {
                    return caches.match('/index.html');
                }
            });
        })
    );
});

// --- Background Sync ---
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-interventions') {
        event.waitUntil(syncFromSW());
    }
});

async function syncFromSW() {
    // On délègue la sync au client (app.js) via un message
    const clients = await self.clients.matchAll();
    clients.forEach(client => {
        client.postMessage({ type: 'SYNC_REQUESTED' });
    });
}
