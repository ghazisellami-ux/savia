'use client';
import { SectionCard } from '@/components/ui/cards';
import { Save, Bell, Palette, Globe, Shield, Database } from 'lucide-react';

export default function SettingsPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-black gradient-text">⚙️ Paramètres</h1>
        <p className="text-savia-text-muted text-sm mt-1">Configuration de l&apos;application SAVIA</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <SectionCard title="🔔 Notifications">
          <div className="space-y-4">
            {[
              { label: 'Alertes Telegram', desc: 'Recevoir les alertes critiques via Telegram', checked: true },
              { label: 'Alertes Email', desc: 'Recevoir les rapports par email', checked: true },
              { label: 'Alertes sonores', desc: 'Notification sonore pour les pannes critiques', checked: false },
            ].map(n => (
              <label key={n.label} className="flex items-center justify-between p-3 rounded-lg bg-savia-bg/50 cursor-pointer hover:bg-savia-surface-hover/30 transition-colors">
                <div>
                  <div className="font-semibold text-sm">{n.label}</div>
                  <div className="text-xs text-savia-text-muted">{n.desc}</div>
                </div>
                <div className={`w-10 h-5 rounded-full relative transition-colors ${n.checked ? 'bg-savia-accent' : 'bg-savia-border'}`}>
                  <div className={`w-4 h-4 rounded-full bg-white absolute top-0.5 transition-transform ${n.checked ? 'translate-x-5' : 'translate-x-0.5'}`} />
                </div>
              </label>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="🔧 SAV Configuration">
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">💰 Taux horaire technicien (€/h)</label>
              <input type="number" defaultValue={65} className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">📅 Période rapports (mois)</label>
              <select defaultValue="1" className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
                <option value="1">Mensuel</option><option value="3">Trimestriel</option><option value="6">Semestriel</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">🔑 Clé API Gemini</label>
              <input type="password" defaultValue="AIza..." className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40" />
            </div>
          </div>
        </SectionCard>

        <SectionCard title="🗄️ Base de données">
          <div className="space-y-3 text-sm">
            <div className="flex justify-between p-3 rounded-lg bg-savia-bg/50"><span className="text-savia-text-muted">Type</span><span className="font-bold text-savia-accent">PostgreSQL</span></div>
            <div className="flex justify-between p-3 rounded-lg bg-savia-bg/50"><span className="text-savia-text-muted">Taille</span><span className="font-bold">124 MB</span></div>
            <div className="flex justify-between p-3 rounded-lg bg-savia-bg/50"><span className="text-savia-text-muted">Dernier backup</span><span className="font-bold text-green-400">18/03/2025 02:00</span></div>
          </div>
        </SectionCard>

        <SectionCard title="ℹ️ À propos">
          <div className="space-y-3 text-sm">
            <div className="flex justify-between p-3 rounded-lg bg-savia-bg/50"><span className="text-savia-text-muted">Version</span><span className="font-bold text-savia-accent">SAVIA v3.0-next</span></div>
            <div className="flex justify-between p-3 rounded-lg bg-savia-bg/50"><span className="text-savia-text-muted">Framework</span><span className="font-bold">Next.js 16</span></div>
            <div className="flex justify-between p-3 rounded-lg bg-savia-bg/50"><span className="text-savia-text-muted">IA Engine</span><span className="font-bold text-green-400">Gemini Pro ✓</span></div>
            <div className="flex justify-between p-3 rounded-lg bg-savia-bg/50"><span className="text-savia-text-muted">Licence</span><span className="font-bold">Entreprise</span></div>
          </div>
        </SectionCard>
      </div>

      <button className="w-full py-3 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all flex items-center justify-center gap-2 cursor-pointer">
        <Save className="w-5 h-5" /> Sauvegarder les paramètres
      </button>
    </div>
  );
}
