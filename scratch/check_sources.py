import sqlite3

conn = sqlite3.connect('backend/data/surveillance.db')
c = conn.cursor()
sources = c.execute("SELECT id, name, location, source_type, path FROM sources").fetchall()
print(f"Total sources: {len(sources)}")
for s in sources:
    print(s)
