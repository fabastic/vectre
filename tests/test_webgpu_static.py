"""Static checks of the WebGPU sources against the Python implementations.

* display.wgsl's Oklab forward constants equal tonemap.M1/M2, and its inverse
  constants (Ottosson's published inverse, typed in) equal the numerical inverse.
* pt.wgsl's LUT layout/trilinear scheme: jh_lut.bin read with the WGSL index formula
  reproduces phase2_scene.lut_lookup.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tonemap import M1, M2  # noqa: E402

WGSL = (ROOT / "src/webgpu/display.wgsl").read_text()


def _nums(fn_name):
    body = WGSL.split(f"fn {fn_name}")[1].split("\n}")[0]
    return [float(x) for x in re.findall(r"-?\d+\.\d{6,}", body.replace("- ", "-").replace("+ ", ""))]


def test_oklab_constants():
    fwd = np.array(_nums("to_oklab"))
    assert fwd.size == 18
    assert np.allclose(fwd[:9], M1.numpy().ravel(), atol=1e-10)
    # second matrix appears as (row0: +,+,- ...) after sign folding
    assert np.allclose(fwd[9:], M2.numpy().ravel(), atol=1e-10)
    inv = np.array(_nums("from_oklab"))
    assert inv.size == 15   # first column of M2^-1 is exactly 1 (written as c.x)
    M2i = torch.linalg.inv(M2).numpy()
    assert np.allclose(M2i[:, 0], 1.0, atol=1e-9)
    assert np.allclose(inv[:6], M2i[:, 1:].ravel(), atol=2e-9)
    assert np.allclose(inv[6:], torch.linalg.inv(M1).numpy().ravel(), atol=2e-9)


def test_lut_layout_matches_python():
    from phase2_scene import LUT_RES, lut_lookup
    raw = np.fromfile(ROOT / "src/webgpu/data/jh_lut.bin", "<f4").reshape(-1, 4)
    coeffs = torch.tensor(raw[:, :3].astype(np.float64))
    g = torch.Generator().manual_seed(0)
    rgb = torch.rand(200, 3, generator=g, dtype=torch.float64)
    ref = lut_lookup(coeffs, rgb)
    # re-implement exactly as pt.wgsl does
    R = LUT_RES
    out = np.zeros((200, 3))
    for n, c in enumerate(rgb.numpy()):
        p = np.clip(c, 0, 1) * (R - 1)
        i0 = np.minimum(np.floor(p).astype(int), R - 2)
        f = p - i0
        for k in range(8):
            o = np.array([k & 1, (k >> 1) & 1, (k >> 2) & 1])
            w = np.prod(np.where(o == 1, f, 1 - f))
            i = i0 + o
            out[n] += w * raw[(i[2] * R + i[1]) * R + i[0], :3]
    assert np.allclose(out, ref.numpy(), atol=1e-5)


if __name__ == "__main__":
    test_oklab_constants(); test_lut_layout_matches_python()
    print("all webgpu static tests passed")
