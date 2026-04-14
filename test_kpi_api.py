import requests
import json

# Login first to get token
login = requests.post("http://localhost:8000/api/login", json={"username": "admin", "password": "admin123"})
token = login.json().get("access_token", "")
headers = {"Authorization": f"Bearer {token}"}

# Get dashboard KPIs
r = requests.get("http://localhost:8000/api/dashboard/kpis", headers=headers)
print("=== /api/dashboard/kpis ===")
print(json.dumps(r.json(), indent=2, ensure_ascii=False))
