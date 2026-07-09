'use client';
import { Camera, CheckCircle, Clock, Eye, Download, Trash2, Upload, X } from 'lucide-react';
import { useState, useRef } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { interventions } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

const API = process.env.NEXT_PUBLIC_API_URL || '';

interface Props {
  fiches: any[];
  setFiches: (f: any[]) => void;
}

export function FichesSigneesTab({ fiches, setFiches }: Props) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('savia_token') : '';
  const { user } = useAuth();
  const [uploadingId, setUploadingId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  
  // Seulement celles avec photo jointe
  const fichesAvecPhoto = fiches.filter((f: any) => f.has_fiche);
  
  // Vérifier si l'utilisateur peut supprimer/modifier
  const canManageFiches = user?.role === 'Admin' || user?.role === 'Manager';

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

  const handleDeleteFiche = async (id: number) => {
    if (!window.confirm(`Supprimer la fiche #${id} ?\n⚠️ Cette action est irréversible.`)) return;
    try {
      const response = await fetch(`/api/interventions/${id}/fiche`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Erreur lors de la suppression');
      }
      const updated = await interventions.listFiches();
      setFiches(updated);
      alert('Fiche supprimée avec succès');
    } catch (err: any) {
      alert(err?.message || 'Erreur lors de la suppression');
    }
  };

  const handleUploadFiche = async (id: number, file: File) => {
    if (!file) return;
    setUploadingId(id);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const response = await fetch(`/api/interventions/${id}/fiche`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Erreur lors de l\'upload');
      }
      const updated = await interventions.listFiches();
      setFiches(updated);
      alert('Fiche mise à jour avec succès');
    } catch (err: any) {
      alert(err?.message || 'Erreur lors de l\'upload');
    } finally {
      setUploadingId(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      if (cameraInputRef.current) cameraInputRef.current.value = '';
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
            <p className="text-xs text-savia-text-muted">{fichesAvecPhoto.length === 1 ? 'fiche signée' : 'fiches signées'}</p>
          </div>
          <div className="border-l border-savia-border/30 pl-6">
            <p className="text-lg font-bold text-green-400">{nbValidees}</p>
            <p className="text-xs text-savia-text-muted">{nbValidees === 1 ? 'validée' : 'validées'}</p>
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
                    {canManageFiches && !isValidee && (
                      <button
                        onClick={() => handleDeleteFiche(f.id)}
                        className="w-11 h-11 rounded-full bg-red-500/30 hover:bg-red-500/50 flex items-center justify-center transition-colors"
                        title="Supprimer la fiche"
                      >
                        <Trash2 className="w-5 h-5 text-red-300" />
                      </button>
                    )}
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
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleValidation(Number(f.id))}
                            className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-green-500/15 hover:bg-green-500/25 text-green-400 text-xs font-bold transition-colors cursor-pointer border border-green-500/30"
                          >
                            <CheckCircle className="w-3.5 h-3.5" />
                            Valider
                          </button>
                          {canManageFiches && (
                            <button
                              onClick={() => handleDeleteFiche(Number(f.id))}
                              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-red-500/15 hover:bg-red-500/25 text-red-400 text-xs font-bold transition-colors cursor-pointer border border-red-500/30"
                              title="Supprimer la fiche"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                              Supprimer
                            </button>
                          )}
                        </div>
                        {canManageFiches && (
                          <div className="flex gap-2 pt-2 border-t border-savia-border/20">
                            <button
                              onClick={() => fileInputRef.current?.click()}
                              disabled={uploadingId === f.id}
                              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-blue-500/15 hover:bg-blue-500/25 text-blue-400 text-xs font-bold transition-colors cursor-pointer border border-blue-500/30 disabled:opacity-50"
                              title="Uploader une nouvelle photo"
                            >
                              <Upload className="w-3.5 h-3.5" />
                              {uploadingId === f.id ? 'Upload...' : 'Uploader'}
                            </button>
                            <button
                              onClick={() => cameraInputRef.current?.click()}
                              disabled={uploadingId === f.id}
                              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-purple-500/15 hover:bg-purple-500/25 text-purple-400 text-xs font-bold transition-colors cursor-pointer border border-purple-500/30 disabled:opacity-50"
                              title="Prendre une photo avec la caméra"
                            >
                              <Camera className="w-3.5 h-3.5" />
                              {uploadingId === f.id ? 'Caméra...' : 'Caméra'}
                            </button>
                          </div>
                        )}
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept="image/*"
                          style={{ display: 'none' }}
                          onChange={(e) => {
                            if (e.target.files?.[0]) {
                              handleUploadFiche(f.id, e.target.files[0]);
                            }
                          }}
                        />
                        <input
                          ref={cameraInputRef}
                          type="file"
                          accept="image/*"
                          capture="environment"
                          style={{ display: 'none' }}
                          onChange={(e) => {
                            if (e.target.files?.[0]) {
                              handleUploadFiche(f.id, e.target.files[0]);
                            }
                          }}
                        />
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
