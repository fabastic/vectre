// WebGPU renderer: device setup, buffers, progressive accumulation, display, timing.
// Modes: 0 = RGB, 1 = spectral hero-4λ + Jakob–Hanika LUT uplift, 2 = spectral with measured spectra.

const f32 = (url) => fetch(url).then((r) => { if (!r.ok) throw new Error(url); return r.arrayBuffer(); })
  .then((b) => new Float32Array(b));

export const MODES = { 0: "rgb", 1: "hero4_jh", 2: "hero4_measured" };
export const TONEMAPS = { clip: 0, reinhard_channel: 1, maxrgb: 2, oklch: 3 };

export class Renderer {
  async init(canvas) {
    if (!navigator.gpu) throw new Error("WebGPU not available (navigator.gpu missing)");
    this.adapter = await navigator.gpu.requestAdapter({ powerPreference: "high-performance" });
    if (!this.adapter) throw new Error("no WebGPU adapter");
    this.hasTimestamps = this.adapter.features.has("timestamp-query");
    this.device = await this.adapter.requestDevice({ requiredFeatures: this.hasTimestamps ? ["timestamp-query"] : [] });
    this.device.lost.then((i) => console.error("device lost", i));
    const ai = this.adapter.info || {};   // GPUAdapterInfo fields are getters: copy explicitly
    this.info = { vendor: ai.vendor, architecture: ai.architecture, device: ai.device, description: ai.description };
    this.scene = await fetch("data/scene.json").then((r) => r.json());
    this.res = this.scene.resolution;
    this.cmf = await f32("data/cmf_1nm.bin");
    this.lut = await f32("data/jh_lut.bin");
    this.matSpec = await f32("data/material_spectra.bin");
    this.lights = {};
    for (const s of Object.keys(this.scene.scenes)) this.lights[s] = await f32(`data/light_${s}.bin`);
    this.buffers = {};
    this._createBuffers();
    await this._createPipelines(canvas);
  }

  _buf(name, size, usage, data) {
    const b = this.device.createBuffer({ label: name, size: Math.max(16, Math.ceil(size / 16) * 16), usage, mappedAtCreation: !!data });
    if (data) { new Float32Array(b.getMappedRange()).set(data); b.unmap(); }
    this.buffers[name] = b;
    return b;
  }

  _createBuffers() {
    const S = GPUBufferUsage.STORAGE, C = GPUBufferUsage.COPY_DST, U = GPUBufferUsage.UNIFORM;
    const sc = this.scene;
    const q = [];
    for (const x of sc.quads) q.push(...x.p0, x.mat, ...x.u, 0, ...x.v, 0, ...x.n, 0);
    this._buf("quads", q.length * 4, S, new Float32Array(q));
    const sp = [];
    for (const x of sc.spheres) sp.push(...x.c, x.r, x.mat, 0, 0, 0);
    this._buf("spheres", sp.length * 4, S, new Float32Array(sp));
    const mr = [];
    for (const m of sc.materials) mr.push(...m.rgb, 0);
    this._buf("mat_rgb", mr.length * 4, S, new Float32Array(mr));
    this._buf("lut", this.lut.byteLength, S, this.lut);
    const c4 = new Float32Array(401 * 4);
    for (let i = 0; i < 401; i++) c4.set([this.cmf[3 * i], this.cmf[3 * i + 1], this.cmf[3 * i + 2], 0], 4 * i);
    this._buf("cmf", c4.byteLength, S, c4);
    this._buf("spec", 401 * 16, S | C);
    this._buf("mat_spec", this.matSpec.byteLength, S, this.matSpec);
    this._buf("accum", this.res * this.res * 16, S | C | GPUBufferUsage.COPY_SRC);
    this._buf("params", 192, U | C);
    this._buf("dparams", 112, U | C);
    this._buf("readback", this.res * this.res * 16, GPUBufferUsage.MAP_READ | C);
    if (this.hasTimestamps) {
      this.maxQ = 512;
      this.querySet = this.device.createQuerySet({ type: "timestamp", count: this.maxQ });
      this._buf("qresolve", this.maxQ * 8, GPUBufferUsage.QUERY_RESOLVE | GPUBufferUsage.COPY_SRC);
      this._buf("qread", this.maxQ * 8, GPUBufferUsage.MAP_READ | C);
    }
  }

  // Bytes of the buffers a given mode actually binds (readback/query buffers excluded).
  memoryForMode(mode) {
    const b = this.buffers, sz = (n) => b[n].size;
    let t = sz("params") + sz("quads") + sz("spheres") + sz("mat_rgb") + sz("accum");
    // unused bindings are still bound (WebGPU requires all), but count what the mode reads:
    if (mode === 1) t += sz("lut") + sz("cmf") + sz("spec");
    if (mode === 2) t += sz("mat_spec") + sz("cmf") + sz("spec");
    return t;
  }

  async _createPipelines(canvas) {
    const dev = this.device;
    const ptCode = await fetch("pt.wgsl").then((r) => r.text());
    const dCode = await fetch("display.wgsl").then((r) => r.text());
    this.ptModule = dev.createShaderModule({ label: "pt", code: ptCode });
    this.dModule = dev.createShaderModule({ label: "display", code: dCode });
    this.compileInfo = {};
    for (const [k, m] of [["pt.wgsl", this.ptModule], ["display.wgsl", this.dModule]]) {
      const ci = await m.getCompilationInfo();
      this.compileInfo[k] = ci.messages.map((x) => `${x.type} ${x.lineNum}:${x.linePos} ${x.message}`);
      if (ci.messages.some((x) => x.type === "error")) throw new Error(`${k}: ${this.compileInfo[k].join("\n")}`);
    }
    this.ptPipe = await dev.createComputePipelineAsync({ layout: "auto", compute: { module: this.ptModule, entryPoint: "main" } });
    const B = this.buffers;
    this.ptBind = dev.createBindGroup({ layout: this.ptPipe.getBindGroupLayout(0), entries:
      ["params", "quads", "spheres", "mat_rgb", "lut", "cmf", "spec", "mat_spec", "accum"].map((n, i) => ({
        binding: i, resource: { buffer: B[n] } })) });
    this.ctx = canvas.getContext("webgpu");
    this.format = navigator.gpu.getPreferredCanvasFormat();
    this.ctx.configure({ device: dev, format: this.format, alphaMode: "opaque" });
    this.dPipe = await dev.createRenderPipelineAsync({ layout: "auto",
      vertex: { module: this.dModule, entryPoint: "vs" },
      fragment: { module: this.dModule, entryPoint: "fs", targets: [{ format: this.format }] },
      primitive: { topology: "triangle-list" } });
    this.dBind = dev.createBindGroup({ layout: this.dPipe.getBindGroupLayout(0), entries: [
      { binding: 0, resource: { buffer: B.dparams } }, { binding: 1, resource: { buffer: B.accum } }] });
  }

  setScene(name) {
    this.sceneName = name;
    const E = this.lights[name];
    const pdf = new Float64Array(401);
    let sum = 0;
    for (let i = 0; i < 401; i++) { pdf[i] = (this.cmf[3 * i] + this.cmf[3 * i + 1] + this.cmf[3 * i + 2]) * E[i]; sum += pdf[i]; }
    const spec = new Float32Array(401 * 4);
    let cdf = 0;
    for (let i = 0; i < 401; i++) { pdf[i] /= sum; cdf += pdf[i]; spec.set([E[i], pdf[i], i === 400 ? 1.0 : cdf, 0], 4 * i); }
    this.device.queue.writeBuffer(this.buffers.spec, 0, spec);
  }

  _writeParams(mode, sampleBase, chunk, seed) {
    const sc = this.scene, lt = sc.light, cam = sc.camera;
    const ab = new ArrayBuffer(192), u = new Uint32Array(ab), f = new Float32Array(ab);
    u.set([this.res, sampleBase, chunk, seed, mode, sc.max_bounces, sc.quads.length, sc.spheres.length,
      sc.lut_res, sc.materials.length, 0, 0]);
    const v4 = (o, a, w = 0) => f.set([a[0], a[1], a[2], w], o);
    v4(12, cam.pos); v4(16, [0, 0, 1]); v4(20, [1, 0, 0]); v4(24, [0, 1, 0], cam.tan_half_fov);
    const area = Math.hypot(...lt.u) * Math.hypot(...lt.v);
    v4(28, lt.p0); v4(32, lt.u); v4(36, lt.v); v4(40, lt.n, area);
    v4(44, sc.scenes[this.sceneName].light_rgb);
    this.device.queue.writeBuffer(this.buffers.params, 0, ab);
  }

  clear() {
    const enc = this.device.createCommandEncoder();
    enc.clearBuffer(this.buffers.accum);
    this.device.queue.submit([enc.finish()]);
  }

  // Render `spp` samples per pixel from scratch. Returns {gpuMs (timestamp sum or null), wallMs}.
  async render(mode, spp, seed = 1234, chunk = 4) {
    this.clear();
    this.mode = mode;
    const nChunks = Math.ceil(spp / chunk);
    if (this.hasTimestamps && 2 * nChunks > this.maxQ) throw new Error("too many chunks for query set");
    const wg = Math.ceil(this.res / 8);
    await this.device.queue.onSubmittedWorkDone();
    const t0 = performance.now();
    let done = 0, q = 0;
    while (done < spp) {
      const c = Math.min(chunk, spp - done);
      this._writeParams(mode, done, c, seed);
      const enc = this.device.createCommandEncoder();
      const desc = this.hasTimestamps ? { timestampWrites: { querySet: this.querySet, beginningOfPassWriteIndex: q, endOfPassWriteIndex: q + 1 } } : {};
      const pass = enc.beginComputePass(desc);
      pass.setPipeline(this.ptPipe); pass.setBindGroup(0, this.ptBind);
      pass.dispatchWorkgroups(wg, wg); pass.end();
      this.device.queue.submit([enc.finish()]);
      done += c; q += 2;
    }
    await this.device.queue.onSubmittedWorkDone();
    const wallMs = performance.now() - t0;
    let gpuMs = null;
    if (this.hasTimestamps) {
      const enc = this.device.createCommandEncoder();
      enc.resolveQuerySet(this.querySet, 0, q, this.buffers.qresolve, 0);
      enc.copyBufferToBuffer(this.buffers.qresolve, 0, this.buffers.qread, 0, q * 8);
      this.device.queue.submit([enc.finish()]);
      await this.buffers.qread.mapAsync(GPUMapMode.READ, 0, q * 8);
      const t = new BigUint64Array(this.buffers.qread.getMappedRange(0, q * 8).slice(0));
      this.buffers.qread.unmap();
      let ns = 0n;
      for (let i = 0; i < q; i += 2) ns += t[i + 1] - t[i];
      gpuMs = Number(ns) / 1e6;
    }
    return { gpuMs, wallMs, dispatches: nChunks };
  }

  async readAccum() {
    const enc = this.device.createCommandEncoder();
    enc.copyBufferToBuffer(this.buffers.accum, 0, this.buffers.readback, 0, this.res * this.res * 16);
    this.device.queue.submit([enc.finish()]);
    await this.buffers.readback.mapAsync(GPUMapMode.READ);
    const out = new Float32Array(this.buffers.readback.getMappedRange().slice(0));
    this.buffers.readback.unmap();
    return out;
  }

  display(tonemap, exposure) {
    const ab = new ArrayBuffer(112), u = new Uint32Array(ab), f = new Float32Array(ab);
    u.set([this.res, this.mode ?? 0, tonemap, 0]);
    f[4] = exposure;
    const M = this.scene.xyz2rgb;
    f.set([...M[0], 0, ...M[1], 0, ...M[2], 0], 8);
    f.set([...this.scene.rgb2xyz[1], 0], 20);
    this.device.queue.writeBuffer(this.buffers.dparams, 0, ab);
    const enc = this.device.createCommandEncoder();
    const pass = enc.beginRenderPass({ colorAttachments: [{ view: this.ctx.getCurrentTexture().createView(),
      loadOp: "clear", storeOp: "store", clearValue: { r: 0, g: 0, b: 0, a: 1 } }] });
    pass.setPipeline(this.dPipe); pass.setBindGroup(0, this.dBind); pass.draw(3); pass.end();
    this.device.queue.submit([enc.finish()]);
  }
}
