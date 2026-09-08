import re

log_path = r'C:\Users\HP\.gemini\antigravity-ide\brain\1612c3fe-fc81-4ac8-9f31-8d225c908f4b\.system_generated\tasks\task-89.log'

with open(log_path, 'r') as f:
    text = f.read()

sections = text.split("ANALYZING VIDEO:")
for s in sections[1:]:
    lines = s.strip().split("\n")
    header = lines[0]
    print("=" * 80)
    print("VIDEO:", header)
    print("=" * 80)
    # Check for telemetry lines with high speed or crawl signals
    for l in lines:
        if "EVENT CONFIRMED" in l or "CRAWLING_CONFIRMED" in l or "RUNNING_CONFIRMED" in l:
            print("EVENT:", l)
        elif "crawlSig=2/3" in l or "crawlSig=3/3" in l:
            print("CRAWL_CANDIDATE:", l)
        elif "vNorm=" in l:
            # check speed
            m = re.search(r'vNorm=([\d\.]+)', l)
            if m and float(m.group(1)) > 1.2:
                print("HIGH_SPEED:", l)
        elif "SUMMARY" in l:
            print(l)
