"""Verification of the colorimetry module.

Run:  python -m pytest tests  (or: python tests/test_colorimetry.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colorimetry import ColorEval, delta_e_2000, load_colorimetry, xyz_to_lab  # noqa: E402


def test_ciede2000_sharma_pairs():
    """All 34 pairs of Sharma et al. (2005), published to 4 decimals."""
    d = np.loadtxt(ROOT / "data/raw/sharma/ciede2000testdata.txt")
    assert d.shape == (34, 7)
    t = torch.tensor(d, dtype=torch.float64)
    de = delta_e_2000(t[:, 0:3], t[:, 3:6])
    err = (de - t[:, 6]).abs().max().item()
    assert err < 5e-5, err
    # symmetry
    de_rev = delta_e_2000(t[:, 3:6], t[:, 0:3])
    assert (de - de_rev).abs().max().item() < 1e-10


def test_against_colour_science():
    """Independent implementation cross-check (colour-science 0.4.x)."""
    import colour
    rng = np.random.default_rng(0)
    lab1 = rng.uniform([0, -100, -100], [100, 100, 100], size=(2000, 3))
    lab2 = lab1 + rng.normal(scale=5, size=lab1.shape)
    ours = delta_e_2000(torch.tensor(lab1), torch.tensor(lab2)).numpy()
    ref = colour.difference.delta_E_CIE2000(lab1, lab2)
    assert np.abs(ours - ref).max() < 1e-9

    white = np.array([95.0, 100.0, 108.0])
    xyz = rng.uniform(0, 110, size=(2000, 3))
    ours_lab = xyz_to_lab(torch.tensor(xyz), torch.tensor(white)).numpy()
    ref_lab = colour.XYZ_to_Lab(xyz / 100.0, colour.XYZ_to_xy(white / 100.0))
    assert np.abs(ours_lab - ref_lab).max() < 1e-9


def test_white_point_and_rgb():
    cm = load_colorimetry()
    assert cm.wl.size == 81
    # D65 white for 2deg observer is approx (95.04, 100, 108.88) at 1 nm;
    # 5 nm summation 380-780 should be within ~0.1.
    print("white XYZ (5nm, 380-780):", cm.white_xyz)
    assert np.allclose(cm.white_xyz, [95.04, 100.0, 108.88], atol=0.15)
    ce = ColorEval(cm)
    rgb_white = ce.spec_to_rgb(torch.ones(81, dtype=torch.float64))
    assert torch.allclose(rgb_white, torch.ones(3, dtype=torch.float64), atol=1e-12)
    import colour
    ref = colour.RGB_COLOURSPACES["sRGB"].matrix_XYZ_to_RGB
    assert np.abs(cm.M_xyz_to_rgb - ref).max() < 5e-3


if __name__ == "__main__":
    test_ciede2000_sharma_pairs()
    test_against_colour_science()
    test_white_point_and_rgb()
    print("all colorimetry tests passed")
