# Data

Nothing under `data/raw/` or `data/processed/` is committed (see licences below).
Run `python src/fetch_data.py` to download and MD5-check the open files.

| Dataset | Source | Licence / terms (as checked 2026-10-10) | Fetched automatically? |
|---|---|---|---|
| Munsell colors matt (spectrophotometer), 1269 chips, 380–800 nm @ 1 nm | Univ. of Eastern Finland (formerly Joensuu) spectral database, page `sites.uef.fi/spectral/?p=405`; mirrored on Zenodo record 3269912 (same MD5s as the original `cs.uef.fi` files) | UEF page: they "will not grant licenses for commercial use for this dataset". Zenodo: "License Not Specified". **Treat as research/non-commercial only.** Cite the lab's general reference (see the UEF databases page) | Yes (from Zenodo; `cs.uef.fi` timed out from here) |
| CIE 1931 2° colour-matching functions, 1 nm | CIE dataset, DOI 10.25039/CIE.DS.xvudnb9b (from CIE 018:2019 Table 6) | CC BY-SA 4.0 (from the CIE metadata JSON) | Yes, MD5 `17cca777…` verified |
| CIE standard illuminant D65, 1 nm | CIE dataset, DOI 10.25039/CIE.DS.hjfjmt59 (from ISO/CIE 11664-2:2022 Table B.1) | CC BY-SA 4.0 | Yes, MD5 `03d4eb9b…` verified |
| CIEDE2000 test data (34 pairs) | Sharma, Wu & Dalal (2005), `hajim.rochester.edu/ece/sites/gsharma/ciede2000/` | Published test data; used only by tests | Yes |
| CIE standard illuminant A, 1 nm | CIE dataset, DOI 10.25039/CIE.DS.8jsxjrsn | CC BY-SA 4.0. The MD5 on the CIE web page (`6c33a1c3…`) does **not** match the served file; the file matches the MD5/SHA-256 in its metadata revision 2 (`ed0e4eff…`) and its published column-sum validation | Yes |
| CIE fluorescent illuminants FL1–FL12, FL3.1–FL3.15, 1 nm | CIE dataset, DOI 10.25039/CIE.DS.54hy6srn (CIE 015:2018 Tables 10.1–10.3) | CC BY-SA 4.0 | Yes, MD5 `77df774b…` verified |
| CIE 224:2017 99 colour-evaluation samples, 1 nm | CIE dataset, DOI 10.25039/CIE.DS.8svs5rqd | CC BY-SA 4.0. **Shippable with attribution + share-alike** | Yes, MD5 `5f8f0b2e…` verified |
| USGS Spectral Library v7 (splib07) | USGS data release, DOI 10.5066/F7RR1WDJ (ScienceBase item 5807a2a2e4b0841e59e3a18d) | Public domain (US Government work, per the USGS download information) | **No.** ScienceBase served a bot challenge to scripted requests. Optional: download it manually; a loader needs writing once the format is seen |
| **ECOSTRESS Spectral Library v1.0** (includes ASTER library v2.0) | JPL, `https://speclib.jpl.nasa.gov/download` | "Copyright © 2017, California Institute of Technology. ALL RIGHTS RESERVED." Citation requested: Meerdink et al. (2019) *Remote Sens. Environ.* 230:111196 and Baldridge et al. (2009) *Remote Sens. Environ.* 113:711–715. No open licence found; ask JPL (contact listed on the site) before redistributing anything derived from it | **No: you need to supply it** |

## What I need from you: ECOSTRESS

1. Go to https://speclib.jpl.nasa.gov/download and order **"ALL Spectra (6139 files)"**.
   The site uses a cart/order flow, which I didn't complete for you. I filter out
   unusable files myself (thermal-IR only, transmittance, or no visible coverage).
2. Unpack the delivered archive so the `*.spectrum.txt` files are anywhere under
   `data/raw/ecostress/`. Subfolders are fine, since the loader searches recursively.
3. Run:
   ```
   python src/fetch_data.py        # reports how many ECOSTRESS files it sees
   python src/preprocess.py        # strict 380–780 coverage
   ```
   `results/data_summary.json` then lists survivors under **both** the strict policy
   and a ≤20 nm edge-extension policy, so you can make the coverage decision.

Expected file format (what `datasets.parse_ecostress_file` handles): a `Key: value`
header including `Name`, `Type`, `Class`, `Sample No.`, `X Units` (e.g.
"Wavelength (micrometers)") and `Y Units` (e.g. "Reflectance (percent)"), then
whitespace-separated `x y` rows, in any order. The parser is tested only on a
synthetic file built to that description, so the first real run needs checking.
