from services.contract_billing import (
    assess_contract_coverage,
    assess_intervention_contract_coverage_in_savepoint,
    parse_included_parts,
    parse_used_parts,
)


def contract(contract_type="Full Service", **overrides):
    values = {
        "id": 7,
        "type_contrat": contract_type,
        "avec_pieces": False,
        "pieces_incluses": "",
    }
    values.update(overrides)
    return values


def assess(**overrides):
    values = {
        "labor_amount": 300,
        "parts_amount": 450,
        "used_parts": [{"ref": "P-001", "qty": 1}],
        "contract": contract(),
        "linked_from_planning": True,
        "part_prices": {"P-001": 450},
    }
    values.update(overrides)
    return assess_contract_coverage(**values)


def test_full_service_is_fully_covered():
    result = assess()

    assert result["coverage_status"] == "covered"
    assert result["contract_id"] == 7
    assert result["uncovered_labor_cost"] == 0
    assert result["uncovered_parts_cost"] == 0
    assert result["uncovered_total_cost"] == 0


def test_labor_only_contract_marks_only_parts_outside_coverage():
    result = assess(contract=contract("Main d'œuvre uniquement"))

    assert result["coverage_status"] == "partial"
    assert result["uncovered_labor_cost"] == 0
    assert result["uncovered_parts_cost"] == 450
    assert result["uncovered_total_cost"] == 450
    assert "billable_total_amount" not in result


def test_included_part_quota_marks_only_excess_cost_outside_coverage():
    result = assess(
        labor_amount=0,
        parts_amount=300,
        used_parts=[{"ref": "P-001", "qty": 3}],
        contract=contract(
            "Pièces incluses",
            avec_pieces=True,
            pieces_incluses='[{"ref":"P-001","designation":"Carte","quota":3}]',
        ),
        linked_from_planning=False,
        previous_part_usage={"P-001": 2},
        part_prices={"P-001": 100},
    )

    assert result["coverage_status"] == "partial"
    assert result["uncovered_parts_cost"] == 200
    assert result["coverage_details"]["parts"][0]["covered_qty"] == 1


def test_missing_contract_is_fully_billable():
    result = assess(contract=None)

    assert result["coverage_status"] == "billable"
    assert result["uncovered_total_cost"] == 750


def test_eligibility_does_not_depend_on_cost_of_service_amounts():
    result = assess(
        labor_amount=0,
        parts_amount=0,
        used_parts=[{"ref": "P-001", "qty": 1}],
        contract=contract("Main d'œuvre uniquement"),
        part_prices={},
    )

    assert result["coverage_status"] == "partial"
    assert result["uncovered_total_cost"] == 0


def test_preventive_recurrence_does_not_cover_an_unplanned_extra_visit():
    result = assess(
        labor_amount=200,
        parts_amount=0,
        used_parts=[],
        contract=contract("Maintenance Préventive"),
        linked_from_planning=False,
        intervention_type="Préventive",
    )

    assert result["coverage_status"] == "billable"
    assert result["uncovered_labor_cost"] == 200


def test_ambiguous_contract_requires_review_and_blocks_automatic_invoice():
    result = assess(ambiguity_reason="Deux contrats correspondent")

    assert result["coverage_status"] == "review"
    assert result["coverage_reason"] == "Deux contrats correspondent"


def test_part_formats_are_parsed_with_quotas_and_quantities():
    used = parse_used_parts("Carte RX | Ref: P-001 | Fournisseur: ACME | Qty: 2")
    included = parse_included_parts('[{"ref":"P-001","designation":"Carte RX","quota":4}]')

    assert used == [{"ref": "P-001", "qty": 2}]
    assert included["p-001"]["quota"] == 4


def test_contract_assessment_failure_is_rolled_back_to_its_savepoint(monkeypatch):
    statements = []

    class Connection:
        def execute(self, statement, params=None):
            statements.append(statement)

    def fail_assessment(conn, intervention_id, *, actor="system"):
        raise RuntimeError("broken assessment")

    monkeypatch.setattr(
        "services.contract_billing.assess_intervention_contract_coverage",
        fail_assessment,
    )

    try:
        assess_intervention_contract_coverage_in_savepoint(Connection(), 82)
    except RuntimeError as exc:
        assert str(exc) == "broken assessment"
    else:
        raise AssertionError("The assessment error should be propagated to the caller")

    assert statements == [
        "SAVEPOINT contract_coverage_assessment",
        "ROLLBACK TO SAVEPOINT contract_coverage_assessment",
        "RELEASE SAVEPOINT contract_coverage_assessment",
    ]
