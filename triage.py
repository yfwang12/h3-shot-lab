"""Estimate review priority for new shots from historical two-reviewer outcomes."""
import argparse
from collections import defaultdict
from math import sqrt
from pathlib import Path
import json
import sys

from review import read_json

MIN_SHOTS = 5
MAX_UPPER_RISK = 0.35


def examples(batches):
    groups = defaultdict(dict)
    seen = set()
    for keyfile, reportfile in batches:
        key, report = read_json(keyfile), read_json(reportfile)
        if report["batch"] != key["batch"] or report["clips"] != len(key["clips"]):
            raise ValueError("Key and report must be from the same completed batch")
        queue = {r["clip"] for r in report["investigation_queue"]}
        if not queue.issubset(key["clips"]):
            raise ValueError("Unknown clip in investigation queue")
        for code, clip in key["clips"].items():
            sample = clip["shot"], clip["seed"], clip["arm"], clip["stage"]
            if sample in seen:
                raise ValueError(f"Repeated evaluation condition {sample}")
            seen.add(sample)
            bucket = groups[(clip["arm"],clip["stage"])]
            shot = clip["shot"]
            # Multiple seeds of one scene contribute one scene-level observation.
            bucket[shot] = bucket.get(shot,False) or code in queue
    return groups


def priority(outcomes):
    n, failures = len(outcomes), sum(outcomes)
    if not n:
        return dict(shots=0, flagged=0, upper_risk=None, priority="standard review")
    p, z = failures / n, 1.96
    upper = (p + z*z/(2*n) + z*sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1 + z*z/n)
    return dict(shots=n, flagged=failures, upper_risk=round(upper,4),
                priority="routine spot-check" if n >= MIN_SHOTS and upper <= MAX_UPPER_RISK else "standard review")


def evaluate(groups):
    result = []
    for (arm, stage), shots in sorted(groups.items()):
        routed, missed = 0, 0
        for held, needs_review in shots.items():
            train = [flag for shot,flag in shots.items() if shot != held]
            if priority(train)["priority"] == "routine spot-check":
                routed += 1
                missed += int(needs_review)
        result.append(dict(arm=arm, stage=stage, next_shot=priority(list(shots.values())),
                           held_out_shots=len(shots), held_out_routine=routed,
                           held_out_routine_with_issue=missed))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--batch", nargs=2, type=Path, action="append", required=True,
                   metavar=("KEY_JSON","REPORT_JSON"))
    args = p.parse_args()
    try:
        print(json.dumps(evaluate(examples(args.batch)), indent=2))
    except (KeyError, ValueError, OSError, TypeError) as e:
        sys.exit(f"Triage error: {e}")

