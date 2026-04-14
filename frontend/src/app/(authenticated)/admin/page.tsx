'use client';
import { useState, useEffect, useCallback } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Modal } from '@/components/ui/modal';
import { Shield, Users, Plus, Edit2, Trash2, Loader2, Save, Wrench } from 'lucide-react';
import { admin, techniciens } from '@/lib/api';

interface User { id: number; nom: string; email: string; role: string; client: string; derniereConnexion: string; }
interface Technicien { id: number; nom: string; specialite: string; qualification: string; dispo: string; email: string; telephone: string; }

const INPUT_CLS = "w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-white placeholder:text-slate-500 focus:ring-2 focus:ring-cyan-500/40 outline-none transition-all";

export default function AdminPage() {
  const [tab, setTab] = useState<'users' | 'techs'>('users');
  const [users, setUsers] = useState<User[]>([]);
  const [techs, setTechs] = useState<Technicien[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddTech, setShowAddTech] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const emptyTech = { nom: '', prenom: '', specialite: '', qualification: '', email: '', telephone: '' };
  const [form, setForm] = useState(emptyTech);

  const loadData = useCallback(async () => {
    try {
      const [usersRes, techsRes] = await Promise.all([admin.users(), techniciens.list()]);
      setUsers(usersRes.map((item: any, i: number) => ({
        id: item.id || i + 1,
        nom: item.nom || item.username || '',
        email: item.email || `${(item.username || 'user')}@savia.tn`,
        role: item.role || 'Lecteur',
        client: item.client || 'Global',
        derniereConnexion: item.derniere_connexion || 'N/A',
      })));
      setTechs(techsRes.map((item: any) => ({
        id: item.id || 0,
        nom: item.nom_complet || `${item.nom || ''} ${item.prenom || ''}`.trim() || 'N/A',
        specialite: item.specialite || 'Général',
        qualification: item.qualification || '',
        dispo: item.dispo || 'Disponible',
        email: item.email || '',
        telephone: item.telephone || '',
      })));
    } catch (err) {
      console.error("Failed to fetch admin data", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleSaveTech = async () => {
    if (!form.nom.trim()) return;
    setIsSaving(true);
    try {
      await techniciens.create(form);
      setForm(emptyTech);
      setShowAddTech(false);
      await loadData();
    } catch (err) { console.error("Save tech failed", err); }
    finally { setIsSaving(false); }
  };

  const handleDeleteTech = async (id: number) => {
    if (!confirm("Supprimer ce technicien ?")) return;
    try { await techniciens.delete(id); await loadData(); }
    catch (err) { console.error("Delete tech failed", err); }
  };

  const adminCount = users.filter(u => u.role.toLowerCase() === 'admin').length;
  const techCount = techs.length;

  if (isLoading) return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text">👑 Administration</h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion des utilisateurs, techniciens et permissions</p>
        </div>
        {tab === 'techs' && (
          <button onClick={() => setShowAddTech(true)} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
            <Plus className="w-4 h-4" /> Nouveau Technicien
          </button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-savia-accent">{users.length}</div><div className="text-xs text-savia-text-muted mt-1">Utilisateurs</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-purple-400">{adminCount}</div><div className="text-xs text-savia-text-muted mt-1">👑 Admins</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-blue-400">{techCount}</div><div className="text-xs text-savia-text-muted mt-1">🔧 Techniciens</div></div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-savia-border pb-0">
        <button onClick={() => setTab('users')} className={`px-4 py-2.5 text-sm font-bold rounded-t-lg transition-all cursor-pointer ${tab === 'users' ? 'bg-savia-surface text-savia-accent border-b-2 border-savia-accent' : 'text-savia-text-muted hover:text-white'}`}>
          <Users className="w-4 h-4 inline mr-1.5" />Utilisateurs
        </button>
        <button onClick={() => setTab('techs')} className={`px-4 py-2.5 text-sm font-bold rounded-t-lg transition-all cursor-pointer ${tab === 'techs' ? 'bg-savia-surface text-savia-accent border-b-2 border-savia-accent' : 'text-savia-text-muted hover:text-white'}`}>
          <Wrench className="w-4 h-4 inline mr-1.5" />Techniciens
        </button>
      </div>

      {/* Users Tab */}
      {tab === 'users' && (
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
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                    <td className="py-2.5 px-3 font-semibold">{u.nom}</td>
                    <td className="py-2.5 px-3 text-savia-text-muted">{u.email}</td>
                    <td className="py-2.5 px-3 text-center">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${u.role.toLowerCase() === 'admin' ? 'bg-purple-500/10 text-purple-400' : u.role.toLowerCase() === 'technicien' ? 'bg-blue-500/10 text-blue-400' : 'bg-green-500/10 text-green-400'}`}>{u.role}</span>
                    </td>
                    <td className="py-2.5 px-3 text-sm">{u.client}</td>
                    <td className="py-2.5 px-3 text-xs text-savia-text-dim">{u.derniereConnexion}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {/* Techniciens Tab */}
      {tab === 'techs' && (
        <SectionCard title="🔧 Équipe Technique">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-savia-border">
                  <th className="text-left py-2 px-3 text-savia-text-muted">Nom</th>
                  <th className="text-left py-2 px-3 text-savia-text-muted">Spécialité</th>
                  <th className="text-left py-2 px-3 text-savia-text-muted">Qualification</th>
                  <th className="text-center py-2 px-3 text-savia-text-muted">Dispo</th>
                  <th className="text-left py-2 px-3 text-savia-text-muted">Email</th>
                  <th className="text-center py-2 px-3 text-savia-text-muted">Actions</th>
                </tr>
              </thead>
              <tbody>
                {techs.map(t => (
                  <tr key={t.id} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                    <td className="py-2.5 px-3 font-semibold">{t.nom}</td>
                    <td className="py-2.5 px-3">{t.specialite}</td>
                    <td className="py-2.5 px-3 text-sm">{t.qualification}</td>
                    <td className="py-2.5 px-3 text-center">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${t.dispo.toLowerCase().includes('dispo') ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>{t.dispo}</span>
                    </td>
                    <td className="py-2.5 px-3 text-xs text-savia-text-muted">{t.email}</td>
                    <td className="py-2.5 px-3 text-center">
                      <button onClick={() => handleDeleteTech(t.id)} className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 cursor-pointer"><Trash2 className="w-3.5 h-3.5" /></button>
                    </td>
                  </tr>
                ))}
                {techs.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-savia-text-muted">Aucun technicien enregistré.</td></tr>}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {/* Add Technicien Modal */}
      <Modal isOpen={showAddTech} onClose={() => setShowAddTech(false)} title="➕ Nouveau Technicien" size="lg">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Nom *</label>
            <input className={INPUT_CLS} placeholder="Ex: Ben Ali" value={form.nom} onChange={e => setForm({...form, nom: e.target.value})} />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Prénom</label>
            <input className={INPUT_CLS} placeholder="Ex: Ahmed" value={form.prenom} onChange={e => setForm({...form, prenom: e.target.value})} />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Spécialité</label>
            <select className={INPUT_CLS} value={form.specialite} onChange={e => setForm({...form, specialite: e.target.value})}>
              <option value="">— Sélectionner —</option>
              <option>Scanner CT</option><option>IRM</option><option>Radiographie</option><option>Mammographie</option><option>Général</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Qualification</label>
            <input className={INPUT_CLS} placeholder="Ex: Ingénieur Biomédical" value={form.qualification} onChange={e => setForm({...form, qualification: e.target.value})} />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Email</label>
            <input type="email" className={INPUT_CLS} placeholder="Ex: ahmed@savia.tn" value={form.email} onChange={e => setForm({...form, email: e.target.value})} />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">Téléphone</label>
            <input className={INPUT_CLS} placeholder="Ex: +216 XX XXX XXX" value={form.telephone} onChange={e => setForm({...form, telephone: e.target.value})} />
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-white/5">
          <button onClick={() => setShowAddTech(false)} className="px-4 py-2 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors cursor-pointer">Annuler</button>
          <button onClick={handleSaveTech} disabled={isSaving || !form.nom.trim()} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Sauvegarder
          </button>
        </div>
      </Modal>
    </div>
  );
}
