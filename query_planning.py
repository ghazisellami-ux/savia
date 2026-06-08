#!/usr/bin/env python3
"""
Query planning related to intervention ID 403 to find the 14:00 - 15:00 times.
"""

import psycopg2
import psycopg2.extras

# Database connection details from .env
DATABASE_URL = "postgresql://savia_user:savia_password_secure_2026@localhost:5432/savia_db"

def query_planning_and_related():
    """Query planning and related tables for intervention 403."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.set_client_encoding('UTF8')
        
        # Use RealDictCursor to get column names
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        print("=" * 120)
        print("SEARCHING FOR PWA TIMES (14:00 - 15:00) - CHECKING RELATED TABLES")
        print("=" * 120)
        
        # First, check if planning_id 403 exists in planning_maintenance
        print("\n\n1. CHECKING planning_maintenance TABLE FOR ID 403:")
        print("-" * 120)
        
        query = "SELECT * FROM planning_maintenance WHERE id = 403"
        cur.execute(query)
        row = cur.fetchone()
        
        if row:
            print("✓ Found planning_maintenance with ID 403:")
            for column_name, value in row.items():
                print(f"  {column_name:30} | {str(value):60}")
        else:
            print("✗ No planning_maintenance with ID 403")
        
        # Check planning_maintenance table structure
        print("\n\n2. CHECKING planning_maintenance TABLE STRUCTURE:")
        print("-" * 120)
        
        schema_query = """
        SELECT 
            column_name,
            data_type,
            is_nullable
        FROM 
            information_schema.columns
        WHERE 
            table_name = 'planning_maintenance'
        ORDER BY 
            ordinal_position
        """
        
        cur.execute(schema_query)
        columns_info = cur.fetchall()
        
        print(f"{'Column Name':30} | {'Data Type':20} | {'Nullable':10}")
        print("-" * 120)
        for col_info in columns_info:
            col_name = col_info['column_name']
            data_type = col_info['data_type']
            is_nullable = col_info['is_nullable']
            print(f"{col_name:30} | {data_type:20} | {str(is_nullable):10}")
        
        # Get all data from planning_maintenance
        print("\n\n3. ALL RECORDS IN planning_maintenance TABLE:")
        print("-" * 120)
        
        query = "SELECT id, machine, date_prevue, date_realisee, description, technicien_assigne FROM planning_maintenance ORDER BY id DESC LIMIT 10"
        cur.execute(query)
        rows = cur.fetchall()
        
        for row in rows:
            print(f"\nID: {row.get('id')}")
            for column_name, value in row.items():
                print(f"  {column_name:30} | {str(value)}")
        
        # Search for any columns that might contain time information
        print("\n\n4. SEARCHING ALL TABLES FOR COLUMNS THAT MIGHT STORE TIMES:")
        print("-" * 120)
        
        # Get all tables
        query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
        """
        cur.execute(query)
        tables = cur.fetchall()
        
        for table_row in tables:
            table_name = table_row['table_name']
            
            # Get columns with 'time' or 'heure' or 'date' in the name
            query = f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' 
            AND (column_name LIKE '%time%' OR column_name LIKE '%heure%' OR column_name LIKE '%start%' OR column_name LIKE '%end%' OR column_name LIKE '%debut%' OR column_name LIKE '%fin%')
            """
            cur.execute(query)
            time_columns = cur.fetchall()
            
            if time_columns:
                print(f"\nTable: {table_name}")
                for col in time_columns:
                    print(f"  {col['column_name']} ({col['data_type']})")
        
        # Check for any JSON or text columns that might contain time data
        print("\n\n5. SEARCHING FOR TIME VALUES IN TEXT/JSON COLUMNS:")
        print("-" * 120)
        
        # Search in interventions table
        query = """
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'interventions' 
        AND (data_type = 'text' OR data_type LIKE '%json%')
        """
        cur.execute(query)
        text_columns = cur.fetchall()
        
        print("Checking interventions table for '14:00' or '15:00' in text fields:")
        for col in text_columns:
            col_name = col['column_name']
            query = f"SELECT id, {col_name} FROM interventions WHERE id = 403 AND {col_name} IS NOT NULL"
            try:
                cur.execute(query)
                result = cur.fetchone()
                if result and result[col_name]:
                    value_str = str(result[col_name])
                    if "14:00" in value_str or "15:00" in value_str or "14h" in value_str or "15h" in value_str:
                        print(f"  ✓ Found time in {col_name}: {value_str}")
            except:
                pass
        
        # Check if there's a separate time_slot or similar table
        print("\n\n6. CHECKING FOR TIME-RELATED TABLES:")
        print("-" * 120)
        
        query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        AND (table_name LIKE '%time%' OR table_name LIKE '%slot%' OR table_name LIKE '%heure%')
        """
        cur.execute(query)
        time_tables = cur.fetchall()
        
        if time_tables:
            for table_row in time_tables:
                print(f"  Found table: {table_row['table_name']}")
                # Get all data from this table
                query = f"SELECT * FROM {table_row['table_name']} LIMIT 5"
                cur.execute(query)
                rows = cur.fetchall()
                if rows:
                    for row in rows:
                        print(f"    {row}")
        else:
            print("  No time-related tables found")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    query_planning_and_related()
