# Next steps: run the Phase 2 benchmark on your own GPU (PowerShell, from the repo root)

The CPU references are finished and committed (`src/webgpu/data/ref_*`, 8192 spp each).
The Intel-iGPU benchmark is done (`results/phase2_benchmark_intel_igpu.json/.csv`). What's left is
a run on a discrete GPU such as the RTX 4060.

## 1. Make Chrome use the RTX 4060 (do this first)

Windows Settings → System → Display → **Graphics** → find or add **Google Chrome** (or Edge) →
Options → **High performance** (should list the NVIDIA GPU) → Save. Then close every Chrome window
and restart it. Check it at `chrome://gpu`: under "WebGPU" / "Dawn Info" the adapter should mention NVIDIA.

## 2. Start the local server

```powershell
.venv\Scripts\python src\webgpu\serve.py
```
Leave it running. It serves http://localhost:8765/ and saves benchmark output.

## 3. Open the benchmark page and run it

Open in Chrome:
```
http://localhost:8765/?auto=1
```
It starts by itself (or click **Run benchmark**). It takes about 1–2 minutes. The log at the bottom
prints one line per row, then `benchmark done`. If it stops with an error ("accumulation check failed",
"device lost", "reference spp ..."), the run is invalid; reload and rerun.

The first log line shows the adapter, e.g. `adapter: {"vendor":"nvidia",...}`. If it says `intel`,
step 1 didn't take effect.

## 4. Find the saved results

Written automatically to `results\phase2\gpu\`: `results.json`, `results.csv`, and `*_xyz.bin`
images. Keep the run under a GPU-specific name so it doesn't overwrite the iGPU run:
```powershell
Copy-Item results\phase2\gpu\results.json results\phase2_benchmark_rtx4060.json
Copy-Item results\phase2\gpu\results.csv  results\phase2_benchmark_rtx4060.csv
```
(Without `serve.py`, use the **Download results.json / results.csv** buttons instead.)

## 5. Regenerate tables and images

```powershell
.venv\Scripts\python src\phase2_report.py
```
Outputs: `results\phase2\phase2_tables.md`, `results\figures\phase2_error_vs_spp.png`,
`results\figures\phase2_<scene>_compare_{64,1024}spp.png`. The report reads `results\phase2\gpu\`,
i.e. the most recent run.

## 6. Run the tests and commit

```powershell
foreach ($t in Get-ChildItem tests\test_*.py) { .venv\Scripts\python -W ignore $t.FullName }
node --test tests/js/metrics.test.mjs tests/js/checks.test.mjs
git add -A; git commit -m "Phase 2: RTX 4060 benchmark"; git push
```

## What to look for

* The adapter in `results.json` → `meta.adapter`. Label every GPU number with it.
* The **hero-4λ vs RGB time ratio** at 16–64 spp (iGPU: +24–35%) and whether it holds on the discrete
  GPU. Accuracy columns should be identical to the iGPU run: same seeds, so the same images up to
  floating point.
* Wide min–max timing ranges mean the GPU is changing clocks; trust medians at ≥ 16 spp.
