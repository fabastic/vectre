"""Steps 4 & 5: multi-bounce products in compressed space, and baselines.

Definitions (stated assumptions, see LAB_NOTEBOOK.md):
  * "n bounces" = n successive per-wavelength multiplications, i.e. the product
    of n+1 reflectance spectra; n=0 is plain reconstruction.
  * Ground truth: per-wavelength product of the ORIGINAL (uncompressed) test
    spectra, rendered to CIELAB under D65 / 2deg on the 81-sample grid.
  * Chain types:
      random : n+1 distinct test spectra, drawn uniformly (N_CHAINS chains)
      self   : one test spectrum multiplied by itself (s^(n+1)); a proxy for
               inter-reflection inside a single coloured material, where
               spectral products are most saturating.
Methods (per K):
  recon_product : decode every input once, multiply at full resolution
                  (lower bound for any method that starts from K weights)
  raw_dmr       : raw PCA, decompress (clamped to [0,1]) - multiply - recompress
  raw_tensor    : raw PCA, K x (K+1) x (K+1) product tensor; final colour via
                  the 3 x (K+1) linear colour matrix (no spectral decode, no clamp)
  sqrt_tensor   : same tensor construction in sqrt space; final decode squares
  log_add       : log-space PCA, weights add exactly; final decode exp + clamp
Baselines (independent of K):
  rgb           : linear sRGB (D65 white -> 1,1,1), per-channel product, NO clamp
  rgb_clamped   : same, inputs clamped to [0,1] as an 8-bit/sRGB texture would be
  quad4         : 4 fixed wavelengths + fitted 3x4 weights (deterministic, biased)
  hero4_sppN    : 4 stratified wavelengths per sample, importance-sampled by
                  (xbar+ybar+zbar)*D65, averaged over N samples (unbiased, noisy)
"""
from __future__ import annotations

import itertools
import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

from colorimetry import ColorEval, load_colorimetry, xyz_to_lab, delta_e_2000
from multiplication import color_matrix, dmr_mul, product_tensor, tensor_mul
from pca import PCAModel, load_processed

ROOT = Path(__file__).resolve().parents[1]
KS = list(range(3, 11))
BOUNCES = [0, 1, 2, 3, 5]
N_CHAINS = 20000
SPP = [1, 16, 256]
SEED = 1234


Y_EXPOSE = 20.0   # exposure-normalised metric: scale so the TRUE product has Y = 20 (L* ~ 52)


def stats(x: torch.Tensor) -> dict:
    x = x.flatten().double()
    return {"mean": x.mean().item(), "median": x.median().item(),
            "p95": torch.quantile(x, 0.95).item(), "max": x.max().item()}


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

def fit_quad4(X_fit: torch.Tensor, M: torch.Tensor):
    """Exhaustive search over all C(81,4) wavelength 4-tuples on the grid.

    For each tuple, 3x4 weights W are the weighted least-squares fit of
    XYZ ~= W r(l1..l4) on X_fit; row weight 1/(Y+1) (~ relative error, so dark
    multi-bounce colours are not ignored). Returns (indices, W, rel_rms).
    """
    xyz = X_fit @ M.T                                   # (N, 3)
    wgt = 1.0 / (xyz[:, 1:2] + 1.0)
    R = X_fit * wgt
    Yw = xyz * wgt
    G = R.T @ R                                         # (81, 81)
    Bm = R.T @ Yw                                       # (81, 3)
    yy = (Yw**2).sum()
    best = (None, None, float("inf"))
    combos = torch.tensor(list(itertools.combinations(range(X_fit.shape[1]), 4)))
    for chunk in combos.split(200_000):
        Gs = G[chunk[:, :, None], chunk[:, None, :]]    # (C, 4, 4)
        bs = Bm[chunk]                                  # (C, 4, 3)
        sol = torch.linalg.solve(Gs + 1e-12 * torch.eye(4, dtype=G.dtype), bs)
        sse = yy - (bs * sol).sum((1, 2))
        i = int(torch.argmin(sse))
        if sse[i] < best[2]:
            best = (chunk[i], sol[i].T, sse[i].item())
    return best[0], best[1], (best[2] / yy.item()) ** 0.5


def hero4_estimate(P: torch.Tensor, M: torch.Tensor, spp: int, gen: torch.Generator) -> torch.Tensor:
    """Unbiased estimate of XYZ = M @ P using 4 stratified wavelengths per sample.

    pdf over the 81 grid samples is proportional to sum of rows of M (i.e.
    (xbar+ybar+zbar)*D65); wavelengths are drawn by inverse CDF at
    u, u+1/4, u+2/4, u+3/4 (mod 1), as in PBRT-v4's SampledWavelengths.
    """
    pdf = M.sum(0)
    pdf = pdf / pdf.sum()
    cdf = torch.cumsum(pdf, 0)
    N = P.shape[0]
    u = torch.rand(N, spp, 1, generator=gen, dtype=P.dtype)
    u = torch.remainder(u + torch.arange(4, dtype=P.dtype) / 4.0, 1.0)      # (N, spp, 4)
    idx = torch.searchsorted(cdf, u.reshape(N, -1).contiguous()).clamp(max=P.shape[1] - 1)
    vals = torch.gather(P, 1, idx) / pdf[idx]                              # (N, spp*4)
    return (vals[:, None, :] * M[:, idx].permute(1, 0, 2)).mean(-1)          # (N, 3)


# ---------------------------------------------------------------------------

def run():
    torch.manual_seed(SEED)
    gen = torch.Generator().manual_seed(SEED)
    X, is_test, dataset, name, group = load_processed()
    test = torch.tensor(is_test)
    Xte, Xtr = X[test], X[~test]
    ce = ColorEval(load_colorimetry())
    M = ce.M
    models = {s: PCAModel.load(ROOT / "results" / "pca" / f"pca_{s}.pt") for s in ("raw", "sqrt", "log")}

    # Fit the 4-wavelength quadrature on TRAIN singles + train products (no test leakage).
    fit_set = [Xtr]
    for n in (1, 2, 3, 5):
        idx = torch.randint(0, Xtr.shape[0], (4000, n + 1), generator=gen)
        fit_set.append(Xtr[idx].prod(1))
    q_idx, q_W, q_rel = fit_quad4(torch.cat(fit_set), M)
    quad = {"wavelengths_nm": [float(ce.cm.wl[i]) for i in q_idx], "W": q_W.tolist(), "fit_rel_rms_xyz": q_rel}
    print("quad4 wavelengths:", quad["wavelengths_nm"], "rel rms:", round(q_rel, 4))

    # Least-squares-fitted product tensor (alternative to the Galerkin tensor).
    # Training pairs: left operand = encoding of a true TRAIN product of depth
    # 0..4, right = a single TRAIN spectrum; target = encoding of the true product.
    # Rows weighted by 1/(Y+1) as for quad4 so dark products are not ignored.
    T_fit = {}
    left = torch.cat([Xtr[torch.randint(0, Xtr.shape[0], (6000, d + 1), generator=gen)].prod(1) for d in range(5)])
    right = Xtr[torch.randint(0, Xtr.shape[0], (left.shape[0],), generator=gen)]
    tgt = left * right
    wrow = 1.0 / (ce.spec_to_xyz(tgt)[:, 1:2] + 1.0)
    for K in KS:
        raw = models["raw"]
        one = torch.ones(left.shape[0], 1, dtype=left.dtype)
        h1, h2 = torch.cat([one, raw.encode(left, K)], 1), torch.cat([one, raw.encode(right, K)], 1)
        F = (h1[:, :, None] * h2[:, None, :]).reshape(left.shape[0], -1)
        sol = torch.linalg.lstsq(F * wrow, raw.encode(tgt, K) * wrow).solution    # ((K+1)^2, K)
        T_fit[K] = sol.T.reshape(K, K + 1, K + 1)

    chains = {}
    for n in BOUNCES:
        # distinct spectra within a chain
        chains[("random", n)] = torch.stack([torch.randperm(Xte.shape[0], generator=gen)[: n + 1]
                                             for _ in range(N_CHAINS)])
        chains[("self", n)] = torch.arange(Xte.shape[0])[:, None].repeat(1, n + 1)

    res = {"config": {"n_chains_random": N_CHAINS, "n_self": int(Xte.shape[0]), "bounces": BOUNCES,
                      "seed": SEED, "quad4": quad, "n_test_spectra": int(Xte.shape[0])}}
    sanity = {}
    for (ctype, n), idx in chains.items():
        P = Xte[idx].prod(1)                       # ground-truth product spectra
        xyz_true = ce.spec_to_xyz(P)
        lab_true = xyz_to_lab(xyz_true, ce.white)
        expo = (Y_EXPOSE / xyz_true[:, 1:2])       # per-chain exposure, applied to truth AND estimate
        lab_true_e = xyz_to_lab(xyz_true * expo, ce.white)
        r = res.setdefault(ctype, {})

        def put(meth, key, xyz):
            d = r.setdefault(meth, {}).setdefault(str(key), {})
            d[str(n)] = stats(delta_e_2000(lab_true, xyz_to_lab(xyz, ce.white)))
            d[f"{n}_expo"] = stats(delta_e_2000(lab_true_e, xyz_to_lab(xyz * expo, ce.white)))

        # ---- baselines ----
        rgb_in = ce.spec_to_rgb(Xte)               # (M, 3)
        put("rgb", "na", 100.0 * rgb_in[idx].prod(1) @ ce.rgb2xyz.T)
        put("rgb_clamped", "na", 100.0 * rgb_in.clamp(0, 1)[idx].prod(1) @ ce.rgb2xyz.T)
        put("quad4", "na", P[:, q_idx] @ q_W.T)
        for spp in SPP:
            put(f"hero4_spp{spp}", "na", hero4_estimate(P, M, spp, gen))

        # ---- compressed-space methods ----
        for K in KS:
            # recon_product: decode inputs once (raw PCA), exact products
            raw = models["raw"]
            Wr = raw.encode(Xte, K)
            put("recon_product", K, ce.spec_to_xyz(raw.decode(Wr)[idx].prod(1)))
            put("raw_floor", K, ce.spec_to_xyz(raw.decode(raw.encode(P, K))))

            T = product_tensor(raw, K)
            C = color_matrix(raw, K, M)
            acc_t, acc_d, acc_nc, acc_f = (Wr[idx[:, 0]],) * 4
            for j in range(1, n + 1):
                wj = Wr[idx[:, j]]
                acc_t = tensor_mul(T, acc_t, wj)
                acc_f = tensor_mul(T_fit[K], acc_f, wj)
                acc_d = dmr_mul(raw, acc_d, wj, clamp=True)
                acc_nc = dmr_mul(raw, acc_nc, wj, clamp=False)
            if n > 0:
                sanity[f"{ctype}_K{K}_n{n}_max|tensor-dmr_noclamp|"] = (acc_t - acc_nc).abs().max().item()
            one = torch.ones_like(acc_t[:, :1])
            xyz_t = torch.cat([one, acc_t], 1) @ C.T
            put("raw_tensor", K, xyz_t)
            put("raw_tensor_specdecode", K, ce.spec_to_xyz(raw.decode(acc_t)))
            put("raw_tensor_fit", K, torch.cat([one, acc_f], 1) @ C.T)
            put("raw_dmr", K, ce.spec_to_xyz(raw.decode(acc_d)))

            sq = models["sqrt"]
            Ws = sq.encode(Xte, K)
            Ts = product_tensor(sq, K)
            acc = Ws[idx[:, 0]]
            for j in range(1, n + 1):
                acc = tensor_mul(Ts, acc, Ws[idx[:, j]])
            put("sqrt_tensor", K, ce.spec_to_xyz(sq.decode(acc)))

            lg = models["log"]
            Wl = lg.encode(Xte, K)
            acc = Wl[idx].sum(1)
            t = (n + 1) * lg.mean + acc @ lg.basis(K).T
            put("log_add", K, ce.spec_to_xyz(torch.exp(t).clamp(0, 1)))
        print(f"done {ctype} n={n}")

    res["sanity"] = {"max_over_all_|tensor - dmr_noclamp|": max(sanity.values()),
                     "rgb_inputs_out_of_[0,1]": int(((ce.spec_to_rgb(Xte) < 0) | (ce.spec_to_rgb(Xte) > 1)).any(1).sum())}
    (ROOT / "results" / "multiplication.json").write_text(json.dumps(res, indent=2))
    return res


BASE = [("rgb", "k", "-"), ("quad4", "tab:brown", "-"),
        ("hero4_spp16", "tab:pink", ":"), ("hero4_spp256", "tab:pink", "--")]
METHS = [("raw_floor", "tab:gray", ":"), ("recon_product", "tab:gray", "--"), ("raw_dmr", "tab:blue", "-"),
         ("raw_tensor", "tab:orange", "-"), ("raw_tensor_fit", "tab:purple", "-"),
         ("sqrt_tensor", "tab:green", "-"), ("log_add", "tab:red", "-")]


def _key(n, expo):
    return f"{n}_expo" if expo else str(n)


def plot(res):
    figdir = ROOT / "results" / "figures"
    for expo in (True, False):
        tag = "expo" if expo else "abs"
        ylab = (f"mean CIEDE2000, exposure-normalised (true Y={Y_EXPOSE:g})" if expo
                else "mean CIEDE2000, absolute")
        for ctype in ("random", "self"):
            r = res[ctype]
            fig, axs = plt.subplots(1, 3, figsize=(15, 4.3), sharey=True)
            for ax, K in zip(axs, (4, 6, 8)):
                for m, c, ls in METHS:
                    ax.plot(BOUNCES, [r[m][str(K)][_key(n, expo)]["mean"] for n in BOUNCES], "o" + ls, color=c, label=m)
                for m, c, ls in BASE:
                    ax.plot(BOUNCES, [r[m]["na"][_key(n, expo)]["mean"] for n in BOUNCES], ls, color=c, marker=".", label=m)
                ax.set_title(f"K = {K}"); ax.set_xlabel("bounces n (product of n+1 spectra)")
                ax.set_yscale("log"); ax.set_ylim(0.02, 300); ax.grid(alpha=.3, which="both"); ax.axhline(1, color="k", lw=.7, ls=":")
            axs[0].set_ylabel(ylab)
            axs[-1].legend(fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1))
            fig.suptitle(f"Error vs bounce count ({ctype} chains, held-out test spectra, {tag})")
            fig.tight_layout(); fig.savefig(figdir / f"error_vs_bounces_{ctype}_{tag}.png", dpi=150); plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(12, 4.3))
    for ax, ctype in zip(axs, ("random", "self")):
        r = res[ctype]
        for m, c, ls in METHS:
            ax.plot(KS, [r[m][str(K)]["3_expo"]["mean"] for K in KS], "o" + ls, color=c, label=m)
        for m, c, ls in BASE:
            ax.axhline(r[m]["na"]["3_expo"]["mean"], color=c, ls=ls, label=m)
        ax.set_yscale("log"); ax.set_xlabel("K"); ax.set_title(f"3 bounces, {ctype} chains (exposure-normalised)")
        ax.grid(alpha=.3, which="both")
    axs[0].set_ylabel("mean CIEDE2000"); axs[1].legend(fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1))
    fig.tight_layout(); fig.savefig(figdir / "error_vs_k_3bounces.png", dpi=150); plt.close(fig)


def table(res):
    lines = []
    for expo in (True, False):
        for ctype in ("random", "self"):
            r = res[ctype]
            metric = "exposure-normalised" if expo else "absolute"
            lines.append(f"\n### {ctype} chains — {metric} CIEDE2000, mean / p95\n")
            lines.append("| method | K | " + " | ".join(f"n={n}" for n in BOUNCES) + " |")
            lines.append("|---|---|" + "---|" * len(BOUNCES))
            for m in ("rgb", "rgb_clamped", "quad4", "hero4_spp1", "hero4_spp16", "hero4_spp256"):
                lines.append(f"| {m} | – | " + " | ".join(
                    f"{r[m]['na'][_key(n, expo)]['mean']:.2f} / {r[m]['na'][_key(n, expo)]['p95']:.2f}" for n in BOUNCES) + " |")
            for m in ("raw_floor", "recon_product", "raw_dmr", "raw_tensor", "raw_tensor_specdecode",
                      "raw_tensor_fit", "sqrt_tensor", "log_add"):
                for K in (3, 4, 6, 8, 10):
                    lines.append(f"| {m} | {K} | " + " | ".join(
                        f"{r[m][str(K)][_key(n, expo)]['mean']:.2f} / {r[m][str(K)][_key(n, expo)]['p95']:.2f}" for n in BOUNCES) + " |")
    txt = "\n".join(lines)
    (ROOT / "results" / "multiplication_tables.md").write_text(txt, encoding="utf-8")
    print(txt)
    print("\nsanity:", res["sanity"])


if __name__ == "__main__":
    t0 = time.time()
    res = run()
    plot(res)
    table(res)
    print(f"elapsed {time.time() - t0:.1f}s")
