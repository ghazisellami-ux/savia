'use client';
import { SectionCard } from '@/components/ui/cards';

const JOURS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
const HEURES = ['08:00', '09:00', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00'];

const EVENTS = [
  { jour: 0, heure: 1, duree: 2, titre: 'MP Scanner CT-01', client: 'Clinique El Manar', tech: 'Ahmed B.', color: 'bg-green-500/20 border-green-500/40 text-green-300' },
  { jour: 1, heure: 3, duree: 3, titre: 'Réparation Mammo GE', client: 'Clinique El Manar', tech: 'Ahmed B.', color: 'bg-red-500/20 border-red-500/40 text-red-300' },
  { jour: 2, heure: 0, duree: 2, titre: 'Calibration IRM', client: 'Hôpital CH. Nicolle', tech: 'Mehdi S.', color: 'bg-blue-500/20 border-blue-500/40 text-blue-300' },
  { jour: 3, heure: 4, duree: 1, titre: 'MAJ Firmware DR-200', client: 'Centre Imagerie Lac', tech: 'Sami K.', color: 'bg-purple-500/20 border-purple-500/40 text-purple-300' },
  { jour: 4, heure: 2, duree: 4, titre: 'Install. Échographe', client: 'Polyclinique Ennasr', tech: 'Sami K.', color: 'bg-savia-accent/20 border-savia-accent/40 text-savia-accent' },
  { jour: 0, heure: 5, duree: 2, titre: 'Vérif. Arceau', client: 'Hôpital CH. Nicolle', tech: 'Mehdi S.', color: 'bg-yellow-500/20 border-yellow-500/40 text-yellow-300' },
];

export default function PlanningPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-black gradient-text">📅 Planning Interventions</h1>
        <p className="text-savia-text-muted text-sm mt-1">Semaine du 17 au 22 Mars 2025</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-savia-accent">{EVENTS.length}</div><div className="text-xs text-savia-text-muted mt-1">Interventions planifiées</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-green-400">3</div><div className="text-xs text-savia-text-muted mt-1">Techniciens affectés</div></div>
        <div className="glass rounded-xl p-4 text-center"><div className="text-3xl font-black text-yellow-400">87%</div><div className="text-xs text-savia-text-muted mt-1">Taux occupation</div></div>
      </div>

      <SectionCard title="📋 Vue Semaine">
        <div className="overflow-x-auto">
          <div className="min-w-[800px]">
            {/* Header */}
            <div className="grid grid-cols-[80px_repeat(6,1fr)] border-b border-savia-border pb-2 mb-2">
              <div></div>
              {JOURS.map(j => (
                <div key={j} className="text-center text-sm font-bold text-savia-text-muted">{j}</div>
              ))}
            </div>
            {/* Grid */}
            {HEURES.map((h, hi) => (
              <div key={h} className="grid grid-cols-[80px_repeat(6,1fr)] min-h-[48px] border-b border-savia-border/30">
                <div className="text-xs text-savia-text-dim py-2 pr-2 text-right">{h}</div>
                {JOURS.map((_, ji) => {
                  const event = EVENTS.find(e => e.jour === ji && e.heure === hi);
                  return (
                    <div key={ji} className="relative border-l border-savia-border/20 px-1 py-0.5">
                      {event && (
                        <div className={`absolute inset-x-1 rounded-lg px-2 py-1 border text-xs cursor-pointer hover:opacity-80 transition-opacity z-10 ${event.color}`}
                          style={{ height: `${event.duree * 48 - 4}px` }}>
                          <div className="font-bold truncate">{event.titre}</div>
                          <div className="opacity-70 truncate">{event.tech}</div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </SectionCard>

      <SectionCard title="👷 Techniciens cette semaine">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {[
            { nom: 'Ahmed B.', interventions: 2, heures: 9, specialite: 'Scanner, Mammographie' },
            { nom: 'Mehdi S.', interventions: 2, heures: 6, specialite: 'IRM, Arceau' },
            { nom: 'Sami K.', interventions: 2, heures: 5, specialite: 'Radio, Échographie' },
          ].map(t => (
            <div key={t.nom} className="glass rounded-xl p-4">
              <div className="font-bold mb-1">👤 {t.nom}</div>
              <div className="text-xs text-savia-text-muted mb-2">{t.specialite}</div>
              <div className="flex gap-3 text-xs">
                <span className="px-2 py-0.5 rounded-full bg-savia-accent/10 text-savia-accent font-bold">{t.interventions} interv.</span>
                <span className="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 font-bold">{t.heures}h</span>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
