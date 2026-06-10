#!/usr/bin/env python3
"""
Script de migration pour ajouter la colonne is_ghost à la table planning_maintenance
sur PostgreSQL (VPS Coolify)
"""
import os
import sys
import psycopg2
from psycopg2 import sql

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://savia_user:savia_password_secure_2026@savia-db:5432/savia-db")

print(f"📊 Connecting to: {DATABASE_URL}")

try:
    # Connect to PostgreSQL
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Add is_ghost column if it doesn't exist
    print("🔧 Adding is_ghost column to planning_maintenance...")
    cursor.execute("""
        ALTER TABLE planning_maintenance 
        ADD COLUMN IF NOT EXISTS is_ghost BOOLEAN DEFAULT false
    """)
    conn.commit()
    print("✅ Column is_ghost added successfully!")
    
    # Verify the column exists
    cursor.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name='planning_maintenance' AND column_name='is_ghost'
    """)
    result = cursor.fetchone()
    
    if result:
        print(f"✅ Verified: is_ghost column exists!")
    else:
        print("❌ ERROR: is_ghost column not found after migration!")
        sys.exit(1)
    
    # Check current constraint on statut
    print("\n🔍 Checking statut CHECK constraint...")
    cursor.execute("""
        SELECT constraint_name, constraint_definition 
        FROM information_schema.table_constraints tc 
        JOIN information_schema.check_constraints cc 
        ON tc.constraint_name = cc.constraint_name 
        WHERE tc.table_name='planning_maintenance' AND tc.constraint_type='CHECK'
    """)
    constraints = cursor.fetchall()
    
    if constraints:
        for constraint_name, constraint_def in constraints:
            print(f"  Found: {constraint_name}")
            print(f"  Definition: {constraint_def}")
            
            # Check if "Décalé" is in the constraint
            if 'Décalé' in constraint_def:
                print("  ✅ 'Décalé' status is already in the constraint!")
            else:
                print("  ⚠️  'Décalé' status NOT found in constraint")
                print("  🔧 Adding 'Décalé' to constraint...")
                
                # Drop old constraint
                cursor.execute(f"ALTER TABLE planning_maintenance DROP CONSTRAINT {constraint_name}")
                
                # Add new constraint with 'Décalé'
                cursor.execute("""
                    ALTER TABLE planning_maintenance 
                    ADD CONSTRAINT planning_maintenance_statut_check 
                    CHECK (statut IN ('Planifiée', 'En cours', 'Terminée', 'En retard', 'Décalé'))
                """)
                conn.commit()
                print("  ✅ Constraint updated with 'Décalé' status!")
    else:
        print("  ❌ No CHECK constraint found on statut!")
        print("  🔧 Creating new constraint...")
        cursor.execute("""
            ALTER TABLE planning_maintenance 
            ADD CONSTRAINT planning_maintenance_statut_check 
            CHECK (statut IN ('Planifiée', 'En cours', 'Terminée', 'En retard', 'Décalé'))
        """)
        conn.commit()
        print("  ✅ Constraint created!")
    
    cursor.close()
    conn.close()
    
    print("\n✅ All migrations completed successfully!")
    print("🚀 The 'Décaler et Réassigner' feature should now work!")
    
except psycopg2.Error as e:
    print(f"❌ Database error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
