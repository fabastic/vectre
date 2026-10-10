"""Tests for Phase 1.5 components: hybrid decode, JH generator, weighted PCA, hero4 unbiasedness."""
from __future__ import annotations

import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from colorimetry import ColorEval, load_colorimetry  # noqa: E402
from eval_illuminants import hero4  # noqa: E402
from eval_shippable_basis import fit_weighted  # noqa: E402
from pca import fit_pca  # noqa: E402
from spectral1nm import Spectral1nm  # noqa: E402
from synthetic_spectra import generate_gp, generate_jh  # noqa: E402


def test_jh_generator_hits_targets():
    s, de = generate_jh(64, seed=3)
    assert s.min() >= 0 and s.max() <= 1
    assert de.max() < 1e-6


def test_weighted_pca_equal_weights_matches_plain():
    X = generate_gp(200, seed=4)
    a, b = fit_pca(X, "log"), fit_weighted([X], "log")
    assert torch.allclose(a.mean, b.mean, atol=1e-10)
    # same subspace for the leading components
    P = a.basis(4) @ a.basis(4).T
    assert (P @ b.basis(4) - b.basis(4)).abs().max() < 1e-8


def test_hybrid_decode_equals_full_decode_at_wavelengths():
    g = torch.Generator().manual_seed(0)
    K, L, N = 6, 81, 100
    mu, B = -torch.rand(L, generator=g), torch.randn(K, L, generator=g)
    w = torch.randn(N, K, generator=g)
    lam = torch.randint(0, L, (N, 4), generator=g)
    full = torch.exp(3 * mu + w @ B)
    hyb = torch.exp(3 * mu[lam] + (B.T[lam] * w[:, None, :]).sum(-1))
    assert torch.allclose(torch.gather(full, 1, lam), hyb, rtol=1e-5)


def test_hero4_unbiased():
    sp = Spectral1nm()
    g = torch.Generator().manual_seed(1)
    L1 = torch.rand(1, 401, generator=g, dtype=torch.float64) * sp.E["NEONLIKE"]
    est = hero4(L1.repeat(64, 1), sp.M1, 4096, g).mean(0)
    true = (L1 @ sp.M1.T)[0]
    assert ((est - true).abs() / true).max() < 0.01


if __name__ == "__main__":
    test_jh_generator_hits_targets(); test_weighted_pca_equal_weights_matches_plain()
    test_hybrid_decode_equals_full_decode_at_wavelengths(); test_hero4_unbiased()
    print("all phase 1.5 tests passed")
