#!/usr/bin/env python3
with open('/opt/data/handbook/knowledge-pulse.md', 'r') as f:
    lines = f.readlines()

print("=== ALL IDEAS WITH STATUS ===")
for i, l in enumerate(lines):
    if '| I-' in l:
        # Parse the table row
        # Format: | ID | Title | Tags | Urgency | Gap | Specificity | Timeliness | Density | Composite | Status | Discovered | LastSeen |
        parts = [p.strip() for p in l.split('|')]
        # parts[0] = '', parts[1] = ID, parts[2] = Title, ..., parts[9] = Composite, parts[10] = Status, parts[11] = Discovered, parts[12] = LastSeen, parts[13] = ''
        id_ = parts[1] if len(parts) > 1 else '?'
        title = parts[2][:70] if len(parts) > 2 else '?'
        status = parts[10] if len(parts) > 10 else '?'
        composite = parts[9] if len(parts) > 9 else '?'
        lastseen = parts[12] if len(parts) > 12 else '?'
        print(f"{id_:6s} | {composite:8s} | {status[:40]:40s} | {title[:65]}")

print("\n=== PENDING IDEAS ===")
for i, l in enumerate(lines):
    if '| I-' in l and 'PENDING' in l:
        parts = [p.strip() for p in l.split('|')]
        id_ = parts[1] if len(parts) > 1 else '?'
        status = parts[10] if len(parts) > 10 else '?'
        composite = parts[9] if len(parts) > 9 else '?'
        title = parts[2][:70] if len(parts) > 2 else '?'
        print(f"{id_} | {composite} | {status} | {title}")
