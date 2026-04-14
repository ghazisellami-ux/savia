'use client';
import { SectionCard } from '@/components/ui/cards';
import {
  Search, Loader2, BookOpen, Download, FileSpreadsheet, FileText,
  FileType, Upload, AlertTriangle, Zap, Wrench, Lightbulb, Tag
} from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import { knowledge } from '@/lib/api';

interface KnowledgeItem {
  code: string;
  message: string;
  cause: string;
  solution: string;
  type: string;
  priorite: string;
}

export default function KnowledgePage() {
  const [search, setSearch] = useState('');
  const [data, setData] = useState<KnowledgeItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'excel' | 'pdf' | 'word'>('excel');
  const [importMsg, setImportMsg] = useState('');
  const [importLoading, setImportLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadData = async () => {
    try {
      const res = await knowledge.list();
      const mapped = res.map((item: any) => ({
        code: item.Code_Erreur || item.code || '',
        message: item.Message || item.message || '',
        cause: item.Cause || item.cause || '',
        solution: item.Solution || item.solution || '',
        type: item.Type || item.type || 'Hardware',
        priorite: item.Priorite || item.priorite || 'MOYENNE',
      }));
      setData(mapped);
    } catch (err) {
      console.error("Failed to fetch knowledge", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const handleImport = async (file: File) => {
    setImportLoading(true);
    setImportMsg('');
    try {
      const token = localStorage.getItem('token');
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/knowledge/import`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      });
      const json = await res.json();
      if (res.ok && json.ok) {
        setImportMsg(`✓ ${json.imported} codes importés avec succès.`);
        await loadData();
      } else {
        setImportMsg(`✗ ${json.detail || 'Erreur inconnue'}`);
      }
    } catch (e: any) {
      setImportMsg(`✗ Erreur: ${e.message}`);
    } finally {
      setImportLoading(false);
    }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleImport(f);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleImport(f);
  };

  const filtered = data.filter(k =>
    !search ||
    k.code.toLowerCase().includes(search.toLowerCase()) ||
    k.message.toLowerCase().includes(search.toLowerCase()) ||
    k.solution.toLowerCase().includes(search.toLowerCase())
  );

  const prioriteColor = (p: string) => {
    if (p === 'HAUTE') return 'bg-red-500/10 text-red-400';
    if (p === 'MOYENNE') return 'bg-yellow-500/10 text-yellow-400';
    return 'bg-green-500/10 text-green-400';
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-savia-accent" />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-black gradient-text flex items-center gap-2">
          <BookOpen className="w-6 h-6" /> Base de Connaissances
        </h1>
        <p className="text-savia-text-muted text-sm mt-1">{data.length} solutions documentées</p>
      </div>

      {/* Import Section */}
      <SectionCard title={<span className="flex items-center gap-2"><Download className="w-4 h-4 text-savia-accent" /> Importer des données</span>}>
        {/* Tabs */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setActiveTab('excel')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all cursor-pointer ${
              activeTab === 'excel'
                ? 'bg-green-500/10 text-green-400 border border-green-500/30'
                : 'bg-savia-bg text-savia-text-muted hover:bg-savia-bg/80 border border-savia-border/30'
            }`}
          >
            <FileSpreadsheet className="w-4 h-4" /> Excel / CSV
          </button>
          <button
            onClick={() => setActiveTab('pdf')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all cursor-pointer ${
              activeTab === 'pdf'
                ? 'bg-red-500/10 text-red-400 border border-red-500/30'
                : 'bg-savia-bg text-savia-text-muted hover:bg-savia-bg/80 border border-savia-border/30'
            }`}
          >
            <FileText className="w-4 h-4" /> PDF Technique
          </button>
          <button
            onClick={() => setActiveTab('word')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all cursor-pointer ${
              activeTab === 'word'
                ? 'bg-blue-500/10 text-blue-400 border border-blue-500/30'
                : 'bg-savia-bg text-savia-text-muted hover:bg-savia-bg/80 border border-savia-border/30'
            }`}
          >
            <FileType className="w-4 h-4" /> Word (.docx)
          </button>
        </div>

        {/* Tab content */}
        {activeTab === 'excel' && (
          <div>
            <p className="text-sm text-savia-text-muted mb-2">
              Importez un fichier Excel ou CSV contenant des codes d&apos;erreur.
            </p>
            <p className="text-xs text-savia-text-dim mb-4">
              Le système détecte automatiquement les colonnes : <span className="font-semibold text-savia-text">Code, Message, Type, Cause, Solution, Priorité</span>
            </p>

            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              className={`border-2 border-dashed rounded-xl p-6 text-center transition-all cursor-pointer ${
                dragOver
                  ? 'border-savia-accent bg-savia-accent/5'
                  : 'border-savia-border/50 hover:border-savia-accent/40'
              }`}
              onClick={() => fileRef.current?.click()}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={onFileChange}
                className="hidden"
              />
              {importLoading ? (
                <div className="flex items-center justify-center gap-2 text-savia-accent">
                  <Loader2 className="w-5 h-5 animate-spin" /> Import en cours...
                </div>
              ) : (
                <>
                  <Upload className="w-8 h-8 mx-auto text-savia-text-dim mb-2" />
                  <p className="text-savia-text-muted text-sm">Drag and drop file here</p>
                  <p className="text-xs text-savia-text-dim mt-1">Limit 200MB per file • CSV, XLSX</p>
                </>
              )}
            </div>

            {importMsg && (
              <div className={`mt-3 p-3 rounded-lg text-sm ${importMsg.startsWith('✓') ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                {importMsg}
              </div>
            )}
          </div>
        )}

        {activeTab === 'pdf' && (
          <div className="text-center p-8 text-savia-text-dim">
            <FileText className="w-10 h-10 mx-auto mb-2 opacity-40" />
            <p className="text-sm">Import PDF technique — bientôt disponible</p>
            <p className="text-xs mt-1">L&apos;IA extraira automatiquement les codes d&apos;erreur des manuels techniques</p>
          </div>
        )}

        {activeTab === 'word' && (
          <div className="text-center p-8 text-savia-text-dim">
            <FileType className="w-10 h-10 mx-auto mb-2 opacity-40" />
            <p className="text-sm">Import Word (.docx) — bientôt disponible</p>
            <p className="text-xs mt-1">Importation de documentation technique au format Word</p>
          </div>
        )}
      </SectionCard>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
        <input
          type="text"
          placeholder="Rechercher par code, message ou solution..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim"
        />
      </div>

      {/* Knowledge Table */}
      <SectionCard title={<span className="flex items-center gap-2"><BookOpen className="w-4 h-4 text-savia-accent" /> Codes d&apos;erreur ({filtered.length})</span>}>
        <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-savia-text-dim uppercase tracking-wider border-b border-savia-border/50 sticky top-0 bg-savia-surface z-10">
                <th className="py-3 px-3">Code</th>
                <th className="py-3 px-3">Message</th>
                <th className="py-3 px-3">Type</th>
                <th className="py-3 px-3">Cause</th>
                <th className="py-3 px-3">Solution</th>
                <th className="py-3 px-3">Priorité</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-savia-border/30">
              {filtered.map((k, idx) => (
                <tr key={`${k.code}-${idx}`} className="hover:bg-savia-bg/40 transition-colors">
                  <td className="py-3 px-3">
                    <span className="font-mono text-savia-accent font-bold text-xs">{k.code}</span>
                  </td>
                  <td className="py-3 px-3">
                    <span className="text-savia-text font-medium">{k.message}</span>
                  </td>
                  <td className="py-3 px-3">
                    <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 inline-flex items-center gap-1">
                      <Tag className="w-3 h-3" /> {k.type}
                    </span>
                  </td>
                  <td className="py-3 px-3">
                    <div className="flex items-start gap-1 text-xs text-yellow-300">
                      <Wrench className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      <span className="text-savia-text-muted">{k.cause || '—'}</span>
                    </div>
                  </td>
                  <td className="py-3 px-3">
                    <div className="flex items-start gap-1 text-xs text-green-300">
                      <Lightbulb className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      <span className="text-savia-text-muted">{k.solution || '—'}</span>
                    </div>
                  </td>
                  <td className="py-3 px-3 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-bold inline-flex items-center gap-1 ${prioriteColor(k.priorite)}`}>
                      <Zap className="w-3 h-3" /> {k.priorite}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="text-center p-8 text-savia-text-dim text-sm">
              <AlertTriangle className="w-6 h-6 mx-auto mb-2 opacity-40" />
              Aucun résultat trouvé.
            </div>
          )}
        </div>
      </SectionCard>
    </div>
  );
}
