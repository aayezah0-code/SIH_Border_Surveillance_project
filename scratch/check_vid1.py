log_path = r'C:\Users\HP\.gemini\antigravity-ide\brain\1612c3fe-fc81-4ac8-9f31-8d225c908f4b\.system_generated\tasks\task-89.log'

with open(log_path, 'r') as f:
    text = f.read()

sections = text.split("ANALYZING VIDEO:")
lines = sections[1].strip().split("\n")
print("VIDEO 1: running.mp4")
for l in lines:
    if "[TELEMETRY]" in l:
        print(l)
