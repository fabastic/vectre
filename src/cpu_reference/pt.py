"""CPU spectral reference path tracer (Python + Numba), Phase 2 Task 1.

Choice: Python+Numba (no Rust/C++ toolchain on this machine). Independent code from the
WebGPU renderer; the shared part is only the scene definition (src/phase2_scene.py).

Spectral model: each camera sample carries NW wavelengths drawn on the 1 nm grid
(380..780) by stratified inverse-CDF sampling (u + i/NW) from a light-aware pdf
p(l) ~ (xbar+ybar+zbar)(l) * E(l); estimator XYZ += cmf(l_i) L(l_i) / p(l_i) / NW.
This is unbiased for the 1 nm sum. full_spectrum=True instead carries all 401
wavelengths with weight 1 (exact spectral integration, slow, used in tests).
Reflectances are the MEASURED 1 nm material spectra (ground truth).

Integrator (contract shared with the GPU, see phase2_scene.py):
  nee=True : for d < MAX_BOUNCES: hit; if light -> add Le only when d == 0, stop;
             NEE (uniform area sampling of the light quad, shadow ray); cosine-sample, T *= R.
  nee=False: pure path tracing (emission counted at every hit), same max path length.
             Used to cross-check NEE. surf_emit > 0 makes EVERY surface emit (furnace test).
"""
from __future__ import annotations

import math

import numba as nb
import numpy as np

EPS = 1e-6


@nb.njit(inline="always")
def rnd(state):
    # xorshift64* -> float in [0,1)
    x = state[0]
    x ^= x >> np.uint64(12)
    x ^= x << np.uint64(25)
    x ^= x >> np.uint64(27)
    state[0] = x
    return float((x * np.uint64(2685821657736338717)) >> np.uint64(11)) * (1.0 / 9007199254740992.0)


@nb.njit(inline="always")
def seed_state(a, b, c):
    # splitmix64 of a combined key
    z = np.uint64(a) * np.uint64(0x9E3779B97F4A7C15) ^ np.uint64(b) * np.uint64(0xBF58476D1CE4E5B9) \
        ^ np.uint64(c) * np.uint64(0x94D049BB133111EB) ^ np.uint64(0x2545F4914F6CDD1D)
    z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    z = z ^ (z >> np.uint64(31))
    if z == 0:
        z = np.uint64(1)
    s = np.empty(1, np.uint64)
    s[0] = z
    return s


@nb.njit(inline="always")
def dot(a0, a1, a2, b0, b1, b2):
    return a0 * b0 + a1 * b1 + a2 * b2


@nb.njit
def intersect(o, d, Q, S, LQ):
    """Return (t, kind, index): kind 0 = quad, 1 = sphere, 2 = light, -1 = miss."""
    tbest, kind, idx = 1e30, -1, -1
    nq = Q.shape[0]
    for k in range(nq + 1):
        q = Q[k] if k < nq else LQ
        denom = dot(d[0], d[1], d[2], q[9], q[10], q[11])
        if abs(denom) < 1e-12:
            continue
        t = dot(q[0] - o[0], q[1] - o[1], q[2] - o[2], q[9], q[10], q[11]) / denom
        if t < EPS or t >= tbest:
            continue
        px, py, pz = o[0] + t * d[0] - q[0], o[1] + t * d[1] - q[1], o[2] + t * d[2] - q[2]
        a = dot(px, py, pz, q[3], q[4], q[5]) / dot(q[3], q[4], q[5], q[3], q[4], q[5])
        b = dot(px, py, pz, q[6], q[7], q[8]) / dot(q[6], q[7], q[8], q[6], q[7], q[8])
        if a < 0 or a > 1 or b < 0 or b > 1:
            continue
        tbest, kind, idx = t, (0 if k < nq else 2), k
    for k in range(S.shape[0]):
        ox, oy, oz = o[0] - S[k, 0], o[1] - S[k, 1], o[2] - S[k, 2]
        bq = dot(ox, oy, oz, d[0], d[1], d[2])
        c = dot(ox, oy, oz, ox, oy, oz) - S[k, 3] * S[k, 3]
        disc = bq * bq - c
        if disc < 0:
            continue
        sq = math.sqrt(disc)
        t = -bq - sq
        if t < EPS:
            t = -bq + sq
        if t < EPS or t >= tbest:
            continue
        tbest, kind, idx = t, 1, k
    return tbest, kind, idx


@nb.njit
def trace_sample(o, d, Q, qmat, S, smat, LQ, refl, Le, wl_idx, nee, max_b, surf_emit, rs):
    """Radiance (per carried wavelength) along ray (o,d). refl: (nmat, 401)."""
    nw = wl_idx.shape[0]
    T = np.ones(nw)
    L = np.zeros(nw)
    o = o.copy(); d = d.copy()
    larea = math.sqrt(dot(LQ[3], LQ[4], LQ[5], LQ[3], LQ[4], LQ[5])) * math.sqrt(dot(LQ[6], LQ[7], LQ[8], LQ[6], LQ[7], LQ[8]))
    nloop = max_b if nee else max_b + 1
    for depth in range(nloop):
        t, kind, idx = intersect(o, d, Q, S, LQ)
        if kind < 0:
            break
        if kind == 2:
            if dot(d[0], d[1], d[2], LQ[9], LQ[10], LQ[11]) < 0 and ((not nee) or depth == 0):
                for i in range(nw):
                    L[i] += T[i] * Le[wl_idx[i]]
            break
        p = np.empty(3)
        for j in range(3):
            p[j] = o[j] + t * d[j]
        n = np.empty(3)
        if kind == 0:
            n[0], n[1], n[2] = Q[idx, 9], Q[idx, 10], Q[idx, 11]
            m = qmat[idx]
        else:
            for j in range(3):
                n[j] = (p[j] - S[idx, j]) / S[idx, 3]
            m = smat[idx]
        if dot(n[0], n[1], n[2], d[0], d[1], d[2]) > 0:
            n = -n
        if surf_emit > 0:
            for i in range(nw):
                L[i] += T[i] * surf_emit
        if (not nee) and depth == max_b:
            break
        if nee:
            a, b = rnd(rs), rnd(rs)
            lx = LQ[0] + a * LQ[3] + b * LQ[6] - p[0]
            ly = LQ[1] + a * LQ[4] + b * LQ[7] - p[1]
            lz = LQ[2] + a * LQ[5] + b * LQ[8] - p[2]
            dist2 = lx * lx + ly * ly + lz * lz
            dist = math.sqrt(dist2)
            wx, wy, wz = lx / dist, ly / dist, lz / dist
            cosx = dot(n[0], n[1], n[2], wx, wy, wz)
            cosl = -dot(LQ[9], LQ[10], LQ[11], wx, wy, wz)
            if cosx > 0 and cosl > 0:
                so = np.empty(3); sd = np.empty(3)
                so[0], so[1], so[2] = p[0] + n[0] * 1e-5, p[1] + n[1] * 1e-5, p[2] + n[2] * 1e-5
                sd[0], sd[1], sd[2] = wx, wy, wz
                ts, ks, _ = intersect(so, sd, Q, S, LQ)
                if ks == 2 and ts > dist - 1e-4:
                    g = cosx * cosl / dist2 * larea / math.pi
                    for i in range(nw):
                        L[i] += T[i] * refl[m, wl_idx[i]] * Le[wl_idx[i]] * g
        # cosine-weighted hemisphere sample around n
        u1, u2 = rnd(rs), rnd(rs)
        r = math.sqrt(u1); phi = 2 * math.pi * u2
        lx_, ly_, lz_ = r * math.cos(phi), r * math.sin(phi), math.sqrt(max(0.0, 1 - u1))
        if abs(n[0]) > 0.9:
            tx, ty, tz = 0.0, 1.0, 0.0
        else:
            tx, ty, tz = 1.0, 0.0, 0.0
        bx, by, bz = n[1] * tz - n[2] * ty, n[2] * tx - n[0] * tz, n[0] * ty - n[1] * tx
        bl = math.sqrt(bx * bx + by * by + bz * bz); bx /= bl; by /= bl; bz /= bl
        cx, cy, cz = n[1] * bz - n[2] * by, n[2] * bx - n[0] * bz, n[0] * by - n[1] * bx
        d = np.empty(3)
        d[0] = lx_ * bx + ly_ * cx + lz_ * n[0]
        d[1] = lx_ * by + ly_ * cy + lz_ * n[1]
        d[2] = lx_ * bz + ly_ * cz + lz_ * n[2]
        for j in range(3):
            o[j] = p[j] + n[j] * 1e-5
        for i in range(nw):
            T[i] *= refl[m, wl_idx[i]]
    return L


@nb.njit(parallel=True)
def render(W, H, spp, seed, cam, Q, qmat, S, smat, LQ, refl, Le, cmf, cdf, pdf, nw, full_spectrum,
           nee, max_b, surf_emit):
    """Returns (xyz_even, xyz_odd, emitter_mask): sums over even/odd sample indices (independent halves)."""
    outA = np.zeros((H, W, 3)); outB = np.zeros((H, W, 3)); mask = np.zeros((H, W), np.uint8)
    nl = cdf.shape[0]
    for i in nb.prange(H):
        for j in range(W):
            rs = seed_state(seed, i * W + j, 7)
            for s in range(spp):
                if full_spectrum:
                    wl = np.arange(nl)
                    w = np.ones(nl)
                else:
                    wl = np.empty(nw, np.int64); w = np.empty(nw)
                    u0 = rnd(rs)
                    for k in range(nw):
                        u = u0 + k / nw
                        if u >= 1.0:
                            u -= 1.0
                        idx = np.searchsorted(cdf, u, side="right")
                        if idx >= nl:
                            idx = nl - 1
                        wl[k] = idx
                        w[k] = 1.0 / (pdf[idx] * nw)
                px = (2.0 * (j + rnd(rs)) / W - 1.0) * cam[9] * (W / H)
                py = (1.0 - 2.0 * (i + rnd(rs)) / H) * cam[9]
                d = np.empty(3)
                for k in range(3):
                    d[k] = cam[3 + k] + px * cam[6 + k] + py * cam[10 + k]
                dn = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
                d /= dn
                o = cam[0:3].copy()
                if s == 0:
                    t, kind, _ = intersect(o, d, Q, S, LQ)
                    mask[i, j] = 1 if kind == 2 else 0
                L = trace_sample(o, d, Q, qmat, S, smat, LQ, refl, Le, wl, nee, max_b, surf_emit, rs)
                X = 0.0; Y = 0.0; Z = 0.0
                for k in range(wl.shape[0]):
                    X += cmf[wl[k], 0] * L[k] * w[k]
                    Y += cmf[wl[k], 1] * L[k] * w[k]
                    Z += cmf[wl[k], 2] * L[k] * w[k]
                if s % 2 == 0:
                    outA[i, j, 0] += X; outA[i, j, 1] += Y; outA[i, j, 2] += Z
                else:
                    outB[i, j, 0] += X; outB[i, j, 1] += Y; outB[i, j, 2] += Z
    return outA, outB, mask


@nb.njit
def radiance_along(o, d, n_samples, seed, Q, qmat, S, smat, LQ, refl, Le, nee, max_b, surf_emit):
    """Mean radiance (all 401 wavelengths) along one ray; used by analytic tests."""
    acc = np.zeros(refl.shape[1])
    wl = np.arange(refl.shape[1])
    rs = seed_state(seed, 1, 2)
    for _ in range(n_samples):
        acc += trace_sample(o, d, Q, qmat, S, smat, LQ, refl, Le, wl, nee, max_b, surf_emit, rs)
    return acc / n_samples


# ---------------------------------------------------------------------------

def pack_quad(p0, u, v, n):
    return np.array([*p0, *u, *v, *n], np.float64)


def camera_array(pos, look=(0, 0, 1), up=(0, 1, 0), tan_half=0.54):
    f = np.asarray(look, float); f /= np.linalg.norm(f)
    r = np.cross(np.asarray(up, float), f); r /= np.linalg.norm(r)    # +x when looking +z with y up
    r = -r if r[0] < 0 and f[2] > 0 else r
    u = np.cross(f, r); u = u if u[1] >= 0 else -u
    cam = np.zeros(13)
    cam[0:3], cam[3:6], cam[6:9], cam[9], cam[10:13] = pos, f, r, tan_half, u
    return cam


def light_pdf(cmf, Le):
    p = cmf.sum(1) * Le
    p = p / p.sum()
    return np.cumsum(p), p
