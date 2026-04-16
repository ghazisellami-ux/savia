'use client';
import { useState, useEffect, useCallback } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Modal } from '@/components/ui/modal';
import {
  Shield, Users, Plus, Trash2, Loader2, Save,
  X, Eye, EyeOff, Edit2, Crown, UserCog,
  Wrench, BarChart3, Monitor, Hospital, TrendingUp, BookOpen,
  ClipboardList, CalendarDays, Cog, FileText, ClipboardCheck, Settings,
  Radio,
} from 'lucide-react';
import { admin, techniciens } from '@/lib/api';

const INPUT = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-3 py-2 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all text-sm";
const LABEL = "block text-xs font-semibold text-savia-text-muted mb-1 uppercase tracking-wider";

// ─── ALL PAGES (matches sidebar exactly) ──────────────────
const ALL_PAGES: {key: string; label: string; icon: any}[] = [
  { key: 'dashboard',          label: 'Dashboard',               icon: BarChart3      },
  { key: 'supervision',        label: 'Supervision',             icon: Monitor        },
  { key: 'equipements',        label: 'Équipements',             icon: Hospital       },
  { key: 'predictions',        label: 'Prédictions',            icon: TrendingUp     },
  { key: 'base_connaissances', label: 'Base de Connaissances',  icon: BookOpen       },
  { key: 'sav',                label: 'SAV & Interventions',    icon: Wrench         },
  { key: 'demandes',           label: "Demandes d'intervention", icon: ClipboardList  },
  { key: 'planning',           label: 'Planning',               icon: CalendarDays   },
  { key: 'pieces',             label: 'Pièces de Rechange',     icon: Cog            },
  { key: 'reports',            label: 'Rapports & Exports',     icon: FileText       },
  { key: 'contrats',           label: 'Contrats & SLA',         icon: ClipboardCheck },
  { key: 'admin',              label: 'Administration',         icon: Settings       },
];

// ─── DEFAULT PROFILES ─────────────────────────────────────
const DEFAULT_PROFILES: Profile[] = [
  {
    id: 'manager',
    nom: 'Manager',
    couleur: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30',
    description: 'Accès complet à toutes les fonctionnalités',
    pages: ALL_PAGES.map(p => p.key),
  },
  {
    id: 'resp_technique',
    nom: 'Responsable Technique',
    couleur: 'text-blue-400',
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/30',
    description: 'SAV, planning, équipements, rapports',
    pages: ['dashboard', 'supervision', 'equipements', 'sav', 'demandes', 'planning', 'reports', 'base_connaissances'],
  },
  {
    id: 'gestionnaire_stock',
    nom: 'Gestionnaire de Stock',
    couleur: 'text-amber-400',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/30',
    description: 'Pièces de rechange, prédictions, commandes',
    pages: ['dashboard', 'pieces', 'predictions', 'reports'],
  },
  {
    id: 'technicien',
    nom: 'Technicien',
    couleur: 'text-cyan-400',
    bg: 'bg-cyan-500/10',
    border: 'border-cyan-500/30',
    description: 'SAV, planning, équipements, demandes',
    pages: ['dashboard', 'sav', 'demandes', 'equipements', 'planning', 'base_connaissances'],
  },
  {
    id: 'lecteur',
    nom: 'Lecteur',
    couleur: 'text-green-400',
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
    description: 'Consultation uniquement (dashboard, rapports)',
    pages: ['dashboard', 'reports'],
  },
];

const PROFILE_ROLE_MAP: Record<string, string> = {
  manager: 'Admin',
  resp_technique: 'Technicien',
  gestionnaire_stock: 'Gestionnaire',
  technicien: 'Technicien',
  lecteur: 'Lecteur',
};

interface Profile {
  id: string;
  nom: string;
  couleur: string;
  bg: string;
  border: string;
  description: string;
  pages: string[];
}

interface User {
  id: number;
  username: string;
  nom_complet: string;
  role: string;
  client: string;
  actif: number;
  email?: string;
  profileId?: string;
}

interface Technicien { id: number; nom: string; specialite: string; qualification: string; dispo: string; email: string; telephone: string; }

const emptyUser = () => ({
  username: '', password: '', nom_complet: '', email: '', profileId: 'lecteur', client: '', actif: true,
});
const emptyTech = { nom: '', prenom: '', specialite: '', qualification: '', email: '', telephone: '' };

export default function AdminPage() {
  const [tab, setTab] = useState<'users' | 'profiles' | 'techs'>('users');
  const [users, setUsers] = useState<User[]>([]);
  const [techs, setTechs] = useState<Technicien[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>(DEFAULT_PROFILES);
  const [isLoading, setIsLoading] = useState(true);

  // User modal
  const [showUserModal, setShowUserModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [userForm, setUserForm] = useState(emptyUser());
  const [showPassword, setShowPassword] = useState(false);
  const [isSavingUser, setIsSavingUser] = useState(false);
  const [userMsg, setUserMsg] = useState('');

  // Profile edit
  const [editingProfile, setEditingProfile] = useState<Profile | null>(null);

  // Tech modal
  const [showAddTech, setShowAddTech] = useState(false);
  const [techForm, setTechForm] = useState(emptyTech);
  const [isSavingTech, setIsSavingTech] = useState(false);

  const load = useCallback(async () => {
    try {
      const [usersRes, techsRes] = await Promise.all([admin.users(), techniciens.list()]);
      setUsers((usersRes as any[]).map((item: any, i: number) => ({
        id: item.id || i + 1,
        username: item.username || '',
        nom_complet: item.nom_complet || item.nom || '',
        role: item.role || 'Lecteur',
        client: item.client || '',
        actif: item.actif ?? 1,
        email: item.email || '',
        profileId: Object.entries(PROFILE_ROLE_MAP).find(([, r]) => r === item.role)?.[0] || 'lecteur',
      })));
      setTechs((techsRes as any[]).map((item: any) => ({
        id: item.id || 0,
        nom: item.nom_complet || `${item.nom || ''} ${item.prenom || ''}`.trim() || 'N/A',
        specialite: item.specialite || 'Général',
        qualification: item.qualification || '',
        dispo: item.dispo || 'Disponible',
        email: item.email || '',
        telephone: item.telephone || '',
      })));
    } catch (err) { console.error(err); }
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ── Save User ────────────────────────────────────────────
  const handleSaveUser = async () => {
    if (!userForm.username.trim()) { setUserMsg('Nom d\'utilisateur requis.'); return; }
    if (!editingUser && !userForm.password.trim()) { setUserMsg('Mot de passe requis.'); return; }
    setIsSavingUser(true); setUserMsg('');
    try {
      const profile = profiles.find(p => p.id === userForm.profileId) || profiles[profiles.length - 1];
      const role = PROFILE_ROLE_MAP[profile.id] || 'Lecteur';
      const payload: any = {
        username: userForm.username,
        nom_complet: userForm.nom_complet,
        email: userForm.email,
        role,
        client: userForm.client,
        actif: userForm.actif ? 1 : 0,
        profil: profile.nom,
        pages_autorisees: profile.pages.join(','),
      };
      if (userForm.password) payload.password = userForm.password;

      if (editingUser) {
        await (admin as any).updateUser(editingUser.id, payload);
        setUserMsg('✅ Utilisateur mis à jour.');
      } else {
        await (admin as any).createUser(payload);
        setUserMsg('✅ Utilisateur créé avec succès !');
      }
      await load();
      setTimeout(() => { setShowUserModal(false); setUserMsg(''); setEditingUser(null); }, 1500);
    } catch (err: any) {
      setUserMsg(`❌ ${err?.message || 'Erreur serveur'}`);
    } finally { setIsSavingUser(false); }
  };

  const openAdd = () => { setEditingUser(null); setUserForm(emptyUser()); setUserMsg(''); setShowPassword(false); setShowUserModal(true); };
  const openEdit = (u: User) => {
    setEditingUser(u);
    setUserForm({ username: u.username, password: '', nom_complet: u.nom_complet, email: u.email || '', profileId: u.profileId || 'lecteur', client: u.client, actif: u.actif === 1 });
    setUserMsg(''); setShowPassword(false); setShowUserModal(true);
  };
  const handleDeleteUser = async (id: number) => {
    if (!confirm('Supprimer cet utilisateur ?')) return;
    try { await (admin as any).deleteUser(id); await load(); } catch { /* noop */ }
  };

  // ── Save Tech ────────────────────────────────────────────
  const handleSaveTech = async () => {
    if (!techForm.nom.trim()) return;
    setIsSavingTech(true);
    try { await techniciens.create(techForm); setTechForm(emptyTech); setShowAddTech(false); await load(); }
    catch { /* noop */ } finally { setIsSavingTech(false); }
  };
  const handleDeleteTech = async (id: number) => {
    if (!confirm('Supprimer ce technicien ?')) return;
    try { await techniciens.delete(id); await load(); } catch { /* noop */ }
  };

  // ── Profile page toggle ───────────────────────────────────
  const togglePage = (profileId: string, pageKey: string) => {
    setProfiles(prev => prev.map(p => p.id !== profileId ? p : {
      ...p, pages: p.pages.includes(pageKey) ? p.pages.filter(k => k !== pageKey) : [...p.pages, pageKey]
    }));
  };

  const roleColor = (role: string) => {
    if (role === 'Admin') return 'bg-purple-500/10 text-purple-400';
    if (role === 'Technicien') return 'bg-blue-500/10 text-blue-400';
    if (role === 'Gestionnaire') return 'bg-amber-500/10 text-amber-400';
    return 'bg-green-500/10 text-green-400';
  };

  if (isLoading) return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text flex items-center gap-2">
            <Crown className="w-7 h-7 text-savia-accent" /> Administration
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion des utilisateurs, profils et permissions</p>
        </div>
        <div className="flex gap-2">
          {tab === 'users' && (
            <button onClick={openAdd} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-cyan-500/20">
              <Plus className="w-4 h-4" /> Nouvel utilisateur
            </button>
          )}
          {tab === 'techs' && (
            <button onClick={() => setShowAddTech(true)} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-cyan-500/20">
              <Plus className="w-4 h-4" /> Nouveau Technicien
            </button>
          )}
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Utilisateurs', value: users.length, color: 'text-savia-accent' },
          { label: 'Actifs', value: users.filter(u => u.actif).length, color: 'text-green-400' },
          { label: 'Profils', value: profiles.length, color: 'text-purple-400' },
          { label: 'Techniciens', value: techs.length, color: 'text-blue-400' },
        ].map(k => (
          <div key={k.label} className="glass rounded-xl p-4 text-center">
            <div className={`text-3xl font-black ${k.color}`}>{k.value}</div>
            <div className="text-xs text-savia-text-muted mt-1">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-savia-border">
        {[
          { id: 'users', label: 'Utilisateurs', icon: <Users className="w-4 h-4" /> },
          { id: 'profiles', label: 'Profils & Permissions', icon: <Shield className="w-4 h-4" /> },
          { id: 'techs', label: 'Techniciens', icon: <Wrench className="w-4 h-4" /> },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id as any)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-bold rounded-t-lg transition-all cursor-pointer border-b-2 ${tab === t.id ? 'border-savia-accent text-savia-accent bg-savia-accent/5' : 'border-transparent text-savia-text-muted hover:text-savia-text'}`}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* ─── TAB: USERS ─────────────────────────────────────── */}
      {tab === 'users' && (
        <SectionCard title={<span className="flex items-center gap-2"><Users className="w-4 h-4 text-savia-accent" /> Utilisateurs ({users.length})</span>}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-savia-border">
                  {['Utilisateur', 'Nom complet', 'Profil / Rôle', 'Client', 'Statut', 'Actions'].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                    <td className="py-2.5 px-3 font-mono text-xs text-savia-accent font-bold">{u.username}</td>
                    <td className="py-2.5 px-3 font-semibold">{u.nom_complet || '—'}</td>
                    <td className="py-2.5 px-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${roleColor(u.role)}`}>{u.role}</span>
                    </td>
                    <td className="py-2.5 px-3 text-sm text-savia-text-muted">{u.client || 'Global'}</td>
                    <td className="py-2.5 px-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${u.actif ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                        {u.actif ? 'Actif' : 'Inactif'}
                      </span>
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1">
                        <button onClick={() => openEdit(u)} className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 cursor-pointer transition-all" title="Modifier">
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => handleDeleteUser(u.id)} className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer transition-all" title="Supprimer">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-savia-text-muted">Aucun utilisateur.</td></tr>}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {/* ─── TAB: PROFILES ──────────────────────────────────── */}
      {tab === 'profiles' && (
        <div className="space-y-4">
          <div className="glass rounded-xl p-4 border border-savia-border">
            <p className="text-sm text-savia-text-muted flex items-center gap-2">
              <Shield className="w-4 h-4 text-savia-accent" />
              Cochez les pages auxquelles chaque profil a accès. Les modifications sont appliquées lors de la prochaine création/modification d'un utilisateur avec ce profil.
            </p>
          </div>
          {profiles.map(profile => (
            <SectionCard key={profile.id} title={
              <div className="flex items-center gap-3">
                <span className={`px-2.5 py-1 rounded-full text-xs font-black ${profile.bg} ${profile.couleur} border ${profile.border}`}>
                  {profile.nom}
                </span>
                <span className="text-xs text-savia-text-muted font-normal">{profile.description}</span>
                <span className="ml-auto text-xs text-savia-accent font-bold">{profile.pages.length}/{ALL_PAGES.length} pages</span>
              </div>
            }>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                {ALL_PAGES.map(page => {
                  const checked = profile.pages.includes(page.key);
                  const Icon = page.icon;
                  return (
                    <label key={page.key} onClick={() => togglePage(profile.id, page.key)}
                      className={`flex items-center gap-2 p-2.5 rounded-lg cursor-pointer transition-all border ${checked ? `${profile.bg} ${profile.border}` : 'border-savia-border hover:bg-savia-surface-hover'}`}>
                      <div className={`w-4 h-4 rounded shrink-0 flex items-center justify-center border transition-all ${checked ? `${profile.couleur.replace('text-', 'bg-').replace('-400', '-500')} border-transparent` : 'border-savia-border'}`}>
                        {checked && <span className="text-white text-xs font-black">✓</span>}
                      </div>
                      <Icon className={`w-3.5 h-3.5 shrink-0 ${checked ? profile.couleur : 'text-savia-text-muted'}`} />
                      <span className="text-xs">{page.label}</span>
                    </label>
                  );
                })}
              </div>
            </SectionCard>
          ))}
        </div>
      )}

      {/* ─── TAB: TECHS ─────────────────────────────────────── */}
      {tab === 'techs' && (
        <SectionCard title={<span className="flex items-center gap-2"><Wrench className="w-4 h-4 text-savia-accent" /> Équipe Technique ({techs.length})</span>}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-savia-border">
                  {['Nom', 'Spécialité', 'Qualification', 'Disponibilité', 'Email', 'Actions'].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {techs.map(t => (
                  <tr key={t.id} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                    <td className="py-2.5 px-3 font-semibold">{t.nom}</td>
                    <td className="py-2.5 px-3">{t.specialite}</td>
                    <td className="py-2.5 px-3 text-sm">{t.qualification}</td>
                    <td className="py-2.5 px-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${t.dispo.toLowerCase().includes('dispo') ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>{t.dispo}</span>
                    </td>
                    <td className="py-2.5 px-3 text-xs text-savia-text-muted">{t.email}</td>
                    <td className="py-2.5 px-3">
                      <button onClick={() => handleDeleteTech(t.id)} className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer">
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
                {techs.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-savia-text-muted">Aucun technicien enregistré.</td></tr>}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {/* ═══════════════ USER MODAL ═══════════════════════════ */}
      {showUserModal && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 backdrop-blur-sm overflow-y-auto py-6 px-4">
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-lg shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-savia-border">
              <h2 className="text-lg font-black gradient-text flex items-center gap-2">
                <UserCog className="w-5 h-5 text-savia-accent" />
                {editingUser ? 'Modifier l\'utilisateur' : 'Nouvel utilisateur'}
              </h2>
              <button onClick={() => setShowUserModal(false)} className="p-1.5 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="px-6 py-5 space-y-5">
              {/* Profil */}
              <div>
                <label className={LABEL}>Profil *</label>
                <div className="grid grid-cols-1 gap-2">
                  {profiles.map(p => (
                    <label key={p.id} onClick={() => setUserForm(f => ({ ...f, profileId: p.id }))}
                      className={`flex items-center gap-3 p-3 rounded-xl cursor-pointer border transition-all ${userForm.profileId === p.id ? `${p.bg} ${p.border}` : 'border-savia-border hover:bg-savia-surface-hover'}`}>
                      <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center ${userForm.profileId === p.id ? p.couleur.replace('text-', 'border-') : 'border-savia-border'}`}>
                        {userForm.profileId === p.id && <div className={`w-2 h-2 rounded-full ${p.couleur.replace('text-', 'bg-')}`} />}
                      </div>
                      <div className="flex-1">
                        <div className={`text-sm font-bold ${userForm.profileId === p.id ? p.couleur : ''}`}>{p.nom}</div>
                        <div className="text-xs text-savia-text-muted">{p.description}</div>
                      </div>
                      <div className="text-xs text-savia-text-muted">{p.pages.length} pages</div>
                    </label>
                  ))}
                </div>
              </div>

              <div className="border-t border-savia-border" />

              {/* Identifiants */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className={LABEL}>Nom d'utilisateur *</label>
                  <input className={INPUT} placeholder="ex: j.dupont" value={userForm.username}
                    onChange={e => setUserForm(f => ({ ...f, username: e.target.value }))}
                    disabled={!!editingUser} />
                  {editingUser && <p className="text-xs text-savia-text-muted mt-1">Non modifiable</p>}
                </div>
                <div>
                  <label className={LABEL}>{editingUser ? 'Nouveau mot de passe' : 'Mot de passe *'}</label>
                  <div className="relative">
                    <input type={showPassword ? 'text' : 'password'} className={`${INPUT} pr-10`}
                      placeholder={editingUser ? 'Laisser vide pour ne pas changer' : '••••••••'}
                      value={userForm.password} onChange={e => setUserForm(f => ({ ...f, password: e.target.value }))} />
                    <button type="button" onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-savia-text-muted hover:text-savia-text cursor-pointer">
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className={LABEL}>Nom complet</label>
                  <input className={INPUT} placeholder="ex: Jean Dupont" value={userForm.nom_complet}
                    onChange={e => setUserForm(f => ({ ...f, nom_complet: e.target.value }))} />
                </div>
                <div>
                  <label className={LABEL}>Adresse email</label>
                  <input type="email" className={INPUT} placeholder="ex: j.dupont@savia.tn" value={userForm.email}
                    onChange={e => setUserForm(f => ({ ...f, email: e.target.value }))} />
                </div>
                <div>
                  <label className={LABEL}>Client (optionnel)</label>
                  <input className={INPUT} placeholder="ex: CHU Tunis" value={userForm.client}
                    onChange={e => setUserForm(f => ({ ...f, client: e.target.value }))} />
                </div>
                <div className="flex items-end pb-1">
                  <label className="flex items-center gap-2 cursor-pointer group">
                    <div onClick={() => setUserForm(f => ({ ...f, actif: !f.actif }))}
                      className={`w-10 h-5 rounded-full transition-all relative ${userForm.actif ? 'bg-savia-accent' : 'bg-savia-surface-hover border border-savia-border'}`}>
                      <div className={`w-4 h-4 rounded-full bg-white absolute top-0.5 transition-all ${userForm.actif ? 'left-5' : 'left-0.5'}`} />
                    </div>
                    <span className="text-sm font-semibold">Compte actif</span>
                  </label>
                </div>
              </div>

              {/* Pages summary */}
              {userForm.profileId && (
                <div className="p-3 rounded-xl bg-savia-surface-hover/60 border border-savia-border">
                  <p className="text-xs text-savia-text-muted mb-2 font-semibold">Pages autorisées pour ce profil :</p>
                  <div className="flex flex-wrap gap-1.5">
                    {(profiles.find(p => p.id === userForm.profileId)?.pages || []).map(key => {
                      const page = ALL_PAGES.find(p => p.key === key);
                      if (!page) return null;
                      const Icon = page.icon;
                      return (
                        <span key={key} className="text-xs px-2 py-0.5 rounded-full bg-savia-accent/10 text-savia-accent border border-savia-accent/20 flex items-center gap-1">
                          <Icon className="w-2.5 h-2.5" /> {page.label}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {userMsg && (
                <div className={`p-3 rounded-lg text-sm font-semibold ${userMsg.includes('✅') ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                  {userMsg}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-savia-border">
              <button onClick={() => setShowUserModal(false)} disabled={isSavingUser}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover transition-all cursor-pointer">
                Annuler
              </button>
              <button onClick={handleSaveUser} disabled={isSavingUser || !userForm.username.trim()}
                className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer disabled:opacity-50 shadow-lg shadow-cyan-500/20">
                {isSavingUser ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {isSavingUser ? 'Enregistrement...' : editingUser ? 'Mettre à jour' : 'Créer l\'utilisateur'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════ TECH MODAL ═══════════════════════════ */}
      <Modal isOpen={showAddTech} onClose={() => setShowAddTech(false)} title="Nouveau Technicien" size="lg">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><label className={LABEL}>Nom *</label><input className={INPUT} placeholder="Ex: Ben Ali" value={techForm.nom} onChange={e => setTechForm({ ...techForm, nom: e.target.value })} /></div>
          <div><label className={LABEL}>Prénom</label><input className={INPUT} placeholder="Ex: Ahmed" value={techForm.prenom} onChange={e => setTechForm({ ...techForm, prenom: e.target.value })} /></div>
          <div>
            <label className={LABEL}>Spécialité</label>
            <select className={INPUT} value={techForm.specialite} onChange={e => setTechForm({ ...techForm, specialite: e.target.value })}>
              <option value="">— Sélectionner —</option>
              {['Scanner CT', 'IRM', 'Radiographie', 'Mammographie', 'Échographie', 'Général'].map(s => <option key={s}>{s}</option>)}
            </select>
          </div>
          <div><label className={LABEL}>Qualification</label><input className={INPUT} placeholder="Ex: Ingénieur Biomédical" value={techForm.qualification} onChange={e => setTechForm({ ...techForm, qualification: e.target.value })} /></div>
          <div><label className={LABEL}>Email</label><input type="email" className={INPUT} placeholder="ahmed@savia.tn" value={techForm.email} onChange={e => setTechForm({ ...techForm, email: e.target.value })} /></div>
          <div><label className={LABEL}>Téléphone</label><input className={INPUT} placeholder="+216 XX XXX XXX" value={techForm.telephone} onChange={e => setTechForm({ ...techForm, telephone: e.target.value })} /></div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-white/5">
          <button onClick={() => setShowAddTech(false)} className="px-4 py-2 rounded-lg text-savia-text-muted hover:text-savia-text hover:bg-white/5 transition-colors cursor-pointer">Annuler</button>
          <button onClick={handleSaveTech} disabled={isSavingTech || !techForm.nom.trim()}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer">
            {isSavingTech ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Sauvegarder
          </button>
        </div>
      </Modal>
    </div>
  );
}
