// Display pass: accumulation buffer -> exposure -> tonemap -> sRGB OETF.
// Tonemaps (formulas identical to src/tonemap.py):
//   0 clip, 1 per-channel Reinhard, 2 max-RGB hue-preserving (default), 3 Oklch chroma-preserving.

struct D {
  res: u32, mode: u32, tonemap: u32, pad: u32,
  exposure: f32, p1: f32, p2: f32, p3: f32,
  x2r0: vec4f, x2r1: vec4f, x2r2: vec4f,     // XYZ (white Y=1) -> linear sRGB, rows
  ycoef: vec4f,                              // luminance weights of linear sRGB
};
@group(0) @binding(0) var<uniform> Dp: D;
@group(0) @binding(1) var<storage, read> accum: array<vec4f>;

@vertex fn vs(@builtin(vertex_index) i: u32) -> @builtin(position) vec4f {
  var p = array<vec2f, 3>(vec2f(-1.0, -1.0), vec2f(3.0, -1.0), vec2f(-1.0, 3.0));
  return vec4f(p[i], 0.0, 1.0);
}

fn cbrt_s(x: f32) -> f32 { return sign(x) * pow(abs(x), 1.0 / 3.0); }
fn to_oklab(c: vec3f) -> vec3f {
  let l = 0.4122214708 * c.r + 0.5363325363 * c.g + 0.0514459929 * c.b;
  let m = 0.2119034982 * c.r + 0.6806995451 * c.g + 0.1073969566 * c.b;
  let s = 0.0883024619 * c.r + 0.2817188376 * c.g + 0.6299787005 * c.b;
  let l_ = cbrt_s(l); let m_ = cbrt_s(m); let s_ = cbrt_s(s);
  return vec3f(0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
               1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
               0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_);
}
fn from_oklab(c: vec3f) -> vec3f {   // Ottosson's published inverse
  let l_ = c.x + 0.3963377774 * c.y + 0.2158037573 * c.z;
  let m_ = c.x - 0.1055613458 * c.y - 0.0638541728 * c.z;
  let s_ = c.x - 0.0894841775 * c.y - 1.2914855480 * c.z;
  let l = l_ * l_ * l_; let m = m_ * m_ * m_; let s = s_ * s_ * s_;
  return vec3f(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
              -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
              -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s);
}
fn in_gamut(c: vec3f) -> bool { return all(c >= vec3f(-1e-6)) && all(c <= vec3f(1.0 + 1e-6)); }

fn tonemap(x: vec3f) -> vec3f {
  if (Dp.tonemap == 0u) { return clamp(x, vec3f(0.0), vec3f(1.0)); }
  if (Dp.tonemap == 1u) { let p = max(x, vec3f(0.0)); return p / (1.0 + p); }
  if (Dp.tonemap == 2u) {
    let p = max(x, vec3f(0.0));
    let m = max(p.r, max(p.g, p.b));
    return p / (1.0 + m);
  }
  let Y = max(dot(x, Dp.ycoef.xyz), 0.0);
  let Yp = Y / (1.0 + Y);
  let lab = to_oklab(x);
  let L = max(lab.x, 1e-12);
  let C = length(lab.yz);
  let h = atan2(lab.z, lab.y);
  let Lp = pow(Yp, 1.0 / 3.0);
  var hi = C * Lp / L;
  let dir = vec2f(cos(h), sin(h));
  if (in_gamut(from_oklab(vec3f(Lp, hi * dir)))) { return clamp(from_oklab(vec3f(Lp, hi * dir)), vec3f(0.0), vec3f(1.0)); }
  var lo = 0.0;
  for (var i = 0; i < 24; i++) {
    let mid = 0.5 * (lo + hi);
    if (in_gamut(from_oklab(vec3f(Lp, mid * dir)))) { lo = mid; } else { hi = mid; }
  }
  return clamp(from_oklab(vec3f(Lp, lo * dir)), vec3f(0.0), vec3f(1.0));
}

fn oetf(c: vec3f) -> vec3f {
  return select(1.055 * pow(c, vec3f(1.0 / 2.4)) - 0.055, 12.92 * c, c <= vec3f(0.0031308));
}

@fragment fn fs(@builtin(position) pos: vec4f) -> @location(0) vec4f {
  let pix = u32(pos.y) * Dp.res + u32(pos.x);
  let a = accum[pix];
  let v = a.xyz / max(a.w, 1.0);
  var lin: vec3f;
  if (Dp.mode == 0u) { lin = v; }
  else { lin = vec3f(dot(Dp.x2r0.xyz, v), dot(Dp.x2r1.xyz, v), dot(Dp.x2r2.xyz, v)); }
  return vec4f(oetf(tonemap(lin * Dp.exposure / 100.0)), 1.0);
}
