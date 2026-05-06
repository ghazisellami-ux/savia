'use client';
// ==========================================
// 🔑 Page de Connexion — SAVIA
// ==========================================
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { auth } from '@/lib/api';
import { Lock, User, Loader2 } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await auth.login(username, password);
      localStorage.setItem('savia_token', res.token);
      localStorage.setItem('savia_user', JSON.stringify(res.user));
      router.push('/dashboard');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Erreur de connexion';
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden">
      {/* Mesh gradient background */}
      <div className="login-mesh" />

      {/* Subtle floating particles */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-64 h-64 rounded-full bg-savia-accent/5 blur-3xl animate-pulse" />
        <div className="absolute bottom-1/3 right-1/3 w-96 h-96 rounded-full bg-savia-accent-blue/5 blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      {/* Login Card */}
      <div className="relative z-10 w-full max-w-md mx-4 animate-fade-in">
        <div className="glass rounded-2xl p-8 shadow-2xl shadow-black/20">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="flex justify-center mb-3">
              <Image
                src="/logo-savia.png"
                alt="SAVIA"
                width={360}
                height={234}
                priority
                className="object-contain"
                style={{ maxWidth: '80%', height: 'auto', filter: 'brightness(0) invert(1)' }}
              />
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="login-username" className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
                Identifiant
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
                <input
                  id="login-username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin"
                  className="w-full bg-savia-bg/50 border border-savia-border rounded-lg pl-10 pr-4 py-3
                             text-savia-text placeholder:text-savia-text-dim
                             focus:outline-none focus:ring-2 focus:ring-savia-accent/40 focus:border-savia-accent/40
                             transition-all"
                  required
                  autoComplete="username"
                />
              </div>
            </div>

            <div>
              <label htmlFor="login-password" className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
                Mot de passe
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
                <input
                  id="login-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-savia-bg/50 border border-savia-border rounded-lg pl-10 pr-4 py-3
                             text-savia-text placeholder:text-savia-text-dim
                             focus:outline-none focus:ring-2 focus:ring-savia-accent/40 focus:border-savia-accent/40
                             transition-all"
                  required
                  autoComplete="current-password"
                />
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-savia-danger text-sm animate-fade-in">
                <span>❌</span> {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-lg font-bold text-savia-text
                         bg-gradient-to-r from-savia-accent to-savia-accent-blue
                         hover:from-savia-accent/90 hover:to-savia-accent-blue/90
                         disabled:opacity-50 disabled:cursor-not-allowed
                         transition-all duration-300 shadow-lg shadow-savia-accent/20
                         hover:shadow-xl hover:shadow-savia-accent/30 hover:-translate-y-0.5
                         flex items-center justify-center gap-2 cursor-pointer"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Connexion...
                </>
              ) : (
                'Se connecter'
              )}
            </button>
          </form>

          {/* Footer */}
          <div className="mt-6 pt-4 border-t border-savia-border text-center">
            <p className="text-xs text-savia-text-dim">
              Powered by <span className="gradient-text font-bold">SAVIA</span> · Maintenance Prédictive
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
