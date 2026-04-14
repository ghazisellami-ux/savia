import os
import sqlite3

search_paths = [
    r'c:\Users\ACER\Desktop',
    r'c:\Users\ACER\Downloads',
    r'c:\Users\ACER\Documents',
    r'c:\Users\ACER\.gemini\antigravity\scratch\sic_radiology'
]

def search_dir(d):
    for root, dirs, files in os.walk(d):
        for f in files:
            if f.endswith('.db'):
                path = os.path.join(root, f)
                try:
                    conn = sqlite3.connect(path)
                    res = conn.execute("SELECT count(*) FROM equipements").fetchone()
                    print(f"[FOUND] {path} -> {res[0]} equipements")
                except Exception as e:
                    pass

for p in search_paths:
    if os.path.exists(p):
        search_dir(p)
