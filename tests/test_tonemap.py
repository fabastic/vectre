"""Tonemapper tests: Oklab vs colour-science, range, hue preservation of maxrgb, oklch hue."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colorimetry import load_colorimetry  # noqa: E402
from tonemap import TONEMAPS, lin_srgb_to_oklab, oklab_to_lin_srgb  # noqa: E402


def test_oklab_matches_colour_science():
    import colour
    cm = load_colorimetry()
    rng = np.random.default_rng(0)
    rgb = rng.uniform(0, 1, (500, 3))
    ours = lin_srgb_to_oklab(torch.tensor(rgb)).numpy()
    xyz = rgb @ cm.M_rgb_to_xyz.T
    ref = colour.XYZ_to_Oklab(xyz)
    # small differences come from our sRGB matrix using the 5 nm-integrated D65 white
    assert np.abs(ours - ref).max() < 2e-3, np.abs(ours - ref).max()
    back = oklab_to_lin_srgb(torch.tensor(ours)).numpy()
    assert np.abs(back - rgb).max() < 1e-9


def test_tonemaps_in_range_and_hue():
    g = torch.Generator().manual_seed(0)
    x = torch.rand(1000, 3, generator=g, dtype=torch.float64) * torch.tensor([50.0, 5.0, 0.5], dtype=torch.float64)
    Ycoef = torch.tensor(load_colorimetry().M_rgb_to_xyz[1])
    for name, tm in TONEMAPS.items():
        y = tm(x, Ycoef)
        assert y.min() >= 0 and y.max() <= 1 + 1e-12, name
    y = TONEMAPS["maxrgb"](x, Ycoef)
    assert torch.allclose(y / y.sum(-1, keepdim=True), x / x.sum(-1, keepdim=True), atol=1e-12)
    # oklch keeps the Oklab hue (to bisection precision) for in-range inputs
    lab_in, lab_out = lin_srgb_to_oklab(x), lin_srgb_to_oklab(TONEMAPS["oklch"](x, Ycoef))
    sel = torch.hypot(lab_out[:, 1], lab_out[:, 2]) > 1e-3
    dh = torch.atan2(lab_in[:, 2], lab_in[:, 1]) - torch.atan2(lab_out[:, 2], lab_out[:, 1])
    dh = torch.remainder(dh + torch.pi, 2 * torch.pi) - torch.pi
    assert dh[sel].abs().max() < 1e-3


if __name__ == "__main__":
    test_oklab_matches_colour_science(); test_tonemaps_in_range_and_hue()
    print("all tonemap tests passed")
