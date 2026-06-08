#!/usr/bin/env python3
"""
Fix Mammographe type to Mammographie in both pieces_rechange and equipements tables
"""

import os
import sys
import psycopg2

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

def fix_types():
    """Update Mammographe to Mammographie in both pieces_rechange and equipements tables."""
    conn = get_connection()
    if not conn:
        return
    
    try:
        cur = conn.cursor()
        
        # ===== FIX PIECES_RECHANGE =====
        print("🔧 Fixing pieces_rechange table...")
        
        # Check current types in pieces_rechange
        cur.execute("""
            SELECT equipement_type, COUNT(*) 
            FROM pieces_rechange 
            WHERE equipement_type IS NOT NULL
            GROUP BY equipement_type
            ORDER BY equipement_type
        """)
        
        print("   📊 Current equipment types:")
        current_types = cur.fetchall()
        for eq_type, count in current_types:
            print(f"      {eq_type}: {count} pieces")
        
        # Update Mammographe to Mammographie in pieces_rechange
        cur.execute("""
            UPDATE pieces_rechange 
            SET equipement_type = 'Mammographie'
            WHERE equipement_type = 'Mammographe'
        """)
        
        updated_pieces = cur.rowcount
        
        if updated_pieces > 0:
            print(f"   ✅ Updated {updated_pieces} pieces from 'Mammographe' to 'Mammographie'")
        else:
            print(f"   ⚠️  No pieces found with type 'Mammographe'")
        
        # Verify pieces_rechange change
        cur.execute("""
            SELECT equipement_type, COUNT(*) 
            FROM pieces_rechange 
            WHERE equipement_type IS NOT NULL
            GROUP BY equipement_type
            ORDER BY equipement_type
        """)
        
        print("   📊 Equipment types after fix:")
        new_types = cur.fetchall()
        for eq_type, count in new_types:
            print(f"      {eq_type}: {count} pieces")
        
        # ===== FIX EQUIPEMENTS =====
        print("\n🔧 Fixing equipements table...")
        
        # Check current types in equipements
        cur.execute("""
            SELECT type, COUNT(*) 
            FROM equipements 
            WHERE type IS NOT NULL
            GROUP BY type
            ORDER BY type
        """)
        
        print("   📊 Current equipment types:")
        current_eq_types = cur.fetchall()
        for eq_type, count in current_eq_types:
            print(f"      {eq_type}: {count} equipements")
        
        # Update Mammographe to Mammographie in equipements
        cur.execute("""
            UPDATE equipements 
            SET type = 'Mammographie'
            WHERE type = 'Mammographe'
        """)
        
        updated_eq = cur.rowcount
        
        if updated_eq > 0:
            print(f"   ✅ Updated {updated_eq} equipements from 'Mammographe' to 'Mammographie'")
        else:
            print(f"   ⚠️  No equipements found with type 'Mammographe'")
        
        # Verify equipements change
        cur.execute("""
            SELECT type, COUNT(*) 
            FROM equipements 
            WHERE type IS NOT NULL
            GROUP BY type
            ORDER BY type
        """)
        
        print("   📊 Equipment types after fix:")
        new_eq_types = cur.fetchall()
        for eq_type, count in new_eq_types:
            print(f"      {eq_type}: {count} equipements")
        
        conn.commit()
        print(f"\n✅ Successfully updated {updated_pieces} pieces and {updated_eq} equipements")
        
        cur.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    fix_types()
