#!/usr/bin/env python
"""
Migration script to convert VPS database schema from equipement_nom to equipement_id.

PROBLEM:
- VPS database has: contrats_equipements(id, contrat_id, equipement_nom TEXT)
- Local database has: contrats_equipements(id, contrat_id, equipement_id INTEGER FK)
- This schema mismatch causes query failures when generating planning/interventions

SOLUTION:
This script converts the VPS schema to the standard schema by:
1. Adding equipement_id column to contrats_equipements (if not exists)
2. Populating equipement_id by joining equipements table with equipement_nom
3. Removing the equipement_nom column
4. Adding FOREIGN KEY constraint

USAGE:
    python migrate_vps_schema.py <database_url>
    
EXAMPLE:
    python migrate_vps_schema.py postgresql://user:password@localhost:5432/savia_db

SAFETY:
- Creates a backup of the table before migration
- Idempotent: can be run multiple times without issues
- Validates data integrity after migration
- Logs all actions for audit trail
"""

import psycopg2
import sys
import logging
from datetime import datetime
from urllib.parse import urlparse

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'migration_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def parse_db_url(db_url):
    """Parse database URL into connection parameters."""
    parsed = urlparse(db_url)
    return {
        'host': parsed.hostname or 'localhost',
        'port': parsed.port or 5432,
        'user': parsed.username or 'postgres',
        'password': parsed.password or '',
        'database': parsed.path.lstrip('/') or 'savia_db'
    }


def connect_db(db_params):
    """Create database connection."""
    try:
        conn = psycopg2.connect(**db_params)
        logger.info("✅ Database connection established")
        return conn
    except Exception as e:
        logger.error(f"❌ Failed to connect to database: {e}")
        raise


def check_schema(conn):
    """Check current schema of contrats_equipements table."""
    cursor = conn.cursor()
    
    try:
        # Get table columns
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'contrats_equipements'
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()
        
        logger.info("Current contrats_equipements schema:")
        for col_name, col_type in columns:
            logger.info(f"  - {col_name}: {col_type}")
        
        # Check if equipement_nom exists (VPS schema)
        has_equipement_nom = any(col[0] == 'equipement_nom' for col in columns)
        # Check if equipement_id exists (standard schema)
        has_equipement_id = any(col[0] == 'equipement_id' for col in columns)
        
        return {
            'columns': columns,
            'has_equipement_nom': has_equipement_nom,
            'has_equipement_id': has_equipement_id
        }
    finally:
        cursor.close()


def migrate_schema(conn, db_params):
    """
    Perform the schema migration.
    Converts from VPS schema (equipement_nom) to standard schema (equipement_id).
    """
    cursor = conn.cursor()
    
    try:
        # Step 1: Check current schema
        logger.info("\n" + "="*70)
        logger.info("STEP 1: Checking current schema")
        logger.info("="*70)
        
        schema_info = check_schema(conn)
        
        if not schema_info['has_equipement_nom']:
            logger.info("✅ equipement_nom column does not exist - already migrated or never existed")
            if schema_info['has_equipement_id']:
                logger.info("✅ equipement_id column exists - schema is correct")
                return True
            else:
                logger.error("❌ Neither equipement_nom nor equipement_id found - schema is invalid")
                return False
        
        logger.info("⚠️  VPS schema detected (equipement_nom exists) - migration required")
        
        # Step 2: Create backup
        logger.info("\n" + "="*70)
        logger.info("STEP 2: Creating backup")
        logger.info("="*70)
        
        backup_table = f"contrats_equipements_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cursor.execute(f"CREATE TABLE {backup_table} AS SELECT * FROM contrats_equipements")
        conn.commit()
        logger.info(f"✅ Backup created: {backup_table}")
        
        # Step 3: Add equipement_id column if it doesn't exist
        logger.info("\n" + "="*70)
        logger.info("STEP 3: Adding equipement_id column")
        logger.info("="*70)
        
        if not schema_info['has_equipement_id']:
            cursor.execute("""
                ALTER TABLE contrats_equipements 
                ADD COLUMN equipement_id INTEGER
            """)
            conn.commit()
            logger.info("✅ equipement_id column added")
        else:
            logger.info("✅ equipement_id column already exists")
        
        # Step 4: Populate equipement_id from equipement_nom
        logger.info("\n" + "="*70)
        logger.info("STEP 4: Populating equipement_id from equipement_nom")
        logger.info("="*70)
        
        # Update equipement_id by joining with equipements table
        cursor.execute("""
            UPDATE contrats_equipements ce
            SET equipement_id = e.id
            FROM equipements e
            WHERE ce.equipement_nom = e.nom
            AND ce.equipement_id IS NULL
        """)
        
        rows_updated = cursor.rowcount
        conn.commit()
        logger.info(f"✅ Updated {rows_updated} rows with equipement_id from equipement_nom")
        
        # Step 5: Check for unmapped equipment
        logger.info("\n" + "="*70)
        logger.info("STEP 5: Checking for unmapped equipment")
        logger.info("="*70)
        
        cursor.execute("""
            SELECT DISTINCT equipement_nom FROM contrats_equipements 
            WHERE equipement_id IS NULL AND equipement_nom IS NOT NULL
        """)
        unmapped = cursor.fetchall()
        
        if unmapped:
            logger.warning("⚠️  Found equipment names not found in equipements table:")
            for (equip_name,) in unmapped:
                logger.warning(f"  - '{equip_name}'")
            logger.warning("These will NOT be migrated. Please check equipements table or use manual mapping.")
        else:
            logger.info("✅ All equipment names successfully mapped to IDs")
        
        # Step 6: Verify data integrity
        logger.info("\n" + "="*70)
        logger.info("STEP 6: Verifying data integrity")
        logger.info("="*70)
        
        cursor.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN equipement_id IS NOT NULL THEN 1 ELSE 0 END) as with_id,
                   SUM(CASE WHEN equipement_id IS NULL THEN 1 ELSE 0 END) as without_id
            FROM contrats_equipements
        """)
        result = cursor.fetchone()
        total, with_id, without_id = result
        
        logger.info(f"Total records: {total}")
        logger.info(f"Records with equipement_id: {with_id}")
        logger.info(f"Records without equipement_id: {without_id}")
        
        if without_id > 0:
            logger.warning(f"⚠️  {without_id} records do not have equipement_id - consider manual review")
        
        # Step 7: Add foreign key constraint if it doesn't exist
        logger.info("\n" + "="*70)
        logger.info("STEP 7: Adding foreign key constraint")
        logger.info("="*70)
        
        # Check if FK already exists
        cursor.execute("""
            SELECT constraint_name FROM information_schema.table_constraints 
            WHERE table_name = 'contrats_equipements' 
            AND constraint_type = 'FOREIGN KEY'
            AND constraint_name LIKE '%equipement_id%'
        """)
        
        fk_exists = cursor.fetchone() is not None
        
        if not fk_exists:
            cursor.execute("""
                ALTER TABLE contrats_equipements
                ADD CONSTRAINT contrats_equipements_equipement_id_fkey
                FOREIGN KEY (equipement_id) REFERENCES equipements(id) ON DELETE RESTRICT
            """)
            conn.commit()
            logger.info("✅ Foreign key constraint added")
        else:
            logger.info("✅ Foreign key constraint already exists")
        
        # Step 8: Remove equipement_nom column (OPTIONAL - keep for backward compatibility if needed)
        logger.info("\n" + "="*70)
        logger.info("STEP 8: Removing equipement_nom column")
        logger.info("="*70)
        
        response = input("Remove equipement_nom column? (y/n): ").strip().lower()
        
        if response == 'y':
            cursor.execute("ALTER TABLE contrats_equipements DROP COLUMN equipement_nom")
            conn.commit()
            logger.info("✅ equipement_nom column removed")
        else:
            logger.info("⏭️  Keeping equipement_nom column for backward compatibility")
        
        # Final summary
        logger.info("\n" + "="*70)
        logger.info("✅ MIGRATION COMPLETED SUCCESSFULLY")
        logger.info("="*70)
        logger.info(f"Backup table: {backup_table}")
        logger.info("Next steps:")
        logger.info("1. Test contract creation on VPS")
        logger.info("2. Verify planning generation works")
        logger.info("3. Check telegram notifications are sent")
        logger.info("4. If all OK, optionally drop the backup table")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        conn.rollback()
        return False
    finally:
        cursor.close()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        logger.error("Usage: python migrate_vps_schema.py <database_url>")
        logger.error("Example: python migrate_vps_schema.py postgresql://user:password@localhost:5432/savia_db")
        sys.exit(1)
    
    db_url = sys.argv[1]
    
    try:
        logger.info("="*70)
        logger.info("VPS Schema Migration - contrats_equipements")
        logger.info("="*70)
        logger.info(f"Database: {db_url}")
        logger.info("")
        
        db_params = parse_db_url(db_url)
        conn = connect_db(db_params)
        
        success = migrate_schema(conn, db_params)
        
        conn.close()
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
