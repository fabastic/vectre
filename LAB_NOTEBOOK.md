# Lab notebook

Each entry: date, decision, why, and **standard vs. possibly novel** (S = standard or known
practice; P = possibly novel and needs a literature check; E = evaluation choice only).

## 2026-10-10: setup and data

* **Environment.** Python 3.12 venv; torch 2.14.1 (CPU wheel; the data is ~10³×81, so a GPU is
  unnecessary), numpy 2.5.3, scipy 1.18.1, matplotlib 3.11.2. colour-science 0.4.7 is used
  only as an independent check in tests. (S)
* **Repo.** Private GitHub repo `FABASTIC/vectre` (user's choice). Raw and processed data are
  gitignored because of licence terms (Munsell: no commercial licence; ECOSTRESS: all rights
  reserved). Exported bases are committed but marked research-only.
* **Munsell source.** UEF "Munsell colors matt (spectrophotometer measured)", 1269 chips,
  380–800 nm @ 1 nm. `cs.uef.fi` timed out, so I used the Zenodo mirror (record 3269912), whose
  `urls.txt` lists the original URLs with identical MD5s. Labels come from the README index
  (1269 parsed = 1269 spectra; asserted). (S)
* **"ASTER" means ECOSTRESS v1.0.** The ASTER library v2.0 is distributed inside
  ECOSTRESS. Download needs a cart/order flow, so the user supplies it. The user chose "ALL
  spectra"; my loader filters by units, coverage and gaps.
* **Coverage policy deferred.** The user asked to see counts under strict vs ≤20 nm edge
  extension before deciding. Both are computed in `results/data_summary.json`.
* **CMFs and D65 from the official CIE CSV datasets** (DOIs in `src/colorimetry.py`), with
  MD5s matching the CIE pages; licence CC BY-SA 4.0 from the CIE metadata JSON. Nothing typed from memory. (S)

## 2026-10-10: colorimetry decisions

* **5 nm summation, sampling the 1 nm CIE tables at grid points**, k = 100/ΣSȳ. Not ASTM E308
  weights. Since ground truth and every approximation use the same linear operator, this
  cannot bias comparisons. White = (95.043, 100, 108.880). (S)
* **CIEDE2000 implemented in torch**, verified on all 34 Sharma et al. (2005) pairs (max error
  < 5e-5, which is publication rounding) and against colour-science (1e-9). (S)
* **sRGB matrix derived from the IEC primaries plus *our* D65 white**, so white maps exactly to
  (1,1,1). This gives RGB its best case, so RGB is exact at n=0. Deliberately generous to the baseline. (E)

## 2026-10-10: preprocessing and split

* **Resampling = box filter (5 nm window) of the piecewise-linear interpolant**, averaging
  only measured parts of the window. This equals point sampling for smooth data and avoids
  aliasing for dense (ECOSTRESS ~1 nm) data. (S)
* **Coverage rule:** native data must reach 380 and 780 nm (0.5 nm tolerance); internal gaps
  > 10 nm in the visible are rejected. The 10 nm gap threshold is my assumption. (E)
* **Values outside [0,1] are clipped and counted** (Munsell: none). (E)
* **Split by material.** Munsell: hold out 8 of 40 *hue pages* (every 5th round the hue
  circle). Neighbouring chips are near-duplicates, so a row split would leak. ECOSTRESS:
  deterministic hash split (20%) by `Type + Name`, so the same mineral never appears in
  both splits. Leakage is asserted in code. (E)

## 2026-10-10: PCA

* **SVD of the centred training matrix in float64**, with a deterministic sign convention. (S)
* **Value spaces: raw, sqrt, logit (requested), plus log (my addition).** I added log because
  multiplication becomes addition there, which is directly relevant to Step 4. eps = 1e-3
  for logit/log (inactive for Munsell, min 0.030). (S for the transforms; see below on log for products)
* Observation: for single spectra the spaces differ little. Logit is best at K=6 (0.38 vs 0.56 raw).

## 2026-10-10: multiplication experiment

* **Definition: n bounces = n multiplications = product of n+1 spectra.** Ambiguous in the brief
  ("pairs … 1, 2, 3, 5 bounces"); I chose this so that "1 bounce" = one pair. (E)
* **Ground truth = per-wavelength product of the original 81-sample spectra.** (E)
* **Two chain types:** random distinct test spectra (20 000), and self-products s^(n+1).
  I added the latter as a proxy for inter-reflection in one material. (E)
* **Galerkin product tensor** K×(K+1)×(K+1) with homogeneous weights. This is the standard
  linear-model approach (Peercy 1993). I verified it equals unclamped DMR to 4e-15 (it must,
  by bilinearity). (S)
* **Least-squares-fitted tensor** (trained on train-split products, 1/(Y+1) row weights). I
  tried it to test whether the operator or the basis is the bottleneck. Result: no gain. (E or
  maybe P as a negative result, but it is unremarkable.)
* **`raw_floor` diagnostic**, the projection of the TRUE product onto the basis, shows the basis is the bottleneck. (E)
* **Log-PCA with exact additive products**, carrying a count of mean terms (n μ + B Σw).
  **P (needs literature check).** Log/optical-density linear models and multiplicative
  mixing are old ideas (e.g. Kubelka–Munk / density-domain work; Drew & Finlayson's work on
  spectral sharpening for products is related), so this may well be published for rendering.
  Do not claim it as novel before checking. The cost problem (addition is not closed; texture
  filtering in log space = geometric mean) is the interesting open part.
* **Exposure-normalised ΔE00 as the primary metric** for chains (true Y scaled to 20). I adopted
  it after measuring that the median L* of random products falls to 0.1 by n=5, where absolute
  ΔE is meaningless. Absolute ΔE is still reported. (E)
* **Baselines:** RGB (unclamped and clamped); fixed 4-wavelength quadrature (exhaustive
  search over all C(81,4) tuples, weights fitted on train singles and products, 1/(Y+1)
  weighting); stochastic 4-wavelength sampling, importance-sampled by (x̄+ȳ+z̄)·D65 with
  stratified offsets u+i/4 as in PBRT-v4 (Wilkie et al. 2014 hero wavelength idea). (S)
  Chosen quadrature wavelengths: 450, 505, 560, 615 nm.

## 2026-10-10: export

* **One .bin per K, 256-byte-aligned arrays** (WebGPU default `minStorageBufferOffsetAlignment`),
  all `array<f32>`; the JSON holds offsets plus values. Read back and verified in float32. (S)
* **Exported:** raw basis/mean/tensor/colour matrices (XYZ and linear sRGB) and log basis/mean.
  The Phase 2 choice between them is pending.

## Open questions for the user

1. Coverage policy for ECOSTRESS, once counts are available.
2. Whether to add illuminant-change experiments (strongly recommended before drawing conclusions vs RGB).
3. Whether log-PCA, a hybrid, or another representation should be the Phase 2 target.
