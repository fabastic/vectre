
---

# Phase 2 (2026-10-10): tonemapper control, CPU reference, WebGPU RGB vs hero-4λ

## Task 0: tonemapper check

**Formulas** (`src/tonemap.py`; the identical WGSL is in `src/webgpu/display.wgsl`). Input is scene-linear sRGB (D65 white) after exposure:
* **per-channel Reinhard** (Phase 1.5): y_c = x_c⁺ / (1 + x_c⁺), x⁺ = max(x, 0).
* **max-RGB (hue-preserving)**: x⁺ = max(x, 0); m = max_c x⁺_c; y = x⁺ · (m/(1+m)) / m = x⁺ / (1+m).
  Channel *ratios* are kept exactly. Out-of-gamut input is handled only by the negative clip.
* **Oklch (chroma-preserving)**: Y = luminance(x); Y′ = Y/(1+Y); (L, C, h) = Oklch(x) with a signed cube
  root; L′ = Y′^(1/3); C′ = C·L′/L; back to linear sRGB; if outside [0,1]³, C′ is reduced by
  bisection at constant L′ and h. Oklab is Ottosson (2020); the constants are verified against
  colour-science and against the numerical inverse in tests.

Same samples as Phase 1.5 (held-out Munsell, 1 nm truth). Chroma is CIELAB C*ab with the D65
white. |Δh| is the mean absolute hue difference from the **scene-linear** truth hue, for samples
with scene chroma > 10. Full table (1x/10x/100x, both chain types): `results/tonemap_check_table.md`.

| light | samples | intensity | tonemap | C* truth | C* RGB | RGB/truth chroma | |Δh| truth (°) | |Δh| RGB (°) | ΔE00 RGB vs truth |
|---|---|---|---|---|---|---|---|---|---|
| D65 | single | 1x | reinhard_channel | 16.5 | 16.5 | 1.00 | 2.1 | 2.1 | 0.00 |
| D65 | single | 1x | maxrgb | 18.9 | 18.9 | 1.00 | 0.0 | 0.0 | 0.00 |
| D65 | single | 1x | oklch | 19.4 | 19.4 | 1.00 | 0.0 | 0.0 | 0.00 |
| D65 | single | 100x | reinhard_channel | 5.3 | 5.3 | 1.00 | 12.2 | 12.2 | 0.00 |
| D65 | single | 100x | maxrgb | 31.0 | 31.0 | 1.00 | 0.0 | 0.0 | 0.00 |
| D65 | single | 100x | oklch | 6.8 | 6.8 | 1.00 | 1.9 | 1.9 | 0.00 |
| D65 | self | 1x | reinhard_channel | 15.0 | 15.9 | 1.06 | 2.9 | 7.0 | 1.72 |
| D65 | self | 1x | maxrgb | 15.2 | 16.3 | 1.07 | 2.9 | 7.8 | 1.72 |
| D65 | self | 1x | oklch | 14.0 | 16.3 | 1.17 | 1.8 | 7.8 | 2.37 |
| D65 | self | 100x | reinhard_channel | 39.9 | 36.4 | 0.91 | 16.4 | 11.4 | 4.07 |
| D65 | self | 100x | maxrgb | 48.8 | 49.7 | 1.02 | 4.9 | 8.5 | 3.56 |
| D65 | self | 100x | oklch | 32.2 | 32.5 | 1.01 | 5.3 | 8.7 | 4.32 |
| NB610 | single | 1x | reinhard_channel | 81.7 | 78.1 | 0.96 | 7.6 | 9.1 | 2.57 |
| NB610 | single | 1x | maxrgb | 81.7 | 78.1 | 0.96 | 7.6 | 9.1 | 2.57 |
| NB610 | single | 1x | oklch | 75.5 | 67.8 | 0.90 | 6.5 | 10.0 | 5.18 |
| NB610 | single | 100x | reinhard_channel | 104.1 | 100.8 | 0.97 | 7.2 | 8.3 | 1.63 |
| NB610 | single | 100x | maxrgb | 104.1 | 100.8 | 0.97 | 7.2 | 8.3 | 1.63 |
| NB610 | single | 100x | oklch | 3.5 | 6.1 | 1.74 | 10.7 | 13.2 | 5.14 |
| NB610 | self | 1x | reinhard_channel | 28.3 | 29.8 | 1.05 | 3.5 | 4.1 | 2.28 |
| NB610 | self | 1x | maxrgb | 28.3 | 29.8 | 1.05 | 3.5 | 4.1 | 2.28 |
| NB610 | self | 1x | oklch | 26.9 | 28.0 | 1.04 | 2.1 | 7.1 | 3.96 |
| NB610 | self | 100x | reinhard_channel | 70.6 | 67.8 | 0.96 | 8.8 | 8.7 | 3.67 |
| NB610 | self | 100x | maxrgb | 70.6 | 67.8 | 0.96 | 8.8 | 8.7 | 3.67 |
| NB610 | self | 100x | oklch | 31.4 | 23.8 | 0.76 | 9.6 | 12.9 | 8.67 |
| NEONLIKE | single | 1x | reinhard_channel | 75.7 | 73.3 | 0.97 | 6.6 | 10.6 | 3.86 |
| NEONLIKE | single | 1x | maxrgb | 77.8 | 75.1 | 0.97 | 8.6 | 12.2 | 3.35 |
| NEONLIKE | single | 1x | oklch | 74.1 | 67.7 | 0.91 | 5.9 | 11.1 | 5.71 |
| NEONLIKE | single | 100x | reinhard_channel | 90.1 | 86.1 | 0.95 | 30.7 | 36.3 | 10.26 |
| NEONLIKE | single | 100x | maxrgb | 101.3 | 100.8 | 0.99 | 8.2 | 11.5 | 4.10 |
| NEONLIKE | single | 100x | oklch | 3.8 | 6.9 | 1.83 | 9.7 | 13.9 | 4.11 |
| NEONLIKE | self | 1x | reinhard_channel | 27.0 | 28.4 | 1.05 | 4.3 | 7.4 | 2.64 |
| NEONLIKE | self | 1x | maxrgb | 27.3 | 28.6 | 1.05 | 4.9 | 7.8 | 2.59 |
| NEONLIKE | self | 1x | oklch | 25.4 | 27.5 | 1.08 | 2.2 | 11.4 | 4.31 |
| NEONLIKE | self | 100x | reinhard_channel | 64.1 | 63.6 | 0.99 | 22.5 | 20.7 | 8.75 |
| NEONLIKE | self | 100x | maxrgb | 68.6 | 68.5 | 1.00 | 9.3 | 11.6 | 6.24 |
| NEONLIKE | self | 100x | oklch | 30.2 | 27.8 | 0.92 | 9.1 | 16.0 | 9.03 |

**Plain answer: once the tonemapper is controlled for, there is no RGB-specific loss of colour
purity.** With the hue-preserving max-RGB operator, RGB's displayed chroma is 0.96–1.07x the
spectral truth's in every case tested (D65, the 610 nm line and neon-like; 1x/10x/100x). What
remains is ordinary colour error:
* **hue:** RGB's mean hue error relative to the scene truth is up to 4.9° larger than the truth's own
  display hue error (D65 self-products: 7.8° vs 2.9°; neon-like: up to +3.6°; one 610 nm case:
  0.3° smaller);
* **total:** ΔE00 RGB vs truth after max-RGB tonemapping is 0 (D65 single surfaces, exact by
  construction) to 6.2 (neon-like self-products at 100x).

The tonemappers themselves differ a lot:
* **Per-channel Reinhard** shifts hue (|Δh| up to 31° for neon-like at 100x) and desaturates.
* **max-RGB** keeps hue (0° under D65) and keeps chroma.
* **Oklch** keeps hue but must drop chroma at high luminance (C* falls to 3–7 at 100x for both
  truth and RGB), because bright saturated colours do not fit the display gamut near white.
* Under the 610 nm line, even the truth shows |Δh| ≈ 7° with max-RGB. That comes from clipping
  the out-of-gamut negative channels, not from RGB rendering.

**max-RGB is now the default display tonemap** (Phase 2 harness and demo).
