import sqlite3
import os

for db_path in ['backend/data/surveillance.db', 'backend/surveillance.db']:
    if os.path.exists(db_path):
        print("=== DB:", db_path)
        conn = sqlite3.connect(db_path)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print("Tables:", tables)
        for (t,) in tables:
            rows = conn.execute(f"SELECT * FROM {t} LIMIT 5").fetchall()
            print(f"Table {t} ({len(rows)} rows sample):")
            for r in rows:
                print("  ", r)
