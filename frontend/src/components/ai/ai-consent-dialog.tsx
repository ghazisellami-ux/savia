'use client';

import { useEffect, useState } from 'react';
import { Brain, CheckCircle2, ShieldCheck, X } from 'lucide-react';

async function setConsent(accepted: boolean) {
  const response = await fetch('/api/ai/governance/consent', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ accepted }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || error.error || 'Impossible d’enregistrer le consentement.');
  }
}

export default function AiConsentDialog() {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const show = () => { setError(''); setOpen(true); };
    window.addEventListener('savia_ai_consent_required', show);
    return () => window.removeEventListener('savia_ai_consent_required', show);
  }, []);

  const accept = async () => {
    setSaving(true); setError('');
    try {
      await setConsent(true);
      setOpen(false);
    } catch (err: any) {
      setError(err?.message || 'Erreur de consentement.');
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-xl rounded-2xl border border-savia-border bg-savia-surface shadow-2xl">
        <div className="flex items-center justify-between border-b border-savia-border px-6 py-4">
          <h2 className="flex items-center gap-2 text-lg font-black text-savia-text"><Brain className="h-5 w-5 text-purple-400" /> Utilisation de l’IA</h2>
          <button onClick={() => setOpen(false)} className="rounded-lg p-1.5 text-savia-text-muted hover:bg-savia-surface-hover"><X className="h-5 w-5" /></button>
        </div>
        <div className="space-y-4 px-6 py-5 text-sm text-savia-text-muted">
          <p>L&apos;IA reçoit uniquement les données nécessaires à l’analyse demandée. Les recommandations sont indicatives : elles doivent toujours être validées par un professionnel avant toute décision.</p>
          <div className="rounded-xl border border-savia-border bg-savia-bg/40 p-4 space-y-2">
            <p className="flex gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-green-400" /> SAVIA ne conserve ni votre question complète, ni la réponse complète de l&apos;IA dans son journal d’usage.</p>
            <p>Seuls l’utilisateur, la date, la fonctionnalité IA, le modèle, le statut et le compteur mensuel sont enregistrés.</p>
          </div>
          <p>Vous pouvez retirer ce consentement à tout moment depuis Paramètres.</p>
          {error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-3 border-t border-savia-border px-6 py-4">
          <button onClick={() => setOpen(false)} className="rounded-lg px-4 py-2 text-sm font-bold text-savia-text-muted hover:bg-savia-surface-hover">Annuler</button>
          <button onClick={accept} disabled={saving} className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-savia-accent to-blue-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-60"><CheckCircle2 className="h-4 w-4" /> {saving ? 'Enregistrement...' : 'J’ai lu et j’accepte'}</button>
        </div>
      </div>
    </div>
  );
}
