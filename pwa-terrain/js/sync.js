// ==========================================
// 🔄 Sync — Synchronisation offline → serveur
// ==========================================

let _syncInProgress = false;

/**
 * Ajoute une opération à la file d'attente de sync.
 * @param {string} type - 'create_intervention' ou 'update_intervention'
 * @param {object} data - Données de l'opération
 */
async function addToSyncQueue(type, data) {
    const op = {
        id: Date.now() + Math.random(),
        type,
        data,
        createdAt: new Date().toISOString(),
    };
    await dbPut(STORES.syncQueue, op);
    updateSyncBadge();
    return op;
}

/**
 * Nombre d'opérations en attente de sync.
 */
async function getSyncQueueCount() {
    const ops = await dbGetAll(STORES.syncQueue);
    return ops.length;
}

/**
 * Met à jour le badge de sync dans le header.
 */
async function updateSyncBadge() {
    const count = await getSyncQueueCount();
    const badge = document.getElementById('sync-badge');
    if (badge) {
        badge.textContent = count;
        badge.classList.toggle('hidden', count === 0);
    }
}

/**
 * Tente de synchroniser toutes les opérations en attente.
 */
async function syncPendingOperations() {
    if (_syncInProgress || !navigator.onLine) return;
    _syncInProgress = true;

    try {
        const ops = await dbGetAll(STORES.syncQueue);
        if (ops.length === 0) {
            _syncInProgress = false;
            return;
        }

        console.log(`[Sync] ${ops.length} opération(s) en attente...`);

        const result = await apiSync(ops);

        // Supprimer les opérations réussies
        if (result && result.results) {
            for (const r of result.results) {
                if (r.ok) {
                    await dbDelete(STORES.syncQueue, r.op_id);
                }
            }
        }

        // Rafraîchir les données depuis le serveur
        await downloadAllData();
        updateSyncBadge();

        showToast(`✅ ${result.synced || 0} opération(s) synchronisée(s)`, 'success');
    } catch (err) {
        console.error('[Sync] Erreur:', err);
    } finally {
        _syncInProgress = false;
    }
}

/**
 * Télécharge toutes les données depuis le serveur dans IndexedDB.
 */
async function downloadAllData() {
    if (!navigator.onLine || !getToken()) return;

    try {
        const [interventions, equipements, techniciens, pieces] = await Promise.all([
            apiGetInterventions(),
            apiGetEquipements(),
            apiGetTechniciens(),
            apiGetPieces(),
        ]);

        await dbPutBulk(STORES.interventions, interventions);
        await dbPutBulk(STORES.equipements, equipements);
        await dbPutBulk(STORES.techniciens, techniciens);
        await dbPutBulk(STORES.pieces, pieces);

        console.log('[Sync] Données téléchargées:', {
            interventions: interventions.length,
            equipements: equipements.length,
            techniciens: techniciens.length,
            pieces: pieces.length,
        });
    } catch (err) {
        console.error('[Sync] Téléchargement échoué:', err);
    }
}

// --- Listeners réseau ---
window.addEventListener('online', () => {
    console.log('[Network] En ligne');
    document.getElementById('offline-banner').classList.add('hidden');
    syncPendingOperations();
});

window.addEventListener('offline', () => {
    console.log('[Network] Hors ligne');
    document.getElementById('offline-banner').classList.remove('hidden');
});
