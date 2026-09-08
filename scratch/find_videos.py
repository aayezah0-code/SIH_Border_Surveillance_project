import os
import sys
import glob

print("Scanning for video files in current directory...")
found = []
for root, dirs, files in os.walk('.'):
    for f in files:
        if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            p = os.path.join(root, f)
            sz = os.path.getsize(p)
            found.append((p, sz))

for p, sz in found:
    print(f"{p} ({sz / 1024 / 1024:.2f} MB)")

# Also let's check Desktop and user directory for relevant video files
print("\nChecking parent/Desktop for video files:")
desktop_files = glob.glob(os.path.expanduser("~/Desktop/*.*"))
for f in desktop_files:
    if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        print(f, f"({os.path.getsize(f) / 1024 / 1024:.2f} MB)")

downloads_files = glob.glob(os.path.expanduser("~/Downloads/*.*"))
for f in downloads_files:
    if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
        print(f, f"({os.path.getsize(f) / 1024 / 1024:.2f} MB)")
