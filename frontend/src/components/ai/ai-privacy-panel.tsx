'use client';

import { useEffect, useState } from 'react';
import { Brain, ShieldCheck } from 'lucide-react';

type State = { provider: string; offer_code: string; monthly_quota: number | null; used_this_month: number; consent_required: boolean; ai_enabled: boolean; data_location: string };

export default function AiPrivacyPanel() {
  const [state, setState] = useState<State | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const token = localStorage.getItem('savia_token') || '';
    const res = await fetch('/api/ai/governance/me', { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) setState(await res.json());
  };
  useEffect(() => { load(); }, []);

  const changeConsent = async (accepted: boolean) => {
    setBusy(true); setMessage('');
    try {
      const token = localStorage.getItem('savia_token') || '';
      const res = await fetch('/api/ai/governance/consent', { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify({ accepted }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Erreur de sauvegarde');
      setState(data); setMessage(accepted ? 'Consentement IA enregistré.' : 'Consentement retiré : les analyses IA sont bloquées pour votre compte.');
    } catch (err: any) { setMessage(err?.message || 'Erreur de sauvegarde'); }
    finally { setBusy(false); }
  };

  return (
    <section className="rounded-xl border border-savia-border bg-savia-surface p-5 space-y-4">
      <div className="flex gap-3"><Brain className="h-5 w-5 text-purple-400" /><div><h2 className="font-bold text-savia-text">IA et confidentialité</h2><p className="text-xs text-savia-text-muted mt-1">L&apos;IA fournit des recommandations indicatives, sans modifier les données SAVIA.</p></div></div>
      {state && <div className="grid gap-3 text-xs text-savia-text-muted sm:grid-cols-2"><p><strong className="text-savia-text">Offre :</strong> {state.offer_code}</p><p><strong className="text-savia-text">Quota ce mois :</strong> {state.monthly_quota === null ? 'Illimité' : `${state.used_this_month}/${state.monthly_quota}`}</p><p><strong className="text-savia-text">Fournisseur :</strong> {state.provider}</p><p><strong className="text-savia-text">Localisation :</strong> {state.data_location}</p></div>}
      <div className="rounded-lg bg-savia-bg/60 p-3 text-xs text-savia-text-muted flex gap-2"><ShieldCheck className="h-4 w-4 shrink-0 text-green-400" /> SAVIA conserve le journal d’utilisation technique, mais ni les prompts ni les réponses de l&apos;IA.</div>
      {message && <p className="text-xs text-savia-accent">{message}</p>}
      {state?.ai_enabled === false ? <p className="text-sm text-amber-400">L’accès IA est désactivé par l’administrateur.</p> : state?.consent_required ? <button disabled={busy} onClick={() => changeConsent(true)} className="rounded-lg bg-savia-accent px-4 py-2 text-sm font-bold text-white disabled:opacity-60">{busy ? 'Enregistrement...' : 'Accepter l’utilisation de l’IA'}</button> : <button disabled={busy} onClick={() => changeConsent(false)} className="rounded-lg border border-red-500/40 px-4 py-2 text-sm font-bold text-red-400 disabled:opacity-60">Retirer mon consentement</button>}
    </section>
  );
}
