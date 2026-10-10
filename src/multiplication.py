"""Operators for multiplying spectra in compressed form (used by Step 4/5 and export).

Linear PCA (raw or sqrt space):  t(s) ~= mu + B w.  Write the homogeneous weight
w_hat = (1, w_1..w_K) and basis b_hat_0 = mu, b_hat_k = b_k.  The per-wavelength
product of two decoded spectra, orthogonally projected back onto the affine
subspace, is

    w'_k = sum_ij  w_hat_i  w_hat_j  <b_k, b_hat_i * b_hat_j>  -  <b_k, mu>,   k=1..K

i.e. a fixed K x (K+1) x (K+1) tensor (the -<b_k,mu> offset is folded into
entry [k,0,0] since w_hat_0 = 1). This is a Galerkin projection of the
product; for a linear basis the idea goes back at least to Peercy, SIGGRAPH 1993
("Linear color representations for full spectral rendering").
Without clamping it is *mathematically identical* to decompress-multiply-
recompress (DMR); DMR differs only if the decoded spectra are clamped to [0,1].

Log-space PCA: log s ~= mu + B w  ->  log(s1 s2) = 2 mu + B (w1 + w2):
products are *exactly* closed if we also carry the count of mean terms c:
(c, w) * (c', w') = (c + c', w + w').  Addition of spectra is NOT closed.
"""
from __future__ import annotations

import torch

from pca import PCAModel, inverse


def product_tensor(model: PCAModel, K: int) -> torch.Tensor:
    """T[k, i, j] for k in 0..K-1 (outputs), i,j in 0..K (homogeneous inputs)."""
    B = model.basis(K)                                    # (L, K)
    Bh = torch.cat([model.mean[:, None], B], dim=1)       # (L, K+1)
    T = torch.einsum("lk,li,lj->kij", B, Bh, Bh).clone()  # (K, K+1, K+1)
    T[:, 0, 0] -= B.T @ model.mean
    return T


def tensor_mul(T: torch.Tensor, w1: torch.Tensor, w2: torch.Tensor) -> torch.Tensor:
    one = torch.ones_like(w1[..., :1])
    h1, h2 = torch.cat([one, w1], -1), torch.cat([one, w2], -1)
    return torch.einsum("kij,...i,...j->...k", T, h1, h2)


def dmr_mul(model: PCAModel, w1: torch.Tensor, w2: torch.Tensor, clamp: bool = True) -> torch.Tensor:
    """Decompress (to transformed space), multiply per wavelength, recompress.

    For the 'raw' space with clamp=True the decoded spectra are clamped to [0,1]
    before multiplying (the physically motivated variant). For 'sqrt' space the
    product is taken in sqrt space (sqrt(s1 s2) = sqrt(s1) sqrt(s2)).
    """
    t1, t2 = model.decode_t(w1), model.decode_t(w2)
    if clamp:
        t1, t2 = t1.clamp(0, 1), t2.clamp(0, 1)
    K = w1.shape[-1]
    return (t1 * t2 - model.mean) @ model.basis(K)


def color_matrix(model: PCAModel, K: int, M_xyz: torch.Tensor) -> torch.Tensor:
    """3 x (K+1) matrix: XYZ = C @ (1, w). Valid only for the raw space (no clamp)."""
    assert model.space == "raw"
    Bh = torch.cat([model.mean[:, None], model.basis(K)], dim=1)
    return M_xyz @ Bh
