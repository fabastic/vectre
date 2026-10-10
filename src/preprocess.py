"""Step 1: load all datasets, resample to 380-780 nm @ 5 nm, filter, split, save.

Usage:  python src/preprocess.py [--edge-ext NM]
  --edge-ext 0   (default) strict coverage, as specified.
  --edge-ext 20  allow up to 20 nm constant extension at the ends (flagged).
Counts under both policies are always reported in results/data_summary.json.

Output: data/processed/spectra.npz with
  X        (N, 81) float64 reflectance factors in [0, 1]
  dataset, name, group : (N,) str
  is_test  (N,) bool
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from colorimetry import WAVELENGTHS
from datasets import group_split, load_ecostress, load_munsell, munsell_hue_split, resample

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edge-ext", type=float, default=0.0)
    args = ap.parse_args()

    munsell = load_munsell()
    eco, eco_rejected = load_ecostress()
    summary = {"grid_nm": [float(WAVELENGTHS[0]), float(WAVELENGTHS[-1]), 5.0],
               "edge_ext_nm_used": args.edge_ext, "datasets": {}}

    # Count survivors under both coverage policies for the report.
    for ds_name, items in [("munsell", munsell), ("ecostress", eco)]:
        info = {"loaded": len(items)}
        if ds_name == "ecostress":
            info["rejected_on_load"] = eco_rejected
        for policy, ext in [("strict", 0.0), ("edge_ext_20nm", 20.0)]:
            c = Counter(resample(s, edge_ext_nm=ext)[1] for s in items)
            info[f"coverage_{policy}"] = dict(c)
        summary["datasets"][ds_name] = info

    X, meta = [], []
    for s in munsell + eco:
        r, status = resample(s, edge_ext_nm=args.edge_ext)
        if r is None:
            continue
        meta.append((s.dataset, s.name, s.group, status, float(r.min()), float(r.max())))
        X.append(r)
    X = np.array(X)
    dataset = np.array([m[0] for m in meta])
    name = np.array([m[1] for m in meta])
    group = np.array([m[2] for m in meta])

    # Range handling: reflectance factors are physically ~[0,1]; measured
    # values can stray slightly (noise, white-reference calibration).
    for ds_name in np.unique(dataset):
        sel = dataset == ds_name
        Xd = X[sel]
        summary["datasets"][ds_name]["range_before_clip"] = {
            "min": float(Xd.min()), "max": float(Xd.max()),
            "n_spectra_with_any_value_lt_0": int((Xd < 0).any(1).sum()),
            "n_spectra_with_any_value_gt_1": int((Xd > 1).any(1).sum()),
            "max_abs_clip_amount": float(np.maximum(Xd - 1, -Xd).clip(min=0).max()),
        }
    X = np.clip(X, 0.0, 1.0)

    # Split by material: Munsell by hue page, ECOSTRESS by material name.
    is_test = np.zeros(len(X), bool)
    m_sel = dataset == "munsell"
    hues = [g.split(":", 1)[1] for g in group[m_sel]]
    test_pages = munsell_hue_split(hues)
    is_test[m_sel] = np.array([h in test_pages for h in hues])
    e_sel = dataset == "ecostress"
    if e_sel.any():
        is_test[e_sel] = group_split(list(group[e_sel]))
    summary["munsell_test_hue_pages"] = sorted(test_pages)

    for ds_name in np.unique(dataset):
        sel = dataset == ds_name
        summary["datasets"][ds_name]["kept"] = int(sel.sum())
        summary["datasets"][ds_name]["train"] = int((sel & ~is_test).sum())
        summary["datasets"][ds_name]["test"] = int((sel & is_test).sum())
        summary["datasets"][ds_name]["groups_train"] = int(len(set(group[sel & ~is_test])))
        summary["datasets"][ds_name]["groups_test"] = int(len(set(group[sel & is_test])))
    assert not (set(group[is_test]) & set(group[~is_test])), "group leakage across split"
    summary["total"] = {"kept": int(len(X)), "train": int((~is_test).sum()), "test": int(is_test.sum())}

    out = ROOT / "data" / "processed" / "spectra.npz"
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, X=X, dataset=dataset, name=name, group=group, is_test=is_test,
                        wavelengths=WAVELENGTHS)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "data_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
