import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend/data/surveillance.db')
c = conn.cursor()

cams = c.execute("SELECT id, source_id, name, location, source_type, uri FROM cameras").fetchall()
print(f"Total cameras in db: {len(cams)}")
for row in cams:
    print(row)
