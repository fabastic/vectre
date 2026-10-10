// node --test tests/js/
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { accumToXYZ, compareImages, deltaE2000, exposureFromRef, xyzToLab } from "../../src/webgpu/metrics.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

test("CIEDE2000 matches all 34 Sharma et al. (2005) pairs", () => {
  const rows = readFileSync(path.join(root, "data/raw/sharma/ciede2000testdata.txt"), "utf8")
    .trim().split(/\r?\n/).map((l) => l.trim().split(/\s+/).map(Number));
  assert.equal(rows.length, 34);
  for (const r of rows) {
    const de = deltaE2000(r.slice(0, 3), r.slice(3, 6));
    assert.ok(Math.abs(de - r[6]) < 5e-5, `${r} -> ${de}`);
    assert.ok(Math.abs(de - deltaE2000(r.slice(3, 6), r.slice(0, 3))) < 1e-10);
  }
});

test("CIELAB of the white is (100, 0, 0) and matches Python fixture", () => {
  const w = [95.04226740613592, 100.0, 108.86103689125933];
  const lab = xyzToLab(...w, w);
  assert.ok(Math.abs(lab[0] - 100) < 1e-9 && Math.abs(lab[1]) < 1e-9 && Math.abs(lab[2]) < 1e-9);
  // dark branch: t below (6/29)^3
  const d = xyzToLab(0.5, 0.4, 0.3, w);
  assert.ok(Math.abs(d[0] - 3.6131) < 1e-3, d);
});

test("compareImages: identical images give zero error; exposure from median", () => {
  const ref = new Float32Array([1, 1, 1, 2, 2, 2, 3, 3, 3, 50, 50, 50]);
  const mask = new Uint8Array([0, 0, 0, 1]);
  const k = exposureFromRef(ref, mask);
  assert.equal(k, 18 / 2);
  const r = compareImages(ref, ref, mask, k, [95.04, 100, 108.86]);
  assert.equal(r.rmse, 0); assert.equal(r.meanDE, 0); assert.equal(r.pixels, 3);
});

test("accumToXYZ divides by count and converts RGB", () => {
  const acc = new Float32Array([2, 4, 6, 2]);
  const I = [[1, 0, 0], [0, 1, 0], [0, 0, 1]];
  assert.deepEqual(Array.from(accumToXYZ(acc, 1, I)), [1, 2, 3]);
  const M = [[0, 1, 0], [1, 0, 0], [0, 0, 2]];
  assert.deepEqual(Array.from(accumToXYZ(acc, 0, M)), [2, 1, 6]);
});
