"""Exit 1 when data/health.json has alerts, so the scrape run turns red and GitHub emails the owner."""
import json
import os
import sys

h = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "health.json"),
                   encoding="utf-8"))
print(f"offers {h['offers']}  ok {h['ok']}  stale {h['stale']}  error {h['error']}  hibor {h['hibor_date']}")
for a in h["alerts"]:
    print("ALERT:", a)
sys.exit(1 if h["alerts"] else 0)
