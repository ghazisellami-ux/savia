#!/usr/bin/env python3
"""
Query intervention ID 403 from PostgreSQL to find where PWA times are stored.
"""

import psycopg2
import psycopg2.extras
from datetime import datetime

# Database connection details from .env
DATABASE_URL = "postgresql://savia_user:savia_password_secure_2026@localhost:5432/savia_db"

def query_intervention_403():
    """Query intervention 403 and display all columns."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.set_client_encoding('UTF8')
        
        # Use RealDictCursor to get column names
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        print("=" * 100)
        print("QUERYING INTERVENTION ID 403")
        print("=" * 100)
        
        # Query the intervention
        query = "SELECT * FROM interventions WHERE id = 403"
        cur.execute(query)
        row = cur.fetchone()
        
        if row is None:
            print("ERROR: Intervention ID 403 not found!")
            return
        
        # Display all columns
        print("\nALL COLUMNS AND VALUES FOR INTERVENTION ID 403:")
        print("-" * 100)
        
        for column_name, value in row.items():
            print(f"{column_name:30} | {str(value):60}")
        
        print("-" * 100)
        
        # Now search for columns containing "14:00" or "15:00" or times
        print("\n\nSEARCHING FOR START_TIME (14:00) AND END_TIME (15:00):")
        print("-" * 100)
        
        times_found = []
        for column_name, value in row.items():
            if value is None:
                continue
            value_str = str(value)
            if "14:00" in value_str or "14:0" in value_str:
                print(f"✓ Found '14:00' in column: {column_name} = {value}")
                times_found.append((column_name, "14:00", value))
            if "15:00" in value_str or "15:0" in value_str:
                print(f"✓ Found '15:00' in column: {column_name} = {value}")
                times_found.append((column_name, "15:00", value))
        
        if not times_found:
            print("⚠ No columns found containing '14:00' or '15:00'")
        
        # Also check for 18:34 and 19:34 (the PDF times)
        print("\n\nSEARCHING FOR PDF TIMES (18:34 and 19:34):")
        print("-" * 100)
        
        pdf_times_found = []
        for column_name, value in row.items():
            if value is None:
                continue
            value_str = str(value)
            if "18:34" in value_str:
                print(f"✓ Found '18:34' in column: {column_name} = {value}")
                pdf_times_found.append((column_name, "18:34", value))
            if "19:34" in value_str:
                print(f"✓ Found '19:34' in column: {column_name} = {value}")
                pdf_times_found.append((column_name, "19:34", value))
        
        if not pdf_times_found:
            print("⚠ No columns found containing '18:34' or '19:34'")
        
        # Display table structure
        print("\n\nTABLE STRUCTURE (Column Details):")
        print("-" * 100)
        
        schema_query = """
        SELECT 
            column_name,
            data_type,
            is_nullable
        FROM 
            information_schema.columns
        WHERE 
            table_name = 'interventions'
        ORDER BY 
            ordinal_position
        """
        
        cur.execute(schema_query)
        columns_info = cur.fetchall()
        
        print(f"{'Column Name':30} | {'Data Type':20} | {'Nullable':10}")
        print("-" * 100)
        for col_info in columns_info:
            col_name = col_info['column_name']
            data_type = col_info['data_type']
            is_nullable = col_info['is_nullable']
            print(f"{col_name:30} | {data_type:20} | {str(is_nullable):10}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    query_intervention_403()
