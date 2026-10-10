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
tests/           colorimetry (Sharma pairs, colour-science cross-check), loaders
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
```

All randomness is seeded. The full pipeline runs in under a minute on a laptop CPU.
