"""Phase 2: shared scene definition for the CPU reference and the WebGPU renderers.

Cornell-box-like scene (all Lambertian):
  box [0,1]^3, open at z=0, camera at (0.5, 0.5, -1.0) looking +z;
  floor/ceiling/back white, left red, right green; emissive quad under the ceiling;
  3 spheres (blue, yellow, magenta).
Materials (ground truth) = MEASURED spectra from CIE 224:2017's 99 colour-evaluation
samples (CC BY-SA 4.0), chosen as the CES closest in CIELAB to classic target colours.
  * CPU reference uses the measured 1 nm spectra (truth).
  * WebGPU RGB mode uses each material's linear sRGB albedo under D65.
  * WebGPU spectral mode uses a Jakob-Hanika uplift of that SAME sRGB albedo, i.e. it
    does NOT see the measured spectrum (as with RGB-authored assets).
Lights (three scene variants): D65, NB610 (synthetic 610 nm Gaussian, FWHM 5 nm), F11 (CIE).
Units: XYZ = sum_lambda cmf(l) L(l) * 1 nm; every light is scaled so its luminance Y = 15.
Integrator contract (both renderers): <= MAX_BOUNCES scattering vertices, next-event
estimation to the light at every vertex, emission from BSDF-sampled hits counted only
for camera rays (depth 0), cosine-weighted sampling, no Russian roulette.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from spectral1nm import WL1, Spectral1nm, raw_illuminant
from synthetic_spectra import jh_sigmoid

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "webgpu" / "data"
CACHE = ROOT / "results" / "phase2"
MAX_BOUNCES = 5
LIGHT_Y = 15.0
RES = 512
LUT_RES = 32
SCENES = ("cornell_d65", "cornell_nb610", "cornell_f11")
LIGHT_OF = {"cornell_d65": "D65", "cornell_nb610": "NB610", "cornell_f11": "F11"}

# Target linear-sRGB colours used only to PICK measured CES samples.
TARGETS = {"white": (0.72, 0.71, 0.68), "red": (0.63, 0.065, 0.05), "green": (0.14, 0.45, 0.09),
           "blue": (0.06, 0.12, 0.45), "yellow": (0.70, 0.55, 0.05), "magenta": (0.45, 0.08, 0.35)}


def geometry():
    q = []   # (p0, u, v, n, material)  quads are axis-aligned rectangles p0 + a u + b v, a,b in [0,1]
    q.append(((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), "white"))      # floor
    q.append(((0, 1, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0), "white"))     # ceiling
    q.append(((0, 0, 1), (1, 0, 0), (0, 1, 0), (0, 0, -1), "white"))     # back
    q.append(((0, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0), "red"))        # left
    q.append(((1, 0, 0), (0, 1, 0), (0, 0, 1), (-1, 0, 0), "green"))     # right
    light = {"p0": (0.38, 0.998, 0.38), "u": (0.24, 0, 0), "v": (0, 0, 0.24), "n": (0, -1, 0)}
    spheres = [((0.28, 0.18, 0.62), 0.18, "blue"), ((0.70, 0.16, 0.40), 0.16, "yellow"),
               ((0.52, 0.10, 0.18), 0.10, "magenta")]
    cam = {"pos": (0.5, 0.5, -1.0), "tan_half_fov": 0.54}
    return q, light, spheres, cam


def select_materials(sp: Spectral1nm):
    tab = np.genfromtxt(ROOT / "data/raw/cie/CIE_srf_cfi_1nm.csv", delimiter=",")
    assert np.allclose(tab[:, 0], WL1)
    R = torch.tensor(np.clip(tab[:, 1:].T, 0, 1))                       # (99, 401)
    from colorimetry import xyz_to_lab, delta_e_2000
    lab = xyz_to_lab(sp.xyz(R, "D65"), sp.white)
    out, used = {}, set()
    for name, t in TARGETS.items():
        lab_t = xyz_to_lab(100.0 * torch.tensor(t, dtype=torch.float64) @ sp.rgb2xyz.T, sp.white)
        d = delta_e_2000(lab, lab_t.expand_as(lab)).clone()
        for u in used:
            d[u] = 1e9
        i = int(torch.argmin(d))
        used.add(i)
        out[name] = {"ces_index": i + 1, "spectrum": R[i], "rgb": sp.rgb_of_reflectance(R[i:i + 1])[0],
                     "dE_to_target": d[i].item()}
    return out


def light_spectrum(name: str) -> np.ndarray:
    e = raw_illuminant(name)
    cmf = Spectral1nm().cmf
    return e * LIGHT_Y / np.sum(e * cmf[:, 1])


# ---------------------------------------------------------------------------
# Jakob-Hanika uplift LUT (own implementation of the published method; the BSD-3
# reference code mitsuba-renderer/rgb2spec was NOT used). Grid over linear sRGB [0,1]^3.
# ---------------------------------------------------------------------------

def jh_eval_1nm(c: torch.Tensor) -> torch.Tensor:
    x = torch.tensor((WL1 - 380.0) / 400.0, dtype=c.dtype)
    return jh_sigmoid(c[..., 0:1] * x**2 + c[..., 1:2] * x + c[..., 2:3])


def fit_jh(rgb: torch.Tensor, sp: Spectral1nm, iters=150, init=None):
    """LM fit of JH coefficients so the 1 nm spectrum's CIELAB (D65) matches rgb's. Returns (c, dE76)."""
    from colorimetry import xyz_to_lab
    lab_t = xyz_to_lab(100.0 * rgb @ sp.rgb2xyz.T, sp.white)
    M1E = sp.M1 * sp.E["D65"]

    def resid(c):
        return xyz_to_lab(jh_eval_1nm(c) @ M1E.T, sp.white)

    jac = torch.func.vmap(torch.func.jacfwd(resid))
    res_fn = torch.func.vmap(resid)
    c = torch.zeros(rgb.shape[0], 3, dtype=torch.float64) if init is None else init.clone()
    lam = torch.full((rgb.shape[0], 1, 1), 1e-2, dtype=torch.float64)
    for _ in range(iters):
        r = res_fn(c) - lab_t
        J = jac(c)
        JtJ = J.transpose(1, 2) @ J
        step = torch.linalg.solve(JtJ + lam * torch.diag_embed(torch.diagonal(JtJ, dim1=1, dim2=2) + 1e-9),
                                  -(J.transpose(1, 2) @ r[..., None]))[..., 0]
        cn = c + step
        better = (res_fn(cn) - lab_t).norm(dim=1) < r.norm(dim=1)
        c = torch.where(better[:, None], cn, c)
        lam = torch.where(better[:, None, None], lam * 0.3, lam * 10).clamp(1e-9, 1e9)
    return c, (res_fn(c) - lab_t).norm(dim=1)


def build_lut(sp: Spectral1nm, res=LUT_RES):
    """Continuation along shells of increasing Chebyshev distance from mid-grey, so
    neighbouring cells start from each other's solution (smooth coefficients)."""
    cache = CACHE / f"jh_lut_{res}.npz"
    if cache.exists():
        d = np.load(cache)
        return torch.tensor(d["coeffs"]), torch.tensor(d["err"])
    g = torch.linspace(0, 1, res, dtype=torch.float64)
    B, G, Rr = torch.meshgrid(g, g, g, indexing="ij")                    # index [b, g, r]
    rgb = torch.stack([Rr, G, B], -1).reshape(-1, 3)
    idx3 = torch.stack(torch.meshgrid(*(torch.arange(res),) * 3, indexing="ij"), -1).reshape(-1, 3)
    centre = (res - 1) / 2
    shell = (idx3.double() - centre).abs().max(1).values.ceil().long()
    coeffs = torch.zeros(rgb.shape[0], 3, dtype=torch.float64)
    err = torch.full((rgb.shape[0],), float("inf"), dtype=torch.float64)
    done = torch.zeros(rgb.shape[0], dtype=torch.bool)
    for s in range(int(shell.max()) + 1):
        sel = torch.where(shell == s)[0]
        if sel.numel() == 0:
            continue
        init = torch.zeros(sel.numel(), 3, dtype=torch.float64)
        if done.any():   # init from nearest solved cell
            d = torch.cdist(idx3[sel].double(), idx3[done].double())
            init = coeffs[done][d.argmin(1)]
        c, e = fit_jh(rgb[sel], sp, init=init)
        bad = e > 0.05
        if bad.any():    # retry from zero init
            c0, e0 = fit_jh(rgb[sel][bad], sp)
            better = e0 < e[bad]
            cb, eb = c[bad], e[bad]
            cb[better], eb[better] = c0[better], e0[better]
            c[bad], e[bad] = cb, eb
        coeffs[sel], err[sel], done[sel] = c, e, True
        print(f"LUT shell {s}: n={sel.numel()} max dE76={e.max().item():.3g}")
    CACHE.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, coeffs=coeffs.numpy(), err=err.numpy())
    return coeffs, err


def lut_lookup(coeffs: torch.Tensor, rgb: torch.Tensor, res=LUT_RES) -> torch.Tensor:
    """Trilinear interpolation of coefficients; layout index = (b*res + g)*res + r. Mirrors the WGSL."""
    p = rgb.clamp(0, 1) * (res - 1)
    i0 = p.floor().long().clamp(max=res - 2)
    f = p - i0
    C = coeffs.reshape(res, res, res, 3)
    out = 0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = ((f[:, 0] if dr else 1 - f[:, 0]) * (f[:, 1] if dg else 1 - f[:, 1]) *
                     (f[:, 2] if db else 1 - f[:, 2]))
                out = out + w[:, None] * C[i0[:, 2] + db, i0[:, 1] + dg, i0[:, 0] + dr]
    return out


def main():
    sp = Spectral1nm()
    mats = select_materials(sp)
    coeffs, err = build_lut(sp)
    quads, light, spheres, cam = geometry()
    names = list(TARGETS)
    from colorimetry import xyz_to_lab, delta_e_2000
    # uplift accuracy at the scene's materials (via the LUT, as the GPU does)
    mat_rgb = torch.stack([mats[n]["rgb"] for n in names])
    c_mat = lut_lookup(coeffs, mat_rgb)
    lab_up = xyz_to_lab(jh_eval_1nm(c_mat) @ (sp.M1 * sp.E["D65"]).T, sp.white)
    lab_t = xyz_to_lab(100.0 * mat_rgb.clamp(0, 1) @ sp.rgb2xyz.T, sp.white)
    uplift_dE = delta_e_2000(lab_t, lab_up)
    # random-colour LUT accuracy
    g = torch.Generator().manual_seed(0)
    rr = torch.rand(4000, 3, generator=g, dtype=torch.float64)
    lab_r = xyz_to_lab(jh_eval_1nm(lut_lookup(coeffs, rr)) @ (sp.M1 * sp.E["D65"]).T, sp.white)
    de_r = delta_e_2000(xyz_to_lab(100.0 * rr @ sp.rgb2xyz.T, sp.white), lab_r)

    lights = {s: light_spectrum(LIGHT_OF[s]) for s in SCENES}
    cmf = sp.cmf
    scene = {
        "resolution": RES, "max_bounces": MAX_BOUNCES, "light_Y": LIGHT_Y, "lut_res": LUT_RES,
        "camera": cam, "quads": [{"p0": p, "u": u, "v": v, "n": n, "mat": names.index(m)} for p, u, v, n, m in quads],
        "light": light, "spheres": [{"c": c, "r": r, "mat": names.index(m)} for c, r, m in spheres],
        "materials": [{"name": n, "ces_index": mats[n]["ces_index"], "rgb": mats[n]["rgb"].tolist(),
                       "dE_ces_to_target": mats[n]["dE_to_target"], "uplift_dE00_via_lut": uplift_dE[i].item()}
                      for i, n in enumerate(names)],
        "scenes": {s: {"light": LIGHT_OF[s], "light_rgb": ((torch.tensor(lights[s]) @ sp.M1.T / sp.c)
                                                           @ sp.xyz2rgb.T).tolist()} for s in SCENES},
        "lut_accuracy_random_rgb_dE00": {"mean": de_r.mean().item(), "p95": torch.quantile(de_r, .95).item(),
                                         "max": de_r.max().item()},
        "lut_fit_dE76": {"mean": err.mean().item(), "max": err.max().item(), "frac_gt_0.5": (err > 0.5).float().mean().item()},
        "wavelengths": [380, 780, 1],
        "xyz2rgb": sp.xyz2rgb.tolist(), "rgb2xyz": sp.rgb2xyz.tolist(),     # white Y=1 <-> rgb 1
        "white_xyz": sp.white.tolist(),                                     # D65, Y=100, for CIELAB
        "notes": "XYZ = sum cmf*L*1nm; light Y=15; materials = CIE 224:2017 CES (CC BY-SA 4.0)",
    }
    # light_rgb: linear sRGB of the light's XYZ (M1/c gives sum cmf*L; xyz2rgb expects white Y=1 scale)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "scene.json").write_text(json.dumps(scene, indent=1))
    # binary blobs (float32 little-endian)
    np.asarray(cmf, "<f4").tofile(DATA / "cmf_1nm.bin")                      # (401,3)
    for s in SCENES:
        np.asarray(lights[s], "<f4").tofile(DATA / f"light_{s}.bin")         # (401,)
    lut = np.zeros((LUT_RES**3, 4), "<f4"); lut[:, :3] = coeffs.numpy()
    lut.tofile(DATA / "jh_lut.bin")
    spectra = np.stack([mats[n]["spectrum"].numpy() for n in names])
    np.save(CACHE / "material_spectra.npy", spectra)
    np.asarray(spectra, "<f4").tofile(DATA / "material_spectra.bin")        # (nmat, 401), GPU mode 2
    print(json.dumps({k: scene[k] for k in ("materials", "lut_accuracy_random_rgb_dE00", "lut_fit_dE76", "scenes")}, indent=1))


if __name__ == "__main__":
    main()
