'use client';
import { useState, useEffect, useCallback } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Modal } from '@/components/ui/modal';
import {
  Shield, Users, Plus, Trash2, Loader2, Save,
  X, Eye, EyeOff, Edit2, Crown, UserCog, Phone, Mail, Send,
  Wrench, BarChart3, Monitor, Hospital, TrendingUp, BookOpen,
  ClipboardList, CalendarDays, Cog, FileText, ClipboardCheck, Settings,
  Star, Radio, Upload, Building2, Globe, Check, DollarSign, MapPin, ShieldCheck,
} from 'lucide-react';
import { admin, techniciens, clients } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

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
  { key: 'finances',           label: 'Finances',               icon: DollarSign     },
  { key: 'carte',              label: 'Carte Géographique',     icon: MapPin         },
  { key: 'sla',                label: 'Suivi SLA',              icon: ShieldCheck    },
  { key: 'admin',              label: 'Administration',         icon: Settings       },
  { key: 'settings',           label: 'Paramètres',             icon: Cog            },
];

// ─── DEFAULT PROFILES ─────────────────────────────────────
const DEFAULT_PROFILES: Profile[] = [
  {
    id: 'admin',
    nom: 'Admin',
    couleur: 'text-red-400',
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    description: 'Super-administrateur — accès total, modifiable uniquement par l\'admin',
    pages: ALL_PAGES.map(p => p.key),
  },
  {
    id: 'manager',
    nom: 'Manager',
    couleur: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30',
    description: 'Accès complet à toutes les fonctionnalités',
    pages: ALL_PAGES.filter(p => p.key !== 'settings').map(p => p.key),
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
  admin: 'Admin',
  manager: 'Manager',
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

interface Technicien {
  id: number;
  nom: string;
  prenom: string;
  specialite: string;
  qualification: string;
  niveau_competence: string;
  dispo: string;
  email: string;
  telephone: string;
  telegram_id: string;
}

const emptyUser = () => ({
  username: '', password: '', nom_complet: '', email: '', profileId: 'lecteur', client: '', actif: true,
});
const SPECIALITES = ['Scanner CT', 'IRM', 'Radiographie', 'Mammographie', 'Échographie', 'DICOM / Informatique médicale', 'Général'];
const NIVEAUX = ['Junior', 'Intermédiaire', 'Senior', 'Expert'];

const emptyTech = () => ({
  nom: '', prenom: '', specialite: '', qualification: '',
  niveau_competence: 'Intermédiaire', email: '', telephone: '', telegram_id: '',
});

export default function AdminPage() {
  const { user: currentUser } = useAuth();
  const [tab, setTab] = useState<'users' | 'profiles' | 'techs' | 'settings'>('users');
  const [users, setUsers] = useState<User[]>([]);
  const [techs, setTechs] = useState<Technicien[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>(DEFAULT_PROFILES);
  const [isLoading, setIsLoading] = useState(true);
  const [clientsList, setClientsList] = useState<string[]>([]);

  // User modal
  const [showUserModal, setShowUserModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [userForm, setUserForm] = useState(emptyUser());
  const [selectedTechId, setSelectedTechId] = useState<number | ''>('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSavingUser, setIsSavingUser] = useState(false);
  const [userMsg, setUserMsg] = useState('');

  // Profile edit
  const [editingProfile, setEditingProfile] = useState<Profile | null>(null);

  // Settings
  const DEVISES = [
    { code: 'TND', label: 'Dinar Tunisien', flag: '🇹🇳', symbol: 'DT' },
    { code: 'DZD', label: 'Dinar Algérien', flag: '🇩🇿', symbol: 'DA' },
    { code: 'MAD', label: 'Dirham Marocain', flag: '🇲🇦', symbol: 'MAD' },
    { code: 'XOF', label: 'Franc CFA (BCEAO)', flag: '🆈', symbol: 'FCFA' },
  ];
  const [devise, setDevise] = useState(() => (typeof window !== 'undefined' ? localStorage.getItem('savia_devise') || 'TND' : 'TND'));
  const [companyName, setCompanyName] = useState(() => (typeof window !== 'undefined' ? localStorage.getItem('savia_company') || '' : ''));
  const [logoPreview, setLogoPreview] = useState<string>(() => (typeof window !== 'undefined' ? localStorage.getItem('savia_logo') || '' : ''));
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [profilesSaving, setProfilesSaving] = useState(false);
  const [profilesSaved,  setProfilesSaved]  = useState(false);
  const [profilesErr,    setProfilesErr]    = useState('');

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => setLogoPreview(ev.target?.result as string);
    reader.readAsDataURL(file);
  };
  const saveSettings = () => {
    localStorage.setItem('savia_devise', devise);
    localStorage.setItem('savia_company', companyName);
    if (logoPreview) localStorage.setItem('savia_logo', logoPreview);
    else localStorage.removeItem('savia_logo');
    window.dispatchEvent(new Event('savia_settings_changed'));
    setSettingsSaved(true);
    setTimeout(() => setSettingsSaved(false), 2000);
  };

  // Tech modal
  const [showAddTech, setShowAddTech] = useState(false);
  const [editingTech, setEditingTech] = useState<Technicien | null>(null);
  const [techForm, setTechForm] = useState(emptyTech());
  const [isSavingTech, setIsSavingTech] = useState(false);
  const [techMsg, setTechMsg] = useState('');

  const load = useCallback(async () => {
    try {
      const [usersRes, techsRes, clientsRes] = await Promise.all([admin.users(), techniciens.list(), clients.list()]);
      setClientsList((clientsRes as any[]).map((c: any) => c.nom || c.client || '').filter(Boolean));
      setUsers((usersRes as any[]).map((item: any, i: number) => ({
        id: item.id || i + 1,
        username: item.username || '',
        nom_complet: item.nom_complet || item.nom || '',
        role: item.role || 'Lecteur',
        client: item.client || '',
        actif: item.actif ?? 1,
        email: item.email || '',
        profileId: item.profil
          ? (profiles.find(p => p.nom === item.profil)?.id || Object.entries(PROFILE_ROLE_MAP).find(([, r]) => r === item.role)?.[0] || 'lecteur')
          : (Object.entries(PROFILE_ROLE_MAP).find(([, r]) => r === item.role)?.[0] || 'lecteur'),
      })));
      setTechs((techsRes as any[]).map((item: any) => ({
        id: item.id || 0,
        nom: item.nom || '',
        prenom: item.prenom || '',
        specialite: item.specialite || 'Général',
        qualification: item.qualification || '',
        niveau_competence: item.niveau_competence || 'Junior',
        dispo: typeof item.dispo === 'number' ? (item.dispo ? 'Disponible' : 'Indisponible') : (item.dispo || 'Disponible'),
        email: item.email || '',
        telephone: item.telephone || '',
        telegram_id: item.telegram_id || '',
      })));

      // Charger les permissions depuis la BD et les appliquer aux profils
      try {
        const token = localStorage.getItem('savia_token') || '';
        const settingsRes = await fetch('/api/settings', { headers: { Authorization: `Bearer ${token}` } });
        if (settingsRes.ok) {
          const settingsData = await settingsRes.json();
          const dbPerms = JSON.parse(settingsData.role_permissions || '{}');
          if (Object.keys(dbPerms).length > 0) {
            setProfiles(prev => prev.map(p => {
              const role = PROFILE_ROLE_MAP[p.id];
              if (!role || !dbPerms[role]) return p;
              const permsForRole = dbPerms[role];
              // Convertir {page: true/false} en tableau de pages autorisées
              const authorizedPages = Object.entries(permsForRole)
                .filter(([, v]) => v === true)
                .map(([k]) => k);
              return { ...p, pages: authorizedPages };
            }));
          }
        }
      } catch { /* silencieux */ }
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

  const openAdd = () => {
    setEditingUser(null);
    setUserForm(emptyUser());
    setSelectedTechId('');
    setUserMsg('');
    setShowPassword(false);
    setShowUserModal(true);
  };
  const openEdit = (u: User) => {
    setEditingUser(u);
    setUserForm({ username: u.username, password: '', nom_complet: u.nom_complet, email: u.email || '', profileId: u.profileId || 'lecteur', client: u.client, actif: u.actif === 1 });
    setSelectedTechId('');
    setUserMsg('');
    setShowPassword(false);
    setShowUserModal(true);
  };
  const handleDeleteUser = async (id: number) => {
    if (!confirm('Supprimer cet utilisateur ?')) return;
    try { await (admin as any).deleteUser(id); await load(); } catch { /* noop */ }
  };

  // ── Save Tech ────────────────────────────────────────────
  const handleSaveTech = async () => {
    if (!techForm.nom.trim()) return;
    setIsSavingTech(true); setTechMsg('');
    try {
      if (editingTech) {
        await techniciens.update(editingTech.id, techForm as any);
      } else {
        await techniciens.create(techForm);
      }
      setTechForm(emptyTech());
      setShowAddTech(false);
      setEditingTech(null);
      setTechMsg('');
      await load();
    } catch (err: any) {
      setTechMsg(`❌ ${err?.message || 'Erreur'}`);
    } finally { setIsSavingTech(false); }  
  };
  const setT = (k: string, v: string) => setTechForm(f => ({ ...f, [k]: v }));

  const openAddTech = () => { setEditingTech(null); setTechForm(emptyTech()); setTechMsg(''); setShowAddTech(true); };
  const openEditTech = (t: Technicien) => {
    setEditingTech(t);
    setTechForm({ nom: t.nom, prenom: t.prenom, specialite: t.specialite, qualification: t.qualification, niveau_competence: t.niveau_competence || 'Intermédiaire', email: t.email, telephone: t.telephone, telegram_id: t.telegram_id });
    setTechMsg('');
    setShowAddTech(true);
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

  // ── Save profiles permissions to DB ──────────────────────
  const saveProfiles = async () => {
    setProfilesSaving(true); setProfilesErr(''); setProfilesSaved(false);
    try {
      // Construire le format role_permissions: {Role: {page: true/false}}
      const rolePerms: Record<string, Record<string, boolean>> = {};
      profiles.forEach(p => {
        const role = PROFILE_ROLE_MAP[p.id];
        if (!role) return;
        rolePerms[role] = {};
        ALL_PAGES.forEach(page => {
          rolePerms[role][page.key] = p.pages.includes(page.key);
        });
      });
      // Sauvegarder toutes les permissions (y compris Admin)

      const token = localStorage.getItem('savia_token') || '';
      const res = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ role_permissions: JSON.stringify(rolePerms) }),
      });
      if (!res.ok) throw new Error(`Erreur ${res.status}`);
      setProfilesSaved(true);
      setTimeout(() => setProfilesSaved(false), 3000);
    } catch (e: any) {
      setProfilesErr(`❌ ${e.message}`);
    } finally {
      setProfilesSaving(false);
    }
  };

  const roleColor = (role: string) => {
    if (role === 'Admin') return 'bg-red-500/10 text-red-400';
    if (role === 'Manager') return 'bg-purple-500/10 text-purple-400';
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
            <button onClick={openAddTech} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-cyan-500/20">
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
          { id: 'users',    label: 'Utilisateurs',       icon: <Users className="w-4 h-4" /> },
          { id: 'profiles', label: 'Profils & Permissions', icon: <Shield className="w-4 h-4" /> },
          { id: 'techs',    label: 'Techniciens',         icon: <Wrench className="w-4 h-4" /> },
          { id: 'settings', label: 'Paramètres',          icon: <Settings className="w-4 h-4" /> },
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
                        {(u.username !== 'admin' || currentUser?.username === 'admin') && (
                          <button onClick={() => openEdit(u)} className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 cursor-pointer transition-all" title="Modifier">
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {u.username !== 'admin' && (
                          <button onClick={() => handleDeleteUser(u.id)} className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer transition-all" title="Supprimer">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
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
                {ALL_PAGES
                  .filter(page => profile.id === 'admin' || page.key !== 'settings')
                  .map(page => {
                  const checked = profile.pages.includes(page.key);
                  const Icon = page.icon;
                  const isAdminProfile = profile.id === 'admin';
                  const isCurrentUserAdmin = currentUser?.username === 'admin';
                  const canToggle = !isAdminProfile || isCurrentUserAdmin;
                  return (
                    <label key={page.key} onClick={() => canToggle && togglePage(profile.id, page.key)}
                      className={`flex items-center gap-2 p-2.5 rounded-lg transition-all border ${!canToggle ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'} ${checked ? `${profile.bg} ${profile.border}` : 'border-savia-border hover:bg-savia-surface-hover'}`}>
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

          {/* Bouton Valider les permissions */}
          <div className="flex items-center justify-between pt-2 border-t border-savia-border">
            <div>
              {profilesSaved && (
                <span className="text-green-400 text-sm font-bold">✅ Permissions sauvegardées !</span>
              )}
              {profilesErr && <span className="text-red-400 text-sm">{profilesErr}</span>}
            </div>
            <button
              onClick={saveProfiles}
              disabled={profilesSaving}
              className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-cyan-500/20 disabled:opacity-50"
            >
              {profilesSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {profilesSaving ? 'Sauvegarde...' : 'Valider les permissions'}
            </button>
          </div>
        </div>
      )}

      {/* ─── TAB: TECHS ─────────────────────────────────────── */}
      {tab === 'techs' && (
        <SectionCard title={<span className="flex items-center gap-2"><Wrench className="w-4 h-4 text-savia-accent" /> Équipe Technique ({techs.length})</span>}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-savia-border">
                  {['Nom & Prénom', 'Spécialité', 'Niveau', 'Téléphone', 'Contact', 'Dispo', 'Actions'].map(h => (
                    <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {techs.map(t => (
                  <tr key={t.id} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                    <td className="py-2.5 px-3">
                      <div className="font-semibold">{t.nom} {t.prenom}</div>
                      <div className="text-xs text-savia-text-muted">{t.qualification}</div>
                    </td>
                    <td className="py-2.5 px-3 text-sm">{t.specialite}</td>
                    <td className="py-2.5 px-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                        t.niveau_competence === 'Expert' ? 'bg-purple-500/10 text-purple-400' :
                        t.niveau_competence === 'Senior' ? 'bg-blue-500/10 text-blue-400' :
                        t.niveau_competence === 'Intermédiaire' ? 'bg-amber-500/10 text-amber-400' :
                        'bg-green-500/10 text-green-400'
                      }`}>{t.niveau_competence || 'Junior'}</span>
                    </td>
                    <td className="py-2.5 px-3 text-xs">
                      {t.telephone && <a href={`tel:${t.telephone}`} className="flex items-center gap-1 text-savia-text-muted hover:text-savia-accent"><Phone className="w-3 h-3" />{t.telephone}</a>}
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        {t.email && <a href={`mailto:${t.email}`} title={t.email} className="p-1 rounded text-savia-text-muted hover:text-savia-accent"><Mail className="w-3.5 h-3.5" /></a>}
                        {t.telegram_id && <a href={`https://t.me/${t.telegram_id.replace('@','')}`} target="_blank" title={t.telegram_id} className="p-1 rounded text-savia-text-muted hover:text-blue-400"><Send className="w-3.5 h-3.5" /></a>}
                      </div>
                    </td>
                    <td className="py-2.5 px-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${String(t.dispo).toLowerCase().includes('dispo') ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>{t.dispo}</span>
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-1">
                        <button onClick={() => openEditTech(t)} className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 cursor-pointer" title="Modifier">
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button onClick={() => handleDeleteTech(t.id)} className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {techs.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-savia-text-muted">Aucun technicien enregistré.</td></tr>}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {/* ─── TAB: SETTINGS ───────────────────────────────────── */}
      {tab === 'settings' && (
        <div className="space-y-6">
          {/* Devise */}
          <SectionCard title={<span className="flex items-center gap-2"><Globe className="w-4 h-4 text-savia-accent" /> Devise de l'application</span>}>
            <p className="text-xs text-savia-text-muted mb-4">La devise sélectionnée sera utilisée sur toutes les pages (rapports, pièces, contrats…)</p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {DEVISES.map(d => (
                <button key={d.code} onClick={() => setDevise(d.code)}
                  className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 cursor-pointer transition-all ${
                    devise === d.code
                      ? 'border-savia-accent bg-savia-accent/10 text-savia-accent'
                      : 'border-savia-border hover:bg-savia-surface-hover text-savia-text'
                  }`}>
                  <span className="text-3xl">{d.flag}</span>
                  <div className="text-center">
                    <div className="text-sm font-black">{d.symbol}</div>
                    <div className="text-xs text-savia-text-muted">{d.label}</div>
                  </div>
                  {devise === d.code && <Check className="w-4 h-4" />}
                </button>
              ))}
            </div>
          </SectionCard>

          {/* Identité client */}
          <SectionCard title={<span className="flex items-center gap-2"><Building2 className="w-4 h-4 text-savia-accent" /> Identité de l'entreprise</span>}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
              <div className="space-y-4">
                <div>
                  <label className={LABEL}>Nom de l'entreprise / client</label>
                  <input className={INPUT} placeholder="Ex: SIC Radiologie Tunisie"
                    value={companyName} onChange={e => setCompanyName(e.target.value)} />
                  <p className="text-xs text-savia-text-muted mt-1">Affiché dans l'en-tête et les rapports PDF</p>
                </div>
                <div>
                  <label className={LABEL}><Upload className="w-3 h-3 inline mr-1" />Logo de l'entreprise</label>
                  <div className="mt-2">
                    <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-savia-border rounded-xl cursor-pointer hover:border-savia-accent hover:bg-savia-accent/5 transition-all">
                      <Upload className="w-6 h-6 text-savia-text-muted mb-2" />
                      <span className="text-xs text-savia-text-muted">Cliquer pour uploader (PNG, JPG, SVG)</span>
                      <span className="text-xs text-savia-text-dim mt-0.5">Recommandé : 200×60 px, fond transparent</span>
                      <input type="file" className="hidden" accept="image/*" onChange={handleLogoUpload} />
                    </label>
                  </div>
                  {logoPreview && (
                    <div className="mt-3 flex items-center gap-3">
                      <button onClick={() => setLogoPreview('')} className="text-xs text-red-400 hover:text-red-300 cursor-pointer">✕ Supprimer le logo</button>
                    </div>
                  )}
                </div>
              </div>

              {/* Aperçu */}
              <div className="flex flex-col items-center gap-4">
                <p className="text-xs text-savia-text-muted font-semibold uppercase tracking-wider">Aperçu</p>
                <div className="w-full bg-savia-bg border border-savia-border rounded-xl p-6 flex items-center justify-center gap-4 min-h-[120px]">
                  {logoPreview
                    ? <img src={logoPreview} alt="logo" className="max-h-16 max-w-[180px] object-contain" />
                    : <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-savia-accent to-blue-600 flex items-center justify-center"><Building2 className="w-6 h-6 text-white" /></div>
                  }
                  <div>
                    <div className="font-black text-lg gradient-text">{companyName || 'SAVIA'}</div>
                    <div className="text-xs text-savia-text-muted">Plateforme de gestion</div>
                    <div className="text-xs text-savia-accent font-semibold mt-1">{DEVISES.find(d => d.code === devise)?.symbol} — {DEVISES.find(d => d.code === devise)?.label}</div>
                  </div>
                </div>
              </div>
            </div>
          </SectionCard>

          {/* Save */}
          <div className="flex justify-end">
            <button onClick={saveSettings}
              className={`flex items-center gap-2 px-8 py-3 rounded-xl font-bold text-white transition-all cursor-pointer shadow-lg ${
                settingsSaved
                  ? 'bg-green-500 shadow-green-500/20'
                  : 'bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 shadow-cyan-500/20'
              }`}>
              {settingsSaved ? <Check className="w-4 h-4" /> : <Save className="w-4 h-4" />}
              {settingsSaved ? 'Paramètres sauvegardés !' : 'Enregistrer les paramètres'}
            </button>
          </div>
        </div>
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

              {/* ── Technicien : sélecteur de tech enregistré ── */}
              {userForm.profileId === 'technicien' && (
                <div>
                  <label className={LABEL}>Lier à un technicien existant *</label>
                  <select className={INPUT} value={selectedTechId}
                    onChange={e => {
                      const id = Number(e.target.value);
                      setSelectedTechId(id || '');
                      if (id) {
                        const t = techs.find(x => x.id === id);
                        if (t) setUserForm(f => ({ ...f, nom_complet: `${t.nom} ${t.prenom}`.trim(), email: t.email || '' }));
                      }
                    }}>
                    <option value="">— Sélectionner un technicien —</option>
                    {techs.map(t => (
                      <option key={t.id} value={t.id}>{t.nom} {t.prenom} — {t.specialite}</option>
                    ))}
                  </select>
                </div>
              )}

              {/* ── Lecteur : sélecteur client obligatoire (avant identifiants) ── */}
              {userForm.profileId === 'lecteur' && (
                <div>
                  <label className={LABEL}>Client associé *</label>
                  <select className={INPUT} value={userForm.client}
                    onChange={e => setUserForm(f => ({ ...f, client: e.target.value }))}>
                    <option value="">— Sélectionner un client —</option>
                    {clientsList.map(c => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  {!userForm.client && <p className="text-xs text-amber-400 mt-1">⚠ Client requis pour le profil Lecteur</p>}
                </div>
              )}

              {/* ── Identifiants (toujours visibles) ── */}
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
                    onChange={e => setUserForm(f => ({ ...f, nom_complet: e.target.value }))}
                    readOnly={userForm.profileId === 'technicien' && !!selectedTechId} />
                </div>
                <div>
                  <label className={LABEL}>Adresse email</label>
                  <input type="email" className={INPUT} placeholder="ex: j.dupont@savia.tn" value={userForm.email || ''}
                    onChange={e => setUserForm(f => ({ ...f, email: e.target.value }))} />
                </div>
                <div className="flex items-end pb-1 col-span-2">
                  <label className="flex items-center gap-2 cursor-pointer">
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
              <button onClick={handleSaveUser}
                disabled={isSavingUser || !userForm.username.trim() || (userForm.profileId === 'lecteur' && !userForm.client)}
                className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer disabled:opacity-50 shadow-lg shadow-cyan-500/20">
                {isSavingUser ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {isSavingUser ? 'Enregistrement...' : editingUser ? 'Mettre à jour' : 'Créer l\'utilisateur'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════════ TECH MODAL ═══════════════════════════ */}
      {showAddTech && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 backdrop-blur-sm overflow-y-auto py-6 px-4">
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-xl shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-savia-border">
              <h2 className="text-lg font-black gradient-text flex items-center gap-2">
                <Wrench className="w-5 h-5 text-savia-accent" /> {editingTech ? 'Modifier le technicien' : 'Nouveau Technicien'}
              </h2>
              <button onClick={() => setShowAddTech(false)} className="p-1.5 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="px-6 py-5 space-y-4">
              {/* Identité */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={LABEL}>Nom *</label>
                  <input className={INPUT} placeholder="Ex: Ben Ali" value={techForm.nom} onChange={e => setT('nom', e.target.value)} />
                </div>
                <div>
                  <label className={LABEL}>Prénom</label>
                  <input className={INPUT} placeholder="Ex: Ahmed" value={techForm.prenom} onChange={e => setT('prenom', e.target.value)} />
                </div>
              </div>

              {/* Compétences */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={LABEL}>Spécialité</label>
                  <select className={INPUT} value={techForm.specialite} onChange={e => setT('specialite', e.target.value)}>
                    <option value="">— Sélectionner —</option>
                    {SPECIALITES.map(s => <option key={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className={LABEL}>Niveau de compétence</label>
                  <div className="flex gap-1.5">
                    {NIVEAUX.map(n => (
                      <button key={n} type="button" onClick={() => setT('niveau_competence', n)}
                        className={`flex-1 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer border ${
                          techForm.niveau_competence === n
                            ? n === 'Expert' ? 'bg-purple-500/20 text-purple-400 border-purple-500/40'
                              : n === 'Senior' ? 'bg-blue-500/20 text-blue-400 border-blue-500/40'
                              : n === 'Intermédiaire' ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                              : 'bg-green-500/20 text-green-400 border-green-500/40'
                            : 'border-savia-border text-savia-text-muted hover:bg-savia-surface-hover'
                        }`}>{n}</button>
                    ))}
                  </div>
                </div>
              </div>

              <div>
                <label className={LABEL}>Qualification</label>
                <input className={INPUT} placeholder="Ex: Ingénieur Biomédical" value={techForm.qualification} onChange={e => setT('qualification', e.target.value)} />
              </div>

              {/* Contact */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={LABEL}><Phone className="w-3 h-3 inline mr-1" />Téléphone</label>
                  <input className={INPUT} placeholder="+216 XX XXX XXX" value={techForm.telephone} onChange={e => setT('telephone', e.target.value)} />
                </div>
                <div>
                  <label className={LABEL}><Mail className="w-3 h-3 inline mr-1" />Email</label>
                  <input type="email" className={INPUT} placeholder="ahmed@savia.tn" value={techForm.email} onChange={e => setT('email', e.target.value)} />
                </div>
              </div>
              <div>
                <label className={LABEL}><Send className="w-3 h-3 inline mr-1" />Telegram (username ou ID)</label>
                <input className={INPUT} placeholder="Ex: @ahmed_savia ou 123456789" value={techForm.telegram_id} onChange={e => setT('telegram_id', e.target.value)} />
              </div>

              {techMsg && (
                <div className={`p-3 rounded-lg text-sm font-semibold ${techMsg.includes('❌') ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}>
                  {techMsg}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 px-6 py-4 border-t border-savia-border">
              <button onClick={() => setShowAddTech(false)} className="px-4 py-2 rounded-lg text-sm font-semibold text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover transition-all cursor-pointer">
                Annuler
              </button>
              <button onClick={handleSaveTech} disabled={isSavingTech || !techForm.nom.trim()}
                className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer shadow-lg shadow-cyan-500/20">
                {isSavingTech ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                {isSavingTech ? 'Enregistrement...' : editingTech ? 'Mettre à jour' : 'Ajouter le technicien'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
