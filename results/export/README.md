# Export layout (for WebGPU)

One package per K (3–10): `vectre_K{K}.bin` + `vectre_K{K}.json`.

* `.bin`: raw little-endian **float32**. Every array starts at a **256-byte-aligned**
  offset (WebGPU's default `minStorageBufferOffsetAlignment`), so you can upload the
  whole file as **one** `GPUBuffer` (usage `STORAGE | COPY_DST`) and bind each array
  with `{buffer, offset: offset_bytes, size: size_bytes}`. In WGSL, declare each array as
  `array<f32>`; avoid `array<vec3<f32>>`, which has 16-byte stride.
* `.json`: `arrays.{name}.offset_bytes / size_bytes / shape`, plus metadata and a
  full float64 copy of every value under `values`, for JS/CPU use and debugging.
* All arrays are C order (row-major, last index fastest). L = 81 wavelengths, 380..780 nm step 5.

| name | shape | meaning |
|---|---|---|
| `wavelengths_nm` | (L) | grid |
| `xyz_weights` | (3, L) | XYZ = W · spectrum (D65 × CIE 1931 2°, white Y = 100) |
| `raw_mean` | (L) | μ of reflectance PCA |
| `raw_basis` | (K, L) | component k is contiguous: `raw_basis[k*L + l]` |
| `raw_tensor` | (K, K+1, K+1) | product tensor; homogeneous input ŵ = (1, w₁..w_K) |
| `raw_color_xyz` | (3, K+1) | XYZ = C · ŵ (no spectral decode needed) |
| `raw_color_linear_srgb` | (3, K+1) | linear sRGB (D65 white → 1,1,1) = C · ŵ |
| `log_mean` | (L) | μ of log-reflectance PCA (eps = 1e-3) |
| `log_basis` | (K, L) | log-space components |

## Operations

```
// Linear (raw) PCA. ŵ = (1, w). The product of a and b:
w_out[k] = Σ_i Σ_j raw_tensor[(k*(K+1) + i)*(K+1) + j] * â[i] * b̂[j]     // K(K+1)^2 MACs
// Colour of a weight vector:
xyz[c]  = Σ_i raw_color_xyz[c*(K+1) + i] * ŵ[i]
// Spectral decode if needed: s[l] = clamp(raw_mean[l] + Σ_k w[k]*raw_basis[k*L+l], 0, 1)

// Log PCA. Carry (count n, weights w). Product = (n_a + n_b, w_a + w_b)      // K adds
// Decode: s[l] = min(1, exp(n*log_mean[l] + Σ_k w[k]*log_basis[k*L+l]));  xyz = xyz_weights · s
```

Read-back check (`src/export.py` → `verify_report.json`): float32 vs float64 reference,
max |Δ| ≤ 2.5e-6 for the tensor, ≤ 1.7e-5 for XYZ, ≤ 3.4e-7 for the log decode.

**Training data / terms:** these bases are fitted on Munsell (UEF) spectra, which
UEF says it will not licence for commercial use. Treat the exported files as
research-only until the licence position is clarified.

**Which to use?** See RESULTS.md: the raw tensor compounds error badly after one or
two bounces. The log basis is exact under multiplication, but it is not closed under addition.
