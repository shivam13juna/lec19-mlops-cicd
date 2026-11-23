"""The release gate. Scores a candidate model against the one already on main.

    python release/gate.py                      # candidate/model.tar.gz against origin/main's copy
    python release/gate.py NEW.tar.gz OLD.tar.gz

Both models score data/live.csv, 1,000 bookings whose real ending is in data/live_labels.csv.
A booking is flagged when its chance of cancelling is above 0.5. The candidate passes only
if it is no worse than the old model on both of these:

    false alarms   share of flagged bookings whose guest still came   (lower is better)
    catch rate     share of real cancellations that were flagged      (higher is better)

Exits 1 when it does not pass, which fails the CI job.
"""
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import numpy as np
import xgboost as xgb

MAX_FALSE_ALARM_RISE = 0.02   # the candidate may not raise the false-alarm share by more than this
MAX_CATCH_RATE_DROP = 0.02    # nor lower the catch rate by more than this


def load(archive):
    d = tempfile.mkdtemp()
    with tarfile.open(archive) as t:
        t.extractall(d, filter="data")
    booster = xgb.Booster()
    booster.load_model(f"{d}/xgboost-model")
    return booster


def score(booster, X, y):
    flagged = booster.predict(xgb.DMatrix(X)) > 0.5
    came = flagged & (y == 0)
    return {"flagged": int(flagged.sum()), "came": int(came.sum()),
            "false_alarms": came.sum() / max(flagged.sum(), 1),
            "catch_rate": (flagged & (y == 1)).sum() / (y == 1).sum()}


def old_from_main():
    """The model on main, read out of Git without touching the working tree."""
    blob = subprocess.run(["git", "show", "origin/main:candidate/model.tar.gz"],
                          capture_output=True, check=True).stdout
    path = Path(tempfile.mkdtemp()) / "old.tar.gz"
    path.write_bytes(blob)
    return str(path)


def main():
    new_path = sys.argv[1] if len(sys.argv) > 1 else "candidate/model.tar.gz"
    old_path = sys.argv[2] if len(sys.argv) > 2 else old_from_main()
    X = np.loadtxt("data/live.csv", delimiter=",")
    y = np.loadtxt("data/live_labels.csv", delimiter=",")
    old, new = score(load(old_path), X, y), score(load(new_path), X, y)

    rise = new["false_alarms"] - old["false_alarms"]
    drop = old["catch_rate"] - new["catch_rate"]
    problems = []
    if rise > MAX_FALSE_ALARM_RISE:
        problems.append(f"false alarms rose by {rise:.3f}, more than the {MAX_FALSE_ALARM_RISE} allowed")
    if drop > MAX_CATCH_RATE_DROP:
        problems.append(f"catch rate fell by {drop:.3f}, more than the {MAX_CATCH_RATE_DROP} allowed")

    lines = ["| 1,000 known bookings | on main | this change |", "|---|---|---|",
             f"| flagged above 0.5 | {old['flagged']} | {new['flagged']} |",
             f"| flagged, but the guest came | {old['came']} | {new['came']} |",
             f"| false alarms (share of flagged) | {old['false_alarms']:.3f} | {new['false_alarms']:.3f} |",
             f"| catch rate (share of cancellations) | {old['catch_rate']:.3f} | {new['catch_rate']:.3f} |",
             "", "PASS" if not problems else "FAIL: " + "; ".join(problems)]
    report = "\n".join(lines)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(report + "\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
