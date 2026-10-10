"""Task C: accumulation-cost micro-benchmark (CPU torch, float32). INDICATIVE ONLY.

Path-tracing-style loop, vectorised over N paths for B bounces. Every bounce:
  (1) fetch the hit material (random id; ids precomputed so RNG is not timed),
  (2) multiply path throughput by the material's reflectance,
  (3) accumulate one emission contribution (NEE-style: throughput * light) into
      the path's radiance; after the last bounce, radiance is scatter-added
      into a per-pixel XYZ image buffer.

Representations
  rgb        throughput 3 floats; albedo table (M,3); radiance accumulates in RGB.
  hero4_jh   4 wavelengths per path (fixed per path), throughput 4 floats.
             Reflectance at the 4 wavelengths evaluated from Jakob-Hanika
             coefficients (M,3) (the usual way to get spectra from RGB textures);
             radiance accumulates in 4-wavelength space; converted to XYZ once
             per path (4x3 MAC with CMF/pdf).
  logpca_K   throughput = K log-PCA weights (+ implicit bounce count n);
             material table (M,K); product = K adds. Accumulation needs the
             full 81-wide decode exp(n mu + B w) then a 3x81 dot (XYZ).
  hybrid4_K  throughput in log-PCA weights; at each emission event decode ONLY at
             the path's 4 wavelengths (4K MAC + 4 exp); radiance in 4-wavelength
             space as hero4. (Variant requested in the brief.)
Material values are random. Timing does not depend on their values.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
L = 81


def analytic(K: int | None, method: str) -> dict:
    """Per-path, per-bounce counts. flops count FMA as 2. exp counted separately."""
    if method == "rgb":
        return {"state_bytes": 4 * (3 + 3), "fetch_bytes": 4 * 3, "flops": 3 + 6, "exp": 0,
                "per_path_end_flops": 0}
    if method == "hero4_jh":
        # per lambda: Horner 2 FMA (4) + S(z)=0.5+0.5*z*rsqrt(1+z^2): fma,rsqrt,mul,fma (~6, rsqrt counted as 1)
        return {"state_bytes": 4 * (4 + 4) + 4, "fetch_bytes": 4 * 3 + 4 * 4,   # coeffs + light at 4 lambdas
                "flops": 4 * 10 + 4 + 8, "exp": 0, "per_path_end_flops": 4 * 3 * 2}
    if method == "logpca":
        return {"state_bytes": 4 * (K + 1 + 3), "fetch_bytes": 4 * K,
                "flops": K + L * (2 * K + 1) + L + 3 * L * 2 + 3, "exp": L,
                "constant_bytes_read": 4 * (L * (K + 1) + 3 * L), "per_path_end_flops": 0}
    if method == "hybrid4":
        return {"state_bytes": 4 * (K + 1 + 4) + 4, "fetch_bytes": 4 * K + 4 * 4,
                "flops": K + 4 * (2 * K + 1) + 8, "exp": 4,
                "constant_bytes_read": 4 * 4 * (K + 1), "per_path_end_flops": 4 * 3 * 2}
    raise ValueError(method)


def run_one(method, K, N, B, M, P, ids, pix, lam, reps=5):
    f32 = torch.float32
    g = torch.Generator().manual_seed(0)
    img = torch.zeros(P, 3, dtype=f32)
    W_E = torch.rand(3, L, generator=g, dtype=f32)                 # CMF * light (3,81)
    E81 = torch.rand(L, generator=g, dtype=f32)
    cmf_over_pdf = torch.rand(L, 3, generator=g, dtype=f32)
    times = []
    for _ in range(reps):
        img.zero_()
        t0 = time.perf_counter()
        if method == "rgb":
            alb = torch.rand(M, 3, generator=g, dtype=f32)
            E = torch.rand(3, generator=g, dtype=f32)
            thr = torch.ones(N, 3, dtype=f32); rad = torch.zeros(N, 3, dtype=f32)
            for b in range(B):
                thr *= alb[ids[b]]
                rad += thr * E
            img.index_add_(0, pix, rad)
        elif method == "hero4_jh":
            coef = torch.randn(M, 3, generator=g, dtype=f32)
            x = lam.to(f32) / (L - 1)
            El = E81[lam]
            thr = torch.ones(N, 4, dtype=f32); rad = torch.zeros(N, 4, dtype=f32)
            for b in range(B):
                c = coef[ids[b]]
                z = (c[:, 0:1] * x + c[:, 1:2]) * x + c[:, 2:3]
                thr *= 0.5 + 0.5 * z * torch.rsqrt(1 + z * z)
                rad += thr * El
            xyz = (rad[:, :, None] * cmf_over_pdf[lam]).sum(1)
            img.index_add_(0, pix, xyz)
        elif method == "logpca":
            tab = torch.randn(M, K, generator=g, dtype=f32) * 0.1
            mu = -torch.rand(L, generator=g, dtype=f32)
            Bm = torch.randn(K, L, generator=g, dtype=f32) * 0.1
            w = torch.zeros(N, K, dtype=f32); xyz = torch.zeros(N, 3, dtype=f32)
            for b in range(B):
                w += tab[ids[b]]
                s = torch.exp(torch.addmm(mu * (b + 1), w, Bm)).clamp_(max=1.0)   # (N,81)
                xyz += s @ W_E.T
            img.index_add_(0, pix, xyz)
        elif method == "hybrid4":
            tab = torch.randn(M, K, generator=g, dtype=f32) * 0.1
            mu = -torch.rand(L, generator=g, dtype=f32)
            Bm = torch.randn(K, L, generator=g, dtype=f32) * 0.1
            mu4, B4, El = mu[lam], Bm.T[lam], E81[lam]                   # (N,4), (N,4,K), (N,4)
            w = torch.zeros(N, K, dtype=f32); rad = torch.zeros(N, 4, dtype=f32)
            for b in range(B):
                w += tab[ids[b]]
                t = mu4 * (b + 1) + (B4 * w[:, None, :]).sum(-1)
                rad += torch.exp(t).clamp_(max=1.0) * El
            xyz = (rad[:, :, None] * cmf_over_pdf[lam]).sum(1)
            img.index_add_(0, pix, xyz)
        times.append(time.perf_counter() - t0)
    times.sort()
    return times[len(times) // 2]


def main():
    torch.manual_seed(0)
    N, B, M, P = 1 << 18, 5, 1024, 256 * 256
    g = torch.Generator().manual_seed(1)
    ids = torch.randint(0, M, (B, N), generator=g)
    pix = torch.arange(N) % P
    lam = torch.randint(0, L, (N, 1), generator=g)
    lam = (lam + torch.tensor([0, 20, 41, 61])) % L                     # stratified 4 per path
    cases = [("rgb", None), ("hero4_jh", None), ("logpca", 4), ("logpca", 6), ("hybrid4", 4), ("hybrid4", 6)]
    out = {"config": {"N_paths": N, "bounces": B, "materials": M, "pixels": P, "dtype": "float32",
                      "threads": torch.get_num_threads(), "torch": torch.__version__,
                      "note": "CPU-only, vectorised torch; indicative, not a GPU prediction"}, "results": {}}
    for m, K in cases:
        name = m if K is None else f"{m}_K{K}"
        t = run_one(m, K, N, B, M, P, ids, pix, lam)
        a = analytic(K, "logpca" if m == "logpca" else m)
        a["ns_per_path_bounce_cpu"] = 1e9 * t / (N * B)
        out["results"][name] = a
        print(name, a)
    (ROOT / "results/bench_accumulation.json").write_text(json.dumps(out, indent=1))
    lines = ["| method | path state (B) | fetch/bounce (B) | FLOPs/bounce | exp/bounce | CPU ns per path-bounce (indicative) |",
             "|---|---|---|---|---|---|"]
    for k, a in out["results"].items():
        lines.append(f"| {k} | {a['state_bytes']} | {a['fetch_bytes']} | {a['flops']} | {a['exp']} | {a['ns_per_path_bounce_cpu']:.1f} |")
    (ROOT / "results/bench_accumulation_table.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
