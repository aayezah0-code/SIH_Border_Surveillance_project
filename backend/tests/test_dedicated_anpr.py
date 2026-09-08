"""
Diagnostic Test Script for Dedicated ANPR Pipeline
Tests real surveillance videos against the dedicated license plate detector + OCR.
"""
import sys
import time
import logging
from pathlib import Path
import cv2

# Configure logging to console
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from ai_engine.modules.detection.yolo_detector import YOLODetector
from ai_engine.modules.recognition.anpr_worker import anpr_worker
from ai_engine.modules.recognition.plate_detector import PlateDetector
from ai_engine.modules.recognition.plate_ocr import PlateOCR

def run_test():
    yolo = YOLODetector()
    p_det = PlateDetector()
    ocr = PlateOCR()

    test_videos = [
        ("0947fa59-4230-4d78-b0cf-7caaccfd20a0.mp4", "Foreground Vehicles Video"),
        ("87e25bf3-dd1f-46af-a3cc-b3afcdb770ed.mp4", "Distant Surveillance Video"),
        ("033aefba-c2e7-4a0d-9ccd-0ef649f9ee0f.mp4", "Aerial Surveillance Video"),
    ]

    for vid_filename, desc in test_videos:
        vid_path = PROJECT_ROOT / "backend" / "uploads" / vid_filename
        if not vid_path.exists():
            print(f"[SKIP] Video not found: {vid_filename}")
            continue

        print("\n" + "=" * 80)
        print(f" TESTING REAL VIDEO: {vid_filename} ({desc})")
        print("=" * 80)

        cap = cv2.VideoCapture(str(vid_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"Video Info: {w}x{h} @ {fps:.1f} FPS, {total_frames} frames total\n")

        # Sample up to 20 frames
        sample_indices = [int(i * (total_frames / min(20, total_frames))) for i in range(min(20, total_frames))]
        
        frame_idx = 0
        while cap.isOpened() and frame_idx < total_frames:
            ret, frame = cap.read()
            if not ret or frame_idx > sample_indices[-1]:
                break

            if frame_idx in sample_indices:
                t0 = time.perf_counter()
                dets = yolo._track_frame(frame, imgsz=640)
                yolo_ms = (time.perf_counter() - t0) * 1000.0

                for d in dets:
                    if d.class_name in ("car", "truck", "bus", "motorcycle"):
                        x1, y1, x2, y2 = d.bbox
                        cx1, cy1 = max(0, x1), max(0, y1)
                        cx2, cy2 = min(w, x2), min(h, y2)
                        veh_crop = frame[cy1:cy2, cx1:cx2]
                        vw, vh = cx2 - cx1, cy2 - cy1

                        t_det_0 = time.perf_counter()
                        plates = p_det.detect_plates(veh_crop, min_conf=0.25, source_id=vid_filename, track_id=d.track_id)
                        p_det_ms = (time.perf_counter() - t_det_0) * 1000.0

                        plate_str = "None"
                        ocr_conf = 0.0
                        is_valid = False
                        best_bbox = "N/A"
                        best_p_conf = 0.0
                        best_p_dim = "N/A"
                        ocr_ms = 0.0

                        if plates:
                            best_p = plates[0]
                            best_bbox = f"({best_p.x1}, {best_p.y1}, {best_p.x2}, {best_p.y2})"
                            best_p_conf = best_p.confidence
                            best_p_dim = f"{best_p.plate_crop.shape[1]}x{best_p.plate_crop.shape[0]}"

                            t_ocr_0 = time.perf_counter()
                            ocr_res = ocr.recognize_plate(best_p.plate_crop)
                            ocr_ms = (time.perf_counter() - t_ocr_0) * 1000.0

                            if ocr_res:
                                plate_str = ocr_res.plate_text
                                ocr_conf = ocr_res.confidence
                                is_valid = ocr_res.is_valid

                        print(
                            f"Frame {frame_idx:02d} | Track #{d.track_id:02d} ({d.class_name:5s}) | "
                            f"VehCrop: {vw}x{vh} | PlateFound: {len(plates) > 0} (BBox: {best_bbox}, Conf: {best_p_conf:.2f}, Dim: {best_p_dim}) | "
                            f"OCR: '{plate_str}' (Conf: {ocr_conf:.2f}, Valid: {is_valid}) | "
                            f"Latencies: YOLO={yolo_ms:.1f}ms, PDet={p_det_ms:.1f}ms, OCR={ocr_ms:.1f}ms"
                        )

            frame_idx += 1

        cap.release()

if __name__ == "__main__":
    run_test()
