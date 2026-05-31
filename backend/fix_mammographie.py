#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 Fix Mammographie Type
Corrige tous les types Mammographe vers Mammographie
"""

import sys
sys.path.insert(0, '.')
from db_engine import get_db

with get_db() as conn:
    print('=== Correction des types Mammographe → Mammographie ===\n')
    
    # Corriger les équipements
    print('📋 Correction des équipements...')
    conn.execute(
        'UPDATE equipements SET type = %s WHERE type = %s',
        ('Mammographie', 'Mammographe')
    )
    print(f'  ✅ Équipements corrigés\n')
    
    # Corriger les pièces
    print('📦 Correction des pièces...')
    conn.execute(
        'UPDATE pieces_rechange SET equipement_type = %s WHERE equipement_type = %s',
        ('Mammographie', 'Mammographe')
    )
    print(f'  ✅ Pièces corrigées\n')
    
    # Vérifier les types uniques
    print('=== Types d\'équipements uniques ===')
    equipement_types = conn.execute('SELECT DISTINCT type FROM equipements ORDER BY type').fetchall()
    for row in equipement_types:
        print(f'  • {row["type"]}')
    
    print('\n=== Types de pièces uniques ===')
    piece_types = conn.execute('SELECT DISTINCT equipement_type FROM pieces_rechange ORDER BY equipement_type').fetchall()
    for row in piece_types:
        print(f'  • {row["equipement_type"]}')
    
    print('\n✅ Correction terminée!')
