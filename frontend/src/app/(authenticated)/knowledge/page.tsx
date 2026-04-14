'use client';
import { SectionCard } from '@/components/ui/cards';
import { Search, Loader2 } from 'lucide-react';
import { useState, useEffect } from 'react';
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

  useEffect(() => {
    async function loadData() {
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
    }
    loadData();
  }, []);

  const filtered = data.filter(k => !search || k.code.toLowerCase().includes(search.toLowerCase()) || k.message.toLowerCase().includes(search.toLowerCase()) || k.solution.toLowerCase().includes(search.toLowerCase()));

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
        <h1 className="text-2xl font-black gradient-text">📚 Base de Connaissances</h1>
        <p className="text-savia-text-muted text-sm mt-1">{data.length} solutions documentées</p>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
        <input type="text" placeholder="Rechercher par code, message ou solution..." value={search} onChange={e => setSearch(e.target.value)} className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
      </div>

      <div className="space-y-3">
        {filtered.map(k => (
          <div key={k.code} className="glass rounded-xl p-4 hover:border-savia-accent/30 transition-all">
            <div className="flex items-center gap-3 mb-3">
              <span className="font-mono text-savia-accent font-bold">{k.code}</span>
              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${k.priorite === 'HAUTE' ? 'bg-red-500/10 text-red-400' : k.priorite === 'MOYENNE' ? 'bg-yellow-500/10 text-yellow-400' : 'bg-green-500/10 text-green-400'}`}>⚡ {k.priorite}</span>
              <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400">📁 {k.type}</span>
            </div>
            <p className="text-sm font-semibold mb-2">{k.message}</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
              <div className="rounded-lg p-3 bg-yellow-500/5 border-l-2 border-l-yellow-500">
                <div className="text-yellow-400 text-xs font-bold uppercase mb-1">🔧 Cause</div>
                <p className="text-savia-text-muted">{k.cause}</p>
              </div>
              <div className="rounded-lg p-3 bg-green-500/5 border-l-2 border-l-green-500">
                <div className="text-green-400 text-xs font-bold uppercase mb-1">💡 Solution</div>
                <p className="text-savia-text-muted">{k.solution}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
