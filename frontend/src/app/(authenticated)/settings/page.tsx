'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Save, CheckCircle, AlertCircle, Send, Eye, EyeOff, Bot, Headphones, BarChart3, Package } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';

const INPUT = "w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 focus:outline-none";
const LABEL = "block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2";
const CARD = "bg-savia-surface border border-savia-border rounded-xl p-6 space-y-4";

/* ─── Telegram Bot config type ─── */
interface BotConfig {
  key: string;          // config key prefix (e.g. "telegram", "telegram_sav")
  label: string;
  description: string;
  icon: React.ReactNode;
  color: string;        // accent color class
}

const BOTS: BotConfig[] = [
  {
    key: 'telegram',
    label: 'Bot Technicien',
    description: "Alertes d'intervention et notifications terrain",
    icon: <Bot className="w-5 h-5" />,
    color: 'text-blue-400',
  },
  {
    key: 'telegram_sav',
    label: 'Bot Back Office SAV',
    description: 'Notifications du service après-vente et suivi des fiches',
    icon: <Headphones className="w-5 h-5" />,
    color: 'text-emerald-400',
  },
  {
    key: 'telegram_manager',
    label: 'Bot Manager',
    description: 'Rapports, KPI et alertes de supervision',
    icon: <BarChart3 className="w-5 h-5" />,
    color: 'text-purple-400',
  },
  {
    key: 'telegram_stock',
    label: 'Bot Gestionnaire de Stock',
    description: 'Alertes de rupture et mouvements de stock',
    icon: <Package className="w-5 h-5" />,
    color: 'text-amber-400',
  },
];

export default function SettingsPage() {
  const { user } = useAuth();
  const router = useRouter();

  /* ─── Bot state: { telegram: { token, chatId }, telegram_sav: { ... }, ... } ─── */
  const [bots, setBots] = useState<Record<string, { token: string; chatId: string }>>(
    Object.fromEntries(BOTS.map(b => [b.key, { token: '', chatId: '' }]))
  );
  const [showTokens, setShowTokens] = useState<Record<string, boolean>>({});

  const [geminiKey, setGeminiKey] = useState('');
  const [tauxHoraire, setTauxHoraire] = useState('');
  const [orgName, setOrgName] = useState('');
  const [showGemini, setShowGemini] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveErr, setSaveErr] = useState('');
  const [testingBot, setTestingBot] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ key: string; ok: boolean; msg: string } | null>(null);

  // Guard : Admin seulement
  useEffect(() => {
    if (user && user.role !== 'Admin') {
      router.replace('/dashboard');
    }
  }, [user, router]);

  // Load settings
  useEffect(() => {
    const jwtToken = localStorage.getItem('savia_token') || '';
    fetch('/api/settings', {
      headers: jwtToken ? { Authorization: `Bearer ${jwtToken}` } : {},
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        const newBots: Record<string, { token: string; chatId: string }> = {};
        BOTS.forEach(b => {
          newBots[b.key] = {
            token: data[`${b.key}_token`] || data[`${b.key === 'telegram' ? 'telegram' : b.key}_token`] || '',
            chatId: data[`${b.key}_chat_id`] || data[`${b.key === 'telegram' ? 'telegram' : b.key}_chat_id`] || '',
          };
        });
        setBots(newBots);
        setGeminiKey(data.gemini_api_key || '');
        setTauxHoraire(data.taux_horaire_technicien || '');
        setOrgName(data.nom_organisation || 'SIC Radiologie');
      })
      .catch(() => {});
  }, []);

  const setBot = (key: string, field: 'token' | 'chatId', value: string) => {
    setBots(prev => ({ ...prev, [key]: { ...prev[key], [field]: value } }));
  };

  const handleSave = async () => {
    setSaveErr(''); setSaved(false); setSaving(true);
    const jwtToken = localStorage.getItem('savia_token') || '';
    try {
      const payload: Record<string, string> = {
        gemini_api_key: geminiKey,
        taux_horaire_technicien: tauxHoraire,
        nom_organisation: orgName,
      };
      BOTS.forEach(b => {
        payload[`${b.key}_token`] = bots[b.key]?.token || '';
        payload[`${b.key}_chat_id`] = bots[b.key]?.chatId || '';
      });
      const res = await fetch('/api/settings', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(jwtToken ? { Authorization: `Bearer ${jwtToken}` } : {}),
        },
        body: JSON.stringify(payload),
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

  const handleTest = async (botKey: string) => {
    const bot = bots[botKey];
    if (!bot?.token) {
      setTestResult({ key: botKey, ok: false, msg: 'Remplissez le Token avant de tester.' });
      return;
    }
    if (!bot?.chatId) {
      setTestResult({ key: botKey, ok: false, msg: 'Remplissez le Chat ID pour tester l\'envoi.' });
      return;
    }
    setTestingBot(botKey); setTestResult(null);
    await handleSave();
    try {
      const label = BOTS.find(b => b.key === botKey)?.label || 'Bot';
      const res = await fetch(
        `https://api.telegram.org/bot${bot.token}/sendMessage`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: bot.chatId,
            text: `✅ *Test SAVIA — ${label}*\nBot Telegram correctement configuré !`,
            parse_mode: 'Markdown',
          }),
        }
      );
      const data = await res.json();
      if (data.ok) {
        setTestResult({ key: botKey, ok: true, msg: '✅ Message de test envoyé !' });
      } else {
        setTestResult({ key: botKey, ok: false, msg: `❌ ${data.description || 'Vérifiez token et Chat ID'}` });
      }
    } catch (e: any) {
      setTestResult({ key: botKey, ok: false, msg: `❌ Impossible de joindre Telegram : ${e.message}` });
    } finally {
      setTestingBot(null);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in max-w-3xl mx-auto pb-10">
      <div>
        <h1 className="text-2xl font-black gradient-text">⚙️ Paramètres</h1>
        <p className="text-savia-text-muted text-sm mt-1">Configuration de l&apos;application SAVIA</p>
      </div>

      {/* ━━━━ TELEGRAM BOTS ━━━━ */}
      <div className={CARD}>
        <div className="flex items-center gap-3 pb-2 border-b border-savia-border">
          <span className="text-2xl">✈️</span>
          <div>
            <h2 className="font-bold text-base text-savia-text">Bots Telegram</h2>
            <p className="text-xs text-savia-text-muted">Configurez les bots pour chaque profil de notification</p>
          </div>
        </div>

        <div className="space-y-5">
          {BOTS.map(bot => {
            const b = bots[bot.key] || { token: '', chatId: '' };
            const show = showTokens[bot.key] || false;
            const isTesting = testingBot === bot.key;
            const result = testResult?.key === bot.key ? testResult : null;
            const hasToken = !!b.token;

            return (
              <div key={bot.key} className={`rounded-xl border p-4 space-y-3 transition-all ${
                hasToken
                  ? 'border-savia-border/60 bg-savia-surface-hover/30'
                  : 'border-savia-border/30 bg-savia-bg/30'
              }`}>
                {/* Header */}
                <div className="flex items-center gap-3">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${bot.color} bg-current/10`}
                    style={{ backgroundColor: `color-mix(in srgb, currentColor 12%, transparent)` }}>
                    {bot.icon}
                  </div>
                  <div className="flex-1">
                    <h3 className="text-sm font-bold text-savia-text">{bot.label}</h3>
                    <p className="text-xs text-savia-text-muted">{bot.description}</p>
                  </div>
                  {hasToken && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/15 text-green-400 font-semibold">
                      Configuré
                    </span>
                  )}
                </div>

                {/* Token */}
                <div>
                  <label className={LABEL}>🤖 Bot Token</label>
                  <div className="relative">
                    <input
                      type={show ? 'text' : 'password'}
                      className={INPUT + ' pr-10 text-sm'}
                      placeholder="8758714477:AAHu8TyqLaak77z..."
                      value={b.token}
                      onChange={e => setBot(bot.key, 'token', e.target.value)}
                    />
                    <button type="button" onClick={() => setShowTokens(prev => ({ ...prev, [bot.key]: !show }))}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-savia-text-muted hover:text-savia-text">
                      {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* Chat ID (optional) */}
                <div>
                  <label className={LABEL}>💬 Chat ID <span className="text-savia-text-dim font-normal normal-case">(optionnel — direct ou groupe)</span></label>
                  <input
                    type="text"
                    className={INPUT + ' text-sm'}
                    placeholder="6070616462  ou  -1001234567890 (groupe)"
                    value={b.chatId}
                    onChange={e => setBot(bot.key, 'chatId', e.target.value)}
                  />
                </div>

                {/* Test button */}
                <div className="flex items-center gap-3">
                  <button onClick={() => handleTest(bot.key)} disabled={isTesting || !b.token}
                    className="flex items-center gap-2 px-4 py-1.5 rounded-lg border border-savia-border text-savia-text-muted font-semibold text-xs hover:bg-savia-surface-hover hover:text-savia-text transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
                    <Send className="w-3.5 h-3.5" />
                    {isTesting ? 'Envoi...' : 'Tester'}
                  </button>
                  {result && (
                    <span className={`text-xs font-medium ${result.ok ? 'text-green-400' : 'text-red-400'}`}>
                      {result.ok ? <CheckCircle className="w-3.5 h-3.5 inline mr-1" /> : <AlertCircle className="w-3.5 h-3.5 inline mr-1" />}
                      {result.msg}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Guide */}
        <div className="bg-savia-bg/60 border border-savia-border rounded-lg p-4 text-xs space-y-1 text-savia-text-muted">
          <p className="font-bold text-savia-text mb-2">📋 Guide en 3 étapes :</p>
          <p><span className="text-savia-accent font-bold">1.</span> Telegram → cherchez <strong>@BotFather</strong> → <code>/newbot</code> → copiez le token</p>
          <p><span className="text-savia-accent font-bold">2.</span> Envoyez <code>/start</code> à votre bot pour activer le chat</p>
          <p><span className="text-savia-accent font-bold">3.</span> Entrez le Token ci-dessus. Le Chat ID est optionnel si vous utilisez le bot en direct</p>
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
