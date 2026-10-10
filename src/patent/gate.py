"""Patent-track feasibility gate (PREREG.md): oracle vs hero-4λ on the CPU reference renderer.

All three methods use the SAME integrator, path sampling and J&H-uplifted material spectra
(the spectra the GPU's hero-4λ mode actually renders with, via the same 32³ LUT):
  hero4  : 4 stratified wavelengths per camera sample, light-aware pdf (the baseline, CPU emulation)
  hero8  : 8 stratified wavelengths per camera sample (candidate (c) data point)
  oracle : all 401 wavelengths carried exactly per path (zero wavelength-sampling noise;
           lower bound for any method that only changes the spectral estimator)
Metric: Phase 2 metric vs the converged 8192-spp references (mean CIEDE2000; exposure from the
reference; emitter and black background pixels excluded). 5 seeds per condition.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "cpu_reference"))

from colorimetry import delta_e_2000, xyz_to_lab  # noqa: E402
from phase2_scene import jh_eval_1nm, lut_lookup  # noqa: E402
from pt import light_pdf, render  # noqa: E402
from render_reference import load_scene  # noqa: E402

SCENES = ("cornell_d65", "cornell_f11", "cornell_nb610")
SPPS = (1, 4)
SEEDS = (101, 202, 303, 404, 505)
METHODS = {"hero4": (4, False), "hero8": (8, False), "oracle": (401, True)}


def jh_material_spectra(sc) -> np.ndarray:
    raw = np.fromfile(ROOT / "src/webgpu/data/jh_lut.bin", "<f4").reshape(-1, 4)
    coeffs = torch.tensor(raw[:, :3].astype(np.float64))
    rgb = torch.tensor([m["rgb"] for m in sc["materials"]], dtype=torch.float64).float().double()  # GPU uses f32
    return jh_eval_1nm(lut_lookup(coeffs, rgb)).numpy()


def score(xyz, ref, excl, k, white):
    m = ~excl.ravel()
    a = xyz_to_lab(torch.tensor(ref.reshape(-1, 3)[m] * k), white)
    b = xyz_to_lab(torch.tensor(xyz.reshape(-1, 3)[m] * k), white)
    return delta_e_2000(a, b).mean().item()


def main():
    out = {"seeds": SEEDS, "rows": []}
    t_all = time.time()
    for scene in SCENES:
        sc, cam, Q, qmat, S, smat, LQ, _refl_measured, Le, cmf = load_scene(scene)
        refl = jh_material_spectra(sc)
        cdf, pdf = light_pdf(cmf, Le)
        rz = np.load(ROOT / f"results/phase2/ref_{scene}.npz")
        ref, k = rz["xyz"], float(rz["exposure"])
        excl = (rz["mask"] == 1) | (ref.sum(-1) == 0)
        white = torch.tensor(sc["white_xyz"], dtype=torch.float64)
        res = sc["resolution"]
        for spp in SPPS:
            for name, (nw, full) in METHODS.items():
                des, secs = [], []
                for seed in SEEDS:
                    t0 = time.time()
                    A, B, _ = render(res, res, spp, seed, cam, Q, qmat, S, smat, LQ, refl, Le, cmf, cdf, pdf,
                                     nw, full, True, sc["max_bounces"], 0.0)
                    secs.append(time.time() - t0)
                    des.append(score((A + B) / spp, ref, excl, k, white))
                row = {"scene": scene, "spp": spp, "method": name, "dE_per_seed": des,
                       "dE_mean": float(np.mean(des)), "dE_std": float(np.std(des, ddof=1)),
                       "cpu_seconds_median": float(np.median(secs))}
                out["rows"].append(row)
                print(f"{scene} spp={spp} {name}: dE {row['dE_mean']:.3f} ± {row['dE_std']:.3f} "
                      f"(cpu {row['cpu_seconds_median']:.1f}s)", flush=True)
    out["total_seconds"] = time.time() - t_all
    (ROOT / "results/patent").mkdir(parents=True, exist_ok=True)
    (ROOT / "results/patent/gate.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
