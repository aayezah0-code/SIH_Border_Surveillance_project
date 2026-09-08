import httpx
import sqlite3
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def analyze_and_check(source_id: str, label: str):
    print("=" * 80)
    print(f"ANALYZING VIA API: {label} (source_id: {source_id})")
    print("=" * 80)

    # 1. Trigger POST /api/v1/detection/analyze/{source_id}
    url = f"{BASE_URL}/api/v1/detection/analyze/{source_id}?max_frames=300&sample_rate=5&confidence=0.35"
    t0 = time.time()
    try:
        resp = httpx.post(url, timeout=120.0)
        print(f"Analyze response status: {resp.status_code} in {time.time()-t0:.2f}s")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Frames processed: {data.get('frames_processed')}, total detections: {data.get('total_detections')}")
        else:
            print(f"Error response: {resp.text}")
    except Exception as e:
        print(f"API request failed: {e}")

    # Allow async workers a brief moment to commit to sqlite
    time.sleep(1.0)

    # 2. Check Database for threat alerts, detection events, and evidence snapshots
    conn = sqlite3.connect("backend/data/surveillance.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, alert_type, threat_level, severity, track_id, object_class, is_intrusion, event_type, description, created_at "
        "FROM threat_alerts WHERE source_id=? ORDER BY id DESC LIMIT 5",
        (source_id,)
    )
    alerts = cursor.fetchall()
    print(f"\n--- Threat Alerts in DB for {source_id} (count: {len(alerts)}) ---")
    for a in alerts:
        print(a)

    cursor.execute(
        "SELECT id, event_type, object_class, track_id, timestamp_sec, threat_level, severity, description, created_at "
        "FROM detection_events WHERE source_id=? AND (event_type LIKE '%SUSPICIOUS%' OR event_type LIKE '%RUNNING%' OR event_type LIKE '%CRAWLING%' OR event_type LIKE '%THROWING%') ORDER BY id DESC LIMIT 5",
        (source_id,)
    )
    events = cursor.fetchall()
    print(f"\n--- Detection Events in DB for {source_id} (count: {len(events)}) ---")
    for ev in events:
        print(ev)

    cursor.execute(
        "SELECT id, event_type, object_class, track_id, filepath, timestamp_sec, created_at "
        "FROM evidence_snapshots WHERE source_id=? ORDER BY id DESC LIMIT 5",
        (source_id,)
    )
    evidence = cursor.fetchall()
    print(f"\n--- Evidence Snapshots in DB for {source_id} (count: {len(evidence)}) ---")
    for snap in evidence:
        print(snap)

    conn.close()
    print("=" * 80 + "\n")

if __name__ == "__main__":
    analyze_and_check("4bee2e49-e24f-4ce4-88bd-25616ac06c0f", "RUNNING VIDEO")
    analyze_and_check("d7a2bb15-aea4-4799-ab2b-1cb1cc2f817d", "CRAWLING VIDEO")
    analyze_and_check("16ad194b-5764-4157-ace1-3e2e225df2fe", "THROWING VIDEO")
