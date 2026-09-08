import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('backend/surveillance.db')
c = conn.cursor()

print("=== CAMERA SOURCES ===")
for r in c.execute("SELECT id, source_id, name, location, source_type, uri FROM camera_sources").fetchall():
    print(r)

print("\n=== THREAT ALERTS ===")
for r in c.execute("SELECT id, alert_type, threat_level, severity, track_id, object_class, description FROM threat_alerts ORDER BY id DESC LIMIT 25").fetchall():
    print(r)

print("\n=== DETECTION EVENTS ===")
for r in c.execute("SELECT id, event_type, object_class, track_id, confidence, description FROM detection_events ORDER BY id DESC LIMIT 25").fetchall():
    print(r)
