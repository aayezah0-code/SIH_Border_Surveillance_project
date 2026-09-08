import re

log_path = r'C:\Users\HP\.gemini\antigravity-ide\brain\1612c3fe-fc81-4ac8-9f31-8d225c908f4b\.system_generated\tasks\task-89.log'

with open(log_path, 'r') as f:
    text = f.read()

sections = text.split("ANALYZING VIDEO:")
for s in sections[1:3]:
    lines = s.strip().split("\n")
    header = lines[0]
    print("\n" + "=" * 80)
    print("VIDEO:", header)
    print("=" * 80)
    for l in lines:
        if "[TELEMETRY]" in l:
            m_v = re.search(r'vNorm=([\d\.]+)', l)
            m_smth = re.search(r'smth=([\d\.]+)', l)
            m_runT = re.search(r'runT=([\d\.]+)s', l)
            m_runState = re.search(r'runState=(\w+)', l)
            v = float(m_v.group(1)) if m_v else 0.0
            smth = float(m_smth.group(1)) if m_smth else 0.0
            runT = float(m_runT.group(1)) if m_runT else 0.0
            st = m_runState.group(1) if m_runState else ""
            print(f"{l.split('|')[0].strip()} | {l.split('|')[1].strip()} | vNorm={v:.2f} smth={smth:.2f} runT={runT:.2f}s state={st}")
