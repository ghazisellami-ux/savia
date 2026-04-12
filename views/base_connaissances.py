# ==========================================
# 📚 PAGE BASE DE CONNAISSANCES
# ==========================================
import streamlit as st
import pandas as pd
import time
from database import lire_base, lire_feuille
from importers import importer_donnees_structurees, importer_pdf, importer_docx
from config import EXCEL_PATH, SHEET_CODES, SHEET_SOLUTIONS


def afficher_base_connaissances():
    """Page de gestion de la base de connaissances."""

    st.title("📚 Base de Connaissances")
    st.markdown("---")

    # ============ IMPORTS ============
    st.subheader("📥 Importer des données")

    tab_xls, tab_pdf, tab_docx = st.tabs(["📊 Excel / CSV", "📄 PDF Technique", "📝 Word (.docx)"])

    with tab_xls:
        st.markdown("Importez un fichier Excel ou CSV contenant des codes d'erreur.")
        st.caption(
            "Le système détecte automatiquement les colonnes : "
            "Code, Message, Type, Cause, Solution, Priorité"
        )

        upload_xls = st.file_uploader(
            "Choisir un fichier", type=["csv", "xlsx"],
            key="upload_xls", label_visibility="collapsed"
        )

        if upload_xls:
            st.info(f"📎 Fichier : **{upload_xls.name}** ({upload_xls.size / 1024:.1f} KB)")
            if st.button("💾 Intégrer dans la base", key="btn_import_xls"):
                with st.spinner("Import en cours..."):
                    nb = importer_donnees_structurees(upload_xls, EXCEL_PATH)
                if nb:
                    st.success(f"✅ **{nb} code(s)** importé(s) avec succès !")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Aucun code importé. Vérifiez le format du fichier.")

    with tab_pdf:
        st.markdown("Extrayez les codes d'erreur depuis un **manuel technique PDF**.")
        st.caption("L'IA analyse chaque page pour trouver les codes d'erreur et solutions.")

        upload_pdf = st.file_uploader(
            "Choisir un PDF", type=["pdf"],
            key="upload_pdf", label_visibility="collapsed"
        )

        if upload_pdf:
            st.info(f"📎 Fichier : **{upload_pdf.name}** ({upload_pdf.size / 1024:.1f} KB)")

            col_p1, col_p2 = st.columns(2)
            page_debut = col_p1.number_input("Page de début", min_value=1, value=1)
            page_fin = col_p2.number_input("Page de fin", min_value=1, value=5)

            if st.button("🧠 Extraire avec l'IA", key="btn_import_pdf", type="primary"):
                nb = importer_pdf(upload_pdf, page_debut, page_fin, EXCEL_PATH)
                if nb:
                    st.success(f"✅ **{nb} code(s)** extraits du PDF !")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Aucun code trouvé dans ces pages.")

    with tab_docx:
        st.markdown("Extrayez les codes d'erreur depuis un **document Word (.docx)**.")
        st.caption("L'IA analyse le texte et les tableaux pour identifier les codes d'erreur, causes et solutions.")

        upload_docx = st.file_uploader(
            "Choisir un fichier Word", type=["docx"],
            key="upload_docx", label_visibility="collapsed"
        )

        if upload_docx:
            st.info(f"📎 Fichier : **{upload_docx.name}** ({upload_docx.size / 1024:.1f} KB)")

            if st.button("🧠 Extraire avec l'IA", key="btn_import_docx", type="primary"):
                nb = importer_docx(upload_docx, EXCEL_PATH)
                if nb:
                    st.success(f"✅ **{nb} code(s)** extraits du document Word !")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.warning("Aucun code trouvé dans ce document.")
    # ============ RESTAURATION DEPUIS EXCEL ============
    import os
    from config import BASE_DIR
    candidates = [
        EXCEL_PATH,
        os.path.join(BASE_DIR, "knowledge_base.xlsx"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge_base.xlsx"),
        "knowledge_base.xlsx",
    ]
    excel_file = None
    for c in candidates:
        if os.path.exists(c):
            excel_file = c
            break

    if excel_file:
        with st.expander("🔄 Restaurer / Réimporter depuis knowledge_base.xlsx"):
            st.info(f"📄 Fichier trouvé : **{os.path.basename(excel_file)}** ({os.path.getsize(excel_file) / 1024:.1f} KB)")
            st.caption("Cliquez pour réimporter les codes et solutions depuis le fichier Excel local.")
            if st.button("🔄 Purger et réimporter", type="primary", key="btn_restore_excel"):
                with st.spinner("Purge et réimportation en cours..."):
                    from db_engine import purger_et_reimporter_excel
                    nb = purger_et_reimporter_excel(excel_file)
                if nb:
                    st.success(f"✅ **{nb} entrées** restaurées avec succès !")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Erreur lors de la migration. Vérifiez les logs Streamlit.")

    # ============ CONSULTATION ============
    st.markdown("---")
    st.subheader("🔍 Consultation de la base")

    hex_db, sol_db = lire_base()

    if not hex_db and not sol_db:
        st.info("📭 La base de connaissances est vide.")
        st.warning("Les codes et solutions n'ont pas été trouvés dans la base de données.")

        # Bouton de restauration depuis Excel
        import os
        from config import BASE_DIR
        # Essayer plusieurs chemins possibles
        candidates = [
            EXCEL_PATH,
            os.path.join(BASE_DIR, "knowledge_base.xlsx"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge_base.xlsx"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "knowledge_base.xlsx"),
            "knowledge_base.xlsx",
        ]
        excel_file = None
        for c in candidates:
            if os.path.exists(c):
                excel_file = c
                break

        if excel_file:
            st.info(f"📄 Fichier **knowledge_base.xlsx** trouvé ({os.path.getsize(excel_file) / 1024:.1f} KB)")
            if st.button("🔄 Restaurer depuis knowledge_base.xlsx", type="primary"):
                with st.spinner("Migration en cours..."):
                    from database import migrer_depuis_excel
                    nb = migrer_depuis_excel(excel_file)
                if nb:
                    st.success(f"✅ **{nb} entrées** restaurées avec succès !")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Erreur lors de la migration. Vérifiez les logs.")
        else:
            st.error(f"Fichier knowledge_base.xlsx introuvable. Chemins testés : {candidates}")
            st.info("Importez des données via les onglets ci-dessus.")
        return

    # Recherche
    recherche = st.text_input(
        "🔎 Rechercher un code ou mot-clé",
        placeholder="Ex: 4A01, tube, calibration..."
    )

    # Onglets codes / solutions
    tab_codes, tab_solutions = st.tabs(["📋 Codes d'erreur", "💡 Solutions"])

    with tab_codes:
        df_codes = lire_feuille(EXCEL_PATH, SHEET_CODES)
        if not df_codes.empty:
            if recherche:
                mask = df_codes.apply(
                    lambda row: recherche.lower() in " ".join(row.astype(str)).lower(),
                    axis=1
                )
                df_codes = df_codes[mask]

            st.caption(f"{len(df_codes)} code(s) dans la base")
            st.dataframe(df_codes, use_container_width=True, hide_index=True)
        else:
            st.info("Aucun code enregistré.")

    with tab_solutions:
        df_sol = lire_feuille(EXCEL_PATH, SHEET_SOLUTIONS)
        if not df_sol.empty:
            if recherche:
                mask = df_sol.apply(
                    lambda row: recherche.lower() in " ".join(row.astype(str)).lower(),
                    axis=1
                )
                df_sol = df_sol[mask]

            st.caption(f"{len(df_sol)} solution(s) dans la base")
            st.dataframe(df_sol, use_container_width=True, hide_index=True)
        else:
            st.info("Aucune solution enregistrée.")

    # ============ STATISTIQUES ============
    st.markdown("---")
    st.subheader("📊 Statistiques de la base")

    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric("📋 Codes", len(hex_db))
    col_s2.metric("💡 Solutions", len(sol_db))

    # Types uniques
    types = set()
    for v in sol_db.values():
        types.add(v.get("Type", "?"))
    col_s3.metric("📁 Types", len(types))

    # ============ EXPORT ============
    st.markdown("---")
    with st.expander("📤 Exporter la base"):
        df_codes_export = lire_feuille(EXCEL_PATH, SHEET_CODES)
        df_sol_export = lire_feuille(EXCEL_PATH, SHEET_SOLUTIONS)

        if not df_codes_export.empty or not df_sol_export.empty:
            col_e1, col_e2 = st.columns(2)

            if not df_codes_export.empty:
                csv_codes = df_codes_export.to_csv(index=False).encode("utf-8")
                col_e1.download_button(
                    "📥 Télécharger Codes (CSV)",
                    csv_codes, "codes_erreur.csv",
                    "text/csv",
                )

            if not df_sol_export.empty:
                csv_sol = df_sol_export.to_csv(index=False).encode("utf-8")
                col_e2.download_button(
                    "📥 Télécharger Solutions (CSV)",
                    csv_sol, "solutions.csv",
                    "text/csv",
                )
