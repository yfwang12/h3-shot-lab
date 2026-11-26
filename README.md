# H3 Shot Lab

A local evaluation kit for game trailers generated with MiniMax H3 and ComfyUI. A shot can look polished while communicating the wrong gameplay rule. This project tests whether a proposed configuration makes the intended event easier to read and shows which clips reviewers need to revisit.

## Try it without a GPU

Python 3.9+ with the standard library is sufficient.

```shell
python demo.py runs/demo
```

Open `runs/demo/reviewer/index.html`. The four included animations are deliberately simple timing diagrams. Watch the moving marker and decide whether the red link breaks on contact. Mark material and identity N/A. Download your ratings. The sample report and triage output in the demo directory use **simulated reviewers** to demonstrate disagreement handling. All quality and speed conclusions about H3 require real renders.

## Run a rendering experiment

1. Prepare a compatible scene-ready ComfyUI canvas with your references and prompt. The adapter targets the node types, IDs and LoRA chain checked in `shot_lab.py`. Rendering uses your existing H3 and VideoHelperSuite environment. The source canvas stays on your machine.
2. Generate four configurations with one command.

   ```shell
   python shot_lab.py scene.json runs/scout-41 --shot scout --seed 41
   ```

   The arms are base, style, action and both. Style enables Mystic at 0.5 and action enables Wushu at 0.3. Turbo stays enabled. Each arm uses the same seed, references and shot prompt. The manifest fingerprints the source and each emitted canvas. Keep reference files, model versions and software versions fixed for a paired comparison.
3. Open each generated canvas in ComfyUI and render. Preview mode saves the first pass and mutes the second output. In the generated `inventory.csv`, enter the actual media path for each arm and a common shot brief. Record rendering failures, retries, elapsed seconds and cache state in `measurements.csv`. If one arm fails, preserve the attempt log and omit that clip from the review inventory. The report counts unresolved or missing comparisons in represented blocks.
4. Build one review pack. Inventories can combine multiple shots and seeds. Paths are relative to the final inventory file or absolute on the operator's computer.

   ```shell
   python review.py pack runs/scout-41/inventory.csv runs/review-01
   ```

   Give **only the reviewer folder** to two reviewers independently. Each opens its HTML locally, plays the anonymized clips, scores four criteria and exports a vote file. Use separate browser profiles or devices for independent reviews. The operator retains the separate `key.json`. Clip bytes are copied intact. Remove any burned-in parameter names and source metadata before a formal blinded study.
5. Compare the votes and estimate the priority for a new shot. The same commands work against the included demonstration.

   ```shell
   python review.py report runs/demo/key.json runs/demo/simulated-A.json runs/demo/simulated-B.json
   python triage.py --batch runs/demo/key.json runs/demo/simulated-report.json
   ```

   For real reviews, use your exported files and add `--output results.json` to the report command. Pass that file to `triage.py`. Add one `--batch KEY REPORT` per historical batch.
6. For an accepted configuration generate full canvases with the same source and seed, adding `--stage full` and choosing a fresh output directory. Queue the selected arm and verify the final render. Cache reuse and elapsed time depend on the local runtime.

## Read the results

| Output | Decision it supports |
| --- | --- |
| Agreement by criterion | Inspect raw agreement and Cohen’s kappa. The comparable count excludes N/A. A null kappa means there are no comparable pairs or chance agreement equals one. |
| Investigation queue | A disagreement on any check goes to human review. Unanimous failures go to rework. Each entry retains the reviewers’ evidence and the shot, seed and arm. |
| Paired contrasts | Count wins, losses and ties against base within the same shot, seed and stage. Disagreements and missing arms are separated from resolved pairs. |
| Historical review priority | For each arm and stage, estimate how often a distinct historical shot produced a disagreement or rejection. A conservative upper bound routes small or uncertain groups to standard review. |

The priority rule uses a 95% Wilson upper bound and counts a shot once even if it has multiple seeds. The provisional defaults are at least five distinct shots and an upper bound at most 0.35 for routine spot-checking. The held-out test omits all seeds of the target shot and reports how often an issue would have entered the routine queue. Both queues involve review. This is a configuration-level baseline. It has no video-content features and its thresholds have not been calibrated on production data.

## Implementation and verification

The repository contains the experiment adapter, review interface, analysis and review-priority logic. Models, rendering nodes and the operator's source canvas are external dependencies. [MiniMax H3](https://github.com/MiniMax-AI/MiniMax-H3) · [ComfyUI](https://github.com/Comfy-Org/ComfyUI)

```shell
python -m unittest discover -s tests -v
```

[中文评测方案](ANALYSIS.zh.md)

