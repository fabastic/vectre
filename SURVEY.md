# Survey: open spectral-rendering work, and where Vectre could fill gaps

Date: 2026-10-10. Method: web search plus page fetches, with licences and last-activity dates
from the GitHub API (`license.spdx_id`, `pushed_at`) where a repo exists. "Not verified" means I
couldn't confirm it this session. "None found in N searches" is a search result, not proof of
absence. No code was copied, nothing was run, and nobody was contacted.

## 1. Open-source spectral renderers (native)

| name | URL | what it does | spectral / RGB | licence | last activity | browser |
|---|---|---|---|---|---|---|
| Mitsuba 3 | github.com/mitsuba-renderer/mitsuba3 | research renderer, forward + differentiable | both (spectral and RGB variants; J&H uplift via rgb2spec, per project docs, not re-checked) | BSD-style (LICENSE text; API reports NOASSERTION) | push 2026-10-08 | no |
| pbrt-v4 | github.com/mmp/pbrt-v4 | textbook renderer (CPU/GPU) | spectral: samples 4 wavelengths per path, RGB uplift by sigmoid-polynomial tables (as cited in our Phase 1.5; not re-checked this session) | Apache-2.0 | 2026-09-08 | no |
| simple-spectral (Mallett) | github.com/geometrian/simple-spectral | minimal reference path tracer for "Spectral Primary Decomposition" (EGSR 2019) | spectral, hero wavelength | MIT | 2020-07-19 | no |
| Peters' path_tracer (`spectral` branch) | github.com/MomentsInGraphics/path_tracer | real-time GPU path tracer; spectral mode with Fourier sRGB uplift; wavelengths importance-sampled by ‖CMF‖₁·illuminant, 4 per path | spectral + RGB, switchable | BSD-3-Clause | branch commit 2025-11-08; repo push 2026-06-20 | no (native GLSL) |
| rust-pathtracer (Gillett-Hernandez) | github.com/gillett-hernandez/rust-pathtracer | wavelength-aware path tracer | spectral (single-wavelength sampling per README) | GPL-3.0 | 2024-07-09 | no |
| iris | github.com/64/iris | spectral CPU path tracer (Rust) | spectral | GPL-3.0 | 2025-01-07 | no |
| Spectrumizer | github.com/JCSaltFish/Spectrumizer | GPU spectral path tracer, Vulkan/OpenGL | spectral | Apache-2.0 | 2026-02-28 | no |
| SlyZ1/Path-Tracer | github.com/SlyZ1/Path-Tracer | C++/OpenGL; hero-4λ integrator switchable against RGB | both | MIT | 2026-09-28 | no |
| Lambda | github.com/TomCrypto/Lambda | simple spectral path tracer | spectral | not verified (NOASSERTION) | 2023-09-16 | no |
| luculentus | github.com/ruuda/luculentus | proof-of-concept spectral tracer | spectral | GPL-3.0 | 2014-10-19 | no |
| pbrt-v2-spectral | github.com/ydnality/pbrt-v2-spectral | pbrt-v2 fork with 31 spectral samples (RenderToolbox3) | spectral | none stated | 2015-08-17 | no |
| LuxCore | github.com/LuxCoreRender/LuxCore | production renderer | not verified (forum threads discuss spectral; mode not confirmed) | Apache-2.0 | 2026-10-09 | no |
| Tungsten | github.com/tunabrain/tungsten | research renderer | not verified | not verified (API: NOASSERTION) | 2022-03-10 | no |
| appleseed | github.com/appleseedhq/appleseed | production renderer | not verified | MIT | 2026-06-11 | no |

Methods worth noting: hero wavelength (Wilkie et al. 2014) is the common baseline. Light-aware
wavelength importance sampling (pdf ∝ CMF·illuminant) is used in Peters' 2025 tracer, which is
the same idea as Vectre Phase 2. Uplift approaches: J&H sigmoid-polynomial (pbrt-v4, Mitsuba),
Fourier sRGB (Peters), spectral primaries (Mallett & Yuksel).

## 2. Browser spectral renderers (WebGL / WebGPU)

| name | URL | what it does | spectral / RGB | licence | last activity | browser |
|---|---|---|---|---|---|---|
| Caustify | github.com/immineal/caustify (demo j4zz.eu/caustify) | WebGL2 dispersion path tracer: prism, gem, lens, Cornell box | spectral, 1 random wavelength per path, Cauchy IOR | MIT | 2026-09-01 (BlenderNation post 2026-09-13) | yes |
| spectral2d-webgpu | github.com/Bruffen/spectral2d-webgpu | 2D spectral path tracer for caustics/dispersion; README TODOs list full spectrum and light colours as unfinished | spectral (partial) | MIT | 2025-07-12 | yes |
| luma.gl SpectralCausticsRenderer | luma.gl docs, experimental | WebGPU photon-caustics add-on, 6 wavelength bands, D65/XYZ; a lighting term, not a full renderer | spectral (6 bands) | MIT (repo LICENSE) | repo push 2026-10-10 | yes |
| Advanced-Jewelry-Renderer-Web | github.com/itlmy/Advanced-Jewelry-Renderer-Web | Three.js path-traced jewellery with "spectral dispersion" | not verified how spectral | MIT | 2026-03-18 | yes |
| DICHROIC | github.com/nathanaellbc/DICHROIC | spectral *film simulation* in WebGPU (not a scene renderer) | spectral (film) | GPL-3.0 | 2026-10-10 | yes |
| floralcraft | github.com/penguinawesome1/floralcraft | voxel sandbox; README says WGSL spectral path tracer | not verified | none stated | 2026-08-11 | yes |
| cybr-light-public | github.com/cybrdelic/cybr-light-public | native spectral renderer + WebGPU **RGB** path tracer | native spectral; browser part RGB | GPL-2.0 | 2026-10-09 | browser part RGB |
| strahl (ZHAW) | github.com/StuckiSimon/strahl | WebGPU OpenPBR path tracer | RGB (described as physically based; no spectral claim found) | MIT | 2025-12-01 | yes |
| three-gpu-pathtracer | github.com/gkjohnson/three-gpu-pathtracer | Three.js path tracer | RGB | MIT | 2026-10-08 | yes |
| "indicatrix-web" | – | gem rendering (named in the brief) | – | – | – | none found in 2 searches |

Plainly: **few exist.** I found no general-purpose 3D spectral path tracer in the browser that
renders coloured materials under arbitrary measured illuminants (3 web searches + 2 GitHub
searches). What exists is dispersion-focused (Caustify, the 2D tracer, luma.gl caustics) or
not verified.

## 3. Blender

| item | status | source |
|---|---|---|
| Spectral Cycles in official Blender | **not merged, confirmed.** The Blender 5.0 Cycles release notes contain no mention of spectral rendering | developer.blender.org/docs/release_notes/5.0/cycles/ |
| "Thoughts on making Cycles into a spectral renderer" devtalk thread | **active**: 2,016 posts, created 2018-09-21, last post 2026-10-10 (Discourse API) | devtalk.blender.org/t/2192 |
| Spectral Cycles branch features (4 wavelengths/ray, OSL unsupported, merge targeted at "4.x") | reported in thread posts. Current state and any merge timeline are **unconfirmed / rumoured** | same thread |
| Mitsuba Blender add-on | exists, active (push 2026-09-23), BSD-3-Clause. Whether it exposes Mitsuba's spectral variants: not verified | github.com/mitsuba-renderer/mitsuba-blender |

## 4. RGB → spectrum uplift tools

| name | URL | method | licence | web-ready table generator? |
|---|---|---|---|---|
| rgb2spec (Jakob & Hanika 2019) | github.com/mitsuba-renderer/rgb2spec | sigmoid-quadratic, LUT optimiser (C++) | BSD-3-Clause | no (native C++ tool); push 2026-09-16 |
| rgb2spec-rs | github.com/nbvdkamp/rgb2spec-rs | Rust port with CLI table generator | BSD-3-Clause | CLI only; push 2022-12-10 |
| colour-science `find_coefficients_Jakob2019` | github.com/colour-science/colour | per-colour J&H solver (Python); `colour.recovery` also has Smits, Meng et al. | BSD-3-Clause | no LUT/web generator found |
| Spectral primaries (Mallett & Yuksel 2019) | graphics.geometrian.com/research/spectral-primaries.html | linear combination of 3 basis spectra, no table needed | code: MIT (simple-spectral); data zip licence not stated | trivially web-usable (no table) |
| Fourier sRGB (Peters et al.) | in MomentsInGraphics/path_tracer `spectral` branch | moment/Fourier-based uplift | BSD-3-Clause (repo) | GLSL/native; not web |
| Jung et al. 2019 (fluorescent wide-gamut uplift) | cg.ivd.kit.edu/uplifting.php | uplift with fluorescence | not verified | not verified |
| Vectre's own J&H LUT generator | this repo (`src/phase2_scene.py`) | LM + continuation, 32³ linear-sRGB LUT | ours (repo private) | Python; WGSL lookup exists |

A JS/WASM J&H table generator: **none found in 2 searches** (plus one GitHub search).

## 5. Shared test scenes / reference images (RGB vs spectral)

| item | URL | what | licence |
|---|---|---|---|
| Peters, Spectral Rendering part 3 (2025-11-20) | momentsingraphics.de/SpectralRendering3Results.html | one balloon scene, RGB vs spectral under 8 illuminants (E, D65, LED, incandescent, CFL, metal halide, HPS, 500 nm); interactive figures; data archive zip | code BSD-3 (repo); data licence not stated |
| Cornell Box measured data | en-cg-web.coecis.cornell.edu/online/box/data.html | 7-band filtered photos of the physical box, reflectance + geometry | not verified |
| TH Köln spectral ground truth (EGSR 2018) | cg.web.th-koeln.de/brdf-gtd/ | 24 measured colour patches at 13 angles, for predictive rendering | "free for research" per page |
| Leeds fluorescent Cornell box (Mitsuba-based) | eprints.whiterose.ac.uk/id/eprint/238501 | fluorescence rendering validated against a physical box | data download not found |
| SFU colour constancy sets | www2.cs.sfu.ca/~colour/data/colour_constancy_test_images/ | real scenes incl. fluorescent surfaces, measured illuminant spectra | not verified |
| Blender devtalk ad-hoc scenes | devtalk thread | MacBeth chart, balloon tests, user-posted EXRs | not verified |

Plainly: **no shared, open test bench** with paired RGB/spectral renders and an independent
converged reference across non-D65 and narrow-band lights was found in 2 searches. Closest:
Peters' single-scene comparison.

## 6. Explainers

| item | URL | type |
|---|---|---|
| Brown CS123 Metamers demo | cs.brown.edu/courses/cs123/archive/2020/demos/metamers/ | interactive: draw spectra, compare RGB response. Basic; no rendering or lights |
| Moments in Graphics spectral series (2025) | momentsingraphics.de/SpectralRenderingOverview.html | technical blog with interactive image comparisons |
| LuxCore / Blender forum posts | forums.luxcorerender.org, devtalk | text explanations (e.g. red surface under green light goes black in RGB) |

Plain-language interactive page specifically about RGB colour drift under coloured or narrow-band
light: **none found in 2 searches.**

## 7. Communities (confirmed, with latest activity seen)

| place | latest activity seen |
|---|---|
| Blender devtalk spectral Cycles thread | 2026-10-10 (last post) |
| Mitsuba 3 GitHub Discussions | 2026-09-24 (latest discussion update) |
| colour-science GitHub Discussions | 2026-05-08 |
| BlenderNation (community news; Caustify post) | 2026-09-13 |
| LuxCoreRender forum spectral threads | threads seen date from ~2020; current activity not verified |
| r/GraphicsProgramming, Discord servers | not verified (Reddit fetch blocked; search does not index Discord) |

## Gaps (with evidence)

**(a) Shared open test bench, RGB vs spectral, non-D65 lights, with reference renders: open gap,
partly covered.** Peters (2025) compares RGB vs spectral under 8 measured lights in one scene,
with BSD-3 code and a data zip, but his reference is his own spectral render. I found no
independent converged ground truth, standard scene files or metric scripts. Measured datasets
(Cornell 7-band photos, TH Köln patches, SFU) are not RGB-vs-spectral renderer benches.

**(b) Plain-language interactive explainer: open gap.** The closest are a basic metamer drawing tool
(Brown CS123) and a technical blog with image sliders (Peters). Nothing found (2 searches) that
lets a non-specialist change the light and watch RGB drift.

**(c) Web-friendly uplift table generator under a permissive licence: partly covered.** Permissive
generators exist (rgb2spec BSD-3 C++, rgb2spec-rs BSD-3 Rust CLI, colour-science BSD-3 per-colour
solver), and Mallett–Yuksel needs no table. No JS/WASM generator was found (2 searches + GitHub
search). The gap is packaging, not science.

**(d) Measured spectral-vs-RGB cost on consumer GPUs, in the browser: open gap for the browser;
covered natively.** Peters reports native timings on an RTX 5070 Ti at 1080p: spectral overhead
≤ 0.3 ms, 2–36% depending on scene and path length. No browser/WebGPU measurement was found
(2 searches). Vectre's own harness exists, but so far it has only run on an Intel iGPU, and the
full benchmark has **not** been run.

## Recommended first releases (ranked)

1. **Open RGB-vs-spectral test bench.** Cornell scene JSON, measured CIE 224 CES materials, CIE
   D65/A/F-series + synthetic narrow-band lights, converged 1 nm CPU references, and verified ΔE00
   metric code. This fills gap (a), and Vectre already has most of it (tested CPU reference: furnace,
   analytic, NEE, full-spectrum checks). Release under CC BY-SA 4.0 because the CES and CIE data
   require it. Exclude Munsell (UEF data has no commercial licence).
2. **Interactive "why RGB drifts" explainer page** built on the existing WebGPU demo. Swap the light
   (D65 → F11 → 610 nm line) and see RGB vs hero-4λ vs reference side by side, with the honest Phase
   1.5/2 findings, including that tonemapping, not RGB, caused the "purity collapse". This fills gap (b),
   for which nothing comparable was found.
3. **Browser cost/accuracy benchmark (WebGPU timestamp queries) with a public results table.**
   This fills gap (d), which Peters covers natively but not in the browser. Ranked third because it
   needs runs on discrete GPUs first (current numbers: Intel iGPU only, full harness not yet run). A
   JS/WASM J&H LUT generator (gap c) would be a small add-on to 1 or 3 rather than its own release,
   since permissive native tools already exist.

Honesty note: Vectre's Phase 2 spectral method (hero-4λ, J&H uplift, light-aware pdf ∝ CMF·E) matches
known practice and is very close to Peters' 2025 tracer. The novel contribution, if any, would be
the open bench, the explainer and browser measurements, not the rendering method.
