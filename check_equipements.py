#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/ubuntu/savia/backend')

from db_engine import lire_equipements

df = lire_equipements()
print("Columns:", df.columns.tolist())
print("\nTotal equipements:", len(df))
print("\nFirst 5 rows:")
print(df[['Nom', 'Client', 'Region', 'Ville']].head(5) if 'Region' in df.columns else df[['Nom', 'Client', 'Ville']].head(5))
print("\nUnique regions:", df['Region'].unique() if 'Region' in df.columns else "NO REGION COLUMN")
print("\nUnique clients:", df['Client'].unique()[:5])
