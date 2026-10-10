# Vectre: Phase 1, PCA spectral compression for real-time spectral rendering

Compress reflectance spectra into a K-dimensional PCA basis, and measure whether the
compressed form survives light transport (per-wavelength multiplication across bounces)
compared with RGB and 4-wavelength sampling. The basis and tensors are exported for WebGPU.

* Results: [RESULTS.md](RESULTS.md)
* Design decisions and provenance: [LAB_NOTEBOOK.md](LAB_NOTEBOOK.md)
* Data sources, licences, and what you must supply: [data/README.md](data/README.md)
* GPU export layout: [results/export/README.md](results/export/README.md)

## Layout

```
data/            raw/ and processed/ (gitignored; fetched or supplied)
src/
  fetch_data.py          download and MD5-check Munsell, CIE CMF/D65, Sharma test data
  colorimetry.py         CMFs, D65, XYZ, CIELAB, CIEDE2000, linear sRGB
  datasets.py            Munsell and ECOSTRESS loaders, resampling, grouped split
  preprocess.py          Step 1: data/processed/spectra.npz, results/data_summary.json
  pca.py                 Step 2: PCA in raw / sqrt / logit / log spaces
  eval_reconstruction.py Step 3: error vs K
  multiplication.py      product tensor, DMR, colour matrix
  eval_multiplication.py Steps 4-5: bounces, baselines, plots, tables
  export.py              Step 6: .bin + .json for WebGPU, with read-back verification
  spectral1nm.py         Phase 1.5: 1 nm truth colorimetry, CIE A/F2/F11 + synthetic line lights
  eval_illuminants.py    Phase 1.5 A: per-illuminant bounce errors + tonemap sweep
  synthetic_spectra.py   Phase 1.5 B: Jakob-Hanika / GP generators, CIE 99 CES loader
  eval_shippable_basis.py Phase 1.5 B: shippable bases vs Munsell basis
  bench_accumulation.py  Phase 1.5 C: path-loop cost (analytic + CPU timing)
  eval_hybrid4.py        Phase 1.5 C: hybrid accuracy + light-aware hero4 check
  tonemap.py, eval_tonemap.py   Phase 2 Task 0: tonemapper control
  phase2_scene.py        Phase 2: shared Cornell scene, CES materials, lights, J&H LUT
  cpu_reference/         Phase 2 Task 1: Numba spectral reference path tracer
  webgpu/                Phase 2 Task 2: WebGPU RGB / hero-4λ renderer + harness (see its README)
  phase2_report.py       Phase 2: tables + side-by-side images from harness output
tests/           Python tests (colorimetry, loaders, CPU reference, WGSL constants); tests/js/ Node tests
results/         json results, markdown tables, figures/, export/, pca/
```

## Reproduce

```
py -3.12 -m venv .venv && .venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python src/fetch_data.py
python tests/test_colorimetry.py && python tests/test_datasets.py
python src/preprocess.py
python src/pca.py
python src/eval_reconstruction.py
python src/eval_multiplication.py
python src/export.py
python src/eval_illuminants.py
python src/eval_shippable_basis.py
python src/bench_accumulation.py
python src/eval_hybrid4.py
python src/eval_tonemap.py
python src/phase2_scene.py                       # scene + J&H LUT (cached)
python src/cpu_reference/render_reference.py     # ~1 h on 16 threads (8192 spp, 3 scenes)
python src/webgpu/serve.py                       # then open http://localhost:8765/?auto=1
python src/phase2_report.py
node --test tests/js/metrics.test.mjs
```

All randomness is seeded. The full pipeline runs in a few minutes on a laptop CPU. Tests: `python tests/test_*.py` (each file runs standalone).
