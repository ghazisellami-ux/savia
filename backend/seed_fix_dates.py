#!/usr/bin/env python3
"""
Fix intervention dates to be distributed across 2025 and 2026 up to today (June 5, 2026)
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

def fix_intervention_dates():
    """Redistribute intervention dates across 2025 and 2026."""
    conn = get_connection()
    if not conn:
        return
    
    try:
        cur = conn.cursor()
        
        # Get all interventions
        cur.execute("SELECT id FROM interventions ORDER BY id")
        intervention_ids = [row[0] for row in cur.fetchall()]
        
        print(f"📊 Found {len(intervention_ids)} interventions to update")
        
        # Today: June 5, 2026
        today = datetime(2026, 6, 5)
        
        # Date range: Jan 1, 2025 to today (June 5, 2026)
        start_date = datetime(2025, 1, 1)
        total_days = (today - start_date).days
        
        print(f"📅 Distributing interventions from {start_date.date()} to {today.date()}")
        print(f"   Total days: {total_days}")
        
        # Distribute interventions evenly across the date range
        updated = 0
        for idx, intervention_id in enumerate(intervention_ids):
            # Calculate a date proportionally distributed across the range
            ratio = idx / max(len(intervention_ids) - 1, 1)
            days_offset = int(ratio * total_days)
            new_date = start_date + timedelta(days=days_offset)
            
            # Add random hours/minutes for variety
            new_date = new_date.replace(
                hour=random.randint(8, 18),
                minute=random.randint(0, 59)
            )
            
            cur.execute(
                "UPDATE interventions SET date = %s WHERE id = %s",
                (new_date, intervention_id)
            )
            updated += 1
            
            if updated % 100 == 0:
                print(f"   Updated {updated}/{len(intervention_ids)} interventions...")
        
        conn.commit()
        print(f"✅ Successfully updated {updated} interventions")
        
        # Verify the distribution
        cur.execute(
            """SELECT 
                EXTRACT(YEAR FROM date) as year,
                EXTRACT(MONTH FROM date) as month,
                COUNT(*) as count
            FROM interventions
            GROUP BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
            ORDER BY year, month"""
        )
        
        print("\n📈 Distribution by month:")
        month_names = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
                       7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
        
        for year, month, count in cur.fetchall():
            print(f"   {int(year)}-{month_names[int(month)]}: {count} interventions")
        
        cur.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    fix_intervention_dates()
