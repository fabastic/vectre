"""Download the openly-fetchable raw data and verify checksums.

Fetched automatically (publisher-provided MD5 checked):
  * CIE 1931 2deg colour-matching functions, 1 nm   (CIE, DOI 10.25039/CIE.DS.xvudnb9b, CC BY-SA 4.0)
  * CIE standard illuminant D65, 1 nm               (CIE, DOI 10.25039/CIE.DS.hjfjmt59, CC BY-SA 4.0)
  * Munsell colors matt (spectrophotometer measured), UEF / Univ. of Joensuu,
    Zenodo mirror record 3269912 (original host cs.uef.fi was unreachable from
    here on 2026-10-10; the Zenodo urls.txt lists the original cs.uef.fi URLs
    and identical MD5s).
  * Sharma, Wu & Dalal (2005) CIEDE2000 test data (34 pairs), used by tests only.

NOT fetched (must be supplied by the user, see data/README.md):
  * ECOSTRESS Spectral Library v1.0 (includes ASTER library v2.0), JPL.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

# (relative destination, url, md5)
FILES = [
    ("cie/CIE_xyz_1931_2deg.csv",
     "https://files.cie.co.at/Publications-datasets/CIE_xyz_1931_2deg.csv",
     "17cca777db64b17170f06f67ce9d3ab7"),
    ("cie/CIE_std_illum_D65.csv",
     "https://files.cie.co.at/Publications-datasets/CIE_std_illum_D65.csv",
     "03d4eb9b837c60671627c946fb534deb"),
    # Phase 1.5 (Task A): illuminant A. NOTE: the CIE web page lists MD5
    # 6c33a1c3...; the file served on 2026-10-10 matches the MD5/SHA-256 in its
    # own metadata revision 2 (below) and its published column-sum validation.
    ("cie/CIE_std_illum_A_1nm.csv",
     "https://files.cie.co.at/Publications-datasets/CIE_std_illum_A_1nm.csv",
     "ed0e4effb55d82b950c0912b6278a9d1"),
    ("cie/CIE_std_illum_A_1nm.csv_metadata_v2.json",
     "https://files.cie.co.at/Publications-datasets/CIE_std_illum_A_1nm.csv_metadata_v2.json", None),
    # FL1..FL12, FL3.1..FL3.15 (CIE 015:2018 tables 10.1-10.3), DOI 10.25039/CIE.DS.54hy6srn
    ("cie/CIE_illum_FLs_1nm.csv",
     "https://files.cie.co.at/Publications-datasets/CIE_illum_FLs_1nm.csv",
     "77df774b47c2de724211d5f26592759e"),
    # Task B: CIE 224:2017 99 colour evaluation samples, 1 nm, DOI 10.25039/CIE.DS.8svs5rqd
    ("cie/CIE_srf_cfi_1nm.csv",
     "https://files.cie.co.at/Publications-datasets/CIE_srf_cfi_1nm.csv",
     "5f8f0b2e6a30a8630bda424b85a1806d"),
    ("munsell_uef/munsell380_800_1.asc.gz",
     "https://zenodo.org/records/3269912/files/munsell380_800_1.asc.gz?download=1",
     "0889e8b580c23589ae6cb89f9f4035e5"),
    ("munsell_uef/README.txt",
     "https://zenodo.org/records/3269912/files/README.txt?download=1",
     "003c7c010f7eeda50b7d2984405e3290"),
    # No publisher MD5 for this file; None = record hash but don't enforce.
    ("sharma/ciede2000testdata.txt",
     "https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/dataNprograms/ciede2000testdata.txt",
     None),
]


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    ok = True
    for rel, url, want in FILES:
        dst = RAW / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            print(f"downloading {url}")
            urllib.request.urlretrieve(url, dst)
        got = md5(dst)
        status = "ok" if want is None or got == want else "MD5 MISMATCH"
        ok &= status == "ok"
        print(f"  {rel:45s} md5={got} {status}")
    eco = RAW / "ecostress"
    n_eco = len(list(eco.rglob("*.spectrum.txt"))) if eco.exists() else 0
    print(f"ECOSTRESS spectrum files present: {n_eco}"
          + ("" if n_eco else "  (optional; see data/README.md)"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
