#!/usr/bin/env python3
"""
Script to query intervention ID 403 and display actual field values
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime

# Connection parameters
conn_params = {
    'host': 'localhost',
    'port': 5432,
    'database': 'savia_db',
    'user': 'savia_user',
    'password': 'savia_password_secure_2026'
}

try:
    # Connect to database
    conn = psycopg2.connect(**conn_params)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Query intervention 403
    cursor.execute("SELECT * FROM interventions WHERE id = 403;")
    result = cursor.fetchone()
    
    if result:
        print("=" * 80)
        print("INTERVENTION ID 403 - FULL DATA")
        print("=" * 80)
        print()
        
        # Display all columns
        for key, value in result.items():
            print(f"{key:30} : {repr(value):50} (type: {type(value).__name__})")
        
        print()
        print("=" * 80)
        print("SPECIFIC FIELDS FOR PDF PARSING")
        print("=" * 80)
        print()
        
        # Focus on the fields you mentioned
        fields = [
            'date_debut_intervention',
            'date_cloture',
            'pieces_utilisees',
            'solution',
            'duree_deplacement'
        ]
        
        for field in fields:
            if field in result:
                value = result[field]
                print(f"{field}:")
                print(f"  Value: {repr(value)}")
                print(f"  Type: {type(value).__name__}")
                if value is not None:
                    print(f"  String representation: {str(value)}")
                print()
        
        print("=" * 80)
        print("JSON SERIALIZABLE VERSION")
        print("=" * 80)
        print()
        
        # Convert to JSON-safe format
        json_safe = {}
        for key, value in result.items():
            if isinstance(value, datetime):
                json_safe[key] = value.isoformat()
            elif value is None:
                json_safe[key] = None
            else:
                json_safe[key] = str(value)
        
        print(json.dumps(json_safe, indent=2, ensure_ascii=False))
        
    else:
        print("❌ No intervention found with ID 403")
    
    cursor.close()
    conn.close()
    
except psycopg2.Error as e:
    print(f"❌ Database error: {e}")
    exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)
