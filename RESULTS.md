# Phase 1 results: PCA spectral compression and multiplication in weight space

Status as of 2026-10-10: **Munsell only.** ECOSTRESS/ASTER is not yet supplied (see
`data/README.md`). Every number below was produced by the scripts in `src/` and is
reproducible with the commands in `README.md`. Full tables:
`results/reconstruction.json`, `results/multiplication_tables.md`, `results/multiplication.json`.

## Plain-language summary

* **Compression works well for single spectra.** On 8 *held-out hue pages* of Munsell chips,
  K = 6 gives mean ΔE00 ≈ 0.4–0.6 and K = 8 gives ≈ 0.2. Train and test errors are almost
  identical. This reproduces a well-known result (Parkkinen et al. 1989; Maloney 1986).
* **Multiplying in a linear PCA basis fails quickly.** The K×(K+1)×(K+1) product tensor
  (the Galerkin projection of the product, as in Peercy 1993) is mathematically
  identical to decompress-multiply-recompress when nothing is clamped. I checked
  this numerically: max difference 4e-15. Both break down after **1–2 bounces**.
  The cause is not the operator: a basis fitted to single reflectances cannot represent the
  *darker, more saturated* product spectra. Even the best possible projection of the
  **true** product onto the basis (`raw_floor`) has exposure-normalised ΔE ≈ 5–26 at
  K = 6 for 1–3 bounces. A least-squares-fitted tensor did not help, since it shares that floor.
* **PCA in log-reflectance space removes the problem for products.** There,
  multiplication is *exactly* addition of weights, so error does not compound
  beyond the input representation error. At K = 6, exposure-normalised ΔE stays at 0.7–1.1
  over 1–5 random bounces; at K = 8 it stays at 0.3–0.5. The **catch** is that log-space
  weights are *not* closed under addition (summing radiance contributions) or under
  linear texture filtering, and getting colour out needs an 81-wide `exp` decode.
  This is a real cost and a design problem for Phase 2, not a solved issue.
  Using log/optical density for multiplicative mixing is an old idea; I have **not**
  done a literature search to establish whether log-PCA for spectral rendering
  products is published (it probably is in some form). **Do not treat this as novel yet.**
* **Baselines.** RGB is exact at 0 bounces under D65 by construction, and its error grows
  roughly linearly with bounces: exposure-normalised mean 2.3 at n=1, 6.3 at n=3, 9.9 at n=5.
  A **fixed 4-wavelength quadrature** (450/505/560/615 nm with fitted weights) is a
  surprisingly strong cheap baseline: 1.4 at n=0, growing to 3.1 at n=5. It beats linear PCA
  for any K ≤ 10 once there is a single multiplication. **Stochastic 4-wavelength (hero)
  sampling** is unbiased, so its error doesn't depend on bounce count, but it is noise:
  ΔE ≈ 12.8 with 1 sample, 2.9 with 16 and 0.73 with 256 samples, flat across bounces.
* **At equal state size:** log-PCA K=4 (1.7–2.8 over 1–5 bounces) is about the same as quad4
  (1.7–3.1) and better than RGB beyond n=1. Log-PCA K=6–8 is clearly the most accurate
  deterministic option here, but it costs more per path (see the cost table).

## Data (Step 1)

| dataset | loaded | kept (strict 380–780) | train | test | split unit |
|---|---|---|---|---|---|
| Munsell matt (UEF) | 1269 | 1269 | 1022 (32 hue pages) | 247 (8 hue pages) | Munsell hue page |
| ECOSTRESS | – (not supplied) | – | – | – | material name |

Test hue pages: 2.5GY, 2.5P, 5G, 5RP, 7.5BG, 7.5R, 10B, 10YR (every 5th page round the hue circle).
Munsell reflectance range is 0.030–0.839: there are no near-blacks, near-whites, or out-of-range values.

## PCA (Step 2): cumulative explained variance (train split, own value space)

| space | K=3 | 4 | 5 | 6 | 8 | 10 |
|---|---|---|---|---|---|---|
| raw | 0.9825 | 0.9919 | 0.9957 | 0.9973 | 0.9991 | 0.9997 |
| sqrt | 0.9835 | 0.9924 | 0.9958 | 0.9973 | 0.9992 | 0.9997 |
| logit | 0.9839 | 0.9928 | 0.9958 | 0.9974 | 0.9993 | 0.9997 |
| log | 0.9840 | 0.9927 | 0.9959 | 0.9974 | 0.9992 | 0.9997 |

![variance](results/figures/variance_explained.png)

## Reconstruction vs K (Step 3): held-out test split, ΔE00 under D65 / CIE 1931 2°

| space | K | RMSE | ΔE mean | ΔE p95 | ΔE max | decode left [0,1] before clamp |
|---|---|---|---|---|---|---|
| raw | 3 | 0.0212 | 3.51 | 7.90 | 14.61 | 2.0% |
| raw | 4 | 0.0144 | 1.15 | 2.55 | 7.47 | 0.8% |
| raw | 6 | 0.0089 | 0.56 | 1.59 | 3.12 | 0% |
| raw | 8 | 0.0052 | 0.19 | 0.49 | 1.76 | 0% |
| raw | 10 | 0.0031 | 0.12 | 0.27 | 1.10 | 0% |
| sqrt | 6 | 0.0083 | 0.46 | 1.28 | 2.45 | 0% |
| logit | 3 | 0.0203 | 2.86 | 6.11 | 9.43 | n/a (in range by construction) |
| logit | 6 | 0.0080 | 0.38 | 0.94 | 2.54 | n/a |
| logit | 8 | 0.0046 | 0.21 | 0.50 | 2.70 | n/a |
| log | 6 | 0.0091 | 0.59 | 1.75 | 3.75 | 0% |
| log | 8 | 0.0050 | 0.22 | 0.53 | 2.91 | 0% |
| log | 10 | 0.0029 | 0.06 | 0.15 | 0.25 | 0% |

The transformed spaces differ only slightly for single spectra. Logit is marginally best at K=6 and
guarantees [0,1]; raw needs clamping at K ≤ 5. Train vs test mean ΔE (raw): 0.55 vs 0.56 at K=6.

![recon](results/figures/recon_error_vs_k.png)

## Multiplication in weight space (Steps 4–5)

*Bounces n* = n multiplications, i.e. the product of n+1 spectra. *Random* = 20 000 chains of
distinct test spectra. *Self* = s^(n+1) for each of the 247 test spectra, a proxy for
inter-reflection inside one coloured material.

**Metric caveat (important).** The median L* of a random product is 57 (n=0), 25 (n=1),
1.9 (n=3) and 0.1 (n=5). Absolute ΔE00 near black is tiny for *any* error, so in the absolute
metric every method appears to *improve* with more bounces. I therefore report primarily an
**exposure-normalised** ΔE00: truth and estimate are scaled by the same factor so the true
Y = 20 (L* ≈ 52). This asks "is the colour right once the image is exposed for this light
path?" It is harsh on methods with an absolute error floor. Absolute numbers are in
`results/multiplication_tables.md`, and both metrics are plotted.

### Random chains, exposure-normalised ΔE00 (mean)

| method | K | n=0 | n=1 | n=2 | n=3 | n=5 |
|---|---|---|---|---|---|---|
| RGB (linear sRGB, unclamped) | – | 0.00 | 2.33 | 4.42 | 6.34 | 9.93 |
| quad4 (fixed 4 λ, fitted weights) | – | 1.36 | 1.74 | 2.11 | 2.46 | 3.12 |
| hero4, 16 spp | – | 3.15 | 2.90 | 2.86 | 2.85 | 2.96 |
| hero4, 256 spp | – | 0.79 | 0.73 | 0.72 | 0.71 | 0.74 |
| raw_floor (projection of TRUE product) | 6 | 0.60 | 5.21 | 13.77 | 25.65 | 64.90 |
| recon_product (decode inputs, exact product) | 6 | 0.60 | 0.88 | 1.08 | 1.26 | 1.57 |
| raw DMR (clamped) | 6 | 0.60 | 5.26 | 14.01 | 26.42 | 67.25 |
| raw tensor (Galerkin) | 4 | 1.22 | 8.63 | 28.39 | 43.57 | 60.29 |
| raw tensor (Galerkin) | 6 | 0.60 | 6.68 | 25.44 | 40.93 | 51.37 |
| raw tensor (Galerkin) | 8 | 0.21 | 2.64 | 10.75 | 27.20 | 85.44 |
| raw tensor (Galerkin) | 10 | 0.12 | 1.55 | 6.98 | 19.07 | 45.87 |
| raw tensor (LS-fitted) | 6 | 0.60 | 6.60 | 24.89 | 40.28 | 49.35 |
| sqrt tensor | 6 | 0.46 | 2.16 | 5.51 | 10.36 | 31.91 |
| sqrt tensor | 10 | 0.08 | 0.73 | 2.00 | 4.93 | 22.78 |
| **log-PCA, add weights** | 4 | 1.34 | 1.72 | 2.04 | 2.30 | 2.76 |
| **log-PCA, add weights** | 6 | 0.57 | 0.73 | 0.85 | 0.96 | 1.13 |
| **log-PCA, add weights** | 8 | 0.22 | 0.29 | 0.35 | 0.40 | 0.49 |
| **log-PCA, add weights** | 10 | 0.06 | 0.08 | 0.10 | 0.11 | 0.14 |

### Self chains (s^(n+1)), absolute ΔE00 (mean). These stay bright enough for the absolute metric to mean something

| method | K | n=0 | n=1 | n=2 | n=3 | n=5 |
|---|---|---|---|---|---|---|
| RGB | – | 0.00 | 2.00 | 2.63 | 2.62 | 2.14 |
| quad4 | – | 1.36 | 1.52 | 1.39 | 1.20 | 0.80 |
| hero4, 256 spp | – | 0.85 | 0.58 | 0.41 | 0.27 | 0.18 |
| raw DMR | 6 | 0.56 | 2.40 | 2.84 | 2.92 | 2.87 |
| raw tensor | 6 | 0.56 | 3.24 | 5.39 | 6.79 | 8.36 |
| raw tensor | 8 | 0.19 | 1.49 | 2.47 | 3.08 | 3.74 |
| sqrt tensor | 6 | 0.46 | 1.34 | 1.65 | 1.68 | 1.47 |
| log-PCA add | 6 | 0.59 | 0.83 | 0.86 | 0.82 | 0.70 |
| log-PCA add | 8 | 0.22 | 0.30 | 0.29 | 0.27 | 0.21 |

![bounces](results/figures/error_vs_bounces_random_expo.png)
![bounces self](results/figures/error_vs_bounces_self_abs.png)
![k](results/figures/error_vs_k_3bounces.png)

### Where each method breaks down (threshold: mean ΔE00 > 2, exposure-normalised, random chains)

| method | K=4 | K=6 | K=8 | K=10 |
|---|---|---|---|---|
| raw tensor / DMR | n=1 | n=1 | n=1 (2.6) | n=2 |
| sqrt tensor | n=1 | n=1 (2.2) | n=2 | n=2 (2.00, borderline) |
| log-PCA add | n=2 (2.04) | not within n ≤ 5 | not within n ≤ 5 | not within n ≤ 5 |
| RGB | n=1 | | | |
| quad4 | n=2 (2.11) | | | |

### Cost per multiplication (operation counts, not measured GPU timings)

| method | state floats | ALU per multiply | colour readout |
|---|---|---|---|
| RGB | 3 | 3 mul | free |
| quad4 / hero4 | 4 | 4 mul | 4×3 MAC (hero4 also needs per-hit spectral evaluation and many spp) |
| raw tensor | K | K(K+1)² MAC: 100 (K=4), 294 (K=6), 648 (K=8) | 3(K+1) MAC |
| raw DMR | K | ≈ 3·81·K + 81: 1539 (K=6) | 3(K+1) MAC |
| log-PCA add | K (+1 count) | **K adds** | 81·K MAC + 81 exp + 243 MAC per decode |

The log-PCA readout cost recurs at **every point where radiance is added**, such as each
emitter hit or NEE sample in a path tracer, because addition is not closed in log space.

## What worked, what failed, what surprised me

**Worked:** low-K PCA for single spectra; log-space PCA for products; the colorimetry
pipeline (verified against all 34 Sharma pairs and colour-science); export round-trip.

**Failed:** the linear-basis product tensor, and DMR, for more than one bounce. Increasing K
does not reliably help: at n=5, raw tensor K=8 (85) is worse than K=6 (51). Fitting the
tensor by least squares changed almost nothing.

**Surprised me:**
1. The absolute ΔE00 *decreases* with bounce count for every method (dark-colour artefact). Without
   exposure normalisation I would have reported the opposite conclusion.
2. The failure of the linear tensor is a **basis** problem, not an operator problem: `raw_floor` ≈ DMR.
3. A dumb fixed 4-wavelength quadrature beats a K=10 linear PCA tensor after a single bounce.
4. Clamping in DMR helps only slightly compared with the unclamped tensor; it does not fix the floor.

## Limitations

* **Munsell only.** Its spectra are smooth, mid-range (0.03–0.84) and include no neutrals,
  blacks, fluorescents or minerals with sharp absorption features. The ECOSTRESS results may differ a lot.
* **D65 only.** RGB is exact at n=0 under D65 by construction. The main advantage of spectral
  methods (illuminant change, metamerism) has **not** been tested yet.
* Small test set: 247 spectra from 8 hue pages. Random chains reuse them heavily.
* Cost figures are operation counts, not WebGPU measurements.
* The 4-wavelength quadrature was fitted on training singles and products with a 1/(Y+1) weighting heuristic.

## Suggested next steps (need your call)

1. Supply ECOSTRESS, then re-run everything and decide the coverage policy.
2. Test illuminant changes (A, F-series, LED), where RGB should lose clearly.
3. Address log-PCA's addition problem. Options include carrying linear XYZ for accumulated
   radiance and log-PCA only for path throughput (decode once per emission event), or a hybrid.
4. Try a linear basis fitted on *products* or with renormalisation of brightness per bounce.
5. Do a literature search on log-domain spectral bases before claiming anything (see LAB_NOTEBOOK).

## References (standard / prior work, not claimed as ours)

* Parkkinen, Hallikainen & Jääskeläinen (1989), JOSA A 6(2): PCA of Munsell spectra.
* Maloney (1986), JOSA A 3(10): low-dimensional linear models of surface reflectance.
* Peercy (1993), SIGGRAPH: linear colour representations for full spectral rendering (product matrices in a linear basis).
* Wilkie et al. (2014), EGSR: hero wavelength spectral sampling. PBRT-v4 uses 4 stratified wavelengths.
* Meng, Simon, Hanika & Dachsbacher (2015), CGF/EGSR: physically meaningful rendering using tristimulus colours.
* Jakob & Hanika (2019), CGF/EG: a low-dimensional function space for efficient spectral upsampling.
* Peters et al. (2019), TOG/SIGGRAPH: moment-based representation of bounded signals for spectral rendering.
* Sharma, Wu & Dalal (2005), Color Res. Appl. 30(1): CIEDE2000 implementation notes and test data.
