'use client';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { SectionCard } from '@/components/ui/cards';
import { Modal } from '@/components/ui/modal';
import { Plus, Search, Package, AlertTriangle, Loader2, Save, Trash2, Edit, Sparkles,
  Wrench, Building2, TrendingDown, DollarSign, CheckCircle2, XCircle, History,
  Brain, Boxes, Factory, ThumbsUp, ThumbsDown, Calendar, ShieldCheck, ShoppingCart, Clock } from 'lucide-react';
import { pieces, interventions, ai } from '@/lib/api';

interface Piece {
  id: number;
  reference: string;
  designation: string;
  equipement_type: string;
  stock_actuel: number;
  stock_minimum: number;
  prix_unitaire: number;
  fournisseur: string;
  notes: string;
}

const INPUT_CLS = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all";
const TAB_CLS = "px-4 py-2.5 text-sm font-semibold rounded-t-lg transition-all cursor-pointer border-b-2";
const TAB_ACTIVE = "border-cyan-400 text-cyan-400 bg-cyan-400/5";
const TAB_INACTIVE = "border-transparent text-savia-text-muted hover:text-savia-text hover:border-slate-500";
const TYPES_EQUIPEMENTS = ["Scanner CT", "IRM", "Radiographie", "Mammographie", "Échographie", "Fluoroscopie", "Angiographie", "Autre"];

export default function PiecesPage() {
  const [activeTab, setActiveTab] = useState(0);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('Tous');
  const [data, setData] = useState<Piece[]>([]);
  const [interventionData, setInterventionData] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedPiece, setSelectedPiece] = useState<Piece | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [aiResult, setAiResult] = useState<any>(null);
  // Feedback
  const [selectedFeedbackPiece, setSelectedFeedbackPiece] = useState('');
  const [feedbackHistory, setFeedbackHistory] = useState<any[]>([]);
  const [showFeedbackHistory, setShowFeedbackHistory] = useState(false);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [decaleDate, setDecaleDate] = useState('');
  const [feedbackSuccess, setFeedbackSuccess] = useState('');

  const emptyForm = { reference: '', designation: '', equipement_type: 'Scanner CT', stock_actuel: '1', stock_minimum: '1', prix_unitaire: '0', fournisseur: '', notes: '' };
  const [form, setForm] = useState(emptyForm);

  const loadData = useCallback(async () => {
    try {
      const [piecesRes, intervRes] = await Promise.all([pieces.list(), interventions.list()]);
      const mapped = piecesRes.map((item: any) => ({
        id: item.id || 0,
        reference: item.reference || item.Reference || '',
        designation: item.designation || item.Nom || '',
        equipement_type: item.equipement_type || item.Compatibilite || '',
        stock_actuel: Number(item.stock_actuel || item.Stock_Actuel || 0),
        stock_minimum: Number(item.stock_minimum || item.Seuil_Critique || 1),
        prix_unitaire: Number(item.prix_unitaire || item.Cout_Unitaire || 0),
        fournisseur: item.fournisseur || item.Fournisseur || '',
        notes: item.notes || '',
      }));
      setData(mapped);
      setInterventionData(intervRes);
    } catch (err) {
      console.error("Failed to fetch pieces", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // Load feedback from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('savia_pieces_feedback');
    if (saved) setFeedbackHistory(JSON.parse(saved));
  }, []);

  const submitFeedback = (type: 'correct' | 'faux_positif' | 'decale', vraiDate?: string) => {
    if (!selectedFeedbackPiece) return;
    const entry = { piece: selectedFeedbackPiece, type, vraiDate, timestamp: new Date().toISOString() };
    const updated = [entry, ...feedbackHistory];
    setFeedbackHistory(updated);
    localStorage.setItem('savia_pieces_feedback', JSON.stringify(updated));
    setFeedbackSuccess(
      type === 'correct' ? 'Prédiction confirmée' :
      type === 'faux_positif' ? 'Faux positif signalé' :
      `Date corrigée → ${vraiDate}`
    );
    setShowDatePicker(false); setDecaleDate('');
    setTimeout(() => setFeedbackSuccess(''), 4000);
  };

  const handleSave = async () => {
    if (!form.designation.trim()) return;
    setIsSaving(true);
    try {
      await pieces.create({
        reference: form.reference.trim().toUpperCase(),
        designation: form.designation.trim(),
        equipement_type: form.equipement_type,
        stock_actuel: Number(form.stock_actuel),
        stock_minimum: Number(form.stock_minimum),
        prix_unitaire: Number(form.prix_unitaire),
        fournisseur: form.fournisseur.trim(),
        notes: form.notes.trim(),
      });
      setForm(emptyForm);
      setShowAddModal(false);
      await loadData();
    } catch (err) { console.error("Save failed", err); }
    finally { setIsSaving(false); }
  };

  const handleEdit = async () => {
    if (!selectedPiece) return;
    setIsSaving(true);
    try {
      await pieces.update(selectedPiece.id, {
        reference: form.reference.trim().toUpperCase(),
        designation: form.designation.trim(),
        equipement_type: form.equipement_type,
        stock_actuel: Number(form.stock_actuel),
        stock_minimum: Number(form.stock_minimum),
        prix_unitaire: Number(form.prix_unitaire),
        fournisseur: form.fournisseur.trim(),
        notes: form.notes.trim(),
      });
      setShowEditModal(false);
      setSelectedPiece(null);
      await loadData();
    } catch (err) { console.error("Edit failed", err); }
    finally { setIsSaving(false); }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Supprimer cette pièce ?")) return;
    try { await pieces.delete(id); await loadData(); }
    catch (err) { console.error("Delete failed", err); }
  };

  // Helper: calculate predicted purchase date client-side
  const predictedDate = (p: Piece): string => {
    const today = new Date();
    const add = (n: number) => new Date(today.getTime() + n * 86400000).toLocaleDateString('fr-FR');
    if (p.stock_actuel === 0) return add(0);                        // Rupture → aujourd'hui
    if (p.stock_actuel <= p.stock_minimum) return add(3);           // Stock bas → +3 jours
    const marge = p.stock_actuel - p.stock_minimum;
    if (marge <= 2) return add(14);                                 // Faible marge → +14 jours
    if (marge <= 5) return add(30);                                 // Bonne marge → +30 jours
    return add(60);                                                 // OK → +60 jours
  };

  const handleAiAnalyze = async () => {
    setIsAnalyzing(true);
    setAiResult(null);
    try {
      const res = await ai.analyzePieces(data.map(p => ({
        designation: p.designation,
        reference: p.reference,
        equipement_type: p.equipement_type,
        stock_actuel: p.stock_actuel,
        stock_minimum: p.stock_minimum,
        prix_unitaire: p.prix_unitaire,
        fournisseur: p.fournisseur,
      })), 'TND');
      if (res.ok && res.result) {
        const raw = typeof res.result === 'string' ? res.result : JSON.stringify(res.result);
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          try { setAiResult(JSON.parse(jsonMatch[0])); }
          catch { setAiResult({ analyse_risque: raw, recommandations: [], plan_achat: [], tendances: [] }); }
        } else {
          try { setAiResult(typeof res.result === 'object' ? res.result : { analyse_risque: raw, recommandations: [], plan_achat: [], tendances: [] }); }
          catch { setAiResult({ analyse_risque: raw, recommandations: [], plan_achat: [], tendances: [] }); }
        }
      } else {
        setAiResult({ analyse_risque: "L'IA n'a pas pu générer de réponse.", recommandations: [], plan_achat: [], tendances: [] });
      }
    } catch (err: any) {
      setAiResult({ analyse_risque: `Erreur: ${err?.message || 'Analyse indisponible'}`, recommandations: [], plan_achat: [], tendances: [] });
    } finally { setIsAnalyzing(false); }
  };

  // Filters
  const types = useMemo(() => ['Tous', ...new Set(data.map(p => p.equipement_type).filter(Boolean))], [data]);
  const filtered = data.filter(p => {
    if (filterType !== 'Tous' && p.equipement_type !== filterType) return false;
    if (search) {
      const s = search.toLowerCase();
      return p.reference.toLowerCase().includes(s) || p.designation.toLowerCase().includes(s) || p.fournisseur.toLowerCase().includes(s);
    }
    return true;
  });

  // KPIs
  const lowStock = data.filter(p => p.stock_actuel <= p.stock_minimum);
  const ruptures = data.filter(p => p.stock_actuel === 0).length;
  const totalValeur = data.reduce((a, p) => a + p.stock_actuel * p.prix_unitaire, 0);
  const fournisseurs = new Set(data.map(p => p.fournisseur).filter(Boolean)).size;

  // Traceability data
  const traceData = useMemo(() => {
    const rows: any[] = [];
    interventionData.forEach((inter: any) => {
      const piecesStr = inter.pieces_utilisees || '';
      if (!piecesStr.trim()) return;
      const parts = piecesStr.replace(/;/g, ',').split(',').map((p: string) => p.trim()).filter(Boolean);
      parts.forEach((partName: string) => {
        rows.push({
          date: (inter.date || '').substring(0, 10),
          piece: partName,
          equipement: inter.machine || '',
          technicien: inter.technicien || '',
          statut: inter.statut || '',
        });
      });
    });
    return rows.sort((a, b) => b.date.localeCompare(a.date));
  }, [interventionData]);

  const tabs = [
    { icon: <Package className="w-4 h-4" />, label: 'Stock' },
    { icon: <History className="w-4 h-4" />, label: 'Traçabilité' },
    { icon: <Edit className="w-4 h-4" />, label: 'Modifier / Supprimer' },
    { icon: <Brain className="w-4 h-4" />, label: 'Prédictions & Achats IA' },
  ];

  if (isLoading) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="w-8 h-8 animate-spin text-savia-accent" /></div>;
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black gradient-text flex items-center gap-3">
            <Wrench className="w-7 h-7" /> Pièces de Rechange
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion du stock, traçabilité et prédictions IA</p>
        </div>
        <button onClick={() => { setForm(emptyForm); setShowAddModal(true); }} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-savia-accent-blue hover:opacity-90 transition-all cursor-pointer shadow-lg">
          <Plus className="w-4 h-4" /> Nouvelle Pièce
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-savia-accent"><Package className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-savia-accent">{data.length}</div>
          <div className="text-xs text-savia-text-muted mt-1">Total pièces</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-red-400"><TrendingDown className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-red-400">{lowStock.length}</div>
          <div className="text-xs text-savia-text-muted mt-1">Stock critique</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-green-400"><DollarSign className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-green-400">{(totalValeur / 1000).toFixed(0)}K</div>
          <div className="text-xs text-savia-text-muted mt-1">Valeur stock (TND)</div>
        </div>
        <div className="glass rounded-xl p-4 text-center">
          <div className="flex justify-center mb-2 text-purple-400"><Factory className="w-5 h-5" /></div>
          <div className="text-3xl font-black text-purple-400">{fournisseurs}</div>
          <div className="text-xs text-savia-text-muted mt-1">Fournisseurs</div>
        </div>
      </div>

      {/* Alerte stock critique */}
      {lowStock.length > 0 && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-5 h-5 text-red-400" />
            <span className="font-bold text-red-400">{lowStock.length} pièce(s) en stock critique !</span>
            <span className="text-xs text-savia-text-muted ml-2">({ruptures} en rupture, {lowStock.length - ruptures} stock bas)</span>
          </div>
          <div className="space-y-2 max-h-40 overflow-y-auto">
            {lowStock.map(p => (
              <div key={p.id} className={`flex items-center justify-between p-2 rounded-lg ${p.stock_actuel === 0 ? 'bg-red-500/10 border-l-4 border-red-500' : 'bg-yellow-500/5 border-l-4 border-yellow-500'}`}>
                <div>
                  <span className="font-bold text-sm">{p.designation}</span>
                  <span className="text-xs text-savia-text-muted ml-2">{p.reference}</span>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span className="flex items-center gap-1"><Boxes className="w-3 h-3" /> {p.stock_actuel} / Min: {p.stock_minimum}</span>
                  <span className="flex items-center gap-1"><Factory className="w-3 h-3" /> {p.fournisseur}</span>
                  <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full font-bold ${p.stock_actuel === 0 ? 'bg-red-500 text-white' : 'bg-yellow-500 text-black'}`}>
                    {p.stock_actuel === 0 ? <><XCircle className="w-3 h-3" /> RUPTURE</> : <><AlertTriangle className="w-3 h-3" /> Bas</>}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
          <input type="text" placeholder="🔍 Rechercher par référence, désignation ou fournisseur..." value={search} onChange={e => setSearch(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim" />
        </div>
        <select value={filterType} onChange={e => setFilterType(e.target.value)} className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text">
          {types.map(t => <option key={t} value={t}>{t === 'Tous' ? '🔧 Tous les types' : t}</option>)}
        </select>
      </div>

      <div className="text-xs text-savia-text-muted flex items-center gap-1">
        <Package className="w-3.5 h-3.5" /> {filtered.length} pièce(s) affichée(s)
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-savia-border overflow-x-auto">
        {tabs.map((tab, i) => (
          <button key={i} onClick={() => setActiveTab(i)} className={`${TAB_CLS} ${activeTab === i ? TAB_ACTIVE : TAB_INACTIVE} whitespace-nowrap flex items-center gap-2`}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 0: STOCK */}
      {activeTab === 0 && (
        <SectionCard title="Inventaire Stock">
          <div className="overflow-x-auto">
            <div className="overflow-y-auto" style={{maxHeight: '380px'}}>
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-savia-surface z-10">
                  <tr className="border-b border-savia-border">
                    {['Référence', 'Désignation', 'Type Équip.', 'Stock', 'Min', 'Fournisseur', 'Prix Unit.'].map(h => (
                      <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(p => (
                    <tr key={p.id} className="border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors">
                      <td className="py-2.5 px-3 font-mono text-savia-accent font-bold text-xs">{p.reference}</td>
                      <td className="py-2.5 px-3 font-semibold">{p.designation}</td>
                      <td className="py-2.5 px-3 text-xs text-savia-text-muted">{p.equipement_type}</td>
                      <td className="py-2.5 px-3 text-center">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${p.stock_actuel === 0 ? 'bg-red-500/10 text-red-400' : p.stock_actuel <= p.stock_minimum ? 'bg-yellow-500/10 text-yellow-400' : 'bg-green-500/10 text-green-400'}`}>
                          {p.stock_actuel}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-center text-xs text-savia-text-muted">{p.stock_minimum}</td>
                      <td className="py-2.5 px-3 text-sm">{p.fournisseur}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-sm">{p.prix_unitaire.toLocaleString('fr')} TND</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </SectionCard>
      )}

      {/* TAB 1: TRAÇABILITÉ */}
      {activeTab === 1 && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div className="glass rounded-xl p-4 text-center">
              <div className="flex justify-center mb-2 text-savia-accent"><Wrench className="w-5 h-5" /></div>
              <div className="text-2xl font-black text-savia-accent">{new Set(traceData.map(t => t.piece)).size}</div>
              <div className="text-xs text-savia-text-muted mt-1">Pièces différentes</div>
            </div>
            <div className="glass rounded-xl p-4 text-center">
              <div className="flex justify-center mb-2 text-blue-400"><Building2 className="w-5 h-5" /></div>
              <div className="text-2xl font-black text-blue-400">{new Set(traceData.map(t => t.equipement)).size}</div>
              <div className="text-xs text-savia-text-muted mt-1">Équipements</div>
            </div>
            <div className="glass rounded-xl p-4 text-center">
              <div className="flex justify-center mb-2 text-purple-400"><Boxes className="w-5 h-5" /></div>
              <div className="text-2xl font-black text-purple-400">{traceData.length}</div>
              <div className="text-xs text-savia-text-muted mt-1">Utilisations totales</div>
            </div>
          </div>

          <SectionCard title="Historique d'utilisation des pièces">
            {traceData.length === 0 ? (
              <div className="text-center text-savia-text-muted py-8">Aucune donnée de traçabilité disponible.</div>
            ) : (
              <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-savia-bg">
                    <tr className="border-b border-savia-border">
                      {['Date', 'Pièce', 'Équipement', 'Technicien', 'Statut'].map(h => (
                        <th key={h} className="text-left py-2 px-3 text-savia-text-muted">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {traceData.map((t, i) => (
                      <tr key={i} className="border-b border-savia-border/30">
                        <td className="py-2 px-3 text-xs">{t.date}</td>
                        <td className="py-2 px-3 font-semibold text-savia-accent">{t.piece}</td>
                        <td className="py-2 px-3">{t.equipement}</td>
                        <td className="py-2 px-3">{t.technicien}</td>
                        <td className="py-2 px-3"><span className={`px-2 py-0.5 rounded-full text-xs font-bold ${t.statut?.toLowerCase().includes('tur') ? 'bg-green-500/10 text-green-400' : 'bg-yellow-500/10 text-yellow-400'}`}>{t.statut}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>
        </div>
      )}

      {/* TAB 2: MODIFIER / SUPPRIMER */}
      {activeTab === 2 && (
        <div className="space-y-3">
          {filtered.map(p => {
            const isLow = p.stock_actuel <= p.stock_minimum;
            return (
              <div key={p.id} className={`glass rounded-xl p-4 border ${isLow ? 'border-red-500/20' : 'border-savia-border/30'}`}>
                <div className="flex items-center justify-between flex-wrap gap-3">
                  <div className="flex items-center gap-3">
                    <span className={`text-lg flex items-center ${
                        p.stock_actuel === 0 ? 'text-red-400' : isLow ? 'text-yellow-400' : 'text-green-400'
                      }`}>
                      {p.stock_actuel === 0
                        ? <XCircle className="w-4 h-4" />
                        : isLow
                        ? <AlertTriangle className="w-4 h-4" />
                        : <CheckCircle2 className="w-4 h-4" />}
                    </span>
                    <div>
                      <div className="font-bold">{p.reference} — {p.designation}</div>
                      <div className="text-xs text-savia-text-muted">{p.equipement_type} | Stock: {p.stock_actuel} | Min: {p.stock_minimum} | {p.prix_unitaire.toLocaleString('fr')} TND</div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={() => {
                      setSelectedPiece(p);
                      setForm({
                        reference: p.reference, designation: p.designation, equipement_type: p.equipement_type,
                        stock_actuel: String(p.stock_actuel), stock_minimum: String(p.stock_minimum),
                        prix_unitaire: String(p.prix_unitaire), fournisseur: p.fournisseur, notes: p.notes,
                      });
                      setShowEditModal(true);
                    }} className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 text-sm font-semibold cursor-pointer">
                      <Edit className="w-3.5 h-3.5" /> Modifier
                    </button>
                    <button onClick={() => handleDelete(p.id)} className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 text-sm font-semibold cursor-pointer">
                      <Trash2 className="w-3.5 h-3.5" /> Supprimer
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* TAB 3: PRÉDICTIONS IA */}
      {activeTab === 3 && (
        <div className="space-y-6">

          {/* Tableau de prédictions */}
          <SectionCard title="État du Stock & Recommandations d'Achat">
            <div className="overflow-x-auto">
              <div className="overflow-y-auto" style={{maxHeight: '400px'}}>
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-savia-surface z-10">
                    <tr className="border-b border-savia-border">
                      {['Pièce', 'Type', 'Stock actuel', 'Min', 'Fournisseur', 'Prix unit.', 'Date prévision', 'Urgence'].map(h => (
                        <th key={h} className="text-left py-2 px-3 text-savia-text-muted text-xs whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data
                      .slice()
                      .sort((a, b) => {
                        // Trier par urgence : rupture > bas > OK
                        const urgA = a.stock_actuel === 0 ? 0 : a.stock_actuel <= a.stock_minimum ? 1 : 2;
                        const urgB = b.stock_actuel === 0 ? 0 : b.stock_actuel <= b.stock_minimum ? 1 : 2;
                        return urgA - urgB;
                      })
                      .map(p => {
                        const isRupture = p.stock_actuel === 0;
                        const isBas = !isRupture && p.stock_actuel <= p.stock_minimum;
                        const manquant = Math.max(0, p.stock_minimum - p.stock_actuel + 1);
                        return (
                          <tr key={p.id} className={`border-b border-savia-border/50 hover:bg-savia-surface-hover/50 transition-colors ${
                            isRupture ? 'bg-red-500/5' : isBas ? 'bg-yellow-500/5' : ''
                          }`}>
                            <td className="py-2.5 px-3">
                              <div className="font-semibold text-sm">{p.designation}</div>
                              <div className="text-xs text-savia-text-muted font-mono">{p.reference}</div>
                            </td>
                            <td className="py-2.5 px-3 text-xs text-savia-text-muted">{p.equipement_type}</td>
                            <td className="py-2.5 px-3 text-center">
                              <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                                isRupture ? 'bg-red-500/15 text-red-400' :
                                isBas ? 'bg-yellow-500/15 text-yellow-400' :
                                'bg-green-500/15 text-green-400'
                              }`}>{p.stock_actuel}</span>
                            </td>
                            <td className="py-2.5 px-3 text-center text-xs text-savia-text-muted">{p.stock_minimum}</td>
                            <td className="py-2.5 px-3 text-xs">{p.fournisseur || '—'}</td>
                            <td className="py-2.5 px-3 text-right font-mono text-xs">{p.prix_unitaire.toLocaleString('fr')} TND</td>
                            <td className="py-2.5 px-3">
                              <span className={`flex items-center gap-1 text-xs font-semibold ${
                                isRupture ? 'text-red-400' : isBas ? 'text-yellow-400' : 'text-green-400/80'
                              }`}>
                                <Calendar className="w-3 h-3" />
                                {predictedDate(p)}
                              </span>
                            </td>
                            <td className="py-2.5 px-3">
                              {isRupture ? (
                                <div className="space-y-0.5">
                                  <span className="flex items-center gap-1 text-xs font-bold text-red-400">
                                    <XCircle className="w-3 h-3" /> Commander immédiatement
                                  </span>
                                  <span className="text-[10px] text-red-400/70">À commander: {manquant} unité(s)</span>
                                </div>
                              ) : isBas ? (
                                <div className="space-y-0.5">
                                  <span className="flex items-center gap-1 text-xs font-bold text-yellow-400">
                                    <AlertTriangle className="w-3 h-3" /> Commander bientôt
                                  </span>
                                  <span className="text-[10px] text-yellow-400/70">À commander: {manquant} unité(s)</span>
                                </div>
                              ) : (
                                <span className="flex items-center gap-1 text-xs text-green-400">
                                  <CheckCircle2 className="w-3 h-3" /> Stock suffisant
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            </div>
          </SectionCard>

          {/* Analyse IA */}
          <SectionCard title="Assistant d'Achat Prédictif IA">
            <div className="text-center space-y-4">
              <p className="text-sm text-savia-text-muted">L&apos;IA analyse vos cycles de remplacement et niveaux de stock pour anticiper les ruptures.</p>
              <div className="flex gap-2 flex-wrap justify-center">
                <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-red-500/10 text-red-400">
                  <XCircle className="w-3 h-3" /> {ruptures} en rupture
                </span>
                <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-yellow-500/10 text-yellow-400">
                  <AlertTriangle className="w-3 h-3" /> {lowStock.length - ruptures} stock bas
                </span>
                <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-green-500/10 text-green-400">
                  <CheckCircle2 className="w-3 h-3" /> {data.length - lowStock.length} OK
                </span>
                <span className="flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-purple-500/10 text-purple-400">
                  <DollarSign className="w-3 h-3" /> Valeur: {(totalValeur / 1000).toFixed(0)}K TND
                </span>
              </div>
              <button onClick={handleAiAnalyze} disabled={isAnalyzing} className="flex items-center gap-2 px-6 py-3 rounded-lg font-bold text-white bg-gradient-to-r from-purple-600 to-pink-500 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-purple-500/20 mx-auto disabled:opacity-50">
                {isAnalyzing ? <Loader2 className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
                {isAnalyzing ? 'Analyse en cours...' : 'Lancer l\'Analyse IA'}
              </button>
            </div>
          </SectionCard>

          {aiResult && (
            <SectionCard title="Résultat de l'Analyse IA">
              <div className="space-y-4">
                {aiResult.analyse_risque && (
                  <div className="p-4 rounded-lg bg-red-500/10 border-l-4 border-red-500">
                    <div className="flex items-center gap-2 font-bold text-sm text-red-400 mb-2 uppercase tracking-wider">
                      <AlertTriangle className="w-4 h-4" /> Analyse du Risque
                    </div>
                    <p className="text-sm text-savia-text leading-relaxed">{aiResult.analyse_risque}</p>
                  </div>
                )}
                {aiResult.recommandations?.length > 0 && (
                  <div className="p-4 rounded-lg bg-yellow-500/10 border-l-4 border-yellow-500">
                    <div className="flex items-center gap-2 font-bold text-sm text-yellow-400 mb-3 uppercase tracking-wider">
                      <ShoppingCart className="w-4 h-4" /> Recommandations d&apos;Achat
                    </div>
                    <div className="space-y-3">
                      {aiResult.recommandations.map((r: any, i: number) => (
                        <div key={i} className={`p-3 rounded-lg ${r.urgence === 'critique' ? 'bg-red-500/10 border border-red-500/20' : r.urgence === 'haute' ? 'bg-yellow-500/10 border border-yellow-500/20' : 'bg-green-500/5 border border-green-500/10'}`}>
                          <div className="flex items-start justify-between flex-wrap gap-2 mb-2">
                            <div>
                              <span className="font-semibold text-sm">{r.piece}</span>
                              <span className="text-xs text-savia-text-muted ml-2 font-mono">{r.reference}</span>
                            </div>
                            <span className={`px-2 py-0.5 rounded-full font-bold text-[11px] ${r.urgence === 'critique' ? 'bg-red-500/20 text-red-400' : r.urgence === 'haute' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'}`}>{r.action}</span>
                          </div>
                          {r.raison && (
                            <div className="text-xs text-savia-text-muted bg-savia-bg/50 rounded px-3 py-2 mb-2 italic border-l-2 border-savia-accent/40">
                              {r.raison}
                            </div>
                          )}
                          <div className="flex items-center gap-3 text-xs flex-wrap">
                            <span className="flex items-center gap-1"><Boxes className="w-3 h-3" /> {r.quantite} unité(s)</span>
                            <span className="flex items-center gap-1"><Calendar className="w-3 h-3 text-blue-400" /><span className="text-blue-400 font-semibold">{r.date_achat}</span></span>
                            <span className="flex items-center gap-1 text-green-400"><DollarSign className="w-3 h-3" />{r.cout_estime?.toLocaleString('fr')} TND</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {aiResult.plan_achat?.length > 0 && (
                  <div className="p-4 rounded-lg bg-green-500/10 border-l-4 border-green-500">
                    <div className="flex items-center gap-2 font-bold text-sm text-green-400 mb-3 uppercase tracking-wider">
                      <Calendar className="w-4 h-4" /> Plan d&apos;Achat Planifié
                    </div>
                    <div className="space-y-2">
                      {aiResult.plan_achat.map((s: any, i: number) => (
                        <div key={i} className="flex items-start justify-between flex-wrap gap-2 p-3 rounded-lg bg-green-500/5">
                          <div><div className="font-semibold text-sm text-green-300">{s.semaine}</div><div className="text-xs text-savia-text-muted mt-1">{(s.pieces || []).join(' · ')}</div></div>
                          <span className="flex items-center gap-1 text-sm font-bold text-green-400"><DollarSign className="w-3.5 h-3.5" />{s.budget?.toLocaleString('fr')} TND</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {aiResult.impact_budget && (
                  <div className="p-4 rounded-lg bg-blue-500/10 border-l-4 border-blue-500">
                    <div className="flex items-center gap-2 font-bold text-sm text-blue-400 mb-3 uppercase tracking-wider"><DollarSign className="w-4 h-4" /> Impact Budget</div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <div className="text-center p-3 rounded-lg bg-blue-500/10"><div className="text-lg font-black text-blue-400">{aiResult.impact_budget.cout_total_commande?.toLocaleString('fr')} TND</div><div className="text-xs text-savia-text-muted">Coût total commande</div></div>
                      <div className="text-center p-3 rounded-lg bg-green-500/10"><div className="text-lg font-black text-green-400">{aiResult.impact_budget.gain_potentiel?.toLocaleString('fr')} TND</div><div className="text-xs text-savia-text-muted">Gain potentiel</div></div>
                      <div className="text-center p-3 rounded-lg bg-purple-500/10"><div className="text-sm font-bold text-purple-400 leading-tight">{aiResult.impact_budget.ratio}</div><div className="text-xs text-savia-text-muted mt-1">Ratio ROI</div></div>
                    </div>
                  </div>
                )}
                {aiResult.tendances?.length > 0 && (
                  <div className="p-4 rounded-lg bg-savia-surface-hover/50 space-y-2">
                    <div className="font-bold text-sm text-savia-text-muted uppercase tracking-wider mb-2">Tendances observées</div>
                    {aiResult.tendances.map((t: string, i: number) => (
                      <div key={i} className="flex items-start gap-2 text-sm text-savia-text"><span className="text-savia-accent mt-0.5">›</span>{t}</div>
                    ))}
                  </div>
                )}
              </div>
            </SectionCard>
          )}

          {/* Feedback — Validez les Prédictions */}
          <SectionCard title="Feedback — Validez les Prédictions IA">
            <div className="space-y-4">
              <p className="text-sm text-savia-text-muted">Sélectionnez une pièce et indiquez si la recommandation était correcte pour améliorer les futures analyses.</p>
              <select value={selectedFeedbackPiece} onChange={e => setSelectedFeedbackPiece(e.target.value)}
                className="w-full bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40">
                <option value="">— Sélectionner une pièce —</option>
                {data.map(p => <option key={p.id} value={p.designation}>{p.designation} ({p.reference})</option>)}
              </select>
              {selectedFeedbackPiece && (
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-3">
                    <button onClick={() => submitFeedback('correct')} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-green-400 bg-green-500/10 border border-green-500/20 hover:bg-green-500/20 transition-all cursor-pointer"><ThumbsUp className="w-4 h-4" />Correct</button>
                    <button onClick={() => submitFeedback('faux_positif')} className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-red-400 bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 transition-all cursor-pointer"><ThumbsDown className="w-4 h-4" />Faux positif</button>
                    <button onClick={() => setShowDatePicker(!showDatePicker)} className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-yellow-400 bg-yellow-500/10 border border-yellow-500/20 hover:bg-yellow-500/20 transition-all cursor-pointer ${showDatePicker ? 'ring-2 ring-yellow-500/40' : ''}`}><Calendar className="w-4 h-4" />Date décalée</button>
                    <button onClick={() => setShowFeedbackHistory(!showFeedbackHistory)} className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-semibold text-savia-text-muted bg-savia-surface border border-savia-border hover:bg-savia-surface-hover transition-all cursor-pointer ${showFeedbackHistory ? 'ring-2 ring-savia-accent/40' : ''}`}><History className="w-4 h-4" />Historique</button>
                  </div>
                  {showDatePicker && (
                    <div className="flex items-center gap-3 p-4 rounded-lg bg-yellow-500/5 border border-yellow-500/20 flex-wrap">
                      <Calendar className="w-5 h-5 text-yellow-400" />
                      <span className="text-sm text-savia-text-muted">Vraie date de commande :</span>
                      <input type="date" value={decaleDate} onChange={e => setDecaleDate(e.target.value)} className="bg-savia-bg border border-savia-border rounded-lg px-3 py-2 text-savia-text focus:ring-2 focus:ring-yellow-500/40" />
                      <button onClick={() => { if (decaleDate) submitFeedback('decale', decaleDate); }} disabled={!decaleDate} className="px-4 py-2 rounded-lg font-semibold text-white bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 transition-all cursor-pointer">Valider</button>
                    </div>
                  )}
                  {feedbackSuccess && (<div className="flex items-center gap-2 p-3 rounded-lg bg-green-500/10 text-green-400 text-sm font-semibold"><ShieldCheck className="w-4 h-4" />{feedbackSuccess}</div>)}
                </div>
              )}
              {showFeedbackHistory && feedbackHistory.length > 0 && (
                <div className="mt-2 space-y-2">
                  <h4 className="text-sm font-bold text-savia-text-muted flex items-center gap-2"><History className="w-4 h-4" />Historique ({feedbackHistory.length} entrées)</h4>
                  <div className="max-h-[200px] overflow-y-auto space-y-2">
                    {feedbackHistory.map((fb: any, i: number) => (
                      <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-savia-bg/50 text-sm">
                        <div className={`p-1.5 rounded-full ${fb.type === 'correct' ? 'bg-green-500/10 text-green-400' : fb.type === 'faux_positif' ? 'bg-red-500/10 text-red-400' : 'bg-yellow-500/10 text-yellow-400'}`}>
                          {fb.type === 'correct' ? <ThumbsUp className="w-3.5 h-3.5" /> : fb.type === 'faux_positif' ? <ThumbsDown className="w-3.5 h-3.5" /> : <Calendar className="w-3.5 h-3.5" />}
                        </div>
                        <div className="flex-1"><span className="font-semibold">{fb.piece}</span><span className="text-savia-text-dim ml-2">{fb.type === 'correct' ? '— Correct' : fb.type === 'faux_positif' ? '— Faux positif' : `— Décalé → ${fb.vraiDate}`}</span></div>
                        <span className="text-xs text-savia-text-dim">{new Date(fb.timestamp).toLocaleDateString('fr-FR')}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {showFeedbackHistory && feedbackHistory.length === 0 && (
                <div className="mt-2 text-center p-6 text-savia-text-muted text-sm"><History className="w-8 h-8 mx-auto mb-2 text-savia-text-dim" />Aucun feedback enregistré.</div>
              )}
            </div>
          </SectionCard>
        </div>
      )}

      {/* Add Modal */}
      <Modal isOpen={showAddModal} onClose={() => setShowAddModal(false)} title="➕ Nouvelle Pièce" size="lg">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><label className="block text-sm text-savia-text-muted mb-1">Référence</label><input className={INPUT_CLS} placeholder="TUBE-RX-001" value={form.reference} onChange={e => setForm({...form, reference: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Désignation *</label><input className={INPUT_CLS} placeholder="Tube radiogène" value={form.designation} onChange={e => setForm({...form, designation: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Type équipement</label>
            <select className={INPUT_CLS} value={form.equipement_type} onChange={e => setForm({...form, equipement_type: e.target.value})}>
              {TYPES_EQUIPEMENTS.map(t => <option key={t}>{t}</option>)}
            </select></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Stock actuel</label><input type="number" className={INPUT_CLS} value={form.stock_actuel} onChange={e => setForm({...form, stock_actuel: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Stock minimum</label><input type="number" className={INPUT_CLS} value={form.stock_minimum} onChange={e => setForm({...form, stock_minimum: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Prix unitaire (TND)</label><input type="number" className={INPUT_CLS} value={form.prix_unitaire} onChange={e => setForm({...form, prix_unitaire: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Fournisseur</label><input className={INPUT_CLS} placeholder="Siemens" value={form.fournisseur} onChange={e => setForm({...form, fournisseur: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Notes</label><input className={INPUT_CLS} value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} /></div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-white/5">
          <button onClick={() => setShowAddModal(false)} className="px-4 py-2 rounded-lg text-savia-text-muted hover:text-savia-text cursor-pointer">Annuler</button>
          <button onClick={handleSave} disabled={isSaving} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-savia-text bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-90 disabled:opacity-50 cursor-pointer">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Sauvegarder
          </button>
        </div>
      </Modal>

      {/* Edit Modal */}
      <Modal isOpen={showEditModal} onClose={() => setShowEditModal(false)} title={`✏️ Modifier — ${selectedPiece?.designation || ''}`} size="lg">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><label className="block text-sm text-savia-text-muted mb-1">Référence</label><input className={INPUT_CLS} value={form.reference} onChange={e => setForm({...form, reference: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Désignation</label><input className={INPUT_CLS} value={form.designation} onChange={e => setForm({...form, designation: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Type équipement</label>
            <select className={INPUT_CLS} value={form.equipement_type} onChange={e => setForm({...form, equipement_type: e.target.value})}>
              {TYPES_EQUIPEMENTS.map(t => <option key={t}>{t}</option>)}
            </select></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Stock actuel</label><input type="number" className={INPUT_CLS} value={form.stock_actuel} onChange={e => setForm({...form, stock_actuel: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Stock minimum</label><input type="number" className={INPUT_CLS} value={form.stock_minimum} onChange={e => setForm({...form, stock_minimum: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Prix unitaire (TND)</label><input type="number" className={INPUT_CLS} value={form.prix_unitaire} onChange={e => setForm({...form, prix_unitaire: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Fournisseur</label><input className={INPUT_CLS} value={form.fournisseur} onChange={e => setForm({...form, fournisseur: e.target.value})} /></div>
          <div><label className="block text-sm text-savia-text-muted mb-1">Notes</label><input className={INPUT_CLS} value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} /></div>
        </div>
        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-white/5">
          <button onClick={() => setShowEditModal(false)} className="px-4 py-2 rounded-lg text-savia-text-muted hover:text-savia-text cursor-pointer">Annuler</button>
          <button onClick={handleEdit} disabled={isSaving} className="flex items-center gap-2 px-5 py-2.5 rounded-lg font-bold text-savia-text bg-gradient-to-r from-cyan-500 to-blue-600 hover:opacity-90 disabled:opacity-50 cursor-pointer">
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Enregistrer
          </button>
        </div>
      </Modal>
    </div>
  );
}
