"""Prepare blind reviews and turn independent ratings into a decision report."""
import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path
import secrets
import shutil
import sys
import tempfile

from shot_lab import ARMS

CRITERIA = ("material", "identity", "motion", "cue")
FIELDS = ("shot", "seed", "stage", "arm", "clip", "brief")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def pack(inventory, dest):
    if dest.exists():
        raise ValueError("Choose a new output directory")
    with inventory.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("Inventory needs " + ", ".join(FIELDS))
        rows = list(reader)
    if not rows:
        raise ValueError("Empty inventory")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        root = Path(tmp) / "pack"
        clips = root / "reviewer" / "clips"
        clips.mkdir(parents=True)
        lookup, public, conditions = {}, [], set()
        secrets.SystemRandom().shuffle(rows)
        for row in rows:
            shot, seed, stage, arm, filename, brief = (row[k].strip() for k in FIELDS)
            key = shot, seed, stage, arm
            if (not shot or not seed.isdecimal() or not brief or arm not in ARMS
                    or stage not in ("preview", "full") or key in conditions):
                raise ValueError(f"Invalid or duplicate condition {key}")
            conditions.add(key)
            src = inventory.parent / filename
            if src.suffix.lower() not in (".gif", ".mp4", ".webm") or not src.is_file() or not src.stat().st_size:
                raise ValueError(f"Missing or unsupported media: {filename}")
            code = secrets.token_hex(8)
            target = clips / (code + src.suffix.lower())
            shutil.copyfile(src, target)
            with target.open("rb") as stream:
                digest = sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            lookup[code] = dict(shot=shot, seed=seed, stage=stage, arm=arm, sha256=digest.hexdigest())
            public.append(dict(id=code, media="clips/" + target.name, brief=brief))
        batch = secrets.token_hex(12)
        (root / "key.json").write_text(json.dumps(dict(batch=batch, clips=lookup), indent=2), encoding="utf-8")
        template = Path(__file__).with_name("reviewer.html").read_text(encoding="utf-8")
        payload = json.dumps(dict(batch=batch, clips=public), ensure_ascii=True).replace("<", "\\u003c")
        (root / "reviewer" / "index.html").write_text(template.replace("/*BATCH*/null", payload), encoding="utf-8")
        root.rename(dest)


def load_votes(file, key):
    obj = read_json(file)
    reviewer = str(obj["reviewer"]).strip().casefold()
    if not reviewer or obj["batch"] != key["batch"] or set(obj["votes"]) != set(key["clips"]):
        raise ValueError(f"Wrong batch, missing reviewer or incomplete review in {file.name}")
    for vote in obj["votes"].values():
        scores = [vote[c] for c in CRITERIA]
        if any(x not in ("pass", "fail", "na") for x in scores) or all(x == "na" for x in scores):
            raise ValueError("Each clip needs a valid assessment")
        if "fail" in scores and not str(vote.get("evidence", "")).strip():
            raise ValueError("Record a timestamp and observation for each failed clip")
    return reviewer, obj["votes"]


def kappa(pairs):
    if not pairs:
        return None
    n = len(pairs)
    a, b = zip(*pairs)
    agree = sum(x == y for x, y in pairs) / n
    expected = sum(a.count(v) * b.count(v) for v in ("pass", "fail")) / n**2
    return (agree - expected) / (1 - expected) if expected < 1 else None


def report(key_file, first, second):
    key = read_json(key_file)
    a, left = load_votes(first, key)
    b, right = load_votes(second, key)
    if a == b:
        raise ValueError("Two distinct reviewer IDs required")
    pairs = defaultdict(list)
    reasons, statuses, counts = [], {}, defaultdict(Counter)
    for code, clip in key["clips"].items():
        matches, failures = [], []
        for criterion in CRITERIA:
            x, y = left[code][criterion], right[code][criterion]
            if "na" not in (x, y):
                pairs[criterion].append((x, y))
            if x != y:
                matches.append(criterion)
            if x == y == "fail":
                failures.append(criterion)
        status = "review" if matches else "reject" if failures else "pass"
        shot, seed, stage, arm = (clip[k] for k in ("shot", "seed", "stage", "arm"))
        statuses[shot, seed, stage, arm] = status
        counts[stage, arm][status] += 1
        if status != "pass":
            reasons.append(dict(clip=code, shot=shot, seed=seed, stage=stage, arm=arm,
                                route=status, disagreement=matches, confirmed_failures=failures,
                                observations=[left[code].get("evidence",""), right[code].get("evidence","")]))
    agreement = {}
    for c in CRITERIA:
        p = pairs[c]
        agreement[c] = dict(comparable=len(p), matching=sum(x == y for x,y in p), kappa=kappa(p))
    # A matched comparison requires the same scene, seed, review batch and stage.
    contrasts = []
    for stage in sorted({k[2] for k in statuses}):
        blocks = {(s, n) for s, n, st, _ in statuses if st == stage}
        for arm in ("style", "action", "both"):
            comparison = Counter(wins=0, losses=0, ties=0, unresolved_or_missing=0)
            for shot, seed in blocks:
                x, y = (statuses.get((shot, seed, stage, v)) for v in ("base", arm))
                if x not in ("pass","reject") or y not in ("pass","reject"):
                    comparison["unresolved_or_missing"] += 1
                elif x == y:
                    comparison["ties"] += 1
                else:
                    comparison["wins" if y == "pass" else "losses"] += 1
            contrasts.append(dict(stage=stage, arm=arm, **comparison))
    return dict(batch=key["batch"], clips=len(key["clips"]), reviewers=[a,b], agreement=agreement,
                outcomes=[dict(stage=st, arm=arm, **{k:c[k] for k in ("pass","reject","review")})
                          for (st,arm),c in sorted(counts.items())],
                paired_vs_base=contrasts, investigation_queue=reasons)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("pack")
    prep.add_argument("inventory", type=Path)
    prep.add_argument("directory", type=Path)
    analyze = sub.add_parser("report")
    for field in ("key", "first", "second"):
        analyze.add_argument(field, type=Path)
    analyze.add_argument("--output", type=Path, help="Write a new UTF-8 report file")
    args = p.parse_args()
    try:
        if args.command == "pack":
            pack(args.inventory,args.directory)
        else:
            result = json.dumps(report(args.key,args.first,args.second), ensure_ascii=True, indent=2)
            if args.output:
                with args.output.open("x", encoding="utf-8") as stream:
                    stream.write(result + "\n")
            else:
                print(result)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        sys.exit(f"Review error: {exc}")


if __name__ == "__main__":
    main()

