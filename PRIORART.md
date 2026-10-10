# Prior-art check for the patent-track candidates (2026-10-11)

Method: web search (papers, GitHub, patent hits as returned by search; I could not query Google
Patents' own search interface directly). Each line lists the query. "None found in N searches"
means exactly that, not that nothing exists. No GPL code (e.g. Metameric) was read.

## Queries run

| # | candidate | query |
|---|---|---|
| 1 | a | log-space spectral basis path throughput multiplication addition spectral rendering logarithmic PCA |
| 2 | a, b | linear model spectral rendering product of reflectances basis coefficients real-time Peercy Drew Finlayson multispectral processing without spectra |
| 3 | a | patent spectral rendering throughput represented as basis coefficients logarithm exponential decode tristimulus |
| 4 | a | optical density log reflectance basis spectral rendering exponential multiplicative spectra compact representation graphics |
| 5 | b | Meyer 1988 wavelength selection synthetic image generation Gaussian quadrature spectral rendering |
| 6 | b | illuminant-adapted quadrature wavelengths spectral rendering optimized sample wavelengths per light source |
| 7 | b | Wallis 1975 Gaussian quadrature tristimulus values weighting functions illuminant wavelengths |
| 8 | b | "Real-Time Spectral Rendering" Color and Imaging Conference 2013 sharp basis four dimensions |
| 9 | c | spectral rendering stratified wavelength samples across pixels blue noise wavelength color noise reduction |
| 10 | c | hero wavelength more than four wavelengths per path cost color noise spectral samples count |
| 11 | c | spectral path tracing low sample count color noise denoising wavelength sampling chromatic noise real-time |
| 12 | all | Google Patents spectral rendering wavelength sampling noise reduction GPU real-time patent |

## (a) Log-PCA throughput + per-light map from log-weights to XYZ

**Closest prior work:**
* **Linear-basis spectral rendering with coefficient arithmetic:** Peercy 1993 (SIGGRAPH);
  Drew & Finlayson 2003 (JOSA A), "Multispectral processing without spectra" (sharpened basis, so
  products become per-coefficient multiplication).
* **Waddle 2013** (IS&T CIC 21, DOI 10.2352/CIC.2013.21.1.art00044) and his 2018 UVic thesis "Fast
  spectral multiplication for real-time rendering": optimised sharp basis, good accuracy at 4
  dimensions, "cost only slightly above RGB".
* **Yu, Guarnera & Guarnera 2026** (arXiv 2602.18741, SIGGRAPH Asia 2026 per arXiv): learned compact
  linear spectral codes. Scaling and addition are exact, products approximate, carried through RGB
  pipelines.
* **Exponential/Bouguer-law construction of reflectances:** Wang, Xu & Sun, "Practical construction of
  reflectances for spectral rendering" (WSCG; otik.zcu.cz/handle/11025/973). The log/optical-density
  domain itself is textbook physics.
* **Patents (search hits):** US5710876A (full-spectral illumination rendering), US7860304B2 (basis
  functions from sensor wavelength dependence), US7929753B2 (log coding in colour coordinate
  systems). None matched log-domain basis throughput with a learned per-light XYZ decode, as far as
  the snippets show.

**What is different:** exact closure of path-throughput products as *additions* in a log-PCA basis
(the published linear/sharp bases make products approximate), plus a per-light *non-linear* fitted
map straight to XYZ that replaces the per-wavelength exp decode. The combination: none found in
4 searches. The parts are known.

**Verdict: unclear.** It is a combination of known ingredients; I cannot rule out a paper or patent
I didn't reach.

## (b) Deterministic low-dimensional spectral throughput with a cheaper decode (my variant: log-PCA + per-light Q-node quadrature)

**Closest prior work:**
* The *class* "deterministic low-dimensional spectral throughput at near-RGB cost" is **published**:
  Drew & Finlayson 2003 and Waddle 2013 (4 dimensions, real-time, slightly above RGB cost).
* Choosing a few wavelengths / quadrature for colour integrals: Meyer 1988, "Wavelength selection for
  synthetic image generation" (CVGIP 41); Wallis 1975, "Fast computation of tristimulus values by use
  of Gaussian quadrature" (JOSA 65). Both are cited in Peercy 1993's references; I didn't read either
  paper, so their details are not verified. ASTM E2022 weighting factors are the standard
  illuminant-weighted tables.
* Light-aware *stochastic* wavelength selection: Peters 2025 blog; Vectre Phase 2 baseline.

**What is different:** only the pairing of a log basis with per-light optimised deterministic
quadrature nodes. Phase 1.5 already showed fixed-node quadrature collapsing under line spectra
(fixed 4λ: ΔE 13 for the 610 nm line, 50 for neon-like); per-light nodes would address that, but this
is the classical weighted-quadrature idea.

**Verdict: published** (as specified in the brief: deterministic low-dimensional throughput with a cheap
decode). The specific log + per-light-quadrature pairing is unclear at best. **Dropped as a separate
candidate**; its decode idea folds into (a) as one possible "per-light map".

## (c) More wavelengths per path (8λ) and/or cross-pixel wavelength stratification

**Closest prior work:**
* Wilkie et al. 2014 (hero wavelength) uses a constant number of wavelengths per path. The count is a
  parameter of that method (pbrt-v4 exposes it at compile time; not re-checked this session).
  Blender devtalk users report colour noise largely gone at 8–10 wavelengths (anecdotal).
* Evans & McCool 1999: wavelength clusters on a shared path.
* Within-pixel correlation of wavelengths: Petitjean, Bauszat & Eisemann 2018 (EGSR/CGF), "Spectral
  gradient sampling for path tracing".
* Per-pixel spectral importance distributions: van de Ruit & Eisemann 2021 (cited in a TU Delft thesis).
* Spectral-aware denoising: Rouphael 2022 (EG poster).
* Blue-noise / low-discrepancy *wavelength* sampling across pixels: none found in 2 searches (#9, #11).

**What is different:** nothing for 8λ. For cross-pixel stratification, possibly the blue-noise
distribution across screen space. **However**, cross-pixel stratification leaves each pixel's
marginal estimator unchanged (same per-pixel variance), so it **cannot lower the pre-registered
per-pixel mean ΔE**; it would only help a filtered or perceptual metric.

**Verdict: 8λ published. Cross-pixel stratification possibly novel, but by construction unable to
pass the pre-registered metric.** Kept only as a cost/accuracy data point (8λ) in the feasibility gate.

## Consequence for the experiment

The only survivor as a distinct method is **(a)**, verdict *unclear*. Before building it, the
pre-registered feasibility gate (PREREG.md) checks whether *any* exact deterministic spectral
estimator on the same paths, i.e. an oracle carrying all 401 wavelengths, could beat hero-4λ by 30%.
