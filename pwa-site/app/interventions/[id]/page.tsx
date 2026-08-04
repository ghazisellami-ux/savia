'use client';
import { useState, useEffect, useMemo } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { isLoggedIn, getUser } from '@/lib/auth';
import Header from '@/components/Header';
import BottomNav from '@/components/BottomNav';
import OfflineInterventionBanner from '@/components/OfflineInterventionBanner';
import TimeScrollPicker from '@/components/TimeScrollPicker';
import {
  Search, Clock, Timer, Car, Wrench, Tag, AlertTriangle, CheckCircle,
  XCircle, FileText, ClipboardList, AlertOctagon, Settings, Camera,
  Trash2, Loader2, Save, CircleDot, Bell, ChevronLeft, ThumbsUp, ThumbsDown, MessageSquare, Zap
} from 'lucide-react';

const ICON_INLINE = { width: '14px', height: '14px', display: 'inline-block', verticalAlign: '-2px', marginRight: '4px' } as const;

const INPUT = {
  width: '100%', background: '#fff', border: '1px solid var(--border)',
  borderRadius: '10px', color: 'var(--text)', padding: '12px 14px',
  fontSize: '1rem', outline: 'none', fontFamily: 'inherit',
} as const;

const LABEL = {
  display: 'block', fontSize: '0.75rem', fontWeight: 700,
  color: 'var(--text-muted)', textTransform: 'uppercase' as const,
  letterSpacing: '0.5px', marginBottom: '6px',
};

const SECTION = {
  background: '#fff', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
  padding: '16px', marginBottom: '16px',
} as const;

const STATUT_STYLES: Record<string, { bg: string; color: string }> = {
  'En cours':            { bg: 'rgba(86,124,141,0.12)',  color: 'var(--teal)'  },
  'En attente de piece': { bg: 'rgba(245,158,11,0.12)',  color: '#B45309'      },
  'Cloturee':            { bg: 'rgba(34,197,94,0.12)',   color: '#15803D'      },
  'Assignée':            { bg: 'rgba(168,85,247,0.12)',  color: '#7C3AED'      },
  'Refusée':             { bg: 'rgba(239,68,68,0.12)',   color: '#DC2626'      },
};

type PiecesQty = Record<number, number>;

// Extrait les mots significatifs d'une chaîne (ignore parenthèses, tirets, etc.)
function coreWords(s: string): string[] {
  return s.toLowerCase().replace(/[()\-_/]/g, ' ').split(/\s+/).filter(w => w.length > 1);
}

// Robust name matching that handles reversed names like "Ghazi Sellami" vs "Sellami Ghazi"
function namesMatch(name1: string, name2: string): boolean {
  if (!name1 || !name2) return false;
  
  const n1Lower = name1.toLowerCase().trim();
  const n2Lower = name2.toLowerCase().trim();
  
  // Exact match
  if (n1Lower === n2Lower) return true;
  
  // Split into words and get meaningful words (length > 1)
  const words1 = n1Lower.split(/\s+/).filter(w => w.length > 1);
  const words2 = n2Lower.split(/\s+/).filter(w => w.length > 1);
  
  // If different number of words, can't match (unless one is subset)
  if (words1.length === 0 || words2.length === 0) return false;
  
  // Check if all words in name1 exist in name2 (handles reversed order)
  const allWords1InName2 = words1.every(w1 => words2.some(w2 => w1 === w2));
  const allWords2InName1 = words2.every(w2 => words1.some(w1 => w2 === w1));
  
  // Both should match if they're the same person in different order
  return allWords1InName2 && allWords2InName1;
}

// Vérifie si le type de pièce correspond à l'équipement de l'intervention
// Compare directement les types d'équipement
function matchesMachine(machineEquipmentType: string, pieceEquipmentType: string): boolean {
  if (!machineEquipmentType || !pieceEquipmentType) return false;
  
  // Direct comparison of equipment types
  const mt = machineEquipmentType.toLowerCase().trim();
  const pt = pieceEquipmentType.toLowerCase().trim();
  
  return mt === pt;
}

export default function InterventionDetailPage() {
  const router = useRouter();
  const params = useParams();
  const id = Number(params?.id);

  const [intervention, setIntervention] = useState<any>(null);
  const [allPieces, setAllPieces]       = useState<any[]>([]);
  const [allEquipements, setAllEquipements] = useState<any[]>([]);
  const [loading, setLoading]           = useState(true);
  const [saving, setSaving]             = useState(false);
  const [error, setError]               = useState('');
  const [success, setSuccess]           = useState('');
  const [photoFile, setPhotoFile]       = useState<File | null>(null);
  const [photoPreview, setPhotoPreview] = useState('');
  const [piecesQty, setPiecesQty]       = useState<PiecesQty>({});
  const [piecesRupture, setPiecesRupture] = useState<any[]>([]); // pièces demandées (rupture)
  const [piecesRuptureMultiTech, setPiecesRuptureMultiTech] = useState<any[]>([]); // pièces rupture multi-tech
  const [searchRupture, setSearchRupture] = useState('');
  const [searchRuptureMultiTech, setSearchRuptureMultiTech] = useState(''); // pour la recherche multi-tech
  const [manualPieces, setManualPieces] = useState<{reference: string; designation: string}[]>([]);
  const [manualPieceForm, setManualPieceForm] = useState({reference: '', designation: ''});
  const [manualPiecesMultiTech, setManualPiecesMultiTech] = useState<{reference: string; designation: string}[]>([]); // pièces manuelles multi-tech
  const [manualPieceFormMultiTech, setManualPieceFormMultiTech] = useState({reference: '', designation: ''}); // formulaire pièces manuelles multi-tech
  const [showRefuseForm, setShowRefuseForm] = useState(false);
  const [refuseRaison, setRefuseRaison] = useState('');
  const [actionLoading, setActionLoading] = useState(false);

  // Per-technician data state
  const [technicianRecords, setTechnicianRecords] = useState<any[]>([]);
  const [currentUserName, setCurrentUserName] = useState('');
  const [currentUserTechId, setCurrentUserTechId] = useState<number | null>(null); // Store the tech ID
  const [usePerTechnicianMode, setUsePerTechnicianMode] = useState(false);
  const [activeTabTech, setActiveTabTech] = useState(''); // Track active technician tab
  const [allTechnicians, setAllTechnicians] = useState<string[]>([]); // All technicians for this intervention

  const [form, setForm] = useState({
    statut: '', probleme: '', cause: '', solution: '',
    description: '', notes: '', type_erreur: '', priorite: '',
    duree_minutes: 0, deplacement: 0, fiche_validation: 'En attente',
    start_time: '08:00', end_time: '09:00',  // HH:MM format
  });
  const [initialFicheValidation, setInitialFicheValidation] = useState('En attente');
  const [initialFormStatut, setInitialFormStatut] = useState('');

  // Per-technician form
  const [techForm, setTechForm] = useState({
    probleme_tech: '',
    cause_tech: '',
    solution_tech: '',
    heure_debut_tech: '08:00',
    heure_fin_tech: '09:00',
    duree_minutes_tech: 60,
    duree_deplacement_tech: 0,
    notes_tech: '',
    statut: 'En cours',
    type_erreur_tech: '',
  });
  const [initialTechnicianStatus, setInitialTechnicianStatus] = useState('En cours');

  useEffect(() => {
    if (!isLoggedIn()) { router.replace('/login'); return; }
    // Get current user name from auth helper
    const user = getUser();
    const userName = user?.nom || '';
    setCurrentUserName(userName);
    console.log('📝 Current user from auth:', { userName, user });
  }, []);

  // Next.js may restore the previous scroll position when navigating from the
  // intervention list. Always start an intervention detail at its header.
  useEffect(() => {
    const scrollToTop = () => {
      window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    };
    const frame = window.requestAnimationFrame(scrollToTop);
    const timer = window.setTimeout(scrollToTop, 80);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
    };
  }, [id]);

  // Separate effect for loading data - waits for currentUserName to be set
  useEffect(() => {
    if (currentUserName) {
      loadAll();
    }
  }, [currentUserName, id]);

  const loadAll = async () => {
    setLoading(true);
    console.log('🔄 loadAll() started with currentUserName:', currentUserName);
    try {
      const [all, pieces, equipements] = await Promise.all([
        api.interventions.list(),
        api.pieces.list(),
        api.equipements.list(),
      ]);

      console.log('✅ Loaded equipements:', equipements);
      console.log('✅ Loaded pieces:', pieces);
      console.log('  └─ Sample piece:', pieces?.[0] ? { reference: pieces[0].reference, designation: pieces[0].designation, equipement_type: pieces[0].equipement_type } : 'none');

      const found = (all as any[]).find(i => Number(i.id) === id);
      if (!found) { setError('Intervention introuvable.'); setLoading(false); return; }

      setIntervention(found);
      setAllPieces(Array.isArray(pieces) ? pieces : []);
      setAllEquipements(Array.isArray(equipements) ? equipements : []);
      
      // DEBUG: Show equipment info
      const foundEquipment = (Array.isArray(equipements) ? equipements : []).find((eq: any) => (eq.Nom || eq.nom) === found.machine);
      console.log('🔍 Intervention machine:', found.machine);
      console.log('🔍 Found equipment:', foundEquipment ? { Nom: foundEquipment.Nom || foundEquipment.nom, Type: foundEquipment.Type || foundEquipment.type } : 'NOT FOUND');
      if (foundEquipment) {
        const equipmentType = (foundEquipment.Type || foundEquipment.type || '').toLowerCase().trim();
        console.log('🔍 Equipment type (normalized):', equipmentType);
        const matchingPieces = (Array.isArray(pieces) ? pieces : []).filter((p: any) => {
          const pieceType = (p.equipement_type || '').toLowerCase().trim();
          return equipmentType === pieceType;
        });
        console.log(`🔍 Matching pieces: ${matchingPieces.length} out of ${pieces?.length || 0}`);
      }
      
      // Parse technicians from comma-separated field
      const techniciens = (found.technicien || '').split(',').map((t: string) => t.trim()).filter((t: string) => t.length > 0);
      console.log('📋 Parsed technicians:', techniciens);
      console.log('🧑 Current user name:', currentUserName);
      
      setAllTechnicians(techniciens);
      
      // Set active tab to current user's technician, fallback to first if not found
      // Multi-tech mode is only active if there are 2 or more technicians
      if (techniciens.length > 1) {
        setUsePerTechnicianMode(true);
        
        // Find current user's tab using robust name matching (handles reversed names)
        const currentUserTab = techniciens.find((tech: string) => {
          const matches = namesMatch(currentUserName, tech);
          console.log(`  Checking match: namesMatch("${currentUserName}", "${tech}") = ${matches}`);
          return matches;
        });
        
        console.log('✅ Matched user tab:', currentUserTab, 'fallback to first:', techniciens[0]);
        setActiveTabTech(currentUserTab || techniciens[0]);
      } else {
        setUsePerTechnicianMode(false);
      }
      
      // Load times in HH:MM format from TIME columns
      let startTime = '08:00';
      let endTime = '09:00';
      
      if (found.start_time) {
        startTime = found.start_time.substring(0, 5);
      }
      
      if (found.end_time) {
        endTime = found.end_time.substring(0, 5);
      }
      
      // Calculate duration from times if both are provided
      let durationMin = 60;
      if (startTime && endTime) {
        const [startH, startM] = startTime.split(':').map(Number);
        const [endH, endM] = endTime.split(':').map(Number);
        durationMin = (endH * 60 + endM) - (startH * 60 + startM);
        if (durationMin <= 0) durationMin += 24 * 60;
        durationMin = Math.max(60, durationMin);
      }
      
      setForm({
        statut:           found.statut || 'En cours',
        probleme:         found.probleme || '',
        cause:            found.cause || '',
        solution:         found.solution || '',
        description:      found.description || '',
        notes:            found.notes || '',
        type_erreur:      found.type_erreur || '',
        priorite:         found.priorite || '',
        duree_minutes:    durationMin,
        deplacement:      found.duree_deplacement ? found.duree_deplacement / 60 : 0,
        fiche_validation: found.fiche_validation || 'En attente',
        start_time:       startTime,
        end_time:         endTime,
      });
      setInitialFicheValidation(found.fiche_validation || 'En attente');
      setInitialFormStatut(found.statut || 'En cours');

      // Load previously used parts from intervention data
      if (found.pieces_utilisees) {
        try {
          console.log('📦 Found pieces_utilisees:', found.pieces_utilisees);
          // Parse pieces_utilisees string format: "ref1 (qty) | ref2 (qty)"
          const pieceLines = String(found.pieces_utilisees || '').split('\n').filter(l => l.trim());
          const previouslyUsedQty: PiecesQty = {};
          
          for (const line of pieceLines) {
            // Try to extract reference and quantity from line
            // Format might be: "Designation | Ref: XXX | ... | Qty: Z"
            const refMatch = line.match(/Ref:\s*([^\s|]+)/i);
            const qtyMatch = line.match(/Qty:\s*(\d+)/i);
            
            if (refMatch && qtyMatch) {
              const ref = refMatch[1];
              const qty = parseInt(qtyMatch[1], 10);
              
              // Find piece by reference
              const piece = allPieces.find(p => 
                (p.reference || '').toLowerCase() === ref.toLowerCase()
              );
              
              if (piece) {
                previouslyUsedQty[piece.id] = qty;
                console.log(`✅ Loaded previously used part: ${piece.reference} qty=${qty}`);
              }
            }
          }
          
          if (Object.keys(previouslyUsedQty).length > 0) {
            setPiecesQty(previouslyUsedQty);
            console.log('📦 Restored pieces_utilisees to state:', previouslyUsedQty);
          }
        } catch (e) {
          console.debug('Error parsing pieces_utilisees:', e);
        }
      }

      // Load technician records if multi-tech mode
      if (techniciens.length > 0) {
        try {
          const techRecords = await api.interventions.getTechnicianData(id);
          setTechnicianRecords(techRecords || []);
          
          // Find current user's tech record and store the ID
          const currentUserRec = techRecords?.find((r: any) => namesMatch(r.technicien_nom || '', currentUserName));
          setInitialTechnicianStatus(currentUserRec?.statut || 'En cours');
          if (currentUserRec?.id) {
            setCurrentUserTechId(currentUserRec.id);
            console.log('✅ Stored current user tech ID:', currentUserRec.id);
          }
          
          // Pre-populate techForm with technician-specific data if available
          // Otherwise use shared intervention data as fallback
          if (currentUserRec) {
            // Use technician-specific data (already saved)
            setTechForm({
              probleme_tech: currentUserRec.probleme_tech || '',
              cause_tech: currentUserRec.cause_tech || '',
              solution_tech: currentUserRec.solution_tech || '',
              heure_debut_tech: currentUserRec.heure_debut_tech || '08:00',
              heure_fin_tech: currentUserRec.heure_fin_tech || '09:00',
              duree_minutes_tech: currentUserRec.duree_minutes_tech || 60,
              duree_deplacement_tech: currentUserRec.duree_deplacement_tech || 0,
              notes_tech: currentUserRec.notes_tech || '',
              statut: currentUserRec.statut || 'En cours',
              type_erreur_tech: currentUserRec.type_erreur_tech || '',
            });
            setInitialTechnicianStatus(currentUserRec.statut || 'En cours');
            console.log('📋 Pre-populated tech form from saved technician data:', {
              probleme_tech: currentUserRec.probleme_tech,
              cause_tech: currentUserRec.cause_tech,
              solution_tech: currentUserRec.solution_tech,
              statut: currentUserRec.statut,
            });
            
            // Load previously used pieces for this technician
            if (currentUserRec.pieces_a_deduire) {
              try {
                const storedPieces = JSON.parse(currentUserRec.pieces_a_deduire);
                console.log('📦 Loaded pieces_a_deduire from tech record:', storedPieces);
                
                if (Array.isArray(storedPieces)) {
                  const previouslyUsedQty: PiecesQty = {};
                  for (const p of storedPieces) {
                    const ref = p.ref || p.reference;
                    const qty = parseInt(p.qty || p.quantite || 0, 10);
                    
                    // Find piece by reference
                    const piece = allPieces.find(pc => 
                      (pc.reference || '').toLowerCase() === (ref || '').toLowerCase()
                    );
                    
                    if (piece && qty > 0) {
                      previouslyUsedQty[piece.id] = qty;
                      console.log(`✅ Loaded piece: ${piece.reference} qty=${qty}`);
                    }
                  }
                  
                  if (Object.keys(previouslyUsedQty).length > 0) {
                    setPiecesQty(previouslyUsedQty);
                    console.log('📦 Restored pieces_a_deduire to state:', previouslyUsedQty);
                  }
                }
              } catch (e) {
                console.debug('Error parsing tech pieces_a_deduire:', e);
              }
            }
          } else {
            // No saved data yet, use shared intervention data as template
            setTechForm(prevForm => ({
              ...prevForm,
              probleme_tech: found.probleme || '',
              cause_tech: found.cause || '',
              solution_tech: found.solution || '',
              notes_tech: found.notes || '',
              type_erreur_tech: found.type_erreur || '',
            }));
            console.log('📋 Pre-populated tech form from shared intervention data (fallback)');
          }
        } catch (e) {
          console.debug('Per-tech records not available:', e);
          setTechnicianRecords([]);
        }
      }
    } catch {
      setError('Erreur lors du chargement.');
    } finally {
      setLoading(false);
    }
  };

  // Filtrer les pièces : l'equipement_type de la pièce doit correspondre
  // au type d'équipement de l'équipement de l'intervention
  const filteredPieces = useMemo(() => {
    if (!intervention?.machine || !allPieces || !allEquipements) {
      console.debug('🔍 filteredPieces: missing data', { machine: intervention?.machine, piecesCount: allPieces?.length, equipementsCount: allEquipements?.length });
      return [];
    }
    
    // Find the equipment for this intervention
    const equipment = allEquipements.find((eq: any) => (eq.Nom || eq.nom) === intervention.machine);
    if (!equipment) {
      console.debug('🔍 filteredPieces: equipment not found for machine:', intervention.machine);
      return [];
    }
    
    // Get the equipment type - API returns "Type" (capitalized)
    const equipmentType = (equipment.Type || equipment.type || '').toLowerCase().trim();
    if (!equipmentType) {
      console.debug('🔍 filteredPieces: no equipment type found', { equipment });
      return [];
    }
    
    console.debug('🔍 filteredPieces: filtering with equipmentType:', equipmentType);
    console.debug('🔍 All pieces:', allPieces.map(p => ({ ref: p.reference, type: p.equipement_type })));
    
    // Filter pieces by matching equipment type
    const filtered = allPieces.filter(p => {
      const pieceType = (p.equipement_type || '').toLowerCase().trim();
      const matches = equipmentType === pieceType;
      if (!matches) console.debug(`  ❌ ${p.reference}: "${pieceType}" !== "${equipmentType}"`);
      return matches;
    });
    
    console.debug(`✅ Filtered ${filtered.length} pieces from ${allPieces.length}`);
    return filtered;
  }, [allPieces, allEquipements, intervention?.machine]);

  const handleQty = (pieceId: number, qty: number) => {
    setPiecesQty(prev => {
      if (qty <= 0) { const next = { ...prev }; delete next[pieceId]; return next; }
      return { ...prev, [pieceId]: qty };
    });
  };

  const selectedCount = Object.keys(piecesQty).length;
  const shouldReturnToInterventions = (statut: string) =>
    statut === 'Cloturee' || statut === 'En attente de piece';
  const returnToInterventions = (delay = 900) => {
    setTimeout(() => {
      router.replace('/interventions');
      window.setTimeout(() => {
        if (window.location.pathname !== '/interventions') {
          window.location.assign('/interventions');
        }
      }, 300);
    }, delay);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setSuccess('');

    const hasClosedFollowUp = Boolean(photoFile) || form.fiche_validation !== initialFicheValidation;
    if (initialFormStatut === 'Cloturee' && !hasClosedFollowUp) {
      setError('Cette intervention est déjà clôturée. Aucune nouvelle mise à jour de statut n’est autorisée depuis le PWA.');
      return;
    }

    // Validation frontend : solution obligatoire pour clôturer
    if (form.statut === 'Cloturee' && !form.solution.trim()) {
      setError('La "Solution appliquée" est obligatoire pour clôturer l\'intervention.');
      document.getElementById('field-solution')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }

    setSaving(true);
    try {
      const pieces_a_deduire = Object.entries(piecesQty).map(([pieceId, qty]) => {
        const p = allPieces.find(x => x.id === Number(pieceId));
        return { 
          id: Number(pieceId), 
          ref: p?.reference || '',
          reference: p?.reference || '',
          qty: qty,
          quantite: qty,
          designation: p?.designation || p?.nom || '',
          prix_unitaire: p?.prix_unitaire || 0,
          fournisseur: p?.fournisseur || '',
        };
      });
      // Reuse parts selected in the stock section when the technician did
      // not repeat the selection in the dedicated rupture section.
      const ruptureSource = piecesRupture.length > 0
        ? piecesRupture
        : Object.entries(piecesQty).map(([pieceId]) => allPieces.find(p => p.id === Number(pieceId))).filter(Boolean);
      const pieces_rupture = ruptureSource.map(p => ({
        id: p.id,
        reference: p.reference || '',
        designation: p.designation || p.nom || '',
      }));
      
      // Calculate duration from times (HH:MM format)
      const calculateDuration = (startTime: string, endTime: string): number => {
        try {
          const [startH, startM] = startTime.split(':').map(Number);
          const [endH, endM] = endTime.split(':').map(Number);
          let duration = (endH * 60 + endM) - (startH * 60 + startM);
          if (duration <= 0) duration += 24 * 60;  // Handle midnight crossing
          return Math.max(60, duration);  // Minimum 1 hour billing
        } catch (e) {
          return 60;
        }
      };
      
      const deploymentMinutes = Math.round(form.deplacement * 60);
      const durationMinutes = calculateDuration(form.start_time, form.end_time);
      
      const updatePayload = { 
        ...(initialFormStatut !== 'Cloturee' ? { statut: form.statut } : {}),
        probleme: form.probleme,
        cause: form.cause,
        solution: form.solution,
        description: form.description,
        notes: form.notes,
        type_erreur: form.type_erreur,
        duree_minutes: durationMinutes,
        start_time: form.start_time,  // Send HH:MM directly
        end_time: form.end_time,      // Send HH:MM directly
        deplacement: deploymentMinutes,  // Send in minutes
        fiche_validation: form.fiche_validation,
        pieces_a_deduire, 
        pieces_rupture, 
        ...(manualPieces.length > 0 ? { pieces_manuelles: manualPieces } : {}) 
      };
      
      console.log('🚀 Sending update payload:', updatePayload);
      console.log('  start_time:', updatePayload.start_time, '(HH:MM format)');
      console.log('  end_time:', updatePayload.end_time, '(HH:MM format)');
      console.log('  duree_minutes:', updatePayload.duree_minutes);
      console.log('  deplacement:', updatePayload.deplacement, 'minutes');
      
      await api.interventions.update(id, updatePayload);
      setInitialFicheValidation(form.fiche_validation);
      setInitialFormStatut(form.statut);
      if (photoFile) {
        try {
          await api.interventions.uploadPhoto(id, photoFile);
        } catch (error) {
          console.error('Photo upload failed:', error);
          throw new Error("L'intervention est mise à jour, mais l'envoi de la fiche signée a échoué.");
        }
      }
      setSuccess('Intervention mise à jour !');
      if (shouldReturnToInterventions(form.statut)) {
        returnToInterventions();
        return;
      }
    } catch (err: any) {
      setError(err?.message || 'Erreur lors de la mise à jour.');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveTechnicianData = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(''); setSuccess('');

    if (initialTechnicianStatus === 'Cloturee') {
      setError('Cette affectation est déjà clôturée. Aucune nouvelle mise à jour de statut n’est autorisée depuis le PWA.');
      return;
    }

    // Validation: solution_tech required when marking as Cloturee
    if (techForm.statut === 'Cloturee' && !techForm.solution_tech.trim()) {
      setError('La "Solution" est obligatoire pour clôturer votre intervention.');
      return;
    }

    setSaving(true);
    try {
      // Upload the signed fiche before closing the technician assignment so a
      // failed upload never leaves a closure without its supporting document.
      if (techForm.statut === 'Cloturee' && photoFile) {
        try {
          await api.interventions.uploadPhoto(id, photoFile);
        } catch (error) {
          console.error('Multi-tech photo upload failed:', error);
          throw new Error("La fiche signée n'a pas pu être envoyée. L'intervention n'a pas été clôturée.");
        }
      }

      // Calculate duration from times
      const calculateDuration = (startTime: string, endTime: string): number => {
        try {
          const [startH, startM] = startTime.split(':').map(Number);
          const [endH, endM] = endTime.split(':').map(Number);
          let duration = (endH * 60 + endM) - (startH * 60 + startM);
          if (duration <= 0) duration += 24 * 60;
          return Math.max(60, duration);
        } catch (e) {
          return 60;
        }
      };

      const durationMinutes = calculateDuration(techForm.heure_debut_tech, techForm.heure_fin_tech);
      const deploymentMinutes = Math.round(techForm.duree_deplacement_tech);

      // Always collect selected pieces (for stock deduction when tech closes)
      const pieces_a_deduire = Object.entries(piecesQty).map(([pieceId, qty]) => {
        const p = allPieces.find(x => x.id === Number(pieceId));
        return { 
          id: Number(pieceId), 
          ref: p?.reference || '',
          reference: p?.reference || '',
          qty: qty,
          quantite: qty,
          designation: p?.designation || p?.nom || '',
          prix_unitaire: p?.prix_unitaire || 0,
          fournisseur: p?.fournisseur || '',
        };
      });

      // Collect pieces rupture if status = "En attente de piece"
      const ruptureSourceMultiTech = piecesRuptureMultiTech.length > 0
        ? piecesRuptureMultiTech
        : Object.entries(piecesQty).map(([pieceId]) => allPieces.find(p => p.id === Number(pieceId))).filter(Boolean);
      const pieces_rupture_tech = techForm.statut === 'En attente de piece' 
        ? ruptureSourceMultiTech.map(p => ({
          id: p.id,
          reference: p.reference || '',
          designation: p.designation || p.nom || '',
        }))
        : [];

      const payload = {
        technicien_nom: currentUserName,
        technicien_id: currentUserTechId, // Send the ID for reliable updating
        probleme_tech: techForm.probleme_tech,
        cause_tech: techForm.cause_tech,
        solution_tech: techForm.solution_tech,
        heure_debut_tech: techForm.heure_debut_tech,
        heure_fin_tech: techForm.heure_fin_tech,
        duree_minutes_tech: durationMinutes,
        duree_deplacement_tech: deploymentMinutes,
        notes_tech: techForm.notes_tech,
        statut: techForm.statut,  // Can be 'Cloturee' or 'En attente de piece' to mark as waiting
        type_erreur_tech: techForm.type_erreur_tech,
        pieces_a_deduire,  // Include pieces (deducted when tech closes)
        pieces_rupture: pieces_rupture_tech,  // Include rupture pieces if waiting
        ...(techForm.statut === 'Cloturee' ? { fiche_validation: form.fiche_validation } : {}),
        ...(manualPiecesMultiTech.length > 0 ? { pieces_manuelles: manualPiecesMultiTech } : {}) // Include manual pieces
      };

      console.log('📤 Sending technician data:', payload);
      
      const response = await api.interventions.updateTechnicianData(id, payload);
      
      if (response.status === 'ALL_COMPLETED') {
        // All technicians done, awaiting admin closure
        setSuccess(`✅ Tous les techniciens ont complété (${response.completed}/${response.total}). En attente de clôture administrative.`);
      } else if (response.status === 'PARTIAL') {
        // Still waiting for others - deduplicate names that are the same (reversed order)
        const pendingList = response.pending_technicians || [];
        const uniquePending: string[] = [];
        
        for (const tech of pendingList) {
          // Check if this tech name already exists in unique list (using robust name matching)
          const isDuplicate = uniquePending.some(existing => namesMatch(existing, tech));
          if (!isDuplicate) {
            uniquePending.push(tech);
          }
        }
        
        const pending = uniquePending.join(', ') || '';
        setSuccess(`✅ Données sauvegardées (${response.completed}/${response.total} techniciens complétés). Restants: ${pending}`);
      } else {
        setSuccess('✅ Vos données ont été enregistrées.');
      }

      if (shouldReturnToInterventions(techForm.statut)) {
        returnToInterventions();
        return;
      }

      setTimeout(async () => {
        // Reload technician data to show updated values
        try {
          console.log('🔄 Reloading technician data...');
          const techRecords = await api.interventions.getTechnicianData(id);
          console.log('📋 Fresh tech records:', techRecords);
          
          setTechnicianRecords(techRecords || []);
          
          // Find current user's record and update form with fresh data
          const currentUserRec = techRecords?.find((r: any) => namesMatch(r.technicien_nom || '', currentUserName));
          if (currentUserRec) {
            console.log('✅ Found current user record:', currentUserRec);
            // Update form with fresh data from database
            setTechForm({
              probleme_tech: currentUserRec.probleme_tech || '',
              cause_tech: currentUserRec.cause_tech || '',
              solution_tech: currentUserRec.solution_tech || '',
              heure_debut_tech: currentUserRec.heure_debut_tech || '08:00',
              heure_fin_tech: currentUserRec.heure_fin_tech || '09:00',
              duree_minutes_tech: currentUserRec.duree_minutes_tech || 60,
              duree_deplacement_tech: currentUserRec.duree_deplacement_tech || 0,
              notes_tech: currentUserRec.notes_tech || '',
              statut: currentUserRec.statut || 'En cours',
              type_erreur_tech: currentUserRec.type_erreur_tech || '',
            });
            setInitialTechnicianStatus(currentUserRec.statut || 'En cours');
            console.log('✅ Updated tech form with fresh data');
          }
        } catch (e) {
          console.error('Error reloading tech data:', e);
        }
      }, 500);
    } catch (err: any) {
      setError(err?.message || 'Erreur lors de la sauvegarde.');
    } finally {
      setSaving(false);
    }
  };

  const set = (k: keyof typeof form, v: any) => setForm(f => ({ ...f, [k]: v }));
  const statutStyle = STATUT_STYLES[form.statut] || { bg: 'rgba(47,65,86,0.08)', color: 'var(--navy)' };
  const isClotured    = form.statut === 'Cloturee';
  const isAttenteP    = form.statut === 'En attente de piece';
  const isAssignee    = form.statut === 'Assignée';
  const isTechnicianStatusLocked = initialTechnicianStatus === 'Cloturee';
  const hasClosedFollowUp = Boolean(photoFile) || form.fiche_validation !== initialFicheValidation;
  const isSingleStatusLocked = initialFormStatut === 'Cloturee';
  const isSingleUpdateLocked = isSingleStatusLocked && !hasClosedFollowUp;

  // Get current technician's data from records (using robust name matching)
  const getCurrentTechData = (): any => {
    if (!activeTabTech || technicianRecords.length === 0) return {};
    return technicianRecords.find((r: any) => namesMatch(r.technicien_nom, activeTabTech)) || {};
  };

  // Check if current user is the active tab technician (using robust name matching)
  const isCurrentUserActiveTech = currentUserName && activeTabTech && namesMatch(currentUserName, activeTabTech);

  // Debug logging
  useEffect(() => {
    console.log('🔍 Multi-tech Debug:', {
      currentUserName,
      activeTabTech,
      usePerTechnicianMode,
      isCurrentUserActiveTech,
      isAssignee,
      showForm: usePerTechnicianMode && isCurrentUserActiveTech && !isAssignee,
    });
  }, [currentUserName, activeTabTech, usePerTechnicianMode, isCurrentUserActiveTech, isAssignee]);

  const handleAccept = async () => {
    setActionLoading(true);
    try {
      await api.interventions.accept(id);
      setForm(f => ({ ...f, statut: 'En cours' }));
      setIntervention((prev: any) => ({ ...prev, statut: 'En cours' }));
      setSuccess('Intervention acceptée ! Vous pouvez maintenant la compléter.');
    } catch (err: any) {
      setError(err?.message || 'Erreur lors de l\'acceptation.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleRefuse = async () => {
    if (!refuseRaison.trim()) {
      setError('Veuillez indiquer la raison du refus.');
      return;
    }
    setActionLoading(true);
    try {
      await api.interventions.refuse(id, refuseRaison.trim());
      setSuccess('Intervention refusée. Le manager sera notifié.');
      returnToInterventions(1200);
    } catch (err: any) {
      setError(err?.message || 'Erreur lors du refus.');
    } finally {
      setActionLoading(false);
    }
  };

  const toggleRupture = (p: any) => {
    setPiecesRupture(prev =>
      prev.find(x => x.id === p.id) ? prev.filter(x => x.id !== p.id) : [...prev, p]
    );
  };

  const toggleRuptureMultiTech = (p: any) => {
    setPiecesRuptureMultiTech(prev =>
      prev.find(x => x.id === p.id) ? prev.filter(x => x.id !== p.id) : [...prev, p]
    );
  };

  // Pour la section "en attente de pièce", filtrer d'abord par type d'équipement puis par recherche
  const searchedPieces = useMemo(() => {
    let base: any[] = [];
    
    if (intervention?.machine && allEquipements && allPieces) {
      // Find the equipment for this intervention
      const equipment = allEquipements.find((eq: any) => (eq.Nom || eq.nom) === intervention.machine);
      if (equipment) {
        // Get the equipment type
        const equipmentType = (equipment.Type || equipment.type || '').toLowerCase().trim();
        if (equipmentType) {
          // Filter pieces by matching equipment type
          base = allPieces.filter(p => {
            const pieceType = (p.equipement_type || '').toLowerCase().trim();
            return equipmentType === pieceType;
          });
        }
      }
    }
    
    if (!searchRupture) return base;
    const q = searchRupture.toLowerCase();
    return base.filter(p =>
      (p.designation || p.nom || '').toLowerCase().includes(q)
      || (p.reference || '').toLowerCase().includes(q)
    );
  }, [allPieces, allEquipements, intervention?.machine, searchRupture]);

  // Same as searchedPieces but for multi-tech mode
  const searchedPiecesMultiTech = useMemo(() => {
    let base: any[] = [];
    
    if (intervention?.machine && allEquipements && allPieces) {
      const equipment = allEquipements.find((eq: any) => (eq.Nom || eq.nom) === intervention.machine);
      if (equipment) {
        const equipmentType = (equipment.Type || equipment.type || '').toLowerCase().trim();
        if (equipmentType) {
          base = allPieces.filter(p => {
            const pieceType = (p.equipement_type || '').toLowerCase().trim();
            return equipmentType === pieceType;
          });
        }
      }
    }
    
    if (!searchRuptureMultiTech) return base;
    const q = searchRuptureMultiTech.toLowerCase();
    return base.filter(p =>
      (p.designation || p.nom || '').toLowerCase().includes(q)
      || (p.reference || '').toLowerCase().includes(q)
    );
  }, [allPieces, allEquipements, intervention?.machine, searchRuptureMultiTech]);

  if (loading) return (
    <div style={{ minHeight: '100dvh', background: 'var(--beige)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center' }}>
        <div className="animate-pulse-dot" style={{ display: 'flex', justifyContent: 'center' }}><Loader2 style={{ width: 48, height: 48, color: 'var(--teal)', animation: 'spin 1s linear infinite' }} /></div>
        <p style={{ color: 'var(--text-muted)', marginTop: '12px' }}>Chargement...</p>
      </div>
    </div>
  );

  if (error && !intervention) return (
    <div style={{ minHeight: '100dvh', background: 'var(--beige)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center', padding: '32px' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '12px' }}><XCircle style={{ width: 48, height: 48, color: 'var(--danger)' }} /></div>
        <p style={{ color: 'var(--danger)' }}>{error}</p>
        <button onClick={() => router.back()} style={{ marginTop: '16px', background: 'var(--teal)', color: '#fff', border: 'none', padding: '10px 20px', borderRadius: '10px', cursor: 'pointer', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '6px' }}><ChevronLeft style={{ width: 16, height: 16 }} /> Retour</button>
      </div>
    </div>
  );

  return (
    <div style={{ minHeight: '100dvh', background: 'var(--beige)' }}>
      <Header />
      <main style={{ padding: 'calc(var(--header-h) + 16px) 16px calc(var(--nav-h) + 24px)' }}>
        <OfflineInterventionBanner interventionId={id} />

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px', flexWrap: 'wrap' }}>
          <button onClick={() => router.back()} style={{ background: 'none', border: 'none', color: 'var(--teal)', fontSize: '1.1rem', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center' }}><ChevronLeft style={{ width: 20, height: 20 }} /></button>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--navy)', margin: 0 }}>
              {intervention?.machine} — {intervention?.client}
            </h1>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              #{id} · {intervention?.date ? new Date(intervention.date).toLocaleDateString('fr-FR') : ''}
            </p>
          </div>
          <span style={{ ...statutStyle, fontSize: '0.7rem', fontWeight: 700, padding: '4px 12px', borderRadius: '20px', textTransform: 'uppercase' }}>
            {form.statut}
          </span>
        </div>

        {success && (
          <div style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid #22C55E', borderRadius: '10px', padding: '14px', textAlign: 'center', color: '#15803D', fontWeight: 700, marginBottom: '16px' }}>
            {success}
          </div>
        )}

        {/* TABS FOR MULTI-TECH INTERVENTIONS */}
        {usePerTechnicianMode && allTechnicians.length > 0 && (
          <div style={{ marginBottom: '16px', display: 'flex', gap: '4px', overflowX: 'auto', paddingBottom: '8px', borderBottom: '2px solid var(--border)' }}>
            {allTechnicians.map((tech: string, idx: number) => {
              // Use robust name matching to find tech data
              const techData = technicianRecords.find((r: any) => namesMatch(r.technicien_nom || '', tech));
              const isActive = namesMatch(activeTabTech, tech);
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setActiveTabTech(tech)}
                  style={{
                    padding: '12px 16px',
                    borderRadius: '10px 10px 0 0',
                    border: isActive ? '2px solid var(--teal)' : '2px solid transparent',
                    borderBottom: isActive ? 'none' : '2px solid var(--border)',
                    background: isActive ? 'rgba(86,124,141,0.1)' : '#fff',
                    color: isActive ? 'var(--teal)' : 'var(--text-muted)',
                    fontWeight: isActive ? 700 : 500,
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                    transition: 'all 0.2s',
                  }}>
                  <span>{tech}</span>
                  {techData?.statut === 'Cloturee' && (
                    <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: '#22C55E', marginLeft: '4px' }} title="Complété"></span>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* MULTI-TECH FORM (per-technician data entry) */}
        {usePerTechnicianMode && isCurrentUserActiveTech && !isAssignee && (
          <form onSubmit={handleSaveTechnicianData}>
            {/* Diagnostic Section */}
            <div style={SECTION}>
              <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Search style={{ width: 16, height: 16 }} /> Mon Diagnostic ({activeTabTech})</h3>
              {[
                { key: 'probleme_tech', label: 'Problème constaté', ph: 'Symptômes observés...' },
                { key: 'cause_tech', label: 'Cause racine', ph: 'Analyse de la cause...' },
                { key: 'solution_tech', label: 'Solution appliquée', ph: 'Actions correctives...' },
              ].map(({ key, label, ph }) => (
                <div key={key} style={{ marginBottom: '12px' }}>
                  <label style={LABEL}>{label}{key === 'solution_tech' && techForm.statut === 'Cloturee' && <span style={{ color: '#ef4444', marginLeft: '4px' }}>*</span>}</label>
                  <textarea
                    style={{ ...INPUT, resize: 'vertical', borderColor: key === 'solution_tech' && techForm.statut === 'Cloturee' && !techForm.solution_tech ? '#ef4444' : undefined }}
                    rows={2}
                    placeholder={ph}
                    value={(techForm as any)[key]}
                    onChange={e => setTechForm(f => ({ ...f, [key as any]: e.target.value }))}
                  />
                </div>
              ))}

              <div style={{ marginBottom: '12px' }}>
                <label style={LABEL}>Type d&apos;erreur</label>
                <select style={INPUT} value={techForm.type_erreur_tech} onChange={e => setTechForm(f => ({ ...f, type_erreur_tech: e.target.value }))}>
                  <option value="">— Aucun —</option>
                  {['Hardware','Software','Réseau','Calibration','Mécanique','Électrique','Autre'].map(t => <option key={t}>{t}</option>)}
                </select>
              </div>
            </div>

            {/* Time & Duration Section */}
            <div style={SECTION}>
              <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Clock style={{ width: 16, height: 16 }} /> Temps</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
                <div>
                  <label style={LABEL}><Clock style={ICON_INLINE} /> Début (HH:MM)</label>
                  <input type="time" style={INPUT} value={techForm.heure_debut_tech} onChange={e => setTechForm(f => ({ ...f, heure_debut_tech: e.target.value }))} />
                </div>
                <div>
                  <label style={LABEL}><Clock style={ICON_INLINE} /> Fin (HH:MM)</label>
                  <input type="time" style={INPUT} value={techForm.heure_fin_tech} onChange={e => setTechForm(f => ({ ...f, heure_fin_tech: e.target.value }))} />
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 14px', marginBottom: '12px', borderRadius: '8px', background: 'rgba(86,124,141,0.12)', border: '1px solid var(--border)' }}>
                <Timer style={{ width: 18, height: 18, color: 'var(--teal)' }} />
                <div>
                  <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Durée de l'intervention</span>
                  <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--teal)', marginTop: '2px' }}>
                    {(() => {
                      const [startH, startM] = techForm.heure_debut_tech.split(':').map(Number);
                      const [endH, endM] = techForm.heure_fin_tech.split(':').map(Number);
                      let durationMin = (endH * 60 + endM) - (startH * 60 + startM);
                      if (durationMin <= 0) durationMin += 24 * 60;
                      durationMin = Math.max(60, durationMin);
                      return (durationMin / 60).toFixed(1);
                    })()}h
                  </div>
                </div>
                <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginLeft: 'auto', background: '#fff', padding: '4px 8px', borderRadius: '4px' }}>Min 1h</span>
              </div>

              <div>
                <label style={LABEL}><Car style={ICON_INLINE} /> Déplacement (en heures)</label>
                <input type="number" style={INPUT} min={0} step={0.5} value={techForm.duree_deplacement_tech === 0 ? '0' : (techForm.duree_deplacement_tech / 60).toFixed(2)} onChange={e => setTechForm(f => ({ ...f, duree_deplacement_tech: Math.round(parseFloat(e.target.value) * 60) || 0 }))} />
              </div>
            </div>

            {/* Notes */}
            <div style={SECTION}>
              <label style={LABEL}><ClipboardList style={ICON_INLINE} /> Notes personnelles</label>
              <textarea style={{ ...INPUT, resize: 'vertical' }} rows={2} placeholder="Observations, remarques..." value={techForm.notes_tech} onChange={e => setTechForm(f => ({ ...f, notes_tech: e.target.value }))} />
            </div>

            {/* Pièces de rechange — Multi-tech mode */}
            {filteredPieces.length > 0 && (
              <div style={SECTION}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>
                    <Wrench style={{ width: 14, height: 14, display: 'inline-block', verticalAlign: '-2px', marginRight: '4px' }} /> Pièces de rechange
                  </h3>
                  {selectedCount > 0 && (
                    <span style={{ background: 'var(--teal)', color: '#fff', fontSize: '0.68rem', fontWeight: 700, padding: '3px 10px', borderRadius: '10px' }}>
                      {selectedCount} sélectionnée{selectedCount > 1 ? 's' : ''}
                    </span>
                  )}
                </div>

                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '10px', background: 'rgba(86,124,141,0.07)', padding: '6px 10px', borderRadius: '8px' }}>
                  <Tag style={{ width: 12, height: 12, display: 'inline-block', verticalAlign: '-1px', marginRight: '4px' }} /> {intervention?.machine} · {filteredPieces.length} pièce{filteredPieces.length > 1 ? 's' : ''} compatible{filteredPieces.length > 1 ? 's' : ''}
                </p>

                {/* 3 pièces visibles, défilement pour le reste */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '244px', overflowY: 'auto', paddingRight: '2px' }}>
                  {filteredPieces.map((p: any) => {
                    const qty = piecesQty[p.id] || 0;
                    const enStock = Number(p.stock_actuel ?? p.stock ?? 0);
                    const rupture = enStock === 0;
                    return (
                      <div key={p.id} style={{
                        background: qty > 0 ? 'rgba(86,124,141,0.06)' : '#fafafa',
                        border: `1px solid ${qty > 0 ? 'var(--teal)' : 'var(--border)'}`,
                        borderRadius: '10px', padding: '10px 12px',
                        display: 'flex', alignItems: 'center', gap: '10px',
                        opacity: rupture && qty === 0 ? 0.55 : 1,
                      }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--navy)', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {p.designation || p.nom}
                          </p>
                          <div style={{ display: 'flex', gap: '6px', marginTop: '3px', flexWrap: 'wrap' }}>
                            <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '2px' }}><Tag style={{ width: 10, height: 10 }} /> {p.reference}</span>
                            <span style={{
                              fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px', borderRadius: '6px',
                              background: rupture ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
                              color: rupture ? 'var(--danger)' : '#15803D',
                            }}>
                              {rupture ? <><AlertTriangle style={{ width: 10, height: 10, display: 'inline-block', verticalAlign: '-1px', marginRight: '2px' }} /> Rupture</> : <><CheckCircle style={{ width: 10, height: 10, display: 'inline-block', verticalAlign: '-1px', marginRight: '2px' }} /> {enStock} en stock</>}
                            </span>
                          </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
                          <button type="button" onClick={() => handleQty(p.id, qty - 1)} disabled={qty === 0}
                            style={{ width: '32px', height: '32px', borderRadius: '8px', border: '1px solid var(--border)', background: qty === 0 ? '#f0f0f0' : '#fff', color: 'var(--navy)', fontWeight: 800, fontSize: '1.1rem', cursor: qty === 0 ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            −
                          </button>
                          <span style={{ minWidth: '26px', textAlign: 'center', fontWeight: 800, color: qty > 0 ? 'var(--teal)' : 'var(--text-dim)', fontSize: '1.05rem' }}>
                            {qty}
                          </span>
                          <button type="button" onClick={() => handleQty(p.id, qty + 1)}
                            style={{ width: '32px', height: '32px', borderRadius: '8px', border: '1px solid var(--border)', background: rupture ? '#f0f0f0' : '#fff', color: 'var(--navy)', fontWeight: 800, fontSize: '1.1rem', cursor: rupture ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            +
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Status */}
            <div style={SECTION}>
              <label style={LABEL}>Mon Statut</label>
              <select
                style={{ ...INPUT, ...(isTechnicianStatusLocked ? { background: '#f1f5f9', color: 'var(--text-muted)', cursor: 'not-allowed' } : {}) }}
                value={techForm.statut}
                disabled={isTechnicianStatusLocked}
                onChange={e => setTechForm(f => ({ ...f, statut: e.target.value }))}
              >
                <option value="En cours">En cours</option>
                <option value="En attente de piece">En attente de pièce</option>
                <option value="Cloturee">Intervention terminée</option>
              </select>
              {isTechnicianStatusLocked && (
                <p style={{ margin: '6px 0 0', color: '#15803D', fontSize: '0.75rem', fontWeight: 600 }}>
                  Cette affectation est clôturée. Le statut ne peut plus être modifié depuis le PWA.
                </p>
              )}
            </div>

            {/* Fiche d'intervention signée — disponible lors de la clôture multi-tech */}
            {techForm.statut === 'Cloturee' && !isTechnicianStatusLocked && (
              <div style={{ ...SECTION, border: '2px dashed var(--teal)' }}>
                <label style={{ ...LABEL, color: 'var(--teal)' }}>
                  <Camera style={{ width: 14, height: 14, display: 'inline-block', verticalAlign: '-2px', marginRight: '4px' }} />
                  Fiche d&apos;intervention signée
                </label>
                <input
                  type="file"
                  id="photo-input-multi"
                  accept="image/*"
                  capture="environment"
                  style={{ display: 'none' }}
                  onChange={e => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    setPhotoFile(file);
                    setPhotoPreview(URL.createObjectURL(file));
                  }}
                />
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    onClick={() => document.getElementById('photo-input-multi')?.click()}
                    style={{ flex: 1, background: 'var(--teal)', color: '#fff', border: 'none', padding: '12px', borderRadius: '10px', fontWeight: 700, cursor: 'pointer', fontSize: '0.9rem' }}
                  >
                    <Camera style={{ width: 16, height: 16, display: 'inline-block', verticalAlign: '-3px', marginRight: '6px' }} />
                    {photoFile ? 'Changer la photo' : 'Prendre / Importer la photo'}
                  </button>
                  {photoFile && (
                    <button
                      type="button"
                      onClick={() => { setPhotoFile(null); setPhotoPreview(''); }}
                      style={{ background: 'var(--danger)', color: '#fff', border: 'none', padding: '12px 16px', borderRadius: '10px', cursor: 'pointer', fontWeight: 700, display: 'flex', alignItems: 'center' }}
                    >
                      <Trash2 style={{ width: 18, height: 18 }} />
                    </button>
                  )}
                </div>
                {photoPreview && (
                  <img src={photoPreview} alt="Aperçu de la fiche signée" style={{ maxWidth: '100%', maxHeight: '220px', borderRadius: '10px', border: '2px solid var(--teal)', objectFit: 'contain', marginTop: '12px', display: 'block' }} />
                )}
                <div style={{ marginTop: '14px' }}>
                  <label style={LABEL}>Statut de la fiche signée</label>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '6px' }}>
                    {[
                      { val: 'En attente', icon: <Clock style={{ width: 14, height: 14 }} />, bg: 'rgba(245,158,11,0.1)', color: '#B45309' },
                      { val: 'Validée', icon: <CheckCircle style={{ width: 14, height: 14 }} />, bg: 'rgba(34,197,94,0.1)', color: '#15803D' },
                    ].map(({ val, icon, bg, color }) => (
                      <button
                        key={val}
                        type="button"
                        onClick={() => set('fiche_validation', val)}
                        style={{
                          padding: '12px 8px',
                          border: `2px solid ${form.fiche_validation === val ? color : 'var(--border)'}`,
                          borderRadius: '10px',
                          background: form.fiche_validation === val ? bg : '#fff',
                          color: form.fiche_validation === val ? color : 'var(--text-muted)',
                          fontWeight: form.fiche_validation === val ? 800 : 500,
                          fontSize: '0.82rem',
                          cursor: 'pointer',
                          transition: 'all 0.2s',
                          textAlign: 'center',
                        }}
                      >
                        {icon} {val}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Pièces requises — visible uniquement quand statut = En attente de piece (multi-tech) */}
            {techForm.statut === 'En attente de piece' && (
              <div style={{ ...SECTION, border: '2px dashed #B45309', background: 'rgba(245,158,11,0.03)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: '#B45309', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>
                    <AlertTriangle style={{ width: 14, height: 14, display: 'inline-block', verticalAlign: '-2px', marginRight: '4px' }} /> Pièces requises (rupture)
                  </h3>
                  {piecesRuptureMultiTech.length > 0 && (
                    <span style={{ background: '#ef4444', color: '#fff', fontSize: '0.68rem', fontWeight: 700, padding: '3px 10px', borderRadius: '10px', animation: 'pulse 2s infinite' }}>
                      {piecesRuptureMultiTech.length} sélectionnée{piecesRuptureMultiTech.length > 1 ? 's' : ''}
                    </span>
                  )}
                </div>
                <p style={{ fontSize: '0.72rem', color: '#B45309', background: 'rgba(245,158,11,0.08)', padding: '6px 10px', borderRadius: '8px', marginBottom: '10px' }}>
                  Sélectionnez les pièces nécessaires — un badge rouge sera créé dans Pièces de rechange
                </p>

                {/* Recherche */}
                <input
                  type="search"
                  placeholder="Rechercher une pièce..."
                  value={searchRuptureMultiTech}
                  onChange={e => setSearchRuptureMultiTech(e.target.value)}
                  style={{ ...INPUT, marginBottom: '10px' }}
                />

                {/* Liste des pièces */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '7px', maxHeight: '280px', overflowY: 'auto' }}>
                  {searchedPiecesMultiTech.length === 0 && (
                    <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem', padding: '12px' }}>Aucune pièce trouvée</p>
                  )}
                  {searchedPiecesMultiTech.map((p: any) => {
                    const enStock = Number(p.stock_actuel ?? p.stock ?? 0);
                    const rupture = enStock === 0;
                    const selected = !!piecesRuptureMultiTech.find(x => x.id === p.id);
                    return (
                      <button key={p.id} type="button" onClick={() => toggleRuptureMultiTech(p)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '10px',
                          padding: '10px 12px', borderRadius: '10px', border: 'none',
                          background: selected ? (rupture ? 'rgba(239,68,68,0.08)' : 'rgba(86,124,141,0.08)') : '#fafafa',
                          outline: selected ? `2px solid ${rupture ? '#ef4444' : 'var(--teal)'}` : '2px solid transparent',
                          cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
                        }}>
                        <span style={{ fontSize: '1.1rem', display: 'flex', alignItems: 'center' }}>{selected ? <CheckCircle style={{ width: 18, height: 18, color: '#15803D' }} /> : (rupture ? <AlertTriangle style={{ width: 18, height: 18, color: '#B45309' }} /> : <CircleDot style={{ width: 18, height: 18, color: 'var(--text-dim)' }} />)}</span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--navy)', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {p.designation || p.nom}
                          </p>
                          <div style={{ display: 'flex', gap: '6px', marginTop: '2px' }}>
                            <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '2px' }}><Tag style={{ width: 10, height: 10 }} /> {p.reference}</span>
                            <span style={{
                              fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px', borderRadius: '6px',
                              background: rupture ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
                              color: rupture ? '#ef4444' : '#15803D',
                            }}>
                              {rupture ? <><AlertTriangle style={{ width: 10, height: 10, display: 'inline-block', verticalAlign: '-1px', marginRight: '2px' }} /> Rupture</> : <><CheckCircle style={{ width: 10, height: 10, display: 'inline-block', verticalAlign: '-1px', marginRight: '2px' }} /> {enStock} en stock</>}
                            </span>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Manual pieces section — visible uniquement quand statut = En attente de piece */}
            {techForm.statut === 'En attente de piece' && (
              <div style={{ marginTop: '14px', borderTop: '1px solid rgba(37,99,235,0.2)', paddingTop: '14px', ...SECTION }}>
                <p style={{ fontSize: '0.78rem', fontWeight: 700, color: '#2563EB', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  🆕 Demander une pièce non référencée
                </p>
                <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
                  <input
                    type="text"
                    placeholder="Référence"
                    value={manualPieceFormMultiTech.reference}
                    onChange={e => setManualPieceFormMultiTech(f => ({ ...f, reference: e.target.value }))}
                    style={{ ...INPUT, flex: 0.4 }}
                  />
                  <input
                    type="text"
                    placeholder="Description"
                    value={manualPieceFormMultiTech.designation}
                    onChange={e => setManualPieceFormMultiTech(f => ({ ...f, designation: e.target.value }))}
                    style={{ ...INPUT, flex: 0.6 }}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => {
                    if (manualPieceFormMultiTech.reference.trim()) {
                      setManualPiecesMultiTech(prev => [...prev, {reference: manualPieceFormMultiTech.reference.trim(), designation: manualPieceFormMultiTech.designation.trim() || manualPieceFormMultiTech.reference.trim()}]);
                      setManualPieceFormMultiTech({reference: '', designation: ''});
                    }
                  }}
                  style={{ width: '100%', padding: '10px', background: '#2563EB', color: '#fff', border: 'none', borderRadius: '8px', fontSize: '0.85rem', fontWeight: 700, cursor: 'pointer', marginBottom: manualPiecesMultiTech.length > 0 ? '8px' : '0' }}
                >
                  + Ajouter à la demande
                </button>
                {manualPiecesMultiTech.length > 0 && (
                  <div style={{ marginTop: '8px' }}>
                    {manualPiecesMultiTech.map((mp, idx) => (
                      <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(37,99,235,0.06)', border: '1px solid rgba(37,99,235,0.2)', borderRadius: '8px', padding: '8px 12px', marginBottom: '4px' }}>
                        <span style={{ flex: 1, fontSize: '0.8rem', color: 'var(--navy)' }}>
                          <strong>{mp.reference}</strong> — {mp.designation}
                        </span>
                        <button type="button" onClick={() => setManualPiecesMultiTech(prev => prev.filter((_, i) => i !== idx))}
                          style={{ background: 'none', border: 'none', color: '#ef4444', fontWeight: 700, fontSize: '1rem', cursor: 'pointer', padding: '2px 6px' }}>✕</button>
                      </div>
                    ))}
                    <p style={{ fontSize: '0.7rem', color: '#2563EB', fontWeight: 600, marginTop: '6px' }}>
                      📨 {manualPiecesMultiTech.length} pièce(s) non référencée(s) — notification dès disponibilité
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Error */}
            {error && <p style={{ color: 'var(--danger)', textAlign: 'center', marginBottom: '12px' }}>{error}</p>}

            {/* Submit */}
            <button
              type="submit"
              disabled={saving || isTechnicianStatusLocked}
              style={{ width: '100%', padding: '16px', background: isTechnicianStatusLocked ? '#cbd5e1' : 'linear-gradient(135deg, var(--teal), var(--navy))', color: isTechnicianStatusLocked ? '#64748b' : '#fff', border: 'none', borderRadius: '12px', fontSize: '1rem', fontWeight: 800, cursor: saving || isTechnicianStatusLocked ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
              {saving ? <><Loader2 style={{ width: 18, height: 18, animation: 'spin 1s linear infinite' }} /> Enregistrement...</> : <><Save style={{ width: 18, height: 18 }} /> Enregistrer Mes Données</>}
            </button>
          </form>
        )}

        {/* READ-ONLY VIEW FOR OTHER TECHNICIANS */}
        {usePerTechnicianMode && !isCurrentUserActiveTech && (
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '12px' }}>Données de {activeTabTech}</h3>
            {(() => {
              const techData = getCurrentTechData();
              if (!techData || !techData.technicien_nom) {
                return <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>Pas encore de données pour ce technicien.</p>;
              }
              
              // Helper to extract HH:MM format (remove seconds)
              const formatTime = (time: string) => time ? time.substring(0, 5) : '—';
              
              // Helper to format duration in hours
              const formatDuration = (minutes: number) => {
                if (!minutes) return '0h';
                const hours = (minutes / 60).toFixed(2);
                return hours.endsWith('.00') ? hours.slice(0, -3) + 'h' : hours + 'h';
              };
              
              // Helper to format deployment in hours (fixing the 0 bug)
              const formatDeployment = (minutes: number) => {
                if (!minutes || minutes === 0) return '0h';
                const hours = (minutes / 60).toFixed(2);
                return hours.endsWith('.00') ? hours.slice(0, -3) + 'h' : hours + 'h';
              };
              
              // Parse pieces_a_deduire JSON if available
              let usedPieces: any[] = [];
              if (techData.pieces_a_deduire) {
                try {
                  const parsed = typeof techData.pieces_a_deduire === 'string' 
                    ? JSON.parse(techData.pieces_a_deduire) 
                    : techData.pieces_a_deduire;
                  usedPieces = Array.isArray(parsed) ? parsed : [];
                } catch (e) {
                  console.debug('Could not parse pieces_a_deduire:', e);
                }
              }
              
              console.log("ss", techData)
              return (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '12px' }}>
                  <div><strong>Problème:</strong> {techData.probleme_tech || '—'}</div>
                  <div><strong>Cause:</strong> {techData.cause_tech || '—'}</div>
                  <div><strong>Solution:</strong> {techData.solution_tech || '—'}</div>
                  <div><strong>Horaires:</strong> {formatTime(techData.heure_debut_tech)} à {formatTime(techData.heure_fin_tech)}</div>
                  <div><strong>Durée:</strong> {formatDuration(techData.duree_minutes_tech)} | <strong>Déplacement:</strong> {formatDeployment(techData.duree_deplacement_tech)}</div>
                  {usedPieces.length > 0 && (
                    <div>
                      <strong>Pièces utilisées:</strong>
                      <div style={{ marginLeft: '12px', marginTop: '6px', display: 'grid', gap: '6px' }}>
                        {usedPieces.map((piece: any, idx: number) => (
                          <div key={idx} style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                            • {piece.designation || piece.ref} | Ref: {piece.ref || piece.reference} | Qty: {piece.qty || piece.quantite}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div><strong>Statut:</strong> <span style={{ ...statutStyle, padding: '4px 12px', borderRadius: '6px', display: 'inline-block' }}>{techData.statut}</span></div>
                </div>
              );
            })()}
          </div>
        )}

        {/* ⓪ Accept/Refuse banner for Assignée interventions */}
        {isAssignee && (
          <div style={{ ...SECTION, border: '2px solid #7C3AED', background: 'rgba(168,85,247,0.04)' }}>
            <h3 style={{ fontSize: '0.9rem', fontWeight: 800, color: '#7C3AED', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Bell style={{ width: 18, height: 18 }} /> Intervention assignée
            </h3>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '16px', lineHeight: 1.5 }}>
              Cette intervention vous a été assignée. Acceptez pour commencer le travail ou refusez avec une justification.
            </p>

            {!showRefuseForm ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                <button type="button" onClick={handleAccept} disabled={actionLoading}
                  style={{ padding: '14px 12px', background: 'linear-gradient(135deg, #22C55E, #15803D)', color: '#fff', border: 'none', borderRadius: '12px', fontWeight: 800, fontSize: '0.95rem', cursor: actionLoading ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', opacity: actionLoading ? 0.7 : 1 }}>
                  {actionLoading ? <Loader2 style={{ width: 18, height: 18, animation: 'spin 1s linear infinite' }} /> : <ThumbsUp style={{ width: 18, height: 18 }} />}
                  Accepter
                </button>
                <button type="button" onClick={() => setShowRefuseForm(true)} disabled={actionLoading}
                  style={{ padding: '14px 12px', background: 'rgba(239,68,68,0.08)', color: '#DC2626', border: '2px solid #DC2626', borderRadius: '12px', fontWeight: 800, fontSize: '0.95rem', cursor: actionLoading ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                  <ThumbsDown style={{ width: 18, height: 18 }} /> Refuser
                </button>
              </div>
            ) : (
              <div>
                <label style={{ ...LABEL, display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <MessageSquare style={{ width: 14, height: 14 }} /> Raison du refus *
                </label>
                <textarea
                  style={{ ...INPUT, resize: 'vertical', borderColor: '#DC2626', marginBottom: '12px' }}
                  rows={3}
                  placeholder="Expliquez la raison du refus (indisponibilité, compétence, etc.)"
                  value={refuseRaison}
                  onChange={e => setRefuseRaison(e.target.value)}
                  autoFocus
                />
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                  <button type="button" onClick={() => { setShowRefuseForm(false); setRefuseRaison(''); setError(''); }}
                    style={{ padding: '12px', background: '#fff', color: 'var(--text-muted)', border: '1px solid var(--border)', borderRadius: '10px', fontWeight: 600, fontSize: '0.9rem', cursor: 'pointer' }}>
                    Annuler
                  </button>
                  <button type="button" onClick={handleRefuse} disabled={actionLoading || !refuseRaison.trim()}
                    style={{ padding: '12px', background: '#DC2626', color: '#fff', border: 'none', borderRadius: '10px', fontWeight: 800, fontSize: '0.9rem', cursor: (actionLoading || !refuseRaison.trim()) ? 'not-allowed' : 'pointer', opacity: (actionLoading || !refuseRaison.trim()) ? 0.6 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
                    {actionLoading ? <Loader2 style={{ width: 16, height: 16, animation: 'spin 1s linear infinite' }} /> : <ThumbsDown style={{ width: 16, height: 16 }} />}
                    Confirmer le refus
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {error && !isAssignee && <p style={{ color: 'var(--danger)', textAlign: 'center', marginBottom: '12px' }}>{error}</p>}
        {error && isAssignee && <p style={{ color: 'var(--danger)', textAlign: 'center', marginBottom: '12px', marginTop: '-8px' }}>{error}</p>}

        {/* Only show full form when NOT in Assignée status AND NOT in multi-tech mode */}
        {!isAssignee && !usePerTechnicianMode && <form onSubmit={handleSave}>

          {/* ① Diagnostic */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Search style={{ width: 16, height: 16 }} /> Diagnostic</h3>
            {[
              { key: 'probleme', label: 'Problème constaté', ph: 'Symptômes observés...' },
              { key: 'cause',    label: 'Cause racine',      ph: 'Analyse de la cause...' },
              { key: 'solution', label: 'Solution appliquée', ph: 'Actions correctives...' },
            ].map(({ key, label, ph }) => (
              <div key={key} id={key === 'solution' ? 'field-solution' : undefined} style={{ marginBottom: '12px' }}>
                <label style={LABEL}>
                  {label}
                  {key === 'solution' && isClotured && (
                    <span style={{ color: '#ef4444', marginLeft: '4px' }}>*</span>
                  )}
                </label>
                <textarea
                  style={{
                    ...INPUT, resize: 'vertical',
                    borderColor: key === 'solution' && isClotured && !(form as any)[key] ? '#ef4444' : undefined,
                  }}
                  rows={2} placeholder={ph}
                  value={(form as any)[key]}
                  onChange={e => set(key as any, e.target.value)}
                />
              </div>
            ))}

            <div style={{ marginBottom: '12px' }}>
              <label style={LABEL}>Type d&apos;erreur</label>
              <select style={INPUT} value={form.type_erreur} onChange={e => set('type_erreur', e.target.value)}>
                <option value="">— Aucun —</option>
                {['Hardware','Software','Réseau','Calibration','Mécanique','Électrique','Autre'].map(t => <option key={t}>{t}</option>)}
              </select>
            </div>

            {/* Time pickers with scrollable UI */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '12px' }}>
              <TimeScrollPicker 
                label="Heure de début"
                value={form.start_time}
                onChange={(time) => {
                  set('start_time', time);
                  // Auto-calculate duration
                  const [startH, startM] = time.split(':').map(Number);
                  const [endH, endM] = form.end_time.split(':').map(Number);
                  let durationMin = (endH * 60 + endM) - (startH * 60 + startM);
                  if (durationMin <= 0) durationMin += 24 * 60;
                  durationMin = Math.max(60, durationMin);
                  setForm(f => ({ ...f, duree_minutes: durationMin }));
                }}
              />
              <TimeScrollPicker 
                label="Heure de fin"
                value={form.end_time}
                onChange={(time) => {
                  set('end_time', time);
                  // Auto-calculate duration
                  const [startH, startM] = form.start_time.split(':').map(Number);
                  const [endH, endM] = time.split(':').map(Number);
                  let durationMin = (endH * 60 + endM) - (startH * 60 + startM);
                  if (durationMin <= 0) durationMin += 24 * 60;
                  durationMin = Math.max(60, durationMin);
                  setForm(f => ({ ...f, duree_minutes: durationMin }));
                }}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 14px', marginTop: '12px', borderRadius: '8px', background: 'rgba(86,124,141,0.12)', border: '1px solid var(--border)' }}>
              <Timer style={{ width: 18, height: 18, color: 'var(--teal)' }} />
              <div>
                <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Durée de l'intervention</span>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--teal)', marginTop: '2px' }}>
                  {(form.duree_minutes / 60).toFixed(1)}h
                </div>
              </div>
              <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginLeft: 'auto', background: '#fff', padding: '4px 8px', borderRadius: '4px' }}>Min 1h</span>
            </div>

            <div style={{ marginTop: '12px' }}>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px' }}>
                <Car style={{ width: 14, height: 14, display: 'inline-block', verticalAlign: '-2px', marginRight: '4px' }} /> Déplacement (heures)
              </label>
              <input
                type="number" style={{ width: '100%', background: '#fff', border: '1px solid var(--border)', borderRadius: '10px', color: 'var(--text)', padding: '12px 14px', fontSize: '1rem', outline: 'none', fontFamily: 'inherit' }} min={0} step={0.5}
                value={form.deplacement}
                onChange={e => set('deplacement', parseFloat(e.target.value) || 0)}
              />
            </div>
          </div>

          {/* ② Pièces de rechange — masqué si aucune correspondance */}
          {filteredPieces.length > 0 && (
            <div style={SECTION}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>
                  <Wrench style={{ width: 14, height: 14, display: 'inline-block', verticalAlign: '-2px', marginRight: '4px' }} /> Pièces de rechange
                </h3>
                {selectedCount > 0 && (
                  <span style={{ background: 'var(--teal)', color: '#fff', fontSize: '0.68rem', fontWeight: 700, padding: '3px 10px', borderRadius: '10px' }}>
                    {selectedCount} sélectionnée{selectedCount > 1 ? 's' : ''}
                  </span>
                )}
              </div>

              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '10px', background: 'rgba(86,124,141,0.07)', padding: '6px 10px', borderRadius: '8px' }}>
                <Tag style={{ width: 12, height: 12, display: 'inline-block', verticalAlign: '-1px', marginRight: '4px' }} /> {intervention?.machine} · {filteredPieces.length} pièce{filteredPieces.length > 1 ? 's' : ''} compatible{filteredPieces.length > 1 ? 's' : ''}
              </p>

              {/* 3 pièces visibles, défilement pour le reste */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '244px', overflowY: 'auto', paddingRight: '2px' }}>
                {filteredPieces.map((p: any) => {
                  const qty = piecesQty[p.id] || 0;
                  const enStock = Number(p.stock_actuel ?? p.stock ?? 0);
                  const rupture = enStock === 0;
                  return (
                    <div key={p.id} style={{
                      background: qty > 0 ? 'rgba(86,124,141,0.06)' : '#fafafa',
                      border: `1px solid ${qty > 0 ? 'var(--teal)' : 'var(--border)'}`,
                      borderRadius: '10px', padding: '10px 12px',
                      display: 'flex', alignItems: 'center', gap: '10px',
                      opacity: rupture && qty === 0 ? 0.55 : 1,
                    }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--navy)', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {p.designation || p.nom}
                        </p>
                        <div style={{ display: 'flex', gap: '6px', marginTop: '3px', flexWrap: 'wrap' }}>
                          <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '2px' }}><Tag style={{ width: 10, height: 10 }} /> {p.reference}</span>
                          <span style={{
                            fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px', borderRadius: '6px',
                            background: rupture ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
                            color: rupture ? 'var(--danger)' : '#15803D',
                          }}>
                            {rupture ? <><AlertTriangle style={{ width: 10, height: 10, display: 'inline-block', verticalAlign: '-1px', marginRight: '2px' }} /> Rupture</> : <><CheckCircle style={{ width: 10, height: 10, display: 'inline-block', verticalAlign: '-1px', marginRight: '2px' }} /> {enStock} en stock</>}
                          </span>
                        </div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
                        <button type="button" onClick={() => handleQty(p.id, qty - 1)} disabled={qty === 0}
                          style={{ width: '32px', height: '32px', borderRadius: '8px', border: '1px solid var(--border)', background: qty === 0 ? '#f0f0f0' : '#fff', color: 'var(--navy)', fontWeight: 800, fontSize: '1.1rem', cursor: qty === 0 ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          −
                        </button>
                        <span style={{ minWidth: '26px', textAlign: 'center', fontWeight: 800, color: qty > 0 ? 'var(--teal)' : 'var(--text-dim)', fontSize: '1.05rem' }}>
                          {qty}
                        </span>
                        <button type="button" onClick={() => handleQty(p.id, qty + 1)}
                          style={{ width: '32px', height: '32px', borderRadius: '8px', border: '1px solid var(--border)', background: rupture ? '#f0f0f0' : '#fff', color: 'var(--navy)', fontWeight: 800, fontSize: '1.1rem', cursor: rupture ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          +
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ③ Description & Notes */}
          <div style={SECTION}>
            <div style={{ marginBottom: '12px' }}>
              <label style={LABEL}><FileText style={ICON_INLINE} /> Description</label>
              <textarea style={{ ...INPUT, resize: 'vertical' }} rows={2}
                value={form.description} onChange={e => set('description', e.target.value)} />
            </div>
            <div>
              <label style={LABEL}><ClipboardList style={ICON_INLINE} /> Notes</label>
              <textarea style={{ ...INPUT, resize: 'vertical' }} rows={2}
                value={form.notes} onChange={e => set('notes', e.target.value)} />
            </div>
          </div>

          {/* ④ Priorité héritée de la demande — lecture seule */}
          <div style={SECTION}>
            <label style={LABEL}><AlertOctagon style={ICON_INLINE} /> Priorité de la demande</label>
            <div style={{ ...INPUT, background: '#f8fafc', color: form.priorite ? 'var(--navy)' : 'var(--text-muted)', fontWeight: 700 }}>
              {form.priorite || 'Non définie'}
            </div>
          </div>

          {/* ⑤ Statut — EN BAS */}
          <div style={SECTION}>
            <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Settings style={{ width: 16, height: 16 }} /> Statut de l&apos;intervention</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
              {['En cours', 'En attente de piece', 'Cloturee'].map(s => {
                const st = STATUT_STYLES[s] || { bg: 'rgba(47,65,86,0.08)', color: 'var(--navy)' };
                return (
                  <button key={s} type="button" disabled={isSingleStatusLocked} onClick={() => set('statut', s)}
                    style={{
                      padding: '10px 4px', border: `2px solid ${form.statut === s ? st.color : 'var(--border)'}`,
                      borderRadius: '10px', background: form.statut === s ? st.bg : '#fff',
                      color: form.statut === s ? st.color : 'var(--text-muted)',
                      fontWeight: form.statut === s ? 800 : 500, fontSize: '0.72rem',
                      cursor: isSingleStatusLocked ? 'not-allowed' : 'pointer', opacity: isSingleStatusLocked && form.statut !== s ? 0.55 : 1,
                      transition: 'all 0.2s', textAlign: 'center',
                    }}>
                    {s}
                  </button>
                );
              })}
            </div>
            {isSingleStatusLocked && (
              <p style={{ margin: '8px 0 0', color: '#15803D', fontSize: '0.75rem', fontWeight: 600 }}>
                L&apos;intervention est clôturée. Le statut ne peut plus être modifié depuis le PWA.
              </p>
            )}
          </div>

          {/* □ Pièces requises — visible uniquement quand statut = En attente de piece */}
          {isAttenteP && (
            <div style={{ ...SECTION, border: '2px dashed #B45309', background: 'rgba(245,158,11,0.03)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: '#B45309', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>
                  <AlertTriangle style={{ width: 14, height: 14, display: 'inline-block', verticalAlign: '-2px', marginRight: '4px' }} /> Pièces requises (rupture)
                </h3>
                {piecesRupture.length > 0 && (
                  <span style={{ background: '#ef4444', color: '#fff', fontSize: '0.68rem', fontWeight: 700, padding: '3px 10px', borderRadius: '10px', animation: 'pulse 2s infinite' }}>
                    {piecesRupture.length} sélectionnée{piecesRupture.length > 1 ? 's' : ''}
                  </span>
                )}
              </div>
              <p style={{ fontSize: '0.72rem', color: '#B45309', background: 'rgba(245,158,11,0.08)', padding: '6px 10px', borderRadius: '8px', marginBottom: '10px' }}>
                Sélectionnez les pièces nécessaires — un badge rouge sera créé dans Pièces de rechange
              </p>

              {/* Recherche */}
              <input
                type="search"
                placeholder="Rechercher une pièce..."
                value={searchRupture}
                onChange={e => setSearchRupture(e.target.value)}
                style={{ ...INPUT, marginBottom: '10px' }}
              />

              {/* Liste des pièces */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '7px', maxHeight: '280px', overflowY: 'auto' }}>
                {searchedPieces.length === 0 && (
                  <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem', padding: '12px' }}>Aucune pièce trouvée</p>
                )}
                {searchedPieces.map((p: any) => {
                  const enStock = Number(p.stock_actuel ?? p.stock ?? 0);
                  const rupture = enStock === 0;
                  const selected = !!piecesRupture.find(x => x.id === p.id);
                  return (
                    <button key={p.id} type="button" onClick={() => toggleRupture(p)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: '10px',
                        padding: '10px 12px', borderRadius: '10px', border: 'none',
                        background: selected ? (rupture ? 'rgba(239,68,68,0.08)' : 'rgba(86,124,141,0.08)') : '#fafafa',
                        outline: selected ? `2px solid ${rupture ? '#ef4444' : 'var(--teal)'}` : '2px solid transparent',
                        cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
                      }}>
                      <span style={{ fontSize: '1.1rem', display: 'flex', alignItems: 'center' }}>{selected ? <CheckCircle style={{ width: 18, height: 18, color: '#15803D' }} /> : (rupture ? <AlertTriangle style={{ width: 18, height: 18, color: '#B45309' }} /> : <CircleDot style={{ width: 18, height: 18, color: 'var(--text-dim)' }} />)}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--navy)', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {p.designation || p.nom}
                        </p>
                        <div style={{ display: 'flex', gap: '6px', marginTop: '2px' }}>
                          <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '2px' }}><Tag style={{ width: 10, height: 10 }} /> {p.reference}</span>
                          <span style={{
                            fontSize: '0.65rem', fontWeight: 700, padding: '1px 6px', borderRadius: '6px',
                            background: rupture ? 'rgba(239,68,68,0.1)' : 'rgba(34,197,94,0.1)',
                            color: rupture ? '#ef4444' : '#15803D',
                          }}>
                            {rupture ? <><XCircle style={{ width: 10, height: 10, display: 'inline-block', verticalAlign: '-1px', marginRight: '2px' }} /> Rupture</> : <><CheckCircle style={{ width: 10, height: 10, display: 'inline-block', verticalAlign: '-1px', marginRight: '2px' }} /> {enStock} en stock</>}
                          </span>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Résumé sélection */}
              {piecesRupture.length > 0 && (
                <div style={{ marginTop: '10px', padding: '8px 12px', background: 'rgba(239,68,68,0.06)', borderRadius: '8px', border: '1px solid rgba(239,68,68,0.2)' }}>
                  <p style={{ fontSize: '0.72rem', fontWeight: 700, color: '#ef4444', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}><Bell style={{ width: 12, height: 12 }} /> Pièces qui seront notifiées :</p>
                  {piecesRupture.map(p => (
                    <p key={p.id} style={{ fontSize: '0.72rem', color: 'var(--text-muted)', margin: '1px 0' }}>
                      • {p.designation || p.nom} ({p.reference})
                    </p>
                  ))}
                </div>
              )}

              {/* Pièce non référencée — saisie libre */}
              <div style={{ marginTop: '14px', borderTop: '1px solid rgba(245,158,11,0.2)', paddingTop: '14px' }}>
                <p style={{ fontSize: '0.78rem', fontWeight: 700, color: '#2563EB', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  🆕 Demander une pièce non référencée
                </p>
                <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
                  <input
                    type="text"
                    placeholder="Référence"
                    style={{ ...INPUT, flex: 1, fontSize: '0.85rem', padding: '10px 12px' }}
                    value={manualPieceForm.reference}
                    onChange={e => setManualPieceForm(prev => ({...prev, reference: e.target.value}))}
                  />
                  <input
                    type="text"
                    placeholder="Désignation"
                    style={{ ...INPUT, flex: 1, fontSize: '0.85rem', padding: '10px 12px' }}
                    value={manualPieceForm.designation}
                    onChange={e => setManualPieceForm(prev => ({...prev, designation: e.target.value}))}
                  />
                </div>
                <button
                  type="button"
                  disabled={!manualPieceForm.reference.trim()}
                  onClick={() => {
                    if (manualPieceForm.reference.trim()) {
                      setManualPieces(prev => [...prev, {reference: manualPieceForm.reference.trim(), designation: manualPieceForm.designation.trim() || manualPieceForm.reference.trim()}]);
                      setManualPieceForm({reference: '', designation: ''});
                    }
                  }}
                  style={{ width: '100%', padding: '10px', background: !manualPieceForm.reference.trim() ? '#e5e7eb' : '#2563EB', color: !manualPieceForm.reference.trim() ? '#9ca3af' : '#fff', border: 'none', borderRadius: '10px', fontWeight: 700, fontSize: '0.85rem', cursor: !manualPieceForm.reference.trim() ? 'not-allowed' : 'pointer' }}
                >
                  + Ajouter à la demande
                </button>
                {manualPieces.length > 0 && (
                  <div style={{ marginTop: '8px' }}>
                    {manualPieces.map((mp, idx) => (
                      <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(37,99,235,0.06)', border: '1px solid rgba(37,99,235,0.2)', borderRadius: '8px', padding: '8px 12px', marginBottom: '4px' }}>
                        <span style={{ flex: 1, fontSize: '0.8rem', color: 'var(--navy)' }}>
                          <strong>{mp.reference}</strong> — {mp.designation}
                        </span>
                        <button type="button" onClick={() => setManualPieces(prev => prev.filter((_, i) => i !== idx))}
                          style={{ background: 'none', border: 'none', color: '#ef4444', fontWeight: 700, fontSize: '1rem', cursor: 'pointer', padding: '2px 6px' }}>✕</button>
                      </div>
                    ))}
                    <p style={{ fontSize: '0.7rem', color: '#2563EB', fontWeight: 600, marginTop: '6px' }}>
                      📨 {manualPieces.length} pièce(s) non référencée(s) — notification dès disponibilité
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {isClotured && (
            <div style={{ ...SECTION, border: '2px dashed var(--teal)' }}>
              <h3 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--teal)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.5px', display: 'flex', alignItems: 'center', gap: '6px' }}><Camera style={{ width: 16, height: 16 }} /> Fiche d&apos;intervention signée</h3>

              {/* Prise de photo */}
              <input type="file" id="photo-input" accept="image/*" capture="environment" style={{ display: 'none' }} onChange={e => {
                const f = e.target.files?.[0];
                if (!f) return;
                setPhotoFile(f);
                setPhotoPreview(URL.createObjectURL(f));
              }} />
              <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                <button type="button" onClick={() => document.getElementById('photo-input')?.click()}
                  style={{ flex: 1, background: 'var(--teal)', color: '#fff', border: 'none', padding: '14px', borderRadius: '10px', fontWeight: 700, cursor: 'pointer', fontSize: '0.95rem' }}>
                  <Camera style={{ width: 16, height: 16, display: 'inline-block', verticalAlign: '-3px', marginRight: '6px' }} /> {photoFile ? 'Changer la photo' : 'Prendre / Importer photo'}
                </button>
                {photoFile && (
                  <button type="button" onClick={() => { setPhotoFile(null); setPhotoPreview(''); }}
                    style={{ background: 'var(--danger)', color: '#fff', border: 'none', padding: '14px 16px', borderRadius: '10px', cursor: 'pointer', fontWeight: 700, display: 'flex', alignItems: 'center' }}><Trash2 style={{ width: 18, height: 18 }} /></button>
                )}
              </div>
              {photoPreview && (
                <img src={photoPreview} alt="Aperçu fiche" style={{ maxWidth: '100%', maxHeight: '220px', borderRadius: '10px', border: '2px solid var(--teal)', objectFit: 'contain', marginBottom: '12px', display: 'block' }} />
              )}
              {!photoFile && (
                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textAlign: 'center', marginBottom: '12px' }}>
                  Joignez une photo de la fiche d&apos;intervention signée par le client
                </p>
              )}

              {/* Statut de la fiche */}
              <div style={{ marginTop: '4px' }}>
                <label style={LABEL}>Statut de la fiche signée</label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '6px' }}>
                  {[
                    { val: 'En attente', icon: <Clock style={{ width: 14, height: 14 }} />, bg: 'rgba(245,158,11,0.1)', color: '#B45309' },
                    { val: 'Validée',    icon: <CheckCircle style={{ width: 14, height: 14 }} />, bg: 'rgba(34,197,94,0.1)',  color: '#15803D' },
                  ].map(({ val, icon, bg, color }) => (
                    <button key={val} type="button"
                      onClick={() => set('fiche_validation', val)}
                      style={{
                        padding: '12px 8px',
                        border: `2px solid ${form.fiche_validation === val ? color : 'var(--border)'}`,
                        borderRadius: '10px',
                        background: form.fiche_validation === val ? bg : '#fff',
                        color: form.fiche_validation === val ? color : 'var(--text-muted)',
                        fontWeight: form.fiche_validation === val ? 800 : 500,
                        fontSize: '0.82rem',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        textAlign: 'center',
                      }}>
                      {icon} {val}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {error && !isAssignee && <p style={{ color: 'var(--danger)', textAlign: 'center', marginBottom: '12px' }}>{error}</p>}

          {/* ⑦ Bouton mise à jour */}
          <button type="submit" disabled={saving || isSingleUpdateLocked}
            style={{ width: '100%', padding: '16px', background: isSingleUpdateLocked ? '#cbd5e1' : 'linear-gradient(135deg, var(--teal), var(--navy))', color: isSingleUpdateLocked ? '#64748b' : '#fff', border: 'none', borderRadius: '12px', fontSize: '1rem', fontWeight: 800, cursor: saving || isSingleUpdateLocked ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
            {saving ? <><Loader2 style={{ width: 18, height: 18, animation: 'spin 1s linear infinite' }} /> Enregistrement...</> : <><Save style={{ width: 18, height: 18 }} /> Mettre à jour{selectedCount > 0 ? ` · ${selectedCount} pièce${selectedCount > 1 ? 's' : ''}` : ''}</>}
          </button>
        </form>}
      </main>
      <BottomNav />
    </div>
  );
}
