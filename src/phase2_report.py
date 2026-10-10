"""Phase 2: tables and side-by-side images from the WebGPU harness output.

Inputs:  results/phase2/gpu/results.json and *_xyz.bin (written by src/webgpu/serve.py),
         results/phase2/ref_<scene>.npz (CPU reference).
Outputs: results/phase2/phase2_tables.md, results/figures/phase2_<scene>_compare.png,
         results/figures/phase2_error_vs_spp.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "cpu_reference"))

from colorimetry import delta_e_2000, xyz_to_lab  # noqa: E402
from render_reference import to_srgb8  # noqa: E402

GPU = ROOT / "results/phase2/gpu"
FIG = ROOT / "results/figures"
MODES = ["rgb", "hero4_jh", "hero4_measured"]
LABEL = {"rgb": "RGB", "hero4_jh": "hero-4λ + J&H uplift", "hero4_measured": "hero-4λ, measured spectra (validation)"}


def first_hit_materials(sc):
    """Material id of the primary-ray hit at each pixel centre (-1 = miss, -2 = light)."""
    from render_reference import load_scene
    from pt import intersect
    _, cam, Q, qmat, S, smat, LQ, *_ = load_scene("cornell_d65")
    res = sc["resolution"]
    out = np.full((res, res), -1, np.int64)
    for i in range(res):
        for j in range(res):
            px = (2.0 * (j + 0.5) / res - 1.0) * cam[9]
            py = (1.0 - 2.0 * (i + 0.5) / res) * cam[9]
            d = cam[3:6] + px * cam[6:9] + py * cam[10:13]
            d = d / np.linalg.norm(d)
            t, kind, idx = intersect(cam[0:3].copy(), d, Q, S, LQ)
            out[i, j] = qmat[idx] if kind == 0 else smat[idx] if kind == 1 else (-2 if kind == 2 else -1)
    return out


def main():
    res = json.loads((GPU / "results.json").read_text())
    rows = res["rows"]
    scene_js = json.loads((ROOT / "src/webgpu/data/scene.json").read_text())
    xyz2rgb, white = np.array(scene_js["xyz2rgb"]), torch.tensor(scene_js["white_xyz"], dtype=torch.float64)
    scenes = list(dict.fromkeys(r["scene"] for r in rows))
    spps = sorted(set(r["spp"] for r in rows))
    lines = [f"Adapter: {res['meta']['adapter']}; timestamp-query: {res['meta']['timestampQuery']}; "
             f"{res['meta']['resolution']}² px; max bounces {res['meta']['maxBounces']}; {res['meta']['timing_note']}.", ""]
    for s in scenes:
        lines.append(f"\n**{s}**: mean ΔE00 / RMSE vs CPU reference (non-emitter pixels)\n")
        lines.append("| mode | " + " | ".join(f"{p} spp" for p in spps) + " |")
        lines.append("|---|" + "---|" * len(spps))
        for m in MODES:
            rr = {r["spp"]: r for r in rows if r["scene"] == s and r["mode"] == m}
            if rr:
                lines.append(f"| {LABEL[m]} | " + " | ".join(f"{rr[p]['mean_dE00']:.2f} / {rr[p]['rmse']:.4f}" for p in spps) + " |")
    lines.append("\n**Cost**: GPU time in ms, median (min–max) over repeated identical renders "
                 "(timestamp queries, summed over dispatches); bound buffer memory\n")
    lines.append("| scene | mode | buffer bytes | " + " | ".join(f"{p} spp ms" for p in spps) + " | ms per spp (at max spp) |")
    lines.append("|---|---|---|" + "---|" * len(spps) + "---|")
    for s in scenes:
        for m in MODES:
            rr = {r["spp"]: r for r in rows if r["scene"] == s and r["mode"] == m}
            if rr:
                lines.append(f"| {s} | {LABEL[m]} | {rr[spps[0]]['buffer_bytes']:,} | " +
                             " | ".join(f"{rr[p]['gpu_ms']:.1f} ({rr[p]['gpu_ms_min']:.1f}–{rr[p]['gpu_ms_max']:.1f})" for p in spps) +
                             f" | {rr[spps[-1]]['gpu_ms_per_spp']:.2f} |")
    (ROOT / "results/phase2/phase2_tables.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

    # per first-hit material: where does each mode fail? (converged, max spp)
    mat_map = first_hit_materials(scene_js)
    names = [m["name"] for m in scene_js["materials"]]
    smax = max(spps)
    lines.append(f"\n**Mean ΔE00 by first-hit surface at {smax} spp** (bias-dominated; light/emitter excluded)\n")
    lines.append("| scene | mode | " + " | ".join(names) + " |")
    lines.append("|---|---|" + "---|" * len(names))
    for s in scenes:
        ref = np.load(ROOT / f"results/phase2/ref_{s}.npz")
        k, R = float(ref["exposure"]), ref["xyz"]
        H = R.shape[0]
        lab_ref = xyz_to_lab(torch.tensor(R * k).reshape(-1, 3), white)
        for m in MODES:
            f = GPU / f"{s}_{m}_{smax}spp_xyz.bin"
            if not f.exists():
                continue
            X = np.fromfile(f, "<f4").reshape(-1, 3).astype(np.float64)
            de = delta_e_2000(lab_ref, xyz_to_lab(torch.tensor(X * k), white)).numpy()
            cells = []
            for mi in range(len(names)):
                sel = (mat_map.ravel() == mi) & (ref["mask"].ravel() == 0)
                cells.append(f"{de[sel].mean():.2f}" if sel.any() else "–")
            lines.append(f"| {s} | {LABEL[m]} | " + " | ".join(cells) + " |")
    (ROOT / "results/phase2/phase2_tables.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[-3 * len(MODES) - 3:]))

    # error vs spp plot
    fig, axs = plt.subplots(1, len(scenes), figsize=(5 * len(scenes), 4), sharey=True)
    for ax, s in zip(np.atleast_1d(axs), scenes):
        for m, c in zip(MODES, ("k", "tab:red", "tab:blue")):
            rr = sorted((r for r in rows if r["scene"] == s and r["mode"] == m), key=lambda r: r["spp"])
            ax.plot([r["spp"] for r in rr], [r["mean_dE00"] for r in rr], "o-", color=c, label=LABEL[m])
        ax.set_xscale("log", base=2); ax.set_yscale("log"); ax.grid(alpha=.3, which="both")
        ax.set_title(s); ax.set_xlabel("samples per pixel")
    np.atleast_1d(axs)[0].set_ylabel("mean ΔE00 vs CPU reference"); np.atleast_1d(axs)[0].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / "phase2_error_vs_spp.png", dpi=130); plt.close(fig)

    # side-by-side images
    for s in scenes:
        ref = np.load(ROOT / f"results/phase2/ref_{s}.npz")
        k, R = float(ref["exposure"]), ref["xyz"]
        H = R.shape[0]
        for spp in (64, 1024):
            fig, axs = plt.subplots(2, 3, figsize=(13.5, 9))
            axs[0, 0].imshow(to_srgb8(R, k, xyz2rgb)); axs[0, 0].set_title(f"CPU reference ({int(ref['spp'])} spp, 1 nm truth)")
            lab_ref = xyz_to_lab(torch.tensor(R * k).reshape(-1, 3), white)
            for j, m in enumerate(("rgb", "hero4_jh"), start=1):
                f = GPU / f"{s}_{m}_{spp}spp_xyz.bin"
                X = np.fromfile(f, "<f4").reshape(H, H, 3).astype(np.float64)
                axs[0, j].imshow(to_srgb8(X, k, xyz2rgb))
                de = delta_e_2000(lab_ref, xyz_to_lab(torch.tensor(X * k).reshape(-1, 3), white)).reshape(H, H).numpy()
                de[ref["mask"] == 1] = 0
                axs[0, j].set_title(f"WebGPU {LABEL[m]}, {spp} spp")
                im = axs[1, j].imshow(de, vmin=0, vmax=10, cmap="magma")
                axs[1, j].set_title(f"ΔE00 vs reference (mean {de[ref['mask'] == 0].mean():.2f})")
            fm = GPU / f"{s}_hero4_measured_{spp}spp_xyz.bin"
            if fm.exists():
                Xm = np.fromfile(fm, "<f4").reshape(H, H, 3).astype(np.float64)
                axs[1, 0].imshow(to_srgb8(Xm, k, xyz2rgb)); axs[1, 0].set_title(f"WebGPU {LABEL['hero4_measured']}, {spp} spp", fontsize=9)
            for a in axs.flat:
                a.axis("off")
            fig.colorbar(im, ax=axs[1, 1:], shrink=0.8, label="ΔE00")
            fig.suptitle(f"{s}: display = max-RGB hue-preserving tonemap, same exposure for all")
            fig.savefig(FIG / f"phase2_{s}_compare_{spp}spp.png", dpi=110, bbox_inches="tight"); plt.close(fig)


if __name__ == "__main__":
    main()
