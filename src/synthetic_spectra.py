"""Task B: licence-free synthetic reflectance generators, and the CIE 99 CES loader.

Generators (all spectra are generated here, no third-party spectral data):
  jh  : Jakob & Hanika (2019) sigmoid-polynomial spectra, s(l) = S(c0 x^2 + c1 x + c2),
        S(z) = 1/2 + z / (2 sqrt(1 + z^2)), x = (l - 380)/400. Coefficients are fitted
        (Adam, batched) so the spectrum's CIELAB under D65 matches a target colour, as
        in their paper (they fit with Gauss-Newton on CIELAB distance). Targets: uniform
        in the *encoded* sRGB cube [0.02, 0.98]^3 (our choice). This is a KNOWN method;
        we only use it as a data generator.
  gp  : sigma(f(l)), f ~ Gaussian process with squared-exponential kernel; length-scale
        uniform in [25, 90] nm, amplitude uniform in [0.5, 2.5], mean uniform in [-3, 1].
        Ranges are arbitrary choices to give smooth spectra spanning dark..bright.
CIE 99 CES: CIE 224:2017 colour-evaluation samples (measured; CC BY-SA 4.0).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from colorimetry import WAVELENGTHS, ColorEval, load_colorimetry
from datasets import Spectrum, resample

ROOT = Path(__file__).resolve().parents[1]


def jh_sigmoid(z):
    return 0.5 + z / (2 * torch.sqrt(1 + z * z))


def jh_spectra(coeffs: torch.Tensor) -> torch.Tensor:
    x = torch.tensor((WAVELENGTHS - 380) / 400, dtype=coeffs.dtype)
    z = coeffs[:, 0:1] * x**2 + coeffs[:, 1:2] * x + coeffs[:, 2:3]
    return jh_sigmoid(z)


def srgb_decode(v):
    return torch.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def generate_jh(n: int, seed: int = 0, iters: int = 200):
    """Returns (spectra (n,81), fit dE76 per sample).

    Batched Levenberg-Marquardt on the CIELAB residual (3 equations, 3 unknowns),
    Jacobian by forward-mode autodiff. Several random restarts per target; the
    best fit is kept. (Jakob & Hanika use Gauss-Newton with continuation over a
    3D table; this is a simpler stand-in, so a few saturated targets may not be
    reachable; we report the residual.)
    """
    from colorimetry import xyz_to_lab
    ce = ColorEval(load_colorimetry())
    g = torch.Generator().manual_seed(seed)
    enc = 0.02 + 0.96 * torch.rand(n, 3, generator=g, dtype=torch.float64)
    lab_t = xyz_to_lab(100.0 * srgb_decode(enc) @ ce.rgb2xyz.T, ce.white)

    def resid(c):            # c: (3,) -> (3,)
        return ce.spec_to_lab(jh_spectra(c[None]))[0]

    jac = torch.func.vmap(torch.func.jacfwd(resid))
    res_fn = torch.func.vmap(resid)
    best_c = torch.zeros(n, 3, dtype=torch.float64)
    best_e = torch.full((n,), float("inf"), dtype=torch.float64)
    for restart in range(4):
        c = (torch.zeros(n, 3, dtype=torch.float64) if restart == 0
             else torch.randn(n, 3, generator=g, dtype=torch.float64) * 10.0 ** restart)
        lam = torch.full((n, 1, 1), 1e-2, dtype=torch.float64)
        for _ in range(iters):
            r = res_fn(c) - lab_t
            J = jac(c)
            JtJ = J.transpose(1, 2) @ J
            step = torch.linalg.solve(JtJ + lam * torch.diag_embed(torch.diagonal(JtJ, dim1=1, dim2=2) + 1e-9),
                                      -(J.transpose(1, 2) @ r[..., None]))[..., 0]
            c_new = c + step
            better = (res_fn(c_new) - lab_t).norm(dim=1) < r.norm(dim=1)
            c = torch.where(better[:, None], c_new, c)
            lam = torch.where(better[:, None, None], lam * 0.3, lam * 10).clamp(1e-9, 1e9)
        e = (res_fn(c) - lab_t).norm(dim=1)
        upd = e < best_e
        best_c[upd], best_e[upd] = c[upd], e[upd]
    return jh_spectra(best_c), best_e


def generate_gp(n: int, seed: int = 0):
    g = torch.Generator().manual_seed(seed)
    wl = torch.tensor(WAVELENGTHS, dtype=torch.float64)
    d2 = (wl[:, None] - wl[None, :]) ** 2
    out = []
    ls = 25 + 65 * torch.rand(n, generator=g, dtype=torch.float64)
    amp = 0.5 + 2.0 * torch.rand(n, generator=g, dtype=torch.float64)
    mu = -3 + 4 * torch.rand(n, generator=g, dtype=torch.float64)
    for i in range(n):
        Kc = amp[i] ** 2 * torch.exp(-0.5 * d2 / ls[i] ** 2) + 1e-6 * torch.eye(wl.numel(), dtype=torch.float64)
        Lc = torch.linalg.cholesky(Kc)
        f = mu[i] + Lc @ torch.randn(wl.numel(), generator=g, dtype=torch.float64)
        out.append(torch.sigmoid(f))
    return torch.stack(out)


def load_cie99() -> torch.Tensor:
    """CIE 224:2017 99 CES at 1 nm -> 5 nm grid with the Phase 1 box filter."""
    tab = np.genfromtxt(ROOT / "data/raw/cie/CIE_srf_cfi_1nm.csv", delimiter=",")
    wl = tab[:, 0]
    rows = []
    for j in range(1, tab.shape[1]):
        r, status = resample(Spectrum("cie99", f"CES{j}", f"cie99:{j}", wl, tab[:, j]))
        assert status == "ok", status
        rows.append(np.clip(r, 0, 1))
    return torch.tensor(np.array(rows))
