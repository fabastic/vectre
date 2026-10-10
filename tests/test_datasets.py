"""Loader tests. The ECOSTRESS test uses a SYNTHETIC file written to mimic the
documented '*.spectrum.txt' layout (Key: value header, blank line, x y rows,
micrometres, percent, descending wavelength). It has NOT yet been checked
against real ECOSTRESS files; re-run preprocessing once data/raw/ecostress exists.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from datasets import Spectrum, load_ecostress, load_munsell, resample, munsell_hue_split  # noqa: E402

SYNTH = """Name: Synthetic test material
Type: Mineral
Class: Silicate
Subclass: Test
Particle Size: 125-500 um
Sample No.: test-001
Owner: JHU
Wavelength Range: VSWIR
Origin: synthetic
Collection Date: N/A
Description: synthetic file for parser test
Measurement: Directional (10 Degree) Hemispherical Reflectance
First Column: X
Second Column: Y
X Units: Wavelength (micrometers)
Y Units: Reflectance (percent)
First X Value: 2.5
Last X Value: 0.35
Number of X Values: {n}
Additional Information: None

{rows}
"""


def test_ecostress_parser(tmp_path=None):
    tmp = Path(tmp_path) if tmp_path else ROOT / "data" / "raw" / "_synthetic_test"
    tmp.mkdir(parents=True, exist_ok=True)
    x = np.arange(2.5, 0.349, -0.001)                     # descending, micrometres
    y = 100 * (0.2 + 0.3 * np.exp(-((x - 0.55) / 0.05) ** 2))  # percent
    rows = "\n".join(f"{a:.4f}\t{b:.4f}" for a, b in zip(x, y))
    (tmp / "mineral.silicate.test.synthetic.vswir.test-001.jhu.becknic.spectrum.txt").write_text(
        SYNTH.format(n=x.size, rows=rows))
    spectra, rejected = load_ecostress(tmp)
    assert len(spectra) == 1 and not rejected
    s = spectra[0]
    assert np.all(np.diff(s.wl_nm) > 0) and abs(s.wl_nm[0] - 350) < 1e-6
    r, status = resample(s)
    assert status == "ok"
    g = np.arange(380, 781, 5)
    expect = 0.2 + 0.3 * np.exp(-((g / 1000 - 0.55) / 0.05) ** 2)
    assert np.abs(r - expect).max() < 2e-3                # box filter vs point value of a smooth bump


def test_coverage_rule():
    wl = np.arange(400, 801, 1.0)
    s = Spectrum("x", "x", "x", wl, np.full(wl.size, 0.5))
    assert resample(s)[0] is None
    r, st = resample(s, edge_ext_nm=20)
    assert st == "ok (edge-extended)" and np.allclose(r, 0.5)


def test_munsell():
    m = load_munsell()
    assert len(m) == 1269
    assert len({s.group for s in m}) == 40
    assert len(munsell_hue_split([s.group.split(":")[1] for s in m])) == 8


if __name__ == "__main__":
    test_ecostress_parser(); test_coverage_rule(); test_munsell()
    print("all dataset tests passed")
