'use client';

import { useState } from 'react';
import { KeyRound, Loader2, ShieldCheck } from 'lucide-react';
import { auth } from '@/lib/api';

export default function ChangePasswordPage() {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    if (newPassword !== confirmation) {
      setError('La confirmation ne correspond pas au nouveau mot de passe.');
      return;
    }

    setLoading(true);
    try {
      const result = await auth.changePassword(currentPassword, newPassword);
      localStorage.setItem('savia_user', JSON.stringify(result.user));
      window.location.assign('/dashboard');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Impossible de modifier le mot de passe.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md glass rounded-2xl p-8 shadow-2xl shadow-black/20">
        <div className="flex justify-center mb-5">
          <div className="w-12 h-12 rounded-xl bg-savia-accent/15 text-savia-accent flex items-center justify-center">
            <KeyRound className="w-6 h-6" />
          </div>
        </div>
        <h1 className="text-xl font-bold text-savia-text text-center">Mise à jour du mot de passe</h1>
        <p className="mt-2 text-sm text-savia-text-muted text-center">
          Votre mot de passe doit être modifié avant d’accéder à SAVIA.
        </p>

        <form onSubmit={handleSubmit} className="mt-7 space-y-4">
          <label className="block">
            <span className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">Mot de passe actuel</span>
            <input
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              autoComplete="current-password"
              required
              className="w-full bg-savia-surface-hover border border-savia-border rounded-lg px-3 py-3 text-savia-text focus:outline-none focus:ring-2 focus:ring-savia-accent/40"
            />
          </label>
          <label className="block">
            <span className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">Nouveau mot de passe</span>
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              autoComplete="new-password"
              minLength={12}
              required
              className="w-full bg-savia-surface-hover border border-savia-border rounded-lg px-3 py-3 text-savia-text focus:outline-none focus:ring-2 focus:ring-savia-accent/40"
            />
          </label>
          <label className="block">
            <span className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">Confirmer le nouveau mot de passe</span>
            <input
              type="password"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="new-password"
              minLength={12}
              required
              className="w-full bg-savia-surface-hover border border-savia-border rounded-lg px-3 py-3 text-savia-text focus:outline-none focus:ring-2 focus:ring-savia-accent/40"
            />
          </label>
          <p className="flex gap-2 text-xs text-savia-text-muted leading-5">
            <ShieldCheck className="w-4 h-4 shrink-0 text-savia-accent" />
            Au moins 12 caractères, avec une minuscule, une majuscule et un chiffre. Il ne doit pas contenir votre identifiant.
          </p>
          {error && <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg font-bold text-savia-text bg-gradient-to-r from-savia-accent to-savia-accent-blue disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Mise à jour...</> : 'Enregistrer le nouveau mot de passe'}
          </button>
        </form>
      </div>
    </div>
  );
}
