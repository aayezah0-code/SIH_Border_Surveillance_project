import cv2
import glob

files = sorted(glob.glob("scratch/thowing_8497_frame_*.jpg") + glob.glob("scratch/throwing_16ad_frame_*.jpg"))
for f in files:
    img = cv2.imread(f)
    if img is not None:
        h, w = img.shape[:2]
        print(f"{f}: {w}x{h}")
