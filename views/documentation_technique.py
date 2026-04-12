# ==========================================
# 📄 PAGE DOCUMENTATION TECHNIQUE
# ==========================================
import streamlit as st
import base64
from db_engine import (
    lire_tous_documents_techniques,
    lire_document_technique_contenu,
    supprimer_document_technique,
)
import time


def page_documentation_technique():
    """Page de consultation de tous les documents techniques avec filtres."""

    st.title("📄 Documentation Technique")
    st.caption("Consultez et recherchez tous les documents techniques du parc d'équipements.")

    # Charger tous les documents
    all_docs = lire_tous_documents_techniques()

    if not all_docs:
        st.info("📭 Aucun document technique n'a été uploadé pour le moment.")
        st.markdown("**Pour ajouter un document :** allez dans *Parc Équipements* → sélectionnez un équipement → *✏️ Modifier* → uploadez un fichier.")
        return

    # --- Extraire les valeurs uniques pour les filtres ---
    fabricants = sorted(set(d.get("fabricant", "") or "" for d in all_docs if d.get("fabricant")))
    modeles = sorted(set(d.get("modele", "") or "" for d in all_docs if d.get("modele")))
    clients = sorted(set(d.get("client", "") or "" for d in all_docs if d.get("client")))
    types_eq = sorted(set(d.get("equipement_type", "") or "" for d in all_docs if d.get("equipement_type")))
    equipements = sorted(set(d.get("equipement_nom", "") or "" for d in all_docs if d.get("equipement_nom")))

    # --- Filtres ---
    st.markdown("### 🔍 Filtres")
    fc1, fc2, fc3, fc4 = st.columns(4)

    filtre_fabricant = fc1.selectbox("🏭 Fabricant", ["Tous"] + fabricants, key="doc_filtre_fab")
    filtre_modele = fc2.selectbox("📋 Modèle", ["Tous"] + modeles, key="doc_filtre_mod")
    filtre_client = fc3.selectbox("🏢 Client", ["Tous"] + clients, key="doc_filtre_cli")
    filtre_type = fc4.selectbox("🔬 Type", ["Tous"] + types_eq, key="doc_filtre_type")

    # Recherche par nom de fichier
    recherche = st.text_input("🔎 Rechercher par nom de fichier", key="doc_recherche",
                              placeholder="Ex: Manuel, Schema, guide...")

    # --- Appliquer les filtres ---
    filtered = all_docs
    if filtre_fabricant != "Tous":
        filtered = [d for d in filtered if d.get("fabricant") == filtre_fabricant]
    if filtre_modele != "Tous":
        filtered = [d for d in filtered if d.get("modele") == filtre_modele]
    if filtre_client != "Tous":
        filtered = [d for d in filtered if d.get("client") == filtre_client]
    if filtre_type != "Tous":
        filtered = [d for d in filtered if d.get("equipement_type") == filtre_type]
    if recherche:
        recherche_lower = recherche.lower()
        filtered = [d for d in filtered if recherche_lower in (d.get("nom_fichier", "") or "").lower()]

    st.markdown("---")

    # --- Résultats ---
    st.markdown(f"### 📄 {len(filtered)} document(s) trouvé(s)")

    if not filtered:
        st.warning("Aucun document ne correspond aux filtres sélectionnés.")
        return

    # Rôle utilisateur
    is_lecteur = st.session_state.get("role", "Lecteur") == "Lecteur"

    # Afficher les documents dans un tableau interactif
    for doc in filtered:
        nom_fichier = doc.get("nom_fichier", "?")
        equipement = doc.get("equipement_nom", "?")
        fabricant = doc.get("fabricant", "—")
        modele = doc.get("modele", "—")
        client = doc.get("client", "—")
        type_eq = doc.get("equipement_type", "—")
        date_ajout = str(doc.get("date_ajout", ""))[:10]
        doc_id = doc.get("id")

        # Déterminer l'icône selon l'extension
        ext = nom_fichier.rsplit(".", 1)[-1].lower() if "." in nom_fichier else ""
        icon_map = {"pdf": "📕", "doc": "📘", "docx": "📘", "xlsx": "📗", "png": "🖼️", "jpg": "🖼️", "jpeg": "🖼️"}
        icon = icon_map.get(ext, "📄")

        with st.container():
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 1, 1])
            c1.markdown(f"**{icon} {nom_fichier}**")
            c2.caption(f"🏥 {equipement} — {fabricant} {modele}")
            c3.caption(f"🏢 {client} | 📅 {date_ajout}")

            # Bouton télécharger
            doc_content = lire_document_technique_contenu(doc_id)
            if doc_content:
                c4.download_button(
                    "📥",
                    data=base64.b64decode(doc_content["contenu_base64"]),
                    file_name=nom_fichier,
                    key=f"dl_doctech_{doc_id}",
                )

            # Bouton supprimer (admin/technicien seulement)
            if not is_lecteur:
                if c5.button("🗑️", key=f"del_doctech_{doc_id}"):
                    supprimer_document_technique(doc_id)
                    st.success(f"✅ Document **{nom_fichier}** supprimé.")
                    time.sleep(0.5)
                    st.rerun()

        st.markdown("<hr style='margin:2px 0; border-color:rgba(148,163,184,0.1)'>", unsafe_allow_html=True)
