"""Dataset loaders, resampling to the common grid, and grouped train/test split.

Every loader returns a list of `Spectrum` records with the *native* sampling;
`resample()` maps them to 380..780 nm @ 5 nm and decides coverage.
"""
from __future__ import annotations

import gzip
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from colorimetry import WAVELENGTHS, WL_STEP

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"


@dataclass
class Spectrum:
    dataset: str
    name: str            # human-readable id
    group: str           # split unit ("material"); all members go to the same split
    wl_nm: np.ndarray    # native wavelengths, ascending, nm
    refl: np.ndarray     # native reflectance factor (fraction, not percent)
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Munsell (UEF / Univ. Joensuu, matt chips, Perkin-Elmer lambda 9, 380-800 @ 1 nm)
# ---------------------------------------------------------------------------

_MUNSELL_LABEL = re.compile(r"^\s*(?:\d+\s+)?([\d.]+)\s*([A-Z]{1,2})\s+([\d.]+)\s*/\s*([\d.]+)\s*$")


def load_munsell(raw_dir: Path = RAW / "munsell_uef") -> list[Spectrum]:
    with gzip.open(raw_dir / "munsell380_800_1.asc.gz", "rt") as f:
        vals = np.array([float(t) for t in f.read().split()])
    n_ch = 421
    assert vals.size % n_ch == 0, vals.size
    spectra = vals.reshape(-1, n_ch)                          # (1269, 421), README: color-major
    wl = np.arange(380, 801, dtype=np.float64)

    # Labels: index listing at the end of the README, in file order.
    text = (raw_dir / "README.txt").read_text(encoding="latin-1")
    index_part = text.split("The index of the ASCII spectra:", 1)[1]
    labels = []
    for line in index_part.splitlines():
        m = _MUNSELL_LABEL.match(line)
        if m:
            labels.append((m.group(1), m.group(2), m.group(3), m.group(4)))
    if len(labels) != spectra.shape[0]:
        raise ValueError(f"parsed {len(labels)} labels for {spectra.shape[0]} spectra")

    out = []
    for (hstep, hfam, value, chroma), r in zip(labels, spectra):
        hue_page = f"{hstep}{hfam}"
        out.append(Spectrum("munsell", f"{hstep} {hfam} {value}/{chroma}", f"munsell:{hue_page}",
                            wl, r.copy(), {"hue": hue_page, "value": float(value), "chroma": float(chroma)}))
    return out


# ---------------------------------------------------------------------------
# ECOSTRESS spectral library v1.0 (incl. ASTER v2.0), JPL.  *.spectrum.txt
# ---------------------------------------------------------------------------

_NUM2 = re.compile(r"^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)[\s,]+([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*$")


def parse_ecostress_file(path: Path) -> tuple[dict, np.ndarray]:
    """Parse one ECOSTRESS '*.spectrum.txt': 'Key: value' header, then 'x y' rows.

    Returns (header dict with lower-cased keys, (N,2) array as stored in the file).
    """
    header, rows = {}, []
    with open(path, "r", encoding="latin-1") as f:
        for line in f:
            m = _NUM2.match(line)
            if m:
                rows.append((float(m.group(1)), float(m.group(2))))
            elif not rows and ":" in line:
                k, v = line.split(":", 1)
                header[k.strip().lower()] = v.strip()
            # anything else (blank lines, trailing notes) is ignored
    return header, np.array(rows, dtype=np.float64).reshape(-1, 2)


def load_ecostress(raw_dir: Path = RAW / "ecostress") -> tuple[list[Spectrum], dict]:
    """Load reflectance spectra. Returns (spectra, rejection counts by reason)."""
    files = sorted(raw_dir.rglob("*.spectrum.txt")) if raw_dir.exists() else []
    out, rejected = [], {}

    def reject(reason):
        rejected[reason] = rejected.get(reason, 0) + 1

    for p in files:
        hdr, xy = parse_ecostress_file(p)
        xu, yu = hdr.get("x units", "").lower(), hdr.get("y units", "").lower()
        if "reflectance" not in yu:
            reject(f"y units not reflectance ({yu or 'missing'})"); continue
        if xy.shape[0] < 2:
            reject("no data rows"); continue
        x, y = xy[:, 0], xy[:, 1]
        if "micrometer" in xu or "micron" in xu or "µm" in xu:
            x = x * 1000.0
        elif "nanometer" in xu or xu.strip().endswith("nm"):
            pass
        else:
            reject(f"unknown x units ({xu or 'missing'})"); continue
        if "percent" in yu:
            y = y / 100.0
        # The library uses negative/sentinel values for missing samples in a few files.
        good = np.isfinite(x) & np.isfinite(y) & (y > -1.0)
        x, y = x[good], y[good]
        order = np.argsort(x)
        x, y = x[order], y[order]
        name = hdr.get("name", p.stem)
        cls = hdr.get("type", "?")
        out.append(Spectrum(
            "ecostress", f"{name} [{hdr.get('sample no.', '?')}]",
            f"ecostress:{cls.lower()}:{name.lower()}",   # split by material name
            x, y, {"file": p.name, "type": cls, "class": hdr.get("class", ""),
                   "subclass": hdr.get("subclass", ""), "particle_size": hdr.get("particle size", ""),
                   "owner": hdr.get("owner", ""), "measurement": hdr.get("measurement", "")}))
    return out, rejected


# ---------------------------------------------------------------------------
# Resampling & coverage
# ---------------------------------------------------------------------------

def resample(s: Spectrum, grid: np.ndarray = WAVELENGTHS, edge_ext_nm: float = 0.0,
             max_gap_nm: float = 10.0) -> tuple[np.ndarray | None, str]:
    """Box-filter the piecewise-linear interpolant over [l-2.5, l+2.5] nm for each grid l.

    The box filter equals point sampling for smooth/coarse data and avoids
    aliasing for densely sampled data. Inside the window, only the measured
    range is averaged (so edges are not polluted by extrapolation).

    Coverage rule: native data must reach grid[0] and grid[-1] (0.5 nm
    tolerance). With edge_ext_nm > 0, up to that many nm may be missing at
    either end and are filled by constant extension of the nearest value.
    Returns (resampled or None, status string).
    """
    lo, hi = s.wl_nm[0], s.wl_nm[-1]
    need_lo, need_hi = grid[0] + 0.5, grid[-1] - 0.5
    if lo > need_lo + edge_ext_nm or hi < need_hi - edge_ext_nm:
        return None, "insufficient range"
    inside = (s.wl_nm >= grid[0] - WL_STEP) & (s.wl_nm <= grid[-1] + WL_STEP)
    w = s.wl_nm[inside]
    if w.size >= 2 and np.max(np.diff(w)) > max_gap_nm:
        return None, f"gap > {max_gap_nm:g} nm in visible"
    half = WL_STEP / 2
    fine = np.arange(grid[0] - half, grid[-1] + half + 1e-9, 0.25)
    vals = np.interp(fine, s.wl_nm, s.refl)                 # constant beyond ends
    valid = (fine >= lo) & (fine <= hi)
    out = np.empty_like(grid)
    for i, g in enumerate(grid):
        win = (fine >= g - half) & (fine <= g + half)
        m = win & valid
        out[i] = vals[m].mean() if m.any() else vals[win].mean()   # latter = edge extension
    status = "ok" if (lo <= need_lo and hi >= need_hi) else "ok (edge-extended)"
    return out, status


def group_split(groups: list[str], test_frac: float = 0.2, salt: str = "vectre-v1") -> np.ndarray:
    """Deterministic grouped split: a group is 'test' iff hash(salt+group) < test_frac.

    Returns boolean mask (True = test). Hash-based so adding/removing other
    groups never moves an existing group between splits.
    """
    def u(g):
        h = hashlib.sha256((salt + g).encode()).digest()
        return int.from_bytes(h[:8], "big") / 2**64
    return np.array([u(g) < test_frac for g in groups])


def munsell_hue_split(hues: list[str], n_test_pages: int = 8) -> set[str]:
    """Hold out every 5th Munsell hue page (8 of 40), spread evenly round the hue circle.

    Neighbouring Munsell chips are nearly identical, so a random-row split would
    leak; holding out whole hue pages tests generalisation to unseen hues.
    """
    fam_order = ["R", "YR", "Y", "GY", "G", "BG", "B", "PB", "P", "RP"]
    def key(h):
        m = re.match(r"([\d.]+)([A-Z]+)", h)
        return fam_order.index(m.group(2)) * 10 + float(m.group(1))
    pages = sorted(set(hues), key=key)
    stride = len(pages) // n_test_pages
    return set(pages[2::stride][:n_test_pages])
