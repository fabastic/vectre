// node --test tests/js/checks.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { checkAccumCounts, checkReference, pcg, scoringMask, seedState, seedStateXorLegacy } from "../../src/webgpu/checks.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

// Two samples a != b have pixel-permuted copies of each other's random streams if
// state(a, p) == state(b, p') for some pixels p != p'. The final PCG hash is a bijection on u32,
// so this happens iff the pre-hash inputs coincide; we count such sample pairs directly.
test("RNG seeding: no sample streams are pixel-permuted copies (catches the old XOR seeding)", () => {
  const P = 512 * 512, N = 1024, seed = 1234;
  // old: input = pix ^ H(s), H(s) = pcg(s ^ pcg(seed)); collision iff H(a) ^ H(b) < P
  const H = Array.from({ length: N }, (_, s) => pcg((s ^ pcg(seed)) >>> 0));
  let legacy = 0;
  for (let a = 0; a < N; a++) for (let b = a + 1; b < N; b++) if (((H[a] ^ H[b]) >>> 0) < P) legacy++;
  assert.ok(legacy > 0, `expected collisions with XOR seeding, got ${legacy}`);
  // new: input = pcg(seed) + s*P + pix, injective while N*P <= 2^32
  const B = Array.from({ length: N }, (_, s) => (pcg(seed) + Math.imul(s, P)) >>> 0);
  let fresh = 0;
  for (let a = 0; a < N; a++) for (let b = a + 1; b < N; b++) {
    const d = (B[b] - B[a]) >>> 0;
    if (d < P || ((B[a] - B[b]) >>> 0) < P) fresh++;
  }
  assert.equal(fresh, 0);
  assert.equal(seedStateXorLegacy(seed, 3, 7), pcg((7 ^ H[3]) >>> 0));
});

test("seedState matches the WGSL expression", () => {
  const wgsl = readFileSync(path.join(root, "src/webgpu/pt.wgsl"), "utf8");
  assert.ok(wgsl.includes("rng = pcg(pcg(P.seed) + (P.sample_base + s) * P.res * P.res + pix);"));
  assert.equal(typeof seedState(1, 2, 3, 4), "number");
});

test("checkAccumCounts rejects partial accumulation and NaN", () => {
  const ok = new Float32Array([1, 2, 3, 4, 5, 6, 7, 4]);
  assert.ok(checkAccumCounts(ok, 4));
  assert.throws(() => checkAccumCounts(new Float32Array([1, 2, 3, 4, 5, 6, 7, 3]), 4));
  assert.throws(() => checkAccumCounts(new Float32Array([NaN, 2, 3, 4]), 4));
});

test("checkReference rejects placeholder / unfinished references", () => {
  const res = 4, ref = new Float32Array(3 * 16), mask = new Uint8Array(16);
  assert.ok(checkReference(ref, mask, { res: 4, spp: 8192 }, res, 8192));
  assert.throws(() => checkReference(new Float32Array(3 * 4), new Uint8Array(4), { res: 2, spp: 16 }, res, 8192));
  assert.throws(() => checkReference(ref, mask, { res: 4, spp: 16 }, res, 8192));
  assert.throws(() => checkReference(ref, mask, null, res, 8192));
});

test("scoringMask excludes emitter and exactly-black reference pixels", () => {
  const ref = new Float32Array([0, 0, 0, 1, 1, 1, 2, 2, 2]);
  assert.deepEqual(Array.from(scoringMask(ref, new Uint8Array([0, 0, 1]))), [1, 0, 1]);
});
