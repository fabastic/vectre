Adapter: {'vendor': 'intel', 'architecture': 'gen-12lp', 'device': '', 'description': ''}; timestamp-query: True; 512² px; max bounces 5; gpu_ms = sum of compute-pass timestamp deltas.


**cornell_d65**: mean ΔE00 / RMSE vs CPU reference (emitter and background pixels excluded)

| mode | 1 spp | 4 spp | 16 spp | 64 spp |
|---|---|---|---|---|
| RGB | 12.88 / 0.4976 | 7.24 / 0.2245 | 3.77 / 0.1233 | 1.97 / 0.0595 |
| hero-4λ + J&H uplift | 18.27 / 0.5192 | 10.65 / 0.2566 | 5.76 / 0.1300 | 3.00 / 0.0699 |
| hero-4λ, measured spectra (validation) | 17.80 / 0.5191 | 10.61 / 0.2565 | 5.76 / 0.1300 | 2.97 / 0.0699 |

**cornell_nb610**: mean ΔE00 / RMSE vs CPU reference (emitter and background pixels excluded)

| mode | 1 spp | 4 spp | 16 spp | 64 spp |
|---|---|---|---|---|
| RGB | 13.15 / 0.5070 | 7.89 / 0.2405 | 5.65 / 0.1364 | 4.77 / 0.0899 |
| hero-4λ + J&H uplift | 11.02 / 0.5624 | 5.29 / 0.2776 | 2.72 / 0.1441 | 1.53 / 0.0777 |
| hero-4λ, measured spectra (validation) | 10.93 / 0.5623 | 5.14 / 0.2774 | 2.52 / 0.1437 | 1.25 / 0.0770 |

**cornell_f11**: mean ΔE00 / RMSE vs CPU reference (emitter and background pixels excluded)

| mode | 1 spp | 4 spp | 16 spp | 64 spp |
|---|---|---|---|---|
| RGB | 12.90 / 0.4156 | 7.46 / 0.1927 | 4.52 / 0.1026 | 3.24 / 0.0581 |
| hero-4λ + J&H uplift | 17.33 / 0.4786 | 10.10 / 0.2346 | 5.64 / 0.1220 | 3.34 / 0.0651 |
| hero-4λ, measured spectra (validation) | 17.48 / 0.4781 | 10.08 / 0.2342 | 5.34 / 0.1218 | 2.72 / 0.0649 |

**Cost**: GPU time in ms, median (min–max) over repeated identical renders (timestamp queries, summed over dispatches); bound buffer memory

| scene | mode | buffer bytes | 1 spp ms | 4 spp ms | 16 spp ms | 64 spp ms | ms per spp (at max spp) |
|---|---|---|---|---|---|---|---|
| cornell_d65 | RGB | 4,195,008 | 5.8 (3.5–8.5) | 11.1 (10.4–36.6) | 45.9 (42.2–65.7) | 175.4 (171.7–192.0) | 2.74 |
| cornell_d65 | hero-4λ + J&H uplift | 4,732,128 | 9.2 (9.2–10.1) | 18.7 (15.9–60.2) | 60.6 (57.5–82.2) | 234.5 (230.0–253.8) | 3.66 |
| cornell_d65 | hero-4λ, measured spectra (validation) | 4,217,472 | 6.8 (6.8–6.9) | 29.7 (13.2–40.0) | 56.7 (54.7–86.0) | 219.2 (217.8–234.7) | 3.43 |
| cornell_nb610 | RGB | 4,195,008 | 4.7 (2.9–8.4) | 13.0 (10.4–31.3) | 44.3 (41.9–63.8) | 182.4 (171.7–204.6) | 2.85 |
| cornell_nb610 | hero-4λ + J&H uplift | 4,732,128 | 8.7 (8.7–10.6) | 17.2 (16.8–28.0) | 59.8 (58.2–76.3) | 225.3 (221.8–246.2) | 3.52 |
| cornell_nb610 | hero-4λ, measured spectra (validation) | 4,217,472 | 6.8 (6.8–7.3) | 35.8 (31.1–35.9) | 54.1 (51.8–75.3) | 207.2 (197.7–231.7) | 3.24 |
| cornell_f11 | RGB | 4,195,008 | 6.9 (3.5–10.8) | 15.0 (13.7–31.7) | 45.5 (43.7–63.4) | 178.6 (174.6–198.5) | 2.79 |
| cornell_f11 | hero-4λ + J&H uplift | 4,732,128 | 7.1 (7.1–9.0) | 18.9 (17.7–29.5) | 60.4 (58.1–76.7) | 231.8 (230.8–253.6) | 3.62 |
| cornell_f11 | hero-4λ, measured spectra (validation) | 4,217,472 | 7.6 (7.6–8.3) | 16.3 (12.4–27.9) | 55.3 (53.1–77.5) | 218.1 (212.5–241.8) | 3.41 |

**Mean ΔE00 by first-hit surface at 1024 spp** (GPU image-only render; emitter and background excluded)

| scene | mode | white | red | green | blue | yellow | magenta |
|---|---|---|---|---|---|---|---|
| cornell_d65 | RGB | 0.93 | 0.39 | 0.41 | 1.32 | 0.98 | 0.64 |
| cornell_d65 | hero-4λ + J&H uplift | 1.21 | 0.65 | 0.48 | 1.16 | 0.75 | 1.07 |
| cornell_d65 | hero-4λ, measured spectra (validation) | 1.08 | 0.33 | 0.44 | 0.52 | 0.67 | 0.55 |
| cornell_nb610 | RGB | 1.71 | 9.85 | 4.88 | 9.18 | 6.55 | 3.76 |
| cornell_nb610 | hero-4λ + J&H uplift | 0.41 | 1.37 | 0.60 | 3.61 | 0.54 | 1.57 |
| cornell_nb610 | hero-4λ, measured spectra (validation) | 0.36 | 0.25 | 0.22 | 0.21 | 0.43 | 0.47 |
| cornell_f11 | RGB | 1.75 | 2.90 | 2.52 | 10.21 | 4.05 | 3.45 |
| cornell_f11 | hero-4λ + J&H uplift | 1.53 | 3.45 | 0.97 | 3.92 | 0.99 | 3.75 |
| cornell_f11 | hero-4λ, measured spectra (validation) | 0.91 | 0.32 | 0.54 | 0.56 | 0.73 | 0.50 |