"""Equipment, catalogue, and technical-document routes."""

import base64

from api.runtime import (
    Body,
    Depends,
    HTTPException,
    Optional,
    Query,
    ajouter_equipement,
    ajouter_fabricant,
    ajouter_type_equipement_custom,
    ajouter_type_intervention_custom,
    app,
    db_lire_clients,
    EquipmentHasTechnicalDocumentsError,
    EquipmentLinkedToContractsError,
    get_db,
    lire_equipements,
    lire_fabricants,
    lire_modeles_equipement,
    ajouter_modele_equipement,
    lire_services_equipement,
    ajouter_service_equipement,
    lire_types_equipement_custom,
    lire_types_intervention_custom,
    log_audit,
    logger,
    modifier_equipement,
    lire_historique_statut_equipement,
    remettre_equipement_en_service,
    supprimer_equipement,
)
from api.security import (
    Depends,
    HTTPException,
    Optional,
    _check_create_permission,
    _verify_token,
    assert_resource_client_access,
    get_client_scope,
    resolve_client_scope,
    get_db,
)
from services.scheduled_jobs import (
    _df_to_records,
    get_db,
    lire_equipements,
    logger,
)
from controllers.auth_dashboard import (
    Depends,
    HTTPException,
    Optional,
    _get_client_filter,
    _verify_token,
    app,
    db_lire_clients,
    get_db,
    lire_equipements,
    log_audit,
    logger,
)
from services.file_security import decode_and_validate_base64


def _wrap_pdf_cell(pdf, text: str, width: float) -> str:
    """Wrap a PDF cell without dropping any part of its value.

    FPDF wraps at spaces, but a client name can also contain a long unbroken
    token (for example a legal suffix or an imported identifier). Splitting
    oversized tokens here keeps those values visible as well.
    """
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    content_width = max(1, width - 1.5)
    lines = []

    def split_token(token: str) -> list[str]:
        chunks = []
        current = ""
        for character in token:
            candidate = current + character
            if current and pdf.get_string_width(candidate) > content_width:
                chunks.append(current)
                current = character
            else:
                current = candidate
        return chunks + [current] if current else chunks

    for paragraph in value.split("\n") or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue

        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if pdf.get_string_width(candidate) <= content_width:
                current = candidate
                continue

            if current:
                lines.append(current)
            token_chunks = split_token(word)
            lines.extend(token_chunks[:-1])
            current = token_chunks[-1] if token_chunks else ""
        lines.append(current)

    return "\n".join(lines) or " "


@app.get("/api/equipements")
def get_equipements(client: Optional[str] = None, user: dict = Depends(_verify_token)):
    df = lire_equipements()
    # Priority: explicit ?client= param, then user's client filter
    client_filter = resolve_client_scope(user, client)
    if client_filter and not df.empty and "Client" in df.columns:
        df = df[df["Client"].astype(str).str.lower() == client_filter.lower()]
    return _df_to_records(df)


@app.post("/api/equipements/export-pdf")
def export_equipements_pdf(body: dict = Body(default={}), user: dict = Depends(_verify_token)):
    """Exporte les clients ou les equipements selon les filtres selectionnes."""
    from fastapi.responses import Response
    from controllers.report_helpers import SaviaPDF, _sanitize
    from datetime import datetime
    from io import BytesIO
    import base64 as _b64

    try:
        def value(row, *keys):
            for key in keys:
                item = row.get(key)
                if item is not None and str(item).strip():
                    return str(item).strip()
            return ""

        export_type = str(body.get("export_type") or "equipements").lower()
        if export_type == "clients":
            client_scope = resolve_client_scope(user, None)
            clients_df = db_lire_clients()
            equipment_df = lire_equipements()
            equipment_counts = {}
            for _, equipment in equipment_df.iterrows():
                client = value(equipment, "Client", "client").casefold()
                if client:
                    equipment_counts[client] = equipment_counts.get(client, 0) + 1

            rows = []
            for _, row in clients_df.iterrows():
                international = str(row.get("international") or "").lower() in ("true", "1", "yes")
                item = {
                    "client": value(row, "nom", "Nom"),
                    "code": value(row, "code_client", "CodeClient"),
                    "type": value(row, "type_client", "TypeClient"),
                    "region": "International" if international else value(row, "region", "Region"),
                    "ville": value(row, "ville", "Ville"),
                    "equipements": str(equipment_counts.get(value(row, "nom", "Nom").casefold(), 0)),
                    "contact": value(row, "contact", "Contact"),
                    "telephone": value(row, "telephone", "Telephone"),
                }
                if not item["client"]:
                    continue
                if client_scope and item["client"].casefold() != client_scope.casefold():
                    continue
                search = str(body.get("client_search") or "").strip().casefold()
                if search and search not in item["client"].casefold():
                    continue
                if body.get("client_type") and item["type"] != body.get("client_type"):
                    continue
                if body.get("client_region"):
                    if body.get("client_region") == "International" and item["region"] != "International":
                        continue
                    if body.get("client_region") != "International" and item["region"] != body.get("client_region"):
                        continue
                if body.get("client_ville") and item["ville"] != body.get("client_ville"):
                    continue
                rows.append(item)
            headers = ["Client", "Code", "Type", "Region", "Ville", "Equipements", "Contact", "Telephone"]
            # Give the client name more room while keeping the compact
            # columns sized for their short values and preserving the table
            # width on the landscape A4 page.
            col_widths = [77, 22, 24, 24, 24, 22, 45, 39]
            keys = ("client", "code", "type", "region", "ville", "equipements", "contact", "telephone")
            title = "LISTE DES CLIENTS"
            filter_pairs = (("Recherche", "client_search"), ("Type", "client_type"), ("Region", "client_region"), ("Ville", "client_ville"))
            report_filename = "clients"
        else:
            df = lire_equipements()
            requested_client = body.get("client") if body.get("client") not in (None, "", "Tous") else None
            client_scope = resolve_client_scope(user, requested_client)
            rows = []
            for _, row in df.iterrows():
                item = {
                    "client": value(row, "Client", "client") or "Centre Principal",
                    "equipement": value(row, "Nom", "nom"),
                    "num_serie": value(row, "NumSerie", "num_serie"),
                    "type": value(row, "Type", "type"),
                    "domaine": value(row, "Domaine", "domaine"),
                    "modele": " - ".join(filter(None, [value(row, "Fabricant", "fabricant"), value(row, "Modele", "modele")])),
                    "modele_filtre": value(row, "Modele", "modele"),
                    "statut": value(row, "Statut", "statut"),
                    "service": value(row, "Service", "service"),
                }
                if client_scope and item["client"].casefold() != client_scope.casefold():
                    continue
                for field in ("type", "domaine", "modele", "statut", "service", "client"):
                    selected = body.get(field)
                    candidate = item["modele_filtre"] if field == "modele" else item[field]
                    if selected not in (None, "", "Tous") and candidate != selected:
                        break
                else:
                    search = str(body.get("search") or "").strip().casefold()
                    serial = value(row, "NumSerie", "num_serie").casefold()
                    if not search or search in item["equipement"].casefold() or search in serial:
                        rows.append(item)
            headers = ["Client", "Equipement", "N° de serie", "Type", "Domaine", "Fabricant / modele", "Statut", "Service"]
            # Keep the table within the printable A4 landscape width while
            # prioritising the client name. Type and domain have enough room
            # for their usual labels to remain on one line; the equipment
            # column gives up the required space.
            col_widths = [62, 32, 28, 34, 34, 36, 28, 23]
            keys = ("client", "equipement", "num_serie", "type", "domaine", "modele", "statut", "service")
            title = "LISTE DES EQUIPEMENTS"
            filter_pairs = (("Recherche", "search"), ("Domaine", "domaine"), ("Type", "type"), ("Modele", "modele"), ("Statut", "statut"), ("Service", "service"), ("Client", "client"))
            report_filename = "equipements"

        if not rows:
            label = "client" if export_type == "clients" else "equipement"
            raise HTTPException(status_code=400, detail=f"Aucun {label} ne correspond aux filtres selectionnes")

        company_name = str(body.get("company_name") or "SAVIA")
        company_logo = str(body.get("company_logo") or "").strip()
        client_logo_io = None
        if company_logo.startswith("data:") and "," in company_logo:
            try:
                client_logo_io = BytesIO(_b64.b64decode(company_logo.split(",", 1)[1]))
            except Exception as logo_error:
                logger.warning(f"Logo societe invalide pour export {export_type}: {logo_error}")

        pdf = SaviaPDF(orientation="L", unit="mm", format="A4")
        pdf.set_header_data("/app/logo-savia.png", client_logo_io, company_name if company_name != "SAVIA" else "", "", report_title=title)
        pdf.set_auto_page_break(auto=True, margin=12)
        pdf.set_top_margin(pdf.HEADER_H + 8)
        pdf.add_page()

        def draw_table_header():
            pdf.set_font("Helvetica", "B", size=8)
            pdf.set_fill_color(1, 180, 188)
            pdf.set_text_color(255, 255, 255)
            for width, label in zip(col_widths, headers):
                pdf.cell(width, 8, _sanitize(label), border=1, align="C", fill=True)
            pdf.ln()

        pdf.set_text_color(30, 40, 55)
        pdf.set_font("Helvetica", "B", size=11)
        pdf.cell(0, 7, _sanitize(title), align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=8)
        pdf.set_text_color(100, 110, 120)
        pdf.cell(0, 5, _sanitize(f"Genere le {datetime.now().strftime('%d/%m/%Y %H:%M')}"), align="R", new_x="LMARGIN", new_y="NEXT")
        filter_labels = []
        for label, key in filter_pairs:
            selected = body.get(key)
            if selected not in (None, "", "Tous"):
                filter_labels.append(f"{label}: {selected}")
        pdf.set_font("Helvetica", "I", size=8)
        pdf.cell(0, 5, _sanitize("Filtres: " + (" | ".join(filter_labels) if filter_labels else "Aucun")), new_x="LMARGIN", new_y="NEXT")
        count_label = f"{len(rows)} client(s)" if export_type == "clients" else f"{len({row['client'] for row in rows})} client(s) - {len(rows)} equipement(s)"
        pdf.set_font("Helvetica", "B", size=9)
        pdf.set_text_color(1, 140, 150)
        pdf.cell(0, 7, _sanitize(count_label), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        draw_table_header()

        pdf.set_font("Helvetica", size=7.5)
        pdf.set_text_color(30, 30, 30)
        row_line_height = 6.5

        def draw_table_row(item):
            wrapped_values = [
                _wrap_pdf_cell(pdf, _sanitize(item[key]), width)
                for width, key in zip(col_widths, keys)
            ]
            row_height = row_line_height * max(value.count("\n") + 1 for value in wrapped_values)

            # Check the complete wrapped row before drawing it so its cells
            # never get split across pages and all borders stay aligned.
            if pdf.get_y() + row_height > pdf.page_break_trigger:
                pdf.add_page()
                draw_table_header()
                pdf.set_font("Helvetica", size=7.5)
                pdf.set_text_color(30, 30, 30)

            row_y = pdf.get_y()
            for width, key, text in zip(col_widths, keys, wrapped_values):
                cell_x = pdf.get_x()
                # Draw the full-height cell first. multi_cell() only draws
                # the height required by its own text, which would otherwise
                # leave the other cells shorter than the wrapped client cell.
                pdf.rect(cell_x, row_y, width, row_height)
                pdf.set_xy(cell_x, row_y)
                pdf.multi_cell(
                    width,
                    row_line_height,
                    text,
                    border=0,
                    align="C" if key == "equipements" else "L",
                    new_x="RIGHT",
                    new_y="TOP",
                )
            pdf.set_xy(pdf.l_margin, row_y + row_height)

        for item in rows:
            draw_table_row(item)

        pdf_bytes = pdf.output(dest="S")
        if isinstance(pdf_bytes, str):
            pdf_bytes = pdf_bytes.encode("latin-1")
        elif isinstance(pdf_bytes, bytearray):
            pdf_bytes = bytes(pdf_bytes)
        filename = f"{report_filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Erreur export PDF equipements: {exc}")
        raise HTTPException(status_code=500, detail="Impossible de generer le PDF des equipements")


@app.post("/api/equipements")
def create_equipement(body: dict, user: dict = Depends(_verify_token)):
    # Check permission
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins"
        )
    
    # A new row is always inserted. The repository returns the generated ID;
    # never resolve it again by (nom, client), because duplicate names are valid.
    equip_id = ajouter_equipement(body)
    nom = body.get("Nom", "")
    client = body.get("Client", "Centre Principal")
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({"equipement": nom, "client": client, "id": equip_id}, ensure_ascii=False)
    log_audit(username, "CREATE_EQUIPEMENT", details, "equipements")
    
    return {"ok": True, "id": equip_id}


@app.put("/api/equipements/{equip_id}")
def update_equipement(equip_id: int, body: dict, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    try:
        modifier_equipement(equip_id, body, change_par=user.get("sub", "unknown"))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({"equipement_id": equip_id, "changes": body}, ensure_ascii=False)
    log_audit(username, "UPDATE_EQUIPEMENT", details, "equipements")
    
    return {"ok": True}


@app.get("/api/equipements/{equip_id}/historique-statuts")
def get_historique_statuts_equipement(
    equip_id: int,
    user: dict = Depends(_verify_token),
):
    with get_db() as conn:
        assert_resource_client_access(conn, "equipement", equip_id, user)
    return lire_historique_statut_equipement(equip_id)


@app.put("/api/equipements/{equip_id}/remise-en-service")
def reactivate_equipement(equip_id: int, body: dict = Body(default={}), user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(
            status_code=403,
            detail="Cette action est réservée aux Responsables, Managers et Admins",
        )
    with get_db() as conn:
        assert_resource_client_access(conn, "equipement", equip_id, user)
    try:
        remettre_equipement_en_service(
            equip_id,
            change_par=user.get("sub", "unknown"),
            raison=body.get("raison") or "Remise en service manuelle",
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if "active" in message.lower() else 404
        raise HTTPException(status_code=status_code, detail=message)
    log_audit(
        user.get("sub", "unknown"),
        "REACTIVATE_EQUIPEMENT",
        f'{{"equipement_id": {equip_id}}}',
        "equipements",
    )
    return {"ok": True, "statut": "Opérationnel"}


@app.delete("/api/equipements/{equip_id}")
def delete_equipement(equip_id: int, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    # Get equipment name before deleting for logging
    try:
        with get_db() as conn:
            row = conn.execute("SELECT nom, client FROM equipements WHERE id = %s", (equip_id,)).fetchone()
            equip_name = dict(row)["nom"] if row else "Unknown"
    except:
        equip_name = "Unknown"
    
    try:
        deleted = supprimer_equipement(equip_id)
    except EquipmentHasTechnicalDocumentsError as exc:
        plural = "s" if exc.document_count > 1 else ""
        raise HTTPException(
            status_code=409,
            detail=(
                f"Impossible de supprimer cet équipement : {exc.document_count} document{plural} "
                f"technique{plural} lui est encore associé. Supprimez d'abord "
                "ses documents techniques."
            ),
        )
    except EquipmentLinkedToContractsError as exc:
        plural = "s" if exc.contract_count > 1 else ""
        raise HTTPException(
            status_code=409,
            detail=(
                f"Impossible de supprimer cet équipement : il est encore rattaché à "
                f"{exc.contract_count} contrat{plural}. Retirez-le d'abord des contrats concernés."
            ),
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="Équipement introuvable")
    
    # Log audit
    username = user.get("sub", "unknown")
    import json
    details = json.dumps({"equipement_id": equip_id, "equipement": equip_name}, ensure_ascii=False)
    log_audit(username, "DELETE_EQUIPEMENT", details, "equipements")
    
    return {"ok": True}


@app.post("/api/equipements/sync-region-ville")
def sync_region_ville(user: dict = Depends(_verify_token)):
    """Sync region and ville from clients to equipements based on client name. Admin operation."""
    if user.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Accès réservé aux administrateurs")
    try:
        from db_engine import _trigger_backup
        
        df_clients = db_lire_clients()
        df_eq = lire_equipements()
        
        if df_clients.empty or df_eq.empty:
            return {"ok": True, "updated": 0}
        
        logger.info(f"Starting sync: {len(df_clients)} clients, {len(df_eq)} equipements")
        
        # Use SQL UPDATE with JOIN to sync region/ville from clients to equipements (PostgreSQL)
        with get_db() as conn:
            cur = conn.cursor()
            
            # Update equipements where client name matches exactly
            cur.execute("""
                UPDATE equipements e
                SET region = c.region, ville = c.ville
                FROM clients c
                WHERE LOWER(e.client) = LOWER(c.nom)
            """)
            exact_matches = cur.rowcount
            conn.commit()
            
            logger.info(f"Exact matches: {exact_matches}")
            
            # For remaining equipements, try fuzzy matching
            # Get equipements that still have region='Nord' but don't have exact client match
            cur.execute("""
                SELECT e.id, e.client
                FROM equipements e
                LEFT JOIN clients c ON LOWER(e.client) = LOWER(c.nom)
                WHERE c.id IS NULL
            """)
            unmatched_equips = cur.fetchall()
            logger.info(f"Unmatched equipements: {len(unmatched_equips)}")
            
            # Try fuzzy matching for unmatched equipements
            fuzzy_matches = 0
            for equip_id, equip_client in unmatched_equips:
                # Find best match in clients table
                best_match = None
                best_score = 0
                
                for _, client_row in df_clients.iterrows():
                    client_nom = str(client_row.get("nom", "")).lower()
                    equip_client_lower = str(equip_client).lower()
                    
                    # Simple fuzzy match: check if one contains the other
                    if equip_client_lower in client_nom or client_nom in equip_client_lower:
                        best_match = client_row
                        break
                
                if best_match is not None:
                    region = str(best_match.get("region", "")).strip()
                    ville = str(best_match.get("ville", "")).strip()
                    
                    cur.execute(
                        "UPDATE equipements SET region = %s, ville = %s WHERE id = %s",
                        (region, ville, equip_id)
                    )
                    fuzzy_matches += 1
            
            conn.commit()
            logger.info(f"Fuzzy matches: {fuzzy_matches}")
            
            total_updated = exact_matches + fuzzy_matches
        
        logger.info(f"Sync completed: {total_updated} equipements updated")
        _trigger_backup()
        return {"ok": True, "updated": total_updated}
    except Exception as e:
        logger.error(f"Sync region/ville error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fabricants")
def get_fabricants(user: dict = Depends(_verify_token)):
    return lire_fabricants()


@app.post("/api/fabricants")
def post_fabricant(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    nom = payload.get("nom", "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    ajouter_fabricant(nom)
    return {"ok": True}


@app.get("/api/modeles-equipement")
def get_modeles_equipement(
    domaine: str = Query(""),
    type: str = Query(""),
    fabricant: str = Query(""),
    user: dict = Depends(_verify_token),
):
    return lire_modeles_equipement(domaine, type, fabricant)


@app.post("/api/modeles-equipement")
def post_modele_equipement(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    nom = str(payload.get("nom") or "").strip()
    domaine = str(payload.get("domaine") or "").strip()
    type_equipement = str(payload.get("type") or payload.get("type_equipement") or "").strip()
    fabricant = str(payload.get("fabricant") or "").strip()
    if not all((nom, domaine, type_equipement, fabricant)):
        raise HTTPException(400, "Nom, domaine, type et fabricant requis")
    model = ajouter_modele_equipement(nom, domaine, type_equipement, fabricant)
    return {"ok": True, **model}


@app.get("/api/services-equipement")
def get_services_equipement(user: dict = Depends(_verify_token)):
    return lire_services_equipement()


@app.post("/api/services-equipement")
def post_service_equipement(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    nom = str(payload.get("nom") or "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    ajouter_service_equipement(nom)
    return {"ok": True}


@app.get("/api/types-equipement-custom")
def get_types_equipement_custom(domaine: str = Query(""), user: dict = Depends(_verify_token)):
    return lire_types_equipement_custom(domaine)


@app.post("/api/types-equipement-custom")
def post_type_equipement_custom(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    nom = payload.get("nom", "").strip()
    domaine = payload.get("domaine", "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    ajouter_type_equipement_custom(nom, domaine)
    return {"ok": True}


@app.get("/api/types-intervention-custom")
def get_types_intervention_custom(user: dict = Depends(_verify_token)):
    return lire_types_intervention_custom()


@app.post("/api/types-intervention-custom")
def post_type_intervention_custom(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    nom = payload.get("nom", "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    ajouter_type_intervention_custom(nom)
    return {"ok": True}


@app.get("/api/domaines-custom")
def get_domaines_custom(user: dict = Depends(_verify_token)):
    from db_engine import lire_domaines_custom
    return lire_domaines_custom()


@app.post("/api/domaines-custom")
def post_domaine_custom(payload: dict = Body(...), user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    from db_engine import ajouter_domaine_custom
    nom = str(payload.get("nom") or "").strip()
    if not nom:
        raise HTTPException(400, "Nom requis")
    try:
        domaine = ajouter_domaine_custom(nom)
        return {"ok": True, "domaine": domaine}
    except Exception as exc:
        logger.error(f"Erreur sauvegarde domaine personnalisé: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Impossible d'enregistrer le domaine")


@app.delete("/api/domaines-custom/{nom}")
def delete_domaine_custom(nom: str, user: dict = Depends(_verify_token)):
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    from db_engine import supprimer_domaine_custom
    if not nom.strip():
        raise HTTPException(400, "Nom requis")
    supprimer_domaine_custom(nom)
    return {"ok": True}


# ==========================================
# DOCUMENTS TECHNIQUES
# ==========================================

@app.post("/api/documents-techniques/upload")
def upload_document(body: dict, user: dict = Depends(_verify_token)):
    """Upload a technical document (base64 encoded) for an equipment."""
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    from db_engine import ajouter_document_technique
    equip_id = body.get("equipement_id")
    nom_fichier = body.get("nom_fichier", "")
    contenu_base64 = body.get("contenu_base64", "")
    if not equip_id or not nom_fichier or not contenu_base64:
        raise HTTPException(status_code=400, detail="equipement_id, nom_fichier et contenu_base64 requis")
    with get_db() as conn:
        assert_resource_client_access(conn, "equipement", int(equip_id), user)
    validated = decode_and_validate_base64(nom_fichier, contenu_base64, "document_technique")
    from s3_storage import upload_private_file
    stored = upload_private_file(
        validated.data,
        category="documents-techniques",
        extension=validated.extension,
        content_type=validated.content_type,
        original_name=validated.display_name,
        content_hash=validated.sha256,
        metadata={"equipment-id": equip_id, "uploaded-by": user.get("sub", "unknown")},
    )
    if not stored:
        raise HTTPException(status_code=503, detail="Le stockage sécurisé des fichiers est momentanément indisponible")
    ajouter_document_technique(
        equip_id, validated.display_name, "", storage_key=stored["s3_key"],
        content_type=validated.content_type, size_bytes=stored["size_bytes"], sha256=validated.sha256,
    )
    return {"ok": True, "filename": validated.display_name}


@app.get("/api/documents-techniques")
def get_all_documents(user: dict = Depends(_verify_token)):
    """List all technical documents with associated equipment info."""
    from db_engine import lire_tous_documents_techniques
    documents = lire_tous_documents_techniques()
    client_scope = get_client_scope(user)
    if client_scope:
        documents = [
            doc for doc in documents
            if str(doc.get("client") or "").strip().casefold() == client_scope.casefold()
        ]
    return documents


@app.get("/api/documents-techniques/{equip_id}")
def get_documents_by_equipment(equip_id: int, user: dict = Depends(_verify_token)):
    """List technical documents for a specific equipment."""
    from db_engine import lire_documents_techniques
    with get_db() as conn:
        assert_resource_client_access(conn, "equipement", equip_id, user)
    return lire_documents_techniques(equip_id)


@app.get("/api/documents-techniques/download/{doc_id}")
def download_document(doc_id: int, user: dict = Depends(_verify_token)):
    """Download a specific technical document (returns base64 content)."""
    from db_engine import lire_document_technique_contenu
    with get_db() as conn:
        assert_resource_client_access(conn, "document_technique", doc_id, user)
    doc = lire_document_technique_contenu(doc_id)
    if doc and doc.get("storage_key"):
        from s3_storage import download_private_file
        stored = download_private_file(doc["storage_key"])
        if not stored:
            raise HTTPException(status_code=503, detail="Le stockage sécurisé des fichiers est momentanément indisponible")
        content, _ = stored
        return {
            "contenu_base64": base64.b64encode(content).decode("ascii"),
            "nom_fichier": doc["nom_fichier"],
        }
    if not doc:
        raise HTTPException(status_code=404, detail="Document non trouvé")
    return doc


@app.delete("/api/documents-techniques/{doc_id}")
def delete_document(doc_id: int, user: dict = Depends(_verify_token)):
    """Delete a technical document."""
    if not _check_create_permission(user):
        raise HTTPException(status_code=403, detail="Cette action est réservée aux Responsables, Managers et Admins")
    from db_engine import lire_document_technique_stockage, supprimer_document_technique
    with get_db() as conn:
        assert_resource_client_access(conn, "document_technique", doc_id, user)
    storage_key = lire_document_technique_stockage(doc_id)
    if storage_key:
        from s3_storage import delete_file
        if not delete_file(storage_key):
            raise HTTPException(status_code=503, detail="Le stockage sécurisé des fichiers est momentanément indisponible")
    supprimer_document_technique(doc_id)
    return {"ok": True}


# ==========================================
# INTERVENTIONS / SAV
# ==========================================

__all__ = [
    "get_equipements",
    "export_equipements_pdf",
    "create_equipement",
    "update_equipement",
    "get_historique_statuts_equipement",
    "reactivate_equipement",
    "delete_equipement",
    "sync_region_ville",
    "get_fabricants",
    "post_fabricant",
    "get_modeles_equipement",
    "post_modele_equipement",
    "get_services_equipement",
    "post_service_equipement",
    "get_types_equipement_custom",
    "post_type_equipement_custom",
    "get_types_intervention_custom",
    "post_type_intervention_custom",
    "get_domaines_custom",
    "post_domaine_custom",
    "delete_domaine_custom",
    "upload_document",
    "get_all_documents",
    "get_documents_by_equipment",
    "download_document",
    "delete_document",
]
