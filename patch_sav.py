import re, sys

path = r"frontend/src/app/(authenticated)/sav/page.tsx"
with open(path, encoding='utf-8') as f:
    src = f.read()

# 1. Ajouter l'import FichesSigneesTab after api import line
src = src.replace(
    "import { interventions, ai, equipements, techniciens as techApi } from '@/lib/api';",
    "import { interventions, ai, equipements, techniciens as techApi } from '@/lib/api';\nimport { FichesSigneesTab } from './FichesSigneesTab';"
)

# 2. Ajouter Camera, Upload, XCircle dans les imports lucide si absents
if 'Camera' not in src:
    src = src.replace(
        "Filter, CalendarDays, CalendarRange",
        "Filter, CalendarDays, CalendarRange, Camera, Eye, ImageOff, Upload, XCircle"
    )

# 3. Ajouter states ficheFile et fiches après activeTab state
src = src.replace(
    "  const [activeTab, setActiveTab] = useState(0);\n",
    "  const [activeTab, setActiveTab] = useState(0);\n  const [ficheFile, setFicheFile] = useState<File | null>(null);\n  const [fiches, setFiches] = useState<any[]>([]);\n"
)

# 4. Ajouter useEffect fiches après le loadData useEffect
src = src.replace(
    "  useEffect(() => { loadData(); }, [loadData]);\n",
    "  useEffect(() => { loadData(); }, [loadData]);\n\n  useEffect(() => {\n    interventions.listFiches().then(setFiches).catch(() => {});\n  }, []);\n"
)

# 5. Ajouter upload fiche dans handleStatusChange après update() call and before setShowStatusModal
old_close = "      setShowStatusModal(false);\n      setSelectedIntervention(null);\n      await loadData();\n    } catch (err) {\n      console.error(\"Status update failed\", err);"
new_close = """      // Upload fiche photo si cloture + fichier selectionne
      if (statusForm.statut.toLowerCase().includes('tur') && ficheFile) {
        try { await interventions.uploadFiche(selectedIntervention.id, ficheFile); }
        catch (fe) { console.error('Erreur upload fiche:', fe); }
      }
      setFicheFile(null);
      setShowStatusModal(false);
      setSelectedIntervention(null);
      await loadData();
      interventions.listFiches().then(setFiches).catch(() => {});
    } catch (err) {
      console.error("Status update failed", err);"""
src = src.replace(old_close, new_close)

# 6. Ajouter tab Fiches Signees dans tableau tabs
src = src.replace(
    "    { icon: <Sparkles className=\"w-4 h-4\" />, label: 'Analyse IA' },\n  ];",
    "    { icon: <Sparkles className=\"w-4 h-4\" />, label: 'Analyse IA' },\n    { icon: <Camera className=\"w-4 h-4\" />, label: 'Fiches Signées' },\n  ];"
)

# 7. Ajouter upload fiche dans modal (apres la zone Duree, avant les boutons)
# On trouve la div de Durée et on ajoute après
duree_block = '          <div><label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1"><Timer className="w-3.5 h-3.5" /> Durée (min)</label><input type="number" className={INPUT_CLS} value={statusForm.duree_minutes} onChange={e => setStatusForm({...statusForm, duree_minutes: e.target.value})} /></div>'
upload_block = '''          {statusForm.statut.toLowerCase().includes('tur') && (
            <div>
              <label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1">
                <Camera className="w-3.5 h-3.5" /> Photo fiche signée <span className="text-xs opacity-60">(optionnel)</span>
              </label>
              <div className="border-2 border-dashed border-savia-border/50 rounded-lg p-4 text-center cursor-pointer hover:border-savia-accent/50 transition-colors"
                onClick={() => document.getElementById('fiche-upload-modal')?.click()}>
                {ficheFile ? (
                  <div className="flex items-center justify-center gap-2 text-green-400">
                    <CheckCircle className="w-4 h-4" />
                    <span className="text-sm font-medium">{ficheFile.name}</span>
                    <button onClick={e => { e.stopPropagation(); setFicheFile(null); }} className="ml-2 text-red-400 hover:text-red-300">
                      <XCircle className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <div className="text-savia-text-muted">
                    <Upload className="w-6 h-6 mx-auto mb-1 opacity-50" />
                    <p className="text-xs">Cliquez pour sélectionner une photo (JPG, PNG, PDF)</p>
                  </div>
                )}
              </div>
              <input id="fiche-upload-modal" type="file" accept="image/*,.pdf" className="hidden"
                onChange={e => setFicheFile(e.target.files?.[0] || null)} />
            </div>
          )}'''
if duree_block in src:
    src = src.replace(duree_block, duree_block + '\n' + upload_block)

# 8. Remplacer l'onglet 5 entier (SectionCard) par le composant FichesSigneesTab
# Trouver et remplacer le bloc onglet 5
onglet5_start = '      {/* === ONGLET 5 : FICHES SIGNÉES === */}\n      {activeTab === 5 && ('
onglet5_new = '      {/* === ONGLET 5 : FICHES SIGNÉES === */}\n      {activeTab === 5 && (\n        <FichesSigneesTab fiches={fiches} setFiches={setFiches} />\n      )}'

# Find start position
idx = src.find(onglet5_start)
if idx == -1:
    print("ERROR: Could not find onglet5 start marker")
    sys.exit(1)

# Find matching closing paren - count parens from after 'activeTab === 5 && ('
# We need to find the closing ')}' for '{activeTab === 5 && ('
after = src[idx + len(onglet5_start):]
depth = 1  # we're inside the outer && (
pos = 0
while pos < len(after) and depth > 0:
    ch = after[pos]
    if ch == '(':
        depth += 1
    elif ch == ')':
        depth -= 1
    pos += 1

# pos is now right after the closing paren, next char should be }
end_idx = idx + len(onglet5_start) + pos
# include the closing }
if after[pos] == '}':
    end_idx += 1

src = src[:idx] + onglet5_new + '\n' + src[end_idx:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(src)

print("Done! Patches applied successfully.")

# Verify key sections exist
checks = [
    "FichesSigneesTab",
    "ficheFile",
    "fiches",
    "listFiches",
    "Fiches Signées",
    "uploadFiche",
]
for c in checks:
    if c in src:
        print(f"  ✓ {c}")
    else:
        print(f"  ✗ MISSING: {c}")
