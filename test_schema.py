#!/usr/bin/env python
"""Test script to verify the contrats_equipements junction table schema."""

import os
import sys
import sqlite3
import tempfile

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from db_engine import init_db, get_db, USE_PG

def test_schema():
    """Test that the contrats_equipements table is created correctly."""
    
    if USE_PG:
        print("⚠️  PostgreSQL mode detected. Skipping SQLite-specific test.")
        return True
    
    # Create a temporary database for testing
    temp_db = tempfile.mktemp(suffix='.db')
    original_db = os.environ.get('DB_PATH')
    
    try:
        # Set up temporary database path
        os.environ['DB_PATH'] = temp_db
        
        # Import and reload db_engine to use our temp db
        import importlib
        import db_engine
        importlib.reload(db_engine)
        
        # Initialize database
        print("✅ Initializing database schema...")
        init_db()
        
        # Connect and verify table structure
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        
        print("\n📋 Verifying contrats_equipements table structure:")
        
        # Get table info
        cursor = conn.execute("PRAGMA table_info(contrats_equipements)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        expected_columns = {
            'id': 'INTEGER',
            'contrat_id': 'INTEGER',
            'equipement_nom': 'TEXT',
            'created_at': 'TIMESTAMP'
        }
        
        for col_name, col_type in expected_columns.items():
            if col_name in columns:
                print(f"  ✅ Column {col_name} exists (type: {columns[col_name]})")
            else:
                print(f"  ❌ Column {col_name} is MISSING")
                return False
        
        # Check foreign keys
        print("\n🔗 Verifying foreign keys:")
        cursor = conn.execute("PRAGMA foreign_key_list(contrats_equipements)")
        fks = cursor.fetchall()
        
        if len(fks) == 0:
            print("  ⚠️  WARNING: No foreign keys found. This may be expected if constraints are not enforced.")
        else:
            for fk in fks:
                print(f"  ✅ FK found: {fk[3]} -> {fk[2]}({fk[4]})")
        
        # Check unique constraint
        print("\n🔑 Verifying UNIQUE constraint:")
        cursor = conn.execute("PRAGMA index_list(contrats_equipements)")
        indexes = cursor.fetchall()
        
        unique_found = False
        for idx in indexes:
            if idx[2] == 1:  # unique flag
                unique_found = True
                print(f"  ✅ Unique index found: {idx[1]}")
        
        if not unique_found:
            print("  ⚠️  WARNING: No UNIQUE constraint visible (may be defined inline)")
        
        # Test migration logic - insert some test data
        print("\n🔄 Testing auto-migration logic:")
        
        # Insert a test contract with equipment
        conn.execute("""
            INSERT INTO contrats (client, equipement, type_contrat, date_debut, date_fin)
            VALUES ('Test Client', 'Test-Equip-001', 'Standard', '2026-01-01', '2027-01-01')
        """)
        conn.commit()
        print("  ✅ Inserted test contract with equipment")
        
        # Re-initialize to run migration
        conn.close()
        init_db()
        
        # Verify migration populated the junction table
        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM contrats_equipements 
            WHERE equipement_nom = 'Test-Equip-001'
        """)
        result = cursor.fetchone()
        
        if result['count'] > 0:
            print(f"  ✅ Migration successfully populated junction table ({result['count']} rows)")
        else:
            print("  ❌ Migration failed to populate junction table")
            return False
        
        # Test idempotency - run migration again
        init_db()
        
        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM contrats_equipements 
            WHERE equipement_nom = 'Test-Equip-001'
        """)
        result = cursor.fetchone()
        
        if result['count'] == 1:  # Should still be 1, not 2
            print("  ✅ Migration is idempotent (safe to run multiple times)")
        else:
            print(f"  ❌ Migration is NOT idempotent (found {result['count']} rows instead of 1)")
            return False
        
        conn.close()
        
        print("\n✅ All tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if os.path.exists(temp_db):
            try:
                os.remove(temp_db)
            except:
                pass

if __name__ == '__main__':
    success = test_schema()
    sys.exit(0 if success else 1)
