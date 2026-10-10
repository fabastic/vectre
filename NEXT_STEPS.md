# Phase 2: finishing steps (run from the repo root in PowerShell)

State at hand-off (2026-10-10 21:22): the D65 reference is done. NB610 and F11 were re-rendering
(8192 spp, progress in `results/phase2/reference_render_log.txt`, about 8 min per scene).
`ref_cornell_nb610.npz` may still be a 64×64 smoke-test placeholder until that run finishes.

## (a) Confirm the references finished

```powershell
Get-Content results\phase2\reference_render_log.txt -Tail 5
Get-ChildItem results\phase2\ref_*.npz | Select-Object Name, Length, LastWriteTime
.venv\Scripts\python -c "import numpy as np; [print(s, np.load(f'results/phase2/ref_{s}.npz')['xyz'].shape, int(np.load(f'results/phase2/ref_{s}.npz')['spp'])) for s in ('cornell_d65','cornell_nb610','cornell_f11')]"
```
Expected: the log ends with `EXIT 0`, and all three files report `(512, 512, 3) 8192`.
If not (crash, or the run was killed), re-render only the missing scenes:
```powershell
.venv\Scripts\python -u src\cpu_reference\render_reference.py --spp 8192 --chunk 512 --scenes cornell_nb610,cornell_f11
```
Each chunk line shows `avg cores busy`. If it drops to about 1, the process is being throttled
(that happened once); keep the terminal in the foreground or set the power mode to Best performance.

## (b) Start the WebGPU server

```powershell
.venv\Scripts\python src\webgpu\serve.py
```
Serves `src/webgpu/` at http://localhost:8765/ and accepts result uploads.

## (c) Run the browser benchmark

Open in Chrome or Edge (WebGPU required; localhost only, not file://):
```
http://localhost:8765/?auto=1
```
It runs 3 scenes × 3 modes (RGB, hero-4λ + J&H, hero-4λ measured) × spp 1/4/16/64/1024.
Expect several minutes. Results save automatically to `results\phase2\gpu\`:
`results.json`, `results.csv`, `*_xyz.bin` (64 and 1024 spp images).
The `results.json` currently there is from a 2-spp smoke test and will be overwritten.
Without `serve.py`, use the "Download results.json/csv" buttons instead.

## (d) Tables and side-by-side images

```powershell
.venv\Scripts\python src\phase2_report.py
```
Writes `results\phase2\phase2_tables.md`, `results\figures\phase2_error_vs_spp.png` and
`results\figures\phase2_<scene>_compare_{64,1024}spp.png`.

Then run the tests and commit:
```powershell
foreach ($t in Get-ChildItem tests\test_*.py) { .venv\Scripts\python -W ignore $t.FullName }
node --test tests/js/metrics.test.mjs
git add -A; git commit -m "Phase 2: benchmark results, tables, images"; git push
```

## (e) What to look for

1. **Renderer validity first:** `hero4_measured` should converge toward the reference. Its mean ΔE00
   at 1024 spp should be small (≲ 1) and keep falling with spp. If it plateaus high, there is a
   GPU renderer bug, and nothing else in the table should be trusted.
2. **Uplift cost:** the `hero4_jh` minus `hero4_measured` gap at 1024 spp is the J&H uplift error
   (expected to be small under D65; may grow under NB610/F11 because the uplift only matches colour
   under D65).
3. **The verdict question:** does RGB's ΔE stay high as spp grows (bias) while hero-4λ keeps falling?
   Compare at 1024 spp per scene, and check the per-surface table (which walls/spheres fail) and
   the ΔE heat-maps in the compare images. Under D65 RGB should be close; under NB610/F11 it
   should be visibly wrong if the Phase 1.5 results hold.
4. **Cost:** `gpu_ms` median (min–max) and `buffer_bytes`. On the iGPU, run-to-run timing varied
   up to ~10x, so use medians and report ranges.
5. Then write the RESULTS.md Phase 2 section. The Task 0 part is drafted in
   `results\_p2_section_task0.md`; append it, add the tables from (d), and add the verdict.

## (f) GPU caveat: Intel iGPU, not the RTX 4060

All GPU numbers so far came from the **Intel integrated GPU** (adapter `intel / gen-12lp`). Chrome
picked it despite `powerPreference: "high-performance"`. To use the RTX 4060:
Windows Settings → System → Display → Graphics → add Chrome (or Edge) → Options → **High
performance** → Save, then fully restart the browser. Confirm at `chrome://gpu`, or in the page
log (`adapter: {"vendor":"nvidia",...}`); the adapter is also recorded in `results.json` → `meta.adapter`.
