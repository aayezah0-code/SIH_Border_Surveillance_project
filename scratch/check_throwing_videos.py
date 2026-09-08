import os
import hashlib

def get_hash(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

files = {
    '16ad194b': 'backend/uploads/16ad194b-5764-4157-ace1-3e2e225df2fe.mp4',
    'a7f350ce': 'backend/uploads/a7f350ce-5380-42c2-aee2-23ef91c91baf.mp4',
    '849705c0': 'backend/uploads/849705c0-d52f-439d-90ec-ddebb44ed905.mp4',
    'aeea87aa': 'backend/uploads/aeea87aa-8338-4651-8f95-e14b47d50d16.mp4',
    '8bd6a7b7': 'backend/uploads/8bd6a7b7-a398-4ffd-8cd1-3714047e574d.mp4',
}

for k, p in files.items():
    if os.path.exists(p):
        size = os.path.getsize(p)
        h = get_hash(p)
        print(f"{k}: size={size}, md5={h}")
    else:
        print(f"{k}: NOT FOUND")
