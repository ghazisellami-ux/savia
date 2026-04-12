'use client';
// ==========================================
// 🛠️ PAGE SUPERVISION — SAVIA Next.js
// Monitoring machines, erreurs, diagnostic IA
// ==========================================
import { useState, useMemo } from 'react';
import { SectionCard, HealthBadge } from '@/components/ui/cards';
import {
  AlertTriangle, Upload, Search, Cpu, Building2, FileText,
  Trash2, Send, Brain, ChevronDown, ChevronUp,
} from 'lucide-react';

// --- Types ---
interface LogEntry {
  file: string;
  machine: string;
  equip_name: string;
  client: string;
}

interface MachineFleet {
  machine: string;
  chemin: string;
  etat: 'OK' | 'ATTENTION' | 'CRITIQUE';
  erreurs: number;
  critiques: number;
  errors: ErrorDetail[];
}

interface ErrorDetail {
  code: string;
  message: string;
  statut: string;
  type: string;
  frequence: number;
  raw?: string;
}

interface AiDiagnostic {
  probleme: string;
  cause: string;
  solution: string;
  prevention: string;
  urgence: string;
  type: string;
  priorite: 'HAUTE' | 'MOYENNE' | 'BASSE';
  confidence: number;
}

// --- Demo Data ---
const DEMO_FLEET: MachineFleet[] = [
  {
    machine: 'Scanner CT-01',
    chemin: 'logs/Scanner_CT-01.log',
    etat: 'CRITIQUE',
    erreurs: 12,
    critiques: 3,
    errors: [
      { code: 'ERR-HV-001', message: 'Haute tension tube instable - fluctuation détectée', statut: 'Non résolu', type: 'Hardware', frequence: 5 },
      { code: 'ERR-DT-003', message: 'Détecteur calibration offset > seuil', statut: 'Non résolu', type: 'Calibration', frequence: 4 },
      { code: 'WARN-TMP-02', message: 'Température gantry élevée (42°C)', statut: 'Monitoring', type: 'Hardware', frequence: 3 },
    ],
  },
  {
    machine: 'IRM Siemens 3T',
    chemin: 'logs/IRM_Siemens_3T.log',
    etat: 'ATTENTION',
    erreurs: 5,
    critiques: 1,
    errors: [
      { code: 'ERR-GR-012', message: 'Gradient amplifier overflow intermittent', statut: 'En cours', type: 'Hardware', frequence: 3 },
      { code: 'WARN-HE-01', message: 'Niveau hélium bas (65%)', statut: 'Monitoring', type: 'Hardware', frequence: 2 },
    ],
  },
  {
    machine: 'Radio DR-200',
    chemin: 'logs/Radio_DR-200.log',
    etat: 'OK',
    erreurs: 2,
    critiques: 0,
    errors: [
      { code: 'INFO-SW-001', message: 'Mise à jour firmware disponible v2.4.1', statut: 'Info', type: 'Software', frequence: 1 },
      { code: 'WARN-CAL-01', message: 'Calibration recommandée dans 15 jours', statut: 'Planifié', type: 'Calibration', frequence: 1 },
    ],
  },
  {
    machine: 'Mammographe GE',
    chemin: 'logs/Mammographe_GE.log',
    etat: 'CRITIQUE',
    erreurs: 8,
    critiques: 4,
    errors: [
      { code: 'ERR-C-ARM-05', message: 'Compression paddle défaillant - force irrégulière', statut: 'Non résolu', type: 'Hardware', frequence: 4 },
      { code: 'ERR-AEC-02', message: 'AEC exposure control erreur répétée', statut: 'Non résolu', type: 'Hardware', frequence: 4 },
    ],
  },
  {
    machine: 'Échographe P500',
    chemin: 'logs/Echographe_P500.log',
    etat: 'OK',
    erreurs: 0,
    critiques: 0,
    errors: [],
  },
  {
    machine: 'Arceau C-Arm',
    chemin: 'logs/Arceau_C-Arm.log',
    etat: 'ATTENTION',
    erreurs: 4,
    critiques: 1,
    errors: [
      { code: 'ERR-MOT-03', message: 'Moteur rotation bras - couple anormal', statut: 'En cours', type: 'Hardware', frequence: 2 },
      { code: 'WARN-FLT-01', message: 'Filtre d\'huile à remplacer', statut: 'Planifié', type: 'Hardware', frequence: 2 },
    ],
  },
];

const DEMO_CLIENTS = ['Clinique El Manar', 'Hôpital Charles Nicolle', 'Centre Imagerie Lac', 'Polyclinique Ennasr'];

const DEMO_AI: AiDiagnostic = {
  probleme: 'Instabilité de la haute tension du tube à rayons X causant des artefacts d\'image et des interruptions d\'acquisition.',
  cause: 'Dégradation progressive du générateur haute tension (HV Generator). Les condensateurs de filtrage montrent des signes de vieillissement, provoquant des micro-coupures et des fluctuations de tension supérieures à la tolérance de ±2%.',
  solution: '1. Vérifier les connexions du câble HT entre le générateur et le tube\n2. Mesurer la tension de sortie avec un multimètre HT calibré\n3. Inspecter les condensateurs de filtrage (C1-C4) pour signes de gonflement\n4. Si défaillants, remplacer le module condensateur (réf. SCA-HV-CAP-01)\n5. Effectuer un test de charge complète après remplacement',
  prevention: 'Planifier une inspection préventive du générateur HT tous les 6 mois. Monitorer les courbes de tension pendant les acquisitions pour détecter les dérives précoces.',
  urgence: 'HAUTE — Risque de dommage au tube si non traité sous 48h. Coût estimé du tube : 45,000€ vs coût réparation : 2,800€.',
  type: 'Hardware',
  priorite: 'HAUTE',
  confidence: 87,
};

// --- Component ---
export default function SupervisionPage() {
  const [selectedClient, setSelectedClient] = useState('Tous');
  const [selectedEquip, setSelectedEquip] = useState('Tous');
  const [selectedMachine, setSelectedMachine] = useState<string>(DEMO_FLEET[0].machine);
  const [selectedError, setSelectedError] = useState<string>('');
  const [showAiDiag, setShowAiDiag] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<AiDiagnostic | null>(null);
  const [expandLogs, setExpandLogs] = useState(false);
  const [expandImport, setExpandImport] = useState(false);

  // Filter machines
  const filteredFleet = useMemo(() => {
    return DEMO_FLEET.filter(m => {
      if (selectedClient !== 'Tous') {
        // Demo: assign clients round-robin
        const idx = DEMO_FLEET.indexOf(m);
        const client = DEMO_CLIENTS[idx % DEMO_CLIENTS.length];
        if (client !== selectedClient) return false;
      }
      if (selectedEquip !== 'Tous' && m.machine !== selectedEquip) return false;
      return true;
    });
  }, [selectedClient, selectedEquip]);

  const currentMachine = DEMO_FLEET.find(m => m.machine === selectedMachine) || DEMO_FLEET[0];

  const handleAnalyzeAI = () => {
    setAiLoading(true);
    // Simulate AI call
    setTimeout(() => {
      setAiResult(DEMO_AI);
      setAiLoading(false);
      setShowAiDiag(true);
    }, 2000);
  };

  const critCount = DEMO_FLEET.filter(m => m.etat === 'CRITIQUE').length;
  const attCount = DEMO_FLEET.filter(m => m.etat === 'ATTENTION').length;
  const okCount = DEMO_FLEET.filter(m => m.etat === 'OK').length;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-black gradient-text">🛠️ Supervision — Monitoring Machines</h1>
        <p className="text-savia-text-muted text-sm mt-1">
          Scan des logs, détection d&apos;erreurs, diagnostic IA
        </p>
      </div>

      {/* Import Log (collapsible) */}
      <div className="glass rounded-xl overflow-hidden">
        <button
          onClick={() => setExpandImport(!expandImport)}
          className="w-full flex items-center justify-between p-4 hover:bg-savia-surface-hover/30 transition-colors cursor-pointer"
        >
          <div className="flex items-center gap-3">
            <Upload className="w-5 h-5 text-savia-accent" />
            <span className="font-semibold">📥 Importer un fichier Log</span>
          </div>
          {expandImport ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {expandImport && (
          <div className="p-4 pt-0 border-t border-savia-border/50 space-y-4">
            <p className="text-savia-text-muted text-sm">
              Uploadez un fichier de log machine et associez-le à un équipement du parc.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
                  🏥 Associer à l&apos;équipement
                </label>
                <select className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40">
                  {DEMO_FLEET.map(m => (
                    <option key={m.machine} value={m.machine}>{m.machine}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
                  📄 Fichier Log
                </label>
                <input
                  type="file"
                  accept=".log,.txt,.csv,.elg2"
                  className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2 text-savia-text
                             file:mr-4 file:py-1 file:px-3 file:rounded-md file:border-0
                             file:text-sm file:font-semibold file:bg-savia-accent/20 file:text-savia-accent
                             hover:file:bg-savia-accent/30 file:cursor-pointer"
                />
              </div>
            </div>
            <button className="w-full py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
              💾 Enregistrer et analyser
            </button>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
            🏢 Client
          </label>
          <select
            value={selectedClient}
            onChange={e => setSelectedClient(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40"
          >
            <option value="Tous">Tous les clients</option>
            {DEMO_CLIENTS.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
            🏥 Équipement
          </label>
          <select
            value={selectedEquip}
            onChange={e => setSelectedEquip(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40"
          >
            <option value="Tous">Tous les équipements</option>
            {DEMO_FLEET.map(m => <option key={m.machine} value={m.machine}>{m.machine}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
            📂 Fichier Log
          </label>
          <select
            value={selectedMachine}
            onChange={e => {
              setSelectedMachine(e.target.value);
              setSelectedError('');
              setAiResult(null);
              setShowAiDiag(false);
            }}
            className="w-full bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40"
          >
            {filteredFleet.map(m => (
              <option key={m.machine} value={m.machine}>
                {m.machine} ({m.erreurs} err.)
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Errors Table */}
      {currentMachine.errors.length === 0 ? (
        <div className="glass rounded-xl p-8 text-center">
          <div className="text-4xl mb-3">✅</div>
          <p className="text-savia-success font-bold text-lg">{currentMachine.machine} — Système sain</p>
          <p className="text-savia-text-muted text-sm mt-1">Aucune erreur détectée dans les logs.</p>
        </div>
      ) : (
        <SectionCard title={`🔎 Erreurs détectées sur ${currentMachine.machine}`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-savia-border">
                  <th className="text-left py-2 px-3 text-savia-text-muted font-semibold">Code</th>
                  <th className="text-left py-2 px-3 text-savia-text-muted font-semibold">Message</th>
                  <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">Type</th>
                  <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">Fréq.</th>
                  <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">Statut</th>
                </tr>
              </thead>
              <tbody>
                {currentMachine.errors.map((err) => (
                  <tr
                    key={err.code}
                    onClick={() => setSelectedError(err.code)}
                    className={`border-b border-savia-border/50 cursor-pointer transition-colors
                      ${selectedError === err.code ? 'bg-savia-accent/10 border-l-2 border-l-savia-accent' : 'hover:bg-savia-surface-hover/50'}`}
                  >
                    <td className="py-2.5 px-3 font-mono text-savia-accent font-bold">{err.code}</td>
                    <td className="py-2.5 px-3">{err.message}</td>
                    <td className="py-2.5 px-3 text-center">
                      <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400">
                        {err.type}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-center font-mono font-bold">{err.frequence}</td>
                    <td className="py-2.5 px-3 text-center">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold
                        ${err.statut === 'Non résolu' ? 'bg-red-500/10 text-red-400' :
                          err.statut === 'En cours' ? 'bg-yellow-500/10 text-yellow-400' :
                          err.statut === 'Monitoring' ? 'bg-blue-500/10 text-blue-400' :
                          'bg-green-500/10 text-green-400'}`}>
                        {err.statut}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {/* Error Detail + AI Diagnostic */}
      {selectedError && (() => {
        const err = currentMachine.errors.find(e => e.code === selectedError);
        if (!err) return null;

        return (
          <>
            {/* Error Info Card */}
            <div className="glass rounded-xl p-5 border-l-4 border-l-red-500">
              <h3 className="text-lg font-bold mb-3">
                🆔 Code : <span className="text-savia-accent font-mono">{err.code}</span> — {err.message}
              </h3>
              <div className="flex items-center gap-2 mb-4">
                <span className="px-3 py-1 rounded-full text-xs font-bold bg-red-500/10 text-red-400 border border-red-500/20">
                  ⚠️ Erreur INCONNUE — Aucune solution dans la base
                </span>
              </div>

              {/* AI Analysis Button */}
              <button
                onClick={handleAnalyzeAI}
                disabled={aiLoading}
                className="w-full py-3 rounded-lg font-bold text-white bg-gradient-to-r from-purple-600 to-blue-600
                           hover:from-purple-500 hover:to-blue-500 disabled:opacity-50
                           transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                {aiLoading ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    🧠 Analyse IA en cours...
                  </>
                ) : (
                  <>
                    <Brain className="w-5 h-5" />
                    ✨ Analyser avec l&apos;IA (Gemini)
                  </>
                )}
              </button>
            </div>

            {/* AI Diagnostic Results */}
            {showAiDiag && aiResult && (
              <div className="space-y-4 animate-fade-in">
                <h3 className="text-lg font-bold gradient-text">📋 Résultat du Diagnostic IA</h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Problème */}
                  <div className="rounded-xl p-4 border-l-4 border-l-red-500 bg-red-500/5">
                    <div className="text-red-400 font-bold text-xs uppercase tracking-wider mb-2">🔴 Problème identifié</div>
                    <p className="text-savia-text text-sm">{aiResult.probleme}</p>
                  </div>
                  {/* Cause */}
                  <div className="rounded-xl p-4 border-l-4 border-l-yellow-500 bg-yellow-500/5">
                    <div className="text-yellow-400 font-bold text-xs uppercase tracking-wider mb-2">🟠 Cause probable</div>
                    <p className="text-savia-text text-sm">{aiResult.cause}</p>
                  </div>
                </div>

                {/* Solution */}
                <div className="rounded-xl p-4 border-l-4 border-l-green-500 bg-green-500/5">
                  <div className="text-green-400 font-bold text-xs uppercase tracking-wider mb-2">🟢 Procédure d&apos;investigation</div>
                  <pre className="text-savia-text text-sm whitespace-pre-wrap font-sans">{aiResult.solution}</pre>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Prévention */}
                  <div className="rounded-xl p-4 border-l-4 border-l-blue-500 bg-blue-500/5">
                    <div className="text-blue-400 font-bold text-xs uppercase tracking-wider mb-2">🛡️ Maintenance préventive</div>
                    <p className="text-savia-text text-sm">{aiResult.prevention}</p>
                  </div>
                  {/* Urgence */}
                  <div className="rounded-xl p-4 border-l-4 border-l-purple-500 bg-purple-500/5">
                    <div className="text-purple-400 font-bold text-xs uppercase tracking-wider mb-2">⏱️ Évaluation d&apos;urgence</div>
                    <p className="text-savia-text text-sm">{aiResult.urgence}</p>
                  </div>
                </div>

                {/* Badges */}
                <div className="flex gap-3">
                  <span className="px-4 py-1.5 rounded-full text-xs font-bold bg-blue-500/10 text-blue-400">
                    📁 {aiResult.type}
                  </span>
                  <span className={`px-4 py-1.5 rounded-full text-xs font-bold
                    ${aiResult.priorite === 'HAUTE' ? 'bg-red-500/10 text-red-400' :
                      aiResult.priorite === 'MOYENNE' ? 'bg-yellow-500/10 text-yellow-400' :
                      'bg-green-500/10 text-green-400'}`}>
                    ⚡ {aiResult.priorite}
                  </span>
                  <span className={`px-4 py-1.5 rounded-full text-xs font-bold
                    ${aiResult.confidence >= 80 ? 'bg-green-500/10 text-green-400' :
                      aiResult.confidence >= 50 ? 'bg-yellow-500/10 text-yellow-400' :
                      'bg-red-500/10 text-red-400'}`}>
                    🎯 Confiance: {aiResult.confidence}%
                  </span>
                </div>
              </div>
            )}

            {/* Save to Knowledge Base */}
            <SectionCard title="💾 Enregistrer dans la Base de Connaissances">
              <p className="text-savia-text-muted text-sm mb-4 italic">
                Remplissez ce formulaire avec la solution qui a réellement fonctionné sur le terrain.
              </p>
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
                    🔧 Cause confirmée
                  </label>
                  <input
                    type="text"
                    defaultValue={aiResult?.cause || ''}
                    placeholder="Décrivez la cause réelle du problème"
                    className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text
                               focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">
                    💡 Solution appliquée
                  </label>
                  <textarea
                    rows={3}
                    defaultValue={aiResult?.solution || ''}
                    placeholder="Décrivez les étapes de la solution qui a fonctionné"
                    className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text
                               focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim resize-none"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">📁 Type</label>
                    <select className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
                      {['Hardware', 'Software', 'Calibration', 'Power', 'Network', 'Autre'].map(t => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2">⚡ Priorité</label>
                    <select className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
                      {['HAUTE', 'MOYENNE', 'BASSE'].map(p => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <button className="w-full py-3 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
                  💾 Enregistrer dans la base
                </button>
              </div>
            </SectionCard>
          </>
        );
      })()}

      {/* Raw Logs (collapsible) */}
      <div className="glass rounded-xl overflow-hidden">
        <button
          onClick={() => setExpandLogs(!expandLogs)}
          className="w-full flex items-center justify-between p-4 hover:bg-savia-surface-hover/30 transition-colors cursor-pointer"
        >
          <div className="flex items-center gap-3">
            <FileText className="w-5 h-5 text-savia-text-muted" />
            <span className="font-semibold">📄 Voir les logs bruts</span>
          </div>
          {expandLogs ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {expandLogs && (
          <div className="p-4 pt-0 border-t border-savia-border/50">
            <pre className="text-xs text-savia-text-dim font-mono bg-savia-bg rounded-lg p-4 overflow-x-auto max-h-64 overflow-y-auto">
{`[2025-03-15 08:23:01] INFO  System startup sequence initiated
[2025-03-15 08:23:12] INFO  Detector warmup: OK (32°C)
[2025-03-15 08:23:45] WARN  HV Generator: ripple exceeds 1.8% (threshold: 2.0%)
[2025-03-15 08:24:01] INFO  Tube current: 250mA - nominal
[2025-03-15 09:15:33] ERROR ERR-HV-001: Haute tension tube instable - fluctuation de 4.2%
[2025-03-15 09:15:34] ERROR Acquisition aborted - patient scan interrupted
[2025-03-15 09:15:35] WARN  Auto-retry scheduled in 30 seconds
[2025-03-15 09:16:05] INFO  Retry attempt 1/3
[2025-03-15 09:16:12] ERROR ERR-HV-001: Haute tension tube instable - fluctuation de 3.8%
[2025-03-15 09:16:35] INFO  Retry attempt 2/3
[2025-03-15 09:17:02] INFO  Acquisition completed (degraded mode)
[2025-03-15 10:45:22] WARN  TMP-02: Gantry temperature 42°C (warning threshold: 40°C)
[2025-03-15 11:30:00] INFO  Calibration check: detector offset 0.12 (max: 0.15)
[2025-03-15 14:22:11] ERROR ERR-DT-003: Détecteur calibration offset 0.18 > seuil 0.15`}
            </pre>
          </div>
        )}
      </div>

      {/* Fleet Status */}
      <SectionCard title="📋 État du Parc">
        {/* Mini KPIs */}
        <div className="flex gap-3 mb-4">
          <div className="flex-1 text-center p-3 rounded-lg bg-red-500/10 border border-red-500/20">
            <div className="text-2xl font-black text-savia-danger">{critCount}</div>
            <div className="text-xs text-red-300">🔴 Critique</div>
          </div>
          <div className="flex-1 text-center p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
            <div className="text-2xl font-black text-savia-warning">{attCount}</div>
            <div className="text-xs text-yellow-300">🟡 Attention</div>
          </div>
          <div className="flex-1 text-center p-3 rounded-lg bg-green-500/10 border border-green-500/20">
            <div className="text-2xl font-black text-savia-success">{okCount}</div>
            <div className="text-xs text-green-300">🟢 OK</div>
          </div>
        </div>

        {/* Fleet Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-savia-border">
                <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">État</th>
                <th className="text-left py-2 px-3 text-savia-text-muted font-semibold">🏥 Équipement</th>
                <th className="text-left py-2 px-3 text-savia-text-muted font-semibold">🏢 Client</th>
                <th className="text-left py-2 px-3 text-savia-text-muted font-semibold">📄 Fichier</th>
                <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">⚠️ Err.</th>
                <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">🔴 Crit.</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_FLEET.map((m, i) => (
                <tr
                  key={m.machine}
                  className={`border-b border-savia-border/50 cursor-pointer transition-colors
                    ${selectedMachine === m.machine ? 'bg-savia-accent/5' : 'hover:bg-savia-surface-hover/50'}`}
                  onClick={() => {
                    setSelectedMachine(m.machine);
                    setSelectedError('');
                    setAiResult(null);
                    setShowAiDiag(false);
                  }}
                >
                  <td className="py-2.5 px-3 text-center text-lg">
                    {m.etat === 'OK' ? '🟢' : m.etat === 'CRITIQUE' ? '🔴' : '🟡'}
                  </td>
                  <td className="py-2.5 px-3 font-bold">{m.machine}</td>
                  <td className="py-2.5 px-3 text-savia-text-muted">{DEMO_CLIENTS[i % DEMO_CLIENTS.length]}</td>
                  <td className="py-2.5 px-3">
                    <code className="text-xs bg-savia-bg px-2 py-0.5 rounded">{m.chemin.split('/').pop()}</code>
                  </td>
                  <td className="py-2.5 px-3 text-center font-mono font-bold">{m.erreurs}</td>
                  <td className="py-2.5 px-3 text-center font-mono font-bold text-red-400">{m.critiques}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      {/* Critical Alerts */}
      {critCount > 0 && (
        <div className="rounded-xl p-4 bg-red-500/10 border border-red-500/20">
          <div className="flex items-center gap-2 text-red-400 font-bold mb-2">
            <AlertTriangle className="w-5 h-5" />
            🚨 {critCount} machine(s) en état CRITIQUE
          </div>
          {DEMO_FLEET.filter(m => m.etat === 'CRITIQUE').map(m => (
            <div key={m.machine} className="text-sm text-savia-text-muted ml-7 mt-1">
              ⚠️ <strong>{m.machine}</strong> — Code <code className="text-red-400">{m.errors[0]?.code}</code> : {m.errors[0]?.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
