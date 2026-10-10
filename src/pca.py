"""Step 2: PCA of reflectance spectra in several value spaces, via torch SVD.

A model in space T approximates   T(s) ~= mu + B w,   B = (L, K) orthonormal columns.
Decoding always returns a reflectance in [0, 1]:
  raw   : T(s)=s              inverse = clamp(t, 0, 1)
  sqrt  : T(s)=sqrt(s)        inverse = clamp(t, 0, 1)^2
  logit : T(s)=log(s/(1-s))   inverse = sigmoid(t)       (in (0,1) by construction)
  log   : T(s)=log(s)         inverse = clamp(exp(t), 0, 1)
eps = 1e-3 guards logit/log at 0 and 1 (Munsell min is 0.030, so it is
inactive there; it matters for very dark ECOSTRESS spectra).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-3
SPACES = ("raw", "sqrt", "logit", "log")


def forward(s: torch.Tensor, space: str) -> torch.Tensor:
    if space == "raw":
        return s
    if space == "sqrt":
        return torch.sqrt(s.clamp(min=0))
    if space == "logit":
        s = s.clamp(EPS, 1 - EPS)
        return torch.log(s / (1 - s))
    if space == "log":
        return torch.log(s.clamp(min=EPS))
    raise ValueError(space)


def inverse(t: torch.Tensor, space: str) -> torch.Tensor:
    if space == "raw":
        return t.clamp(0, 1)
    if space == "sqrt":
        return t.clamp(0, 1) ** 2
    if space == "logit":
        return torch.sigmoid(t)
    if space == "log":
        return torch.exp(t).clamp(0, 1)
    raise ValueError(space)


@dataclass
class PCAModel:
    space: str
    mean: torch.Tensor        # (L,)
    components: torch.Tensor  # (L, Kmax), orthonormal columns
    explained_var: torch.Tensor        # (Kmax,) variance per component (transformed space)
    explained_var_ratio: torch.Tensor  # (Kmax,)

    def basis(self, K: int) -> torch.Tensor:
        return self.components[:, :K]

    def encode(self, s: torch.Tensor, K: int) -> torch.Tensor:
        return (forward(s, self.space) - self.mean) @ self.basis(K)

    def decode_t(self, w: torch.Tensor) -> torch.Tensor:
        """Decode to the transformed space (no range clamp)."""
        return self.mean + w @ self.basis(w.shape[-1]).T

    def decode(self, w: torch.Tensor) -> torch.Tensor:
        return inverse(self.decode_t(w), self.space)

    def save(self, path: Path):
        torch.save({"space": self.space, "mean": self.mean, "components": self.components,
                    "explained_var": self.explained_var,
                    "explained_var_ratio": self.explained_var_ratio}, path)

    @staticmethod
    def load(path: Path) -> "PCAModel":
        d = torch.load(path)
        return PCAModel(d["space"], d["mean"], d["components"], d["explained_var"], d["explained_var_ratio"])


def fit_pca(X_train: torch.Tensor, space: str, k_max: int = 20) -> PCAModel:
    """PCA by SVD of the centred training matrix (float64)."""
    T = forward(X_train.to(torch.float64), space)
    mu = T.mean(0)
    U, S, Vh = torch.linalg.svd(T - mu, full_matrices=False)
    # Deterministic sign convention: largest-magnitude entry of each component positive.
    V = Vh.T
    signs = torch.sign(V[V.abs().argmax(0), torch.arange(V.shape[1])])
    V = V * signs
    var = S**2 / (T.shape[0] - 1)
    return PCAModel(space, mu, V[:, :k_max].contiguous(), var[:k_max], (var / var.sum())[:k_max])


def load_processed():
    d = np.load(ROOT / "data" / "processed" / "spectra.npz")
    X = torch.tensor(d["X"], dtype=torch.float64)
    return X, d["is_test"], d["dataset"], d["name"], d["group"]


def main():
    X, is_test, dataset, *_ = load_processed()
    Xtr = X[~torch.tensor(is_test)]
    out = ROOT / "results" / "pca"
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for space in SPACES:
        m = fit_pca(Xtr, space)
        m.save(out / f"pca_{space}.pt")
        summary[space] = {"cumulative_explained_var_ratio": torch.cumsum(m.explained_var_ratio, 0)[:10].tolist()}
        np.savetxt(out / f"mean_{space}.txt", m.mean.numpy())
    (out / "pca_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"fit on {Xtr.shape[0]} training spectra ({dict(zip(*np.unique(dataset[~is_test], return_counts=True)))})")
    for s, v in summary.items():
        print(s, " ".join(f"{x:.5f}" for x in v["cumulative_explained_var_ratio"]))


if __name__ == "__main__":
    main()
