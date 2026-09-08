import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

for p in ['backend/surveillance.db', 'backend/data/surveillance.db']:
    print("Checking", p)
    conn = sqlite3.connect(p)
    c = conn.cursor()
    tables = [t[0] for t in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", tables)
    for t in tables:
        cols = [col[1] for col in c.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"  {t}: {cols}")
        count = c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"    row count: {count}")
