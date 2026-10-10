# Patent-track experiment: result (2026-10-11)

**Verdict: FAIL.** No candidate can meet the pre-registered rule. The pre-registered feasibility
gate failed: even an exact oracle, which removes wavelength-sampling noise entirely, does not beat
light-aware hero-4λ by 30% in 4 of the 6 required conditions. Per the stopping rule, I did not build
the candidates and took no GPU measurements.

## Pre-registered rule (from PREREG.md, committed in db78ebc before any experiment)

Method X must, on the Cornell scenes (D65, F11, 610 nm line; 512²; Phase 2 metric vs the converged
8192-spp references, emitter and background excluded), have mean ΔE00:
* **≥ 30% lower** than light-aware hero-4λ + Jakob–Hanika at **both 1 and 4 spp under all three
  lights**;
* a mean paired improvement over 5 seeds of **> 2× the SD** of the paired differences;
* **≤ 10% more** GPU frame time and **≤ 25% more** buffer memory (same adapter).

Feasibility gate: an oracle carrying all 401 wavelengths exactly along the same paths bounds every
candidate that only changes the spectral estimator. If the oracle is not ≥ 30% better in all 6
conditions, stop.

## Gate measurement (CPU emulation, same integrator, same J&H-uplifted spectra, 5 seeds)

The CPU emulation of hero-4λ reproduces the Phase 2 GPU numbers (D65 1 spp: 18.27 CPU vs 18.27 GPU;
F11 1 spp: 17.36 vs 17.33; 610 nm 1 spp: 11.02 vs 11.02; 4 spp within 0.03).

| light | spp | hero-4λ (baseline) | oracle (exact, all 401 λ) | oracle reduction | hero-8λ (candidate c) | hero-8λ reduction |
|---|---|---|---|---|---|---|
| D65 | 1 | 18.273 ± 0.013 | 12.870 ± 0.003 | **29.6% (fail)** | 13.953 ± 0.004 | 23.6% (fail) |
| D65 | 4 | 10.656 ± 0.010 | 7.232 ± 0.006 | 32.1% (pass) | 7.928 ± 0.008 | 25.6% (fail) |
| F11 | 1 | 17.363 ± 0.017 | 12.376 ± 0.005 | **28.7% (fail)** | 14.176 ± 0.008 | 18.4% (fail) |
| F11 | 4 | 10.122 ± 0.012 | 6.908 ± 0.008 | 31.8% (pass) | 7.954 ± 0.007 | 21.4% (fail) |
| 610 nm | 1 | 11.024 ± 0.016 | 10.980 ± 0.006 | **0.4% (fail)** | 11.002 ± 0.016 | 0.2% (fail) |
| 610 nm | 4 | 5.293 ± 0.008 | 5.274 ± 0.009 | **0.4% (fail)** | 5.280 ± 0.008 | 0.2% (fail) |

Values are mean ΔE00 ± SD across 5 seeds of the per-image mean ΔE. The SD across seeds is small
(≤ 0.02) because each image averages about 226k pixels; per-pixel noise is large. Paired
improvements exceed 2 SD everywhere except the oracle at 610 nm / 4 spp, where 0.019 ± 0.012 is not
significant. Raw data: `results/patent/gate.json`; code: `src/patent/gate.py`.

**Why it fails:**
* At 1 spp most of the remaining error is *geometric* path-sampling noise, which no spectral
  representation removes. The exact oracle ends at 12.87 under D65, essentially RGB's 12.88 from
  Phase 2.
* Under the 610 nm line, light-aware hero-4λ is already spectrally almost noise-free, because all
  4 wavelengths land on the line. There is nothing left for a spectral method to remove (0.4%).

## Per-candidate results

| candidate | prior-art verdict (PRIORART.md) | built? | ΔE (best case) | frame time | memory | pre-registered rule |
|---|---|---|---|---|---|---|
| (a) log-PCA throughput + per-light XYZ map | unclear (combination of known parts) | no | bounded below by the oracle: fails D65 1 spp, F11 1 spp and both 610 nm conditions even with zero approximation error | not measured | not measured | **FAIL** (by the pre-registered gate) |
| (b) deterministic low-dim throughput, cheap decode | **published** as a class (Drew & Finlayson 2003; Waddle 2013) | no (dropped) | same oracle bound | not measured | not measured | **FAIL** (and published) |
| (c) hero-8λ / cross-pixel stratification | 8λ: published (Wilkie 2014 uses a constant N); cross-pixel stratification can't change the per-pixel metric | 8λ CPU-emulated only | 13.95 / 7.93 / 14.18 / 7.95 / 11.00 / 5.28 (−0.2% to −25.6%) | not measured | not measured | **FAIL** (accuracy alone) |

No GPU numbers were taken. The stopping rule fired at the gate, before any GPU work, so there are no
Intel iGPU or RTX 4060 frame-time or memory results for any candidate.

## Closest prior art and what is distinguishing

* **(a):** linear/sharp-basis coefficient arithmetic (Peercy 1993; Drew & Finlayson 2003; Waddle 2013,
  4 dimensions at slightly above RGB cost); learned compact spectral codes (Yu, Guarnera & Guarnera,
  arXiv 2602.18741, 2026); exponential/Bouguer-law reflectance construction (Wang, Xu & Sun).
  Distinguishing: exact product closure by log-domain addition plus a per-light non-linear map to
  XYZ. That combination was not found in 4 searches, so the verdict is unclear. **It cannot pass the
  rule regardless of novelty.**
* **(b):** published as specified. Quadrature roots: Meyer 1988, Wallis 1975 (details not verified).
* **(c):** hero wavelength (Wilkie et al. 2014), spectral gradient sampling (Petitjean et al. 2018),
  wavelength clusters (Evans & McCool 1999).

## Plain statement

**Not enough to take to a patent attorney.** No candidate met the pre-registered performance rule,
and the oracle bound shows that no method which only changes how the spectrum is carried can meet
it on these scenes. The one possibly distinguishing combination, (a), is unclear against prior art,
and its parts are published. This statement describes measurements and search results only; it is
not a legal opinion.

## Was the rule wrong? (verdict unchanged)

Possibly, in two ways; I report them and keep the original verdict.
1. Requiring a ≥ 30% gain under the 610 nm line is structurally unreachable for spectral-noise
   methods: light-aware hero-4λ is already nearly exact there (oracle gain 0.4%).
2. The per-pixel mean ΔE at 1 spp is dominated by geometric noise, which spectral methods don't touch.
   A rule that separates chromatic from luminance error, or one evaluated after a denoiser, would
   measure what these candidates change.

Changing the rule now would be post-hoc, so the verdict stays **FAIL**.

Side observation, not part of the verdict: hero-8λ cuts mean ΔE by 18–26% under D65 and F11 at
1–4 spp. That is a published technique, and its GPU cost was not measured.

## Limitations

* The 610 nm source is synthetic (Gaussian, FWHM 5 nm), not a measured lamp.
* One small Cornell-like scene, Lambertian only, six CIE 224 CES materials, ≤ 5 bounces.
* The gate was CPU emulation; it matches the Phase 2 GPU hero-4λ numbers, but no GPU timings were
  taken for any candidate.
* Intel iGPU only in this project so far; the RTX 4060 is to be run by the owner.
* The prior-art search was web search only (no direct Google Patents query interface, no paywalled
  full texts); "none found" is limited to the listed queries.
