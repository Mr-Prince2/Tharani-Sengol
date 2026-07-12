import re

with open("app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

def find_pattern(pattern):
    compiled = re.compile(pattern, re.IGNORECASE)
    results = []
    for idx, line in enumerate(lines):
        if compiled.search(line):
            results.append((idx + 1, line.strip()))
    return results

print("=== DEFS ===")
for num, content in find_pattern(r"^def\s+"):
    print(f"{num}: {content}")

print("\n=== SPECIFIC PATTERNS ===")
for num, content in find_pattern(r"check_geofence|process_gps|process_telemetry|compute_prediction|illegal_mining_rf|explain"):
    print(f"{num}: {content}")
