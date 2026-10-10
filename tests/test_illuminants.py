"""Sanity tests for the 1 nm colorimetry and illuminants (Task A).

Reference chromaticities below are approximate published CIE 015 values used
only as loose sanity tolerances (+-0.002), not as input data.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colorimetry import ColorEval, load_colorimetry  # noqa: E402
from spectral1nm import ILLUMINANTS, WL1, Spectral1nm, interp_matrix, raw_illuminant  # noqa: E402


def xy(xyz):
    return (xyz[:2] / xyz.sum()).numpy()


def test_white_points():
    sp = Spectral1nm()
    one = torch.ones(WL1.size, dtype=torch.float64)
    # textbook D65 white integrates 360-830 nm; truncating to 380-780 nm costs ~0.02 in Z
    assert np.allclose(sp.white.numpy(), [95.047, 100.0, 108.883], atol=0.05)
    for name, ref in {"A": (0.4476, 0.4074), "F2": (0.3721, 0.3751), "F11": (0.3805, 0.3769)}.items():
        assert np.allclose(xy(sp.xyz(one, name)), ref, atol=2e-3), (name, xy(sp.xyz(one, name)))
    for name in ILLUMINANTS:
        assert abs(sp.xyz(one, name)[1].item() - 100.0) < 1e-9
    assert torch.allclose(sp.rgb_of_light("D65"), torch.ones(3, dtype=torch.float64), atol=1e-12)


def test_narrowband_shape():
    e = raw_illuminant("NB610")
    half = WL1[e >= 0.5 * e.max()]
    assert WL1[e.argmax()] == 610 and 4 <= half.max() - half.min() <= 6   # FWHM 5 nm on a 1 nm grid


def test_interp_and_5nm_consistency():
    A = interp_matrix()
    assert np.allclose(A.sum(1), 1) and A.shape == (401, 81)
    sp, ce = Spectral1nm(), ColorEval(load_colorimetry())
    # D65 5 nm-folded weights vs Phase 1 5 nm summation: same colorimetry within ~0.5%
    rel = (sp.W5("D65") - ce.M).abs().sum() / ce.M.abs().sum()
    assert rel < 5e-3, rel


if __name__ == "__main__":
    test_white_points(); test_narrowband_shape(); test_interp_and_5nm_consistency()
    print("all illuminant tests passed")
