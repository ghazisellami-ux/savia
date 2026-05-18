#!/usr/bin/env python3
"""
Comprehensive diagnostic and fix for dashboard filters
"""
import sys
sys.path.insert(0, '/home/ubuntu/savia/backend')

from db_engine import lire_clients, lire_equipements, get_db, _trigger_backup
import pandas as pd

print("=" * 80)
print("COMPREHENSIVE DIAGNOSTIC AND FIX")
print("=" * 80)

# Step 1: Diagnose the problem
print("\n1. DIAGNOSING THE PROBLEM...")
df_clients = lire_clients()
df_eq = lire_equipements()

print(f"\n   CLIENTS:")
print(f"   - Total: {len(df_clients)}")
print(f"   - With region: {(df_clients['region'].notna() & (df_clients['region'] != '')).sum()}")
print(f"   - Regions: {df_clients[df_clients['region'] != '']['region'].value_counts().to_dict()}")

print(f"\n   EQUIPEMENTS:")
print(f"   - Total: {len(df_eq)}")
if 'Region' in df_eq.columns:
    print(f"   - With region: {(df_eq['Region'].notna() & (df_eq['Region'] != '')).sum()}")
    print(f"   - Regions: {df_eq[df_eq['Region'] != '']['Region'].value_counts().to_dict()}")
    print(f"   - Empty regions: {(df_eq['Region'].isna() | (df_eq['Region'] == '')).sum()}")
    
    # Show sample of equipements without region
    print(f"\n   Sample equipements without region:")
    no_region = df_eq[(df_eq['Region'].isna()) | (df_eq['Region'] == '')][['Nom', 'Client', 'Region', 'Ville']].head(5)
    for idx, row in no_region.iterrows():
        print(f"      - {row['Nom']} (Client: {row['Client']})")

# Step 2: Fix - Populate region/ville for ALL equipements
print("\n2. FIXING - POPULATING REGION/VILLE FOR ALL EQUIPEMENTS...")

# Create a comprehensive mapping from clients
client_map = {}
for _, row in df_clients.iterrows():
    nom = str(row.get("nom", "")).strip()
    if nom:
        region = str(row.get("region", "Nord")).strip()
        ville = str(row.get("ville", "")).strip()
        client_map[nom.lower()] = {"region": region, "ville": ville}

print(f"   Client map: {len(client_map)} clients")

# Update ALL equipements with region/ville from their client
updated = 0
with get_db() as conn:
    for _, row in df_eq.iterrows():
        client_name = str(row.get("Client", "")).strip()
        equip_id = row.get("id")
        
        if client_name and client_name.lower() in client_map:
            client_info = client_map[client_name.lower()]
            region = client_info["region"]
            ville = client_info["ville"]
            
            # Update equipement
            conn.execute(
                "UPDATE equipements SET region = ?, ville = ? WHERE id = ?",
                (region, ville, equip_id)
            )
            updated += 1

_trigger_backup()
print(f"   ✓ Updated {updated} equipements")

# Step 3: Verify the fix
print("\n3. VERIFYING THE FIX...")
df_eq = lire_equipements()

if 'Region' in df_eq.columns:
    with_region = (df_eq['Region'].notna() & (df_eq['Region'] != '')).sum()
    print(f"   Equipements with region: {with_region}/{len(df_eq)}")
    print(f"   Regions: {df_eq[df_eq['Region'] != '']['Region'].value_counts().to_dict()}")
    
    # Test filtering
    print(f"\n   Testing filters:")
    for region in df_eq[df_eq['Region'] != '']['Region'].unique():
        count = len(df_eq[df_eq['Region'] == region])
        print(f"      - Region '{region}': {count} equipements")

print("\n" + "=" * 80)
print("✓ DIAGNOSTIC AND FIX COMPLETE")
print("=" * 80)
print("\nNow test the dashboard:")
print("1. Go to Dashboard")
print("2. Select a region from the dropdown")
print("3. KPIs should update to show only data for that region")
print("4. Try other filters (ville, equipment type)")
