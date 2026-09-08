import os
import hashlib
import sqlite3

conn = sqlite3.connect('backend/data/surveillance.db')
c = conn.cursor()
db_cams = {r[0]: (r[1], r[2]) for r in c.execute("SELECT source_id, name, location FROM cameras").fetchall()}

uploads_dir = "backend/uploads"
hashes = {}
for f in os.listdir(uploads_dir):
    if not f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
        continue
    p = os.path.join(uploads_dir, f)
    try:
        with open(p, 'rb') as fp:
            h = hashlib.md5(fp.read()).hexdigest()
    except Exception as e:
        continue
    stem = os.path.splitext(f)[0]
    info = db_cams.get(stem, (f, "Unknown"))
    if h not in hashes:
        hashes[h] = {
            "first_file": f,
            "orig_name": info[0],
            "size_kb": round(os.path.getsize(p) / 1024, 1),
            "duplicates": [f]
        }
    else:
        hashes[h]["duplicates"].append(f)

print(f"Total unique video files: {len(hashes)}")
for h, d in hashes.items():
    print(f"Hash {h[:8]} | Orig: {d['orig_name']} | File: {d['first_file']} | Size: {d['size_kb']}KB | Dups: {len(d['duplicates'])}")
