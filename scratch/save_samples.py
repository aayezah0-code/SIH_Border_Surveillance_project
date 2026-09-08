import cv2
import os

def save_sample_frames(video_path, out_prefix):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Sampling {video_path}: {total} frames at {fps} fps")
    
    step = max(1, total // 8)
    for idx in range(0, total, step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret and frame is not None:
            # Resize for small thumbnail
            h, w = frame.shape[:2]
            thumb = cv2.resize(frame, (360, int(360 * h / w)))
            out_name = f"scratch/{out_prefix}_frame_{idx}.jpg"
            cv2.imwrite(out_name, thumb)
            print(f"Saved {out_name}")
    cap.release()

if __name__ == "__main__":
    save_sample_frames("backend/uploads/849705c0-d52f-439d-90ec-ddebb44ed905.mp4", "thowing_8497")
    save_sample_frames("backend/uploads/16ad194b-5764-4157-ace1-3e2e225df2fe.mp4", "throwing_16ad")
