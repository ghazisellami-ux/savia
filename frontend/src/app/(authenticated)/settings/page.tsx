'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Save, CheckCircle, AlertCircle, Send, Eye, EyeOff } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';

const INPUT = "w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 focus:outline-none";
const LABEL = "block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2";
const CARD = "bg-savia-surface border border-savia-border rounded-xl p-6 space-y-4";

export default function SettingsPage() {
  const { user } = useAuth();
  const router = useRouter();

  const [token,       setToken]       = useState('');
  const [chatId,      setChatId]      = useState('');
  const [geminiKey,   setGeminiKey]   = useState('');
  const [tauxHoraire, setTauxHoraire] = useState('');
  const [orgName,     setOrgName]     = useState('');
  const [showToken,   setShowToken]   = useState(false);
  const [showGemini,  setShowGemini]  = useState(false);
  const [saving,      setSaving]      = useState(false);
  const [testing,     setTesting]     = useState(false);
  const [saved,       setSaved]       = useState(false);
  const [saveErr,     setSaveErr]     = useState('');
  const [testResult,  setTestResult]  = useState<{ ok: boolean; msg: string } | null>(null);

  // Guard : Admin seulement
  useEffect(() => {
    if (user && user.role !== 'Admin') {
      router.replace('/dashboard');
    }
  }, [user, router]);

  // Charger silencieusement — pas de blocage si l'API échoue
  useEffect(() => {
    const jwtToken = localStorage.getItem('savia_token') || '';
    fetch('/api/settings', {
      headers: jwtToken ? { Authorization: `Bearer ${jwtToken}` } : {},
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        setToken(data.telegram_token || '');
        setChatId(data.telegram_chat_id || '');
        setGeminiKey(data.gemini_api_key || '');
        setTauxHoraire(data.taux_horaire_technicien || '');
        setOrgName(data.nom_organisation || 'SIC Radiologie');
      })
      .catch(() => {}); // silencieux
  }, []);

  const handleSave = async () => {
    setSaveErr(''); setSaved(false); setSaving(true);
    const jwtToken = localStorage.getItem('savia_token') || '';
    try {
      const res = await fetch('/api/settings', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(jwtToken ? { Authorization: `Bearer ${jwtToken}` } : {}),
        },
        body: JSON.stringify({
          telegram_token: token,
          telegram_chat_id: chatId,
          gemini_api_key: geminiKey,
          taux_horaire_technicien: tauxHoraire,
          nom_organisation: orgName,
        }),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 4000);
      } else {
        setSaveErr(`Erreur serveur (${res.status})`);
      }
    } catch (e: any) {
      setSaveErr(`Impossible de joindre l'API : ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!token || !chatId) {
      setTestResult({ ok: false, msg: 'Remplissez le Token et le Chat ID avant de tester.' });
      return;
    }
    setTesting(true); setTestResult(null);
    // Sauvegarder d'abord
    await handleSave();
    try {
      const res = await fetch(
        `https://api.telegram.org/bot${token}/sendMessage`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: chatId,
            text: '✅ *Test SAVIA* — Bot Telegram correctement configuré !',
            parse_mode: 'Markdown',
          }),
        }
      );
      const data = await res.json();
      if (data.ok) {
        setTestResult({ ok: true, msg: '✅ Message de test envoyé avec succès dans Telegram !' });
      } else {
        setTestResult({ ok: false, msg: `❌ ${data.description || 'Vérifiez token et Chat ID'}` });
      }
    } catch (e: any) {
      setTestResult({ ok: false, msg: `❌ Impossible de joindre Telegram : ${e.message}` });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl mx-auto pb-10">
      <div>
        <h1 className="text-2xl font-black gradient-text">⚙️ Paramètres</h1>
        <p className="text-savia-text-muted text-sm mt-1">Configuration de l&apos;application SAVIA</p>
      </div>

      {/* ━━━━ TELEGRAM ━━━━ */}
      <div className={CARD}>
        <div className="flex items-center gap-3 pb-2 border-b border-savia-border">
          <span className="text-2xl">✈️</span>
          <div>
            <h2 className="font-bold text-base text-savia-text">Notifications Telegram</h2>
            <p className="text-xs text-savia-text-muted">Alertes d&apos;intervention et ruptures de stock en temps réel</p>
          </div>
        </div>

        {/* Token */}
        <div>
          <label className={LABEL}>🤖 Bot Token</label>
          <div className="relative">
            <input
              type={showToken ? 'text' : 'password'}
              className={INPUT + ' pr-10'}
              placeholder="8758714477:AAHu8TyqLaak77z2WeEMaWLt_INgy_w9abU"
              value={token}
              onChange={e => setToken(e.target.value)}
            />
            <button type="button" onClick={() => setShowToken(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-savia-text-muted hover:text-savia-text">
              {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-xs text-savia-text-muted mt-1">Obtenu via <strong>@BotFather</strong> → <code>/newbot</code></p>
        </div>

        {/* Chat ID */}
        <div>
          <label className={LABEL}>💬 Chat ID</label>
          <input
            type="text"
            className={INPUT}
            placeholder="6070616462  ou  -1001234567890 (groupe)"
            value={chatId}
            onChange={e => setChatId(e.target.value)}
          />
          <p className="text-xs text-savia-text-muted mt-1">
            Votre Chat ID personnel : <strong className="text-savia-accent">6070616462</strong>
            {' '}· Pour un groupe : négatif (ex: <code>-100123...</code>)
          </p>
        </div>

        {/* Bouton test */}
        <button onClick={handleTest} disabled={testing}
          className="flex items-center gap-2 px-5 py-2 rounded-lg border border-savia-accent text-savia-accent font-semibold text-sm hover:bg-savia-accent/10 transition-colors disabled:opacity-40">
          <Send className="w-4 h-4" />
          {testing ? 'Envoi...' : '🧪 Tester la connexion Telegram'}
        </button>

        {testResult && (
          <div className={`flex items-start gap-2 p-3 rounded-lg text-sm font-medium ${testResult.ok ? 'bg-green-500/10 text-green-400 border border-green-500/30' : 'bg-red-500/10 text-red-400 border border-red-500/30'}`}>
            {testResult.ok ? <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" /> : <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />}
            {testResult.msg}
          </div>
        )}

        {/* Guide */}
        <div className="bg-savia-bg/60 border border-savia-border rounded-lg p-4 text-xs space-y-1 text-savia-text-muted">
          <p className="font-bold text-savia-text mb-2">📋 Guide en 3 étapes :</p>
          <p><span className="text-savia-accent font-bold">1.</span> Telegram → cherchez <strong>@BotFather</strong> → <code>/newbot</code> → copiez le token</p>
          <p><span className="text-savia-accent font-bold">2.</span> Envoyez <code>/start</code> à votre bot pour activer le chat</p>
          <p><span className="text-savia-accent font-bold">3.</span> Entrez Token + Chat ID ci-dessus et cliquez Tester</p>
        </div>
      </div>

      {/* ━━━━ ORGANISATION ━━━━ */}
      <div className={CARD}>
        <div className="flex items-center gap-3 pb-2 border-b border-savia-border">
          <span className="text-2xl">🏢</span>
          <h2 className="font-bold text-base text-savia-text">Organisation</h2>
        </div>
        <div>
          <label className={LABEL}>Nom de l&apos;organisation</label>
          <input type="text" className={INPUT} placeholder="SIC Radiologie"
            value={orgName} onChange={e => setOrgName(e.target.value)} />
        </div>
      </div>

      {/* ━━━━ SAV ━━━━ */}
      <div className={CARD}>
        <div className="flex items-center gap-3 pb-2 border-b border-savia-border">
          <span className="text-2xl">🔧</span>
          <h2 className="font-bold text-base text-savia-text">SAV &amp; Financier</h2>
        </div>
        <div>
          <label className={LABEL}>💰 Taux horaire technicien (TND/h)</label>
          <input type="number" className={INPUT} placeholder="65" min={0}
            value={tauxHoraire} onChange={e => setTauxHoraire(e.target.value)} />
        </div>
      </div>

      {/* ━━━━ IA ━━━━ */}
      <div className={CARD}>
        <div className="flex items-center gap-3 pb-2 border-b border-savia-border">
          <span className="text-2xl">🤖</span>
          <h2 className="font-bold text-base text-savia-text">Intelligence Artificielle</h2>
        </div>
        <div>
          <label className={LABEL}>🔑 Clé API Gemini</label>
          <div className="relative">
            <input
              type={showGemini ? 'text' : 'password'}
              className={INPUT + ' pr-10'}
              placeholder="AIzaSy..."
              value={geminiKey}
              onChange={e => setGeminiKey(e.target.value)}
            />
            <button type="button" onClick={() => setShowGemini(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-savia-text-muted hover:text-savia-text">
              {showGemini ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          <p className="text-xs text-savia-text-muted mt-1">
            Obtenez votre clé sur{' '}
            <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer"
              className="text-savia-accent underline">Google AI Studio</a>
          </p>
        </div>
      </div>

      {saveErr && (
        <div className="flex items-center gap-2 p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" /> {saveErr}
        </div>
      )}

      {saved && (
        <div className="flex items-center gap-2 p-4 rounded-lg bg-green-500/10 border border-green-500/30 text-green-400 font-bold text-sm">
          <CheckCircle className="w-4 h-4" /> Paramètres sauvegardés avec succès !
        </div>
      )}

      <button onClick={handleSave} disabled={saving}
        className="w-full py-3 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all flex items-center justify-center gap-2 disabled:opacity-60 cursor-pointer">
        <Save className="w-5 h-5" />
        {saving ? 'Sauvegarde...' : 'Sauvegarder les paramètres'}
      </button>
    </div>
  );
}
