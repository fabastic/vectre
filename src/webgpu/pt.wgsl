// Vectre Phase 2: progressive path tracer, one invocation per pixel, spp_chunk samples per dispatch.
// Integrator contract identical to the CPU reference (src/phase2_scene.py):
//   <= max_bounces scattering vertices, NEE to the quad light at every vertex,
//   emission from BSDF-sampled hits only for camera rays, cosine sampling, no RR.
// Modes:
//   0 = RGB: albedo = linear sRGB under D65, light = linear sRGB of the light's XYZ.
//   1 = spectral hero-4lambda (Wilkie et al. 2014): 4 stratified wavelengths per sample from a
//       light-aware pdf ~ (xbar+ybar+zbar)*E on the 1 nm grid; reflectance by Jakob & Hanika
//       (2019) sigmoid-quadratic uplift of the SAME sRGB albedo, coefficients from a 3D LUT.
//   2 = spectral hero-4lambda with the MEASURED material spectra (validation of the renderer
//       itself against the CPU reference; not available to an RGB-authored pipeline).

const PI: f32 = 3.14159265358979;
const EPS: f32 = 1e-4;
const NL: u32 = 401u;

struct Params {
  res: u32, sample_base: u32, spp_chunk: u32, seed: u32,
  mode: u32, max_bounces: u32, nq: u32, ns: u32,
  lut_res: u32, nmat: u32, pad0: u32, pad1: u32,
  cam_pos: vec4f, cam_fwd: vec4f, cam_right: vec4f, cam_up: vec4f,   // cam_up.w = tan(fov/2)
  lp0: vec4f, lu: vec4f, lv: vec4f, ln: vec4f,                       // ln.w = light area
  light_rgb: vec4f,
};
struct Quad { p0: vec4f, u: vec4f, v: vec4f, n: vec4f };              // p0.w = material id
struct Sphere { cr: vec4f, m: vec4f };                                 // m.x = material id

@group(0) @binding(0) var<uniform> P: Params;
@group(0) @binding(1) var<storage, read> quads: array<Quad>;
@group(0) @binding(2) var<storage, read> spheres: array<Sphere>;
@group(0) @binding(3) var<storage, read> mat_rgb: array<vec4f>;
@group(0) @binding(4) var<storage, read> lut: array<vec4f>;            // lut_res^3, index (b*R+g)*R+r
@group(0) @binding(5) var<storage, read> cmf: array<vec4f>;            // 401 x (xbar,ybar,zbar,0)
@group(0) @binding(6) var<storage, read> spec: array<vec4f>;           // 401 x (E, pdf, cdf, 0)
@group(0) @binding(7) var<storage, read> mat_spec: array<f32>;         // nmat x 401 (mode 2 only)
@group(0) @binding(8) var<storage, read_write> accum: array<vec4f>;    // res^2 x (sum3, count)

var<private> rng: u32;

fn pcg(v: u32) -> u32 {
  let s = v * 747796405u + 2891336453u;
  let w = ((s >> ((s >> 28u) + 4u)) ^ s) * 277803737u;
  return (w >> 22u) ^ w;
}
fn rnd() -> f32 { rng = pcg(rng); return f32(rng >> 8u) * (1.0 / 16777216.0); }

struct Hit { t: f32, kind: i32, idx: u32 };   // kind: -1 miss, 0 quad, 1 sphere, 2 light

fn intersect(o: vec3f, d: vec3f) -> Hit {
  var h = Hit(1e30, -1, 0u);
  for (var k = 0u; k <= P.nq; k++) {
    var p0: vec3f; var u: vec3f; var v: vec3f; var n: vec3f;
    if (k < P.nq) { let q = quads[k]; p0 = q.p0.xyz; u = q.u.xyz; v = q.v.xyz; n = q.n.xyz; }
    else { p0 = P.lp0.xyz; u = P.lu.xyz; v = P.lv.xyz; n = P.ln.xyz; }
    let denom = dot(d, n);
    if (abs(denom) < 1e-12) { continue; }
    let t = dot(p0 - o, n) / denom;
    if (t < EPS || t >= h.t) { continue; }
    let rel = o + t * d - p0;
    let a = dot(rel, u) / dot(u, u);
    let b = dot(rel, v) / dot(v, v);
    if (a < 0.0 || a > 1.0 || b < 0.0 || b > 1.0) { continue; }
    h = Hit(t, select(2, 0, k < P.nq), k);
  }
  for (var k = 0u; k < P.ns; k++) {
    let s = spheres[k].cr;
    let oc = o - s.xyz;
    let bq = dot(oc, d);
    let c = dot(oc, oc) - s.w * s.w;
    let disc = bq * bq - c;
    if (disc < 0.0) { continue; }
    let sq = sqrt(disc);
    var t = -bq - sq;
    if (t < EPS) { t = -bq + sq; }
    if (t < EPS || t >= h.t) { continue; }
    h = Hit(t, 1, k);
  }
  return h;
}

fn sample_cdf(u: f32) -> u32 {     // first index with cdf > u (numpy searchsorted side='right')
  var lo = 0u; var hi = NL - 1u;
  while (lo < hi) {
    let mid = (lo + hi) / 2u;
    if (spec[mid].z > u) { hi = mid; } else { lo = mid + 1u; }
  }
  return lo;
}

fn lut_coeffs(rgb: vec3f) -> vec3f {
  let R = P.lut_res;
  let p = clamp(rgb, vec3f(0.0), vec3f(1.0)) * f32(R - 1u);
  let i0 = min(vec3u(floor(p)), vec3u(R - 2u));
  let f = p - vec3f(i0);
  var c = vec3f(0.0);
  for (var k = 0u; k < 8u; k++) {
    let o = vec3u(k & 1u, (k >> 1u) & 1u, (k >> 2u) & 1u);
    let w = select(1.0 - f.x, f.x, o.x == 1u) * select(1.0 - f.y, f.y, o.y == 1u) * select(1.0 - f.z, f.z, o.z == 1u);
    let i = i0 + o;
    c += w * lut[(i.z * R + i.y) * R + i.x].xyz;
  }
  return c;
}

fn jh(c: vec3f, wl: u32) -> f32 {
  let x = f32(wl) / 400.0;                   // (lambda - 380) / 400, lambda = 380 + index
  let z = (c.x * x + c.y) * x + c.z;
  return 0.5 + 0.5 * z * inverseSqrt(1.0 + z * z);
}

fn reflectance(m: u32, wl: vec4u) -> vec4f {
  if (P.mode == 0u) { return vec4f(mat_rgb[m].xyz, 0.0); }
  if (P.mode == 1u) {
    let c = lut_coeffs(mat_rgb[m].xyz);
    return vec4f(jh(c, wl.x), jh(c, wl.y), jh(c, wl.z), jh(c, wl.w));
  }
  let b = m * NL;
  return vec4f(mat_spec[b + wl.x], mat_spec[b + wl.y], mat_spec[b + wl.z], mat_spec[b + wl.w]);
}

fn emission(wl: vec4u) -> vec4f {
  if (P.mode == 0u) { return vec4f(P.light_rgb.xyz, 0.0); }
  return vec4f(spec[wl.x].x, spec[wl.y].x, spec[wl.z].x, spec[wl.w].x);
}

fn trace(o_in: vec3f, d_in: vec3f, wl: vec4u) -> vec4f {
  var o = o_in; var d = d_in;
  var T = vec4f(1.0); var L = vec4f(0.0);
  let Le = emission(wl);
  for (var depth = 0u; depth < P.max_bounces; depth++) {
    let h = intersect(o, d);
    if (h.kind < 0) { break; }
    if (h.kind == 2) {
      if (depth == 0u && dot(d, P.ln.xyz) < 0.0) { L += T * Le; }
      break;
    }
    let p = o + h.t * d;
    var n: vec3f; var m: u32;
    if (h.kind == 0) { n = quads[h.idx].n.xyz; m = u32(quads[h.idx].p0.w); }
    else { let s = spheres[h.idx]; n = (p - s.cr.xyz) / s.cr.w; m = u32(s.m.x); }
    if (dot(n, d) > 0.0) { n = -n; }
    let R = reflectance(m, wl);
    // next-event estimation: uniform area sampling of the light quad
    let a = rnd(); let b = rnd();
    let ld = P.lp0.xyz + a * P.lu.xyz + b * P.lv.xyz - p;
    let dist2 = dot(ld, ld); let dist = sqrt(dist2); let wi = ld / dist;
    let cosx = dot(n, wi); let cosl = -dot(P.ln.xyz, wi);
    if (cosx > 0.0 && cosl > 0.0) {
      let sh = intersect(p + n * EPS, wi);
      if (sh.kind == 2 && sh.t > dist - 1e-3) {
        L += T * R * Le * (cosx * cosl / dist2 * P.ln.w / PI);
      }
    }
    // cosine-weighted continuation: BRDF*cos/pdf = R
    let u1 = rnd(); let u2 = rnd();
    let r = sqrt(u1); let phi = 2.0 * PI * u2;
    let tv = select(vec3f(1.0, 0.0, 0.0), vec3f(0.0, 1.0, 0.0), abs(n.x) > 0.9);
    let bx = normalize(cross(n, tv)); let cy = cross(n, bx);
    d = normalize(r * cos(phi) * bx + r * sin(phi) * cy + sqrt(max(0.0, 1.0 - u1)) * n);
    o = p + n * EPS;
    T *= R;
  }
  return L;
}

@compute @workgroup_size(8, 8)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  if (gid.x >= P.res || gid.y >= P.res) { return; }
  let pix = gid.y * P.res + gid.x;
  var acc = vec3f(0.0);
  for (var s = 0u; s < P.spp_chunk; s++) {
    rng = pcg(pix ^ pcg((P.sample_base + s) ^ pcg(P.seed)));
    var wl = vec4u(0u); var ww = vec4f(0.0);
    if (P.mode != 0u) {
      let u0 = rnd();
      for (var i = 0u; i < 4u; i++) {
        var u = u0 + f32(i) * 0.25;
        if (u >= 1.0) { u -= 1.0; }
        let idx = sample_cdf(u);
        wl[i] = idx;
        ww[i] = 1.0 / (4.0 * spec[idx].y);
      }
    }
    let px = (2.0 * (f32(gid.x) + rnd()) / f32(P.res) - 1.0) * P.cam_up.w;
    let py = (1.0 - 2.0 * (f32(gid.y) + rnd()) / f32(P.res)) * P.cam_up.w;
    let d = normalize(P.cam_fwd.xyz + px * P.cam_right.xyz + py * P.cam_up.xyz);
    let L = trace(P.cam_pos.xyz, d, wl);
    if (P.mode == 0u) { acc += L.xyz; }
    else {
      acc += cmf[wl.x].xyz * (L.x * ww.x) + cmf[wl.y].xyz * (L.y * ww.y)
           + cmf[wl.z].xyz * (L.z * ww.z) + cmf[wl.w].xyz * (L.w * ww.w);
    }
  }
  let prev = accum[pix];
  accum[pix] = vec4f(prev.xyz + acc, prev.w + f32(P.spp_chunk));
}
