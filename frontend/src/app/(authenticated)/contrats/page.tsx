'use client';
import { useState, useEffect, useCallback, useRef } from 'react';
import { contrats, equipements, pieces as piecesApi, clients as clientsApi } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { useRoleGuard } from '@/lib/use-role-guard';
import { KpiCard } from '@/components/ui/cards';
import { downloadBlob } from '@/lib/download';
import {
  Plus, Search, FileText, Calendar, DollarSign, Clock, Wrench,
  X, ChevronDown, Package, Bell, RefreshCcw, CheckSquare, StickyNote,
  Loader2, AlertTriangle, CheckCircle2, ShieldCheck, Building2,
  Eye, Download, Edit2, Camera, Paperclip, Trash2
} from 'lucide-react';

const INPUT = "w-full bg-savia-surface-hover border border-savia-border rounded-lg px-3 py-2 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all text-sm";
const LABEL = "block text-xs font-semibold text-savia-text-muted mb-1 uppercase tracking-wider";
const SECTION_TITLE = "flex items-center gap-2 text-sm font-bold text-savia-text mb-3 pb-2 border-b border-savia-border";

// Les formules ci-dessous correspondent directement aux règles appliquées dans
// le suivi de facturation. « Standard » et « Premium » restent lisibles pour
// les anciens contrats, mais ne sont plus proposés à la création.
const TYPES_CONTRAT = ['Maintenance Préventive', 'Maintenance Corrective', 'Full Service', 'Pièces uniquement', 'Main d\'œuvre uniquement'];
const RECURRENCES = ['Mensuelle', 'Trimestrielle', 'Semestrielle', 'Annuelle', 'Hebdomadaire'];

const CONTRACT_BILLING_RULES = [
  {
    type: 'Maintenance Préventive',
    covered: 'Main-d’œuvre des maintenances prévues au planning',
    billing: 'Les visites hors planning et les pièces non couvertes sont à facturer.',
  },
  {
    type: 'Maintenance Corrective',
    covered: 'Main-d’œuvre des interventions correctives',
    billing: 'Les pièces restent à facturer, sauf si une couverture de pièces est configurée.',
  },
  {
    type: 'Full Service',
    covered: 'Main-d’œuvre et toutes les pièces utilisées',
    billing: 'Intervention entièrement couverte : aucun dossier de facturation à établir.',
  },
  {
    type: 'Pièces uniquement',
    covered: 'Toutes les pièces, ou la sélection définie dans les quotas',
    billing: 'La main-d’œuvre et les éventuelles pièces hors quota sont à facturer.',
  },
  {
    type: 'Main d\'œuvre uniquement',
    covered: 'Main-d’œuvre des interventions couvertes',
    billing: 'Les pièces utilisées sont à facturer.',
  },
] as const;

const DAY_MS = 86_400_000;

const contractDate = (value: string): Date | null => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? null : date;
};

const oneYearLater = (value: string): string => {
  const start = contractDate(value);
  if (!start) return value;
  const end = new Date(Date.UTC(start.getUTCFullYear() + 1, start.getUTCMonth(), start.getUTCDate()));
  // 29 February becomes 28 February when the following year is not leap.
  if (end.getUTCMonth() !== start.getUTCMonth()) {
    return new Date(Date.UTC(start.getUTCFullYear() + 1, start.getUTCMonth() + 1, 0)).toISOString().substring(0, 10);
  }
  return end.toISOString().substring(0, 10);
};

const formatContractDateFr = (value: string): string => {
  const date = contractDate(value);
  if (!date) return value || '';

  return `${String(date.getUTCDate()).padStart(2, '0')}/${String(date.getUTCMonth() + 1).padStart(2, '0')}/${date.getUTCFullYear()}`;
};

const parseContractDateFr = (value: string): string | null => {
  const match = value.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;

  const [, rawDay, rawMonth, rawYear] = match;
  const year = Number(rawYear);
  const month = Number(rawMonth);
  const day = Number(rawDay);
  const date = new Date(Date.UTC(year, month - 1, day));

  if (
    date.getUTCFullYear() !== year
    || date.getUTCMonth() !== month - 1
    || date.getUTCDate() !== day
  ) {
    return null;
  }

  return `${rawYear}-${rawMonth}-${rawDay}`;
};

function ContractDateInput({
  value,
  onChange,
  disabled = false,
  className = INPUT,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
}) {
  const nativeInputRef = useRef<HTMLInputElement>(null);
  const [displayValue, setDisplayValue] = useState(() => formatContractDateFr(value));

  useEffect(() => {
    setDisplayValue(formatContractDateFr(value));
  }, [value]);

  const openCalendar = () => {
    const nativeInput = nativeInputRef.current;
    if (!nativeInput || disabled) return;

    try {
      nativeInput.showPicker();
    } catch {
      nativeInput.focus();
    }
  };

  return (
    <div className="relative w-full">
      <input
        type="text"
        inputMode="numeric"
        maxLength={10}
        placeholder="JJ/MM/AAAA"
        value={displayValue}
        disabled={disabled}
        className={`${className} pr-11 ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
        onChange={event => {
          const digits = event.target.value.replace(/\D/g, '').substring(0, 8);
          const nextDisplay = [digits.substring(0, 2), digits.substring(2, 4), digits.substring(4, 8)]
            .filter(Boolean)
            .join('/');

          setDisplayValue(nextDisplay);
          if (!nextDisplay) {
            onChange('');
            return;
          }

          const isoDate = parseContractDateFr(nextDisplay);
          if (isoDate) onChange(isoDate);
        }}
        onBlur={() => setDisplayValue(formatContractDateFr(value))}
      />
      <input
        ref={nativeInputRef}
        type="date"
        value={value}
        tabIndex={-1}
        aria-hidden="true"
        className="sr-only"
        onChange={event => onChange(event.target.value)}
      />
      <button
        type="button"
        onMouseDown={event => event.preventDefault()}
        onClick={openCalendar}
        disabled={disabled}
        className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-savia-text-muted transition-colors hover:text-savia-accent disabled:cursor-not-allowed"
        aria-label="Ouvrir le calendrier"
        title="Choisir une date"
      >
        <Calendar className="h-4 w-4" />
      </button>
    </div>
  );
}

const isHistoricalContractStart = (startValue: string): boolean => {
  const start = contractDate(startValue);
  if (!start) return false;
  const now = new Date();
  const cutoff = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  cutoff.setUTCMonth(cutoff.getUTCMonth() - 1);
  return start < cutoff;
};

const anniversaryOf = (start: Date, year: number): Date => {
  const anniversary = new Date(Date.UTC(year, start.getUTCMonth(), start.getUTCDate()));
  // A 29 February contract renews on the last day of February in non-leap years.
  if (anniversary.getUTCMonth() !== start.getUTCMonth()) {
    return new Date(Date.UTC(year, start.getUTCMonth() + 1, 0));
  }
  return anniversary;
};

const plural = (count: number, singular: string, pluralValue: string) => `${count} ${count === 1 ? singular : pluralValue}`;

/**
 * Formats an indicative duration without rounding a few surplus days into a
 * new year. Near a full month, the remaining period is shown in months.
 */
const formatContractDuration = (startValue: string, endValue: string): string | null => {
  const start = contractDate(startValue);
  const end = contractDate(endValue);
  if (!start || !end || end < start) return null;

  const totalDays = Math.round((end.getTime() - start.getTime()) / DAY_MS);
  let fullYears = end.getUTCFullYear() - start.getUTCFullYear();
  if (anniversaryOf(start, start.getUTCFullYear() + fullYears) > end) fullYears -= 1;
  const completedAnniversary = anniversaryOf(start, start.getUTCFullYear() + fullYears);
  const nextAnniversary = anniversaryOf(start, start.getUTCFullYear() + fullYears + 1);
  const daysUntilNextAnniversary = Math.round((nextAnniversary.getTime() - end.getTime()) / DAY_MS);

  // Preserve the agreed convention: one or two missing days still count as a year.
  if (daysUntilNextAnniversary > 0 && daysUntilNextAnniversary <= 2) {
    return plural(fullYears + 1, 'an', 'ans');
  }

  if (fullYears === 0) {
    const months = Math.max(1, Math.round(totalDays / 30.4375));
    return plural(months, 'mois', 'mois');
  }

  const remainingDays = Math.round((end.getTime() - completedAnniversary.getTime()) / DAY_MS);
  if (remainingDays === 0) return plural(fullYears, 'an', 'ans');
  if (remainingDays < 25) {
    return `${plural(fullYears, 'an', 'ans')} et ${plural(remainingDays, 'jour', 'jours')}`;
  }

  const remainingMonths = Math.max(1, Math.round(remainingDays / 30.4375));
  if (remainingMonths >= 12) return plural(fullYears + 1, 'an', 'ans');
  return `${plural(fullYears, 'an', 'ans')} et ${plural(remainingMonths, 'mois', 'mois')}`;
};

interface Contrat {
  id: string;
  client: string;
  equipement: string;
  equipements?: string[];
  equipement_ids?: number[];
  equipement_details?: ContractEquipment[];
  type_contrat: string;
  date_debut: string;
  date_fin: string;
  date_signature?: string;
  sla_temps_reponse_h: number;
  montant: number;
  statut: string;
  conditions: string;
  notes: string;
  avec_pieces?: boolean;
  pieces_incluses?: string;
  rappel_avant_jours?: number;
  recurrence_maintenance?: string;
  date_premiere_maintenance?: string;
  date_derniere_maintenance?: string;
  fichier_contrat?: string;
  fichier_content_type?: string;
  has_fichier?: boolean;
  fichiers?: ContractAttachment[];
}

interface ContractAttachment {
  id: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at?: string;
}

interface ContractEquipment {
  id: number;
  nom: string;
  fabricant?: string;
  modele?: string;
  num_serie?: string;
}

const emptyForm = () => {
  const dateDebut = new Date().toISOString().substring(0, 10);
  return {
  client: '',
  equipement: '',
  equipements: [] as string[],
  equipement_ids: [] as number[],
  type_contrat: TYPES_CONTRAT[0],
  date_debut: dateDebut,
  date_fin: oneYearLater(dateDebut),
  date_signature: '',
  // 0 signifie qu'aucun engagement SLA de réponse n'est prévu.
  sla_temps_reponse_h: 0,
  montant: 0,
  avec_pieces: false,
  pieces_selectionnees: [] as { ref: string; designation: string; quota: number }[],
  rappel_avant: 30,
  rappel_unite: 'jours' as 'jours' | 'mois',
  recurrence_maintenance: RECURRENCES[2],
  date_premiere_maintenance: dateDebut,
  date_derniere_maintenance: '',
  conditions: '',
  notes: '',
  statut: 'Actif',
  };
};

const normalizeContractEquipments = (item: any): string[] => {
  const source = Array.isArray(item.equipements) && item.equipements.length > 0
    ? item.equipements
    : [item.equipement];
  const names = source.map((value: any) => typeof value === 'string' ? value : value?.nom)
    .filter((name: any): name is string => typeof name === 'string' && name.trim().length > 0);
  return names.map((name: string) => name.trim());
};

const normalizeContractEquipmentDetails = (item: any): ContractEquipment[] => (
  Array.isArray(item.equipements) ? item.equipements : []
)
  .filter((equipment: any): equipment is Record<string, unknown> => equipment && typeof equipment === 'object')
  .map((equipment: Record<string, unknown>): ContractEquipment => ({
    id: Number(equipment.id || equipment.equipement_id),
    nom: String(equipment.nom || equipment.equipement_nom || '').trim(),
    fabricant: String(equipment.fabricant || '').trim(),
    modele: String(equipment.modele || '').trim(),
    num_serie: String(equipment.num_serie || '').trim(),
  }))
  .filter((equipment: ContractEquipment) => equipment.id > 0 && equipment.nom);

const contractEquipmentItems = (contract: Contrat): Array<ContractEquipment | string> => (
  contract.equipement_details && contract.equipement_details.length > 0
    ? contract.equipement_details
    : normalizeContractEquipments(contract)
);

const contractEquipmentLabel = (equipment: ContractEquipment | string): string => (
  typeof equipment === 'string' ? equipment : equipment.nom
);

const contractEquipmentMeta = (equipment: ContractEquipment | string): string => {
  if (typeof equipment === 'string') return '';
  const manufacturerModel = [equipment.fabricant, equipment.modele].filter(Boolean).join(' · ');
  return [manufacturerModel, equipment.num_serie ? `SN: ${equipment.num_serie}` : ''].filter(Boolean).join(' · ');
};

export default function ContratsPage() {
  const { user } = useAuth();
  useRoleGuard('contrats');
  const canEdit = user?.role === 'Admin' || user?.role === 'Manager' || user?.role === 'Responsable Technique';
  const [search, setSearch] = useState('');
  const [filterStatut, setFilterStatut] = useState('');
  const [data, setData] = useState<Contrat[]>([]);
  const [equips, setEquips] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [stockPieces, setStockPieces] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingContrat, setEditingContrat] = useState<Contrat | null>(null);
  const [selectedContrat, setSelectedContrat] = useState<Contrat | null>(null);
  const [isPdfGen, setIsPdfGen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');
  const [form, setForm] = useState(emptyForm());
  const [contractAttachments, setContractAttachments] = useState<File[]>([]);
  const [pendingAttachmentUpload, setPendingAttachmentUpload] = useState<{ contractId: string; files: File[] } | null>(null);
  const contractFileInputRef = useRef<HTMLInputElement>(null);
  const contractCameraInputRef = useRef<HTMLInputElement>(null);
  const [equipmentDropdownOpen, setEquipmentDropdownOpen] = useState(false);
  const [billingRulesOpen, setBillingRulesOpen] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ contratId: string; contratName: string } | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      // The contract list is readable by client accounts. The other datasets
      // are only needed by the internal create/edit form; /api/pieces is
      // deliberately forbidden for Lecteur and must not hide valid contracts.
      const ctrs = await contrats.list();
      setData((ctrs as any[]).map((item: any) => {
        const equipmentDetails = normalizeContractEquipmentDetails(item);
        return {
        id: String(item.id || ''),
        client: item.client || item.Client || '',
        equipement: item.equipement || normalizeContractEquipments(item)[0] || '',
        equipements: normalizeContractEquipments(item),
        equipement_ids: Array.isArray(item.equipement_ids) && item.equipement_ids.length > 0
          ? item.equipement_ids.map((id: any) => Number(id)).filter((id: number) => id > 0)
          : equipmentDetails.map(equipment => equipment.id),
        equipement_details: equipmentDetails,
        type_contrat: item.type_contrat || TYPES_CONTRAT[0],
        date_debut: (item.date_debut || '').substring(0, 10),
        date_fin: (item.date_fin || '').substring(0, 10),
        date_signature: (item.date_signature || '').substring(0, 10),
        sla_temps_reponse_h: Number(item.sla_temps_reponse_h ?? 0),
        montant: item.montant || item.Montant_Annuel || 0,
        statut: item.statut || 'Actif',
        conditions: item.conditions || '',
        notes: item.notes || '',
        avec_pieces: item.avec_pieces || false,
        pieces_incluses: item.pieces_incluses || '',
        rappel_avant_jours: item.rappel_avant_jours || 30,
        recurrence_maintenance: item.recurrence_maintenance || 'Semestrielle',
        date_premiere_maintenance: (item.date_premiere_maintenance || '').substring(0, 10),
        date_derniere_maintenance: (item.date_derniere_maintenance || '').substring(0, 10),
        fichier_contrat: item.fichier_contrat || '',
        fichier_content_type: item.fichier_content_type || '',
        fichiers: Array.isArray(item.fichiers) ? item.fichiers : [],
        has_fichier: Boolean(item.has_fichier) || (Array.isArray(item.fichiers) && item.fichiers.length > 0),
        };
      }));

      if (!canEdit) return;

      const [eqs, cls, pcs] = await Promise.all([equipements.list(), clientsApi.list(), piecesApi.list()]);
      setEquips(eqs as any[]);
      setClients(cls as any[]);
      setStockPieces(pcs as any[]);
    } catch (err) { console.error(err); }
    finally { setIsLoading(false); }
  }, [canEdit]);

  useEffect(() => { load(); }, [load]);

  // Helper function to determine actual status
  const getActualStatus = (c: Contrat) => {
    const fin = new Date(c.date_fin + 'T23:59:59');
    const daysLeft = Math.floor((fin.getTime() - Date.now()) / 86400000);
    
    if (daysLeft < 0) {
      return 'Expiré';
    }
    
    const statut = (c.statut || 'Actif').toLowerCase();
    if (statut.includes('suspendu')) {
      return 'Suspendu';
    }
    if (statut.includes('expiré')) {
      return 'Expiré';
    }
    
    return 'Actif';
  };

  // Derived lists
  const clientsList = clients.map((c: any) => c.nom).sort();
  const contractedEquipmentIds = new Set(
    data.flatMap(contract => contract.equipement_ids || [])
  );
  const hasLegacyContractEquipment = data.some(contract =>
    normalizeContractEquipments(contract).length > 0 && !(contract.equipement_ids || []).length
  );
  const contractedEquipmentNames = new Set(
    data.flatMap(contract => normalizeContractEquipments(contract))
  );
  const currentContractEquipmentIds = new Set(editingContrat?.equipement_ids || []);
  const currentContractEquipmentNames = new Set(
    editingContrat ? normalizeContractEquipments(editingContrat) : []
  );
  const allEquipsByClient = form.client
    ? equips.filter((e: any) => e.Client === form.client)
    : [];
  const equipsByClient = allEquipsByClient.filter((e: any) => {
    const equipmentId = Number(e.id);
    const equipmentName = String(e.Nom || e.nom || '').trim();
    const isCurrent = currentContractEquipmentIds.has(equipmentId) || currentContractEquipmentNames.has(equipmentName);
    const isAlreadyContracted = contractedEquipmentIds.has(equipmentId) ||
      (hasLegacyContractEquipment && contractedEquipmentNames.has(equipmentName));
    return isCurrent || !isAlreadyContracted;
  });

  // Filter pieces — use designation + equipement_type (correct DB fields)
  // When multiple equipments are selected, show pieces for all of them
  const filteredPieces = form.equipements.length > 0
    ? stockPieces.filter((p: any) => {
        // Check if piece matches ANY of the selected equipments
        return form.equipements.some(selectedEq => {
          const eq = equips.find((e: any) => e.Nom === selectedEq);
          // Equipment type is stored in "Type" field (renamed from "type" in the backend)
          const eqType = (eq?.Type || '').toLowerCase().trim();
          if (!eqType) return false; // If no equipment type, don't include the piece
          
          const pDesignation = (p.designation || '').toLowerCase().trim();
          const pEquipType = (p.equipement_type || '').toLowerCase().trim();
          
          // Match equipment type against piece's equipement_type field
          // Case-insensitive exact match is preferred
          return eqType === pEquipType;
        });
      })
    : stockPieces;

  const applyAttachmentState = (contractId: string, attachment: ContractAttachment) => {
    const updateContract = (contract: Contrat): Contrat => {
      const fichiers = [...(contract.fichiers || []).filter(file => file.id !== attachment.id), attachment];
      return { ...contract, fichiers, has_fichier: true, fichier_contrat: fichiers[0]?.filename || attachment.filename };
    };
    setData(previous => previous.map(contract => contract.id === contractId
      ? updateContract(contract)
      : contract));
    setSelectedContrat(previous => previous?.id === contractId
      ? updateContract(previous)
      : previous);
  };

  const retryAttachmentUpload = async () => {
    if (!pendingAttachmentUpload) return;
    setIsSaving(true);
    try {
      for (const file of pendingAttachmentUpload.files) {
        const result = await contrats.uploadFile(pendingAttachmentUpload.contractId, file);
        applyAttachmentState(pendingAttachmentUpload.contractId, result);
      }
      setPendingAttachmentUpload(null);
      setContractAttachments([]);
      setSaveMsg('✅ Contrat sauvegardé et pièces jointes envoyées avec succès.');
      await load();
      setTimeout(() => { setShowModal(false); setSaveMsg(''); }, 2500);
    } catch (err: any) {
      setSaveMsg(`Échec de l'envoi de la pièce jointe : ${err?.message || 'indisponible'}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSave = async (forcePlanningRebuild = false) => {
    // A contract whose creation/update already succeeded must never be
    // submitted again just because its attachment upload failed.
    if (pendingAttachmentUpload) {
      await retryAttachmentUpload();
      return;
    }
    if (!form.client) { setSaveMsg('Veuillez sélectionner un client.'); return; }
    if (form.equipements.length === 0) { setSaveMsg('Veuillez sélectionner au moins un équipement.'); return; }
    const contractStart = contractDate(form.date_debut);
    const contractEnd = contractDate(form.date_fin);
    const firstMaintenance = contractDate(form.date_premiere_maintenance);
    const lastMaintenance = contractDate(form.date_derniere_maintenance);
    const today = new Date();
    const todayUtc = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate()));
    if (!contractStart || !contractEnd || !firstMaintenance) {
      setSaveMsg('Veuillez renseigner les dates du contrat et de la première maintenance au format JJ/MM/AAAA.');
      return;
    }
    if (contractEnd < contractStart) {
      setSaveMsg('La date de fin doit être postérieure à la date de début.');
      return;
    }
    if (firstMaintenance < contractStart || firstMaintenance > contractEnd) {
      setSaveMsg('La première maintenance doit être comprise dans la période du contrat.');
      return;
    }
    if (isHistoricalContractStart(form.date_debut)) {
      if (!lastMaintenance) {
        setSaveMsg('Renseignez la date de la dernière maintenance pour ce contrat historique.');
        return;
      }
      if (lastMaintenance && (lastMaintenance < contractStart || lastMaintenance > contractEnd || lastMaintenance > todayUtc)) {
        setSaveMsg('La dernière maintenance doit être comprise dans le contrat et ne peut pas être future.');
        return;
      }
    }
    setIsSaving(true);
    setSaveMsg('');
    try {
      const payload = {
        client: form.client,
        equipements: form.equipements,
        equipement_ids: form.equipement_ids,
        equipement: form.equipements[0] || '', // Keep for backward compatibility
        type_contrat: form.type_contrat,
        date_debut: form.date_debut,
        date_fin: form.date_fin,
        date_signature: form.date_signature || '',
        sla_temps_reponse_h: Number(form.sla_temps_reponse_h),
        montant: Number(form.montant),
        avec_pieces: form.avec_pieces,
        pieces_incluses: form.avec_pieces ? JSON.stringify(form.pieces_selectionnees) : '',
        rappel_avant_jours: form.rappel_unite === 'jours' ? form.rappel_avant : form.rappel_avant * 30,
        recurrence_maintenance: form.recurrence_maintenance,
        date_premiere_maintenance: form.date_premiere_maintenance,
        date_derniere_maintenance: isHistoricalContractStart(form.date_debut)
          ? form.date_derniere_maintenance
          : '',
        force_replan: forcePlanningRebuild,
        conditions: form.conditions,
        notes: form.notes,
        statut: form.statut,
      };
      let savedContractId = editingContrat?.id;
      if (editingContrat) {
        const result = await contrats.update(Number(editingContrat.id), payload);
        const planningMsg = result.planning
          ? `\n📅 ${result.planning.removed} visite(s) automatique(s) remplacée(s) ; ${result.planning.created} visite(s) ajoutée(s) au planning.`
          : '';
        setSaveMsg(`✅ Contrat mis à jour avec succès !${planningMsg}`);
      } else {
        const result = await (contrats as any).create(payload) as any;
        savedContractId = result?.contrat_id ? String(result.contrat_id) : undefined;
        const nbPlannings = result?.nb_plannings || 0;
        const planningMsg = nbPlannings > 0
          ? `\n📅 ${nbPlannings} maintenance(s) ajoutée(s) au planning automatiquement`
          : '\nℹ️ Aucune maintenance à venir n’a été créée. Vérifiez la première maintenance, la fin du contrat et la récurrence.';
        setSaveMsg(`✅ Contrat créé avec succès !${planningMsg}`);
      }
      if (contractAttachments.length > 0 && savedContractId) {
        try {
          for (const file of contractAttachments) {
            const uploaded = await contrats.uploadFile(savedContractId, file);
            applyAttachmentState(savedContractId, uploaded);
          }
        } catch {
          setPendingAttachmentUpload({ contractId: savedContractId, files: contractAttachments });
          await load();
          setSaveMsg('');
          return;
        }
      }
      setForm(emptyForm());
      setContractAttachments([]);
      if (contractFileInputRef.current) contractFileInputRef.current.value = '';
      if (contractCameraInputRef.current) contractCameraInputRef.current.value = '';
      setEditingContrat(null);
      await load();
      setTimeout(() => { setShowModal(false); setSaveMsg(''); }, 4000);
    } catch (err: any) {
      setSaveMsg(`❌ Erreur: ${err?.message || 'Indisponible'}`);
    } finally { setIsSaving(false); }
  };

  const openEdit = (c: Contrat) => {
    setEditingContrat(c);
    setContractAttachments([]);
    setPendingAttachmentUpload(null);
    
    // Parse pieces_incluses from JSON if it exists
    let pieces_selectionnees: { ref: string; designation: string; quota: number }[] = [];
    if (c.pieces_incluses) {
      try {
        const parsed = JSON.parse(c.pieces_incluses);
        if (Array.isArray(parsed)) {
          pieces_selectionnees = parsed;
        }
      } catch (e) {
        console.debug('Could not parse pieces_incluses:', e);
      }
    }
    
    // Convert rappel_avant_jours to rappel_avant and rappel_unite
    const rappel_avant_jours = c.rappel_avant_jours || 30;
    const rappel_avant = rappel_avant_jours % 30 === 0 ? rappel_avant_jours / 30 : rappel_avant_jours;
    const rappel_unite = rappel_avant_jours % 30 === 0 ? 'mois' : 'jours';
    
    setForm({
      client: c.client,
      equipement: c.equipement,
      equipements: c.equipements || (c.equipement ? [c.equipement] : []),
      equipement_ids: c.equipement_ids?.length
        ? c.equipement_ids
        : (c.equipement_details || []).map(equipment => equipment.id),
      type_contrat: c.type_contrat,
      date_debut: c.date_debut,
      date_fin: c.date_fin,
      date_signature: c.date_signature || '',
      sla_temps_reponse_h: c.sla_temps_reponse_h,
      montant: c.montant,
      avec_pieces: c.avec_pieces || false,
      pieces_selectionnees: pieces_selectionnees,
      rappel_avant: rappel_avant,
      rappel_unite: rappel_unite as 'jours' | 'mois',
      recurrence_maintenance: c.recurrence_maintenance || RECURRENCES[2],
      date_premiere_maintenance: c.date_premiere_maintenance || c.date_debut,
      date_derniere_maintenance: c.date_derniere_maintenance || '',
      conditions: c.conditions,
      notes: c.notes,
      statut: c.statut,
    });
    setSaveMsg('');
    setShowModal(true);
  };

  const set = (k: string, v: any) => setForm(f => ({ ...f, [k]: v }));

  const chooseContractAttachments = (files: File[] | FileList) => {
    const selectedFiles = Array.from(files);
    if (selectedFiles.length === 0) return;
    const allowed = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];
    const invalidFile = selectedFiles.find(file => !allowed.includes(file.type));
    if (invalidFile) {
      setSaveMsg('❌ Format refusé. Choisissez une image JPG, PNG, WEBP ou un PDF.');
      return;
    }
    const existingCount = editingContrat?.fichiers?.length || 0;
    if (existingCount + contractAttachments.length + selectedFiles.length > 10) {
      setSaveMsg('❌ Un contrat ne peut pas contenir plus de 10 pièces jointes.');
      return;
    }
    setSaveMsg('');
    setContractAttachments(current => [...current, ...selectedFiles]);
  };

  const removeContractAttachment = (index: number) => {
    setContractAttachments(current => current.filter((_, attachmentIndex) => attachmentIndex !== index));
    setPendingAttachmentUpload(null);
  };

  // Toggle a piece in/out of selection (identified by unique reference)
  const togglePiece = (ref: string, designation: string) => setForm(f => {
    const exists = f.pieces_selectionnees.find(s => s.ref === ref);
    return {
      ...f,
      pieces_selectionnees: exists
        ? f.pieces_selectionnees.filter(s => s.ref !== ref)
        : [...f.pieces_selectionnees, { ref, designation, quota: 1 }],
    };
  });

  const setPieceQuota = (ref: string, quota: number) => setForm(f => ({
    ...f,
    pieces_selectionnees: f.pieces_selectionnees.map(s => s.ref === ref ? { ...s, quota: Math.max(1, quota) } : s),
  }));

  // Equipment multi-select handlers
  const toggleEquipment = (equipment: any) => {
    const equipmentId = Number(equipment.id);
    const equipmentName = String(equipment.Nom || equipment.nom || '').trim();
    setForm(f => {
      if (!equipmentName) return f;
      const selectedIndex = equipmentId > 0 ? f.equipement_ids.indexOf(equipmentId) : -1;
      if (selectedIndex >= 0) {
        return {
          ...f,
          equipement_ids: f.equipement_ids.filter(id => id !== equipmentId),
          equipements: f.equipements.filter((_, index) => index !== selectedIndex),
        };
      }
      const nameIndex = f.equipements.indexOf(equipmentName);
      if (equipmentId <= 0 && nameIndex >= 0) {
        return { ...f, equipements: f.equipements.filter((_, index) => index !== nameIndex) };
      }
      return {
        ...f,
        equipement_ids: equipmentId > 0 ? [...f.equipement_ids, equipmentId] : f.equipement_ids,
        equipements: [...f.equipements, equipmentName],
      };
    });
  };

  const removeEquipment = (index: number) => {
    setForm(f => ({
      ...f,
      equipement_ids: f.equipement_ids.filter((_, equipmentIndex) => equipmentIndex !== index),
      equipements: f.equipements.filter((_, equipmentIndex) => equipmentIndex !== index),
    }));
  };

  const filtered = data
    .filter(c => {
      const matchSearch = !search || c.client.toLowerCase().includes(search.toLowerCase()) ||
        c.id.toLowerCase().includes(search.toLowerCase()) ||
        (c.type_contrat || '').toLowerCase().includes(search.toLowerCase());
      
      // Determine actual status
      const actualStatus = getActualStatus(c);
      
      const matchStatut = !filterStatut || actualStatus.toLowerCase() === filterStatut.toLowerCase();
      return matchSearch && matchStatut;
    })
    // Sort by ID descending (newest first)
    .sort((a, b) => Number(b.id) - Number(a.id));

  const actifs = data.filter(c => getActualStatus(c) === 'Actif').length;
  const suspendus = data.filter(c => getActualStatus(c) === 'Suspendu').length;
  const expires = data.filter(c => getActualStatus(c) === 'Expiré').length;
  const expiringIn60 = data.filter(c => {
    const fin = new Date(c.date_fin + 'T23:59:59');
    const diff = Math.floor((fin.getTime() - Date.now()) / 86400000);
    return diff >= 0 && diff <= 60 && getActualStatus(c) === 'Actif';
  }).length;
  
  // Calculate prorata revenue for current year (2026)
  const currentYear = new Date().getFullYear();
  const yearStart = new Date(currentYear, 0, 1);
  const yearEnd = new Date(currentYear, 11, 31);
  const daysInYear = 365;
  
  const totalRevenu = data.reduce((total, c) => {
    const montant = c.montant || 0;
    if (montant === 0) return total;
    
    const debut = new Date(c.date_debut);
    const fin = new Date(c.date_fin);
    
    // Calculate overlap between contract and current year
    const overlapStart = new Date(Math.max(debut.getTime(), yearStart.getTime()));
    const overlapEnd = new Date(Math.min(fin.getTime(), yearEnd.getTime()));
    
    // If no overlap, return 0
    if (overlapStart > overlapEnd) return total;
    
    // Calculate days of overlap
    const daysOverlap = (overlapEnd.getTime() - overlapStart.getTime()) / 86400000 + 1; // +1 to include both start and end days
    
    // Calculate prorata revenue
    const prorataRevenu = montant * (daysOverlap / daysInYear);
    
    return total + prorataRevenu;
  }, 0);
  const formDuration = formatContractDuration(form.date_debut, form.date_fin);
  const isHistoricalContract = isHistoricalContractStart(form.date_debut);

  if (isLoading) return (
    <div className="flex justify-center items-center h-64">
      <Loader2 className="w-8 h-8 animate-spin text-savia-accent" />
    </div>
  );

  const handleContratPdf = async (c: Contrat) => {
    setIsPdfGen(true);
    console.log('Starting contract PDF generation for:', c.id);
    try {
      const cn = localStorage.getItem('savia_company') || 'SAVIA';
      const cl = localStorage.getItem('savia_logo') || '';

      const res = await fetch(`/api/contrats/${c.id}/contrat-pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ company_name: cn, company_logo: cl }),
      });
      if (!res.ok) throw new Error('Erreur HTTP ' + res.status);
      const blob = await res.blob();
      if (!blob || blob.size === 0) throw new Error('PDF vide reçu');
      const safeClient = c.client.replace(/\s+/g, '_').replace(/[^A-Za-z0-9._-]/g, '');
      downloadBlob(blob, `contrat_maintenance_${c.id}_${safeClient}.pdf`);
    } catch (err: any) {
      console.error('PDF Error:', err);
      alert('Erreur PDF: ' + (err?.message || err));
    }
    finally { setIsPdfGen(false); }
  };

  const handleContractAttachmentDownload = async (c: Contrat, attachment: ContractAttachment) => {
    try {
      const blob = await contrats.downloadFile(c.id, attachment.id);
      downloadBlob(blob, attachment.filename || `contrat_${c.id}`);
    } catch (err: any) {
      alert('Erreur pièce jointe : ' + (err?.message || err));
    }
  };

  const handleDeleteContractAttachment = async (c: Contrat, attachment: ContractAttachment) => {
    if (!canEdit) return;
    if (!window.confirm(`Supprimer définitivement « ${attachment.filename} » du contrat #${c.id} ?`)) return;
    setIsDeleting(true);
    try {
      await contrats.deleteFile(c.id, attachment.id);
      const removeAttachment = (contract: Contrat): Contrat => {
        const fichiers = (contract.fichiers || []).filter(file => file.id !== attachment.id);
        return { ...contract, fichiers, has_fichier: fichiers.length > 0, fichier_contrat: fichiers[0]?.filename || '' };
      };
      setData(previous => previous.map(contract => contract.id === c.id ? removeAttachment(contract) : contract));
      setSelectedContrat(previous => previous?.id === c.id ? removeAttachment(previous) : previous);
      setEditingContrat(previous => previous?.id === c.id ? removeAttachment(previous) : previous);
      setSaveMsg('✅ Pièce jointe supprimée.');
    } catch (err: any) {
      setSaveMsg(`❌ Erreur suppression pièce jointe: ${err?.message || 'Indisponible'}`);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDeleteContrat = async () => {
    if (!deleteConfirm) return;
    setIsDeleting(true);
    try {
      const res = await fetch(`/api/contrats/${deleteConfirm.contratId}`, {
        method: 'DELETE',
        credentials: 'same-origin',
      });

      if (!res.ok) throw new Error(`Erreur HTTP ${res.status}`);
      
      // Reload the data
      await load();
      setDeleteConfirm(null);
      setSelectedContrat(null);
      setSaveMsg('✅ Contrat et ses données associées supprimés avec succès!');
    } catch (err: any) {
      setSaveMsg(`❌ Erreur suppression: ${err?.message || 'Indisponible'}`);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black gradient-text flex items-center gap-2">
            <FileText className="w-7 h-7 text-savia-accent" /> Contrats de Maintenance
          </h1>
          <p className="text-savia-text-muted text-sm mt-1">Gestion des contrats SAV et maintenance préventive</p>
        </div>
        {canEdit && <button onClick={() => { setEditingContrat(null); setForm(emptyForm()); setContractAttachments([]); setPendingAttachmentUpload(null); setSaveMsg(''); setShowModal(true); }}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-cyan-500/20">
          <Plus className="w-4 h-4" /> Nouveau contrat
        </button>}
      </div>

      {/* KPIs - All in one row */}
      <div className="grid grid-cols-2 md:grid-cols-12 gap-2">
        {[
          { label: 'Total contrats', value: data.length, color: 'text-savia-accent', icon: <FileText className="w-4 h-4" />, span: false },
          { label: 'Actifs', value: actifs, color: 'text-green-400', icon: <CheckCircle2 className="w-4 h-4" />, span: false },
          { label: 'Suspendus', value: suspendus, color: 'text-orange-400', icon: <AlertTriangle className="w-4 h-4" />, span: false },
          { label: 'Expiré', value: expires, color: 'text-red-500', icon: <AlertTriangle className="w-4 h-4" />, span: false },
          { label: 'Expire dans 60j', value: expiringIn60, color: 'text-yellow-400', icon: <Clock className="w-4 h-4" />, span: false },
        ].map(k => (
          <KpiCard key={k.label} emphasis className="md:col-span-2" appearance="status-stripe" icon={k.icon} value={String(k.value)} label={k.label}
            variant={k.label === 'Actifs' ? 'success' : k.label === 'Expiré' ? 'danger' : k.label === 'Suspendus' || k.label === 'Expire dans 60j' ? 'warning' : 'default'} />
        ))}
        
        {/* Revenu annuel - larger card (2 columns) */}
        <KpiCard emphasis className="md:col-span-2" appearance="status-stripe" icon={<DollarSign className="h-6 w-6" />} value={`${(totalRevenu / 1000).toFixed(0)}K TND`} label="Revenu annuel" variant="success" />
      </div>

      <section className="glass overflow-hidden rounded-xl">
        <button
          type="button"
          onClick={() => setBillingRulesOpen(open => !open)}
          aria-expanded={billingRulesOpen}
          className="flex w-full items-center justify-between gap-3 p-5 text-left transition-colors hover:bg-savia-surface-hover/50"
        >
          <span className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-savia-text-muted">
            <DollarSign className="h-4 w-4 text-savia-accent" /> Types de contrat et suivi de facturation
          </span>
          <ChevronDown className={`h-5 w-5 shrink-0 text-savia-text-muted transition-transform ${billingRulesOpen ? 'rotate-180' : ''}`} />
        </button>
        {billingRulesOpen && (
          <div className="border-t border-savia-border px-5 pb-5">
            <p className="mb-4 mt-4 text-sm text-savia-text-muted">La couverture ci-dessous détermine les éléments présentés comme facturables dans le suivi de facturation.</p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-savia-border text-xs uppercase tracking-wider text-savia-text-muted">
                  <tr>
                    <th className="px-3 py-2.5 font-semibold">Type de contrat</th>
                    <th className="px-3 py-2.5 font-semibold">Couverture contractuelle</th>
                    <th className="px-3 py-2.5 font-semibold">Suivi de facturation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-savia-border/70">
                  {CONTRACT_BILLING_RULES.map(rule => (
                    <tr key={rule.type} className="align-top hover:bg-savia-surface-hover/40">
                      <td className="px-3 py-3 font-bold text-savia-accent">{rule.type}</td>
                      <td className="px-3 py-3 text-savia-text">{rule.covered}</td>
                      <td className="px-3 py-3 text-savia-text-muted">{rule.billing}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {/* ===== BANNER : contrats expirant dans 30j ===== */}
      {(() => {
        const expiring30 = data.filter(c => {
          const fin = new Date(c.date_fin + 'T23:59:59');
          const diff = Math.floor((fin.getTime() - Date.now()) / 86400000);
          return diff >= 0 && diff <= 30 && getActualStatus(c) === 'Actif';
        });
        if (expiring30.length === 0) return null;
        return (
          <div className="rounded-xl border-l-4 border-amber-500 bg-amber-50 p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />
              <span className="font-bold text-amber-800">
                ⚠️ {expiring30.length} contrat(s) expire(nt) dans moins de 30 jours
              </span>
            </div>
            <div className="space-y-2 md:pl-7">
              {expiring30.map(c => {
                const fin = new Date(c.date_fin + 'T23:59:59');
                const daysLeft = Math.floor((fin.getTime() - Date.now()) / 86400000);
                const contractEquipments = contractEquipmentItems(c);
                const visibleEquipments = contractEquipments.slice(0, 3);
                const hiddenEquipmentCount = contractEquipments.length - visibleEquipments.length;
                const expiryDate = c.date_fin.split('-').reverse().join('/');
                return (
                  <div key={c.id} className="flex flex-col gap-3 rounded-lg bg-amber-100/60 p-3 text-sm text-amber-800 md:flex-row md:items-center">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded bg-amber-200/70 px-1.5 py-0.5 font-mono text-xs">#{c.id}</span>
                        <span title={c.client} className="min-w-0 max-w-full truncate font-bold text-amber-900 md:max-w-md">
                          {c.client}
                        </span>
                      </div>
                      {contractEquipments.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {visibleEquipments.map((equipment, index) => {
                            const label = contractEquipmentLabel(equipment);
                            const meta = contractEquipmentMeta(equipment);
                            const equipmentTitle = [label, meta].filter(Boolean).join(' · ');
                            return (
                              <span
                                key={typeof equipment === 'string' ? `${label}-${index}` : equipment.id}
                                title={equipmentTitle}
                                className="inline-flex max-w-64 items-center gap-1 truncate rounded-full border border-amber-300/70 bg-amber-50 px-2 py-0.5 text-xs text-amber-700"
                              >
                                <Wrench className="h-3 w-3 shrink-0" />
                                <span className="truncate">{label}{meta && ` · ${meta}`}</span>
                              </span>
                            );
                          })}
                          {hiddenEquipmentCount > 0 && (
                            <span className="inline-flex items-center rounded-full border border-amber-300/70 bg-amber-200/60 px-2 py-0.5 text-xs font-bold text-amber-800">
                              + {hiddenEquipmentCount} {hiddenEquipmentCount === 1 ? 'autre' : 'autres'}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center justify-between gap-3 rounded-lg border border-amber-300/70 bg-amber-50 px-3 py-2 text-right md:block">
                      <span className="font-black text-amber-800">{daysLeft} j restant{daysLeft === 1 ? '' : 's'}</span>
                      <span className="block whitespace-nowrap text-xs font-semibold text-amber-600">Expire le {expiryDate}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}

      {/* Search & Filters */}
      <div className="flex gap-3 flex-col md:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-savia-text-dim" />
          <input type="text" placeholder="Rechercher par client, type, référence..." value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-savia-surface border border-savia-border rounded-lg pl-10 pr-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 placeholder:text-savia-text-dim outline-none" />
        </div>
        <div className="flex gap-2 flex-wrap items-center">
          <label className="text-xs font-semibold text-savia-text-muted uppercase tracking-wider">Filtre statut :</label>
          <select value={filterStatut} onChange={e => setFilterStatut(e.target.value)}
            className="bg-savia-surface border border-savia-border rounded-lg px-4 py-2.5 text-savia-text focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all text-sm font-semibold">
            <option value="">Tous les statuts</option>
            <option value="actif">Actif</option>
            <option value="suspendu">Suspendu</option>
            <option value="expiré">Expiré</option>
          </select>
          {filterStatut && (
            <button onClick={() => setFilterStatut('')}
              className="flex items-center gap-1.5 px-3 py-2.5 rounded-lg text-xs font-semibold text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover transition-all cursor-pointer border border-savia-border">
              <X className="w-3.5 h-3.5" /> Réinitialiser
            </button>
          )}
        </div>
      </div>

      {/* Contract list */}
      <div className="space-y-3">
        {filtered.length === 0 && (
          <div className="glass rounded-xl p-8 text-center text-savia-text-muted">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
            Aucun contrat trouvé
          </div>
        )}
        {filtered.map(c => {
          const fin = new Date(c.date_fin + 'T23:59:59'); // Add time to ensure full day
          const daysLeft = Math.floor((fin.getTime() - Date.now()) / 86400000);
          const actualStatus = getActualStatus(c);
          const isExpired = actualStatus === 'Expiré';
          const isSuspendu = actualStatus === 'Suspendu';
          const isExpiring = daysLeft >= 0 && daysLeft <= 60 && actualStatus === 'Actif';
          const contractEquipments = contractEquipmentItems(c);
          const visibleEquipments = contractEquipments.slice(0, 3);
          const hiddenEquipmentCount = contractEquipments.length - visibleEquipments.length;
          
          // Determine badge color and text
          let badgeClass = 'bg-green-500/10 text-green-400';
          let badgeText = actualStatus;
          
          if (isExpired) {
            badgeClass = 'bg-red-500/10 text-red-500';
            badgeText = 'Expiré';
          } else if (isSuspendu) {
            badgeClass = 'bg-orange-500/10 text-orange-400';
            badgeText = 'Suspendu';
          } else if (isExpiring) {
            badgeClass = 'bg-yellow-500/10 text-yellow-400';
            badgeText = `Expire dans ${daysLeft}j`;
          }
          
          return (
            <div key={c.id} className="glass rounded-xl p-4 hover:border-savia-accent/30 transition-all">
              <div className="flex items-start justify-between mb-2">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <FileText className="w-4 h-4 text-savia-accent shrink-0" />
                    <span className="font-mono text-savia-accent font-bold text-sm">#{c.id}</span>
                    <span className="font-bold">{c.client}</span>
                  </div>
                  {/* Display equipments */}
                  {contractEquipments.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {visibleEquipments.map((equipment, index) => {
                        const label = contractEquipmentLabel(equipment);
                        const meta = contractEquipmentMeta(equipment);
                        return (
                          <span key={typeof equipment === 'string' ? `${label}-${index}` : equipment.id} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-savia-accent/10 text-savia-accent text-xs font-medium border border-savia-accent/20">
                            <Wrench className="w-2.5 h-2.5" /> {label}
                            {meta && <span className="text-savia-text-muted font-normal">({meta})</span>}
                          </span>
                        );
                      })}
                      {hiddenEquipmentCount > 0 && (
                        <span className="inline-flex items-center rounded-full border border-savia-border bg-savia-surface-hover px-2 py-0.5 text-xs font-semibold text-savia-text-muted">
                          + {hiddenEquipmentCount} {hiddenEquipmentCount === 1 ? 'autre' : 'autres'}
                        </span>
                      )}
                    </div>
                  )}
                  <div className="flex items-center gap-3 text-xs text-savia-text-muted flex-wrap">
                    <span className="flex items-center gap-1"><Wrench className="w-3 h-3" /> {c.type_contrat}</span>
                    <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> SLA: {c.sla_temps_reponse_h}h</span>
                    <span className="flex items-center gap-1"><Calendar className="w-3 h-3" /> {formatContractDateFr(c.date_debut)} → {formatContractDateFr(c.date_fin)}</span>
                    {c.montant > 0 && <span className="flex items-center gap-1"><DollarSign className="w-3 h-3" /> {c.montant.toLocaleString('fr')} TND/an</span>}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-bold whitespace-nowrap ${badgeClass}`}>
                    {badgeText}
                  </span>
                </div>
              </div>
              {(c.conditions || c.notes) && (
                <div className="mt-2 space-y-1.5 border-l-2 border-savia-border pl-2 text-xs text-savia-text-muted">
                  {c.conditions && (
                    <p className="font-bold line-clamp-2"><span className="font-semibold">Conditions : </span>{c.conditions}</p>
                  )}
                  {c.notes && (
                    <p className="italic line-clamp-2"><span className="font-semibold not-italic">Notes : </span>{c.notes}</p>
                  )}
                </div>
              )}
              {/* Action buttons */}
              <div className="flex items-center gap-2 mt-3 pt-2 border-t border-savia-border/40">
                <button
                  onClick={() => setSelectedContrat(c)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-savia-accent hover:bg-savia-accent/10 border border-savia-accent/20 transition-all cursor-pointer"
                >
                  <Eye className="w-3.5 h-3.5" /> Voir les détails
                </button>
                {(c.fichiers?.length || 0) > 0 && (
                  <button
                    onClick={() => handleContractAttachmentDownload(c, c.fichiers![0])}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-purple-300 hover:bg-purple-500/10 border border-purple-400/20 transition-all cursor-pointer"
                  >
                    <Paperclip className="w-3.5 h-3.5" /> Pièces jointes ({c.fichiers!.length})
                  </button>
                )}
                {canEdit && (
                  <button
                    onClick={() => openEdit(c)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-blue-400 hover:bg-blue-500/10 border border-blue-400/20 transition-all cursor-pointer"
                  >
                    <Edit2 className="w-3.5 h-3.5" /> Modifier
                  </button>
                )}
                <button
                  onClick={() => handleContratPdf(c)}
                  disabled={isPdfGen}
                  className="hidden flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer"
                >
                  <Download className="w-3.5 h-3.5" /> {isPdfGen ? 'Génération...' : 'Télécharger PDF'}
                </button>
                {canEdit && (
                  <button
                    onClick={() => setDeleteConfirm({ contratId: c.id, contratName: c.client })}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-red-400 hover:bg-red-500/10 border border-red-400/20 transition-all cursor-pointer ml-auto"
                  >
                    <X className="w-3.5 h-3.5" /> Supprimer
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* ============== DETAIL MODAL ============== */}
      {selectedContrat && (() => {
        const c = selectedContrat;
        const actualStatus = getActualStatus(c);
        const fin = new Date(c.date_fin + 'T23:59:59');
        const daysLeft = Math.floor((fin.getTime() - Date.now()) / 86400000);
        const isExpired = actualStatus === 'Expiré';
        const isExpiring = daysLeft >= 0 && daysLeft <= 60 && actualStatus === 'Actif';
        const isSuspendu = actualStatus === 'Suspendu';
        const duration = formatContractDuration(c.date_debut, c.date_fin);
        
        let statutLabel = actualStatus;
        let badgeClass = 'bg-green-500/15 text-green-400';
        
        if (isExpired) {
          statutLabel = 'Expiré';
          badgeClass = 'bg-red-500/15 text-red-400';
        } else if (isSuspendu) {
          statutLabel = 'Suspendu';
          badgeClass = 'bg-orange-500/15 text-orange-400';
        } else if (isExpiring) {
          statutLabel = `Expire dans ${daysLeft}j`;
          badgeClass = 'bg-yellow-500/15 text-yellow-400';
        }
        
        return (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setSelectedContrat(null)}>
            <div className="glass rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl" onClick={e => e.stopPropagation()}>
              {/* Header */}
              <div className="flex items-center justify-between p-5 border-b border-savia-border">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-savia-accent/10 flex items-center justify-center">
                    <FileText className="w-5 h-5 text-savia-accent" />
                  </div>
                  <div>
                    <h2 className="font-bold text-lg">Contrat #{c.id}</h2>
                    <p className="text-xs text-savia-text-muted">{c.type_contrat}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => handleContratPdf(c)} disabled={isPdfGen}
                    className="hidden flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer">
                    <Download className="w-4 h-4" /> {isPdfGen ? 'Génération...' : 'Télécharger PDF'}
                  </button>
                  <button onClick={() => setSelectedContrat(null)} className="p-2 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted hover:text-savia-text transition-all cursor-pointer">
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>
              {/* Content */}
              <div className="p-5 space-y-5">
                {/* Status badge */}
                <div className="flex items-center gap-3">
                  <span className={`px-3 py-1 rounded-full text-sm font-bold ${badgeClass}`}>{statutLabel}</span>
                  {c.montant > 0 && <span className="text-savia-text-muted text-sm">{c.montant.toLocaleString('fr')} TND / an</span>}
                </div>
                {/* Grid info */}
                <div className="grid grid-cols-2 gap-4">
                  {[{icon: Building2, label: 'Client', val: c.client},
                    {icon: Wrench, label: 'Type de contrat', val: c.type_contrat || '—'},
                    {icon: Calendar, label: 'Date début', val: formatContractDateFr(c.date_debut)},
                    {icon: Calendar, label: 'Date fin', val: formatContractDateFr(c.date_fin)},
                    {icon: Calendar, label: 'Date de signature', val: c.date_signature ? formatContractDateFr(c.date_signature) : '—'},
                    {icon: Clock, label: 'Durée', val: duration || '—'},
                    {icon: RefreshCcw, label: 'Récurrence', val: c.recurrence_maintenance || '—'},
                    {icon: Calendar, label: 'Première maintenance', val: c.date_premiere_maintenance ? formatContractDateFr(c.date_premiere_maintenance) : '—'},
                    {icon: Clock, label: 'SLA Réponse', val: c.sla_temps_reponse_h + 'h'},
                    {icon: DollarSign, label: 'Montant annuel', val: (c.montant||0).toLocaleString('fr') + ' TND'},
                  ].map(({icon: Icon, label, val}) => (
                    <div key={label} className="bg-savia-surface-hover/40 rounded-xl p-3 flex items-start gap-3">
                      <Icon className="w-4 h-4 text-savia-accent mt-0.5 shrink-0" />
                      <div>
                        <p className="text-xs text-savia-text-muted font-semibold uppercase tracking-wider">{label}</p>
                        <p className="text-sm font-semibold mt-0.5">{val}</p>
                      </div>
                    </div>
                  ))}
                </div>
                
                {/* Equipments List */}
                {contractEquipmentItems(c).length > 0 && (
                  <div className="bg-savia-surface-hover/40 rounded-xl p-4">
                    <p className="text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-3 flex items-center gap-2"><Wrench className="w-3.5 h-3.5 text-savia-accent" /> Équipements</p>
                    <div className="space-y-2">
                      {contractEquipmentItems(c).map((equipment, index) => {
                        const label = contractEquipmentLabel(equipment);
                        const meta = contractEquipmentMeta(equipment);
                        return (
                          <div key={typeof equipment === 'string' ? `${label}-${index}` : equipment.id} className="flex items-start gap-2 px-3 py-2 rounded-lg bg-savia-accent/10 border border-savia-accent/30 text-savia-accent">
                            <Wrench className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                            <div className="min-w-0">
                              <p className="text-sm font-semibold">{label}</p>
                              {meta && <p className="text-xs font-normal text-savia-text-muted mt-0.5">{meta}</p>}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                
                {/* Pièces couvertes */}
                {c.avec_pieces && c.pieces_incluses && (() => {
                  try {
                    const pieces = JSON.parse(c.pieces_incluses);
                    if (Array.isArray(pieces) && pieces.length > 0) {
                      return (
                        <div className="bg-savia-surface-hover/40 rounded-xl p-4">
                          <p className="text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-3 flex items-center gap-2"><Package className="w-3.5 h-3.5 text-savia-accent" /> Pièces couvertes par le contrat</p>
                          <div className="space-y-2">
                            {pieces.map((p: any) => (
                              <div key={p.ref} className="flex items-center justify-between px-3 py-2 rounded-lg bg-savia-surface/40 border border-savia-border/30">
                                <div>
                                  <p className="text-sm font-semibold text-savia-text">{p.designation}</p>
                                  <p className="text-xs text-savia-text-muted font-mono">{p.ref}</p>
                                </div>
                                <span className="text-sm font-bold text-savia-accent">Quota: {p.quota}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    }
                  } catch (e) {
                    console.debug('Could not parse pieces:', e);
                  }
                  return null;
                })()}
                
                {(c.fichiers?.length || 0) > 0 && (
                  <div className="bg-savia-surface-hover/40 rounded-xl p-4 space-y-2">
                    <p className="text-xs text-savia-text-muted font-semibold uppercase tracking-wider">Pièces jointes du contrat</p>
                    {c.fichiers!.map(attachment => (
                      <div key={attachment.id} className="flex items-center justify-between gap-3 rounded-lg bg-savia-surface/40 border border-savia-border/30 px-3 py-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <Paperclip className="w-4 h-4 text-purple-300 shrink-0" />
                          <div className="min-w-0">
                            <p className="text-sm font-semibold truncate">{attachment.filename || 'Document joint'}</p>
                            <p className="text-xs text-savia-text-muted">{(attachment.size_bytes / 1024 / 1024).toFixed(2)} Mo</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <button onClick={() => handleContractAttachmentDownload(c, attachment)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-purple-300 hover:bg-purple-500/10 border border-purple-400/20 transition-all cursor-pointer">
                            <Download className="w-3.5 h-3.5" /> Télécharger
                          </button>
                          {canEdit && (
                            <button
                              onClick={() => handleDeleteContractAttachment(c, attachment)}
                              disabled={isDeleting}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-red-400 hover:bg-red-500/10 border border-red-400/20 transition-all cursor-pointer disabled:opacity-50"
                              title="Supprimer la pièce jointe"
                            >
                              <Trash2 className="w-3.5 h-3.5" /> Supprimer
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Conditions */}
                {c.conditions && (
                  <div className="bg-savia-surface-hover/40 rounded-xl p-4">
                    <p className="text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2"><ShieldCheck className="w-3.5 h-3.5 text-savia-accent" /> Conditions contractuelles</p>
                    <p className="text-sm text-savia-text leading-relaxed whitespace-pre-wrap font-bold">{c.conditions}</p>
                  </div>
                )}
                {/* Notes */}
                {c.notes && (
                  <div className="bg-savia-surface-hover/40 rounded-xl p-4">
                    <p className="text-xs font-semibold text-savia-text-muted uppercase tracking-wider mb-2 flex items-center gap-2"><StickyNote className="w-3.5 h-3.5 text-savia-accent" /> Notes internes</p>
                    <p className="text-sm text-savia-text leading-relaxed whitespace-pre-wrap italic">{c.notes}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })()}

      {/* ===================== MODAL ===================== */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 backdrop-blur-sm overflow-y-auto py-6 px-4">
          <div className="bg-savia-surface border border-savia-border rounded-2xl w-full max-w-2xl shadow-2xl">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-savia-border">
              <h2 className="text-lg font-black gradient-text flex items-center gap-2">
                {editingContrat ? <Edit2 className="w-5 h-5 text-blue-400" /> : <Plus className="w-5 h-5 text-savia-accent" />}
                {editingContrat ? `Modifier le contrat #${editingContrat.id}` : 'Nouveau Contrat'}
              </h2>
              <button onClick={() => setShowModal(false)} className="p-1.5 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted hover:text-savia-text transition-all cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="px-6 py-5 space-y-6 max-h-[80vh] overflow-y-auto">

              {/* === SECTION: Client & Équipement === */}
              <div>
                <div className={SECTION_TITLE}>
                  <Building2 className="w-4 h-4 text-savia-accent" /> Client &amp; Équipement
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className={LABEL}>Client *</label>
                    <select className={INPUT} value={form.client} onChange={e => { set('client', e.target.value); set('equipements', []); set('equipement_ids', []); }}>
                      <option value="">— Sélectionner un client —</option>
                      {clientsList.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                  
                  {/* Multi-select Equipment Dropdown */}
                  <div>
                    <label className={LABEL}>Équipements</label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setEquipmentDropdownOpen(!equipmentDropdownOpen)}
                        disabled={!form.client}
                        className={`w-full flex items-center justify-between px-3 py-2 rounded-lg border transition-all text-sm ${
                          !form.client
                            ? 'bg-savia-surface-hover/50 border-savia-border/50 text-savia-text-muted cursor-not-allowed'
                            : 'bg-savia-surface-hover border-savia-border text-savia-text hover:border-savia-accent/40 focus:ring-2 focus:ring-savia-accent/40 cursor-pointer'
                        }`}
                      >
                        <span className="text-left">
                          {form.equipements.length === 0
                            ? '-- Sélectionnez --'
                            : `${form.equipements.length} équipement(s)`}
                        </span>
                        <ChevronDown className={`w-4 h-4 transition-transform ${equipmentDropdownOpen ? 'rotate-180' : ''}`} />
                      </button>

                      {/* Dropdown Menu */}
                      {equipmentDropdownOpen && form.client && (
                        <div className="absolute z-10 top-full left-0 right-0 mt-1 bg-savia-surface border border-savia-border rounded-lg shadow-lg overflow-hidden">
                          <div className="max-h-64 overflow-y-auto divide-y divide-savia-border/40">
                            {equipsByClient.length === 0 ? (
                              <div className="px-4 py-3 text-xs text-savia-text-muted italic">
                                {editingContrat
                                  ? 'Aucun équipement disponible pour ce client'
                                  : allEquipsByClient.length > 0
                                    ? 'Tous les équipements de ce client ont déjà un contrat'
                                    : 'Aucun équipement disponible pour ce client'}
                              </div>
                            ) : (
                              equipsByClient.map((e: any) => (
                                <label
                                  key={e.id}
                                  className={`flex items-center gap-3 cursor-pointer px-4 py-3 hover:bg-savia-surface-hover transition-colors ${
                                    form.equipement_ids.includes(Number(e.id)) ? 'bg-savia-accent/10' : ''
                                  }`}
                                >
                                  <input
                                    type="checkbox"
                                    className="accent-cyan-400 w-4 h-4 shrink-0"
                                    checked={form.equipement_ids.includes(Number(e.id))}
                                    onChange={() => toggleEquipment(e)}
                                  />
                                  <div className="flex-1 min-w-0">
                                    <div className="text-sm font-semibold text-savia-text">{e.Nom || e.nom}</div>
                                    <div className="text-xs text-savia-text-muted">
                                      {[e.Fabricant || e.fabricant, e.Modele || e.modele, e.NumSerie || e.Num_Serie || e.num_serie ? `SN: ${e.NumSerie || e.Num_Serie || e.num_serie}` : '']
                                        .filter(Boolean).join(' · ')}
                                    </div>
                                  </div>
                                </label>
                              ))
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                    
                    {!form.client && <p className="text-xs text-savia-text-muted mt-1">Sélectionnez d'abord un client</p>}
                  </div>

                  {/* Équipements sélectionnés : pleine largeur et deux colonnes pour éviter une longue liste verticale. */}
                  {form.equipements.length > 0 && (
                    <div className="md:col-span-2 grid grid-cols-1 gap-2 md:grid-cols-2">
                      {form.equipements.map((equip, index) => {
                        const selectedEquipment = equips.find(e => Number(e.id) === form.equipement_ids[index]);
                        const selectedMeta = selectedEquipment
                          ? [selectedEquipment.Fabricant || selectedEquipment.fabricant, selectedEquipment.Modele || selectedEquipment.modele,
                            selectedEquipment.NumSerie || selectedEquipment.Num_Serie || selectedEquipment.num_serie
                              ? `SN: ${selectedEquipment.NumSerie || selectedEquipment.Num_Serie || selectedEquipment.num_serie}` : '']
                              .filter(Boolean).join(' · ')
                          : '';
                        return (
                          <div
                            key={`${equip}-${form.equipement_ids[index] || index}`}
                            className="flex min-w-0 items-center gap-2 rounded-lg border border-savia-accent/30 bg-savia-accent/10 px-3 py-2 text-savia-accent"
                          >
                            <Wrench className="h-4 w-4 shrink-0" />
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-semibold" title={equip}>{equip}</p>
                              {selectedMeta && <p className="truncate text-xs text-savia-text-muted" title={selectedMeta}>{selectedMeta}</p>}
                            </div>
                            <button
                              type="button"
                              onClick={() => removeEquipment(index)}
                              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full hover:bg-savia-accent/20 transition-colors"
                              aria-label={`Retirer ${equip}`}
                            >
                              <X className="h-3 w-3" />
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {/* === SECTION: Contrat === */}
              <div>
                <div className={SECTION_TITLE}>
                  <FileText className="w-4 h-4 text-savia-accent" /> Détails du Contrat
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className={LABEL}>Type de contrat</label>
                    <select className={INPUT} value={form.type_contrat} onChange={e => {
                      const type = e.target.value;
                      setForm(current => ({
                        ...current,
                        type_contrat: type,
                        // Le modèle « Pièces uniquement » active d'emblée la
                        // sélection des pièces et de leurs quotas.
                        avec_pieces: type === 'Pièces uniquement' ? true : current.avec_pieces,
                      }));
                    }}>
                      {!TYPES_CONTRAT.includes(form.type_contrat) && (
                        <option value={form.type_contrat}>{form.type_contrat} (ancien modèle)</option>
                      )}
                      {TYPES_CONTRAT.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={LABEL}>Statut</label>
                    <select className={INPUT} value={form.statut} onChange={e => set('statut', e.target.value)}>
                      {['Actif', 'Suspendu', 'Expiré'].map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={LABEL}>Date début</label>
                    <ContractDateInput value={form.date_debut} onChange={value => setForm(current => ({
                      ...current,
                      date_debut: value,
                      // Tant que la première maintenance n'a pas été modifiée,
                      // elle suit naturellement le nouveau début du contrat.
                      date_premiere_maintenance: current.date_premiere_maintenance === current.date_debut
                        ? value
                        : current.date_premiere_maintenance,
                    }))} />
                  </div>
                  <div>
                    <label className={LABEL}>Date fin</label>
                    <ContractDateInput value={form.date_fin} onChange={value => set('date_fin', value)} />
                  </div>
                  <div className="md:col-span-2">
                    <label className={LABEL}>Date de signature <span className="normal-case font-normal">(optionnelle)</span></label>
                    <ContractDateInput value={form.date_signature} onChange={value => set('date_signature', value)} />
                  </div>
                  <div className="md:col-span-2 rounded-lg border border-savia-accent/20 bg-savia-accent/5 px-3 py-2 text-sm">
                    {formDuration ? (
                      <span className="text-savia-text-muted">Durée indicative : <strong className="text-savia-accent">{formDuration}</strong></span>
                    ) : (
                      <span className="text-amber-500">Sélectionnez une date de fin postérieure à la date de début.</span>
                    )}
                  </div>
                  <div>
                    <label className={LABEL}>SLA Réponse (heures)</label>
                    <input type="text" inputMode="numeric" className={INPUT} value={form.sla_temps_reponse_h}
                      onChange={e => set('sla_temps_reponse_h', Math.min(240, Math.max(0, Number(e.target.value) || 0)))} />
                    <p className="text-xs text-savia-text-muted mt-1">0h = aucun engagement SLA de réponse</p>
                  </div>
                  <div>
                    <label className={LABEL}>Montant annuel (TND)</label>
                    <input type="text" inputMode="decimal" className={INPUT} value={form.montant} placeholder="0"
                      onChange={e => set('montant', Math.max(0, Number(e.target.value.replace(',', '.')) || 0))} />
                  </div>
                </div>
              </div>

              {/* === SECTION: Pièce jointe === */}
              <div>
                <div className={SECTION_TITLE}>
                  <Paperclip className="w-4 h-4 text-savia-accent" /> Pièce jointe du contrat
                </div>
                <div className="rounded-xl border border-dashed border-savia-border bg-savia-surface-hover/30 p-4 space-y-3">
                  <input
                    ref={contractFileInputRef}
                    type="file"
                    multiple
                    accept="image/jpeg,image/png,image/webp,application/pdf,.jpg,.jpeg,.png,.webp,.pdf"
                    className="hidden"
                    onChange={e => { chooseContractAttachments(e.target.files || []); e.currentTarget.value = ''; }}
                  />
                  <input
                    ref={contractCameraInputRef}
                    type="file"
                    accept="image/*"
                    capture="environment"
                    className="hidden"
                    onChange={e => { chooseContractAttachments(e.target.files || []); e.currentTarget.value = ''; }}
                  />
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => contractCameraInputRef.current?.click()} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold text-white bg-savia-accent hover:opacity-90 transition-all cursor-pointer">
                      <Camera className="w-4 h-4" /> Prendre une photo
                    </button>
                    <button type="button" onClick={() => contractFileInputRef.current?.click()} className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-semibold text-savia-text border border-savia-border hover:bg-savia-surface-hover transition-all cursor-pointer">
                    <Paperclip className="w-4 h-4" /> Choisir des images ou PDF
                  </button>
                </div>
                  {contractAttachments.length > 0 ? (
                    <div className="space-y-2">
                      {contractAttachments.map((attachment, index) => (
                        <div key={`${attachment.name}-${index}`} className="flex items-center justify-between gap-3 rounded-lg bg-savia-accent/10 border border-savia-accent/20 px-3 py-2">
                          <div className="min-w-0">
                            <p className="text-sm font-semibold truncate">{attachment.name}</p>
                            <p className="text-xs text-savia-text-muted">{(attachment.size / 1024 / 1024).toFixed(2)} Mo · sera enregistré avec le contrat</p>
                          </div>
                          <button type="button" onClick={() => removeContractAttachment(index)} className="p-1.5 rounded-lg text-savia-text-muted hover:text-red-400 hover:bg-red-500/10 cursor-pointer" aria-label="Retirer la pièce jointe">
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : editingContrat?.fichiers?.length ? (
                    <p className="text-xs text-savia-text-muted">{editingContrat.fichiers.length} fichier(s) déjà joint(s). Les fichiers sélectionnés seront ajoutés.</p>
                  ) : (
                    <p className="text-xs text-savia-text-muted">Formats acceptés : JPG, PNG, WEBP ou PDF · taille maximale : 20 Mo par fichier · 10 fichiers maximum.</p>
                  )}
                </div>
              </div>

              {/* === SECTION: Pièces === */}
              <div>
                <div className={SECTION_TITLE}>
                  <Package className="w-4 h-4 text-savia-accent" /> Pièces de Rechange
                </div>
                <label className="flex items-center gap-3 cursor-pointer group mb-3">
                  <div onClick={() => set('avec_pieces', !form.avec_pieces)}
                    className={`w-5 h-5 rounded flex items-center justify-center border-2 transition-all ${form.avec_pieces ? 'bg-savia-accent border-savia-accent' : 'border-savia-border group-hover:border-savia-accent/60'}`}>
                    {form.avec_pieces && <CheckSquare className="w-3 h-3 text-white" />}
                  </div>
                  <span className="text-sm font-semibold">Pièces couvertes par le contrat</span>
                </label>
                {form.avec_pieces && (
                  <div className="space-y-3 mt-2">
                    <p className="text-xs text-savia-text-muted">Sélectionnez les pièces couvertes et définissez un quota pour la durée du contrat :</p>
                    <div className="border border-savia-border rounded-xl overflow-hidden">
                      <div className="max-h-64 overflow-y-auto divide-y divide-savia-border">
                        {filteredPieces.length === 0 ? (
                          <p className="text-xs text-savia-text-muted p-3">Aucune pièce disponible.</p>
                        ) : filteredPieces.map((p: any) => {
                          const ref = p.reference || String(p.id || Math.random());
                          const dsg = p.designation || p.reference || '—';
                          const sel = form.pieces_selectionnees.find(s => s.ref === ref);
                          return (
                            <div key={ref} className={`transition-colors ${sel ? 'bg-savia-accent/5' : 'bg-savia-surface-hover/30'}`}>
                              <label className="flex items-center gap-3 cursor-pointer px-3 py-2.5 hover:bg-savia-surface-hover">
                                <input type="checkbox" className="accent-cyan-400 w-4 h-4 shrink-0"
                                  checked={!!sel}
                                  onChange={() => togglePiece(ref, dsg)} />
                                <div className="flex-1 min-w-0">
                                  <div className="text-sm font-bold text-[#2F4156] truncate">{dsg}</div>
                                  <div className="text-[10px] font-mono text-savia-text-muted">{ref}</div>
                                </div>
                                <div className="text-right shrink-0">
                                  <div className="text-sm font-bold text-[#2F4156]">{p.stock_actuel}</div>
                                  <div className="text-[10px] text-savia-text-dim">en stock</div>
                                </div>
                              </label>
                              {sel && (
                                <div className="flex items-center gap-2 px-10 pb-2.5">
                                  <span className="text-xs text-savia-text-muted shrink-0">Quota contrat :</span>
                                  <input type="number" min={1} value={sel.quota}
                                    className="w-20 text-sm font-bold border-2 border-savia-accent/40 rounded-lg px-2 py-1.5 bg-savia-surface-hover text-savia-text outline-none focus:border-savia-accent"
                                    style={{ appearance: 'textfield' }}
                                    onChange={e => setPieceQuota(ref, Number(e.target.value))} />
                                  <span className="text-xs text-savia-text-muted">unités sur la durée du contrat</span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    {form.pieces_selectionnees.length > 0 && (
                      <p className="text-xs font-semibold text-savia-accent">
                        {form.pieces_selectionnees.length} pièce(s) sélectionnée(s) — quota total : {form.pieces_selectionnees.reduce((a, b) => a + b.quota, 0)} unités
                      </p>
                    )}
                  </div>
                )}
              </div>

              {/* === SECTION: Rappel & Maintenance === */}
              <div>
                <div className={SECTION_TITLE}>
                  <Bell className="w-4 h-4 text-savia-accent" /> Rappels &amp; Maintenance
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className={LABEL}>Rappel avant expiration</label>
                    <div className="grid grid-cols-2 gap-2">
                      <input type="text" inputMode="numeric"
                        className="w-full border-2 border-savia-accent/40 rounded-lg px-3 py-2 bg-savia-surface-hover text-savia-text font-bold outline-none focus:border-savia-accent"
                        value={form.rappel_avant}
                        onChange={e => set('rappel_avant', Math.min(365, Math.max(1, Number(e.target.value) || 1)))} />
                      <select className={INPUT} value={form.rappel_unite} onChange={e => set('rappel_unite', e.target.value)}>
                        <option value="jours">jours</option>
                        <option value="mois">mois</option>
                      </select>
                    </div>
                  </div>
                  <div>
                    <label className={LABEL}>Récurrence maintenance</label>
                    <select className={INPUT} value={form.recurrence_maintenance} onChange={e => set('recurrence_maintenance', e.target.value)}>
                      {RECURRENCES.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={LABEL}>Date première maintenance</label>
                    <ContractDateInput value={form.date_premiere_maintenance}
                      onChange={value => set('date_premiere_maintenance', value)} />
                    <p className="mt-1 text-xs text-savia-text-muted">La première intervention sera créée à cette date.</p>
                  </div>
                  <div>
                    <label className={LABEL}>Date dernière maintenance</label>
                    <ContractDateInput
                      value={form.date_derniere_maintenance}
                      onChange={value => set('date_derniere_maintenance', value)}
                      disabled={!isHistoricalContract}
                    />
                    <p className="mt-1 text-xs text-savia-text-muted">
                      {isHistoricalContract
                        ? 'La suite du planning partira après cette maintenance.'
                        : 'Disponible si le début du contrat remonte à plus d’un mois.'}
                    </p>
                  </div>
                </div>
              </div>

              {/* === SECTION: Conditions & Notes === */}
              <div>
                <div className={SECTION_TITLE}>
                  <StickyNote className="w-4 h-4 text-savia-accent" /> Conditions &amp; Notes
                </div>
                <div className="space-y-3">
                  <div>
                    <label className={LABEL}>Conditions du contrat</label>
                    <textarea className={`${INPUT} resize-none`} rows={3} placeholder="Pénalités, exclusions, engagements..."
                      value={form.conditions} onChange={e => set('conditions', e.target.value)} />
                  </div>
                  <div>
                    <label className={LABEL}>Notes internes</label>
                    <textarea className={`${INPUT} resize-none`} rows={3} placeholder="Remarques, contacts, informations complémentaires..."
                      value={form.notes} onChange={e => set('notes', e.target.value)} />
                  </div>
                </div>
              </div>

              {pendingAttachmentUpload && (
                <div className="p-3 rounded-lg border border-amber-400/30 bg-amber-500/10 text-sm text-amber-200">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                    <div className="space-y-2">
                      <p className="font-semibold">Le contrat #{pendingAttachmentUpload.contractId} a bien été sauvegardé, mais l'envoi de la pièce jointe a échoué.</p>
                      <p className="text-xs text-amber-100/80">Réessayez l'envoi ci-dessous. Le contrat ne sera pas recréé.</p>
                      <button
                        type="button"
                        onClick={retryAttachmentUpload}
                        disabled={isSaving}
                        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-amber-600 hover:bg-amber-500 disabled:opacity-50 cursor-pointer"
                      >
                        {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCcw className="w-3.5 h-3.5" />}
                        Réessayer l'envoi
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Save message */}
              {saveMsg && (
                <div className={`p-3 rounded-lg text-sm font-semibold whitespace-pre-line ${saveMsg.includes('✅') ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                  {saveMsg}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-savia-border">
              <button onClick={() => setShowModal(false)} disabled={isSaving}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover transition-all cursor-pointer">
                Annuler
              </button>
              {editingContrat && !pendingAttachmentUpload && (
                <button
                  type="button"
                  onClick={() => handleSave(true)}
                  disabled={isSaving || !form.client}
                  title="Remplace les maintenances automatiques planifiées selon les dates actuelles, sans toucher aux maintenances clôturées."
                  className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-bold text-savia-accent border border-savia-accent/40 hover:bg-savia-accent/10 transition-all cursor-pointer disabled:opacity-50"
                >
                  <RefreshCcw className="w-4 h-4" />
                  Régénérer le planning
                </button>
              )}
              <button onClick={() => handleSave()} disabled={isSaving || (!pendingAttachmentUpload && !form.client)}
                className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-savia-accent to-blue-600 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-cyan-500/20 disabled:opacity-50">
                {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                {isSaving ? 'Enregistrement...' : pendingAttachmentUpload ? 'Réessayer l’envoi' : editingContrat ? 'Mettre à jour' : 'Créer le contrat'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ============== DELETE CONFIRMATION MODAL ============== */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setDeleteConfirm(null)}>
          <div className="glass rounded-2xl w-full max-w-md shadow-2xl" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between p-5 border-b border-savia-border">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-red-500" />
                </div>
                <div>
                  <h2 className="font-bold text-lg text-red-500">Supprimer le contrat</h2>
                  <p className="text-xs text-savia-text-muted">Cette action est irréversible</p>
                </div>
              </div>
              <button onClick={() => setDeleteConfirm(null)} className="p-2 rounded-lg hover:bg-savia-surface-hover text-savia-text-muted hover:text-savia-text transition-all cursor-pointer">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="p-6 space-y-4">
              <div className="bg-red-500/10 rounded-lg p-4 border border-red-500/20">
                <p className="text-sm text-savia-text">
                  Êtes-vous sûr de vouloir supprimer le contrat <span className="font-bold text-red-400">#{deleteConfirm.contratId}</span> pour <span className="font-bold">{deleteConfirm.contratName}</span>?
                </p>
              </div>
              
              <div className="bg-amber-500/10 rounded-lg p-3 border border-amber-500/20">
                <div className="flex gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                  <div className="text-xs text-amber-600">
                    <p className="font-semibold mb-1">⚠️ Cette suppression inclura:</p>
                    <ul className="list-disc list-inside space-y-0.5">
                      <li>Le contrat lui-même</li>
                      <li>Tous les équipements associés</li>
                      <li>Toutes les maintenances planifiées</li>
                      <li>Les interventions liées à ce contrat</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-savia-border">
              <button 
                onClick={() => setDeleteConfirm(null)} 
                disabled={isDeleting}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-savia-text-muted hover:text-savia-text hover:bg-savia-surface-hover transition-all cursor-pointer disabled:opacity-50">
                Annuler
              </button>
              <button 
                onClick={handleDeleteContrat} 
                disabled={isDeleting}
                className="flex items-center gap-2 px-6 py-2.5 rounded-lg font-bold text-white bg-gradient-to-r from-red-600 to-red-700 hover:opacity-90 transition-all cursor-pointer shadow-lg shadow-red-500/20 disabled:opacity-50">
                {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <X className="w-4 h-4" />}
                {isDeleting ? 'Suppression...' : 'Supprimer définitivement'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
