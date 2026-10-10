"""1 nm ground-truth colorimetry and illuminants (Phase 1.5, Task A).

Phase 1 integrated on the 5 nm grid. That cannot resolve a 5 nm-FWHM emission
line, so for illuminant tests the GROUND TRUTH is computed at 1 nm (380..780,
401 samples) from native 1 nm reflectances (Munsell is measured at 1 nm).
Methods that live on the 5 nm grid (PCA decodes) are linearly interpolated to
1 nm and integrated with the same 1 nm weights, i.e. their colour is
    XYZ = W_E5 @ s5,   W_E5 = c * CMF^T diag(E) @ A   (A: 5nm->1nm interpolation)
which is the best a 5 nm-sampled renderer can do for that light.

Illuminants (all normalised so a perfect white reflector has Y = 100):
  D65, A        CIE datasets (DOIs 10.25039/CIE.DS.hjfjmt59, 10.25039/CIE.DS.8jsxjrsn)
  F2, F11       columns FL2, FL11 of CIE_illum_FLs_1nm.csv (DOI 10.25039/CIE.DS.54hy6srn,
                from CIE 015:2018 Tables 10.1-10.3)
  NB610         SYNTHETIC: single Gaussian line, centre 610 nm, FWHM 5 nm
  NEONLIKE      SYNTHETIC multi-line source, NOT real neon data: 14 lines at
                seeded-random positions in 580-710 nm (where a neon discharge
                is qualitatively strongest) with random relative strengths,
                each a Gaussian of FWHM 1 nm. Real Ne I line data (NIST ASD)
                could not be fetched programmatically; see LAB_NOTEBOOK.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from colorimetry import WAVELENGTHS as WL5, _rgb_to_xyz_matrix

ROOT = Path(__file__).resolve().parents[1]
CIE = ROOT / "data" / "raw" / "cie"
WL1 = np.arange(380, 781, 1, dtype=np.float64)       # 401 samples
ILLUMINANTS = ("D65", "A", "F2", "F11", "NB610", "NEONLIKE")


def _table(path: Path) -> np.ndarray:
    return np.genfromtxt(path, delimiter=",", dtype=np.float64)


def _on_grid(tab: np.ndarray, cols, wl=WL1) -> np.ndarray:
    idx = {int(round(w)): i for i, w in enumerate(tab[:, 0])}
    out = tab[[idx[int(w)] for w in wl]][:, cols]
    out = np.nan_to_num(out, nan=0.0)   # CIE: NaN gaps may be set to zero for computation
    return out


def _gauss(center, fwhm, wl=WL1):
    sigma = fwhm / (2 * np.sqrt(2 * np.log(2)))
    return np.exp(-0.5 * ((wl - center) / sigma) ** 2)


def raw_illuminant(name: str) -> np.ndarray:
    if name == "D65":
        return _on_grid(_table(CIE / "CIE_std_illum_D65.csv"), 1)
    if name == "A":
        return _on_grid(_table(CIE / "CIE_std_illum_A_1nm.csv"), 1)
    if name in ("F2", "F11"):
        col = {"F2": 2, "F11": 11}[name]          # column 0 = lambda, then FL1..FL12, FL3.x
        return _on_grid(_table(CIE / "CIE_illum_FLs_1nm.csv"), col)
    if name == "NB610":
        return _gauss(610.0, 5.0)
    if name == "NEONLIKE":
        rng = np.random.default_rng(20261010)
        centers = rng.uniform(580, 710, 14)
        strengths = rng.uniform(0.1, 1.0, 14) ** 2
        return sum(a * _gauss(c, 1.0) for a, c in zip(strengths, centers))
    raise ValueError(name)


def interp_matrix(src=WL5, dst=WL1) -> np.ndarray:
    """(len(dst), len(src)) linear-interpolation matrix."""
    A = np.zeros((dst.size, src.size))
    for i, w in enumerate(dst):
        j = np.searchsorted(src, w, side="right") - 1
        j = min(max(j, 0), src.size - 2)
        t = (w - src[j]) / (src[j + 1] - src[j])
        A[i, j], A[i, j + 1] = 1 - t, t
    return A


class Spectral1nm:
    """Ground-truth colorimetry at 1 nm, Lab always relative to the D65 white.

    Using the D65 white for every illuminant models an un-white-balanced
    display: the image is shown as rendered (an evaluation choice, see notebook).
    """

    def __init__(self, dtype=torch.float64):
        cmf = _on_grid(_table(CIE / "CIE_xyz_1931_2deg.csv"), [1, 2, 3])
        d65 = raw_illuminant("D65")
        self.c = 100.0 / np.sum(d65 * cmf[:, 1])
        self.cmf = cmf
        self.white = torch.tensor(self.c * cmf.T @ d65, dtype=dtype)       # D65 white, Y = 100
        M_rgb2xyz = _rgb_to_xyz_matrix(self.white.numpy() / 100.0)        # sRGB primaries, D65 white
        self.rgb2xyz = torch.tensor(M_rgb2xyz, dtype=dtype)
        self.xyz2rgb = torch.tensor(np.linalg.inv(M_rgb2xyz), dtype=dtype)
        self.A = interp_matrix()
        self.dtype = dtype
        self.E = {}
        for n in ILLUMINANTS:
            e = raw_illuminant(n)
            self.E[n] = torch.tensor(e * 100.0 / (self.c * np.sum(e * cmf[:, 1])), dtype=dtype)
        self.M1 = torch.tensor(self.c * cmf.T, dtype=dtype)                  # (3, 401): XYZ = M1 @ radiance

    def xyz_of_radiance(self, L1: torch.Tensor) -> torch.Tensor:
        return L1 @ self.M1.T

    def xyz(self, T1: torch.Tensor, illum: str) -> torch.Tensor:
        """XYZ of a 1 nm reflectance/throughput under an illuminant."""
        return (T1 * self.E[illum]) @ self.M1.T

    def W5(self, illum: str) -> torch.Tensor:
        """(3, 81) weights for a 5 nm-sampled throughput, via linear interpolation to 1 nm."""
        return (self.M1 * self.E[illum]) @ torch.tensor(self.A, dtype=self.dtype)

    def rgb_of_reflectance(self, R1: torch.Tensor) -> torch.Tensor:
        """Standard albedo: linear sRGB of the reflectance under D65 (white -> 1,1,1)."""
        return (self.xyz(R1, "D65") / 100.0) @ self.xyz2rgb.T

    def rgb_of_light(self, illum: str) -> torch.Tensor:
        """Linear sRGB of the illuminant itself (= of a white reflector under it)."""
        return (self.xyz(torch.ones(WL1.size, dtype=self.dtype), illum) / 100.0) @ self.xyz2rgb.T
