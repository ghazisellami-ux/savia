#!/usr/bin/env python3
"""
Test suite for multi-equipment contracts migration.

Tests the auto-migration from contrats.equipement (single) to contrats_equipements (junction table).
This migration runs automatically during init_db() startup and must be:
1. Idempotent (can be run multiple times without creating duplicates)
2. Handle NULL equipements gracefully
3. Migrate all non-null equipment values
4. Preserve backward compatibility

**Acceptance Criteria:**
✅ Table contrats_equipements created automatically
✅ All contracts with non-null equipement migrated to junction table
✅ No duplicates created on re-running migration
✅ Contracts with NULL equipement handled correctly
✅ Migration runs silently without breaking backend startup
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime, timedelta

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

# Set environment for testing (disable PostgreSQL, use SQLite)
# DO THIS BEFORE importing db_engine!
os.environ.pop("DATABASE_URL", None)
os.environ.pop("POSTGRES_USER", None)
os.environ.pop("POSTGRES_PASSWORD", None)
os.environ.pop("POSTGRES_DB", None)
os.environ.pop("POSTGRES_HOST", None)

# Setup logging to see migration messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("test_migration")

# Now import after environment is set
from db_engine import (
    init_db, get_db, ajouter_contrat, lire_contrats, 
    get_contract_equipements, modifier_contrat, generer_planning_from_contrat
)
from config import BASE_DIR

# Use test database
TEST_DB_PATH = os.path.join(BASE_DIR, "test_contracts_migration.db")


def setup_test_db():
    """Create a fresh test database."""
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    
    # Override DB path for testing
    import db_engine
    db_engine.DB_PATH = TEST_DB_PATH
    
    # Initialize database (this will run the migration)
    init_db()
    logger.info(f"✅ Test database created: {TEST_DB_PATH}")


def teardown_test_db():
    """Remove test database after tests."""
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
        logger.info("✅ Test database cleaned up")


def test_1_table_creation():
    """Test 1: Verify contrats_equipements table exists."""
    logger.info("\n" + "="*70)
    logger.info("TEST 1: Table Creation")
    logger.info("="*70)
    
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='contrats_equipements'
        """)
        result = cursor.fetchone()
    
    assert result is not None, "contrats_equipements table should exist"
    logger.info("✅ Table contrats_equipements exists")
    
    # Check columns
    with get_db() as conn:
        cursor = conn.execute("PRAGMA table_info(contrats_equipements)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
    
    expected_cols = {"id", "contrat_id", "equipement_nom", "created_at"}
    actual_cols = set(columns.keys())
    
    assert expected_cols.issubset(actual_cols), f"Missing columns. Expected: {expected_cols}, Got: {actual_cols}"
    logger.info(f"✅ All expected columns present: {expected_cols}")


def test_2_single_equipment_migration():
    """Test 2: Migrate contract with single equipment."""
    logger.info("\n" + "="*70)
    logger.info("TEST 2: Single Equipment Migration")
    logger.info("="*70)
    
    # Manually insert a contract with single equipment into contrats table
    with get_db() as conn:
        conn.execute("""
            INSERT INTO contrats 
            (client, equipement, type_contrat, date_debut, date_fin, 
             sla_temps_reponse_h, statut)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "Test Client 1",
            "IRM-001",
            "Maintenance Préventive",
            "2026-01-01",
            "2027-01-01",
            24,
            "Actif"
        ))
        
        # Get the ID
        row = conn.execute("SELECT MAX(id) as id FROM contrats").fetchone()
        contrat_id = row["id"]
    
    logger.info(f"✅ Created contract {contrat_id} with equipement='IRM-001'")
    
    # Now run the migration
    init_db()  # This re-runs migrations
    
    # Verify the equipment was migrated to junction table
    equipements = get_contract_equipements(contrat_id)
    assert "IRM-001" in equipements, f"Expected IRM-001 in equipements, got {equipements}"
    logger.info(f"✅ Equipment migrated correctly: {equipements}")


def test_3_multiple_contracts_migration():
    """Test 3: Migrate multiple contracts with different equipements."""
    logger.info("\n" + "="*70)
    logger.info("TEST 3: Multiple Contracts Migration")
    logger.info("="*70)
    
    test_data = [
        ("Client A", "Scanner-CT-01", "Maintenance Préventive"),
        ("Client B", "Radiographie-02", "Maintenance Corrective"),
        ("Client C", "Echographe-03", "Support Technique"),
    ]
    
    contract_ids = []
    with get_db() as conn:
        for client, equipement, type_contrat in test_data:
            conn.execute("""
                INSERT INTO contrats 
                (client, equipement, type_contrat, date_debut, date_fin, statut)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                client, equipement, type_contrat, 
                "2026-01-01", "2027-01-01", "Actif"
            ))
            row = conn.execute("SELECT MAX(id) as id FROM contrats").fetchone()
            contract_ids.append(row["id"])
        
        logger.info(f"✅ Created {len(contract_ids)} contracts")
    
    # Run migration
    init_db()
    
    # Verify all were migrated
    for idx, (client, equipement, _) in enumerate(test_data):
        equipements = get_contract_equipements(contract_ids[idx])
        assert equipement in equipements, \
            f"Contract {idx}: Expected {equipement}, got {equipements}"
        logger.info(f"✅ Contract {idx+1}: '{equipement}' migrated")


def test_4_null_equipment_handling():
    """Test 4: Handle contracts with NULL equipement gracefully."""
    logger.info("\n" + "="*70)
    logger.info("TEST 4: NULL Equipment Handling")
    logger.info("="*70)
    
    with get_db() as conn:
        conn.execute("""
            INSERT INTO contrats 
            (client, equipement, type_contrat, date_debut, date_fin, statut)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Client With Null",
            None,  # NULL equipement
            "Maintenance Préventive",
            "2026-01-01",
            "2027-01-01",
            "Actif"
        ))
        
        row = conn.execute("SELECT MAX(id) as id FROM contrats").fetchone()
        contrat_id = row["id"]
    
    logger.info(f"✅ Created contract {contrat_id} with equipement=NULL")
    
    # Run migration
    init_db()
    
    # Verify NULL contract has no junction entries (should be OK)
    equipements = get_contract_equipements(contrat_id)
    assert len(equipements) == 0, \
        f"NULL equipment should result in empty list, got {equipements}"
    logger.info(f"✅ NULL equipment handled correctly (no junction entries created)")


def test_5_empty_string_equipment():
    """Test 5: Handle contracts with empty string equipement."""
    logger.info("\n" + "="*70)
    logger.info("TEST 5: Empty String Equipment Handling")
    logger.info("="*70)
    
    with get_db() as conn:
        conn.execute("""
            INSERT INTO contrats 
            (client, equipement, type_contrat, date_debut, date_fin, statut)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Client With Empty",
            "",  # Empty equipement
            "Maintenance Préventive",
            "2026-01-01",
            "2027-01-01",
            "Actif"
        ))
        
        row = conn.execute("SELECT MAX(id) as id FROM contrats").fetchone()
        contrat_id = row["id"]
    
    logger.info(f"✅ Created contract {contrat_id} with equipement=''")
    
    # Run migration
    init_db()
    
    # Verify empty contract has no junction entries
    equipements = get_contract_equipements(contrat_id)
    assert len(equipements) == 0, \
        f"Empty equipment should result in empty list, got {equipements}"
    logger.info(f"✅ Empty equipment handled correctly (no junction entries created)")


def test_6_idempotence():
    """Test 6: Running migration multiple times doesn't create duplicates."""
    logger.info("\n" + "="*70)
    logger.info("TEST 6: Idempotence (No Duplicates on Re-run)")
    logger.info("="*70)
    
    # Insert a contract
    with get_db() as conn:
        conn.execute("""
            INSERT INTO contrats 
            (client, equipement, type_contrat, date_debut, date_fin, statut)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Idempotence Test",
            "IRM-Idempotent",
            "Maintenance Préventive",
            "2026-01-01",
            "2027-01-01",
            "Actif"
        ))
        
        row = conn.execute("SELECT MAX(id) as id FROM contrats").fetchone()
        contrat_id = row["id"]
    
    logger.info(f"✅ Created contract {contrat_id}")
    
    # Run migration first time
    init_db()
    
    with get_db() as conn:
        count1 = conn.execute(
            "SELECT COUNT(*) as cnt FROM contrats_equipements WHERE contrat_id=?",
            (contrat_id,)
        ).fetchone()["cnt"]
    logger.info(f"✅ After 1st migration: {count1} junction entries")
    
    # Run migration again
    init_db()
    
    with get_db() as conn:
        count2 = conn.execute(
            "SELECT COUNT(*) as cnt FROM contrats_equipements WHERE contrat_id=?",
            (contrat_id,)
        ).fetchone()["cnt"]
    logger.info(f"✅ After 2nd migration: {count2} junction entries")
    
    assert count1 == count2, \
        f"Migration not idempotent! Count changed from {count1} to {count2}"
    assert count1 == 1, f"Expected 1 junction entry, got {count1}"
    logger.info("✅ Migration is idempotent (no duplicates created)")


def test_7_create_with_multiple_equipements():
    """Test 7: Create contract with multiple equipements using new API."""
    logger.info("\n" + "="*70)
    logger.info("TEST 7: Create Contract with Multiple Equipements")
    logger.info("="*70)
    
    # First, ensure some equipements exist
    with get_db() as conn:
        for eq_name in ["IRM-Multi-A", "Scanner-Multi-B", "Radiographie-Multi-C"]:
            conn.execute("""
                INSERT OR IGNORE INTO equipements (nom, type, client)
                VALUES (?, ?, ?)
            """, (eq_name, "Imagerie", "Multi Client"))
    
    logger.info("✅ Created test equipements")
    
    # Create contract with multiple equipements
    contrat_id = ajouter_contrat({
        "client": "Multi Equipment Client",
        "equipements": ["IRM-Multi-A", "Scanner-Multi-B", "Radiographie-Multi-C"],
        "type_contrat": "Maintenance Préventive",
        "date_debut": "2026-01-01",
        "date_fin": "2027-01-01",
        "sla_temps_reponse_h": 24,
        "statut": "Actif"
    })
    
    logger.info(f"✅ Created contract {contrat_id} with 3 equipements")
    
    # Verify all 3 are stored
    equipements = get_contract_equipements(contrat_id)
    assert len(equipements) == 3, f"Expected 3 equipements, got {len(equipements)}"
    assert set(equipements) == {"IRM-Multi-A", "Scanner-Multi-B", "Radiographie-Multi-C"}
    logger.info(f"✅ All 3 equipements stored correctly: {equipements}")


def test_8_modify_equipements():
    """Test 8: Modify contract equipements list."""
    logger.info("\n" + "="*70)
    logger.info("TEST 8: Modify Contract Equipements")
    logger.info("="*70)
    
    # Ensure equipements exist
    with get_db() as conn:
        for eq_name in ["IRM-Mod-1", "Scanner-Mod-2", "Echo-Mod-3", "Mammo-Mod-4"]:
            conn.execute("""
                INSERT OR IGNORE INTO equipements (nom, type, client)
                VALUES (?, ?, ?)
            """, (eq_name, "Imagerie", "Modify Client"))
    
    # Create initial contract with 2 equipements
    contrat_id = ajouter_contrat({
        "client": "Modify Client",
        "equipements": ["IRM-Mod-1", "Scanner-Mod-2"],
        "type_contrat": "Maintenance Préventive",
        "date_debut": "2026-01-01",
        "date_fin": "2027-01-01",
        "sla_temps_reponse_h": 24,
        "statut": "Actif"
    })
    
    equipements = get_contract_equipements(contrat_id)
    assert len(equipements) == 2
    logger.info(f"✅ Initial equipements: {equipements}")
    
    # Modify to different equipements
    modifier_contrat(contrat_id, {
        "client": "Modify Client",
        "equipements": ["Echo-Mod-3", "Mammo-Mod-4"],  # Different set
        "type_contrat": "Maintenance Préventive",
        "date_debut": "2026-01-01",
        "date_fin": "2027-01-01",
        "sla_temps_reponse_h": 24,
        "statut": "Actif"
    })
    
    equipements = get_contract_equipements(contrat_id)
    assert len(equipements) == 2
    assert set(equipements) == {"Echo-Mod-3", "Mammo-Mod-4"}
    logger.info(f"✅ Modified equipements: {equipements}")


def test_9_planning_generation_multiple_equipements():
    """Test 9: Planning auto-generation for each equipment."""
    logger.info("\n" + "="*70)
    logger.info("TEST 9: Planning Generation for Multiple Equipements")
    logger.info("="*70)
    
    # Ensure equipements exist
    with get_db() as conn:
        for eq_name in ["IRM-Plan-A", "Scanner-Plan-B"]:
            conn.execute("""
                INSERT OR IGNORE INTO equipements (nom, type, client)
                VALUES (?, ?, ?)
            """, (eq_name, "Imagerie", "Plan Client"))
    
    # Create contract with planning
    today = datetime.now().date()
    contrat_id = ajouter_contrat({
        "client": "Plan Client",
        "equipements": ["IRM-Plan-A", "Scanner-Plan-B"],
        "type_contrat": "Maintenance Préventive",
        "date_debut": today.isoformat(),
        "date_fin": (today + timedelta(days=365)).isoformat(),
        "recurrence_maintenance": "Mensuelle",
        "date_premiere_maintenance": today.isoformat(),
        "sla_temps_reponse_h": 24,
        "statut": "Actif"
    })
    
    logger.info(f"✅ Created contract {contrat_id} with planning")
    
    # Generate planning
    count = generer_planning_from_contrat(contrat_id)
    logger.info(f"✅ Generated {count} planning entries")
    
    # Verify planning entries
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT machine FROM planning_maintenance WHERE contrat_id=?",
            (contrat_id,)
        ).fetchall()
        machines = [dict(row)["machine"] for row in rows]
    
    assert len(machines) == 2, f"Expected 2 different machines in planning, got {len(machines)}"
    assert set(machines) == {"IRM-Plan-A", "Scanner-Plan-B"}
    logger.info(f"✅ Planning entries created for: {machines}")


def test_10_backward_compatibility():
    """Test 10: Old single-equipement API still works."""
    logger.info("\n" + "="*70)
    logger.info("TEST 10: Backward Compatibility (Single Equipement API)")
    logger.info("="*70)
    
    # Ensure equipement exists
    with get_db() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO equipements (nom, type, client)
            VALUES (?, ?, ?)
        """, ("IRM-Compat", "Imagerie", "Compat Client"))
    
    # Use old API (single equipement string)
    contrat_id = ajouter_contrat({
        "client": "Compat Client",
        "equipement": "IRM-Compat",  # Old singular API
        "type_contrat": "Maintenance Préventive",
        "date_debut": "2026-01-01",
        "date_fin": "2027-01-01",
        "sla_temps_reponse_h": 24,
        "statut": "Actif"
    })
    
    logger.info(f"✅ Created contract using old API: equipement='IRM-Compat'")
    
    # Verify it still works (should be in junction table)
    equipements = get_contract_equipements(contrat_id)
    assert len(equipements) == 1
    assert equipements[0] == "IRM-Compat"
    logger.info(f"✅ Old API still works: {equipements}")


def main():
    """Run all tests."""
    logger.info("\n\n")
    logger.info("╔" + "="*68 + "╗")
    logger.info("║" + " MULTI-EQUIPMENT CONTRACTS MIGRATION TEST SUITE ".center(68) + "║")
    logger.info("╚" + "="*68 + "╝")
    
    try:
        # Setup
        setup_test_db()
        
        # Run tests
        tests = [
            ("Table Creation", test_1_table_creation),
            ("Single Equipment Migration", test_2_single_equipment_migration),
            ("Multiple Contracts Migration", test_3_multiple_contracts_migration),
            ("NULL Equipment Handling", test_4_null_equipment_handling),
            ("Empty String Equipment", test_5_empty_string_equipment),
            ("Idempotence", test_6_idempotence),
            ("Create Multiple Equipements", test_7_create_with_multiple_equipements),
            ("Modify Equipements", test_8_modify_equipements),
            ("Planning Generation", test_9_planning_generation_multiple_equipements),
            ("Backward Compatibility", test_10_backward_compatibility),
        ]
        
        passed = 0
        failed = 0
        
        for name, test_func in tests:
            try:
                test_func()
                passed += 1
            except AssertionError as e:
                logger.error(f"❌ TEST FAILED: {name}")
                logger.error(f"   Error: {e}")
                failed += 1
            except Exception as e:
                logger.error(f"❌ TEST ERROR: {name}")
                logger.error(f"   Exception: {e}")
                failed += 1
        
        # Summary
        logger.info("\n\n")
        logger.info("╔" + "="*68 + "╗")
        logger.info("║" + " TEST SUMMARY ".center(68) + "║")
        logger.info("║" + "-"*68 + "║")
        logger.info(f"║ PASSED: {passed:<60}║")
        logger.info(f"║ FAILED: {failed:<60}║")
        logger.info("║" + "-"*68 + "║")
        
        if failed == 0:
            logger.info("║" + " ✅ ALL TESTS PASSED ".center(68) + "║")
        else:
            logger.info("║" + " ❌ SOME TESTS FAILED ".center(68) + "║")
        
        logger.info("╚" + "="*68 + "╝\n")
        
        return 0 if failed == 0 else 1
        
    finally:
        # Cleanup
        teardown_test_db()


if __name__ == "__main__":
    sys.exit(main())
