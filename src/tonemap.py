"""Tonemappers on scene-linear sRGB (D65 white), all returning display-linear sRGB in [0,1].

  reinhard_channel  y_c = x_c+ / (1 + x_c+),  x+ = max(x, 0)            (Phase 1.5)
  maxrgb            x+ = max(x, 0); m = max_c x+_c;  y = x+ * (m/(1+m)) / m
                    Hue-preserving: channel RATIOS of the (negative-clipped) colour are kept
                    exactly. Out-of-gamut input is handled only by the negative clip.
  oklch             Y = luminance of x (row 2 of the sRGB->XYZ matrix); Y' = Y/(1+Y);
                    (L, C, h) = Oklch(x) (signed cube root, so out-of-gamut x is allowed);
                    L' = cbrt(Y')  (Oklab L of an achromatic colour of luminance Y');
                    C' = C * L'/L  (keeps C/L, i.e. Oklab "saturation");
                    then convert (L', C', h) back to linear sRGB and, if any channel is
                    outside [0,1], reduce C' by bisection at constant L', h (30 steps).
Oklab: Ottosson (2020), linear-sRGB -> LMS -> signed cbrt -> Lab matrices below;
verified against colour-science's XYZ_to_Oklab in tests/test_tonemap.py.
"""
from __future__ import annotations

import torch

M1 = torch.tensor([[0.4122214708, 0.5363325363, 0.0514459929],
                   [0.2119034982, 0.6806995451, 0.1073969566],
                   [0.0883024619, 0.2817188376, 0.6299787005]], dtype=torch.float64)
M2 = torch.tensor([[0.2104542553, 0.7936177850, -0.0040720468],
                   [1.9779984951, -2.4285922050, 0.4505937099],
                   [0.0259040371, 0.7827717662, -0.8086757660]], dtype=torch.float64)
M1i, M2i = torch.linalg.inv(M1), torch.linalg.inv(M2)


def _cbrt(x):
    return torch.sign(x) * x.abs() ** (1.0 / 3.0)


def lin_srgb_to_oklab(rgb):
    return _cbrt(rgb @ M1.T) @ M2.T


def oklab_to_lin_srgb(lab):
    return ((lab @ M2i.T) ** 3) @ M1i.T


def reinhard_channel(x, Ycoef=None):
    xp = x.clamp(min=0)
    return xp / (1 + xp)


def maxrgb(x, Ycoef=None):
    xp = x.clamp(min=0)
    m = xp.max(-1, keepdim=True).values
    return torch.where(m > 0, xp * (1.0 / (1 + m)), torch.zeros_like(xp))   # = xp * (m/(1+m))/m


def oklch(x, Ycoef):
    """Ycoef: (3,) luminance weights of linear sRGB (row Y of sRGB->XYZ, white Y=1)."""
    Y = (x @ Ycoef).clamp(min=0)
    Yp = Y / (1 + Y)
    lab = lin_srgb_to_oklab(x)
    L = lab[..., 0].clamp(min=1e-12)
    C = torch.hypot(lab[..., 1], lab[..., 2])
    h = torch.atan2(lab[..., 2], lab[..., 1])
    Lp = Yp ** (1.0 / 3.0)
    Cp = C * Lp / L

    def to_rgb(c):
        return oklab_to_lin_srgb(torch.stack([Lp, c * torch.cos(h), c * torch.sin(h)], -1))

    lo, hi = torch.zeros_like(Cp), Cp.clone()
    ok = lambda c: ((to_rgb(c) >= -1e-9) & (to_rgb(c) <= 1 + 1e-9)).all(-1)
    inside = ok(hi)
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        good = ok(mid)
        lo = torch.where(good, mid, lo)
        hi = torch.where(good, hi, mid)
    c_final = torch.where(inside, Cp, lo)
    return to_rgb(c_final).clamp(0, 1)


TONEMAPS = {"reinhard_channel": reinhard_channel, "maxrgb": maxrgb, "oklch": oklch}
