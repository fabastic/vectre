"""Step 3: reconstruction accuracy vs K (3..10) for each PCA value space.

Metrics on the held-out TEST split (train reported too, for overfit check):
  * spectral RMSE in reflectance units (after inverse transform + [0,1] range)
  * CIEDE2000 under D65 / CIE 1931 2deg (mean, median, p95, max)
  * fraction of spectra whose *unclamped* decode left [0,1] (raw/sqrt/log only)
Outputs: results/reconstruction.json, results/figures/{variance_explained,recon_error_vs_k}.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

from colorimetry import ColorEval, load_colorimetry
from pca import SPACES, PCAModel, load_processed

ROOT = Path(__file__).resolve().parents[1]
KS = list(range(3, 11))


def stats(x: torch.Tensor) -> dict:
    x = x.flatten().double()
    return {"mean": x.mean().item(), "median": x.median().item(),
            "p95": torch.quantile(x, 0.95).item(), "max": x.max().item()}


def evaluate(model: PCAModel, X: torch.Tensor, K: int, ce: ColorEval) -> dict:
    w = model.encode(X, K)
    t = model.decode_t(w)
    from pca import inverse
    R = inverse(t, model.space)
    raw_out = None
    if model.space in ("raw", "sqrt"):
        raw_out = ((t < 0) | (t > 1)).any(1).float().mean().item()
    elif model.space == "log":
        raw_out = (t > 0).any(1).float().mean().item()
    rmse = torch.sqrt(((R - X) ** 2).mean(1))
    de = ce.de_spec(X, R)
    return {"rmse": stats(rmse), "de2000": stats(de), "frac_out_of_range_before_clamp": raw_out}


def main():
    X, is_test, dataset, *_ = load_processed()
    test = torch.tensor(is_test)
    ce = ColorEval(load_colorimetry())
    results = {}
    for space in SPACES:
        m = PCAModel.load(ROOT / "results" / "pca" / f"pca_{space}.pt")
        results[space] = {}
        for K in KS:
            results[space][K] = {"test": evaluate(m, X[test], K, ce), "train": evaluate(m, X[~test], K, ce)}
        # per-dataset test breakdown at all K (only meaningful once ECOSTRESS is present)
        for ds in np.unique(dataset):
            sel = torch.tensor((dataset == ds) & is_test)
            if sel.sum() > 0:
                results[space][f"test_{ds}"] = {K: evaluate(m, X[sel], K, ce)["de2000"] for K in KS}
    (ROOT / "results" / "reconstruction.json").write_text(json.dumps(results, indent=2))

    # ---- table to stdout (markdown) ----
    print("| space | K | RMSE mean | dE00 mean | dE00 median | dE00 p95 | dE00 max | out-of-range before clamp |")
    print("|---|---|---|---|---|---|---|---|")
    for space in SPACES:
        for K in KS:
            r = results[space][K]["test"]
            oor = r["frac_out_of_range_before_clamp"]
            print(f"| {space} | {K} | {r['rmse']['mean']:.4f} | {r['de2000']['mean']:.3f} | "
                  f"{r['de2000']['median']:.3f} | {r['de2000']['p95']:.3f} | {r['de2000']['max']:.3f} | "
                  f"{'n/a' if oor is None else f'{100*oor:.1f}%'} |")
    print("\ntrain-vs-test dE00 mean (raw):",
          {K: (round(results['raw'][K]['train']['de2000']['mean'], 3), round(results['raw'][K]['test']['de2000']['mean'], 3)) for K in KS})

    # ---- plots ----
    figdir = ROOT / "results" / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4))
    for space in SPACES:
        m = PCAModel.load(ROOT / "results" / "pca" / f"pca_{space}.pt")
        cum = torch.cumsum(m.explained_var_ratio, 0).numpy()[:10]
        ax.plot(range(1, 11), 1 - cum, "o-", label=space)
    ax.set_yscale("log"); ax.set_xlabel("K (number of components)")
    ax.set_ylabel("unexplained variance fraction (1 - cumulative)")
    ax.set_title("PCA variance (train split, in each value space)")
    ax.grid(alpha=.3, which="both"); ax.legend()
    fig.tight_layout(); fig.savefig(figdir / "variance_explained.png", dpi=150); plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    for space in SPACES:
        axs[0].plot(KS, [results[space][K]["test"]["rmse"]["mean"] for K in KS], "o-", label=space)
        axs[1].plot(KS, [results[space][K]["test"]["de2000"]["mean"] for K in KS], "o-", label=f"{space} mean")
        axs[1].plot(KS, [results[space][K]["test"]["de2000"]["p95"] for K in KS], "x--", alpha=.6,
                    color=axs[1].lines[-1].get_color(), label=f"{space} p95")
    axs[0].set_ylabel("spectral RMSE (reflectance)"); axs[1].set_ylabel("CIEDE2000 (D65, 2°)")
    for a in axs:
        a.set_xlabel("K"); a.set_yscale("log"); a.grid(alpha=.3, which="both")
    axs[1].axhline(1.0, color="k", lw=.8, ls=":")
    axs[0].legend(); axs[1].legend(fontsize=7, ncol=2)
    fig.suptitle("Reconstruction error vs K (held-out test split)")
    fig.tight_layout(); fig.savefig(figdir / "recon_error_vs_k.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
