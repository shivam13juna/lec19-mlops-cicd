"""Call the endpoint every 5 seconds with the 1,000 known bookings and print how many
it flags. The number tells you which model answered. Stop it with Ctrl-C.

    python release/watch.py
"""
import time
from datetime import datetime
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from config import ENDPOINT, runtime

bookings = (Path(__file__).resolve().parent.parent / "data/live.csv").read_bytes()
try:
    while True:
        now = datetime.now().strftime("%H:%M:%S")
        try:
            response = runtime.invoke_endpoint(EndpointName=ENDPOINT, ContentType="text/csv", Body=bookings)
            chances = response["Body"].read().decode().replace(",", "\n").split()
            print(f"{now} answered, flagged {sum(float(c) > 0.5 for c in chances)}", flush=True)
        except (BotoCoreError, ClientError) as e:
            print(f"{now} NO ANSWER: {str(e)[:100]}", flush=True)
        time.sleep(5)
except KeyboardInterrupt:
    pass
