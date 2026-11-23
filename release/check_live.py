"""Send the 1,000 known bookings to the endpoint and count what it flags.

    python release/check_live.py
"""
from pathlib import Path

from config import ENDPOINT, runtime

ROOT = Path(__file__).resolve().parent.parent
bookings = (ROOT / "data/live.csv").read_bytes()
labels = [int(float(x)) for x in (ROOT / "data/live_labels.csv").read_text().split()]

response = runtime.invoke_endpoint(EndpointName=ENDPOINT, ContentType="text/csv", Body=bookings)
chances = [float(x) for x in response["Body"].read().decode().replace(",", "\n").split()]

flagged = [c > 0.5 for c in chances]
came = sum(f and y == 0 for f, y in zip(flagged, labels))
print(f"bookings {len(chances)}, really cancelled {sum(labels)}, "
      f"flagged {sum(flagged)}, flagged but the guest came {came}")
