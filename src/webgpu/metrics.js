// Image metrics vs the CPU reference. Pure functions, unit-tested in Node (tests/js/).
// CIELAB (CIE 015) and CIEDE2000 (Sharma, Wu & Dalal 2005), ported from src/colorimetry.py.

export function xyzToLab(X, Y, Z, w) {
  const d = 6 / 29;
  const f = (t) => (t > d * d * d ? Math.cbrt(t) : t / (3 * d * d) + 4 / 29);
  const fx = f(X / w[0]), fy = f(Y / w[1]), fz = f(Z / w[2]);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}

export function deltaE2000(lab1, lab2) {
  const [L1, a1, b1] = lab1, [L2, a2, b2] = lab2;
  const rad = Math.PI / 180;
  const C1 = Math.hypot(a1, b1), C2 = Math.hypot(a2, b2);
  const Cb7 = ((C1 + C2) / 2) ** 7;
  const G = 0.5 * (1 - Math.sqrt(Cb7 / (Cb7 + 25 ** 7)));
  const a1p = (1 + G) * a1, a2p = (1 + G) * a2;
  const C1p = Math.hypot(a1p, b1), C2p = Math.hypot(a2p, b2);
  const hue = (b, a) => (a === 0 && b === 0 ? 0 : ((Math.atan2(b, a) / rad) % 360 + 360) % 360);
  const h1p = hue(b1, a1p), h2p = hue(b2, a2p);
  const dLp = L2 - L1, dCp = C2p - C1p;
  const zeroC = C1p * C2p === 0;
  let dhp = h2p - h1p;
  if (dhp > 180) dhp -= 360; else if (dhp < -180) dhp += 360;
  if (zeroC) dhp = 0;
  const dHp = 2 * Math.sqrt(C1p * C2p) * Math.sin((dhp * rad) / 2);
  const Lbp = (L1 + L2) / 2, Cbp = (C1p + C2p) / 2;
  let hbp;
  if (zeroC) hbp = h1p + h2p;
  else if (Math.abs(h1p - h2p) <= 180) hbp = (h1p + h2p) / 2;
  else hbp = h1p + h2p < 360 ? (h1p + h2p + 360) / 2 : (h1p + h2p - 360) / 2;
  const T = 1 - 0.17 * Math.cos((hbp - 30) * rad) + 0.24 * Math.cos(2 * hbp * rad)
    + 0.32 * Math.cos((3 * hbp + 6) * rad) - 0.2 * Math.cos((4 * hbp - 63) * rad);
  const dTheta = 30 * Math.exp(-(((hbp - 275) / 25) ** 2));
  const Cbp7 = Cbp ** 7;
  const RC = 2 * Math.sqrt(Cbp7 / (Cbp7 + 25 ** 7));
  const SL = 1 + (0.015 * (Lbp - 50) ** 2) / Math.sqrt(20 + (Lbp - 50) ** 2);
  const SC = 1 + 0.045 * Cbp, SH = 1 + 0.015 * Cbp * T;
  const RT = -Math.sin(2 * dTheta * rad) * RC;
  return Math.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2 + RT * (dCp / SC) * (dHp / SH));
}

// Exposure used everywhere: reference median Y over non-emitter pixels -> 18 (white = 100).
export function exposureFromRef(refXYZ, mask) {
  const ys = [];
  for (let i = 0; i < mask.length; i++) if (!mask[i]) ys.push(refXYZ[3 * i + 1]);
  ys.sort((a, b) => a - b);
  const n = ys.length;
  const med = n % 2 ? ys[(n - 1) / 2] : 0.5 * (ys[n / 2 - 1] + ys[n / 2]);
  return 18 / med;
}

// test, ref: Float32Array/Array of XYZ triplets (absolute units). Emitter pixels excluded.
// RMSE is over X,Y,Z after exposure, in units of the white (Y_white = 1).
export function compareImages(test, ref, mask, k, white) {
  let se = 0, n = 0;
  const des = [];
  for (let i = 0; i < mask.length; i++) {
    if (mask[i]) continue;
    const t = [test[3 * i] * k, test[3 * i + 1] * k, test[3 * i + 2] * k];
    const r = [ref[3 * i] * k, ref[3 * i + 1] * k, ref[3 * i + 2] * k];
    for (let c = 0; c < 3; c++) { se += ((t[c] - r[c]) / 100) ** 2; n++; }
    des.push(deltaE2000(xyzToLab(...r, white), xyzToLab(...t, white)));
  }
  des.sort((a, b) => a - b);
  const mean = des.reduce((a, b) => a + b, 0) / des.length;
  return { rmse: Math.sqrt(se / n), meanDE: mean, medianDE: des[des.length >> 1],
           p95DE: des[Math.floor(0.95 * (des.length - 1))], pixels: des.length };
}

// accum: Float32Array of vec4 (sum, count). mode 0 = linear sRGB -> XYZ via rgb2xyz; else XYZ.
export function accumToXYZ(accum, mode, rgb2xyz) {
  const n = accum.length / 4, out = new Float32Array(3 * n);
  for (let i = 0; i < n; i++) {
    const c = Math.max(accum[4 * i + 3], 1);
    const v = [accum[4 * i] / c, accum[4 * i + 1] / c, accum[4 * i + 2] / c];
    for (let r = 0; r < 3; r++) {
      out[3 * i + r] = mode === 0 ? rgb2xyz[r][0] * v[0] + rgb2xyz[r][1] * v[1] + rgb2xyz[r][2] * v[2] : v[r];
    }
  }
  return out;
}

export function toCSV(rows) {
  const cols = Object.keys(rows[0]);
  return [cols.join(","), ...rows.map((r) => cols.map((c) => r[c]).join(","))].join("\n");
}
