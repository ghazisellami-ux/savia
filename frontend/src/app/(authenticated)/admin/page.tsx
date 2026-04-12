'use client';
import { SectionCard } from '@/components/ui/cards';
import { Shield, Users, Plus, Edit2, Trash2 } from 'lucide-react';

const DEMO_USERS = [
  { id: 1, nom: 'Admin SAVIA', email: 'admin@savia.tn', role: 'Admin', client: 'Global', derniereConnexion: '2025-03-18 14:30' },
  { id: 2, nom: 'Ahmed Ben Salah', email: 'ahmed@savia.tn', role: 'Technicien', client: 'Global', derniereConnexion: '2025-03-18 09:15' },
  { id: 3, nom: 'Mehdi Slimani', email: 'mehdi@savia.tn', role: 'Technicien', client: 'Global', derniereConnexion: '2025-03-17 16:45' },
  { id: 4, nom: 'Dr. Ben Ali', email: 'benali@elmanar.tn', role: 'Lecteur', client: 'Clinique El Manar', derniereConnexion: '2025-03-16 11:20' },
  { id: 5, nom: 'Mme Trabelsi', email: 'trabelsi@elmanar.tn', role: 'Lecteur', client: 'Clinique El Manar', derniereConnexion: '2025-03-15 08:00' },
];

export default function AdminPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text">👑 Administration</h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion des utilisateurs et permissions</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
          <Plus className="w-4 h-4" /> Nouvel utilisateur
        </button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-savia-accent">{DEMO_USERS.length}</div><div className="text-xs text-savia-text-muted mt-1">Utilisateurs</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-purple-400">{DEMO_USERS.filter(u => u.role === 'Admin').length}</div><div className="text-xs text-savia-text-muted mt-1">👑 Admins</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-blue-400">{DEMO_USERS.filter(u => u.role === 'Technicien').length}</div><div className="text-xs text-savia-text-muted mt-1">🔧 Techniciens</div></div>
      </div>

      <SectionCard title="👥 Utilisateurs">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-savia-border">
                <th className="text-left py-2 px-3 text-savia-text-muted">Nom</th>
                <th className="text-left py-2 px-3 text-savia-text-muted">Email</th>
                <th className="text-center py-2 px-3 text-savia-text-muted">Rôle</th>
                <th className="text-left py-2 px-3 text-savia-text-muted">Client</th>
                <th className="text-left py-2 px-3 text-savia-text-muted">Dernière connexion</th>
                <th className="text-center py-2 px-3 text-savia-text-muted">Actions</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_USERS.map(u => (
                <tr key={u.id} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                  <td className="py-2.5 px-3 font-semibold">{u.nom}</td>
                  <td className="py-2.5 px-3 text-savia-text-muted">{u.email}</td>
                  <td className="py-2.5 px-3 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${u.role === 'Admin' ? 'bg-purple-500/10 text-purple-400' : u.role === 'Technicien' ? 'bg-blue-500/10 text-blue-400' : 'bg-green-500/10 text-green-400'}`}>{u.role}</span>
                  </td>
                  <td className="py-2.5 px-3 text-sm">{u.client}</td>
                  <td className="py-2.5 px-3 text-xs text-savia-text-dim">{u.derniereConnexion}</td>
                  <td className="py-2.5 px-3 text-center">
                    <div className="flex justify-center gap-1">
                      <button className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 cursor-pointer"><Edit2 className="w-3.5 h-3.5" /></button>
                      <button className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer"><Trash2 className="w-3.5 h-3.5" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
