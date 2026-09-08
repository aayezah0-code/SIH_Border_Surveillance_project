import re

log_path = r'C:\Users\HP\.gemini\antigravity-ide\brain\1612c3fe-fc81-4ac8-9f31-8d225c908f4b\.system_generated\tasks\task-89.log'

with open(log_path, 'r') as f:
    text = f.read()

sections = text.split("ANALYZING VIDEO:")
for s in sections[1:3]: # running.mp4 and running_test.mp4
    lines = s.strip().split("\n")
    header = lines[0]
    print("\n" + "=" * 80)
    print("VIDEO:", header)
    print("=" * 80)
    for l in lines:
        if "[TELEMETRY]" in l:
            # print all telemetry lines
            print(l)
