#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔧 Fix Equipment Types Mismatch
Corrige les incohérences entre les types d'équipements et les types de pièces.
"""

import os
import sys
import logging

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from db_engine import get_db
from config import TYPES_EQUIPEMENTS

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("fix_equipment_types")

# Mapping des types incorrects vers les types corrects
TYPE_CORRECTIONS = {
    "Mammographe": "Mammographie",  # Correction du type incorrect
    "mammographe": "Mammographie",
}

def fix_equipment_types():
    """Corrige les types d'équipements et de pièces dans la base de données."""
    logger.info("=" * 60)
    logger.info("🔧 Correction des types d'équipements et de pièces")
    logger.info("=" * 60)
    
    try:
        with get_db() as conn:
            # Corriger les équipements
            logger.info("\n📋 Correction des équipements...")
            for incorrect, correct in TYPE_CORRECTIONS.items():
                cursor = conn.execute(
                    "UPDATE equipements SET type = ? WHERE LOWER(type) = LOWER(?)",
                    (correct, incorrect)
                )
                if cursor.rowcount > 0:
                    logger.info(f"  ✅ {cursor.rowcount} équipement(s) corrigé(s): '{incorrect}' → '{correct}'")
            
            # Corriger les pièces
            logger.info("\n📦 Correction des pièces...")
            for incorrect, correct in TYPE_CORRECTIONS.items():
                cursor = conn.execute(
                    "UPDATE pieces_rechange SET equipement_type = ? WHERE LOWER(equipement_type) = LOWER(?)",
                    (correct, incorrect)
                )
                if cursor.rowcount > 0:
                    logger.info(f"  ✅ {cursor.rowcount} pièce(s) corrigée(s): '{incorrect}' → '{correct}'")
            
            # Vérifier les types uniques
            logger.info("\n📊 Types d'équipements uniques dans la base:")
            equipement_types = conn.execute(
                "SELECT DISTINCT type FROM equipements ORDER BY type"
            ).fetchall()
            for row in equipement_types:
                logger.info(f"  • {row['type']}")
            
            logger.info("\n📊 Types de pièces uniques dans la base:")
            piece_types = conn.execute(
                "SELECT DISTINCT equipement_type FROM pieces_rechange ORDER BY equipement_type"
            ).fetchall()
            for row in piece_types:
                logger.info(f"  • {row['equipement_type']}")
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ Correction terminée avec succès!")
        logger.info("=" * 60)
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la correction: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = fix_equipment_types()
    sys.exit(0 if success else 1)
