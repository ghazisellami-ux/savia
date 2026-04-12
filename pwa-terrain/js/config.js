// ==========================================
// ⚙️ Config — URL de l'API SIC Terrain
// ==========================================
// Modifier cette URL pour pointer vers le serveur API (Render)
// Si vide, utilise le serveur actuel (PythonAnywhere)

const SIC_API_URL = '';  // Laisse vide pour utiliser l'URL courante (le VPS)

// Forcer la suppression de l'ancienne URL Render en cache chez le client
localStorage.removeItem('SIC_API_URL');
