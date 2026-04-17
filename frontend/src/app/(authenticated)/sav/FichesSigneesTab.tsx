'use client';
import { Camera, CheckCircle, Clock, Eye, Download } from 'lucide-react';
import { SectionCard } from '@/components/ui/cards';
import { interventions } from '@/lib/api';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Props {
  fiches: any[];
  setFiches: (f: any[]) => void;
}

export function FichesSigneesTab({ fiches, setFiches }: Props) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('savia_token') : '';
  // Seulement celles avec photo jointe
  const fichesAvecPhoto = fiches.filter((f: any) => f.has_fiche);

  const handleValidation = async (id: number) => {
    if (!window.confirm(`Valider définitivement la fiche #${id} ?\n⚠️ Cette action est irréversible.`)) return;
    try {
      await interventions.updateFicheValidation(id, 'Validée');
      const updated = await interventions.listFiches();
      setFiches(updated);
    } catch (err: any) {
      alert(err?.message || 'Erreur lors de la validation');
    }
  };

  const nbValidees = fichesAvecPhoto.filter((f: any) => f.fiche_validation === 'Validée').length;

  return (
    <SectionCard title="Fiches d'Intervention Signées">
      {/* En-tête compteurs */}
      <div className="flex items-center gap-4 mb-6">
        <div className="w-9 h-9 rounded-lg bg-green-500/15 flex items-center justify-center flex-shrink-0">
          <Camera className="w-5 h-5 text-green-400" />
        </div>
        <div className="flex gap-6">
          <div>
            <p className="text-lg font-bold text-savia-text">{fichesAvecPhoto.length}</p>
            <p className="text-xs text-savia-text-muted">fiche{fichesAvecPhoto.length !== 1 ? 's' : ''} signée{fichesAvecPhoto.length !== 1 ? 's' : ''}</p>
          </div>
          <div className="border-l border-savia-border/30 pl-6">
            <p className="text-lg font-bold text-green-400">{nbValidees}</p>
            <p className="text-xs text-savia-text-muted">validée{nbValidees !== 1 ? 's' : ''}</p>
          </div>
          <div className="border-l border-savia-border/30 pl-6">
            <p className="text-lg font-bold text-amber-400">{fichesAvecPhoto.length - nbValidees}</p>
            <p className="text-xs text-savia-text-muted">en attente</p>
          </div>
        </div>
      </div>

      {fichesAvecPhoto.length === 0 ? (
        <div className="text-center py-16 text-savia-text-muted">
          <Camera className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-sm">Aucune fiche signée avec photo</p>
          <p className="text-xs mt-1 opacity-60">Uploadez une photo lors de la clôture d&apos;une intervention</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {fichesAvecPhoto.map((f: any) => {
            const isValidee = f.fiche_validation === 'Validée';
            const ficheUrl = `${API}/api/interventions/${f.id}/fiche?token=${token}`;
            return (
              <div
                key={f.id}
                className={`rounded-xl border overflow-hidden flex flex-col transition-all ${
                  isValidee
                    ? 'border-green-500/40 bg-green-500/5'
                    : 'border-savia-border/40 bg-savia-surface-hover hover:border-amber-400/40'
                }`}
              >
                {/* ── Photo ── */}
                <div className="relative h-52 bg-savia-surface group">
                  <img
                    src={ficheUrl}
                    alt={`Fiche #${f.id}`}
                    className="w-full h-full object-cover"
                    onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
                  />
                  {/* Badge statut */}
                  <div className={`absolute top-2 right-2 px-2 py-0.5 rounded-full text-xs font-bold flex items-center gap-1 ${
                    isValidee ? 'bg-green-500 text-white' : 'bg-amber-500 text-white'
                  }`}>
                    {isValidee ? <CheckCircle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                    {isValidee ? 'Validée' : 'En attente'}
                  </div>
                  {/* Hover actions */}
                  <div className="absolute inset-0 bg-black/55 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-4">
                    <a href={ficheUrl} target="_blank" rel="noopener noreferrer"
                      className="w-11 h-11 rounded-full bg-white/20 hover:bg-white/35 flex items-center justify-center transition-colors" title="Voir en plein écran">
                      <Eye className="w-5 h-5 text-white" />
                    </a>
                    <a href={ficheUrl} download={f.fiche_photo_nom || `fiche_${f.id}.jpg`}
                      className="w-11 h-11 rounded-full bg-white/20 hover:bg-white/35 flex items-center justify-center transition-colors" title="Télécharger">
                      <Download className="w-5 h-5 text-white" />
                    </a>
                  </div>
                </div>

                {/* ── Infos ── */}
                <div className="p-4 flex flex-col gap-2 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono text-savia-accent">#{f.id}</span>
                    <span className="text-sm font-semibold text-savia-text truncate">{f.machine}</span>
                  </div>
                  <p className="text-xs text-savia-text-muted">{f.technicien}</p>
                  <p className="text-xs text-savia-text-muted/60">{String(f.date || '').substring(0, 10)}</p>
                  {f.probleme && (
                    <p className="text-xs text-savia-text-muted line-clamp-2 border-t border-savia-border/20 pt-2">{f.probleme}</p>
                  )}

                  {/* ── Validation client ── */}
                  <div className="border-t border-savia-border/20 pt-3 mt-auto">
                    <p className="text-xs text-savia-text-muted mb-2 font-medium">Validation client</p>
                    {isValidee ? (
                      <div className="flex items-center gap-2 text-green-400 bg-green-500/10 rounded-lg px-3 py-2.5">
                        <CheckCircle className="w-4 h-4 flex-shrink-0" />
                        <div>
                          <p className="text-xs font-bold">Fiche validée</p>
                          <p className="text-xs opacity-70">Aucune modification possible</p>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 text-amber-400 bg-amber-500/10 rounded-lg px-3 py-2">
                          <Clock className="w-4 h-4 flex-shrink-0" />
                          <p className="text-xs font-medium">En attente de validation</p>
                        </div>
                        <button
                          onClick={() => handleValidation(Number(f.id))}
                          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-green-500/15 hover:bg-green-500/25 text-green-400 text-xs font-bold transition-colors cursor-pointer border border-green-500/30"
                        >
                          <CheckCircle className="w-3.5 h-3.5" />
                          Marquer comme validée
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}
