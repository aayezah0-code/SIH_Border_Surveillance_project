import os
import requests

video_path = r"C:\Users\HP\Downloads\7939015-uhd_2160_3840_24fps.mp4"

# 1. Upload video
print("Uploading video to /api/v1/video/upload...")
with open(video_path, "rb") as f:
    r = requests.post("http://127.0.0.1:8000/api/v1/video/upload", files={"file": ("7939015.mp4", f, "video/mp4")})

print("Upload status:", r.status_code)
upload_data = r.json()
print("Upload response:", upload_data)
source_id = upload_data.get("source_id") or upload_data.get("id")

# 2. Run Analyze
print(f"Triggering analysis on source_id: {source_id}...")
r_ana = requests.post(f"http://127.0.0.1:8000/api/v1/detection/analyze/{source_id}?confidence=0.40&sample_rate=5")
print("Analyze status:", r_ana.status_code)
ana_data = r_ana.json()
print(f"Frames processed: {ana_data.get('frames_processed')}")
print(f"Total detections: {ana_data.get('total_detections')}")
print(f"Unique classes: {ana_data.get('unique_classes')}")
print(f"Suspicious events count: {len(ana_data.get('suspicious_events', []))}")
for ev in ana_data.get("suspicious_events", []):
    print("  -> Activity:", ev.get("activity"), "| Track ID:", ev.get("track_id"), "| Severity:", ev.get("severity"), "| Score:", ev.get("score"))

