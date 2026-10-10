"""Phase 2 Task 0: does any RGB-specific purity loss survive once the tonemapper is controlled for?

Same scenes as Phase 1.5's tonemap sweep (held-out Munsell, 1 nm truth, lights D65 /
NB610 / NEONLIKE, single surfaces n=0 and self-products n=3, intensity 1x/10x/100x where
1x = white reflector at scene-linear Y=1). For each tonemapper, both the spectral truth
and the RGB render go through the identical display pipeline:
    XYZ -> linear sRGB (D65) -> x s -> tonemap -> display-linear sRGB -> XYZ -> CIELAB(D65)
Reported: mean display chroma C*ab (truth vs RGB), mean |hue shift| of each relative to
the SCENE-LINEAR truth hue (only samples with scene chroma > 10), and mean dE00 RGB vs truth.
"""
from __future__ import annotations

import json
from pathlib import Path

import torch

from colorimetry import delta_e_2000, xyz_to_lab
from eval_illuminants import load_test_spectra
from spectral1nm import Spectral1nm
from tonemap import TONEMAPS

ROOT = Path(__file__).resolve().parents[1]


def hue_deg(lab):
    return torch.rad2deg(torch.atan2(lab[..., 2], lab[..., 1]))


def hdiff(a, b):
    return ((a - b + 180) % 360 - 180).abs()


def main():
    sp = Spectral1nm()
    X5, R1 = load_test_spectra()
    Ycoef = sp.rgb2xyz[1]
    rgbR = sp.rgb_of_reflectance(R1)
    g = torch.Generator().manual_seed(11)
    out, lines = {}, []
    lines.append("| light | chain | s | tonemap | C* truth | C* RGB | RGB chroma ratio | |Δh| truth (°) | |Δh| RGB (°) | ΔE00 RGB vs truth |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for illum in ("D65", "NB610", "NEONLIKE"):
        rgbE = sp.rgb_of_light(illum)
        for ctype, n in (("single", 0), ("self", 3)):
            idx = (torch.randint(0, R1.shape[0], (R1.shape[0], 1), generator=g) if ctype == "single"
                   else torch.arange(R1.shape[0])[:, None]).repeat(1, n + 1)
            xyz_t = sp.xyz(R1[idx].prod(1), illum)
            xyz_r = 100.0 * (rgbE * rgbR[idx].prod(1)) @ sp.rgb2xyz.T
            lab_scene = xyz_to_lab(xyz_t, sp.white)
            chroma_ok = torch.hypot(lab_scene[:, 1], lab_scene[:, 2]) > 10
            for s in (1, 10, 100):
                for tm_name, tm in TONEMAPS.items():
                    disp = {}
                    for k, v in (("truth", xyz_t), ("rgb", xyz_r)):
                        lin = (v / 100.0) @ sp.xyz2rgb.T * s
                        disp[k] = xyz_to_lab(100.0 * tm(lin, Ycoef) @ sp.rgb2xyz.T, sp.white)
                    C = {k: torch.hypot(v[:, 1], v[:, 2]) for k, v in disp.items()}
                    dh = {k: hdiff(hue_deg(v), hue_deg(lab_scene))[chroma_ok].mean().item() for k, v in disp.items()}
                    de = delta_e_2000(disp["truth"], disp["rgb"]).mean().item()
                    rec = {"C_truth": C["truth"].mean().item(), "C_rgb": C["rgb"].mean().item(),
                           "dh_truth": dh["truth"], "dh_rgb": dh["rgb"], "dE_rgb": de}
                    out[f"{illum}/{ctype}/{s}x/{tm_name}"] = rec
                    lines.append(f"| {illum} | {ctype} n={n} | {s}x | {tm_name} | {rec['C_truth']:.1f} | {rec['C_rgb']:.1f} | "
                                 f"{rec['C_rgb']/rec['C_truth']:.2f} | {rec['dh_truth']:.1f} | {rec['dh_rgb']:.1f} | {de:.2f} |")
    (ROOT / "results/tonemap_check.json").write_text(json.dumps(out, indent=1))
    (ROOT / "results/tonemap_check_table.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
