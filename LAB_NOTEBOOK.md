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

## 2026-10-10: Phase 1.5, Task A (illuminants)

* **ECOSTRESS still absent.** Task B is run without it, as the brief allows.
* **CIE A, F2, F11 from official CIE CSVs.** F-series = columns FL2 and FL11 of
  `CIE_illum_FLs_1nm.csv`. The **illuminant A MD5 on the CIE web page does not match the served
  file**; the file matches its own metadata v2 MD5/SHA-256 and the published column-sum
  validation, so I accepted it and documented the discrepancy. (S)
* **Ground truth moved to 1 nm** for illuminant tests. A 5 nm grid cannot represent a 5 nm-FWHM
  line. Native 1 nm Munsell data is used; PCA methods stay on 5 nm and are integrated through
  1 nm CMF·E weights folded by linear interpolation. Measured: uncompressed 5 nm vs 1 nm truth
  ≤ 0.14 ΔE, so the grid is not the bottleneck for these (smooth) reflectances. (E)
* **NEONLIKE is synthetic.** The NIST ASD lines endpoint returned input/software errors to
  scripted queries, and I didn't type real Ne lines from memory. 14 Gaussian lines (FWHM
  1 nm) at seeded-random positions in 580–710 nm. Labelled as not real neon everywhere. (E)
* **Lights normalised to white-reflector Y=100; CIELAB always relative to the D65 white**
  ("display as rendered", no white balance/CAT). This choice penalises nothing in particular
  but makes non-D65 scenes look tinted, which is what a renderer outputs without white
  balance. (E)
* **RGB pipeline = standard practice:** albedo is linear sRGB under D65, light is linear sRGB
  of its XYZ, per-channel product. As analysed by Meng et al. 2015. (S)
* **Fixed 4λ generalised** with Qᵢ = Wᵢ / E_D65(λᵢ), so it is light-independent. (E)
* **Hero-4λ pdf.** The main tables use a light-agnostic pdf ∝ Σ CMF. A **light-aware** pdf
  ∝ Σ CMF · E was added as a fairness check after seeing the line-spectrum results; it is known
  practice (wavelength importance sampling). It turned out to be decisive for the verdict:
  NB610 0.10 at 16 spp. (S)
* **Tonemapper = per-channel Reinhard on clipped linear sRGB**, applied identically to truth and
  methods. Intensities 1x/10x/100x of white-reflector Y=1. Only one tonemapper was tested. (E)
* Finding: the "RGB colour purity collapse" is reproduced, but it comes from the tonemapper and
  affects truth equally (D65 100x: chroma 4.7 for both). It is not RGB-specific.

## 2026-10-10: Phase 1.5, Task B (shippable basis)

* **Sources checked:** ECOSTRESS (absent; all rights reserved), USGS splib07 (public domain,
  but ScienceBase served a Cloudflare challenge, which I didn't bypass), CIE 224 99 CES (CC
  BY-SA 4.0, fetched and verified).
* **Jakob & Hanika 2019 sigmoid-quadratic generator** (their S(z) = ½ + z/(2√(1+z²))). (S) The
  first Adam fit was poor (mean ΔE76 6.6, 35% > 1). I replaced it with batched LM plus restarts:
  residual < 1e-13 for all 5000 targets. Targets uniform in the *encoded* sRGB cube (my choice). (E)
* **GP-smooth generator:** sigmoid of an SE-kernel GP; length-scale 25–90 nm, amplitude 0.5–2.5,
  mean −3..1. These ranges are arbitrary. (E)
* **Balanced weighted PCA** (equal total weight per source). My first union run let 10 000
  synthetic spectra swamp 99 measured ones. (E)
* **Test = 247 held-out Munsell chips** (research use for evaluation only). One CIE-99 sample is
  within 0.004 RMSE of a test chip, which I noted as minor contamination. (E)

## 2026-10-10: Phase 1.5, Task C (accumulation cost)

* **Benchmark design:** vectorised torch, float32, 2^18 paths × 5 bounces, one emission event per
  bounce, scatter-add to a 256² image. Material ids are precomputed so RNG isn't timed. CPU-only,
  indicative. (E)
* **hero-4λ evaluates reflectance via Jakob–Hanika coefficients** (3 floats per material), the
  usual way to get spectra from RGB textures. (S)
* **FLOP counting convention:** FMA = 2, exp counted separately, rsqrt counted as 1. (E)
* **Hybrid (log-PCA throughput, 4λ accumulation)** evaluated for accuracy as well as cost. It is
  strictly worse than hero-4λ on true spectra (noise + bias). (E)
* **Verdict recorded in RESULTS.md: pivot.** Make hero-4λ + J&H uplift + light-aware wavelength
  sampling the WebGPU baseline; test log-PCA only in the 1–4 spp + denoiser regime. That regime
  is a **hypothesis, not measured**.
* **Novelty status unchanged:** log-PCA multiplicative closure is still "P, literature check
  needed". Nothing in Phase 1.5 is claimed as novel; all baselines are known techniques.

## 2026-10-10: Phase 2, Task 0 (tonemapper check)

* **Two extra tonemappers:** max-RGB Reinhard (scales the colour by m/(1+m)/m, m = max channel;
  keeps channel ratios exactly, after clipping negatives) and an Oklch operator (Reinhard on
  luminance; Oklab L' = cbrt(Y'); keeps C/L and hue; bisection-reduces chroma to fit the sRGB
  gamut). Exact formulas are in `src/tonemap.py`. Both are standard ideas (max-RGB/"ratio-preserving"
  tonemapping; Oklab, Ottosson 2020). Oklab constants were verified against colour-science. (S)
* **Hue shift is measured against the scene-linear truth hue** (CIELAB h_ab, D65 white), only for
  samples with scene chroma > 10 to avoid noisy greys. (E)
* Finding: with max-RGB, RGB's display chroma is 0.96–1.07x the truth's. No RGB-specific purity
  loss remains; RGB's error is hue/lightness (ΔE 1.6–6.2 vs truth after tonemapping).

## 2026-10-10: Phase 2, Task 1 (CPU reference)

* **Python + Numba** (no Rust/C++ toolchain installed). Code is independent of the WGSL; only the
  scene JSON is shared. (E)
* **Scene materials = measured CIE 224:2017 CES spectra** (CC BY-SA 4.0), picked as nearest in
  CIELAB to classic Cornell-box target colours (CES 60/11/46/78/29/97 for
  white/red/green/blue/yellow/magenta). The GPU spectral mode only sees their sRGB albedo + J&H
  uplift, so uplift error is part of the comparison, as for RGB-authored assets. (E)
* **Integrator contract**: ≤ 5 scattering vertices, NEE at every vertex, emission from BSDF hits only at
  depth 0, cosine sampling, no Russian roulette. This is standard; it is identical in both renderers so
  truncation bias is shared. (S)
* **Reference spectral estimator**: 8 stratified wavelengths per path from a light-aware pdf on the
  1 nm grid. It is unbiased; tests check it against full 401-wavelength integration (agreement < 2%). (S)
* **Tests**: white furnace (closed cube, every surface emits; exact Σρᵏ, to 1e-12), analytic
  point-to-rectangle form factor (formula checked against scipy quadrature to 1e-10; NEE within
  0.5%, pure PT within 2%), NEE vs pure path tracing on the Cornell scene, and sampled vs full
  spectrum. (S)
* **Resolution 512², 8192 spp reference** (≈ 18 min/scene on 16 CPU threads). Half-split noise is
  reported per scene. (E)
* **Exposure for all metrics/images**: reference median non-emitter Y → 18 (white = 100); the
  emitter pixels are excluded from metrics. (E)

## 2026-10-10: Phase 2, Task 2 (WebGPU)

* **J&H uplift**: own implementation of the published method (Jakob & Hanika 2019); the reference code
  `mitsuba-renderer/rgb2spec` is **BSD-3-Clause** (checked via the GitHub API) but was **not used**.
  The LUT is 32³ over linear sRGB [0,1]³ (simpler than their max-channel parametrisation), fitted
  by LM with continuation from mid-grey outward, and trilinear in coefficients. All grid
  points fit to < 5e-7 ΔE76. Interpolated random colours: mean 0.05, p95 0.15, max 2.5 ΔE00
  (worst near gamut corners). (S method / E parametrisation)
* **Hero-4λ** (Wilkie et al. 2014) with **light-aware wavelength pdf** ∝ (x̄+ȳ+z̄)·E on the 1 nm
  grid, inverse-CDF binary search, stratified u + i/4. These are known techniques. (S)
* **RGB light colour** = linear sRGB of the light's XYZ, **negatives kept** (NB610 → (73.6, −0.77,
  −1.39)). This is consistent with Phase 1.5; clamping would be an artist choice. (E)
* **Mode 2 (measured spectra on GPU)** was added for validation, to separate renderer bugs from
  uplift error. It is not part of the RGB-vs-spectral comparison. (E)
* **Timing**: timestamp queries around each compute pass (4 spp per dispatch), summed. A warm-up
  render precedes each mode. Memory = bytes of buffers the mode reads. (E)
* **Adapter caveat**: in this environment Chrome exposed the **Intel integrated GPU** (gen-12lp), not
  the RTX 4060, so all GPU numbers I report are from that iGPU. (E)
* **WGSL validation**: compiled via Chrome's WebGPU (`getCompilationInfo`: no messages). No standalone
  naga/tint was available. Constants and LUT layout are cross-checked against Python in
  `tests/test_webgpu_static.py`. Metrics JS is tested in Node against the Sharma pairs.

## Open questions for the user

1. Coverage policy for ECOSTRESS, once counts are available (still not supplied).
2. ~~Illuminant-change experiments~~ done in Phase 1.5 (Task A).
3. Phase 2 target: recommendation is to pivot to hero-4λ + light-aware sampling as the
   baseline, with log-PCA tested only at 1–4 spp + denoiser. Needs your decision.
4. Whether to download USGS splib07 (public domain) manually as a second shippable measured set.
