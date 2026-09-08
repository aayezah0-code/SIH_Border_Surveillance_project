import os
import sys
import logging

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
logging.basicConfig(level=logging.WARNING)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

from ai_engine.modules.detection.yolo_detector import YOLODetector

def scan_vid(video_path, confidence, sample_rate, max_frames, label):
    print(f"\n------------------------------------------------------------", flush=True)
    print(f"SCAN: {label}  conf={confidence}  rate=1/{sample_rate}  max={max_frames}", flush=True)
    print(f"------------------------------------------------------------", flush=True)

    det = YOLODetector.get_instance()
    det._reset_tracker()
    class_counts = {}
    total_frames = [0]
    non_person_dets = []

    def on_frame(fd):
        total_frames[0] += 1
        for d in fd.detections:
            cls = d.class_name
            class_counts[cls] = class_counts.get(cls, 0) + 1
            if cls != "person":
                cx = (d.x1 + d.x2) / 2
                cy = (d.y1 + d.y2) / 2
                non_person_dets.append((fd.frame_index, cls, d.track_id, d.confidence, (d.x1, d.y1, d.x2, d.y2)))
                print(f"  [F{fd.frame_index:04d}] NON-PERSON: {cls} "
                      f"track={d.track_id} conf={d.confidence:.2f} "
                      f"center=({cx:.0f},{cy:.0f}) "
                      f"box=({d.x1:.0f},{d.y1:.0f},{d.x2:.0f},{d.y2:.0f})", flush=True)

    det.process_video(
        video_path=video_path,
        max_frames=max_frames,
        sample_rate=sample_rate,
        confidence=confidence,
        on_frame_processed=on_frame,
    )

    print(f"  Frames processed: {total_frames[0]}", flush=True)
    print(f"  Class distribution: {class_counts}", flush=True)
    non_person = {k: v for k, v in class_counts.items() if k != "person"}
    print(f"  NON-PERSON objects count: {non_person}", flush=True)
    print(f"  Total NON-PERSON detection instances: {len(non_person_dets)}", flush=True)

def main():
    v1 = os.path.join(BASE_DIR, "backend", "uploads", "16ad194b-5764-4157-ace1-3e2e225df2fe.mp4")
    v2 = os.path.join(BASE_DIR, "backend", "uploads", "849705c0-d52f-439d-90ec-ddebb44ed905.mp4")

    for vpath, vtitle in [(v2, "Thowing.mp4 (849705c0)"), (v1, "throwing.mp4 (16ad194b)")]:
        print(f"\n======================================================================", flush=True)
        print(f"SURVEY FOR {vtitle}: {vpath}", flush=True)
        print(f"======================================================================", flush=True)
        scan_vid(vpath, 0.40, 5, 100, "Default API settings (conf=0.40, rate=1/5)")
        scan_vid(vpath, 0.20, 2, 100, "Low conf (conf=0.20, rate=1/2)")
        scan_vid(vpath, 0.10, 1, 60, "Ultra-low conf (conf=0.10, rate=1/1)")

if __name__ == "__main__":
    main()
