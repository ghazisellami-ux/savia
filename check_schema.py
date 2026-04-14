import sqlite3
import pprint

conn = sqlite3.connect('sic_radiologie.db')
schema = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
for name, sql in schema:
    print(f"--- {name} ---")
    print(sql)
