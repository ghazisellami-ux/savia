// ==========================================
// 🚀 App — Routing SPA + logique principale
// ==========================================

// --- DOM References ---
const $header = document.getElementById('app-header');
const $bottomNav = document.getElementById('bottom-nav');
const $pageLogin = document.getElementById('page-login');
const $pageList = document.getElementById('page-list');
const $pageForm = document.getElementById('page-form');
const $loginForm = document.getElementById('login-form');
const $loginError = document.getElementById('login-error');
const $userName = document.getElementById('user-name');
const $btnLogout = document.getElementById('btn-logout');
const $btnNewInterv = document.getElementById('btn-new-interv');
const $btnBack = document.getElementById('btn-back');
const $intervList = document.getElementById('interventions-list');
const $intervForm = document.getElementById('intervention-form');
const $filterStatut = document.getElementById('filter-statut');
const $formTitle = document.getElementById('form-title');
const $formClient = document.getElementById('form-client');
const $formMachine = document.getElementById('form-machine');
const $formType = document.getElementById('form-type');
const $diagSection = document.getElementById('diagnostic-section');
const $formTechnicien = document.getElementById('form-technicien');
const $pageNotifs = document.getElementById('page-notifs');
const $notifsList = document.getElementById('notifs-list');
const $notifBadge = document.getElementById('notif-badge');
const $navNotifBadge = document.getElementById('nav-notif-badge');
const $btnNotifs = document.getElementById('btn-notifs');

// --- Global data (for filtering) ---
let allEquipements = [];
let allPieces = [];

// --- State ---
let currentPage = 'login';
let editingIntervention = null;
let capturedPhotoFile = null;

// --- Photo capture handler ---
document.addEventListener('DOMContentLoaded', () => {
    const photoInput = document.getElementById('form-photo');
    if (photoInput) {
        photoInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                capturedPhotoFile = file;
                const reader = new FileReader();
                reader.onload = function(ev) {
                    document.getElementById('photo-preview-img').src = ev.target.result;
                    document.getElementById('photo-preview').style.display = 'block';
                    document.getElementById('btn-remove-photo').style.display = 'inline-block';
                    document.getElementById('btn-take-photo').textContent = '📷 Reprendre la photo';
                };
                reader.readAsDataURL(file);
            }
        });
    }
    // Show/hide photo+validation sections when statut changes
    const statutSelect = document.getElementById('form-statut');
    if (statutSelect) {
        statutSelect.addEventListener('change', updateClotureFields);
    }
});

function updateClotureFields() {
    const statut = (document.getElementById('form-statut').value || '').toLowerCase();
    const isCloture = statut.includes('tur') || statut.includes('clotur') || statut.includes('termin');
    const formId = document.getElementById('form-id').value;
    document.getElementById('photo-section').style.display = (isCloture && formId) ? '' : 'none';
    document.getElementById('validation-section').style.display = (isCloture && formId) ? '' : 'none';
}

function removePhoto() {
    capturedPhotoFile = null;
    document.getElementById('form-photo').value = '';
    document.getElementById('photo-preview').style.display = 'none';
    document.getElementById('btn-remove-photo').style.display = 'none';
    document.getElementById('btn-take-photo').textContent = '📷 Prendre une photo';
}

// --- Helpers ---
function showPage(name) {
    currentPage = name;
    [$pageLogin, $pageList, $pageForm, $pageNotifs].forEach(p => p.classList.remove('active'));
    $pageLogin.classList.add('hidden');
    $pageList.classList.add('hidden');
    $pageForm.classList.add('hidden');
    $pageNotifs.classList.add('hidden');

    const showChrome = name !== 'login';
    $header.classList.toggle('hidden', !showChrome);
    $bottomNav.classList.toggle('hidden', !showChrome);

    switch (name) {
        case 'login':
            $pageLogin.classList.remove('hidden');
            $pageLogin.classList.add('active');
            break;
        case 'list':
            $pageList.classList.remove('hidden');
            $pageList.classList.add('active');
            loadInterventionsList();
            break;
        case 'form':
            $pageForm.classList.remove('hidden');
            $pageForm.classList.add('active');
            break;
        case 'notifs':
            $pageNotifs.classList.remove('hidden');
            $pageNotifs.classList.add('active');
            loadNotifications();
            break;
    }

    // Update nav state
    document.querySelectorAll('.nav-item').forEach(n => {
        n.classList.toggle('active', n.dataset.page === name);
    });
}

function showToast(message, type = 'success') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit' })
            + ' ' + d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    } catch {
        return dateStr.substring(0, 16);
    }
}

function getStatusBadgeClass(statut) {
    const s = (statut || '').toLowerCase();
    if (s.includes('tur')) return 'badge-cloturee';
    if (s.includes('attente')) return 'badge-attente';
    return 'badge-en-cours';
}

function displayStatut(statut) {
    const s = (statut || '').toLowerCase();
    if (s.includes('tur')) return 'Clôturée';
    if (s.includes('attente')) return 'En attente de pièce';
    return 'En cours';
}

// --- Load interventions ---
async function loadInterventionsList() {
    let interventions = [];
    // Récupérer le nom du technicien connecté pour filtrer
    const user = getUser();
    const techName = user?.nom || user?.username || '';

    try {
        if (navigator.onLine && getToken()) {
            interventions = await apiGetInterventions(null, techName);
            await dbPutBulk(STORES.interventions, interventions);
        } else {
            interventions = await dbGetAll(STORES.interventions);
        }
    } catch {
        interventions = await dbGetAll(STORES.interventions);
    }

    // Apply filter — default to 'En cours' if no filter set
    const filterVal = $filterStatut.value || 'En cours';
    if (filterVal && filterVal !== 'Toutes') {
        interventions = interventions.filter(i => {
            const s = (i.statut || '').toLowerCase();
            if (filterVal === 'Cloturee') return s.includes('tur');
            if (filterVal === 'En cours') return !s.includes('tur') && !s.includes('attente');
            if (filterVal === 'En attente de piece') return s.includes('attente');
            return i.statut === filterVal;
        });
    }

    // Sort by date descending
    interventions.sort((a, b) => (b.date || '').localeCompare(a.date || ''));

    renderInterventionsList(interventions);
}

function renderInterventionsList(interventions) {
    if (interventions.length === 0) {
        $intervList.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📋</div>
                <p>Aucune intervention trouvée</p>
            </div>`;
        return;
    }

    $intervList.innerHTML = interventions.map(i => {
        const offlineBadge = i._offline ? '<span class="card-badge badge-offline">hors-ligne</span>' : '';
        return `
        <div class="card" data-id="${i.id}" onclick="openIntervention(${i.id})">
            <div class="card-header">
                <span class="card-machine">${i.machine || '?'}</span>
                <span>
                <span class="card-badge ${getStatusBadgeClass(i.statut)}">${displayStatut(i.statut)}</span>
                    ${offlineBadge}
                </span>
            </div>
            <div class="card-detail">${i.type_intervention || ''} — ${i.technicien || ''}</div>
            <div class="card-detail">${(i.description || '').substring(0, 80)}${(i.description || '').length > 80 ? '...' : ''}</div>
            <div class="card-footer">
                <span>${formatDate(i.date)}</span>
                <span>${i.code_erreur ? '🔴 ' + i.code_erreur : ''}</span>
            </div>
        </div>`;
    }).join('');
}

// --- Populate form selects ---
async function populateFormSelects() {
    let equipements = [];
    let pieces = [];
    let techniciens = [];
    try {
        if (navigator.onLine && getToken()) {
            equipements = await apiGetEquipements();
            await dbPutBulk(STORES.equipements, equipements);
            try {
                pieces = await apiGetPieces();
                await dbPutBulk(STORES.pieces, pieces);
            } catch {
                pieces = await dbGetAll(STORES.pieces);
            }
            try {
                techniciens = await apiGetTechniciens();
                await dbPutBulk(STORES.techniciens, techniciens);
            } catch {
                techniciens = await dbGetAll(STORES.techniciens);
            }
        } else {
            equipements = await dbGetAll(STORES.equipements);
            pieces = await dbGetAll(STORES.pieces);
            techniciens = await dbGetAll(STORES.techniciens);
        }
    } catch {
        equipements = await dbGetAll(STORES.equipements);
        pieces = await dbGetAll(STORES.pieces);
        techniciens = await dbGetAll(STORES.techniciens);
    }

    // Filtrer les équipements : exclure les logs et entrées sans nom valide
    const validEquipements = equipements.filter(e => {
        const nom = (e.Nom || e.nom || '').toLowerCase();
        if (!nom) return false;
        // Exclure les fichiers log, txt, csv
        if (nom.match(/\.(log|txt|csv|xlsx?|pdf|zip)$/i)) return false;
        if (nom.startsWith('log_') || nom.startsWith('logs/')) return false;
        if (nom.includes('/') || nom.includes('\\')) return false;
        return true;
    });

    // Clients uniques (exclure 'Centre Principal' qui est un fallback)
    const clients = [...new Set(validEquipements.map(e => e.Client || e.client).filter(c => c && c !== 'Centre Principal'))].sort();
    $formClient.innerHTML = clients.map(c => `<option value="${c}">${c}</option>`).join('');

    // Store globally for filtering
    allEquipements = validEquipements;
    allPieces = pieces;

    // Initialiser les machines pour le premier client
    updateMachineOptions(validEquipements);

    // Setup techniciens options
    if ($formTechnicien) {
        const techNames = techniciens.map(t => {
            const prenom = t.prenom || '';
            const nom = t.nom || '';
            return (prenom + ' ' + nom).trim() || t.username || '';
        }).filter(n => n);
        $formTechnicien.innerHTML = techNames.map(n =>
            `<option value="${n}">${n}</option>`
        ).join('');

        // Pre-select logged-in technician by default
        const currentUser = getUser();
        const currentName = (currentUser?.nom || currentUser?.username || '').toLowerCase();
        if (currentName) {
            Array.from($formTechnicien.options).forEach(opt => {
                if (opt.value.toLowerCase() === currentName) {
                    opt.selected = true;
                }
            });
        }
    }

    $formClient.addEventListener('change', () => updateMachineOptions(allEquipements));
    $formMachine.addEventListener('change', () => updatePiecesOptions());
}

function updatePiecesOptions() {
    const $formPieces = document.getElementById('form-pieces');
    if (!$formPieces) return;

    // Trouver le type d'équipement de la machine sélectionnée
    const selectedMachine = $formMachine.value;
    const equip = allEquipements.find(e => (e.Nom || e.nom) === selectedMachine);
    const equipType = equip ? (equip.Type || equip.type || '') : '';

    // Filtrer les pièces par type d'équipement
    let filteredPieces = allPieces;
    if (equipType) {
        filteredPieces = allPieces.filter(p => {
            const pieceType = (p.equipement_type || p.type || '').toLowerCase();
            return pieceType === equipType.toLowerCase() || pieceType === '' || pieceType === 'autre';
        });
    }

    // Afficher avec stock actuel
    $formPieces.innerHTML = filteredPieces.map(p => {
        const stock = p.stock_actuel ?? p.quantite ?? 0;
        const stockClass = stock <= 0 ? ' (⚠️ RUPTURE)' : '';
        return `<option value="${p.reference}">[${p.reference}] ${p.designation} — Stock: ${stock}${stockClass}</option>`;
    }).join('');

    if (filteredPieces.length === 0) {
        $formPieces.innerHTML = '<option value="" disabled>Aucune pièce pour ce type</option>';
    }

    // Reset quantity inputs
    updatePiecesQtyInputs();
}

function updateMachineOptions(equipements) {
    const selectedClient = $formClient.value;
    const machines = equipements.filter(e => {
        const client = e.Client || e.client || '';
        return client === selectedClient;
    });
    $formMachine.innerHTML = machines.map(m =>
        `<option value="${m.Nom || m.nom}">${m.Nom || m.nom}</option>`
    ).join('');
    if (machines.length === 0) {
        $formMachine.innerHTML = '<option value="">Aucun équipement</option>';
    }
    // Mettre à jour les pièces selon le type du premier équipement
    updatePiecesOptions();
}

// --- Dynamic quantity inputs for selected pieces ---
function updatePiecesQtyInputs() {
    const $formPieces = document.getElementById('form-pieces');
    const $qtyContainer = document.getElementById('pieces-qty-container');
    if (!$formPieces || !$qtyContainer) return;

    const selectedRefs = Array.from($formPieces.selectedOptions).map(opt => opt.value);

    if (selectedRefs.length === 0) {
        $qtyContainer.innerHTML = '';
        return;
    }

    $qtyContainer.innerHTML = '<label style="font-weight:600; font-size:0.85rem; margin-bottom:4px; display:block;">📦 Quantités utilisées :</label>';
    selectedRefs.forEach(ref => {
        const piece = allPieces.find(p => p.reference === ref);
        const designation = piece ? piece.designation : ref;
        const existingInput = document.getElementById(`qty-${ref}`);
        const currentVal = existingInput ? existingInput.value : 1;

        const row = document.createElement('div');
        row.style.cssText = 'display:flex; align-items:center; gap:8px; margin:4px 0; padding:6px 8px; background:rgba(255,255,255,0.05); border-radius:6px;';
        row.innerHTML = `
            <span style="flex:1; font-size:0.85rem;">${designation}</span>
            <input type="number" id="qty-${ref}" class="piece-qty-input" 
                   min="1" value="${currentVal}" 
                   style="width:60px; padding:4px 8px; border-radius:4px; border:1px solid var(--border); background:var(--bg-card); color:var(--text); text-align:center;">
        `;
        $qtyContainer.appendChild(row);
    });
}

// --- Build pieces_a_deduire array from form ---
function buildPiecesADeduire() {
    const $formPieces = document.getElementById('form-pieces');
    if (!$formPieces) return [];

    const selectedRefs = Array.from($formPieces.selectedOptions).map(opt => opt.value);
    if (selectedRefs.length === 0) return [];

    const result = [];
    selectedRefs.forEach(ref => {
        const piece = allPieces.find(p => p.reference === ref);
        const qtyInput = document.getElementById(`qty-${ref}`);
        const qty = qtyInput ? parseInt(qtyInput.value) || 1 : 1;

        result.push({
            ref: ref,
            qty: qty,
            designation: piece ? piece.designation : ref,
            prix_unitaire: piece ? (piece.prix_unitaire || 0) : 0,
        });
    });
    return result;
}

// --- Open form ---
function openNewIntervention() {
    editingIntervention = null;
    $formTitle.textContent = 'Nouvelle Intervention';
    $intervForm.reset();
    document.getElementById('form-id').value = '';
    document.getElementById('form-statut').value = 'En cours';
    $diagSection.style.display = '';
    populateFormSelects();
    showPage('form');
}

async function openIntervention(id) {
    let interv = null;
    try {
        if (navigator.onLine && getToken()) {
            const all = await apiGetInterventions();
            interv = all.find(i => i.id === id);
        }
    } catch { }
    if (!interv) {
        interv = await dbGet(STORES.interventions, id);
    }
    if (!interv) {
        showToast('Intervention introuvable', 'error');
        return;
    }

    editingIntervention = interv;
    $formTitle.textContent = `Intervention #${id}`;
    await populateFormSelects();

    // Remplir le formulaire
    document.getElementById('form-id').value = id;
    if (interv.notes) {
        const match = interv.notes.match(/\[(.+?)\]/);
        if (match) $formClient.value = match[1];
    }
    // Trigger update machines after setting client
    const equipements = await dbGetAll(STORES.equipements);
    updateMachineOptions(equipements);

    setTimeout(() => {
        $formMachine.value = interv.machine || '';
        // Trigger change event to update pieces filter for the correct machine
        $formMachine.dispatchEvent(new Event('change'));

        document.getElementById('form-type').value = interv.type_intervention || 'Corrective';
        document.getElementById('form-statut').value = interv.statut || 'En cours';
        // Mémoriser le statut original pour forcer la mise à jour
        window._originalStatut = interv.statut || 'En cours';
        document.getElementById('form-description').value = interv.description || '';
        document.getElementById('form-probleme').value = interv.probleme || '';
        document.getElementById('form-cause').value = interv.cause || '';
        document.getElementById('form-solution').value = interv.solution || '';
        document.getElementById('form-duree').value = ((interv.duree_minutes || 0) / 60).toFixed(1);
        document.getElementById('form-deplacement').value = ((interv.deplacement_minutes || 0) / 60).toFixed(1);
        document.getElementById('form-code-erreur').value = interv.code_erreur || '';

        // Multi-select techniciens (handle both "prenom nom" and "nom prenom" formats)
        if ($formTechnicien) {
            const assignedTechs = (interv.technicien || '').split(',').map(t => t.trim());
            Array.from($formTechnicien.options).forEach(opt => {
                const optVal = opt.value.toLowerCase();
                opt.selected = assignedTechs.some(t => {
                    const tLower = t.toLowerCase();
                    if (optVal === tLower) return true;
                    // Try reversed format: "nom prenom" vs "prenom nom"
                    const parts = tLower.split(/\s+/);
                    if (parts.length >= 2) {
                        const reversed = parts.reverse().join(' ');
                        if (optVal === reversed) return true;
                    }
                    return false;
                });
            });
        }

        // Multi-select pieces
        const $formPieces = document.getElementById('form-pieces');
        if ($formPieces) {
            const usedPieces = (interv.pieces_utilisees || '').split(',').map(p => p.trim());
            Array.from($formPieces.options).forEach(opt => {
                opt.selected = usedPieces.includes(opt.value);
            });
        }

        document.getElementById('form-notes').value = interv.notes || '';
        document.getElementById('form-type-erreur').value = interv.type_erreur || '';
        document.getElementById('form-priorite').value = interv.priorite || '';
        // Set validation client
        const valClient = document.getElementById('form-validation-client');
        if (valClient) valClient.value = interv.validation_client || 'En attente';
        // Update cloture-specific fields visibility
        updateClotureFields();
    }, 50);

    // Reset photo state
    capturedPhotoFile = null;
    document.getElementById('form-photo').value = '';
    document.getElementById('photo-preview').style.display = 'none';
    document.getElementById('btn-remove-photo').style.display = 'none';
    document.getElementById('btn-take-photo').textContent = '📷 Prendre une photo';

    // Toggle diagnostic section
    $diagSection.style.display = '';

    showPage('form');
}

// --- Save intervention ---
async function saveIntervention(e) {
    e.preventDefault();

    const formId = document.getElementById('form-id').value;

    // --- Validations obligatoires pour interventions existantes ---
    if (formId) {
        const newStatut = document.getElementById('form-statut').value;
        const dureeVal = parseFloat(document.getElementById('form-duree').value || 0);
        let hasError = false;

        // 1. Obliger la mise à jour du statut
        if (window._originalStatut && newStatut === window._originalStatut) {
            showToast('⚠️ Veuillez mettre à jour le statut avant d\'enregistrer', 'warning');
            const $statut = document.getElementById('form-statut');
            $statut.focus();
            $statut.style.border = '2px solid #ef4444';
            $statut.style.boxShadow = '0 0 8px rgba(239,68,68,0.5)';
            setTimeout(() => { $statut.style.border = ''; $statut.style.boxShadow = ''; }, 4000);
            hasError = true;
        }

        // 2. Obliger de remplir le nombre d'heures de travail
        if (dureeVal <= 0) {
            showToast('⚠️ Veuillez remplir le nombre d\'heures de travail', 'warning');
            const $duree = document.getElementById('form-duree');
            $duree.style.border = '2px solid #ef4444';
            $duree.style.boxShadow = '0 0 8px rgba(239,68,68,0.5)';
            if (!hasError) $duree.focus();
            setTimeout(() => { $duree.style.border = ''; $duree.style.boxShadow = ''; }, 4000);
            hasError = true;
        }

        // 3. Pièce obligatoire si "En attente de pièce"
        const isAttentePiece = newStatut.toLowerCase().includes('attente') && newStatut.toLowerCase().includes('piece');
        if (isAttentePiece) {
            const $pieces = document.getElementById('form-pieces');
            const selectedPieces = $pieces ? Array.from($pieces.selectedOptions) : [];
            if (selectedPieces.length === 0) {
                showToast('⚠️ Sélectionnez la pièce manquante pour recevoir une notification quand elle sera disponible', 'warning');
                if ($pieces) {
                    $pieces.style.border = '2px solid #ef4444';
                    $pieces.style.boxShadow = '0 0 8px rgba(239,68,68,0.5)';
                    $pieces.scrollIntoView({ behavior: 'smooth' });
                    if (!hasError) $pieces.focus();
                    setTimeout(() => { $pieces.style.border = ''; $pieces.style.boxShadow = ''; }, 4000);
                }
                hasError = true;
            }
        }

        // 4. Photo obligatoire si clôture
        const statutLower = newStatut.toLowerCase();
        const isCloture = statutLower.includes('tur') || statutLower.includes('clotur') || statutLower.includes('termin');
        if (isCloture && !capturedPhotoFile) {
            showToast('📸 Photo de la fiche signée obligatoire pour clôturer', 'warning');
            const photoSection = document.getElementById('photo-section');
            photoSection.style.display = '';
            photoSection.style.border = '2px solid #ef4444';
            photoSection.style.boxShadow = '0 0 8px rgba(239,68,68,0.5)';
            photoSection.scrollIntoView({ behavior: 'smooth' });
            setTimeout(() => { photoSection.style.border = ''; photoSection.style.boxShadow = ''; }, 4000);
            hasError = true;
        }

        if (hasError) return;
    }

    const client = $formClient.value;

    // Extract multi-select values for techniciens
    let techStr = "";
    if ($formTechnicien) {
        techStr = Array.from($formTechnicien.selectedOptions).map(opt => opt.value).join(', ');
    }
    if (!techStr) techStr = getUser()?.nom || getUser()?.username || '';

    // Extract multi-select values for pieces
    const $formPieces = document.getElementById('form-pieces');
    let piecesStr = "";
    if ($formPieces) {
        piecesStr = Array.from($formPieces.selectedOptions).map(opt => opt.value).join(', ');
    }

    const data = {
        machine: $formMachine.value,
        client: client,
        type_intervention: document.getElementById('form-type').value,
        statut: document.getElementById('form-statut').value,
        description: document.getElementById('form-description').value,
        probleme: document.getElementById('form-probleme').value,
        cause: document.getElementById('form-cause').value,
        solution: document.getElementById('form-solution').value,
        duree_minutes: Math.round(parseFloat(document.getElementById('form-duree').value || 0) * 60),
        deplacement_minutes: Math.round(parseFloat(document.getElementById('form-deplacement').value || 0) * 60),
        code_erreur: document.getElementById('form-code-erreur').value,
        type_erreur: document.getElementById('form-type-erreur').value,
        priorite: document.getElementById('form-priorite').value,
        pieces_utilisees: piecesStr,
        notes: `[${client}] ` + document.getElementById('form-notes').value,
        technicien: techStr,
        validation_client: document.getElementById('form-validation-client').value || 'En attente',
    };

    // Build pieces_a_deduire for stock deduction when closing
    const statut = data.statut.toLowerCase();
    if (statut.includes('tur') || statut.includes('clotur')) {
        data.pieces_a_deduire = buildPiecesADeduire();
        console.log('[PWA] pieces_a_deduire:', data.pieces_a_deduire);
    }

    try {
        if (navigator.onLine && getToken()) {
            if (formId) {
                await apiUpdateIntervention(parseInt(formId), data);
                // Upload photo si présente
                if (capturedPhotoFile) {
                    try {
                        await apiUploadPhoto(parseInt(formId), capturedPhotoFile);
                        showToast('📸 Photo envoyée', 'success');
                    } catch (photoErr) {
                        showToast(`⚠️ Photo non envoyée: ${photoErr.message}`, 'warning');
                    }
                }
            } else {
                const result = await apiCreateIntervention(data);
                // Upload photo pour nouvelle intervention si ID retourné
                if (capturedPhotoFile && result && result.id) {
                    try {
                        await apiUploadPhoto(result.id, capturedPhotoFile);
                    } catch (photoErr) {
                        console.warn('Photo upload failed:', photoErr);
                    }
                }
            }
            showToast(formId ? '✅ Intervention mise à jour' : '✅ Intervention créée');
        } else {
            // Mode offline
            if (formId) {
                await addToSyncQueue('update_intervention', { intervention_id: parseInt(formId), ...data });
                // Update local copy
                const local = await dbGet(STORES.interventions, parseInt(formId));
                if (local) {
                    Object.assign(local, data, { _offline: true });
                    await dbPut(STORES.interventions, local);
                }
            } else {
                const tempId = Date.now();
                const offlineInterv = {
                    id: tempId,
                    ...data,
                    date: new Date().toISOString(),
                    _offline: true,
                };
                await dbPut(STORES.interventions, offlineInterv);
                await addToSyncQueue('create_intervention', { ...data, date: offlineInterv.date });
            }
            showToast('📱 Enregistré hors-ligne — sera synchronisé', 'success');
        }
    } catch (err) {
        showToast(`❌ Erreur: ${err.message}`, 'error');
        return;
    }

    showPage('list');
}

// --- Toggle diagnostic section visibility ---
function updateDiagnosticVisibility() {
    const type = document.getElementById('form-type').value;
    $diagSection.style.display = (type === 'Corrective') ? '' : 'none';
}

// ==========================================
// 🔔 Notifications
// ==========================================

let notifPollingInterval = null;

async function loadNotifications() {
    if (!navigator.onLine || !getToken()) {
        $notifsList.innerHTML = '<div class="empty-state"><div class="empty-icon">🔔</div><p>Connectez-vous en ligne pour voir les notifications</p></div>';
        return;
    }
    try {
        const notifs = await apiGetNotifications('terrain');
        renderNotifications(notifs);
    } catch (err) {
        console.warn('[NOTIF] Erreur chargement:', err);
        $notifsList.innerHTML = '<div class="empty-state"><div class="empty-icon">⚠️</div><p>Impossible de charger les notifications</p></div>';
    }
}

function renderNotifications(notifs) {
    if (!notifs || notifs.length === 0) {
        $notifsList.innerHTML = '<div class="empty-state"><div class="empty-icon">🔔</div><p>Aucune notification</p></div>';
        return;
    }

    $notifsList.innerHTML = notifs.map(n => {
        const isRupture = n.type === 'piece_rupture';
        const isArrivee = n.type === 'piece_arrivee';
        const icon = isArrivee ? '🟢' : '🚨';
        const typeLabel = isArrivee ? 'Pièce disponible' : 'Rupture de stock';
        const bgClass = n.statut === 'non_lu' ? 'notif-unread' : 'notif-read';
        const dateStr = n.date_creation ? formatDate(n.date_creation) : '';

        return `
        <div class="card notif-card ${bgClass}" data-notif-id="${n.id}">
            <div class="card-header">
                <span class="card-machine">${icon} ${typeLabel}</span>
                <span class="card-badge ${isArrivee ? 'badge-en-cours' : 'badge-attente'}">${n.statut === 'non_lu' ? 'Nouveau' : n.statut}</span>
            </div>
            <div class="card-detail" style="font-weight:600;">📦 ${n.piece_nom || ''} (${n.piece_reference || ''})</div>
            <div class="card-detail">🏥 ${n.equipement || ''} ${n.client ? ' — 🏢 ' + n.client : ''}</div>
            <div class="card-detail">👨‍🔧 ${n.technicien || ''}</div>
            ${n.intervention_ref ? '<div class="card-detail">🔧 ' + n.intervention_ref + '</div>' : ''}
            <div class="card-footer">
                <span>${dateStr}</span>
                ${n.statut === 'non_lu' ? '<button class="btn btn-sm btn-notif-read" onclick="markNotifRead(' + n.id + ')">Marquer lu</button>' : ''}
            </div>
        </div>`;
    }).join('');
}

async function updateNotifBadge() {
    if (!navigator.onLine || !getToken()) return;
    try {
        const result = await apiGetNotificationCount('terrain');
        const count = result.count || 0;
        if (count > 0) {
            $notifBadge.textContent = count;
            $notifBadge.classList.remove('hidden');
            if ($navNotifBadge) {
                $navNotifBadge.textContent = count;
                $navNotifBadge.classList.remove('hidden');
            }
        } else {
            $notifBadge.classList.add('hidden');
            if ($navNotifBadge) $navNotifBadge.classList.add('hidden');
        }
    } catch (err) {
        console.warn('[NOTIF] Badge update failed:', err);
    }
}

async function markNotifRead(notifId) {
    try {
        await apiMarkNotificationRead(notifId);
        showToast('✅ Notification marquée comme lue');
        loadNotifications();
        updateNotifBadge();
    } catch (err) {
        showToast('❌ Erreur: ' + err.message, 'error');
    }
}

function startNotifPolling() {
    if (notifPollingInterval) clearInterval(notifPollingInterval);
    updateNotifBadge();
    notifPollingInterval = setInterval(updateNotifBadge, 30000); // Every 30s
}

// --- Init ---
async function initApp() {
    // Register Service Worker
    if ('serviceWorker' in navigator) {
        try {
            await navigator.serviceWorker.register('/sw.js');
            console.log('[SW] Enregistré');
        } catch (err) {
            console.warn('[SW] Échec:', err);
        }
    }

    // Check network status
    if (!navigator.onLine) {
        document.getElementById('offline-banner').classList.remove('hidden');
    }

    // Check login
    if (isLoggedIn()) {
        const user = getUser();
        $userName.textContent = user?.nom || user?.username || '';
        showPage('list');
        // Download fresh data in background
        downloadAllData();
        updateSyncBadge();
        // Try sync pending
        syncPendingOperations();
        // Start notification polling
        startNotifPolling();
    } else {
        showPage('login');
    }
}

// --- Event Listeners ---
$loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    $loginError.classList.add('hidden');
    const username = document.getElementById('login-user').value.trim();
    const password = document.getElementById('login-pass').value;

    try {
        const user = await handleLogin(username, password);
        $userName.textContent = user.nom || user.username;
        showPage('list');
        downloadAllData();
    } catch (err) {
        $loginError.textContent = err.message;
        $loginError.classList.remove('hidden');
    }
});

$btnLogout.addEventListener('click', handleLogout);

$btnNewInterv.addEventListener('click', openNewIntervention);
document.getElementById('nav-new').addEventListener('click', openNewIntervention);

$btnBack.addEventListener('click', () => showPage('list'));

document.querySelectorAll('.nav-item[data-page="list"]').forEach(el => {
    el.addEventListener('click', () => showPage('list'));
});

// Notification bell click
$btnNotifs.addEventListener('click', () => showPage('notifs'));
document.getElementById('nav-notifs')?.addEventListener('click', () => showPage('notifs'));

$intervForm.addEventListener('submit', saveIntervention);

$filterStatut.addEventListener('change', loadInterventionsList);

document.getElementById('form-type').addEventListener('change', updateDiagnosticVisibility);

// Listen for pieces selection changes to show quantity inputs
document.getElementById('form-pieces')?.addEventListener('change', updatePiecesQtyInputs);

// --- Start ---
initApp();
