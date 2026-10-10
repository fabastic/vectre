# Vectre WebGPU demo (Phase 2): RGB vs spectral hero-4λ

Plain JS + WGSL, no framework, no build step. Files:

| file | role |
|---|---|
| `index.html` | UI: scene / mode / spp / tonemap, "Run benchmark", JSON/CSV download |
| `renderer.js` | WebGPU setup, buffers, progressive accumulation, timestamp queries, display |
| `pt.wgsl` | path tracer kernel: modes RGB, hero-4λ + Jakob–Hanika LUT uplift, hero-4λ with measured spectra (validation) |
| `display.wgsl` | exposure, tonemap (clip / per-channel Reinhard / **max-RGB hue-preserving, default** / Oklch), sRGB OETF |
| `metrics.js` | CIELAB, CIEDE2000, RMSE vs the CPU reference (unit-tested in Node) |
| `harness.js` | every scene × mode × spp (1, 4, 16, 64, 1024): GPU time, buffer memory, ΔE00, RMSE |
| `serve.py` | local static server; also saves harness output to `results/phase2/gpu/` |
| `data/` | scene, CMFs, light spectra, J&H LUT, measured spectra, CPU reference images |

## Run it on your machine

1. Use **Chrome 113+ (or Edge) with WebGPU enabled** (default on Windows/macOS/ChromeOS).
   Check `chrome://gpu`: "WebGPU: Hardware accelerated".
2. **Optional, recommended: make Chrome use the NVIDIA GPU.** On a laptop Chrome often picks the
   integrated GPU. In Windows: Settings → System → Display → Graphics → add/select Chrome →
   "High performance", then restart Chrome. The page logs which adapter it got.
3. From the repo root:
   ```
   python src/webgpu/serve.py
   ```
   (any Python 3.9+; no packages needed). A plain `python -m http.server` also works for
   viewing, but then results are only available via the download buttons.
4. Open **http://localhost:8765/** (WebGPU needs a secure context; `localhost` counts,
   `file://` does not).
5. Click **Run benchmark**, or open **http://localhost:8765/?auto=1**. It takes a few
   minutes; the log shows each row.
6. Results:
   * with `serve.py`: written automatically to `results/phase2/gpu/results.json`, `results.csv`
     and `*_xyz.bin` images;
   * otherwise: click **Download results.json** / **Download results.csv**.
   Paste `results.json` back to me (or commit it) and I'll run `python src/phase2_report.py`
   for tables and side-by-side images.

## What the numbers mean

* `gpu_ms`: sum of compute-pass durations from **timestamp queries** (if the adapter supports
  `timestamp-query`; otherwise `null`, and only `wall_ms` is available. That is
  `performance.now()` around submit → `onSubmittedWorkDone`, which includes CPU/driver overhead).
* `buffer_bytes`: bytes of the GPU buffers that mode reads (scene + accumulation, plus the LUT,
  CMF and spectral tables for spectral modes). Readback/query buffers are excluded.
* `mean_dE00`, `rmse`: vs the CPU reference (`src/cpu_reference/`), emitter pixels excluded, with the
  same exposure (reference median Y → 18).
* The `hero4_measured` mode uses the measured spectra, which an RGB-authored pipeline would not have. It
  exists to validate that the GPU renderer converges to the CPU reference.
