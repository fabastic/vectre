"""Tests for the CPU reference path tracer (Phase 2 Task 1)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "cpu_reference"))
sys.path.insert(0, str(ROOT / "src"))

from pt import camera_array, light_pdf, pack_quad, radiance_along, render  # noqa: E402

FAR_LIGHT = pack_quad((10, 10, 10), (0.1, 0, 0), (0, 0, 0.1), (0, -1, 0))   # unreachable dummy light


def closed_cube():
    q = [((0, 0, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0)), ((0, 1, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0)),
         ((0, 0, 1), (1, 0, 0), (0, 1, 0), (0, 0, -1)), ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
         ((0, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0)), ((1, 0, 0), (0, 1, 0), (0, 0, 1), (-1, 0, 0))]
    return np.array([pack_quad(*x) for x in q]), np.zeros(6, np.int64)


def test_white_furnace():
    """Closed cube, every surface emits Le=1 and reflects rho: L = sum_{k=0}^{N} rho^k exactly."""
    Q, qm = closed_cube()
    S, sm = np.zeros((0, 4)), np.zeros(0, np.int64)
    Le = np.zeros(401)
    for rho in (0.5, 1.0):
        refl = np.full((1, 401), rho)
        o = np.array([0.5, 0.5, 0.5])
        for d in ([0, 0, 1.0], [0.3, -0.8, 0.2]):
            d = np.array(d) / np.linalg.norm(d)
            L = radiance_along(o, d, 200, 1, Q, qm, S, sm, FAR_LIGHT, refl, Le, False, 5, 1.0)
            expect = sum(rho**k for k in range(6))
            assert np.allclose(L, expect, atol=1e-12), (rho, L[:3], expect)


def view_factor_point_to_rect(a, b, c):
    """Differential area to a parallel a x b rectangle centred above it at distance c
    (4 x the standard corner formula)."""
    X, Y = (a / 2) / c, (b / 2) / c
    f = (X / math.sqrt(1 + X * X) * math.atan(Y / math.sqrt(1 + X * X))
         + Y / math.sqrt(1 + Y * Y) * math.atan(X / math.sqrt(1 + Y * Y))) / (2 * math.pi)
    return 4 * f


def test_view_factor_formula_vs_quadrature():
    from scipy import integrate
    a, b, c = 0.6, 0.4, 0.5
    num, _ = integrate.dblquad(lambda y, x: c * c / (math.pi * (x * x + y * y + c * c) ** 2),
                               -a / 2, a / 2, -b / 2, b / 2)
    assert abs(num - view_factor_point_to_rect(a, b, c)) < 1e-10


def test_two_surface_analytic():
    """Floor point under a parallel emitter: single-bounce radiance = rho * Le * F."""
    a, b, c, rho, Le0 = 0.6, 0.4, 0.5, 0.6, 2.0
    Q = np.array([pack_quad((-5, 0, -5), (10, 0, 0), (0, 0, 10), (0, 1, 0))])
    qm = np.zeros(1, np.int64)
    LQ = pack_quad((-a / 2, c, -b / 2), (a, 0, 0), (0, 0, b), (0, -1, 0))
    S, sm = np.zeros((0, 4)), np.zeros(0, np.int64)
    refl, Le = np.full((1, 401), rho), np.full(401, Le0)
    o = np.array([1.5, 0.2, 0.0]); d = -o / np.linalg.norm(o)       # ray hits the floor at the origin
    expect = rho * Le0 * view_factor_point_to_rect(a, b, c)
    L_nee = radiance_along(o, d, 400000, 3, Q, qm, S, sm, LQ, refl, Le, True, 1, 0.0)[0]
    L_pt = radiance_along(o, d, 400000, 4, Q, qm, S, sm, LQ, refl, Le, False, 1, 0.0)[0]
    assert abs(L_nee / expect - 1) < 0.005, (L_nee, expect)
    assert abs(L_pt / expect - 1) < 0.02, (L_pt, expect)


def _cornell_small(name, res=24, spp=2048, full=False, nee=True, nw=8):
    from render_reference import load_scene
    sc, cam, Q, qmat, S, smat, LQ, refl, Le, cmf = load_scene(name)
    cdf, pdf = light_pdf(cmf, Le)
    A, B, mask = render(res, res, spp, 5 if nee else 6, cam, Q, qmat, S, smat, LQ, refl, Le, cmf, cdf, pdf,
                        nw, full, nee, sc["max_bounces"], 0.0)
    return (A + B) / spp, mask


def test_nee_matches_pure_path_tracing():
    a, m = _cornell_small("cornell_d65", nee=True)
    b, _ = _cornell_small("cornell_d65", nee=False, spp=8192)
    sel = m == 0
    ra, rb = a[sel].mean(0), b[sel].mean(0)
    assert np.all(np.abs(ra / rb - 1) < 0.02), (ra, rb)


def test_sampled_wavelengths_match_full_spectrum():
    for name in ("cornell_nb610", "cornell_f11"):
        a, m = _cornell_small(name, spp=1024, nw=8)
        b, _ = _cornell_small(name, spp=256, full=True)
        sel = m == 0
        ra, rb = a[sel].mean(0), b[sel].mean(0)
        assert np.all(np.abs(ra / rb - 1) < 0.02), (name, ra, rb)


if __name__ == "__main__":
    test_white_furnace(); print("furnace ok")
    test_view_factor_formula_vs_quadrature(); print("view factor ok")
    test_two_surface_analytic(); print("two-surface ok")
    test_nee_matches_pure_path_tracing(); print("nee vs pt ok")
    test_sampled_wavelengths_match_full_spectrum(); print("wavelength sampling ok")
    print("all cpu reference tests passed")
