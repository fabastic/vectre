"""Task C accuracy companion: what does the cheap 'hybrid4' variant cost in accuracy?

hybrid4 = log-PCA throughput, evaluated only at 4 stratified wavelengths per
sample (same estimator as hero4 but applied to the log-PCA-approximated
throughput instead of the true one). Compared with hero4 on the TRUE spectra,
and with the full-decode log-PCA, under D65 and the narrow-band NB610 light.
Exposure-normalised dE00 (true Y = 20), random chains, held-out Munsell.
"""
from __future__ import annotations

import json
from pathlib import Path

import torch

from colorimetry import delta_e_2000, xyz_to_lab
from eval_illuminants import hero4, load_test_spectra
from pca import PCAModel
from spectral1nm import Spectral1nm

ROOT = Path(__file__).resolve().parents[1]


def main():
    sp = Spectral1nm()
    X5, R1 = load_test_spectra()
    lg = PCAModel.load(ROOT / "results/pca/pca_log.pt")
    A = torch.tensor(sp.A)
    g = torch.Generator().manual_seed(99)
    out = {}
    for illum in ("D65", "F11", "NB610"):
        E = sp.E[illum]
        for n in (1, 3, 5):
            idx = torch.stack([torch.randperm(X5.shape[0], generator=g)[: n + 1] for _ in range(5000)])
            T1 = R1[idx].prod(1)
            xyz_t = sp.xyz(T1, illum)
            expo = 20.0 / xyz_t[:, 1:2]
            lab_t = xyz_to_lab(xyz_t * expo, sp.white)
            de = lambda xyz: delta_e_2000(lab_t, xyz_to_lab(xyz * expo, sp.white)).mean().item()
            row = {}
            for K in (4, 6):
                t5 = (n + 1) * lg.mean + lg.encode(X5, K)[idx].sum(1) @ lg.basis(K).T
                T1_hat = torch.exp(t5).clamp(0, 1) @ A.T                 # log-PCA throughput at 1 nm
                row[f"logpca_full_K{K}"] = de(sp.xyz(T1_hat, illum))
                for spp in (16, 256):
                    row[f"hybrid4_K{K}_spp{spp}"] = de(hero4(T1_hat * E, sp.M1, spp, g))
            for spp in (16, 256):
                row[f"hero4_true_spp{spp}"] = de(hero4(T1 * E, sp.M1, spp, g))
            out[f"{illum}_n{n}"] = row
            print(illum, n, {k: round(v, 2) for k, v in row.items()})
    (ROOT / "results/hybrid4_accuracy.json").write_text(json.dumps(out, indent=1))


def light_aware_check():
    """Fairness check: hero4 with a LIGHT-AWARE wavelength pdf ~ (xbar+ybar+zbar) * E.

    Real renderers can importance-sample wavelengths by the light's spectrum
    (single light here; with many lights this needs MIS). This bounds how much
    of hero4's noise under line spectra is due to the light-agnostic pdf.
    """
    sp = Spectral1nm()
    X5, R1 = load_test_spectra()
    g = torch.Generator().manual_seed(5)
    out = {}
    for illum in ("D65", "F11", "NB610", "NEONLIKE"):
        E = sp.E[illum]
        ME = sp.M1 * E                                   # (3,401) light-weighted CMF
        for n in (1, 5):
            idx = torch.stack([torch.randperm(X5.shape[0], generator=g)[: n + 1] for _ in range(5000)])
            T1 = R1[idx].prod(1)
            xyz_t = sp.xyz(T1, illum)
            expo = 20.0 / xyz_t[:, 1:2]
            lab_t = xyz_to_lab(xyz_t * expo, sp.white)
            for spp in (1, 16, 256):
                # hero4(L, M, ...) samples with pdf ~ M.sum(0); passing (T1, ME) gives pdf ~ CMF*E
                xyz = hero4(T1, ME, spp, g)
                out[f"{illum}_n{n}_spp{spp}"] = delta_e_2000(lab_t, xyz_to_lab(xyz * expo, sp.white)).mean().item()
    print({k: round(v, 2) for k, v in out.items()})
    (ROOT / "results/hero4_light_aware.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
    light_aware_check()
