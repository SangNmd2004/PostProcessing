"""
Privacy-amplification block accumulation and the abort rule (2026-10-22).

Old rule: one PA block per fixed amount of key (one session, ~1.2 Mbit); the block is discarded when its
finite-key length is <= 0, and the link is "aborted" above QBER 11 %.
Problem: 11 % is the single-photon, f = 1, infinite-key limit. With decoy WCP sources, f > 1 and finite-size
decoy bounds, blocks of ~1e6 bits give no key above ~2-3 % QBER although the asymptotic threshold is 6-11 %
(results/exp_decoy.txt), so the old rule throws away keys that more statistics would have produced.

New rule (PAAccumulator), evaluated after every reconciled chunk with the statistics gathered so far:
  * ell = finite-key length of everything accumulated (pa_model.secure_length_decoy, Lim 2014).
  * asym = asymptotic secret fraction of the same statistics (counts and leak scaled by ASYM_SCALE, which removes
    every finite-size term): the best this channel can ever give with this f.
  * ABORT  when asym <= 0: no amount of data gives a key (channel / misalignment / dark counts too bad, or f too
           high). The accumulated bits are discarded. This replaces "QBER > 11 %".
  * EMIT   when ell > 0 and doubling the block would raise the secret fraction by less than DOUBLE_GAIN
           (projection: the same statistics with every count doubled), or ell / n >= NEAR_ASYM * asym, or
           n >= N_MAX, or the block is older than MAX_AGE_S (key latency). Waiting longer would gain little,
           the PA input limit is reached, or the key consumer has waited long enough.
           (A first version emitted only near the asymptotic fraction: on MODERATE it never emitted within 1 h.)
  * SPLIT-EMIT when ell falls below (1 - DROP) of the best ell seen in this block: the channel got worse and the
           new data only dilutes the block. The block as it was at its best point is emitted, the data after that
           point starts the next block. (Without this, a good MODERATE period followed by SEVERE data was dragged
           to asymptotic fraction <= 0 and aborted together with the bad data.) Block boundaries depend only on
           public counts, so the finite-key analysis of each block is unchanged.
  * ABORT  when n >= N_MAX and ell <= 0 (would need a block larger than the PA can process).
After 'emit' the caller calls emitted(): full reset, or after a split the counts of the emitted part are removed.
  * WAIT   otherwise: keep accumulating.
Per IR block, QBER > Q_BLOCK_MAX (11 %, on the public test-basis estimate) still drops that block before
reconciliation: such a block can only lower the accumulated key.

N_MAX: pa_hankel_hash takes up to 2^20 input words (33.5 Mbit); 16 Mbit keeps a pass at ~2 M cycles. PA time of a
block = ceil(ell / 1024) passes x (n / 8 + 40) cycles, e.g. 12 Mbit -> 0.5 Mbit key: 490 passes, ~7.4 s at 100 MHz,
small against the hours of link time such a block needs at high loss. The key buffer lives in CPU memory / DDR.
"""
import pa_model as pa

N_MAX = 16_000_000
NEAR_ASYM = 0.85
DOUBLE_GAIN = 0.10
DROP = 0.05
SPLIT_MIN_ELL = 100_000     # split only blocks whose best ell is significant (small ell is noisy: 1 s of data
                            # moved it by > 5 % and split MODERATE into useless kbit blocks)
MAX_AGE_S = 3600.0          # emit a positive-length block at the latest 1 h after its first bit (30 min cost
                            # key on MIXED: smaller blocks)
ASYM_SCALE = 1e6
Q_BLOCK_MAX = 0.11


class PAAccumulator:
    def __init__(self, mu, pk, n_max=N_MAX, near_asym=NEAR_ASYM, double_gain=DOUBLE_GAIN, max_age_s=MAX_AGE_S,
                 eps_sec=1e-9, eps_cor=1e-15):
        self.mu, self.pk = list(mu), list(pk)
        self.n_max, self.near_asym, self.double_gain = n_max, near_asym, double_gain
        self.max_age_s = max_age_s
        self.eps_sec, self.eps_cor = eps_sec, eps_cor
        self.reset()

    def reset(self):
        self.nk = [0, 0, 0]          # key-basis bits kept after IR, per intensity
        self.nt = [0, 0, 0]          # test-basis detections of the same time span, per intensity
        self.mt = [0, 0, 0]          # their errors
        self.leak = 0                # leak_EC of the kept IR blocks incl. verification tags
        self.t_start = None
        self.best = None             # snapshot at the largest ell so far: (ell, nk, nt, mt, leak, t)
        self.t_last = None
        self.emit_n = 0              # key bits of the block emitted by the last 'emit'
        self._split = False

    @property
    def n(self):
        return sum(self.nk)

    def add(self, nk, nt, mt, leak, t=None):
        for k in range(3):
            self.nk[k] += nk[k]
            self.nt[k] += nt[k]
            self.mt[k] += mt[k]
        self.leak += leak
        if self.t_start is None:
            self.t_start = t
        self.t_last = t

    def _ell(self, s):
        return pa.secure_length_decoy([x * s for x in self.nk], [x * s for x in self.nt], [x * s for x in self.mt],
                                      self.mu, self.pk, self.leak * s, self.eps_sec, self.eps_cor)["ell"]

    def lengths(self):
        """(finite-key ell, asymptotic secret fraction, projected fraction of a block twice as large)."""
        if self.n == 0 or min(self.nt) == 0:
            return 0, 0.0, 0.0
        n = self.n
        return self._ell(1), self._ell(ASYM_SCALE) / (n * ASYM_SCALE), self._ell(2) / (2 * n)

    def decide(self, t=None):
        """('emit' | 'wait' | 'abort', ell, asymptotic fraction, reason). t: current time (s) for the age limit."""
        ell, asym, frac2 = self.lengths()
        n = self.n
        if n == 0:
            return "wait", 0, 0.0, "empty"
        self._split = False
        if ell > 0 and (self.best is None or ell > self.best[0]):
            self.best = (ell, list(self.nk), list(self.nt), list(self.mt), self.leak, self.t_last)
        if self.best is not None and self.best[0] >= SPLIT_MIN_ELL and ell < (1 - DROP) * self.best[0]:
            self._split = True
            self.emit_n = sum(self.best[1])
            return "emit", self.best[0], asym, "ell dropped: channel got worse, emit the block at its best point"
        if asym <= 0 and n >= 200_000:          # enough data for the point estimates themselves
            return "abort", ell, asym, "no key even with infinite data (asymptotic fraction <= 0)"
        self.emit_n = n
        if ell > 0:
            frac = ell / n
            if n >= self.n_max:
                return "emit", ell, asym, "PA input limit"
            if frac2 <= frac * (1 + self.double_gain):
                return "emit", ell, asym, "doubling the block gains < {:.0%}".format(self.double_gain)
            if frac >= self.near_asym * asym:
                return "emit", ell, asym, "near asymptotic"
            if t is not None and self.t_start is not None and t - self.t_start >= self.max_age_s:
                return "emit", ell, asym, "age limit"
        if n >= self.n_max:
            return "abort", ell, asym, "PA input limit reached with ell <= 0"
        return "wait", ell, asym, ""

    def emitted(self):
        """Call after an 'emit': full reset, or keep the data that came after the emitted snapshot."""
        if not self._split:
            self.reset()
            return
        _, nk, nt, mt, leak, t = self.best
        self.nk = [a - b for a, b in zip(self.nk, nk)]
        self.nt = [a - b for a, b in zip(self.nt, nt)]
        self.mt = [a - b for a, b in zip(self.mt, mt)]
        self.leak -= leak
        self.t_start = t
        self.best = None
        self._split = False
