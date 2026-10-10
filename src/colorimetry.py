"""Colorimetry: CIE 1931 2deg CMFs, D65, XYZ, CIELAB, CIEDE2000, linear sRGB.

Data provenance (no values typed from memory):
  * CMFs: CIE_xyz_1931_2deg.csv, CIE dataset DOI 10.25039/CIE.DS.xvudnb9b
    (from CIE 018:2019 Table 6), 360-830 nm @ 1 nm.
  * D65:  CIE_std_illum_D65.csv, CIE dataset DOI 10.25039/CIE.DS.hjfjmt59
    (from ISO/CIE 11664-2:2022 Table B.1), 300-830 nm @ 1 nm.
  Both are CC BY-SA 4.0 and are MD5-verified by src/fetch_data.py.

Integration convention (an explicit assumption, see LAB_NOTEBOOK.md):
  Tristimulus values are computed by plain summation on the common 5 nm grid
  380..780 nm, using the 1 nm CIE tables *sampled* at the 5 nm grid points
  (CIE 015:2018 permits 5 nm summation; we do not use ASTM E308 weighting
  tables). Normalisation k = 100 / sum(S * ybar), so a perfect reflector has
  Y = 100. Because the *same* linear operator is used for ground truth and for
  every approximation, this choice cannot bias the comparisons.

sRGB: the linear-sRGB matrix is *derived* from the IEC 61966-2-1 primary
chromaticities R(0.64,0.33) G(0.30,0.60) B(0.15,0.06), white-balanced to the
D65 white point produced by our own integration, so a perfect white reflector
maps exactly to RGB (1,1,1). This gives the RGB baseline its best case.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
CIE_DIR = ROOT / "data" / "raw" / "cie"

# Common spectral grid used everywhere in the project.
WL_START, WL_END, WL_STEP = 380, 780, 5
WAVELENGTHS = np.arange(WL_START, WL_END + 1, WL_STEP, dtype=np.float64)  # 81 samples
N_WL = WAVELENGTHS.size


def _read_cie_csv(path: Path) -> np.ndarray:
    # CIE CSVs have no header; missing entries are literally "NaN".
    return np.genfromtxt(path, delimiter=",", dtype=np.float64)


def _sample_at(table: np.ndarray, wl: np.ndarray) -> np.ndarray:
    """Pick rows of a 1 nm table at integer wavelengths `wl` (exact, no interpolation)."""
    idx = {int(round(w)): i for i, w in enumerate(table[:, 0])}
    rows = [idx[int(w)] for w in wl]
    out = table[rows, 1:]
    if np.isnan(out).any():
        raise ValueError(f"NaN in CIE table {table.shape} on requested grid")
    return out


@dataclass
class Colorimetry:
    wl: np.ndarray            # (L,)
    cmf: np.ndarray           # (L, 3) xbar, ybar, zbar
    illum: np.ndarray         # (L,)  D65 relative SPD
    M_xyz: np.ndarray         # (3, L) reflectance -> XYZ (Y_white = 100)
    white_xyz: np.ndarray     # (3,)
    M_xyz_to_rgb: np.ndarray  # (3, 3) XYZ/100 -> linear sRGB
    M_rgb_to_xyz: np.ndarray  # (3, 3)


def load_colorimetry(wl: np.ndarray = WAVELENGTHS, cie_dir: Path = CIE_DIR) -> Colorimetry:
    cmf = _sample_at(_read_cie_csv(cie_dir / "CIE_xyz_1931_2deg.csv"), wl)
    d65 = _sample_at(_read_cie_csv(cie_dir / "CIE_std_illum_D65.csv"), wl)[:, 0]
    k = 100.0 / np.sum(d65 * cmf[:, 1])
    M_xyz = k * (cmf * d65[:, None]).T             # (3, L)
    white = M_xyz.sum(axis=1)                      # XYZ of perfect reflector
    M_rgb_to_xyz = _rgb_to_xyz_matrix(white / 100.0)
    return Colorimetry(wl, cmf, d65, M_xyz, white, np.linalg.inv(M_rgb_to_xyz), M_rgb_to_xyz)


def _rgb_to_xyz_matrix(white_xyz: np.ndarray) -> np.ndarray:
    """Standard derivation of an RGB->XYZ matrix from primaries + white point."""
    prim = np.array([[0.64, 0.33], [0.30, 0.60], [0.15, 0.06]])  # IEC 61966-2-1 sRGB
    P = np.stack([prim[:, 0] / prim[:, 1], np.ones(3), (1 - prim.sum(1)) / prim[:, 1]])  # cols = XYZ of primaries (Y=1)
    S = np.linalg.solve(P, white_xyz)
    return P * S[None, :]


# ---------------------------------------------------------------------------
# Torch colour maths (float64 recommended for evaluation)
# ---------------------------------------------------------------------------

def xyz_to_lab(xyz: torch.Tensor, white: torch.Tensor) -> torch.Tensor:
    """CIE 1976 L*a*b* (CIE 015:2018 eq. 8.x). xyz: (..., 3)."""
    t = xyz / white
    d = 6.0 / 29.0
    f = torch.where(t > d**3, torch.clamp(t, min=d**3) ** (1.0 / 3.0), t / (3 * d * d) + 4.0 / 29.0)
    L = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return torch.stack([L, a, b], dim=-1)


def delta_e_2000(lab1: torch.Tensor, lab2: torch.Tensor) -> torch.Tensor:
    """CIEDE2000 (kL=kC=kH=1), following Sharma, Wu & Dalal, Color Res. Appl. 30(1), 2005.

    Verified against the paper's 34 published test pairs in tests/test_colorimetry.py.
    """
    L1, a1, b1 = lab1.unbind(-1)
    L2, a2, b2 = lab2.unbind(-1)
    rad = torch.pi / 180.0
    C1 = torch.sqrt(a1**2 + b1**2)
    C2 = torch.sqrt(a2**2 + b2**2)
    Cb7 = ((C1 + C2) / 2) ** 7
    G = 0.5 * (1 - torch.sqrt(Cb7 / (Cb7 + 25.0**7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p = torch.sqrt(a1p**2 + b1**2)
    C2p = torch.sqrt(a2p**2 + b2**2)
    h1p = torch.remainder(torch.atan2(b1, a1p) / rad, 360.0)
    h2p = torch.remainder(torch.atan2(b2, a2p) / rad, 360.0)
    h1p = torch.where((a1p == 0) & (b1 == 0), torch.zeros_like(h1p), h1p)
    h2p = torch.where((a2p == 0) & (b2 == 0), torch.zeros_like(h2p), h2p)

    dLp = L2 - L1
    dCp = C2p - C1p
    zeroC = (C1p * C2p) == 0
    dh = h2p - h1p
    dhp = torch.where(dh > 180, dh - 360, torch.where(dh < -180, dh + 360, dh))
    dhp = torch.where(zeroC, torch.zeros_like(dhp), dhp)
    dHp = 2 * torch.sqrt(C1p * C2p) * torch.sin(dhp * rad / 2)

    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hsum = h1p + h2p
    hbp = torch.where(
        (h1p - h2p).abs() <= 180, hsum / 2,
        torch.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2))
    hbp = torch.where(zeroC, hsum, hbp)

    T = (1 - 0.17 * torch.cos((hbp - 30) * rad) + 0.24 * torch.cos(2 * hbp * rad)
         + 0.32 * torch.cos((3 * hbp + 6) * rad) - 0.20 * torch.cos((4 * hbp - 63) * rad))
    dtheta = 30 * torch.exp(-(((hbp - 275) / 25) ** 2))
    Cbp7 = Cbp**7
    RC = 2 * torch.sqrt(Cbp7 / (Cbp7 + 25.0**7))
    SL = 1 + 0.015 * (Lbp - 50) ** 2 / torch.sqrt(20 + (Lbp - 50) ** 2)
    SC = 1 + 0.045 * Cbp
    SH = 1 + 0.015 * Cbp * T
    RT = -torch.sin(2 * dtheta * rad) * RC
    return torch.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2
                      + RT * (dCp / SC) * (dHp / SH))


class ColorEval:
    """Convenience wrapper: spectra / XYZ / RGB -> Lab -> dE2000, all in torch float64."""

    def __init__(self, cm: Colorimetry, dtype=torch.float64):
        self.cm = cm
        self.M = torch.tensor(cm.M_xyz, dtype=dtype)            # (3, L)
        self.white = torch.tensor(cm.white_xyz, dtype=dtype)
        self.xyz2rgb = torch.tensor(cm.M_xyz_to_rgb, dtype=dtype)
        self.rgb2xyz = torch.tensor(cm.M_rgb_to_xyz, dtype=dtype)
        self.dtype = dtype

    def spec_to_xyz(self, s: torch.Tensor) -> torch.Tensor:
        return s.to(self.dtype) @ self.M.T

    def spec_to_lab(self, s: torch.Tensor) -> torch.Tensor:
        return xyz_to_lab(self.spec_to_xyz(s), self.white)

    def spec_to_rgb(self, s: torch.Tensor) -> torch.Tensor:
        """Linear sRGB of a reflectance under D65 (white reflector -> (1,1,1))."""
        return (self.spec_to_xyz(s) / 100.0) @ self.xyz2rgb.T

    def rgb_to_lab(self, rgb: torch.Tensor) -> torch.Tensor:
        return xyz_to_lab(100.0 * rgb.to(self.dtype) @ self.rgb2xyz.T, self.white)

    def de_spec(self, s_ref: torch.Tensor, s_test: torch.Tensor) -> torch.Tensor:
        return delta_e_2000(self.spec_to_lab(s_ref), self.spec_to_lab(s_test))
