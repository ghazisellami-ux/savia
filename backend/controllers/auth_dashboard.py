"""Authentication and primary dashboard routes."""

from api.runtime import (
    Any,
    Depends,
    HTTPException,
    JWT_EXPIRY_HOURS,
    JWT_ISSUER,
    JWT_SECRET,
    IS_PRODUCTION,
    PASSWORD_ROTATION_DAYS,
    Optional,
    Request,
    Response,
    app,
    bcrypt,
    datetime,
    db_lire_clients,
    get_db,
    jwt,
    lire_equipements,
    lire_contrats,
    get_contract_equipements,
    lire_interventions,
    lire_planning,
    log_audit,
    logger,
    pd,
    read_sql,
    timedelta,
    unicodedata,
)
from services.sla_tracking import (
    active_sla_contracts,
    compliance_percentage,
    elapsed_hours,
    sla_contract_for,
    sla_start_value,
)
from api.security import (
    ChangePasswordRequest,
    LoginRequest,
    _verify_password_change_token,
    _verify_password,
    _verify_token,
    get_client_scope,
    resolve_client_scope,
    validate_password_policy,
    AUTH_COOKIE_NAME,
)
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_MAX_ATTEMPTS = 5


def _consume_login_attempts(*keys: str) -> bool:
    """Atomically reserve attempts in PostgreSQL for all Coolify replicas."""
    limited = False
    with get_db() as conn:
        for key in keys:
            row = conn.execute(
                """INSERT INTO login_rate_limits
                       (rate_key, window_started_at, attempts, updated_at)
                   VALUES (%s, CURRENT_TIMESTAMP, 1, CURRENT_TIMESTAMP)
                   ON CONFLICT (rate_key) DO UPDATE SET
                       attempts = CASE
                           WHEN login_rate_limits.window_started_at
                                <= CURRENT_TIMESTAMP - INTERVAL '15 minutes'
                           THEN 1
                           ELSE login_rate_limits.attempts + 1
                       END,
                       window_started_at = CASE
                           WHEN login_rate_limits.window_started_at
                                <= CURRENT_TIMESTAMP - INTERVAL '15 minutes'
                           THEN CURRENT_TIMESTAMP
                           ELSE login_rate_limits.window_started_at
                       END,
                       updated_at = CURRENT_TIMESTAMP
                   RETURNING attempts""",
                (key,),
            ).fetchone()
            if row and int(row["attempts"]) > _LOGIN_MAX_ATTEMPTS:
                limited = True
    return limited


def _clear_login_attempts(*keys: str) -> None:
    """Clear both the account and IP counters after a successful login."""
    with get_db() as conn:
        for key in keys:
            conn.execute("DELETE FROM login_rate_limits WHERE rate_key = %s", (key,))


def _password_rotation_due(password_changed_at: Any) -> bool:
    if not isinstance(password_changed_at, datetime):
        return True
    if password_changed_at.tzinfo is not None:
        password_changed_at = password_changed_at.replace(tzinfo=None)
    return password_changed_at <= datetime.utcnow() - timedelta(days=PASSWORD_ROTATION_DAYS)


def _resolve_technician_id(conn, username: str, full_name: str) -> int | None:
    """Resolve a logged-in technician without guessing between homonyms."""
    row = conn.execute(
        "SELECT id FROM techniciens WHERE LOWER(BTRIM(username)) = LOWER(BTRIM(%s))",
        (username,),
    ).fetchone()
    if row:
        return int(row["id"])
    if not str(full_name or "").strip():
        return None
    match = conn.execute(
        """SELECT MIN(id) AS id FROM techniciens
           WHERE LOWER(BTRIM(CONCAT(prenom, ' ', nom))) = LOWER(BTRIM(%s))
              OR LOWER(BTRIM(CONCAT(nom, ' ', prenom))) = LOWER(BTRIM(%s))
           HAVING COUNT(*) = 1""",
        (full_name, full_name),
    ).fetchone()
    return int(match["id"]) if match and match.get("id") is not None else None


def _issue_access_token(user_data: dict) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": user_data["username"],
        "role": user_data["role"],
        "nom": user_data.get("nom_complet", ""),
        "client": user_data.get("client", "") or "",
        "pages_autorisees": user_data.get("pages_autorisees", "") or "",
        "technicien_id": user_data.get("technicien_id"),
        "pv": int(user_data.get("password_version") or 1),
        "iss": JWT_ISSUER,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _login_response(user_data: dict, token: str | None = None) -> dict:
    password_change_required = bool(user_data.get("must_change_password"))
    response = {
        "password_change_required": password_change_required,
        "user": {
            "username": user_data["username"],
            "nom": user_data.get("nom_complet", ""),
            "role": user_data["role"],
            "client": user_data.get("client", "") or "",
            "pages_autorisees": user_data.get("pages_autorisees", "") or "",
            "technicien_id": user_data.get("technicien_id"),
            "password_change_required": password_change_required,
        },
    }
    # The browser never receives the JWT; it is set as an HttpOnly cookie.
    # The explicit PWA compatibility path retains the token for offline sync.
    if token is not None:
        response["token"] = token
    return response


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=JWT_EXPIRY_HOURS * 3600,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/")

@app.get("/")
def root():
    return {"status": "ok", "service": "SAVIA API", "version": "2.0.0"}


@app.post("/api/auth/login")
def login(body: LoginRequest, request: Request, response: Response):
    ip_address = request.client.host if request.client else "unknown"
    login_username = body.username.strip()
    username_key = login_username.casefold()
    ip_key = f"ip:{ip_address}"
    account_key = f"account:{username_key}"
    if _consume_login_attempts(ip_key, account_key):
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives de connexion. Réessayez dans 15 minutes.",
            headers={"Retry-After": str(_LOGIN_WINDOW_SECONDS)},
        )
    
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM utilisateurs WHERE LOWER(BTRIM(username)) = LOWER(BTRIM(%s)) AND actif = 1",
            (login_username,)
        ).fetchone()

    if not row or not _verify_password(body.password, row["password_hash"]):
        log_audit(login_username, "LOGIN_FAILED", f"Identifiants incorrects", "auth", ip_address)
        raise HTTPException(status_code=401, detail="Identifiants incorrects")

    user_data = dict(row)
    with get_db() as conn:
        user_data["technicien_id"] = _resolve_technician_id(
            conn,
            user_data["username"],
            user_data.get("nom_complet", ""),
        )
    request.state.access_username = user_data.get("username", "")
    request.state.access_role = user_data.get("role", "")
    rotation_due = _password_rotation_due(user_data.get("password_changed_at"))
    if rotation_due:
        user_data["must_change_password"] = True
    with get_db() as conn:
        conn.execute(
            """UPDATE utilisateurs
               SET last_login = CURRENT_TIMESTAMP,
                   must_change_password = %s
               WHERE id = %s""",
            (bool(user_data.get("must_change_password")), user_data["id"]),
        )
    
    # Log successful login
    log_audit(user_data.get("username", login_username), "LOGIN", "Connexion réussie", "auth", ip_address)
    _clear_login_attempts(ip_key, account_key)
    
    is_pwa_client = request.headers.get("X-SAVIA-Client", "").lower() == "pwa"
    token = _issue_access_token(user_data)
    # The PWA persists its bearer token separately for offline use.  Setting the
    # dashboard cookie here would overwrite a browser session on the same host:
    # cookies are scoped by hostname and path, not by port.
    if not is_pwa_client:
        _set_auth_cookie(response, token)
    return _login_response(user_data, token if is_pwa_client else None)


@app.post("/api/auth/logout")
def logout(response: Response):
    _clear_auth_cookie(response)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict = Depends(_verify_password_change_token)):
    return {"user": user}


@app.post("/api/auth/change-password")
def change_password(body: ChangePasswordRequest, request: Request, response: Response, user: dict = Depends(_verify_password_change_token)):
    try:
        validate_password_policy(body.new_password, user["sub"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit être différent de l'ancien")

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM utilisateurs WHERE username = %s AND actif = 1",
            (user["sub"],),
        ).fetchone()
        if not row or not _verify_password(body.current_password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
        updated = conn.execute(
            """UPDATE utilisateurs
               SET password_hash = %s,
                   password_changed_at = CURRENT_TIMESTAMP,
                   must_change_password = false,
                   password_version = COALESCE(password_version, 1) + 1
               WHERE id = %s
               RETURNING username, nom_complet, role, client, pages_autorisees,
                         password_version, must_change_password""",
            (bcrypt.hashpw(body.new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"), row["id"]),
        ).fetchone()

    user_data = dict(updated)
    ip_address = request.client.host if request.client else "unknown"
    log_audit(user_data["username"], "PASSWORD_CHANGED", "Mot de passe modifié par l'utilisateur", "auth", ip_address)
    token = _issue_access_token(user_data)
    _set_auth_cookie(response, token)
    is_pwa_client = request.headers.get("X-SAVIA-Client", "").lower() == "pwa"
    return _login_response(user_data, token if is_pwa_client else None)


def _get_client_filter(user: dict) -> Optional[str]:
    """Retourne le client restricté pour un Lecteur, None sinon (accès total)."""
    return get_client_scope(user)


_TERMINAL_INTERVENTION_STATUSES = frozenset({
    "cloturee", "clôturée", "terminee", "terminée", "realisee", "réalisée",
    "annulee", "annulée", "closed", "resolved", "completee", "complétée",
})


def _is_terminal_intervention_status(value: object) -> bool:
    """Return whether a status closes an intervention for availability purposes."""
    return str(value or "").strip().casefold() in _TERMINAL_INTERVENTION_STATUSES


def _filter_interventions_for_equipments(df_int, df_eq):
    """Scope interventions to equipment IDs, retaining a name fallback for legacy rows."""
    if df_int.empty:
        return df_int
    if df_eq.empty:
        return df_int.iloc[0:0].copy()

    if "equipement_id" in df_int.columns and "id" in df_eq.columns:
        equipment_ids = pd.to_numeric(df_eq["id"], errors="coerce").dropna().astype(int)
        intervention_ids = pd.to_numeric(df_int["equipement_id"], errors="coerce")
        matches_equipment_id = intervention_ids.isin(equipment_ids)

        # Older records without an equipment_id can still be included, but only
        # as a compatibility fallback. New records are always matched by ID.
        matches_legacy_name = pd.Series(False, index=df_int.index)
        if "machine" in df_int.columns and "Nom" in df_eq.columns:
            names = df_eq["Nom"].dropna().astype(str).tolist()
            matches_legacy_name = intervention_ids.isna() & df_int["machine"].isin(names)
        return df_int[matches_equipment_id | matches_legacy_name].copy()

    if "machine" in df_int.columns and "Nom" in df_eq.columns:
        return df_int[df_int["machine"].isin(df_eq["Nom"].dropna().tolist())].copy()
    return df_int.iloc[0:0].copy()


# ==========================================
# DASHBOARD — Aggregated KPIs
# ==========================================

@app.get("/api/dashboard/kpis")
def get_dashboard_kpis(
    client: Optional[str] = None,
    region: Optional[str] = None,
    ville: Optional[str] = None,
    equipment_type: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Compute real KPIs from the database, optionally filtered by client, region, ville, equipment type, and date range."""
    try:
        df_eq = lire_equipements()
        df_int = lire_interventions()
        df_clients = db_lire_clients()  # Get ALL clients from clients table

        # Align the dashboard with the interventions list: a future planned
        # maintenance is not yet an active intervention and must not lower the
        # resolution rate denominator.
        if not df_int.empty and "planning_id" in df_int.columns:
            try:
                with get_db() as conn:
                    future_planning_rows = conn.execute(
                        """SELECT id
                           FROM planning_maintenance
                           WHERE date_prevue > CURRENT_DATE
                             AND statut NOT IN ('Cloturee', 'Réalisée', 'Terminée', 'Annulée')"""
                    ).fetchall()
                future_planning_ids = {
                    int(row.get("id"))
                    for row in future_planning_rows
                    if row.get("id") is not None
                }
                if future_planning_ids:
                    def is_future_planned(value):
                        try:
                            return int(value) in future_planning_ids
                        except (TypeError, ValueError):
                            return False

                    df_int = df_int[~df_int["planning_id"].apply(is_future_planned)]
            except Exception as exc:
                logger.warning("Unable to filter future planned interventions for dashboard: %s", exc)
        
        # Debug logging
        logger.info(f"KPI filters: client={client}, region={region}, ville={ville}, equipment_type={equipment_type}")
        logger.info(f"Initial equipements count: {len(df_eq)}")
        logger.info(f"Initial interventions count: {len(df_int)}")
        logger.info(f"Total clients in database: {len(df_clients)}")

        # Pour Lecteur : forcer le filtre par son client
        effective_client = resolve_client_scope(user, client)

        # IMPORTANT: Count unique clients from ALL clients table (not just equipements)
        # This ensures we show all clients, even those without equipment
        nb_clients_all = 0
        if not df_clients.empty and "nom" in df_clients.columns:
            nb_clients_all = len(df_clients["nom"].dropna().unique())

        # Create a COPY of df_eq for CURRENT STATUS calculation (not filtered by date)
        df_eq_for_status = df_eq.copy()
        
        # Filter equipements by client
        if effective_client and not df_eq.empty and "Client" in df_eq.columns:
            df_eq = df_eq[df_eq["Client"].astype(str).str.lower() == effective_client.lower()]
            df_eq_for_status = df_eq_for_status[df_eq_for_status["Client"].astype(str).str.lower() == effective_client.lower()]
            logger.info(f"After client filter: {len(df_eq)} equipements")

        # Filter equipements by region (join with clients table to get region)
        if region and not df_eq.empty and not df_clients.empty:
            if region.lower() == "international":
                # Get international clients
                clients_in_region = df_clients[
                    df_clients["international"].notna() & 
                    (df_clients["international"].astype(bool) == True)
                ]["nom"].tolist() if "international" in df_clients.columns else []
            else:
                # Get clients in this region
                clients_in_region = df_clients[
                    df_clients["region"].notna() & 
                    (df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip())
                ]["nom"].tolist() if "region" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_region and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_region)]
                df_eq_for_status = df_eq_for_status[df_eq_for_status["Client"].astype(str).isin(clients_in_region)]
                logger.info(f"After region filter (via clients): {len(df_eq)} equipements from {len(clients_in_region)} clients")

        # Filter equipements by ville (join with clients table to get ville)
        if ville and not df_eq.empty and not df_clients.empty:
            # Get clients in this ville
            clients_in_ville = df_clients[
                df_clients["ville"].notna() & 
                (df_clients["ville"].astype(str).str.lower().str.strip() == ville.lower().strip())
            ]["nom"].tolist() if "ville" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_ville and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_ville)]
                df_eq_for_status = df_eq_for_status[df_eq_for_status["Client"].astype(str).isin(clients_in_ville)]
                logger.info(f"After ville filter (via clients): {len(df_eq)} equipements from {len(clients_in_ville)} clients")

        # Filter equipements by equipment type
        # Add .str.strip() to handle whitespace and .notna() to handle NULL values
        if equipment_type and not df_eq.empty and "Type" in df_eq.columns:
            df_eq = df_eq[df_eq["Type"].notna() & (df_eq["Type"].astype(str).str.lower().str.strip() == equipment_type.lower().strip())]
            df_eq_for_status = df_eq_for_status[df_eq_for_status["Type"].notna() & (df_eq_for_status["Type"].astype(str).str.lower().str.strip() == equipment_type.lower().strip())]
            logger.info(f"After equipment_type filter: {len(df_eq)} equipements")

        # Scope interventions by the equipment ID. Machine names are not unique
        # enough to identify an asset reliably.
        if effective_client:
            df_int = _filter_interventions_for_equipments(df_int, df_eq)
            logger.info(f"After client intervention filter: {len(df_int)} interventions")

        # Apply the same ID-based scope for the other equipment dimensions.
        if region or ville or equipment_type:
            df_int = _filter_interventions_for_equipments(df_int, df_eq)
            logger.info(f"After region/ville/type intervention filter: {len(df_int)} interventions")

        # Operational indicators (open work, SLA and preventive planning) are
        # always about the current situation. Keep this scoped-but-undated
        # dataset before applying the dashboard period to historical KPIs.
        df_int_current = df_int.copy()

        # Filter interventions by date range
        if not df_int.empty and "date" in df_int.columns:
            df_int["date"] = pd.to_datetime(df_int["date"], errors="coerce")
            if date_start:
                df_int = df_int[df_int["date"] >= pd.to_datetime(date_start)]
            if date_end:
                df_int = df_int[df_int["date"] <= pd.to_datetime(date_end)]
            logger.info(f"After date filter: {len(df_int)} interventions")

        def _activity_availability() -> float:
            """Average monthly availability for the selected period."""
            if df_int.empty or "date" not in df_int.columns:
                return 100.0

            dates = pd.to_datetime(df_int["date"], errors="coerce")
            if dates.dropna().empty:
                return 100.0

            start_date = pd.to_datetime(date_start, errors="coerce") if date_start else dates.min()
            end_date = pd.to_datetime(date_end, errors="coerce") if date_end else dates.max()
            if pd.isna(start_date) or pd.isna(end_date):
                return 100.0

            months = pd.period_range(start=start_date.to_period("M"), end=end_date.to_period("M"), freq="M")
            if len(months) == 0:
                return 100.0

            monthly_values = []
            for month in months:
                month_start = month.to_timestamp()
                month_end = (month + 1).to_timestamp()
                month_int = df_int[(dates >= month_start) & (dates < month_end)]
                nb_month_interventions = len(month_int)

                availability = 100.0
                if nb_month_interventions > 0:
                    if "statut" in df_int.columns:
                        unfinished = int((~month_int["statut"].map(_is_terminal_intervention_status)).sum())
                        availability = max(0.0, 100.0 - (unfinished * 2.0))
                    else:
                        availability = max(0.0, 100.0 - (nb_month_interventions * 2.0))
                monthly_values.append(availability)

            return round(sum(monthly_values) / len(monthly_values), 1)

        nb_eq = len(df_eq_for_status) if not df_eq_for_status.empty else 0
        nb_critiques = 0
        dispo = 100.0

        def _status_key(value: Any) -> str:
            text = unicodedata.normalize("NFD", str(value or "").strip().lower())
            return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        
        # Alertes Critiques = CURRENT equipment status (not filtered by month)
        # Shows all equipment currently in critical/down state
        if not df_eq_for_status.empty and "Statut" in df_eq_for_status.columns:
            status_values = df_eq_for_status["Statut"].map(_status_key)
            critical_statuses = {"hors service", "critique", "en panne"}
            unavailable_statuses = critical_statuses | {"en atelier"}
            nb_critiques = int(status_values.isin(critical_statuses).sum())
            nb_unavailable = int(status_values.isin(unavailable_statuses).sum())
            dispo = round(((nb_eq - nb_unavailable) / nb_eq) * 100, 1) if nb_eq > 0 else 100.0

        # Combine current status availability with the same activity-based
        # monthly availability used by the trend chart. Annual views average
        # the monthly values instead of counting all yearly interventions at once.
        dispo = min(dispo, _activity_availability())

        # Count unique clients
        # If NO filters applied: show ALL clients from clients table (66)
        # If filters applied: show only clients with equipment matching those filters
        nb_clients = 0
        if region or ville or equipment_type or effective_client:
            # Filters applied: count clients from filtered equipements only
            if not df_eq.empty and "Client" in df_eq.columns:
                nb_clients = len(df_eq["Client"].dropna().unique())
        else:
            # No filters applied: show ALL clients from clients table
            nb_clients = nb_clients_all

        # Calculate intervention-based KPIs
        nb_interventions = len(df_int) if not df_int.empty else 0

        closed_statuses = {"cloturee", "closed", "resolved", "terminee", "completee", "annulee"}

        def _is_closed_status(value: Any) -> bool:
            return _status_key(value) in closed_statuses

        # Open interventions are deliberately not limited to the selected
        # historic period: an intervention remains actionable until it closes.
        nb_interventions_ouvertes = 0
        nb_interventions_retard = 0
        if not df_int_current.empty and "statut" in df_int_current.columns:
            open_interventions = df_int_current[
                ~df_int_current["statut"].apply(_is_closed_status)
            ].copy()
            nb_interventions_ouvertes = len(open_interventions)
            if not open_interventions.empty:
                due_col = "planning_date" if "planning_date" in open_interventions.columns else "date"
                if due_col in open_interventions.columns:
                    due_dates = pd.to_datetime(open_interventions[due_col], errors="coerce")
                    nb_interventions_retard = int((due_dates.dt.date < datetime.now().date()).fillna(False).sum())

        # Preventive work comes from the planning table, not from interventions:
        # future planning rows do not yet have an intervention by design.
        preventives_retard = 0
        preventives_7j = 0
        preventives_30j = 0
        try:
            df_plan = lire_planning()
            if not df_plan.empty:
                if effective_client and "client" in df_plan.columns:
                    df_plan = df_plan[
                        df_plan["client"].astype(str).str.strip().str.casefold()
                        == effective_client.strip().casefold()
                    ]
                if (region or ville or equipment_type) and "machine" in df_plan.columns:
                    scoped_machines = set(df_eq["Nom"].dropna().astype(str)) if "Nom" in df_eq.columns else set()
                    df_plan = df_plan[df_plan["machine"].astype(str).isin(scoped_machines)]
                if "is_ghost" in df_plan.columns:
                    df_plan = df_plan[~df_plan["is_ghost"].fillna(False).astype(bool)]
                if "statut" in df_plan.columns:
                    df_plan = df_plan[~df_plan["statut"].apply(_is_closed_status)]
                if "type_maintenance" in df_plan.columns:
                    df_plan = df_plan[
                        df_plan["type_maintenance"].astype(str).str.normalize("NFKD")
                        .str.encode("ascii", "ignore").str.decode("ascii")
                        .str.lower().str.contains("prevent")
                    ]
                if "date_prevue" in df_plan.columns:
                    planned_dates = pd.to_datetime(df_plan["date_prevue"], errors="coerce").dt.date
                    today = datetime.now().date()
                    in_7_days = today + timedelta(days=7)
                    in_30_days = today + timedelta(days=30)
                    preventives_retard = int((planned_dates < today).fillna(False).sum())
                    preventives_7j = int(((planned_dates >= today) & (planned_dates <= in_7_days)).fillna(False).sum())
                    preventives_30j = int(((planned_dates > in_7_days) & (planned_dates <= in_30_days)).fillna(False).sum())
        except Exception as exc:
            logger.warning("Unable to compute preventive dashboard KPIs: %s", exc)

        # SLA: use the same contract-resolution rules as the dedicated SLA
        # page. The rate combines closed cases in the selected period with
        # currently open commitments; only work covered by a contract is used.
        sla_respect_pct = 100.0
        sla_hors_delai = 0
        sla_suivies = 0
        try:
            contractual_slas = active_sla_contracts(
                lire_contrats().to_dict("records"), get_contract_equipements,
            )
            machine_clients = {}
            if not df_eq_for_status.empty and {"Nom", "Client"}.issubset(df_eq_for_status.columns):
                machine_clients = dict(zip(df_eq_for_status["Nom"], df_eq_for_status["Client"]))

            active_sla_items = []
            if not df_int_current.empty:
                for _, intervention in df_int_current.iterrows():
                    if _is_closed_status(intervention.get("statut")):
                        continue
                    machine = intervention.get("machine", "")
                    client_name = intervention.get("client", "") or machine_clients.get(machine, "")
                    contract = sla_contract_for(contractual_slas, client_name, machine, intervention.get("type_intervention", ""))
                    if not contract:
                        continue
                    elapsed = elapsed_hours(sla_start_value(intervention), datetime.now(), business_day_start_hour=8)
                    if elapsed is None:
                        continue
                    active_sla_items.append({"breached": elapsed > contract["sla_h"]})

            historical_compliant = 0
            historical_total = 0
            if not df_int.empty:
                for _, intervention in df_int.iterrows():
                    if not _is_closed_status(intervention.get("statut")):
                        continue
                    start = pd.to_datetime(intervention.get("date_debut_intervention"), errors="coerce")
                    end = pd.to_datetime(intervention.get("date_cloture"), errors="coerce")
                    if pd.isna(start) or pd.isna(end):
                        continue
                    machine = intervention.get("machine", "")
                    client_name = intervention.get("client", "") or machine_clients.get(machine, "")
                    contract = sla_contract_for(contractual_slas, client_name, machine, intervention.get("type_intervention", ""))
                    if not contract:
                        continue
                    historical_total += 1
                    if (end - start).total_seconds() <= contract["sla_h"] * 3600:
                        historical_compliant += 1

            sla_hors_delai = sum(1 for item in active_sla_items if item["breached"])
            sla_suivies = historical_total + len(active_sla_items)
            sla_respect_pct = compliance_percentage(historical_compliant, historical_total, active_sla_items)
        except Exception as exc:
            logger.warning("Unable to compute SLA dashboard KPIs: %s", exc)
        
        # MTBF is based only on corrective failures, per equipment. Preventive
        # visits are planned work and must never shorten a reliability metric.
        mtbf = 0.0
        corrective_interventions = pd.DataFrame()
        if not df_int.empty and {"date", "machine", "type_intervention"}.issubset(df_int.columns):
            corrective_interventions = df_int[
                df_int["type_intervention"].astype(str).str.normalize("NFKD")
                .str.encode("ascii", "ignore").str.decode("ascii")
                .str.lower().str.contains("correct")
            ].copy()
            corrective_interventions["date"] = pd.to_datetime(corrective_interventions["date"], errors="coerce")
            gaps = []
            for _, failures in corrective_interventions.dropna(subset=["date"]).groupby("machine"):
                dates = failures["date"].sort_values()
                if len(dates) > 1:
                    gaps.extend(dates.diff().dropna().dt.total_seconds().div(3600).tolist())
            if gaps:
                mtbf = float(sum(gaps) / len(gaps))
        
        # MTTR uses the recorded duration in minutes for closed corrective work.
        mttr = 0.0
        if not corrective_interventions.empty and "duree_minutes" in corrective_interventions.columns:
            repaired = corrective_interventions[
                corrective_interventions["statut"].apply(_is_closed_status)
            ] if "statut" in corrective_interventions.columns else corrective_interventions
            durations = pd.to_numeric(repaired["duree_minutes"], errors="coerce")
            durations = durations[durations > 0]
            if not durations.empty:
                mttr = float(durations.mean() / 60.0)
        
        # Calculate total cost = cout_main_oeuvre + cout_pieces (NOT cout_interventions which double-counts)
        # Use ALL interventions (not just closed) to match SAV page calculation
        # Recalculate cout_main_oeuvre from duration × current hourly rate (same as SAV page does)
        cout_main_oeuvre_total = 0.0
        cout_pieces_total = 0.0
        
        if not df_int.empty:
            # Get current hourly rate from config
            try:
                with get_db() as conn:
                    config_row = conn.execute(
                        "SELECT valeur FROM config_client WHERE cle = 'taux_horaire_technicien'"
                    ).fetchone()
                    taux_horaire = float(config_row["valeur"]) if config_row else 100.0
            except (ValueError, TypeError, AttributeError):
                taux_horaire = 100.0
            
            # Recalculate labor cost from duration × hourly rate (same as SAV page line 676)
            # This matches the formula: (total_minutes / 60) × hourly_rate
            if "duree_minutes" in df_int.columns:
                durations = pd.to_numeric(df_int["duree_minutes"], errors="coerce").fillna(0)
                total_minutes = float(durations.sum())
                cout_main_oeuvre_total = (total_minutes / 60.0) * taux_horaire
            
            logger.info(f"Recalculated cout_main_oeuvre from duration: {total_minutes} min × {taux_horaire}/h = {cout_main_oeuvre_total} DT")
            
            # Sum cout_pieces from all interventions
            for col in ["cout_pieces", "pieces", "cout_pieces_utilisees", "pieces_cost", "cout_Pieces", "Cout_Pieces", "Cout_pieces_utilisees", "Cost_Pieces"]:
                if col in df_int.columns:
                    pieces_costs = pd.to_numeric(df_int[col], errors="coerce").dropna()
                    if len(pieces_costs) > 0:
                        cout_pieces_total = float(pieces_costs.sum())
                    logger.info(f"Found {col}: total = {cout_pieces_total}")
                    break
        
        # Average cost of a corrective intervention is more actionable than a
        # fleet-wide total. It follows the same labour + parts calculation.
        cout_correctif_moyen = 0.0
        if not corrective_interventions.empty:
            corrective_count = len(corrective_interventions)
            corrective_labor = 0.0
            corrective_parts = 0.0
            if "duree_minutes" in corrective_interventions.columns:
                corrective_labor = (
                    float(pd.to_numeric(corrective_interventions["duree_minutes"], errors="coerce").fillna(0).sum())
                    / 60.0 * taux_horaire
                )
            for col in ["cout_pieces", "pieces", "cout_pieces_utilisees", "pieces_cost"]:
                if col in corrective_interventions.columns:
                    corrective_parts = float(pd.to_numeric(corrective_interventions[col], errors="coerce").fillna(0).sum())
                    break
            cout_correctif_moyen = (corrective_labor + corrective_parts) / corrective_count

        # Total cost = main d'oeuvre + pièces (no double-counting)
        cout_total = cout_main_oeuvre_total + cout_pieces_total
        logger.info(f"Dashboard KPIs: cout_main_oeuvre_total={cout_main_oeuvre_total}, cout_pieces_total={cout_pieces_total}, cout_total={cout_total}")

        # Calculate resolution rate (% of closed interventions)
        taux_resolution = 0.0
        if nb_interventions > 0 and not df_int.empty:
            # Check for status column (could be "Statut", "statut", "status", etc.)
            status_col = None
            for col in ["Statut", "statut", "status", "Status"]:
                if col in df_int.columns:
                    status_col = col
                    break
            
            if status_col:
                # Count closed/resolved interventions
                closed_statuses = {"clôturée", "cloturee", "closed", "resolved", "terminée", "terminee", "complétée", "completee"}
                nb_closed = len(df_int[df_int[status_col].astype(str).str.lower().str.strip().isin(closed_statuses)])
                taux_resolution = round((nb_closed / nb_interventions) * 100, 1) if nb_interventions > 0 else 0

        return {
            "nb_equipements": nb_eq,
            "nb_critiques": nb_critiques,
            "disponibilite": dispo,
            "mtbf": round(mtbf, 1),
            "mttr": round(mttr, 1),
            "cout_total": round(cout_total, 2),
            "nb_interventions": nb_interventions,
            "nb_clients": nb_clients,
            "taux_resolution": taux_resolution,
            "interventions_ouvertes": nb_interventions_ouvertes,
            "interventions_retard": nb_interventions_retard,
            "preventives_retard": preventives_retard,
            "preventives_7j": preventives_7j,
            "preventives_30j": preventives_30j,
            "sla_respect_pct": sla_respect_pct,
            "sla_hors_delai": sla_hors_delai,
            "sla_suivies": sla_suivies,
            "cout_correctif_moyen": round(cout_correctif_moyen, 2),
        }
    except Exception as e:
        logger.error(f"Dashboard KPIs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/health-scores")
def get_health_scores(
    client: Optional[str] = None,
    region: Optional[str] = None,
    ville: Optional[str] = None,
    equipment_type: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    user: dict = Depends(_verify_token),
):
    """Compute health scores per equipment based on intervention history."""
    try:
        # Load data efficiently with selective columns
        df_eq = lire_equipements()
        
        # Load only necessary intervention columns for scoring
        with get_db() as conn:
            int_query = """
            SELECT i.machine, i.equipement_id, i.type_intervention, i.date, i.date_cloture, i.statut
            FROM interventions i
            WHERE COALESCE(i.is_temporary, 0) = 0
            ORDER BY i.date DESC
            """
            df_int = read_sql(int_query, conn)
        
        df_clients = db_lire_clients()  # Get clients table for region/ville filtering

        # Pour Lecteur : forcer le filtre par son client
        effective_client = resolve_client_scope(user, client)

        # Filter equipements by client
        if effective_client and not df_eq.empty and "Client" in df_eq.columns:
            df_eq = df_eq[df_eq["Client"].astype(str).str.lower() == effective_client.lower()]

        # Filter equipements by region (join with clients table to get region)
        if region and not df_eq.empty and not df_clients.empty:
            if region.lower() == "international":
                # Get international clients
                clients_in_region = df_clients[
                    df_clients["international"].notna() & 
                    (df_clients["international"].astype(bool) == True)
                ]["nom"].tolist() if "international" in df_clients.columns else []
            else:
                # Get clients in this region
                clients_in_region = df_clients[
                    df_clients["region"].notna() & 
                    (df_clients["region"].astype(str).str.lower().str.strip() == region.lower().strip())
                ]["nom"].tolist() if "region" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_region and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_region)]

        # Filter equipements by ville (join with clients table to get ville)
        if ville and not df_eq.empty and not df_clients.empty:
            # Get clients in this ville
            clients_in_ville = df_clients[
                df_clients["ville"].notna() & 
                (df_clients["ville"].astype(str).str.lower().str.strip() == ville.lower().strip())
            ]["nom"].tolist() if "ville" in df_clients.columns else []
            
            # Filter equipements by these clients
            if clients_in_ville and "Client" in df_eq.columns:
                df_eq = df_eq[df_eq["Client"].astype(str).isin(clients_in_ville)]

        # Filter equipements by equipment type
        if equipment_type and not df_eq.empty and "Type" in df_eq.columns:
            df_eq = df_eq[df_eq["Type"].notna() & (df_eq["Type"].astype(str).str.lower().str.strip() == equipment_type.lower().strip())]

        # Filter interventions by date range. Closed interventions are scored on
        # closure date so repaired equipment can recover over time.
        if not df_int.empty and "date" in df_int.columns:
            df_int["date"] = pd.to_datetime(df_int["date"], errors="coerce")
            if "date_cloture" in df_int.columns:
                df_int["date_cloture"] = pd.to_datetime(df_int["date_cloture"], errors="coerce")
                df_int["score_date"] = df_int["date_cloture"].fillna(df_int["date"])
            else:
                df_int["score_date"] = df_int["date"]
            if date_start:
                df_int = df_int[df_int["score_date"] >= pd.to_datetime(date_start)]
            if date_end:
                date_end_exclusive = pd.to_datetime(date_end) + pd.Timedelta(days=1)
                df_int = df_int[df_int["score_date"] < date_end_exclusive]

        scores = []

        if df_eq.empty:
            return []

        import datetime as _dt
        today = pd.Timestamp(_dt.date.today())

        def _norm(value: Any) -> str:
            text = unicodedata.normalize("NFD", str(value or "").strip().lower())
            return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")

        def _is_closed(status: Any) -> bool:
            status_key = _norm(status)
            return any(token in status_key for token in [
                "cloturee", "terminee", "completee", "closed", "resolved",
            ])

        def _is_cancelled(status: Any) -> bool:
            status_key = _norm(status)
            return any(token in status_key for token in [
                "annule", "refuse", "cancelled", "canceled",
            ])

        def _is_traceability(intervention_type: Any) -> bool:
            type_key = _norm(intervention_type)
            return any(token in type_key for token in ["installation", "formation"])

        def _is_preventive(intervention_type: Any) -> bool:
            type_key = _norm(intervention_type)
            return any(token in type_key for token in [
                "prevent", "preven", "controle", "inspection", "maintenance preventive",
            ])

        for _, eq in df_eq.iterrows():
            nom = eq.get("Nom", "")
            client_val = str(eq.get("Client", "") or "")
            statut = _norm(eq.get("Statut", ""))
            equipment_id = pd.to_numeric(pd.Series([eq.get("id")]), errors="coerce").iloc[0]

            pannes = 0
            open_correctives = 0
            recent_correctives = 0
            latest_corrective_date = None
            corrective_penalty = 0
            preventive_bonus = 0

            if not df_int.empty:
                if pd.notna(equipment_id) and "equipement_id" in df_int.columns:
                    intervention_equipment_ids = pd.to_numeric(df_int["equipement_id"], errors="coerce")
                    # Name matching is retained only for unmigrated historical
                    # rows that have no equipment_id yet.
                    legacy_name_match = pd.Series(False, index=df_int.index)
                    if "machine" in df_int.columns:
                        legacy_name_match = (
                            intervention_equipment_ids.isna()
                            & (df_int["machine"].map(_norm) == _norm(nom))
                        )
                    df_machine = df_int[
                        (intervention_equipment_ids == int(equipment_id)) | legacy_name_match
                    ]
                elif "machine" in df_int.columns:
                    df_machine = df_int[df_int["machine"].map(_norm) == _norm(nom)]
                else:
                    df_machine = df_int.iloc[0:0]

                for _, intervention in df_machine.iterrows():
                    intervention_type = intervention.get("type_intervention", "")
                    if _is_traceability(intervention_type):
                        continue
                    if _is_cancelled(intervention.get("statut", "")):
                        continue

                    score_date = intervention.get("score_date")
                    if pd.isna(score_date):
                        score_date = intervention.get("date")
                    if pd.isna(score_date):
                        continue

                    days_since = max(0, int((today - pd.Timestamp(score_date).normalize()).days))
                    is_closed = _is_closed(intervention.get("statut", ""))

                    if _is_preventive(intervention_type):
                        if is_closed and days_since <= 180:
                            preventive_bonus += 3
                        continue

                    pannes += 1
                    latest_corrective_date = (
                        pd.Timestamp(score_date)
                        if latest_corrective_date is None
                        else max(latest_corrective_date, pd.Timestamp(score_date))
                    )
                    if days_since <= 90:
                        recent_correctives += 1

                    if not is_closed:
                        open_correctives += 1
                        corrective_penalty += 25
                    elif days_since <= 30:
                        corrective_penalty += 15
                    elif days_since <= 90:
                        corrective_penalty += 8
                    elif days_since <= 180:
                        corrective_penalty += 4
                    elif days_since <= 365:
                        corrective_penalty += 1

            stability_bonus = 0
            if open_correctives == 0:
                if latest_corrective_date is None:
                    stability_bonus = 10
                elif (today - latest_corrective_date.normalize()).days > 90:
                    stability_bonus = 10

            score = 100 - corrective_penalty + min(preventive_bonus, 10) + stability_bonus
            score = max(0, min(100, round(score)))

            # Current equipment status remains authoritative.
            if statut == "hors service":
                score = min(score, 25)
            elif statut in {"critique", "en panne"}:
                score = min(score, 45)
            elif statut in {"en atelier", "en maintenance", "maintenance"}:
                score = min(score, 60)

            tendance = "stable"
            if open_correctives > 0 or recent_correctives >= 2:
                tendance = "baisse"
            elif open_correctives == 0 and (pannes == 0 or stability_bonus > 0 or preventive_bonus > 0):
                tendance = "hausse"

            scores.append({
                "equipment_id": int(equipment_id) if pd.notna(equipment_id) else None,
                "machine": nom,
                "score": score,
                "tendance": tendance,
                "pannes": pannes,
                "client": client_val,
            })

        return sorted(scores, key=lambda x: x["score"])
    except Exception as e:
        logger.error(f"Erreur get_health_scores: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# ÉQUIPEMENTS
# ==========================================

__all__ = [
    "root",
    "login",
    "me",
    "_get_client_filter",
    "get_dashboard_kpis",
    "get_health_scores",
]
