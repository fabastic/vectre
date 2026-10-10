// Benchmark/accuracy harness: every scene x mode x spp, vs the CPU reference.
import { accumToXYZ, compareImages, exposureFromRef, toCSV } from "./metrics.js";
import { MODES } from "./renderer.js";

const SEED = 1234;

async function fetchF32(url) { const r = await fetch(url); if (!r.ok) throw new Error(url); return new Float32Array(await r.arrayBuffer()); }
async function fetchU8(url) { const r = await fetch(url); if (!r.ok) throw new Error(url); return new Uint8Array(await r.arrayBuffer()); }

export async function save(name, body) {
  // Works with src/webgpu/serve.py; silently skipped on a plain static server.
  try { const r = await fetch(`save/${name}`, { method: "POST", body }); return r.ok; } catch { return false; }
}

export async function runHarness(r, { sppList = [1, 4, 16, 64, 1024], modes = [0, 1, 2], scenes = null,
  saveImagesAt = [64, 1024], log = console.log } = {}) {
  const sc = r.scene, white = sc.white_xyz;
  const out = { meta: { date: new Date().toISOString(), userAgent: navigator.userAgent,
    adapter: { vendor: r.info.vendor, architecture: r.info.architecture, device: r.info.device, description: r.info.description },
    timestampQuery: r.hasTimestamps, resolution: r.res, maxBounces: sc.max_bounces, seed: SEED, chunk: 4,
    timing_note: r.hasTimestamps ? "gpu_ms = sum of compute-pass timestamp deltas" :
      "NO timestamp-query: only wall_ms (performance.now around submit..onSubmittedWorkDone), includes CPU/driver overhead",
    compileInfo: r.compileInfo }, rows: [] };
  for (const scene of scenes || Object.keys(sc.scenes)) {
    r.setScene(scene);
    const ref = await fetchF32(`data/ref_${scene}_xyz.bin`);
    const mask = await fetchU8(`data/ref_${scene}_mask.bin`);
    const k = exposureFromRef(ref, mask);
    for (const mode of modes) {
      await r.render(mode, 4, 99);                              // warm-up (pipeline, caches)
      for (const spp of sppList) {
        // Timing: median of `reps` identical renders (same seed => identical image). The iGPU
        // showed large run-to-run variation (clock ramping), so single timings are not reported.
        const reps = spp <= 64 ? 5 : 2;
        const ts = [];
        for (let i = 0; i < reps; i++) ts.push(await r.render(mode, spp, SEED));
        const med = (xs) => { const s = [...xs].sort((a, b) => a - b); return s[s.length >> 1]; };
        const t = { gpuMs: r.hasTimestamps ? med(ts.map((x) => x.gpuMs)) : null, wallMs: med(ts.map((x) => x.wallMs)),
          dispatches: ts[0].dispatches, gpuMin: r.hasTimestamps ? Math.min(...ts.map((x) => x.gpuMs)) : null,
          gpuMax: r.hasTimestamps ? Math.max(...ts.map((x) => x.gpuMs)) : null, reps };
        const acc = await r.readAccum();
        const xyz = accumToXYZ(acc, mode, sc.rgb2xyz);
        const m = compareImages(xyz, ref, mask, k, white);
        const row = { scene, mode: MODES[mode], spp, gpu_ms: t.gpuMs, wall_ms: t.wallMs,
          gpu_ms_per_spp: t.gpuMs == null ? null : t.gpuMs / spp, gpu_ms_min: t.gpuMin, gpu_ms_max: t.gpuMax,
          timing_reps: t.reps, dispatches: t.dispatches,
          buffer_bytes: r.memoryForMode(mode), rmse: m.rmse, mean_dE00: m.meanDE, median_dE00: m.medianDE,
          p95_dE00: m.p95DE, exposure: k };
        out.rows.push(row);
        log(`${scene} ${MODES[mode]} spp=${spp} gpu=${t.gpuMs?.toFixed(1)}ms wall=${t.wallMs.toFixed(1)}ms dE=${m.meanDE.toFixed(3)} rmse=${m.rmse.toFixed(4)}`);
        if (saveImagesAt.includes(spp)) await save(`${scene}_${MODES[mode]}_${spp}spp_xyz.bin`, xyz);
        r.display(2, k);
      }
    }
  }
  await save("results.json", JSON.stringify(out, null, 1));
  await save("results.csv", toCSV(out.rows));
  return out;
}

export function download(name, text, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name; a.click();
}
