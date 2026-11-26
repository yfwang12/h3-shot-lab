"""Run an offline demonstration with schematic clips and explicitly simulated votes."""
import argparse
from copy import deepcopy
from pathlib import Path
import json

from review import CRITERIA, pack, read_json, report
from triage import evaluate, examples

HERE = Path(__file__).resolve().parent


def save(path, obj):
    path.write_text(json.dumps(obj,indent=2)+"\n", encoding="utf-8")


def demo(out):
    pack(HERE / "examples" / "inventory.csv", out)
    keyfile = out / "key.json"
    key = read_json(keyfile)
    left = dict(batch=key["batch"], reviewer="SIMULATED-A", votes={})
    for code, clip in key["clips"].items():
        vote = dict.fromkeys(CRITERIA, "na")
        vote.update(motion="pass", cue="pass", evidence="")
        if clip["arm"] in ("base","action"):
            vote.update(cue="fail",evidence="~0.5 s: link disappears before contact.")
        left["votes"][code] = vote
    right = deepcopy(left)
    right["reviewer"] = "SIMULATED-B"
    for code, clip in key["clips"].items():
        if clip["arm"] == "action":
            right["votes"][code].update(cue="pass", evidence="Timing looked simultaneous at normal speed.")
    a,b = out/"simulated-A.json",out/"simulated-B.json"
    save(a,left)
    save(b,right)
    reportfile=out/"simulated-report.json"
    save(reportfile,report(keyfile,a,b))
    save(out/"simulated-triage.json",evaluate(examples([(keyfile,reportfile)])))
    return out/"reviewer"/"index.html"


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    print(demo(args.output))

