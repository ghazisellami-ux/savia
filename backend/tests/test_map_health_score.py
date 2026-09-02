from controllers import finance


def test_map_status_fallback_scores_degraded_equipment_below_100():
    assert finance._map_status_score("Hors Service") == 25
    assert finance._map_status_score("Critique") == 45
    assert finance._map_status_score("En atelier") == 60
    assert finance._map_status_score("En maintenance") == 75
    assert finance._map_status_score("Opérationnel") == 100


def test_map_health_key_matches_equipment_and_client_names_case_insensitively():
    assert finance._map_health_key(" Scanner A ") == finance._map_health_key("scanner a")
    assert finance._map_health_key("Clinique A") == finance._map_health_key("CLINIQUE A")


def test_map_site_score_averages_detailed_equipment_scores():
    score = finance._map_site_score(
        "Clinique A",
        [
            {"nom": "Scanner A", "statut": "Opérationnel"},
            {"nom": "Scanner B", "statut": "Opérationnel"},
        ],
        {
            ("scanner a", "clinique a"): 42,
            ("scanner b", "clinique a"): 86,
        },
    )
    assert score == 64
