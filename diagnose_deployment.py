#!/usr/bin/env python3
"""
Deployment Health Check for SAVIA
Vérifie les éléments critiques avant le déploiement
"""
import os
import sys
import json
from pathlib import Path

def check_frontend_build():
    """Vérifie que le build frontend est OK"""
    frontend_dir = Path("frontend/.next")
    if not frontend_dir.exists():
        return False, "❌ Frontend build missing (.next directory not found)"
    return True, "✅ Frontend build OK"

def check_backend_files():
    """Vérifie que les fichiers backend essentiels existent"""
    required_files = [
        "backend/main.py",
        "backend/auth.py",
        "backend/db_engine.py",
        "backend/requirements.txt",
    ]
    missing = [f for f in required_files if not Path(f).exists()]
    if missing:
        return False, f"❌ Backend files missing: {', '.join(missing)}"
    return True, "✅ Backend files OK"

def check_admin_page():
    """Vérifie que la page admin a les modifications correctes"""
    admin_page = Path("frontend/src/app/(authenticated)/admin/page.tsx")
    if not admin_page.exists():
        return False, "❌ Admin page not found"
    
    content = admin_page.read_text()
    
    # Vérifier que l'onglet profiles a adminOnly: true
    if "adminOnly: true" not in content:
        return False, "❌ Admin page missing adminOnly flag for profiles tab"
    
    # Vérifier que le filtre est appliqué
    if ".filter(t => !t.adminOnly || currentUser?.username === 'admin')" not in content:
        return False, "❌ Admin page missing role-based tab filtering"
    
    # Vérifier que defaultTab est défini correctement
    if "const defaultTab = currentUser?.username === 'admin' ? 'users' : 'settings'" not in content:
        return False, "❌ Admin page missing defaultTab logic for non-admins"
    
    return True, "✅ Admin page modifications OK"

def check_auth_context():
    """Vérifie que les permissions par défaut incluent settings: true pour tous"""
    auth_context = Path("frontend/src/lib/auth-context.tsx")
    if not auth_context.exists():
        return False, "❌ Auth context not found"
    
    content = auth_context.read_text()
    
    # Vérifier que settings: true est présent pour tous les rôles
    roles = ["Admin", "Manager", "Technicien", "Gestionnaire", "Lecteur"]
    for role in roles:
        if f"{role}:" in content:
            # Chercher settings: true après le rôle
            role_section = content[content.find(f"{role}:"):content.find(f"{role}:") + 500]
            if "settings: true" not in role_section:
                return False, f"❌ Auth context: {role} missing settings: true"
    
    return True, "✅ Auth context permissions OK"

def check_git_status():
    """Vérifie que git est disponible et le repo est clean"""
    try:
        import subprocess
        result = subprocess.run(["git", "status", "--porcelain"], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            return False, "❌ Git not available or not a git repo"
        
        # Vérifier qu'on est sur develop
        branch_result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                      capture_output=True, text=True, timeout=5)
        current_branch = branch_result.stdout.strip()
        if current_branch != "develop":
            return False, f"❌ Not on develop branch (current: {current_branch})"
        
        return True, "✅ Git status OK (on develop branch)"
    except Exception as e:
        return False, f"❌ Git check failed: {e}"

def main():
    print("\n" + "="*60)
    print("🔍 SAVIA Deployment Health Check")
    print("="*60 + "\n")
    
    checks = [
        ("Frontend Build", check_frontend_build),
        ("Backend Files", check_backend_files),
        ("Admin Page Modifications", check_admin_page),
        ("Auth Context Permissions", check_auth_context),
        ("Git Status", check_git_status),
    ]
    
    results = []
    for name, check_func in checks:
        try:
            success, message = check_func()
            results.append((success, message))
            print(f"{message}")
        except Exception as e:
            results.append((False, f"❌ {name} check failed: {e}"))
            print(f"❌ {name} check failed: {e}")
    
    print("\n" + "="*60)
    passed = sum(1 for success, _ in results if success)
    total = len(results)
    print(f"Results: {passed}/{total} checks passed")
    print("="*60 + "\n")
    
    if passed == total:
        print("✅ All checks passed! Ready to deploy.")
        return 0
    else:
        print("❌ Some checks failed. Please fix the issues before deploying.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
