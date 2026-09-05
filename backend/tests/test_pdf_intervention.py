from contextlib import contextmanager

import pandas as pd
import pymupdf

import controllers.pdf_intervention as pdf_intervention
from controllers.pdf_intervention import _collect_technician_names, _fiche_display_date


def test_collect_technician_names_uses_assignments_when_legacy_field_has_only_one_name():
    names = _collect_technician_names(
        "Alice Martin",
        [
            {"technicien_nom": "Alice Martin"},
            {"technicien_nom": "Bob Diallo"},
        ],
        [],
    )

    assert names == ["Alice Martin", "Bob Diallo"]


def test_collect_technician_names_adds_session_technicians_without_duplicates():
    names = _collect_technician_names(
        "Alice Martin, Bob Diallo",
        [{"technicien_nom": "alice martin"}],
        [
            {"technicien_nom": "Bob Diallo"},
            {"technicien_nom": "Chloe Mensah"},
        ],
    )

    assert names == ["Alice Martin", "Bob Diallo", "Chloe Mensah"]


def test_fiche_display_date_prefers_closure_then_start_then_legacy_date():
    assert _fiche_display_date({
        "date": "2026-09-01",
        "date_debut_intervention": "2026-09-02 08:00:00",
        "date_cloture": "2026-09-03 16:30:00",
    }) == "2026-09-03"
    assert _fiche_display_date({
        "date": "2026-09-01",
        "date_debut_intervention": "2026-09-02 08:00:00",
    }) == "2026-09-02"
    assert _fiche_display_date({"date": "2026-09-01"}) == "2026-09-01"


def test_generated_pdf_shows_intervention_type_and_every_assigned_technician(monkeypatch, tmp_path):
    class FakeConnection:
        def execute(self, *_args, **_kwargs):
            return None

    @contextmanager
    def fake_get_db():
        yield FakeConnection()

    intervention = {
        "id": 39,
        "date": "2026-09-05",
        "date_debut_intervention": "2026-09-06 08:00:00",
        "date_cloture": "2026-09-07 17:00:00",
        "client": "Hopital Central",
        "machine": "Analyseur X100",
        "technicien": "Alice Martin",
        "type_intervention": "Préventive",
        "statut": "Cloturee",
        "solution": "Controle general",
    }
    assignments = [
        {"technicien_nom": "Alice Martin"},
        {"technicien_nom": "Bob Diallo"},
    ]

    monkeypatch.setattr(pdf_intervention, "get_db", fake_get_db)
    monkeypatch.setattr(pdf_intervention, "assert_resource_client_access", lambda *_args: None)
    monkeypatch.setattr(pdf_intervention, "lire_interventions", lambda: pd.DataFrame([intervention]))
    monkeypatch.setattr(pdf_intervention, "lire_equipements", lambda: pd.DataFrame())
    monkeypatch.setattr(pdf_intervention, "lire_contrats", lambda: pd.DataFrame())
    monkeypatch.setattr("db_engine.get_interventions_techniciens", lambda _id: assignments)
    monkeypatch.setattr("db_engine.list_work_sessions", lambda _id: [])

    response = pdf_intervention.generate_fiche_intervention_pdf(39, {}, {"role": "admin"})
    output_path = tmp_path / "fiche_intervention_39.pdf"
    output_path.write_bytes(response.body)
    with pymupdf.open(output_path) as document:
        extracted_text = "\n".join(page.get_text() for page in document)

    assert "Technicien(s): Alice Martin, Bob Diallo" in extracted_text
    assert "Type d'intervention: Préventive" in extracted_text
    assert "Date: 2026-09-07" in extracted_text
