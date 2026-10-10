"""Task B: bases trained on shippable data vs the (research-only) Munsell basis.

Test set: the same 247 held-out Munsell test chips as Phase 1 (research use, for
evaluation only). Metrics follow Phase 1 exactly (5 nm grid, D65, CIE 1931 2deg):
  * reconstruction dE00 (raw and log spaces), K = 4, 6, 8
  * log-PCA products: exposure-normalised dE00, random chains, n = 1, 3, 5
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

from colorimetry import ColorEval, delta_e_2000, load_colorimetry, xyz_to_lab
from pca import PCAModel, fit_pca, forward, load_processed
from synthetic_spectra import generate_gp, generate_jh, load_cie99

ROOT = Path(__file__).resolve().parents[1]
KS = [4, 6, 8]
BOUNCES = [1, 3, 5]
N_SYN = 5000


def fit_weighted(parts: list[torch.Tensor], space: str, k_max: int = 20) -> PCAModel:
    """PCA where each source contributes equal total weight (row weight 1/N_source)."""
    T = torch.cat([forward(p, space) for p in parts])
    w = torch.cat([torch.full((p.shape[0],), 1.0 / p.shape[0], dtype=torch.float64) for p in parts])
    w = w / w.sum()
    mu = (w[:, None] * T).sum(0)
    U, S, Vh = torch.linalg.svd(torch.sqrt(w)[:, None] * (T - mu), full_matrices=False)
    V = Vh.T
    V = V * torch.sign(V[V.abs().argmax(0), torch.arange(V.shape[1])])
    var = S**2
    return PCAModel(space, mu, V[:, :k_max].contiguous(), var[:k_max], (var / var.sum())[:k_max])


def chain_error(model, Xte, K, ce, idx, n):
    P = Xte[idx].prod(1)
    xyz_t = ce.spec_to_xyz(P)
    expo = 20.0 / xyz_t[:, 1:2]
    W = model.encode(Xte, K)
    t = (n + 1) * model.mean + W[idx].sum(1) @ model.basis(K).T
    xyz_a = ce.spec_to_xyz(torch.exp(t).clamp(0, 1))
    return delta_e_2000(xyz_to_lab(xyz_t * expo, ce.white), xyz_to_lab(xyz_a * expo, ce.white)).mean().item()


def main():
    torch.manual_seed(0)
    ce = ColorEval(load_colorimetry())
    X, is_test, dataset, *_ = load_processed()
    test = torch.tensor(is_test)
    Xte, Xmun_tr = X[test], X[~test]

    jh, jh_de = generate_jh(N_SYN, seed=1)
    gp = generate_gp(N_SYN, seed=2)
    cie99 = load_cie99()
    # Overlap check: is any CIE 99 sample (nearly) a Munsell test chip?
    d = torch.cdist(cie99, Xte) / np.sqrt(81)
    overlap = {"min_rmse_cie99_to_munsell_test": d.min().item(),
               "n_cie99_with_rmse_below_0.005": int((d.min(1).values < 0.005).sum())}
    sources = {
        "munsell_train (research-only, reference)": Xmun_tr,
        "cie99": cie99,
        "synthetic_jh": jh,
        "synthetic_gp": gp,
        "synthetic_jh+gp (balanced)": [jh, gp],
        "cie99+jh+gp (balanced)": [cie99, jh, gp],
        "cie99+gp (balanced)": [cie99, gp],
    }
    g = torch.Generator().manual_seed(7)
    chains = {n: torch.stack([torch.randperm(Xte.shape[0], generator=g)[: n + 1] for _ in range(20000)])
              for n in BOUNCES}
    res = {"overlap": overlap,
           "jh_fit_dE76": {"mean": jh_de.mean().item(), "p95": torch.quantile(jh_de, .95).item(),
                           "frac_above_1": (jh_de > 1).float().mean().item()},
           "n_spectra": {k: int(v.shape[0]) if torch.is_tensor(v) else sum(int(p.shape[0]) for p in v)
                         for k, v in sources.items()}, "bases": {}}
    for name, Xs in sources.items():
        r = res["bases"][name] = {}
        for space in ("raw", "log"):
            m = fit_pca(Xs, space) if torch.is_tensor(Xs) else fit_weighted(Xs, space)
            for K in KS:
                R = m.decode(m.encode(Xte, K))
                de = ce.de_spec(Xte, R)
                r[f"{space}_K{K}_recon"] = {"mean": de.mean().item(), "p95": torch.quantile(de, .95).item()}
                if space == "log":
                    for n in BOUNCES:
                        r[f"log_K{K}_n{n}_expo"] = chain_error(m, Xte, K, ce, chains[n], n)
        print(name, {k: round(v["mean"] if isinstance(v, dict) else v, 3) for k, v in r.items()})
    (ROOT / "results/shippable_basis.json").write_text(json.dumps(res, indent=1))

    # table
    lines = ["| basis trained on | N | raw K4 | raw K6 | raw K8 | log K4 | log K6 | log K8 | log K6 n=1/3/5 (expo) | log K8 n=1/3/5 (expo) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in res["bases"].items():
        lines.append(f"| {name} | {res['n_spectra'][name]} | " + " | ".join(
            f"{r[f'{s}_K{K}_recon']['mean']:.2f}" for s in ("raw", "log") for K in KS) + " | " +
            " / ".join(f"{r[f'log_K6_n{n}_expo']:.2f}" for n in BOUNCES) + " | " +
            " / ".join(f"{r[f'log_K8_n{n}_expo']:.2f}" for n in BOUNCES) + " |")
    txt = "\n".join(lines)
    (ROOT / "results/shippable_basis_table.md").write_text(txt, encoding="utf-8")
    print(txt); print(res["overlap"], res["jh_fit_dE76"])

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for name, r in res["bases"].items():
        ax.plot(KS, [r[f"log_K{K}_recon"]["mean"] for K in KS], "o-", label=name)
    ax.set_yscale("log"); ax.set_xlabel("K"); ax.set_ylabel("mean dE00 on held-out Munsell (log-PCA recon)")
    ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7)
    ax.set_title("Basis trained on shippable data vs Munsell basis")
    fig.tight_layout(); fig.savefig(ROOT / "results/figures/shippable_basis_recon.png", dpi=140)


if __name__ == "__main__":
    main()
