#!/usr/bin/env python3
"""
Fix intervention IDs to be unique (remove duplicates and regenerate)
"""

import os
import sys
import psycopg2
from datetime import datetime, timedelta
import random

sys.path.insert(0, os.path.dirname(__file__))

def get_connection():
    """Get a direct database connection."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('POSTGRES_USER', 'savia_user'),
            password=os.getenv('POSTGRES_PASSWORD', 'savia_password_secure_2026'),
            database=os.getenv('POSTGRES_DB', 'savia_db'),
            port=os.getenv('DB_PORT', 5432)
        )
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

def fix_intervention_ids():
    """Remove duplicates and ensure unique intervention IDs."""
    conn = get_connection()
    if not conn:
        return
    
    try:
        cur = conn.cursor()
        
        # Check for duplicate IDs
        cur.execute("""
            SELECT id, COUNT(*) as count
            FROM interventions
            GROUP BY id
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        """)
        
        duplicates = cur.fetchall()
        if duplicates:
            print(f"⚠️  Found {len(duplicates)} duplicate IDs:")
            for intervention_id, count in duplicates[:10]:  # Show first 10
                print(f"   ID {intervention_id}: appears {count} times")
        
        # Get all interventions sorted by date
        cur.execute("""
            SELECT id, date, machine, technicien, type_intervention, description, statut, priorite, duree_minutes, cout, cout_pieces
            FROM interventions
            ORDER BY date ASC, id ASC
        """)
        
        interventions = cur.fetchall()
        print(f"\n📊 Found {len(interventions)} total interventions")
        
        # Delete all interventions
        cur.execute("DELETE FROM interventions")
        print(f"🗑️  Cleared all interventions")
        
        # Recreate with unique sequential IDs
        print(f"🔄 Recreating interventions with unique IDs...")
        
        for new_id, (old_id, date, machine, technicien, type_intervention, description, statut, priorite, duree_minutes, cout, cout_pieces) in enumerate(interventions, 1):
            cur.execute("""
                INSERT INTO interventions 
                (id, date, machine, technicien, type_intervention, description, statut, priorite, duree_minutes, cout, cout_pieces)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (new_id, date, machine, technicien, type_intervention, description, statut, priorite, duree_minutes, cout, cout_pieces))
            
            if new_id % 50 == 0:
                print(f"   Recreated {new_id}/{len(interventions)} interventions...")
        
        conn.commit()
        print(f"✅ Successfully recreated {len(interventions)} interventions with unique IDs (1-{len(interventions)})")
        
        # Verify no duplicates
        cur.execute("""
            SELECT COUNT(*) as total, COUNT(DISTINCT id) as unique_count
            FROM interventions
        """)
        
        total, unique_count = cur.fetchone()
        print(f"\n📈 Verification:")
        print(f"   Total interventions: {total}")
        print(f"   Unique IDs: {unique_count}")
        
        if total == unique_count:
            print(f"   ✅ All IDs are unique!")
        else:
            print(f"   ❌ Still have duplicates!")
        
        cur.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    fix_intervention_ids()
