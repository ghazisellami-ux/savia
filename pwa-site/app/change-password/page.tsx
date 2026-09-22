'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { saveSession } from '@/lib/auth';

export default function ChangePasswordPage() {
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError('');
    if (newPassword !== confirmation) {
      setError('La confirmation ne correspond pas au nouveau mot de passe.');
      return;
    }
    setSaving(true);
    try {
      const result = await api.changePassword(currentPassword, newPassword);
      const previous = JSON.parse(localStorage.getItem('savia_site_user') || '{}');
      saveSession(result.token || localStorage.getItem('savia_site_token') || '', {
        id: previous.id || 0,
        nom: result.user.nom || previous.nom || result.user.username,
        role: result.user.role,
        username: result.user.username,
      });
      router.replace('/interventions');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Impossible de modifier le mot de passe.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <main style={{ minHeight: '100dvh', background: 'var(--beige)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <form onSubmit={submit} style={{ width: '100%', maxWidth: 380, background: '#fff', borderRadius: 16, padding: 24, boxShadow: '0 12px 36px rgba(0,0,0,.12)' }}>
        <h1 style={{ color: 'var(--navy)', fontSize: '1.25rem', fontWeight: 800, marginBottom: 8 }}>Modifier le mot de passe</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '.85rem', marginBottom: 20 }}>Votre mot de passe doit être modifié avant l’accès aux interventions.</p>
        <input type="password" required placeholder="Mot de passe actuel" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} style={inputStyle} />
        <input type="password" required minLength={12} placeholder="Nouveau mot de passe" value={newPassword} onChange={e => setNewPassword(e.target.value)} style={inputStyle} />
        <input type="password" required minLength={12} placeholder="Confirmer le nouveau mot de passe" value={confirmation} onChange={e => setConfirmation(e.target.value)} style={inputStyle} />
        {error && <p style={{ color: 'var(--danger)', fontSize: '.82rem', marginBottom: 12 }}>{error}</p>}
        <button type="submit" disabled={saving} style={{ width: '100%', padding: 12, border: 0, borderRadius: 10, color: '#fff', background: 'linear-gradient(135deg, var(--teal), var(--navy))', fontWeight: 700 }}>
          {saving ? 'Enregistrement...' : 'Enregistrer'}
        </button>
      </form>
    </main>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: 12, marginBottom: 12, border: '1px solid var(--border)', borderRadius: 10,
  color: 'var(--text)', background: '#fff', outline: 'none', boxSizing: 'border-box',
};
