"""Render the Phase 2 reference images on CPU.

Usage: python src/cpu_reference/render_reference.py [--spp N] [--res R] [--scenes a,b]
Outputs per scene (results/phase2/):
  ref_<scene>.npz            xyz (H,W,3) = mean over all samples, xyz_a / xyz_b (independent
                             halves), emitter mask, spp, timing
  ../../src/webgpu/data/ref_<scene>_xyz.bin   float32 (H,W,3) for the browser harness
  ref_<scene>_srgb.png       display image (exposure: reference median non-emitter Y -> 18,
                             max-RGB hue-preserving tonemap, sRGB OETF)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "cpu_reference"))

from pt import camera_array, light_pdf, pack_quad, render  # noqa: E402

DATA = ROOT / "src" / "webgpu" / "data"
OUT = ROOT / "results" / "phase2"


def load_scene(name: str):
    sc = json.loads((DATA / "scene.json").read_text())
    Q = np.array([pack_quad(q["p0"], q["u"], q["v"], q["n"]) for q in sc["quads"]])
    qmat = np.array([q["mat"] for q in sc["quads"]], np.int64)
    lt = sc["light"]
    LQ = pack_quad(lt["p0"], lt["u"], lt["v"], lt["n"])
    S = np.array([[*s["c"], s["r"]] for s in sc["spheres"]], np.float64)
    smat = np.array([s["mat"] for s in sc["spheres"]], np.int64)
    refl = np.load(OUT / "material_spectra.npy").astype(np.float64)
    Le = np.fromfile(DATA / f"light_{name}.bin", "<f4").astype(np.float64)
    cmf = np.fromfile(DATA / "cmf_1nm.bin", "<f4").astype(np.float64).reshape(401, 3)
    cam = camera_array(sc["camera"]["pos"], tan_half=sc["camera"]["tan_half_fov"])
    return sc, cam, Q, qmat, S, smat, LQ, refl, Le, cmf


def to_srgb8(xyz, k, xyz2rgb):
    """Exposure k, max-RGB hue-preserving tonemap, sRGB OETF -> uint8."""
    rgb = np.clip((xyz * k / 100.0) @ xyz2rgb.T, 0, None)
    m = rgb.max(-1, keepdims=True)
    rgb = rgb / (1 + m)
    enc = np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
    return (np.clip(enc, 0, 1) * 255 + 0.5).astype(np.uint8)


def exposure(xyz, mask):
    return 18.0 / np.median(xyz[..., 1][mask == 0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spp", type=int, default=4096)
    ap.add_argument("--res", type=int, default=None)
    ap.add_argument("--nw", type=int, default=8)
    ap.add_argument("--chunk", type=int, default=512, help="spp per progress chunk (even)")
    ap.add_argument("--scenes", default="cornell_d65,cornell_nb610,cornell_f11")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    from spectral1nm import Spectral1nm
    xyz2rgb = Spectral1nm().xyz2rgb.numpy()
    import matplotlib.pyplot as plt
    for name in a.scenes.split(","):
        sc, cam, Q, qmat, S, smat, LQ, refl, Le, cmf = load_scene(name)
        res = a.res or sc["resolution"]
        cdf, pdf = light_pdf(cmf, Le)
        # Render in chunks (independent seeds) so progress is visible and a stall is detectable.
        # Each chunk has an even spp, so the even/odd halves stay balanced.
        assert a.spp % a.chunk == 0 and a.chunk % 2 == 0
        t0, c0 = time.time(), time.process_time()
        A = B = None
        for ci in range(a.spp // a.chunk):
            tc = time.time()
            a_, b_, mask = render(res, res, a.chunk, 20261010 + ci, cam, Q, qmat, S, smat, LQ, refl, Le, cmf,
                                  cdf, pdf, a.nw, False, True, sc["max_bounces"], 0.0)
            A = a_ if A is None else A + a_
            B = b_ if B is None else B + b_
            wall = time.time() - t0
            print(f"[{time.strftime('%H:%M:%S')}] {name} chunk {ci + 1}/{a.spp // a.chunk} "
                  f"({a.chunk} spp) {time.time() - tc:.1f}s; total {wall:.0f}s; "
                  f"avg cores busy {(time.process_time() - c0) / max(wall, 1e-9):.1f}", flush=True)
        dt = time.time() - t0
        na, nb_ = (a.spp + 1) // 2, a.spp // 2
        xyz = (A + B) / a.spp
        xa, xb = A / na, B / nb_
        k = exposure(xyz, mask)
        np.savez_compressed(OUT / f"ref_{name}.npz", xyz=xyz, xyz_a=xa, xyz_b=xb, mask=mask, spp=a.spp,
                            nw=a.nw, seconds=dt, exposure=k)
        xyz.astype("<f4").tofile(DATA / f"ref_{name}_xyz.bin")
        mask.astype(np.uint8).tofile(DATA / f"ref_{name}_mask.bin")
        import hashlib
        (DATA / f"ref_{name}_meta.json").write_text(json.dumps({
            "scene": name, "res": int(res), "spp": int(a.spp), "nw": int(a.nw), "seconds": float(dt),
            "exposure": float(k), "xyz_sha256": hashlib.sha256((DATA / f"ref_{name}_xyz.bin").read_bytes()).hexdigest()}, indent=1))
        plt.imsave(OUT / f"ref_{name}_srgb.png", to_srgb8(xyz, k, xyz2rgb))
        # half-vs-half noise estimate (relative RMSE of Y on non-emitter pixels)
        m = mask == 0
        rel = np.sqrt(np.mean(((xa - xb)[..., 1][m] * k) ** 2)) / 2 / 100.0
        print(f"{name}: {res}x{res} spp={a.spp} nw={a.nw} {dt:.1f}s exposure={k:.4f} "
              f"half-split noise (Y, rel. to white=1, std of full mean)={rel:.5f}", flush=True)


if __name__ == "__main__":
    main()
