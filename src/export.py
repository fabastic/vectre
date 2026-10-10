"""Step 6: export bases and product tensors for WebGPU (.bin float32 LE + .json).

One package per K in 3..10:  results/export/vectre_K{K}.bin / .json
Each array starts at a 256-byte-aligned offset (WebGPU's default
minStorageBufferOffsetAlignment), so the whole .bin can be uploaded as ONE
GPUBuffer and bound per-array with (offset, size). Layout is documented in
results/export/README.md; the .json carries offsets/shapes AND the values.

After writing, the .bin is read back and a float32 numpy re-implementation of
the tensor product / colour matrix / log-PCA decode is checked against the
float64 torch reference.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from colorimetry import ColorEval, load_colorimetry
from multiplication import color_matrix, product_tensor, tensor_mul
from pca import PCAModel, load_processed

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "export"
ALIGN = 256
KS = range(3, 11)


def build(K: int, raw: PCAModel, lg: PCAModel, ce: ColorEval) -> dict[str, np.ndarray]:
    C_xyz = color_matrix(raw, K, ce.M)                     # (3, K+1), XYZ with Y_white = 100
    C_rgb = ce.xyz2rgb @ (C_xyz / 100.0)                   # (3, K+1), linear sRGB, white = 1
    return {
        "wavelengths_nm": ce.cm.wl,
        "xyz_weights": ce.cm.M_xyz,                        # (3, 81): XYZ = W @ spectrum
        "raw_mean": raw.mean.numpy(),
        "raw_basis": raw.basis(K).T.numpy(),               # (K, 81), component-major
        "raw_tensor": product_tensor(raw, K).numpy(),      # (K, K+1, K+1)
        "raw_color_xyz": C_xyz.numpy(),
        "raw_color_linear_srgb": C_rgb.numpy(),
        "log_mean": lg.mean.numpy(),
        "log_basis": lg.basis(K).T.numpy(),                # (K, 81)
    }


def write(K: int, arrays: dict[str, np.ndarray], meta: dict):
    blob, entries, off = bytearray(), {}, 0
    for name, a in arrays.items():
        a32 = np.ascontiguousarray(a, dtype="<f4")
        pad = (-off) % ALIGN
        blob += b"\0" * pad
        off += pad
        entries[name] = {"offset_bytes": off, "size_bytes": a32.nbytes, "shape": list(a32.shape),
                         "dtype": "float32", "order": "C (row-major, last index fastest)"}
        blob += a32.tobytes()
        off += a32.nbytes
    blob += b"\0" * ((-len(blob)) % 4)
    (OUT / f"vectre_K{K}.bin").write_bytes(bytes(blob))
    manifest = {"K": K, "n_wavelengths": int(arrays["wavelengths_nm"].size), "alignment_bytes": ALIGN,
                "total_bytes": len(blob), "arrays": entries, **meta,
                "values": {k: np.asarray(v, dtype=np.float64).tolist() for k, v in arrays.items()}}
    (OUT / f"vectre_K{K}.json").write_text(json.dumps(manifest, indent=1))


def read_back(K: int) -> dict[str, np.ndarray]:
    man = json.loads((OUT / f"vectre_K{K}.json").read_text())
    blob = (OUT / f"vectre_K{K}.bin").read_bytes()
    return {n: np.frombuffer(blob, "<f4", count=int(np.prod(e["shape"])), offset=e["offset_bytes"]).reshape(e["shape"])
            for n, e in man["arrays"].items()}


def verify(K: int, raw: PCAModel, lg: PCAModel, X: torch.Tensor, ce: ColorEval) -> dict:
    a = read_back(K)
    w = raw.encode(X, K)
    w1, w2 = w[:-1], w[1:]
    ref = tensor_mul(product_tensor(raw, K), w1, w2).numpy()
    h1 = np.concatenate([np.ones((len(w1), 1), np.float32), w1.numpy().astype(np.float32)], 1)
    h2 = np.concatenate([np.ones((len(w2), 1), np.float32), w2.numpy().astype(np.float32)], 1)
    got = np.einsum("kij,ni,nj->nk", a["raw_tensor"], h1, h2)
    xyz_ref = (torch.cat([torch.ones(len(w1), 1, dtype=w.dtype), w1], 1) @ color_matrix(raw, K, ce.M).T).numpy()
    xyz_got = h1 @ a["raw_color_xyz"].T
    wl = lg.encode(X, K).numpy().astype(np.float32)
    dec_got = np.clip(np.exp(a["log_mean"] + wl @ a["log_basis"]), 0, 1)
    dec_ref = lg.decode(lg.encode(X, K)).numpy()
    return {"tensor_max_abs_err": float(np.abs(got - ref).max()),
            "color_xyz_max_abs_err": float(np.abs(xyz_got - xyz_ref).max()),
            "log_decode_max_abs_err": float(np.abs(dec_got - dec_ref).max())}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    X, is_test, *_ = load_processed()
    ce = ColorEval(load_colorimetry())
    raw = PCAModel.load(ROOT / "results" / "pca" / "pca_raw.pt")
    lg = PCAModel.load(ROOT / "results" / "pca" / "pca_log.pt")
    meta = {"spectral_grid": "380..780 nm step 5 (81 samples)",
            "trained_on": "Munsell matt (UEF), train split (32 of 40 hue pages); ECOSTRESS not yet included",
            "log_eps": 1e-3,
            "illuminant_observer": "CIE D65, CIE 1931 2deg (CIE datasets, CC BY-SA 4.0)"}
    report = {}
    for K in KS:
        write(K, build(K, raw, lg, ce), meta)
        report[K] = verify(K, raw, lg, X[torch.tensor(is_test)], ce)
        print(K, report[K])
    (OUT / "verify_report.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
