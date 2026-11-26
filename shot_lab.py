"""Build a matched 2 x 2 experiment from a compatible ComfyUI H3 video canvas."""

import argparse
import copy
import csv
import hashlib
import json
import re
from pathlib import Path


ARMS = {
    "base": (False, False),
    "style": (True, False),
    "action": (False, True),
    "both": (True, True),
}
NODES = {
    53: "LoraLoaderModelOnly", 128: "LoraLoaderModelOnly",
    319: "LoraLoaderModelOnly", 256: "RandomNoise",
    214: "VHS_VideoCombine", 264: "VHS_VideoCombine",
    265: "MiniMaxH3ReferenceToVideo", 261: "BasicScheduler",
    289: "SplitSigmas", 263: "Text",
}
MODELS = {53: "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors",
          128: "MysticXXX_MMH3-V1.safetensors",
          319: "wushu_spatial_physics_v2_1000_pruned.safetensors"}


def indexed(graph):
    return {node["id"]: node for node in graph["nodes"]}


def validate(graph):
    nodes = indexed(graph)
    for key, kind in NODES.items():
        if nodes.get(key, {}).get("type") != kind:
            raise ValueError(f"Expected node {key} ({kind}) in the source graph")
    for key, name in MODELS.items():
        if nodes[key]["widgets_values"][0].replace("\\", "/").split("/")[-1] != name:
            raise ValueError(f"Unexpected LoRA on node {key}")
    edges = {(edge[1], edge[3]) for edge in graph["links"]}
    if not {(319, 128), (128, 53), (53, 39)}.issubset(edges):
        raise ValueError("Unexpected model chain for this experiment")
    if nodes[53].get("mode", 0) != 0:
        raise ValueError("This experiment requires the source Turbo LoRA enabled")


def generate(source, output, shot, seed, stage):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", shot):
        raise ValueError("Use a short alphanumeric shot ID, optionally with - or _")
    if not 0 <= seed <= 2**53 - 1:
        raise ValueError("Seed must be an exact nonnegative JavaScript integer")
    raw = source.read_bytes()
    graph = json.loads(raw.decode("utf-8-sig"))
    validate(graph)
    rows = []
    files = {}
    for arm, (style, action) in ARMS.items():
        variant = copy.deepcopy(graph)
        nodes = indexed(variant)
        nodes[256]["widgets_values"] = [seed, "fixed"]
        for key, enabled, weight in [(128, style, 0.5), (319, action, 0.3)]:
            nodes[key]["mode"] = 0 if enabled else 4
            nodes[key]["widgets_values"][1] = weight
        prefix = f"h3-shot-lab/{shot}/{seed}/{arm}"
        for key, label in [(264, "preview"), (214, "final")]:
            video = nodes[key]
            video["mode"] = 2 if label == "final" and stage == "preview" else 0
            settings = video["widgets_values"]
            settings["save_output"] = True
            settings["filename_prefix"] = f"{prefix}-{label}"
            settings.pop("videopreview", None)
        name = f"{shot}-{seed}-{arm}-{stage}.json"
        files[name] = json.dumps(variant, ensure_ascii=False, indent=2) + "\n"
        rows.append({"arm": arm, "workflow": name, "style_active": style,
                     "canvas_sha256": hashlib.sha256(files[name].encode("utf-8")).hexdigest(),
                     "action_active": action, "prefix": prefix, "stage": stage})
    manifest = {"source_sha256": hashlib.sha256(raw).hexdigest(), "shot": shot,
                "seed": seed, "stage": stage, "variants": rows}
    files["manifest.json"] = json.dumps(manifest, indent=2) + "\n"
    output.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        (output / name).write_bytes(data.encode("utf-8"))
    with (output / "inventory.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["shot", "seed", "stage", "arm", "clip", "brief"])
        for arm in ARMS:
            writer.writerow([shot, seed, stage, arm, "", ""])
    with (output / "measurements.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["shot", "seed", "arm", "stage", "attempt", "cache_state",
                         "runtime_seconds", "failure_reason", "clip", "reviewer",
                         "material_pass", "identity_pass", "action_pass", "cue_pass"])
        for arm in ARMS:
            writer.writerow([shot, seed, arm, stage, 1] + [""] * 9)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Scene-ready ComfyUI canvas JSON")
    parser.add_argument("output", type=Path, help="New experiment directory")
    parser.add_argument("--shot", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--stage", choices=["preview", "full"], default="preview")
    args = parser.parse_args()
    try:
        generate(args.source, args.output, args.shot, args.seed, args.stage)
    except (ValueError, OSError, KeyError, TypeError, IndexError) as exc:
        parser.exit(1, f"Cannot build experiment: {exc}\n")
    print(f"Created four workflows, a manifest and a review sheet in {args.output}")


if __name__ == "__main__":
    main()
