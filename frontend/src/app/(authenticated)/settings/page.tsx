'use client';
import { useState, useEffect } from 'react';
import { Save, CheckCircle, AlertCircle, Send } from 'lucide-react';

const INPUT_CLASS = "w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 focus:outline-none transition-all";
const LABEL_CLASS = "block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2";

async function fetchAPI(path: string, opts: RequestInit = {}) {
  const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
  const res = await fetch(path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opts.headers,
    },
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export default function SettingsPage() {
  const [settings, setSettings] = useState({
    telegram_token: '',
    telegram_chat_id: '',
    gemini_api_key: '',
    taux_horaire_technicien: '',
    nom_organisation: '',
  });
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);
  const [testing, setTesting]   = useState(false);
  const [saved, setSaved]       = useState(false);
  const [error, setError]       = useState('');
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);

  useEffect(() => { loadSettings(); }, []);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const data = await fetchAPI('/api/settings');
      setSettings(prev => ({
        ...prev,
        telegram_token:          data.telegram_token          || '',
        telegram_chat_id:        data.telegram_chat_id        || '',
        gemini_api_key:          data.gemini_api_key          || '',
        taux_horaire_technicien: data.taux_horaire_technicien || '',
        nom_organisation:        data.nom_organisation        || '',
      }));
    } catch {
      setError('Impossible de charger les paramètres.');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setError(''); setSaved(false); setSaving(true);
    try {
      await fetchAPI('/api/settings', { method: 'PUT', body: JSON.stringify(settings) });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      setError('Erreur lors de la sauvegarde.');
    } finally {
      setSaving(false);
    }
  };

  const handleTestTelegram = async () => {
    if (!settings.telegram_token || !settings.telegram_chat_id) {
      setTestResult({ ok: false, msg: 'Token et Chat ID requis avant de tester.' });
      return;
    }
    setTesting(true); setTestResult(null);
    try {
      // Sauvegarder d'abord, puis envoyer un message de test via l'API Telegram
      await fetchAPI('/api/settings', { method: 'PUT', body: JSON.stringify(settings) });
      const url = `https://api.telegram.org/bot${settings.telegram_token}/sendMessage`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: settings.telegram_chat_id,
          text: '✅ *Test SAVIA* — Bot correctement configuré !',
          parse_mode: 'Markdown',
        }),
      });
      const data = await res.json();
      if (data.ok) {
        setTestResult({ ok: true, msg: '✅ Message de test envoyé avec succès !' });
      } else {
        setTestResult({ ok: false, msg: `❌ Erreur Telegram : ${data.description || 'Vérifiez token et chat_id'}` });
      }
    } catch (e: any) {
      setTestResult({ ok: false, msg: `❌ Impossible d'atteindre l'API Telegram : ${e.message}` });
    } finally {
      setTesting(false);
    }
  };

  const set = (k: keyof typeof settings, v: string) => setSettings(prev => ({ ...prev, [k]: v }));

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-pulse text-savia-text-muted">Chargement des paramètres...</div>
    </div>
  );

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl mx-auto">
      <div>
        <h1 className="text-2xl font-black gradient-text">⚙️ Paramètres</h1>
        <p className="text-savia-text-muted text-sm mt-1">Configuration de l&apos;application SAVIA</p>
      </div>

      {/* ─────────── SECTION TELEGRAM ─────────── */}
      <div className="bg-savia-surface border border-savia-border rounded-xl p-6">
        <div className="flex items-center gap-3 mb-5">
          <span className="text-2xl">✈️</span>
          <div>
            <h2 className="font-bold text-lg text-savia-text">Notifications Telegram</h2>
            <p className="text-xs text-savia-text-muted">Les alertes et mises à jour d&apos;intervention seront envoyées sur votre groupe Telegram</p>
          </div>
        </div>

        <div className="space-y-4">
          {/* Bot Token */}
          <div>
            <label className={LABEL_CLASS}>🤖 Bot Token</label>
            <input
              type="password"
              className={INPUT_CLASS}
              placeholder="7455123456:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              value={settings.telegram_token}
              onChange={e => set('telegram_token', e.target.value)}
            />
            <p className="text-xs text-savia-text-muted mt-1">
              Obtenu via <strong>@BotFather</strong> sur Telegram → <code>/newbot</code>
            </p>
          </div>

          {/* Chat ID */}
          <div>
            <label className={LABEL_CLASS}>💬 Chat ID / Groupe ID</label>
            <input
              type="text"
              className={INPUT_CLASS}
              placeholder="-1001234567890"
              value={settings.telegram_chat_id}
              onChange={e => set('telegram_chat_id', e.target.value)}
            />
            <p className="text-xs text-savia-text-muted mt-1">
              Négatif pour les groupes (ex: <code>-1001234567890</code>). Positif pour les messages privés.{' '}
              Trouvez-le via{' '}
              <a
                href={settings.telegram_token ? `https://api.telegram.org/bot${settings.telegram_token}/getUpdates` : 'https://api.telegram.org/bot<VOTRE_TOKEN>/getUpdates'}
                target="_blank"
                rel="noopener noreferrer"
                className="text-savia-accent underline"
              >
                getUpdates API
              </a>
            </p>
          </div>

          {/* Guide rapide */}
          <div className="bg-savia-bg/60 border border-savia-border rounded-lg p-4 text-xs text-savia-text-muted space-y-1">
            <p className="font-bold text-savia-text">📋 Comment configurer en 3 étapes :</p>
            <p>1. Ouvrez Telegram → cherchez <strong>@BotFather</strong> → tapez <code>/newbot</code></p>
            <p>2. Créez un groupe SAVIA Alertes → ajoutez votre bot → envoyez un message</p>
            <p>3. Ouvrez le lien getUpdates ci-dessus → copiez le <code>"id"</code> dans <code>"chat"</code></p>
          </div>

          {/* Bouton test */}
          <button
            type="button"
            onClick={handleTestTelegram}
            disabled={testing || !settings.telegram_token || !settings.telegram_chat_id}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-savia-accent text-savia-accent font-semibold text-sm hover:bg-savia-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send className="w-4 h-4" />
            {testing ? 'Envoi en cours...' : '🧪 Tester la connexion Telegram'}
          </button>

          {testResult && (
            <div className={`flex items-center gap-2 p-3 rounded-lg text-sm font-medium ${testResult.ok ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-red-500/10 text-red-400 border border-red-500/30'}`}>
              {testResult.ok ? <CheckCircle className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
              {testResult.msg}
            </div>
          )}
        </div>
      </div>

      {/* ─────────── SECTION GÉNÉRAL ─────────── */}
      <div className="bg-savia-surface border border-savia-border rounded-xl p-6">
        <div className="flex items-center gap-3 mb-5">
          <span className="text-2xl">🏢</span>
          <h2 className="font-bold text-lg text-savia-text">Organisation</h2>
        </div>
        <div>
          <label className={LABEL_CLASS}>Nom de l&apos;organisation</label>
          <input
            type="text"
            className={INPUT_CLASS}
            placeholder="SIC Radiologie"
            value={settings.nom_organisation}
            onChange={e => set('nom_organisation', e.target.value)}
          />
        </div>
      </div>

      {/* ─────────── SECTION SAV ─────────── */}
      <div className="bg-savia-surface border border-savia-border rounded-xl p-6">
        <div className="flex items-center gap-3 mb-5">
          <span className="text-2xl">🔧</span>
          <h2 className="font-bold text-lg text-savia-text">SAV & Financier</h2>
        </div>
        <div>
          <label className={LABEL_CLASS}>💰 Taux horaire technicien (TND/h)</label>
          <input
            type="number"
            className={INPUT_CLASS}
            placeholder="65"
            value={settings.taux_horaire_technicien}
            onChange={e => set('taux_horaire_technicien', e.target.value)}
          />
        </div>
      </div>

      {/* ─────────── SECTION IA ─────────── */}
      <div className="bg-savia-surface border border-savia-border rounded-xl p-6">
        <div className="flex items-center gap-3 mb-5">
          <span className="text-2xl">🤖</span>
          <h2 className="font-bold text-lg text-savia-text">Intelligence Artificielle</h2>
        </div>
        <div>
          <label className={LABEL_CLASS}>🔑 Clé API Gemini</label>
          <input
            type="password"
            className={INPUT_CLASS}
            placeholder="AIza..."
            value={settings.gemini_api_key}
            onChange={e => set('gemini_api_key', e.target.value)}
          />
          <p className="text-xs text-savia-text-muted mt-1">
            Obtenez votre clé sur{' '}
            <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer" className="text-savia-accent underline">
              Google AI Studio
            </a>
          </p>
        </div>
      </div>

      {/* Erreur globale */}
      {error && (
        <div className="flex items-center gap-2 p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" /> {error}
        </div>
      )}

      {/* Succès */}
      {saved && (
        <div className="flex items-center gap-2 p-4 rounded-lg bg-green-500/10 border border-green-500/30 text-green-400 font-semibold text-sm">
          <CheckCircle className="w-4 h-4" /> Paramètres sauvegardés avec succès !
        </div>
      )}

      {/* Bouton sauvegarde */}
      <button
        onClick={handleSave}
        disabled={saving}
        className="w-full py-3 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60"
      >
        <Save className="w-5 h-5" />
        {saving ? 'Sauvegarde...' : 'Sauvegarder les paramètres'}
      </button>
    </div>
  );
}
