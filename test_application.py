#!/usr/bin/env python3
"""
Test script for SAVIA application
Tests all major endpoints and features to ensure the application is working correctly
"""

import requests
import json
import sys
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
import time

# Configuration
BASE_URL = "http://localhost:8000"
TIMEOUT = 10

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, test_name: str):
        self.passed += 1
        print(f"{Colors.GREEN}✓{Colors.RESET} {test_name}")
    
    def add_fail(self, test_name: str, error: str):
        self.failed += 1
        self.errors.append((test_name, error))
        print(f"{Colors.RED}✗{Colors.RESET} {test_name}: {error}")
    
    def print_summary(self):
        total = self.passed + self.failed
        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"Total: {total} | {Colors.GREEN}Passed: {self.passed}{Colors.RESET} | {Colors.RED}Failed: {self.failed}{Colors.RESET}")
        
        if self.errors:
            print(f"\n{Colors.BOLD}Failed Tests:{Colors.RESET}")
            for test_name, error in self.errors:
                print(f"  {Colors.RED}✗{Colors.RESET} {test_name}")
                print(f"    Error: {error}")
        
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")
        return self.failed == 0

def print_header(title: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")

def check_server_health(results: TestResults) -> bool:
    """Check if the server is running"""
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=TIMEOUT)
        if response.status_code == 200:
            results.add_pass("Server health check")
            return True
        else:
            results.add_fail("Server health check", f"Status code: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        results.add_fail("Server health check", f"Cannot connect to {BASE_URL}")
        return False
    except Exception as e:
        results.add_fail("Server health check", str(e))
        return False

def test_interventions(results: TestResults):
    """Test interventions endpoints"""
    print_header("Testing Interventions")
    
    try:
        # Test GET interventions
        response = requests.get(f"{BASE_URL}/api/interventions", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results.add_pass(f"GET /api/interventions (found {len(data)} interventions)")
            
            # Check if technician names are full names (not usernames)
            if data:
                first_intervention = data[0]
                if 'technicien' in first_intervention:
                    tech_name = first_intervention['technicien']
                    # Full names should contain space or be empty
                    if ' ' in tech_name or tech_name == '':
                        results.add_pass(f"Technician names are full names (sample: '{tech_name}')")
                    else:
                        results.add_fail("Technician names format", f"Expected full name, got: '{tech_name}'")
        else:
            results.add_fail("GET /api/interventions", f"Status code: {response.status_code}")
    except Exception as e:
        results.add_fail("GET /api/interventions", str(e))

def test_demandes_intervention(results: TestResults):
    """Test demandes d'intervention endpoints"""
    print_header("Testing Demandes d'Intervention")
    
    try:
        response = requests.get(f"{BASE_URL}/api/demandes-intervention", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results.add_pass(f"GET /api/demandes-intervention (found {len(data)} demandes)")
            
            # Check technician names
            if data:
                first_demande = data[0]
                if 'technicien_assigne' in first_demande:
                    tech_name = first_demande['technicien_assigne']
                    if ' ' in tech_name or tech_name == '':
                        results.add_pass(f"Demande technician names are full names (sample: '{tech_name}')")
                    else:
                        results.add_fail("Demande technician names format", f"Expected full name, got: '{tech_name}'")
        else:
            results.add_fail("GET /api/demandes-intervention", f"Status code: {response.status_code}")
    except Exception as e:
        results.add_fail("GET /api/demandes-intervention", str(e))

def test_planning(results: TestResults):
    """Test planning endpoints"""
    print_header("Testing Planning Maintenance")
    
    try:
        response = requests.get(f"{BASE_URL}/api/planning", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results.add_pass(f"GET /api/planning (found {len(data)} maintenances)")
            
            # Check technician names
            if data:
                first_planning = data[0]
                if 'technicien_assigne' in first_planning:
                    tech_name = first_planning['technicien_assigne']
                    if ' ' in tech_name or tech_name == '':
                        results.add_pass(f"Planning technician names are full names (sample: '{tech_name}')")
                    else:
                        results.add_fail("Planning technician names format", f"Expected full name, got: '{tech_name}'")
                
                # Check client name
                if 'client' in first_planning and first_planning['client']:
                    results.add_pass(f"Planning client name present (sample: '{first_planning['client']}')")
                else:
                    results.add_fail("Planning client name", "Client name is missing or empty")
                
                # Check automatic status logic
                if 'date_prevue' in first_planning and 'statut' in first_planning:
                    date_str = first_planning['date_prevue']
                    status = first_planning['statut']
                    results.add_pass(f"Planning status present (date: {date_str}, status: {status})")
        else:
            results.add_fail("GET /api/planning", f"Status code: {response.status_code}")
    except Exception as e:
        results.add_fail("GET /api/planning", str(e))

def test_planning_filters(results: TestResults):
    """Test planning filters (region, ville)"""
    print_header("Testing Planning Filters")
    
    try:
        # Test with region filter
        response = requests.get(f"{BASE_URL}/api/planning?region=Tunis", timeout=TIMEOUT)
        if response.status_code == 200:
            results.add_pass("GET /api/planning with region filter")
        else:
            results.add_fail("GET /api/planning with region filter", f"Status code: {response.status_code}")
        
        # Test with ville filter
        response = requests.get(f"{BASE_URL}/api/planning?ville=Tunis", timeout=TIMEOUT)
        if response.status_code == 200:
            results.add_pass("GET /api/planning with ville filter")
        else:
            results.add_fail("GET /api/planning with ville filter", f"Status code: {response.status_code}")
        
        # Test with both filters
        response = requests.get(f"{BASE_URL}/api/planning?region=Tunis&ville=Tunis", timeout=TIMEOUT)
        if response.status_code == 200:
            results.add_pass("GET /api/planning with region and ville filters")
        else:
            results.add_fail("GET /api/planning with region and ville filters", f"Status code: {response.status_code}")
    except Exception as e:
        results.add_fail("Planning filters", str(e))

def test_clients(results: TestResults):
    """Test clients endpoints"""
    print_header("Testing Clients")
    
    try:
        response = requests.get(f"{BASE_URL}/api/clients", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results.add_pass(f"GET /api/clients (found {len(data)} clients)")
            
            # Check if clients have region and ville
            if data:
                first_client = data[0]
                has_region = 'region' in first_client and first_client['region']
                has_ville = 'ville' in first_client and first_client['ville']
                if has_region and has_ville:
                    results.add_pass(f"Clients have region and ville (sample: {first_client.get('nom', 'N/A')} - {first_client.get('region', 'N/A')}, {first_client.get('ville', 'N/A')})")
                else:
                    results.add_fail("Clients region/ville", f"Missing region or ville in client data")
        else:
            results.add_fail("GET /api/clients", f"Status code: {response.status_code}")
    except Exception as e:
        results.add_fail("GET /api/clients", str(e))

def test_equipements(results: TestResults):
    """Test equipements endpoints"""
    print_header("Testing Equipements")
    
    try:
        response = requests.get(f"{BASE_URL}/api/equipements", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results.add_pass(f"GET /api/equipements (found {len(data)} equipements)")
            
            # Check if equipements have domaine
            if data:
                equipements_with_domaine = [e for e in data if e.get('domaine')]
                if equipements_with_domaine:
                    first_eq = equipements_with_domaine[0]
                    results.add_pass(f"Equipements have domaine (sample: {first_eq.get('Nom', 'N/A')} - {first_eq.get('domaine', 'N/A')})")
                else:
                    results.add_fail("Equipements domaine", "No equipements with domaine found")
        else:
            results.add_fail("GET /api/equipements", f"Status code: {response.status_code}")
    except Exception as e:
        results.add_fail("GET /api/equipements", str(e))

def test_techniciens(results: TestResults):
    """Test techniciens endpoints"""
    print_header("Testing Techniciens")
    
    try:
        response = requests.get(f"{BASE_URL}/api/techniciens", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results.add_pass(f"GET /api/techniciens (found {len(data)} techniciens)")
            
            # Check if techniciens have nom and prenom
            if data:
                first_tech = data[0]
                has_nom = 'nom' in first_tech and first_tech['nom']
                has_prenom = 'prenom' in first_tech and first_tech['prenom']
                if has_nom and has_prenom:
                    full_name = f"{first_tech.get('prenom', '')} {first_tech.get('nom', '')}".strip()
                    results.add_pass(f"Techniciens have nom and prenom (sample: {full_name})")
                else:
                    results.add_fail("Techniciens nom/prenom", f"Missing nom or prenom in technicien data")
        else:
            results.add_fail("GET /api/techniciens", f"Status code: {response.status_code}")
    except Exception as e:
        results.add_fail("GET /api/techniciens", str(e))

def test_domaines_custom(results: TestResults):
    """Test custom domaines endpoints"""
    print_header("Testing Custom Domaines")
    
    try:
        response = requests.get(f"{BASE_URL}/api/domaines-custom", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results.add_pass(f"GET /api/domaines-custom (found {len(data)} custom domaines)")
        else:
            results.add_fail("GET /api/domaines-custom", f"Status code: {response.status_code}")
    except Exception as e:
        results.add_fail("GET /api/domaines-custom", str(e))

def test_reports(results: TestResults):
    """Test reports endpoints"""
    print_header("Testing Reports")
    
    try:
        response = requests.get(f"{BASE_URL}/api/reports", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results.add_pass(f"GET /api/reports (found {len(data)} reports)")
            
            # Check technician names in reports
            if data:
                first_report = data[0]
                if 'technicien' in first_report:
                    tech_name = first_report['technicien']
                    if ' ' in tech_name or tech_name == '':
                        results.add_pass(f"Report technician names are full names (sample: '{tech_name}')")
                    else:
                        results.add_fail("Report technician names format", f"Expected full name, got: '{tech_name}'")
        else:
            results.add_fail("GET /api/reports", f"Status code: {response.status_code}")
    except Exception as e:
        results.add_fail("GET /api/reports", str(e))

def test_ai_analysis(results: TestResults):
    """Test AI analysis endpoints"""
    print_header("Testing AI Analysis")
    
    try:
        response = requests.get(f"{BASE_URL}/api/ai-analysis", timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results.add_pass(f"GET /api/ai-analysis (found {len(data)} analyses)")
        else:
            results.add_fail("GET /api/ai-analysis", f"Status code: {response.status_code}")
    except Exception as e:
        results.add_fail("GET /api/ai-analysis", str(e))

def main():
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}SAVIA Application Test Suite{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"Testing: {BASE_URL}")
    print(f"Timeout: {TIMEOUT}s\n")
    
    results = TestResults()
    
    # Check server health first
    if not check_server_health(results):
        print(f"\n{Colors.RED}{Colors.BOLD}Server is not running!{Colors.RESET}")
        print(f"Please start the backend server at {BASE_URL}")
        sys.exit(1)
    
    # Run all tests
    test_interventions(results)
    test_demandes_intervention(results)
    test_planning(results)
    test_planning_filters(results)
    test_clients(results)
    test_equipements(results)
    test_techniciens(results)
    test_domaines_custom(results)
    test_reports(results)
    test_ai_analysis(results)
    
    # Print summary
    success = results.print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
