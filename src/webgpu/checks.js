// Harness integrity checks (pure functions, unit-tested in Node: tests/js/checks.test.mjs).

// PCG hash and the per-sample seeding used in pt.wgsl (kept in sync; a static test checks the WGSL text).
export const pcg = (v) => {
  const s = (Math.imul(v >>> 0, 747796405) + 2891336453) >>> 0;
  const w = Math.imul(((s >>> ((s >>> 28) + 4)) ^ s) >>> 0, 277803737) >>> 0;
  return ((w >>> 22) ^ w) >>> 0;
};
export const seedState = (seed, sampleIdx, pix, res) =>
  pcg((pcg(seed) + Math.imul(sampleIdx, res * res) + pix) >>> 0);
export const seedStateXorLegacy = (seed, sampleIdx, pix) => pcg((pix ^ pcg((sampleIdx ^ pcg(seed)) >>> 0)) >>> 0);

// Every pixel must have accumulated exactly `spp` samples (catches dropped dispatches,
// device loss, failed clears, partial readbacks).
export function checkAccumCounts(accum, spp) {
  let bad = 0, nonfinite = 0;
  for (let i = 0; i < accum.length; i += 4) {
    if (accum[i + 3] !== spp) bad++;
    if (!Number.isFinite(accum[i]) || !Number.isFinite(accum[i + 1]) || !Number.isFinite(accum[i + 2])) nonfinite++;
  }
  if (bad || nonfinite) throw new Error(`accumulation check failed: ${bad} pixels with count != ${spp}, ${nonfinite} non-finite`);
  return true;
}

// Reference must be the converged render: right size, and metadata (written by
// render_reference.py) must report the expected resolution and at least minSpp samples.
export function checkReference(refXYZ, mask, meta, res, minSpp) {
  const n = res * res;
  if (refXYZ.length !== 3 * n) throw new Error(`reference has ${refXYZ.length / 3} px, expected ${n}`);
  if (mask.length !== n) throw new Error(`mask has ${mask.length} px, expected ${n}`);
  if (!meta || meta.res !== res) throw new Error(`reference metadata missing or res mismatch: ${JSON.stringify(meta)}`);
  if (!(meta.spp >= minSpp)) throw new Error(`reference spp ${meta.spp} < required ${minSpp} (placeholder/unfinished?)`);
  for (let i = 0; i < refXYZ.length; i++) if (!Number.isFinite(refXYZ[i])) throw new Error("reference has non-finite values");
  return true;
}

// Pixels to score: not the emitter, and not background misses (reference exactly black),
// which would otherwise dilute the mean.
export function scoringMask(refXYZ, emitterMask) {
  const m = new Uint8Array(emitterMask.length);
  for (let i = 0; i < m.length; i++) {
    const black = refXYZ[3 * i] === 0 && refXYZ[3 * i + 1] === 0 && refXYZ[3 * i + 2] === 0;
    m[i] = emitterMask[i] || black ? 1 : 0;   // 1 = excluded (same convention as the emitter mask)
  }
  return m;
}
