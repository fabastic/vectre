# Pre-registration: patent-track experiment (written 2026-10-11, before any experiment)

Branch: `patent-track`. Everything private. This file is committed before any result is computed
and must not be edited afterwards, except to append a dated "post-hoc note" section that leaves
the rules below unchanged.

## Hypothesis

"Method X beats light-aware hero-4λ at equal GPU time and memory at 1 and 4 spp under D65, F11
and the 610 nm line."

## Baseline

Light-aware hero-4λ + Jakob & Hanika (2019) uplift, exactly as in Phase 2 (`src/webgpu/pt.wgsl`
mode 1): 4 stratified wavelengths per camera sample from pdf ∝ (x̄+ȳ+z̄)·E on the 1 nm grid,
reflectance = J&H sigmoid-quadratic from the 32³ LUT. Hero wavelength sampling is Wilkie et al.
2014; the uplift is Jakob & Hanika 2019. Neither is ours.

## Pass rule (fixed now)

On the existing Cornell scenes (`cornell_d65`, `cornell_f11`, `cornell_nb610`; 512²; ≤ 5
scattering vertices; NEE), against the converged 8192-spp CPU references, with the Phase 2 metric
(mean CIEDE2000; same exposure; emitter **and** black background pixels excluded):

1. **Accuracy:** mean ΔE00 of X must be **≥ 30% lower** than hero-4λ's at **both 1 and 4 spp**,
   under **all three** lights (6 conditions, all must pass).
2. **Noise / robustness:** each condition is run with **5 seeds**. The pass test uses the mean
   over seeds. I also report the standard deviation across seeds of the mean ΔE, and the per-seed
   paired difference X − hero-4λ. A condition only passes if the 30% reduction holds for the mean
   **and** the mean paired improvement exceeds 2× the standard deviation of the paired differences
   (so it isn't seed luck).
3. **Cost:** median GPU frame time (timestamp queries, ≥ 5 repeats, same adapter) at most **10%
   higher** than hero-4λ, and bound buffer memory at most **25% higher**, at each spp.

A candidate passes only if 1, 2 and 3 all hold in all 6 conditions.

## Equal-cost definition

Same scene, same spp, same resolution, same adapter (Intel iGPU `gen-12lp` in this session; the
RTX 4060 is run by the owner), median of repeated identical renders, buffer bytes as in Phase 2's
`memoryForMode`.

## Candidates (at most three)

* **(a) Log-PCA throughput + per-light XYZ map.** Path throughput is K log-PCA weights (K = 4 and 6)
  plus a bounce count. Products are exact weight additions (Phase 1.5). Each NEE contribution maps
  (count, weights) to XYZ through a small per-light fitted function (low-order polynomial or tiny
  fixed network) instead of the 81-wavelength exp decode. Deterministic: no wavelength sampling.
* **(b) Log-PCA throughput + per-light Q-node spectral quadrature decode.** Same throughput as (a), but
  the decode evaluates exp(nμ + Bw) at Q = 8 wavelengths whose positions and weights are optimised
  per light for the measure CMF·E. Cheaper than (a)'s network and still deterministic.
* **(c) Hero with more wavelengths per path (8λ) and/or cross-pixel wavelength stratification.**
  Reduces wavelength-sampling noise at small extra per-hit cost; geometry is unchanged.

Why these: Phase 2 showed the 1–4 spp gap to RGB is mostly *colour* noise from wavelength
sampling. (a) and (b) remove wavelength sampling entirely; (c) reduces it.

## Feasibility gate (pre-registered, computed first)

All three candidates share hero-4λ's *path* (geometry) sampling and only change how the spectrum is
carried. Their per-pixel error is therefore bounded below by an **oracle** that carries the *exact*
J&H spectrum at all 401 wavelengths along each path (zero wavelength-sampling noise; CPU only, not a
real-time method). I will compute oracle vs hero-4λ on the CPU reference renderer with the same J&H
uplifted spectra, at 1 and 4 spp, 5 seeds, same metric.

**Gate rule:** if the oracle itself is not ≥ 30% better than hero-4λ (mean over seeds) in every one
of the 6 conditions, then no candidate that only changes the spectral estimator can pass rule 1.
In that case I stop, write the negative result, and do not build the candidates. (If the gate
fails only for some conditions, the verdict is still "fail" under the all-6 rule.)

## Order of work

1. This file (commit).
2. Prior-art search, ≥ 3 queries per candidate (PRIORART.md); drop clearly published candidates.
3. Feasibility gate on CPU.
4. Only if the gate passes: CPU/torch emulation of surviving candidates; then WebGPU only if close.
5. Report in PATENT_TRACK.md.

## Stopping rule

Stop after about 2 hours of work, at a failed feasibility gate, or when the literature check kills
all candidates, whichever comes first, and write the negative result. The pass rule above is not
changed after seeing results. If I think it was wrong, I will say so in the report and keep the
original verdict.
