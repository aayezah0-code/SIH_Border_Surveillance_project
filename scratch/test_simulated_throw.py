import os
import sys
sys.path.insert(0, os.path.abspath("."))

from ai_engine.modules.behavior.suspicious.track_history import TrackHistoryBuffer, TrackObservation
from ai_engine.modules.behavior.suspicious.throwing_detector import ThrowingDetector

# Test ThrowingDetector on simulated stitched data
detector = ThrowingDetector()
source_id = "test_cam"

# Simulate person #1 and stitched ball (Track 5 -> 6 -> 7 -> 8)
# Person at (1492, 1920), height=1800
person_obs_1 = TrackObservation(
    timestamp_sec=6.05, frame_index=145,
    center_x=1492.0, center_y=1920.0,
    x1=1350, y1=1020, x2=1634, y2=2820,
    width=284, height=1800,
    confidence=0.92, class_name="person", track_id=1
)

ball_obs_1 = TrackObservation(
    timestamp_sec=6.05, frame_index=145,
    center_x=1465.0, center_y=1783.0,
    x1=1398, y1=1712, x2=1532, y2=1855,
    width=134, height=143,
    confidence=0.64, class_name="sports ball", track_id=5
)

# Step 2: Frame 150
person_obs_2 = TrackObservation(
    timestamp_sec=6.26, frame_index=150,
    center_x=1492.0, center_y=1920.0,
    x1=1350, y1=1020, x2=1634, y2=2820,
    width=284, height=1800,
    confidence=0.90, class_name="person", track_id=1
)

ball_obs_2 = TrackObservation(
    timestamp_sec=6.26, frame_index=150,
    center_x=1347.0, center_y=1253.0,
    x1=1260, y1=1149, x2=1435, y2=1357,
    width=175, height=208,
    confidence=0.95, class_name="sports ball", track_id=6
)

# Step 3: Frame 155
person_obs_3 = TrackObservation(
    timestamp_sec=6.46, frame_index=155,
    center_x=1492.0, center_y=1920.0,
    x1=1350, y1=1020, x2=1634, y2=2820,
    width=284, height=1800,
    confidence=0.90, class_name="person", track_id=1
)

ball_obs_3 = TrackObservation(
    timestamp_sec=6.46, frame_index=155,
    center_x=1124.0, center_y=844.0,
    x1=1011, y1=729, x2=1237, y2=960,
    width=226, height=231,
    confidence=0.49, class_name="sports ball", track_id=7
)

# Step 4: Frame 160
person_obs_4 = TrackObservation(
    timestamp_sec=6.67, frame_index=160,
    center_x=1492.0, center_y=1920.0,
    x1=1350, y1=1020, x2=1634, y2=2820,
    width=284, height=1800,
    confidence=0.92, class_name="person", track_id=1
)

ball_obs_4 = TrackObservation(
    timestamp_sec=6.67, frame_index=160,
    center_x=759.0, center_y=1110.0,
    x1=618, y1=951, x2=900, y2=1269,
    width=282, height=318,
    confidence=0.88, class_name="sports ball", track_id=8
)

buf = TrackHistoryBuffer()
print("Simulating step 1 (Frame 145)...")
buf.update(source_id, person_obs_1, 6.05)
buf.update(source_id, ball_obs_1, 6.05)
evs1 = detector.process_frame(source_id, [person_obs_1, ball_obs_1], buf)
print("  Events:", evs1)

print("Simulating step 2 (Frame 150)...")
buf.update(source_id, person_obs_2, 6.26)
buf.update(source_id, ball_obs_2, 6.26)
evs2 = detector.process_frame(source_id, [person_obs_2, ball_obs_2], buf)
print("  Events:", evs2)

print("Simulating step 3 (Frame 155)...")
buf.update(source_id, person_obs_3, 6.46)
buf.update(source_id, ball_obs_3, 6.46)
evs3 = detector.process_frame(source_id, [person_obs_3, ball_obs_3], buf)
print("  Events:", evs3)

print("Simulating step 4 (Frame 160)...")
buf.update(source_id, person_obs_4, 6.67)
buf.update(source_id, ball_obs_4, 6.67)
evs4 = detector.process_frame(source_id, [person_obs_4, ball_obs_4], buf)
print("  Events:", evs4)

