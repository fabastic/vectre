"""Task A: illuminant change and narrow-band light.

For each illuminant, the colour of light that has bounced n times
(radiance = E * R_0 * ... * R_n, n multiplications as in Phase 1) is
rendered by each method and compared with 1 nm ground truth.

Methods
  grid5_exact   exact product on the 5 nm grid (box-filtered spectra), integrated
                via 5nm->1nm interpolation. Isolates the 5 nm discretisation error.
  rgb           standard RGB rendering: albedo = linear sRGB of the reflectance
                under D65; light = linear sRGB of the illuminant's own XYZ;
                per-channel product; back to XYZ. Primaries IEC 61966-2-1, white
                = CIE D65 (1 nm). (The usual practice discussed by Meng et al. 2015.)
  quad4         fixed 450/505/560/615 nm (Phase 1 fit). Generalised to any light as
                XYZ = sum_i Q_i E(l_i) T(l_i), Q_i = W_i / E_D65(l_i).
  hero4_sppN    4 stratified wavelengths/sample on the 1 nm grid, pdf ~ xbar+ybar+zbar
                (light-agnostic, as a renderer sampling visible wavelengths), N samples.
  raw_tensor_K  linear PCA (Munsell raw basis) product tensor; colour = C_E @ (1,w)
  raw_dmr_K     linear PCA, decompress (clamped) - multiply - recompress
  log_add_K     log-PCA, weights added; decode exp at the end.

Metrics: CIEDE2000 with CIELAB relative to the D65 white (display as rendered,
no white balance). Primary = exposure-normalised (truth and estimate scaled so
true Y = 20); secondary = plain (light normalised so a white reflector has Y=100).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

from colorimetry import delta_e_2000, xyz_to_lab
from datasets import load_munsell
from multiplication import dmr_mul, product_tensor, tensor_mul
from pca import PCAModel, load_processed
from spectral1nm import ILLUMINANTS, WL1, Spectral1nm

ROOT = Path(__file__).resolve().parents[1]
BOUNCES = [0, 1, 3, 5]
KS = [4, 6, 8]
N_CHAINS = 20000
SPP = [16, 256]
SEED = 4321
Y_EXPOSE = 20.0
QUAD_WL = [450, 505, 560, 615]


def stats(x):
    x = x.flatten()
    return {"mean": x.mean().item(), "median": x.median().item(), "p95": torch.quantile(x, .95).item(),
            "max": x.max().item()}


def hero4(L1, M1, spp, gen):
    """Unbiased 4-wavelength estimate of XYZ = M1 @ L1 (L1: (N,401) radiance)."""
    pdf = M1.sum(0); pdf = pdf / pdf.sum(); cdf = torch.cumsum(pdf, 0)
    N = L1.shape[0]
    u = torch.rand(N, spp, 1, generator=gen, dtype=L1.dtype)
    u = torch.remainder(u + torch.arange(4, dtype=L1.dtype) / 4.0, 1.0).reshape(N, -1)
    idx = torch.searchsorted(cdf, u.contiguous()).clamp(max=L1.shape[1] - 1)
    vals = torch.gather(L1, 1, idx) / pdf[idx]
    return (vals[:, None, :] * M1[:, idx].permute(1, 0, 2)).mean(-1)


def load_test_spectra():
    X5, is_test, dataset, *_ = load_processed()
    mun = load_munsell()
    assert len(mun) == int((dataset == "munsell").sum())
    m_test = np.where(is_test[: len(mun)])[0]
    R1 = torch.tensor(np.stack([mun[i].refl[: WL1.size] for i in m_test]), dtype=torch.float64)
    assert np.allclose(mun[0].wl_nm[: WL1.size], WL1)
    return X5[torch.tensor(m_test)], R1


def run():
    gen = torch.Generator().manual_seed(SEED)
    sp = Spectral1nm()
    X5, R1 = load_test_spectra()
    M = X5.shape[0]
    raw = PCAModel.load(ROOT / "results/pca/pca_raw.pt")
    lg = PCAModel.load(ROOT / "results/pca/pca_log.pt")
    q = json.loads((ROOT / "results/multiplication.json").read_text())["config"]["quad4"]
    assert q["wavelengths_nm"] == QUAD_WL
    qW = torch.tensor(q["W"], dtype=torch.float64)              # (3,4), fitted for D65 reflectance colour
    qidx = [int(w - 380) for w in QUAD_WL]
    Q = qW / sp.E["D65"][qidx]                                  # light-independent quadrature weights

    rgbR = sp.rgb_of_reflectance(R1)                            # (M,3)
    enc = {K: (raw.encode(X5, K), lg.encode(X5, K)) for K in KS}

    chains = {}
    for n in BOUNCES:
        chains[("random", n)] = torch.stack([torch.randperm(M, generator=gen)[: n + 1] for _ in range(N_CHAINS)])
        chains[("self", n)] = torch.arange(M)[:, None].repeat(1, n + 1)

    res = {"config": {"bounces": BOUNCES, "Ks": KS, "n_chains": N_CHAINS, "spp": SPP, "seed": SEED,
                      "Y_expose": Y_EXPOSE, "quad4_wavelengths": QUAD_WL,
                      "light_rgb": {i: sp.rgb_of_light(i).tolist() for i in ILLUMINANTS}}}
    for illum in ILLUMINANTS:
        E = sp.E[illum]
        W5 = sp.W5(illum)
        rgbE = sp.rgb_of_light(illum)
        ri = res.setdefault(illum, {})
        for (ctype, n), idx in chains.items():
            T1 = R1[idx].prod(1)
            xyz_true = sp.xyz(T1, illum)
            lab_true = xyz_to_lab(xyz_true, sp.white)
            expo = Y_EXPOSE / xyz_true[:, 1:2]
            lab_true_e = xyz_to_lab(xyz_true * expo, sp.white)
            r = ri.setdefault(ctype, {})

            def put(meth, xyz):
                d = r.setdefault(meth, {})
                d[str(n)] = stats(delta_e_2000(lab_true, xyz_to_lab(xyz, sp.white)))
                d[f"{n}_expo"] = stats(delta_e_2000(lab_true_e, xyz_to_lab(xyz * expo, sp.white)))

            put("grid5_exact", X5[idx].prod(1) @ W5.T)
            put("rgb", 100.0 * (rgbE * rgbR[idx].prod(1)) @ sp.rgb2xyz.T)
            put("quad4", (E[qidx] * T1[:, qidx]) @ Q.T)
            for spp in SPP:
                put(f"hero4_spp{spp}", hero4(T1 * E, sp.M1, spp, gen))
            for K in KS:
                Wr, Wl = enc[K]
                T = product_tensor(raw, K)
                acc_t, acc_d = Wr[idx[:, 0]], Wr[idx[:, 0]]
                for j in range(1, n + 1):
                    acc_t = tensor_mul(T, acc_t, Wr[idx[:, j]])
                    acc_d = dmr_mul(raw, acc_d, Wr[idx[:, j]], clamp=True)
                put(f"raw_tensor_K{K}", raw.decode_t(acc_t) @ W5.T)        # linear => = C_E @ (1,w)
                put(f"raw_dmr_K{K}", raw.decode(acc_d) @ W5.T)
                t = (n + 1) * lg.mean + Wl[idx].sum(1) @ lg.basis(K).T
                put(f"log_add_K{K}", torch.exp(t).clamp(0, 1) @ W5.T)
        print("done", illum)
    res["tonemap"] = tonemap_test(sp, X5, R1, raw, lg, Q, qidx, rgbR, chains)
    (ROOT / "results/illuminants.json").write_text(json.dumps(res, indent=1))
    return res


def tonemap_test(sp, X5, R1, raw, lg, Q, qidx, rgbR, chains):
    """Intensity sweep through a stated tonemapper.

    Display pipeline (identical for truth and every method):
      XYZ -> linear sRGB (D65) -> scale by intensity s -> clip negatives to 0
      -> per-channel Reinhard x/(1+x) -> back to XYZ (display white Y=100) -> CIELAB(D65).
    1x = a white reflector under the light has Y = 1 in scene-linear units
    (i.e. XYZ/100). We report dE00 of each method's display colour vs the
    truth's display colour, and the mean chroma C*ab, to test whether RGB
    loses colour purity relative to spectral truth at high intensity.
    """
    out = {}
    K = 6
    for illum in ILLUMINANTS:
        E, W5, rgbE = sp.E[illum], sp.W5(illum), sp.rgb_of_light(illum)
        for ctype, n in (("random", 0), ("self", 3)):
            idx = chains[(ctype, n)][:5000]
            T1 = R1[idx].prod(1)
            xyz = {"truth": sp.xyz(T1, illum),
                   "rgb": 100.0 * (rgbE * rgbR[idx].prod(1)) @ sp.rgb2xyz.T,
                   "quad4": (E[qidx] * T1[:, qidx]) @ Q.T,
                   f"log_add_K{K}": torch.exp((n + 1) * lg.mean + lg.encode(X5, K)[idx].sum(1)
                                              @ lg.basis(K).T).clamp(0, 1) @ W5.T}
            for s in (1, 10, 100):
                disp = {}
                for m, v in xyz.items():
                    rgb = (v / 100.0) @ sp.xyz2rgb.T * s
                    rgb = rgb.clamp(min=0)
                    tm = rgb / (1 + rgb)
                    disp[m] = xyz_to_lab(100.0 * tm @ sp.rgb2xyz.T, sp.white)
                lin_true = xyz_to_lab(xyz["truth"] * s, sp.white)    # untonemapped, for reference chroma
                key = f"{illum}|{ctype}_n{n}|{s}x"
                out[key] = {"chroma_truth_scene_linear": torch.hypot(lin_true[:, 1], lin_true[:, 2]).mean().item()}
                for m, lab in disp.items():
                    out[key][f"chroma_{m}"] = torch.hypot(lab[:, 1], lab[:, 2]).mean().item()
                    if m != "truth":
                        out[key][f"dE_{m}"] = stats(delta_e_2000(disp["truth"], lab))
    return out


def report(res):
    lines = []
    meths = ["grid5_exact", "rgb", "quad4", "hero4_spp16", "hero4_spp256"] + \
            [f"{m}_K{K}" for m in ("raw_tensor", "raw_dmr", "log_add") for K in KS]
    for illum in ILLUMINANTS:
        for ctype in ("random", "self"):
            r = res[illum][ctype]
            lines.append(f"\n#### {illum}, {ctype} chains: mean dE00, exposure-normalised (plain in brackets)\n")
            lines.append("| method | " + " | ".join(f"n={n}" for n in BOUNCES) + " |")
            lines.append("|---|" + "---|" * len(BOUNCES))
            for m in meths:
                lines.append(f"| {m} | " + " | ".join(
                    f"{r[m][f'{n}_expo']['mean']:.2f} ({r[m][str(n)]['mean']:.2f})" for n in BOUNCES) + " |")
    lines.append("\n#### Tonemap sweep (per-channel Reinhard on clipped linear sRGB); dE00 vs tonemapped truth, mean chroma C*ab\n")
    lines.append("| case | C* truth (scene) | C* truth (display) | C* rgb | dE rgb | C* quad4 | dE quad4 | C* log6 | dE log6 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for key, v in res["tonemap"].items():
        lines.append(f"| {key.replace('|', ', ')} | {v['chroma_truth_scene_linear']:.1f} | {v['chroma_truth']:.1f} | {v['chroma_rgb']:.1f} | "
                     f"{v['dE_rgb']['mean']:.2f} | {v['chroma_quad4']:.1f} | {v['dE_quad4']['mean']:.2f} | "
                     f"{v['chroma_log_add_K6']:.1f} | {v['dE_log_add_K6']['mean']:.2f} |")
    txt = "\n".join(lines)
    (ROOT / "results/illuminants_tables.md").write_text(txt, encoding="utf-8")
    print(txt)


def plot(res):
    figdir = ROOT / "results/figures"
    style = {"grid5_exact": ("tab:gray", ":"), "rgb": ("k", "-"), "quad4": ("tab:brown", "-"),
             "hero4_spp16": ("tab:pink", ":"), "hero4_spp256": ("tab:pink", "--"),
             "raw_tensor_K6": ("tab:orange", "-"), "raw_dmr_K6": ("tab:blue", "-"),
             "log_add_K4": ("tab:red", ":"), "log_add_K6": ("tab:red", "-"), "log_add_K8": ("tab:red", "--")}
    for ctype in ("random", "self"):
        fig, axs = plt.subplots(2, 3, figsize=(15, 8), sharey=True)
        for ax, illum in zip(axs.flat, ILLUMINANTS):
            r = res[illum][ctype]
            for m, (c, ls) in style.items():
                ax.plot(BOUNCES, [r[m][f"{n}_expo"]["mean"] for n in BOUNCES], ls, color=c, marker="o", ms=3, label=m)
            ax.set_title(illum); ax.set_yscale("log"); ax.set_ylim(0.02, 300)
            ax.axhline(1, color="k", lw=.6, ls=":"); ax.grid(alpha=.3, which="both")
            ax.set_xlabel("bounces n")
        axs[0, 0].set_ylabel("mean dE00 (exposure-normalised)"); axs[1, 0].set_ylabel("mean dE00 (exposure-normalised)")
        axs[0, -1].legend(fontsize=7, loc="upper left", bbox_to_anchor=(1.01, 1))
        fig.suptitle(f"Error vs bounces per illuminant ({ctype} chains, held-out Munsell, 1 nm truth)")
        fig.tight_layout(); fig.savefig(figdir / f"illuminants_error_vs_bounces_{ctype}.png", dpi=140); plt.close(fig)


if __name__ == "__main__":
    t0 = time.time()
    res = run(); report(res); plot(res)
    print(f"elapsed {time.time()-t0:.1f}s")
