'use client';
// ==========================================
// 🛠️ PAGE SUPERVISION — SAVIA Next.js
// Monitoring machines, erreurs, diagnostic IA
// ==========================================
import { useState, useEffect, useMemo } from 'react';
import { SectionCard, HealthBadge } from '@/components/ui/cards';
import {
  AlertTriangle, Upload, Search, Cpu, Building2, FileText,
  Trash2, Send, Brain, ChevronDown, ChevronUp, Server, Activity, 
  CheckCircle2, Database, Settings, ShieldAlert, Folder, Zap, Save, Lightbulb
} from 'lucide-react';
import { equipements as equipApi, clients as clientsApi, ai as aiApi, logs as logsApi } from '@/lib/api';

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

// --- AI Fallback ---
const AI_FALLBACK: AiDiagnostic = {
  probleme: 'Instabilité de la haute tension du tube à rayons X causant des artefacts d\'image et des interruptions d\'acquisition.',
  cause: 'Dégradation progressive du générateur haute tension (HV Generator). Les condensateurs de filtrage montrent des signes de vieillissement.',
  solution: '1. Vérifier les connexions du câble HT\n2. Mesurer la tension de sortie\n3. Inspecter les condensateurs (C1-C4)\n4. Remplacer module condensateur (réf. SCA-HV-CAP-01)\n5. Test de charge complet après remplacement',
  prevention: 'Planifier inspection préventive du générateur HT tous les 6 mois.',
  urgence: 'HAUTE — Risque de dommage au tube si non traité sous 48h.',
  type: 'Hardware',
  priorite: 'HAUTE',
  confidence: 87,
};

function mapEquipToFleet(items: any[]): MachineFleet[] {
  return items.map((item: any, i: number) => {
    const health = item.Score_Sante || item.health || 80;
    const etat: 'OK' | 'ATTENTION' | 'CRITIQUE' = health >= 80 ? 'OK' : health >= 50 ? 'ATTENTION' : 'CRITIQUE';
    const errCount = item.nb_erreurs || item.erreurs || (etat === 'CRITIQUE' ? 8 : etat === 'ATTENTION' ? 4 : 1);
    const critCount = etat === 'CRITIQUE' ? Math.ceil(errCount / 3) : etat === 'ATTENTION' ? 1 : 0;
    
    // Simulate error objects if there are none
    let simulatedErrors: any[] = [];
    if (!item.errors || item.errors.length === 0) {
      if (etat === 'CRITIQUE') {
        simulatedErrors = [
          { code: `ERR-HV-0${(i%9)+1}`, message: 'Haute tension instable - variation détectée', statut: 'Non résolu', type: 'Hardware', frequence: 5 },
          { code: `ERR-TMP-0${(i%3)+1}`, message: 'Surchauffe tube détectée', statut: 'Monitoring', type: 'System', frequence: 3 }
        ];
      } else if (etat === 'ATTENTION') {
        simulatedErrors = [
          { code: `ERR-CAL-0${(i%5)+1}`, message: 'Calibration capteur requise hors tolérance', statut: 'Non résolu', type: 'Software', frequence: 2 }
        ];
      } else if (errCount > 0) {
        simulatedErrors = [
          { code: `WARN-0${(i%5)+1}`, message: 'Micro-coupure réseau passée', statut: 'Résolu', type: 'Network', frequence: 1 }
        ];
      }
    } else {
      simulatedErrors = item.errors;
    }

    return {
      machine: item.Nom || item.nom || 'Équipement',
      chemin: `logs/${(item.Nom || 'equip').replace(/\s+/g, '_')}.log`,
      etat,
      erreurs: errCount,
      critiques: critCount,
      errors: simulatedErrors,
    };
  });
}

// --- Component ---
export default function SupervisionPage() {
  const [fleet, setFleet] = useState<MachineFleet[]>([]);
  const [clientList, setClientList] = useState<string[]>([]);
  const [selectedClient, setSelectedClient] = useState('Tous');
  const [selectedEquip, setSelectedEquip] = useState('Tous');
  const [selectedMachine, setSelectedMachine] = useState<string>('');
  const [selectedError, setSelectedError] = useState<string>('');
  const [showAiDiag, setShowAiDiag] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<AiDiagnostic | null>(null);
  const [expandLogs, setExpandLogs] = useState(false);
  const [expandImport, setExpandImport] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importEquip, setImportEquip] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [importSuccess, setImportSuccess] = useState('');
  const [rawLogContent, setRawLogContent] = useState<string>('');
  const [deletingLog, setDeletingLog] = useState<string>('');

  // Delete log handler
  const handleDeleteLog = async (machine: MachineFleet) => {
    const confirmed = window.confirm(`Supprimer tous les logs de "${machine.machine}" ?\n\nCette action est irréversible.`);
    if (!confirmed) return;

    setDeletingLog(machine.machine);
    try {
      const result = await logsApi.deleteMachine(machine.machine);
      // Remove from local fleet state
      setFleet(prev => prev.filter(m => m.machine !== machine.machine));
      if (selectedMachine === machine.machine) {
        setSelectedMachine('');
        setSelectedError('');
        setAiResult(null);
        setShowAiDiag(false);
      }
      alert(`✓ ${result.message}`);
    } catch (err) {
      console.error('Delete log failed', err);
      alert('Erreur lors de la suppression des logs.');
    } finally {
      setDeletingLog('');
    }
  };

  useEffect(() => {
    async function loadData() {
      try {
        const [equipRes, clientRes] = await Promise.all([equipApi.list(), clientsApi.list()]);
        const mapped = mapEquipToFleet(equipRes);
        setFleet(mapped);
        if (mapped.length > 0) setSelectedMachine(mapped[0].machine);
        const names = clientRes.map((c: any) => c.Nom || c.nom || '').filter(Boolean);
        setClientList(names.length > 0 ? names : ['Client 1']);
      } catch (err) {
        console.error('Failed to load supervision data', err);
      }
    }
    loadData();
  }, []);

  // Filter machines
  const filteredFleet = useMemo(() => {
    return fleet.filter(m => {
      if (selectedClient !== 'Tous') {
        const idx = fleet.indexOf(m);
        const client = clientList[idx % clientList.length];
        if (client !== selectedClient) return false;
      }
      if (selectedEquip !== 'Tous' && m.machine !== selectedEquip) return false;
      return true;
    });
  }, [selectedClient, selectedEquip, fleet, clientList]);

  const currentMachine = fleet.find(m => m.machine === selectedMachine) || fleet[0];

  const handleAnalyzeAI = async () => {
    setAiLoading(true);
    try {
      const err = currentMachine.errors.find((e: any) => e.code === selectedError);
      if (!err) return;
      
      const response = await aiApi.analyzeDiagnostic(
        currentMachine.machine, 
        err.code, 
        err.message, 
        "Pas de logs supplementaires specifiés"
      );
      
      if (response && response.ok && response.result) {
        setAiResult(response.result as AiDiagnostic);
      } else {
        // Dynamic fallback using the error's own data
        setAiResult({
          probleme: `Erreur ${err.code} sur ${currentMachine.machine}: ${err.message}`,
          cause: `Analyse automatique indisponible. Code ${err.code} détecté ${err.frequence} fois.`,
          solution: `1. Inspecter l'équipement ${currentMachine.machine}\n2. Rechercher le code ${err.code} dans la base de connaissances\n3. Consulter la documentation technique`,
          prevention: `Planifier une maintenance préventive pour ${currentMachine.machine}.`,
          urgence: err.statut === 'INCONNU' ? 'À ÉVALUER — Statut inconnu' : 'MOYENNE',
          type: err.type || '?',
          priorite: err.frequence > 10 ? 'HAUTE' : err.frequence > 3 ? 'MOYENNE' : 'BASSE',
          confidence: 0,
        });
      }
    } catch (error) {
      console.error("AI Error", error);
      const err = currentMachine.errors.find((e: any) => e.code === selectedError);
      // Dynamic fallback on error — specific to this error code
      setAiResult({
        probleme: `Erreur ${err?.code || selectedError} — ${err?.message || 'Erreur inconnue'}`,
        cause: `L'IA Gemini n'est pas disponible. Configurez GOOGLE_API_KEY dans le fichier .env du backend.`,
        solution: `1. Vérifier ${err?.code || selectedError} dans la documentation\n2. Consulter la base de connaissances locale\n3. Contacter le support technique si nécessaire`,
        prevention: 'Configurer GOOGLE_API_KEY pour activer les diagnostics IA automatiques.',
        urgence: `Fréquence: ${err?.frequence || '?'} occurrence(s)`,
        type: err?.type || '?',
        priorite: 'MOYENNE',
        confidence: 0,
      });
    } finally {
      setAiLoading(false);
      setShowAiDiag(true);
    }
  };

  const handleImportLog = async () => {
    if (!importFile || !importEquip) return;
    setImportLoading(true);
    setImportSuccess('');
    try {
      const text = await importFile.text();
      setRawLogContent(text);
      const lines = text.split('\n').filter(l => l.trim());
      // ---- V0-compatible log parser (matches Streamlit log_analyzer.py) ----
      const isCSV = lines.slice(0, 20).filter(l => l.trim().startsWith('"') && l.includes('","')).length >= 3;
      const rawEvents: Array<{code: string; message: string; severite: string}> = [];

      if (isCSV) {
        // CSV Parser (Giotto/IMS format)
        for (const line of lines) {
          const row: string[] = [];
          let cur = '', inQ = false;
          for (let c = 0; c < line.length; c++) {
            if (line[c] === '"') { inQ = !inQ; continue; }
            if (line[c] === ',' && !inQ) { row.push(cur.trim()); cur = ''; continue; }
            cur += line[c];
          }
          row.push(cur.trim());
          if (row.length < 6) continue;
          const level = row[3], codeNum = row[4], msg = row[5];
          const subMsg = row.length > 7 ? row[7] : '';
          if (level === 'Info' && !msg.includes('Error') && !msg.includes('Fault')) continue;
          let sev = 'ATTENTION';
          if (level === 'Alarm') sev = 'ERREUR';
          else if (level === 'Critical' || level === 'Fatal') sev = 'CRITIQUE';
          let msgClean = msg;
          if (subMsg && subMsg !== msg) msgClean = `${msg} \u2014 ${subMsg}`;
          const stErr: string[] = [];
          for (let s = 8; s + 1 < row.length; s += 2) { if (row[s+1] === 'State Error') stErr.push(row[s]); }
          if (stErr.length > 0) msgClean += ` [${stErr.join(', ')}]`;
          rawEvents.push({ code: codeNum, message: msgClean, severite: sev });
        }
      } else {
        // Text Log Parser
        for (const line of lines) {
          const t = line.trim();
          if (!t) continue;
          const tsM = t.match(/(\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}:\d{2})/);
          const noTs = tsM ? t.replace(tsM[0], '').trim() : t;
          let sev = '';
          if (/\b(CRITICAL|FATAL|CRITIQUE)\b/i.test(t)) sev = 'CRITIQUE';
          else if (/\b(ERROR|ERREUR)\b/i.test(t)) sev = 'ERREUR';
          else if (/\b(WARNING|WARN|ATTENTION|ALARM)\b/i.test(t)) sev = 'ATTENTION';
          const sM = noTs.match(/(?:Code|code|ERR|Err|ERROR|error|FAULT|fault)[:\s]+([0-9A-Fa-f]{2,8})/);
          if (sM) {
            const code = sM[1].toUpperCase();
            const mM = noTs.match(/(?:Code|ERR|ERROR|FAULT)[:\s]+[0-9A-Fa-f]{2,8}\s*[-:]\s*(.+)/i);
            rawEvents.push({ code, message: mM ? mM[1].trim().substring(0, 120) : 'Erreur Inconnue', severite: sev || 'ATTENTION' });
            continue;
          }
          const hM = noTs.match(/(?<![0-9A-Za-z])0x([0-9A-Fa-f]{2,8})(?![0-9A-Za-z])/);
          if (hM) { rawEvents.push({ code: hM[1].toUpperCase(), message: 'Erreur Inconnue', severite: sev || 'ATTENTION' }); continue; }
          if (sev) {
            const mc = noTs.replace(/\[.*?\]/g, '').trim().replace(/^\d+\s*/, '').trim();
            const nc = t.match(/\b(\d{2,4})\b/);
            rawEvents.push({ code: nc ? nc[1] : 'TXT', message: (mc || t).substring(0, 120), severite: sev });
          }
        }
      }
      // Aggregate by code with frequency (like V0)
      const parsedErrors: Array<{code: string; message: string; statut: string; type: string; frequence: number}> = [];
      let errCount = 0, critCount = 0;
      for (const evt of rawEvents) {
        errCount++;
        if (evt.severite === 'CRITIQUE') critCount++;
        const ex = parsedErrors.find(e => e.code === evt.code);
        if (ex) { ex.frequence++; }
        else { parsedErrors.push({ code: evt.code, message: evt.message, statut: 'INCONNU', type: '?', frequence: 1 }); }
      }
      parsedErrors.sort((a, b) => b.frequence - a.frequence);
      if (parsedErrors.length === 0 && lines.length > 0) {
        parsedErrors.push({ code: 'INFO', message: `${lines.length} lignes - aucune erreur`, statut: 'OK', type: 'Info', frequence: lines.length });
      }

      // Update fleet for the selected equipment
      setFleet(prev => prev.map(m => {
        if (m.machine !== importEquip) return m;
        return {
          ...m,
          chemin: importFile.name,
          erreurs: errCount,
          critiques: critCount,
          etat: critCount > 0 ? 'CRITIQUE' as const : errCount > 0 ? 'ATTENTION' as const : 'OK' as const,
          errors: parsedErrors,
        };
      }));
      // Select this machine and its first error if any
      setSelectedMachine(importEquip);
      if (parsedErrors.length > 0 && parsedErrors[0].statut !== 'OK') {
        setSelectedError(parsedErrors[0].code);
      }
      setImportSuccess(`✓ ${lines.length} lignes parsées — ${errCount} erreur(s) détectée(s) dont ${critCount} critique(s)`);
      setImportFile(null);

      // Save log to backend database
      try {
        const token = localStorage.getItem('savia_token');
        await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/logs/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
          body: JSON.stringify({
            equipement: importEquip,
            filename: importFile.name,
            content: text,
            nb_errors: errCount,
            nb_critiques: critCount,
          }),
        });
      } catch (saveErr) {
        console.warn('Log save to DB failed (non-blocking):', saveErr);
      }
      // Reset file input
      const fileInput = document.getElementById('log-file-input') as HTMLInputElement;
      if (fileInput) fileInput.value = '';
    } catch (err) {
      console.error('Import error:', err);
      setImportSuccess('✗ Erreur lors de l\'import du fichier');
    } finally {
      setImportLoading(false);
    }
  };

  const critCount = fleet.filter(m => m.etat === 'CRITIQUE').length;
  const attCount = fleet.filter(m => m.etat === 'ATTENTION').length;
  const okCount = fleet.filter(m => m.etat === 'OK').length;

  if (fleet.length === 0 || !currentMachine) {
    return <div className="flex justify-center items-center h-64"><div className="w-8 h-8 border-4 border-savia-accent border-t-transparent rounded-full animate-spin" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
          <Activity className="w-8 h-8 text-savia-accent" /> Supervision — Monitoring Machines
        </h1>
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
            <span className="font-semibold">Importer un fichier Log</span>
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
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Server className="w-4 h-4" /> Associer à l&apos;équipement
                </label>
                <select
                  value={importEquip}
                  onChange={e => setImportEquip(e.target.value)}
                  className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40"
                >
                  <option value="">— Sélectionner un équipement —</option>
                  {fleet.map(m => (
                    <option key={m.machine} value={m.machine}>{m.machine}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <FileText className="w-4 h-4" /> Fichier Log
                </label>
                <input
                  id="log-file-input"
                  type="file"
                  accept=".log,.txt,.csv,.elg2"
                  onChange={e => setImportFile(e.target.files?.[0] || null)}
                  className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2 text-savia-text
                             file:mr-4 file:py-1 file:px-3 file:rounded-md file:border-0
                             file:text-sm file:font-semibold file:bg-savia-accent/20 file:text-savia-accent
                             hover:file:bg-savia-accent/30 file:cursor-pointer"
                />
              </div>
            </div>
            <button
              onClick={handleImportLog}
              disabled={!importFile || !importEquip || importLoading}
              className="w-full py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {importLoading ? 'Analyse en cours...' : 'Enregistrer et analyser'}
            </button>
            {importSuccess && (
              <div className={`text-sm p-2 rounded-lg ${importSuccess.startsWith('✓') ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                {importSuccess}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
            <Building2 className="w-4 h-4" /> Client
          </label>
          <select
            value={selectedClient}
            onChange={e => setSelectedClient(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40"
          >
            <option value="Tous">Tous les clients</option>
            {clientList.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
            <Server className="w-4 h-4" /> Équipement
          </label>
          <select
            value={selectedEquip}
            onChange={e => setSelectedEquip(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40"
          >
            <option value="Tous">Tous les équipements</option>
            {fleet.map(m => <option key={m.machine} value={m.machine}>{m.machine}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
            <FileText className="w-4 h-4" /> Fichier Log
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
          <CheckCircle2 className="w-12 h-12 mb-3 mx-auto text-savia-success" />
          <p className="text-savia-success font-bold text-lg">{currentMachine.machine} — Système sain</p>
          <p className="text-savia-text-muted text-sm mt-1">Aucune erreur détectée dans les logs.</p>
        </div>
      ) : (
        <SectionCard title={<span className="flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-savia-accent" /> Erreurs détectées sur {currentMachine.machine}</span>}>
          <div className="overflow-x-auto max-h-[280px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-900 z-10">
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
                    onClick={() => { setSelectedError(err.code); setAiResult(null); setShowAiDiag(false); }}
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
                <Database className="w-5 h-5 inline mr-1 -mt-1 text-red-500" /> Code : <span className="text-savia-accent font-mono">{err.code}</span> — {err.message}
              </h3>
              <div className="flex items-center gap-2 mb-4">
                <span className="px-3 py-1 rounded-full text-xs font-bold bg-red-500/10 text-red-400 border border-red-500/20">
                  <AlertTriangle className="w-4 h-4 inline mr-1 -mt-0.5 text-red-400" /> Erreur INCONNUE — Aucune solution dans la base
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
                    Analyse IA en cours...
                  </>
                ) : (
                  <>
                    <Brain className="w-5 h-5" />
                    Analyser avec l&apos;IA (Gemini)
                  </>
                )}
              </button>
            </div>

            {/* AI Diagnostic Results */}
            {showAiDiag && aiResult && (
              <div className="space-y-4 animate-fade-in">
                <h3 className="text-lg font-bold gradient-text flex items-center gap-2"><Brain className="w-5 h-5" /> Résultat du Diagnostic IA</h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Problème */}
                  <div className="rounded-xl p-4 border-l-4 border-l-red-500 bg-red-500/5">
                    <div className="flex items-center gap-2 text-red-400 font-bold text-xs uppercase tracking-wider mb-2"><AlertTriangle className="w-4 h-4" /> Problème identifié</div>
                    <p className="text-savia-text text-sm">{aiResult.probleme}</p>
                  </div>
                  {/* Cause */}
                  <div className="rounded-xl p-4 border-l-4 border-l-yellow-500 bg-yellow-500/5">
                    <div className="flex items-center gap-2 text-yellow-400 font-bold text-xs uppercase tracking-wider mb-2"><Search className="w-4 h-4" /> Cause probable</div>
                    <p className="text-savia-text text-sm">{aiResult.cause}</p>
                  </div>
                </div>

                {/* Solution */}
                <div className="rounded-xl p-4 border-l-4 border-l-green-500 bg-green-500/5">
                  <div className="flex items-center gap-2 text-green-400 font-bold text-xs uppercase tracking-wider mb-2"><Settings className="w-4 h-4" /> Procédure d&apos;investigation</div>
                  <pre className="text-savia-text text-sm whitespace-pre-wrap font-sans">{aiResult.solution}</pre>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Prévention */}
                  <div className="rounded-xl p-4 border-l-4 border-l-blue-500 bg-blue-500/5">
                    <div className="flex items-center gap-2 text-blue-400 font-bold text-xs uppercase tracking-wider mb-2"><ShieldAlert className="w-4 h-4" /> Maintenance préventive</div>
                    <p className="text-savia-text text-sm">{aiResult.prevention}</p>
                  </div>
                  {/* Urgence */}
                  <div className="rounded-xl p-4 border-l-4 border-l-purple-500 bg-purple-500/5">
                    <div className="flex items-center gap-2 text-purple-400 font-bold text-xs uppercase tracking-wider mb-2"><Activity className="w-4 h-4" /> Évaluation d&apos;urgence</div>
                    <p className="text-savia-text text-sm">{aiResult.urgence}</p>
                  </div>
                </div>

                {/* Badges */}
                <div className="flex gap-3">
                  <span className="px-4 py-1.5 rounded-full text-xs font-bold bg-blue-500/10 text-blue-400">
                    <Folder className="w-3 h-3 inline mr-1 -mt-0.5" /> {aiResult.type}
                  </span>
                  <span className={`px-4 py-1.5 rounded-full text-xs font-bold
                    ${aiResult.priorite === 'HAUTE' ? 'bg-red-500/10 text-red-400' :
                      aiResult.priorite === 'MOYENNE' ? 'bg-yellow-500/10 text-yellow-400' :
                      'bg-green-500/10 text-green-400'}`}>
                    <Zap className="w-3 h-3 inline mr-1 -mt-0.5" /> {aiResult.priorite}
                  </span>
                  <span className={`px-4 py-1.5 rounded-full text-xs font-bold
                    ${aiResult.confidence >= 80 ? 'bg-green-500/10 text-green-400' :
                      aiResult.confidence >= 50 ? 'bg-yellow-500/10 text-yellow-400' :
                      'bg-red-500/10 text-red-400'}`}>
                    <CheckCircle2 className="w-3 h-3 inline mr-1 -mt-0.5" /> Confiance: {aiResult.confidence}%
                  </span>
                </div>
              </div>
            )}

            {/* Save to Knowledge Base */}
            <SectionCard title={<span className="flex items-center gap-2"><Save className="w-4 h-4 text-savia-accent" /> Enregistrer dans la Base de Connaissances</span>}>
              <p className="text-savia-text-muted text-sm mb-4 italic">
                Remplissez ce formulaire avec la solution qui a réellement fonctionné sur le terrain.
              </p>
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Settings className="w-4 h-4" /> Cause confirmée
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
                  <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                    <Lightbulb className="w-4 h-4" /> Solution appliquée
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
                    <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2"><Folder className="w-4 h-4" /> Type</label>
                    <select className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
                      {['Hardware', 'Software', 'Calibration', 'Power', 'Network', 'Autre'].map(t => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2"><Zap className="w-4 h-4" /> Priorité</label>
                    <select className="w-full bg-savia-bg/50 border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
                      {['HAUTE', 'MOYENNE', 'BASSE'].map(p => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <button className="w-full py-3 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer">
                  <Save className="w-5 h-5 inline mr-2 -mt-1" /> Enregistrer dans la base
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
            <span className="font-semibold">Voir les logs bruts</span>
          </div>
          {expandLogs ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {expandLogs && (
          <div className="p-4 pt-0 border-t border-savia-border/50">
            {rawLogContent ? (
              <pre className="text-xs text-savia-text-dim font-mono bg-savia-bg rounded-lg p-4 overflow-x-auto max-h-[400px] overflow-y-auto whitespace-pre-wrap">
                {rawLogContent}
              </pre>
            ) : (
              <div className="text-center py-8 text-savia-text-muted">
                <FileText className="w-10 h-10 mx-auto mb-2 text-savia-text-dim" />
                <p className="text-sm">Aucun fichier log importé.</p>
                <p className="text-xs mt-1">Importez un fichier log via le bouton ci-dessus pour voir son contenu brut ici.</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Fleet Status */}
      <SectionCard title={<span className="flex items-center gap-2"><Activity className="w-4 h-4 text-savia-accent" /> État du Parc</span>}>
        {/* Mini KPIs */}
        <div className="flex gap-3 mb-4">
          <div className="flex-1 text-center p-3 rounded-lg bg-red-500/10 border border-red-500/20">
          <div className="text-2xl font-black text-savia-danger">{critCount}</div>
            <div className="text-xs text-red-300 flex items-center justify-center gap-1"><AlertTriangle className="w-3 h-3" /> Critique</div>
          </div>
          <div className="flex-1 text-center p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
            <div className="text-2xl font-black text-savia-warning">{attCount}</div>
            <div className="text-xs text-yellow-300 flex items-center justify-center gap-1"><Activity className="w-3 h-3" /> Attention</div>
          </div>
          <div className="flex-1 text-center p-3 rounded-lg bg-green-500/10 border border-green-500/20">
            <div className="text-2xl font-black text-savia-success">{okCount}</div>
            <div className="text-xs text-green-300 flex items-center justify-center gap-1"><CheckCircle2 className="w-3 h-3" /> OK</div>
          </div>
        </div>

        {/* Fleet Table */}
        <div className="overflow-x-auto max-h-[300px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-slate-900 z-10">
              <tr className="border-b border-savia-border">
                <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">État</th>
                <th className="text-left py-2 px-3 text-savia-text-muted font-semibold"><Server className="w-3 h-3 inline mr-1 -mt-0.5" /> Équipement</th>
                <th className="text-left py-2 px-3 text-savia-text-muted font-semibold"><Building2 className="w-3 h-3 inline mr-1 -mt-0.5" /> Client</th>
                <th className="text-left py-2 px-3 text-savia-text-muted font-semibold"><FileText className="w-3 h-3 inline mr-1 -mt-0.5" /> Fichier</th>
                <th className="text-center py-2 px-3 text-savia-text-muted font-semibold"><AlertTriangle className="w-3 h-3 inline mr-1 -mt-0.5" /> Err.</th>
                <th className="text-center py-2 px-3 text-savia-text-muted font-semibold"><AlertTriangle className="w-3 h-3 inline mr-1 -mt-0.5 text-red-500" /> Crit.</th>
                <th className="text-center py-2 px-3 text-savia-text-muted font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {fleet.map((m, i) => (
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
                    {m.etat === 'OK' ? <CheckCircle2 className="w-5 h-5 mx-auto text-green-400" /> : m.etat === 'CRITIQUE' ? <AlertTriangle className="w-5 h-5 mx-auto text-red-500" /> : <Activity className="w-5 h-5 mx-auto text-yellow-400" />}
                  </td>
                  <td className="py-2.5 px-3 font-bold">{m.machine}</td>
                  <td className="py-2.5 px-3 text-savia-text-muted">{clientList[i % clientList.length]}</td>
                  <td className="py-2.5 px-3">
                    <code className="text-xs bg-savia-bg px-2 py-0.5 rounded">{m.chemin.split('/').pop()}</code>
                  </td>
                  <td className="py-2.5 px-3 text-center font-mono font-bold">{m.erreurs}</td>
                  <td className="py-2.5 px-3 text-center font-mono font-bold text-red-400">{m.critiques}</td>
                  <td className="py-2.5 px-3 text-center">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteLog(m); }}
                      disabled={deletingLog === m.machine}
                      title={`Supprimer les logs de ${m.machine}`}
                      className="p-1.5 rounded-lg text-savia-text-muted hover:text-red-400 hover:bg-red-500/10
                                 transition-all disabled:opacity-30 cursor-pointer"
                    >
                      {deletingLog === m.machine ? (
                        <div className="w-4 h-4 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </td>
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
            {critCount} machine(s) en état CRITIQUE
          </div>
          {fleet.filter(m => m.etat === 'CRITIQUE').map(m => (
            <div key={m.machine} className="text-sm text-savia-text-muted ml-7 mt-1">
              <AlertTriangle className="w-3 h-3 inline mr-1 -mt-0.5 text-red-400" /> <strong>{m.machine}</strong> — Code <code className="text-red-400">{m.errors[0]?.code}</code> : {m.errors[0]?.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
