"""
Privacy amplification (PA) golden model: streaming Hankel (Toeplitz-type) universal hash, plus the secure
key-length formula the firmware uses to decide how many output bits to keep.

Hash (bit-exact with rtl/pa/pa_hankel_hash.v):
    y[j] = XOR_{i < n_in} x[i] AND s[i + j],   j = 0 .. L_OUT - 1
  x : n_in input bits (reconciled key bits, D positions removed, accumulated over IR blocks; zero-padded to a
      multiple of 32 - padding does not change y),
  s : seed bits from a TRNG, shared with Alice over the authenticated channel. The core consumes
      n_in + L_OUT + 32 seed bits (word-aligned); only s[0 .. n_in + L_OUT - 2] matter.
  The matrix H[j][i] = s[i + j] is a Hankel matrix (a Toeplitz matrix with its columns reversed), so the
  family {H_s} is 2-universal like the Toeplitz family -> leftover hash lemma applies.
  Outputs longer than L_OUT = 1024 bits: run pass c with the seed starting at bit c * L_OUT (rows c*L_OUT ..),
  same input. The same core with a fresh seed and only the first 64 output bits is the verification hash.

Secure length (asymptotic-plus-finite-size form, e.g. Lim et al. / Tomamichel et al.; epsilons per stage):
    ell = floor( n_pa * (1 - h(Q_ph)) - leak_EC - log2(2 / eps_ver) - 2 * log2(1 / (2 * eps_pa)) )
    Q_ph = Q + mu,  mu = sqrt( (n_pa + k) / (n_pa * k) * (k + 1) / k * ln(1 / eps_pe) )
  (k = PE sample size, BB84 phase error ~ bit error). Firmware rounds ell down to a multiple of 64.

Usage: python pa_model.py [out_dir]   -> writes TB vectors for tb/tb_qkd_ir.v (PA part)
"""
import math
import os
import sys

import numpy as np

L_OUT = 1024        # output bits per pass (RTL parameter)
B_STEP = 8          # input bits per clock (RTL parameter)


def pa_hash(x, seed, l_out=L_OUT):
    """x: (n_in,) 0/1, seed: (>= n_in + l_out - 1,) 0/1 -> y (l_out,) 0/1."""
    x = np.asarray(x, dtype=np.uint8)
    seed = np.asarray(seed, dtype=np.uint8)
    n_in = len(x)
    y = np.zeros(l_out, dtype=np.uint8)
    for i in np.nonzero(x)[0]:
        y ^= seed[i:i + l_out]
    assert len(seed) >= n_in + l_out - 1
    return y


def h2(p):
    return 0.0 if p <= 0 or p >= 1 else -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def secure_length(n_pa, q, leak_ec, k_pe, eps_pe=1e-10, eps_pa=1e-10, eps_ver=1e-12):
    mu = math.sqrt((n_pa + k_pe) / (n_pa * k_pe) * (k_pe + 1) / k_pe * math.log(1 / eps_pe))
    q_ph = min(0.5, q + mu)
    ell = n_pa * (1 - h2(q_ph)) - leak_ec - math.log2(2 / eps_ver) - 2 * math.log2(1 / (2 * eps_pa))
    return max(0, int(ell) // 64 * 64), q_ph


def secure_length_decoy(nk, nt, mt, mu, pk, leak_ec, eps_sec=1e-9, eps_cor=1e-15):
    """Finite-key secret length of decoy-state BB84 with three intensities mu[0] > mu[1] + mu[2], mu[1] > mu[2] >= 0
    (Lim, Curty, Walenta, Xu, Zbinden, PRA 89, 022307 (2014), eqs. 1-5 and the gamma term; the paper's basis X is
    our key basis Z, its basis Z our test basis X).
      nk[k] : key-basis sifted detections with intensity k (all of them form the key)
      nt[k], mt[k] : test-basis sifted detections and errors with intensity k
      leak_ec : information leaked by error correction INCLUDING verification tags
    Returns dict(ell, s0, s1, phi, ...). Every statistical estimate uses eps_sec / 21 (Hoeffding)."""
    e1 = eps_sec / 21.0
    m1, m2, m3 = mu

    def dlt(n):
        return math.sqrt(n / 2.0 * math.log(1.0 / e1))

    def bounds(cnt):
        tot = sum(cnt)
        d = dlt(tot)
        lo = [math.exp(mu[k]) / pk[k] * (cnt[k] - d) for k in range(3)]
        hi = [math.exp(mu[k]) / pk[k] * (cnt[k] + d) for k in range(3)]
        return lo, hi

    tau0 = sum(pk[k] * math.exp(-mu[k]) for k in range(3))
    tau1 = sum(pk[k] * math.exp(-mu[k]) * mu[k] for k in range(3))

    def s01(cnt):
        lo, hi = bounds(cnt)
        s0 = max(0.0, tau0 * (m2 * lo[2] - m3 * hi[1]) / (m2 - m3))
        s1 = tau1 * m1 / (m1 * (m2 - m3) - m2 ** 2 + m3 ** 2) * (
            lo[1] - hi[2] - (m2 ** 2 - m3 ** 2) / m1 ** 2 * (hi[0] - s0 / tau0))
        return s0, max(0.0, s1)

    s0k, s1k = s01(nk)
    s0t, s1t = s01(nt)
    mlo, mhi = bounds(mt)
    v1 = tau1 * (mhi[1] - mlo[2]) / (m2 - m3)
    if s1k <= 0 or s1t <= 0:
        return {"ell": 0, "s0": s0k, "s1": s1k, "phi": 0.5, "v1": v1, "s1_test": s1t}
    b = min(0.5, max(1e-9, v1 / s1t))
    c, d = s1t, s1k
    gam = math.sqrt((c + d) * (1 - b) * b / (c * d * math.log(2)) *
                    math.log2((c + d) / (c * d * (1 - b) * b) * 21 ** 2 / eps_sec ** 2))
    phi = min(0.5, b + gam)
    ell = s0k + s1k * (1 - h2(phi)) - leak_ec - 6 * math.log2(21 / eps_sec) - math.log2(2 / eps_cor)
    return {"ell": max(0, int(ell)), "s0": s0k, "s1": s1k, "phi": phi, "v1": v1, "s1_test": s1t}


def bits_to_words(bits, width):
    return [sum(int(bits[w * width + i]) << i for i in range(width)) for w in range(len(bits) // width)]


def write_vectors(out_dir, n_in_words=128, seed=99):
    """One PA job: n_in_words * 32 input bits, seed of (n_in_words + 33) words, expected 16 x 64-bit outputs."""
    rng = np.random.default_rng(seed)
    n_in = 32 * n_in_words
    x = rng.integers(0, 2, n_in).astype(np.uint8)
    s = rng.integers(0, 2, n_in + L_OUT + 32).astype(np.uint8)
    y = pa_hash(x, s)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "pa_x.hex"), "w") as fh:
        fh.writelines(f"{w:08x}\n" for w in bits_to_words(x, 32))
    with open(os.path.join(out_dir, "pa_seed.hex"), "w") as fh:
        fh.writelines(f"{w:08x}\n" for w in bits_to_words(s, 32))
    with open(os.path.join(out_dir, "pa_y.hex"), "w") as fh:
        fh.writelines(f"{w:016x}\n" for w in bits_to_words(y, 64))
    with open(os.path.join(out_dir, "pa_n.hex"), "w") as fh:
        fh.write(f"{n_in_words:x}\n")
    print(f"PA vectors: {n_in} input bits, {len(s)} seed bits, {L_OUT} output bits -> {os.path.normpath(out_dir)}")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    write_vectors(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "data", "tb"))
