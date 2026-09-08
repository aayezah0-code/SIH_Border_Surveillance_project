import re

log_path = r'C:\Users\HP\.gemini\antigravity-ide\brain\1612c3fe-fc81-4ac8-9f31-8d225c908f4b\.system_generated\tasks\task-89.log'

with open(log_path, 'r') as f:
    text = f.read()

sections = text.split("ANALYZING VIDEO:")
for s in sections[1:]:
    lines = s.strip().split("\n")
    header = lines[0]
    print("\n" + "#" * 80)
    print("VIDEO:", header)
    print("#" * 80)

    # Let's inspect all telemetry lines for person tracks
    t_lines = [l for l in lines if "[TELEMETRY]" in l]
    print(f"Total telemetry frames for persons: {len(t_lines)}")
    
    # Print sample of first 5, middle 5, last 5
    if t_lines:
        print("--- First 5 frames ---")
        for l in t_lines[:5]:
            print(l)
        print("--- Middle 5 frames ---")
        mid = len(t_lines) // 2
        for l in t_lines[max(0, mid-2):min(len(t_lines), mid+3)]:
            print(l)
        print("--- Last 5 frames ---")
        for l in t_lines[-5:]:
            print(l)

    # Let's extract max vNorm, min relH, max AR
    v_norms = []
    rel_hs = []
    ars = []
    crawl_sigs = []
    for l in t_lines:
        m_v = re.search(r'vNorm=([\d\.]+)', l)
        m_h = re.search(r'relH=([\d\.]+)', l)
        m_ar = re.search(r'AR=([\d\.]+)', l)
        m_sig = re.search(r'crawlSig=(\d)/3', l)
        if m_v: v_norms.append(float(m_v.group(1)))
        if m_h: rel_hs.append(float(m_h.group(1)))
        if m_ar: ars.append(float(m_ar.group(1)))
        if m_sig: crawl_sigs.append(int(m_sig.group(1)))

    if v_norms:
        print(f"vNorm: min={min(v_norms):.2f}, max={max(v_norms):.2f}, avg={sum(v_norms)/len(v_norms):.2f}")
    if rel_hs:
        print(f"relH: min={min(rel_hs):.2f}, max={max(rel_hs):.2f}, avg={sum(rel_hs)/len(rel_hs):.2f}")
    if ars:
        print(f"AR: min={min(ars):.2f}, max={max(ars):.2f}, avg={sum(ars)/len(ars):.2f}")
    if crawl_sigs:
        print(f"crawlSig distribution: 0={crawl_sigs.count(0)}, 1={crawl_sigs.count(1)}, 2={crawl_sigs.count(2)}, 3={crawl_sigs.count(3)}")
