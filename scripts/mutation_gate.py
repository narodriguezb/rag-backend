import json
import sys
from pathlib import Path

THRESHOLD = float(sys.argv[1]) if len(sys.argv) > 1 else 50.0
STATS_FILE = Path("mutants/mutmut-cicd-stats.json")

if not STATS_FILE.exists():
    print(f"ERROR: {STATS_FILE} not found. Run 'mutmut run' and 'mutmut export-cicd-stats' first.")
    sys.exit(2)

stats = json.loads(STATS_FILE.read_text())
killed = stats.get("killed", 0)
total = stats.get("total", 0)
skipped = stats.get("skipped", 0)
denominator = total - skipped

score = (killed / denominator * 100) if denominator else 0.0

print(f"Mutation stats: {stats}")
print(f"Mutation score: {score:.2f}% (killed {killed} / {denominator}) — threshold {THRESHOLD:.2f}%")

if score < THRESHOLD:
    print(f"FAIL: mutation score {score:.2f}% is below threshold {THRESHOLD:.2f}%")
    sys.exit(1)

print("PASS")
