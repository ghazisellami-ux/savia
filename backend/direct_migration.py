#!/usr/bin/env python3
"""
Direct migration script to add is_ghost column and Décalé status to planning_maintenance
Exécutez ceci dans le terminal Coolify pour fixer les migrations
"""
import psycopg2
import os
import sys

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://savia_user:savia_password_secure_2026@savia-db:5432/savia-db')

print("🔗 Connecting to PostgreSQL...")
try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    print("✅ Connected!")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    sys.exit(1)

# Step 1: Add is_ghost column
print("\n1️⃣ Adding is_ghost column...")
try:
    cur.execute("""
        ALTER TABLE planning_maintenance 
        ADD COLUMN is_ghost BOOLEAN DEFAULT false
    """)
    conn.commit()
    print("✅ Column is_ghost added!")
except psycopg2.errors.DuplicateColumn:
    print("ℹ️ Column is_ghost already exists")
    conn.rollback()
except Exception as e:
    print(f"❌ Error: {e}")
    conn.rollback()
    sys.exit(1)

# Step 2: Check current constraint
print("\n2️⃣ Checking current statut constraint...")
try:
    cur.execute("""
        SELECT constraint_name, check_clause 
        FROM information_schema.check_constraints 
        WHERE constraint_name LIKE 'planning_maintenance%'
    """)
    constraints = cur.fetchall()
    
    if constraints:
        for constraint_name, check_clause in constraints:
            print(f"  Found: {constraint_name}")
            print(f"  Clause: {check_clause}")
            
            if check_clause and 'Décalé' in check_clause:
                print("  ✅ 'Décalé' already in constraint")
            else:
                print("  ⚠️ 'Décalé' NOT in constraint, updating...")
                # Drop old constraint
                cur.execute(f"ALTER TABLE planning_maintenance DROP CONSTRAINT {constraint_name}")
                # Add new constraint
                cur.execute("""
                    ALTER TABLE planning_maintenance 
                    ADD CONSTRAINT planning_maintenance_statut_check 
                    CHECK (statut IN ('Planifiée', 'En cours', 'Terminée', 'En retard', 'Décalé'))
                """)
                conn.commit()
                print("  ✅ Constraint updated!")
    else:
        print("  ℹ️ No existing constraint found, creating new one...")
        cur.execute("""
            ALTER TABLE planning_maintenance 
            ADD CONSTRAINT planning_maintenance_statut_check 
            CHECK (statut IN ('Planifiée', 'En cours', 'Terminée', 'En retard', 'Décalé'))
        """)
        conn.commit()
        print("  ✅ Constraint created!")
except Exception as e:
    print(f"❌ Error: {e}")
    conn.rollback()
    sys.exit(1)

# Step 3: Verify
print("\n3️⃣ Verifying migrations...")
try:
    # Check is_ghost column
    cur.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name='planning_maintenance' AND column_name='is_ghost'
    """)
    if cur.fetchone():
        print("  ✅ is_ghost column verified!")
    else:
        print("  ❌ is_ghost column NOT found!")
        sys.exit(1)
    
    # Check constraint
    cur.execute("""
        SELECT check_clause FROM information_schema.check_constraints 
        WHERE constraint_name LIKE 'planning_maintenance%'
    """)
    result = cur.fetchone()
    if result and 'Décalé' in result[0]:
        print("  ✅ 'Décalé' in constraint verified!")
    else:
        print("  ❌ 'Décalé' NOT in constraint!")
        sys.exit(1)
except Exception as e:
    print(f"❌ Verification error: {e}")
    sys.exit(1)

cur.close()
conn.close()

print("\n✅ All migrations completed successfully!")
print("🚀 The reschedule feature should now work!")
