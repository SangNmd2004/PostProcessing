/*
 * Bob-side driver for the qkd_pp_axi IP: dynamic blind reconciliation controller + privacy amplification.
 *
 * REFERENCE CODE - NOT COMPILED OR RUN ON THE BOARD YET. It mirrors model/dyn_ir.py (Controller) and
 * model/pa_model.py line by line; the model is the reference when they disagree. Platform hooks (DMA, the
 * classical channel to Alice, TRNG) are declared extern and must be provided by the AE350 BSP / application.
 *
 * One block (n = 3072 variable nodes, d = 307 modulated positions D, n - d = 2765 key bits):
 *   1. PE: q_pe = mismatches in a PE sample (done by the QKD stack before IR).
 *   2. plan(): code + r0. Alice sends syndrome + r0 revealed bits of D in ONE message (HOLD mode).
 *      D of the chosen code = qkd_punct_pos[code] (grouping & sorting, model/puncture.py), in reveal order;
 *      Alice uses the same table. qkd_build_ch_words() puts Bob's key bits on the other positions.
 *   3. DMA channel symbols + syndrome; wait STATUS.WAIT; write r0 REVEALs; RETRY (attempt 1).
 *   4. IRQ: SUCCESS -> read key (DMA), ERRCNT -> monitoring; FAIL -> ask Alice for
 *      delta = clamp(ALPHA * n_usc, DELTA_MIN, remaining) more bits, REVEAL them, RETRY.
 *      No bits left -> DISCARD.
 *   5. Verification: 64-bit Hankel hash of the reconciled key with a fresh public seed, compared with Alice's
 *      tag. A mismatch (decoder converged to a wrong codeword: seen in ~0.5 % of blocks at 3-4 % QBER in the
 *      model with random D) discards the block. Its cost is the log2(2/eps_ver) term of pa_secure_length().
 *   6. f_adj self-tuning after the block.
 *
 * Two profiles (model/dyn_ir.py PROFILES, results/exp_mode.txt, exp_adaptive.txt), chosen per block from the
 * number of sifted blocks waiting (qkd_select_profile, hysteresis BACKLOG_HI / BACKLOG_LO):
 *   EFFICIENCY  basic blind: code from a QBER table, r0 = 0 (all of D punctured), reveal d/4 per failure.
 *               Most secret bits per sifted bit (eta 0.481 on the 1-6 % drift, 0.265 on the team CSV);
 *               IR capacity 11.5 Mbit/s at RTT 100 us. Used while the IR keeps up with the raw key.
 *   THROUGHPUT  dynamic: PE bound z = 1.5, f* = 1.3 self-tuning, rescue-room code choice F_SAFE = 1.7,
 *               r0 pre-reveals, delta = n_usc. ~1.06 attempts/block, 21.6 Mbit/s capacity, 8.4 Mbit/s secret.
 *               Used when sifted blocks pile up.
 * Both: GS positions D, normalized min-sum (CFG2.NMS), early discard above Q_ABORT, verification hash.
 */
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include "qkd_pp_regs.h"
#include "qkd_punct_tables.h"

/* ---------------- platform hooks (to be provided) ---------------- */
extern void dma_to_stream_ch(const uint32_t *words, uint32_t n_words);     /* -> s_axis_ch   */
extern void dma_to_stream_syn(const uint32_t *words, uint32_t n_words);    /* -> s_axis_syn  */
extern void dma_from_stream_key(uint64_t *words, uint32_t n_words);        /* <- m_axis_key  */
extern void dma_to_stream_pa(const uint32_t *x, uint32_t nx, const uint32_t *seed, uint32_t ns);
extern void dma_from_stream_pa(uint64_t *y, uint32_t n_words);
extern void wait_irq(void);
/* classical channel: Alice reveals the values of D positions [first, first + count) in her reveal order */
extern uint32_t alice_reveal(uint32_t first, uint32_t count, uint32_t *reveal_words /* {val<<16 | pos} */);
/* verification: Bob sends a fresh seed, Alice returns the 64-bit hash of her key under that seed */
extern uint64_t alice_verification_tag(const uint32_t *seed, uint32_t n_seed_words);
extern void trng_fill(uint32_t *words, uint32_t n_words);

/* ---------------- controller parameters (model/dyn_ir.py PROFILES) ---------------- */
/* THROUGHPUT profile (dynamic)                                                                                */
#define F_TARGET   1.30f    /* initial f* (rate R* = 1 - f* h(q))                                            */
#define F_MIN      1.05f
#define F_MAX      1.80f
#define F_DOWN     0.98f    /* after a first-attempt success                                                  */
#define F_UP       1.04f    /* per failed attempt                                                             */
#define ALPHA      1.0f     /* reveal delta per unsatisfied check                                             */
#define DELTA_MIN  16u
#define PE_Z       1.5f     /* PE upper confidence bound: q + z * sigma                                       */
#define F_SAFE     1.7f     /* use a code only if, with all of D revealed, it still reaches f = F_SAFE        */
                            /* (rescue room; without this rule 1-3 of 24 blocks failed at 2-5 % QBER)         */
/* EFFICIENCY profile (basic blind)                                                                            */
#define BASIC_STEP ((QKD_D + 3u) / 4u)   /* 77 bits revealed per failure                                      */
/* both                                                                                                        */
#define Q_ABORT    0.11f    /* early discard on the PE point estimate (no secret key for BB84 above ~11 %)    */
#define BACKLOG_HI 4u       /* >= this many sifted blocks waiting -> THROUGHPUT                               */
#define BACKLOG_LO 1u       /* <= this many -> EFFICIENCY                                                     */

#define CORE_CFG   qkd_cfg(CODE_R34 /*overwritten*/, 8, 50, 1, 2, 16)   /* lq 8, iter_max 50, PP 1/2/16      */
#define CORE_ET    12u
#define VER_WORDS  ((QKD_NKEY + 31u) / 32u)    /* 87 words of reconciled key hashed for verification         */

typedef enum { PROF_EFFICIENCY = 0, PROF_THROUGHPUT = 1 } qkd_profile_t;

typedef struct {
    qkd_profile_t profile;
    float f_adj;            /* THROUGHPUT profile only (self-tuning f*)                      */
    float q_ewma;           /* EWMA of ERRCNT-measured QBER, for monitoring / PE calibration */
    int   have_ewma;
} dyn_ctrl_t;

/* call before each block with the number of sifted blocks waiting behind it */
void qkd_select_profile(dyn_ctrl_t *c, uint32_t backlog)
{
    if (backlog >= BACKLOG_HI)      c->profile = PROF_THROUGHPUT;
    else if (backlog <= BACKLOG_LO) c->profile = PROF_EFFICIENCY;
}

/* EFFICIENCY profile code table (model/dyn_ir.py basic_code) */
static uint32_t basic_code(float q)
{
    if (q <= 0.008f) return CODE_R56;
    if (q <= 0.022f) return CODE_R34;
    if (q <= 0.045f) return CODE_R23;
    return CODE_R12;
}

static float h2(float p)
{
    if (p <= 0.0f || p >= 1.0f) return 0.0f;
    return -p * log2f(p) - (1.0f - p) * log2f(1.0f - p);
}

/* rate window of a mother code: [R_min, R_max] = all D revealed .. all D punctured */
static void code_window(uint32_t code, float *r_min, float *r_max)
{
    float m = (float)(QKD_MB(code) * QKD_ZC);
    *r_max = 1.0f - (m - (float)QKD_D) / (float)QKD_NKEY;
    *r_min = 1.0f - m / (float)QKD_NKEY;
}

/* returns false for an early discard; otherwise code and r0 */
static bool plan(const dyn_ctrl_t *c, float q_pe, uint32_t n_pe, uint32_t *code, uint32_t *r0)
{
    if (q_pe > Q_ABORT) return false;                     /* point estimate, as model/dyn_ir.py */
    if (c->profile == PROF_EFFICIENCY) {                  /* basic blind: all of D punctured */
        *code = basic_code(q_pe);
        *r0 = 0;
        return true;
    }
    float qq = q_pe > 1.0f / (float)n_pe ? q_pe : 1.0f / (float)n_pe;
    float q_use = q_pe + PE_Z * sqrtf(qq * (1.0f - q_pe) / (float)n_pe);
    float r_star = 1.0f - c->f_adj * h2(q_use);
    float r_safe = 1.0f - F_SAFE * h2(q_use);             /* rate the block must still be able to reach */

    int best = -1;
    for (int k = CODE_R56; k >= CODE_R12; k--) {          /* most shortening first */
        float lo, hi;
        code_window((uint32_t)k, &lo, &hi);
        if (lo <= r_safe && r_star >= lo) { best = k; break; }   /* R* > hi: start at hi (r0 = 0) */
    }
    if (best < 0) best = CODE_R12;
    float need = (float)QKD_NKEY * (1.0f - r_star) - (float)(QKD_MB(best) * QKD_ZC - QKD_D);
    int32_t rr = (int32_t)ceilf(need);
    if (rr < 0) rr = 0;
    if (rr > (int32_t)QKD_D) rr = (int32_t)QKD_D;
    *code = (uint32_t)best;
    *r0 = (uint32_t)rr;
    return true;
}

static uint32_t next_reveal(const dyn_ctrl_t *c, uint32_t n_usc, uint32_t remaining)
{
    if (c->profile == PROF_EFFICIENCY)
        return BASIC_STEP < remaining ? BASIC_STEP : remaining;
    uint32_t d = (uint32_t)lroundf(ALPHA * (float)n_usc);
    if (d < DELTA_MIN) d = DELTA_MIN;
    return d < remaining ? d : remaining;
}

static void update(dyn_ctrl_t *c, bool success, uint32_t errcnt, uint32_t attempts)
{
    if (success) {
        float q = (float)errcnt / (float)QKD_NKEY;
        c->q_ewma = c->have_ewma ? 0.5f * c->q_ewma + 0.5f * q : q;
        c->have_ewma = 1;
    }
    if (attempts == 0 || c->profile != PROF_THROUGHPUT) return;
    if (success && attempts == 1) {
        c->f_adj *= F_DOWN;
        if (c->f_adj < F_MIN) c->f_adj = F_MIN;
    } else {
        uint32_t fails = success ? attempts - 1 : attempts;
        for (uint32_t i = 0; i < fails; i++) c->f_adj *= F_UP;
        if (c->f_adj > F_MAX) c->f_adj = F_MAX;
    }
}

static void reveal_bits(const uint32_t *words, uint32_t count)
{
    for (uint32_t i = 0; i < count; i++) QKD_REVEAL = words[i];   /* each write stalls until the core took it */
}

void qkd_init(dyn_ctrl_t *c)
{
    c->profile = PROF_EFFICIENCY;
    c->f_adj = F_TARGET;
    c->q_ewma = 0.0f;
    c->have_ewma = 0;
    QKD_CFG2 = CFG2_ET(CORE_ET) | CFG2_HOLD | CFG2_NMS;
    QKD_IRQ_EN = 0x3u;                                    /* SUCCESS, FAIL */
}

void qkd_pa_pass(const uint32_t *x, uint32_t n_words, const uint32_t *seed, uint64_t y[16]);

/*
 * Channel symbols of one block for `code`: 2 (punctured) on the d positions qkd_punct_pos[code], Bob's key bits
 * (bob_bits[0 .. NKEY-1], one bit per byte) on the remaining positions in increasing order (model: key_pos).
 */
void qkd_build_ch_words(const uint8_t *bob_bits, uint32_t code, uint32_t *ch_words)
{
    static uint8_t is_d[QKD_N];
    for (uint32_t i = 0; i < QKD_N; i++) is_d[i] = 0;
    for (uint32_t i = 0; i < QKD_PUNCT_D; i++) is_d[qkd_punct_pos[code][i]] = 1;
    for (uint32_t w = 0; w < QKD_N / 16u; w++) ch_words[w] = 0;
    uint32_t k = 0;
    for (uint32_t i = 0; i < QKD_N; i++) {
        uint32_t sym = is_d[i] ? 2u : (uint32_t)(bob_bits[k++] & 1u);
        ch_words[i / 16u] |= sym << (2u * (i % 16u));
    }
}

/* 64-bit verification tag of the reconciled key (key bits only, D removed): first word of a Hankel hash */
static uint64_t verification_tag(const uint64_t *key_n, uint32_t code, const uint32_t *seed)
{
    static uint8_t is_d[QKD_N];
    static uint32_t x[VER_WORDS];
    uint64_t y[16];
    for (uint32_t i = 0; i < QKD_N; i++) is_d[i] = 0;
    for (uint32_t i = 0; i < QKD_PUNCT_D; i++) is_d[qkd_punct_pos[code][i]] = 1;
    for (uint32_t w = 0; w < VER_WORDS; w++) x[w] = 0;
    uint32_t k = 0;
    for (uint32_t i = 0; i < QKD_N; i++) {
        if (is_d[i]) continue;
        uint32_t b = (uint32_t)(key_n[i / 64u] >> (i % 64u)) & 1u;
        x[k / 32u] |= b << (k % 32u);
        k++;
    }
    qkd_pa_pass(x, VER_WORDS, seed, y);
    return y[0];
}

/*
 * Reconcile one block. bob_bits: the NKEY = 2765 sifted key bits of the block (one per byte). The channel symbols
 * depend on the code (its D table), so they are built here after plan(). get_syndrome(code, syn_words) obtains
 * Alice's mb * 4 syndrome words for that code (Bob announces `code`, Alice answers with syndrome + r0 reveals).
 * key_out: 48 x 64-bit words (all n positions; D positions are qkd_punct_pos[code]). Returns true when the block
 * decoded AND passed the verification hash.
 */
extern void get_syndrome(uint32_t code, uint32_t *syn_words);

bool qkd_reconcile_block(dyn_ctrl_t *c, float q_pe, uint32_t n_pe, const uint8_t *bob_bits,
                         uint64_t *key_out, uint32_t *leak_bits)
{
    static uint32_t rv[QKD_D];
    static uint32_t ch_words[QKD_N / 16u];
    static uint32_t syn_words[12u * QKD_ZC / 32u];
    uint32_t code, r0;
    if (!plan(c, q_pe, n_pe, &code, &r0)) {               /* early discard: nothing sent, nothing leaked */
        update(c, false, 0, 0);
        *leak_bits = 0;
        return false;
    }
    QKD_CFG = (CORE_CFG & ~3u) | code;
    qkd_build_ch_words(bob_bits, code, ch_words);
    get_syndrome(code, syn_words);

    dma_to_stream_ch(ch_words, QKD_N / 16u);
    dma_to_stream_syn(syn_words, QKD_MB(code) * QKD_ZC / 32u);
    while (!(QKD_STATUS & STATUS_WAIT)) { }               /* HOLD: block loaded */

    uint32_t revealed = alice_reveal(0, r0, rv);          /* r0 bits travel with the syndrome */
    reveal_bits(rv, revealed);

    uint32_t attempts = 0;
    bool ok = false;
    for (;;) {
        QKD_STATUS = STATUS_SUCCESS | STATUS_FAIL;        /* clear sticky flags */
        QKD_CTRL = CTRL_RETRY;
        attempts++;
        wait_irq();
        uint32_t st = QKD_STATUS;
        if (st & STATUS_SUCCESS) {
            static uint32_t vseed[VER_WORDS + PA_PRELOAD];
            dma_from_stream_key(key_out, QKD_N / 64u);
            trng_fill(vseed, VER_WORDS + PA_PRELOAD);    /* fresh public seed per block */
            ok = verification_tag(key_out, code, vseed) == alice_verification_tag(vseed, VER_WORDS + PA_PRELOAD);
            break;                                        /* mismatch: wrong codeword -> block discarded */
        }
        if (revealed >= QKD_D) {                          /* nothing left to reveal */
            QKD_CTRL = CTRL_DISCARD;
            break;
        }
        uint32_t delta = next_reveal(c, STATUS_N_USC(st), QKD_D - revealed);
        uint32_t got = alice_reveal(revealed, delta, rv);
        reveal_bits(rv, got);
        revealed += got;
    }
    *leak_bits = QKD_MB(code) * QKD_ZC - QKD_D + revealed;
    update(c, ok, ok ? (QKD_ERRCNT & 0xFFFu) : 0u, attempts);
    return ok;
}

/* ---------------- privacy amplification ---------------- */

/* secure output length (model/pa_model.py secure_length), rounded down to 64 bits */
uint32_t pa_secure_length(uint32_t n_pa, float q, uint32_t leak_ec, uint32_t k_pe,
                          float eps_pe, float eps_pa, float eps_ver)
{
    float mu = sqrtf((float)(n_pa + k_pe) / ((float)n_pa * (float)k_pe) *
                     (float)(k_pe + 1) / (float)k_pe * logf(1.0f / eps_pe));
    float q_ph = q + mu > 0.5f ? 0.5f : q + mu;
    float ell = (float)n_pa * (1.0f - h2(q_ph)) - (float)leak_ec - log2f(2.0f / eps_ver)
                - 2.0f * log2f(1.0f / (2.0f * eps_pa));
    if (ell <= 0.0f) return 0;
    return ((uint32_t)ell) / 64u * 64u;
}

/*
 * One PA pass: x = n_words * 32 reconciled key bits (zero-padded), seed = (n_words + 33) TRNG words shared with
 * Alice. Output: 1024 hash bits (16 words). For ell > 1024 run pass c with seed starting at bit c * 1024.
 * The same call with a fresh seed and only y[0] kept is the 64-bit verification hash.
 */
void qkd_pa_pass(const uint32_t *x, uint32_t n_words, const uint32_t *seed, uint64_t y[16])
{
    QKD_PA_NWORDS = n_words;
    QKD_STATUS = STATUS_PA_DONE;
    QKD_PA_CTRL = 1u;
    dma_to_stream_pa(x, n_words, seed, n_words + PA_PRELOAD);
    dma_from_stream_pa(y, PA_L_OUT / 64u);
    while (!(QKD_STATUS & STATUS_PA_DONE)) { }
}

/* ---------------- PA block accumulation and abort rule (model/pa_accum.py) ----------------
 *
 * The link is no longer aborted at a fixed QBER of 11 % (single-photon, f = 1, infinite-key limit). Reconciled
 * blocks are accumulated with their decoy statistics; after each block pa_accum_decide() returns
 *   PA_EMIT  : ell > 0 and (doubling the block would gain < PA_DOUBLE_GAIN, or ell / n >= PA_NEAR_ASYM * asymptotic
 *              fraction, or n >= PA_N_MAX, or the block is older than PA_MAX_AGE_S) -> run PA on the block
 *   PA_WAIT  : keep accumulating
 *   PA_EMIT  (split): ell fell below (1 - PA_DROP) of the best ell of this block (channel got worse): the block as
 *              it was at its best point is emitted, the later data stays for the next block (pa_accum_emitted)
 *   PA_ABORT : asymptotic fraction <= 0 (no key with any amount of data), or PA_N_MAX reached with ell <= 0
 * Q_ABORT (11 %, test-basis estimate) still drops single IR blocks before reconciliation.
 *
 * Use, per reconciled block (after qkd_reconcile_block() returned true and passed verification):
 *   append the NKEY key bits to the key buffer (CPU memory / DDR, up to PA_N_MAX bits);
 *   pa_accum_add(&acc, nk_per_intensity, nt, mt, leak_bits + 64, t_now);   nt / mt: test-basis counts and
 *                                                                          errors of the block's time window
 *   switch (pa_accum_decide(&acc, t_now, &ell)) {
 *     case PA_EMIT:  ceil(ell / 1024) qkd_pa_pass() calls over the first acc.emit_n bits of the buffer -> ell
 *                    secret bits; drop those bits from the buffer; pa_accum_emitted(&acc)
 *     case PA_ABORT: discard the buffer, reset, report "no key possible on this channel / with this f"
 *     case PA_WAIT:  continue
 *   }
 * Alice runs the same decision on the same public statistics, so both sides emit / abort together.
 */
#define PA_N_MAX       16000000.0   /* key bits per PA block (pa_hankel_hash input limit 2^20 words = 33.5 Mbit) */
#define PA_NEAR_ASYM   0.85
#define PA_DOUBLE_GAIN 0.10         /* emit when doubling the block would raise the secret fraction < 10 % */
#define PA_DROP        0.05         /* split when ell < 95 % of the best ell of the block                    */
#define PA_MAX_AGE_S   3600.0       /* emit a positive-length block at the latest 1 h after its first bit     */
#define PA_SPLIT_MIN_ELL 100000.0   /* split only blocks whose best ell is significant (small ell is noisy)  */
#define PA_ASYM_SCALE  1e6
#define PA_EPS_SEC     1e-9
#define PA_EPS_COR     1e-15
/* decoy source of the transmitter: signal / decoy / vacuum intensity and probability */
static const double DECOY_MU[3] = {0.6, 0.2, 0.0};
static const double DECOY_P[3]  = {0.75, 0.125, 0.125};

typedef enum { PA_WAIT = 0, PA_EMIT = 1, PA_ABORT = 2 } pa_action_t;

typedef struct {
    double nk[3];      /* key-basis bits kept after IR, per intensity           */
    double nt[3];      /* test-basis detections of the same time span          */
    double mt[3];      /* test-basis errors                                    */
    double leak;       /* leak_EC of the kept blocks incl. 64-bit tags         */
    double t_start;    /* time of the first block (s), < 0 when empty          */
    double t_last;     /* time of the last block added                         */
    /* snapshot at the largest ell so far (best[] valid when best_ell > 0)     */
    double best_ell, best_nk[3], best_nt[3], best_mt[3], best_leak, best_t;
    int    split;      /* last PA_EMIT was a split at the best snapshot        */
    double emit_n;     /* key bits of the block emitted by the last PA_EMIT    */
} pa_accum_t;

static double h2d(double p)
{
    if (p <= 0.0 || p >= 1.0) return 0.0;
    return -p * log2(p) - (1.0 - p) * log2(1.0 - p);
}

/* Lim et al. 2014 finite-key length (model: pa_model.secure_length_decoy); returns ell (bits, may be <= 0) */
static double secure_length_decoy(const double nk[3], const double nt[3], const double mt[3], double leak)
{
    const double *mu = DECOY_MU, *pk = DECOY_P;
    double e1 = PA_EPS_SEC / 21.0, ln_e1 = log(1.0 / e1);
    double tau0 = 0.0, tau1 = 0.0;
    for (int k = 0; k < 3; k++) {
        tau0 += pk[k] * exp(-mu[k]);
        tau1 += pk[k] * exp(-mu[k]) * mu[k];
    }
    double lo[3], hi[3], s0[2], s1[2];
    const double *cnt[2] = {nk, nt};
    for (int b = 0; b < 2; b++) {                       /* b = 0 key basis, 1 test basis */
        double tot = cnt[b][0] + cnt[b][1] + cnt[b][2];
        double d = sqrt(tot / 2.0 * ln_e1);
        for (int k = 0; k < 3; k++) {
            lo[k] = exp(mu[k]) / pk[k] * (cnt[b][k] - d);
            hi[k] = exp(mu[k]) / pk[k] * (cnt[b][k] + d);
        }
        s0[b] = tau0 * (mu[1] * lo[2] - mu[2] * hi[1]) / (mu[1] - mu[2]);
        if (s0[b] < 0.0) s0[b] = 0.0;
        s1[b] = tau1 * mu[0] / (mu[0] * (mu[1] - mu[2]) - mu[1] * mu[1] + mu[2] * mu[2]) *
                (lo[1] - hi[2] - (mu[1] * mu[1] - mu[2] * mu[2]) / (mu[0] * mu[0]) * (hi[0] - s0[b] / tau0));
        if (s1[b] < 0.0) s1[b] = 0.0;
    }
    double mtot = mt[0] + mt[1] + mt[2], dm = sqrt(mtot / 2.0 * ln_e1);
    double mhi1 = exp(mu[1]) / pk[1] * (mt[1] + dm), mlo2 = exp(mu[2]) / pk[2] * (mt[2] - dm);
    double v1 = tau1 * (mhi1 - mlo2) / (mu[1] - mu[2]);
    if (s1[0] <= 0.0 || s1[1] <= 0.0) return -1.0;
    double bb = v1 / s1[1];
    if (bb > 0.5) bb = 0.5;
    if (bb < 1e-9) bb = 1e-9;
    double c = s1[1], dd = s1[0];
    double gam = sqrt((c + dd) * (1.0 - bb) * bb / (c * dd * log(2.0)) *
                      log2((c + dd) / (c * dd * (1.0 - bb) * bb) * 441.0 / (PA_EPS_SEC * PA_EPS_SEC)));
    double phi = bb + gam;
    if (phi > 0.5) phi = 0.5;
    return s0[0] + s1[0] * (1.0 - h2d(phi)) - leak - 6.0 * log2(21.0 / PA_EPS_SEC) - log2(2.0 / PA_EPS_COR);
}

void pa_accum_reset(pa_accum_t *a)
{
    for (int k = 0; k < 3; k++) a->nk[k] = a->nt[k] = a->mt[k] = 0.0;
    a->leak = 0.0;
    a->t_start = -1.0;
    a->t_last = -1.0;
    a->best_ell = 0.0;
    a->split = 0;
    a->emit_n = 0.0;
}

/* after each IR block: key bits kept per intensity, test-basis counts / errors of its time window, its leak */
void pa_accum_add(pa_accum_t *a, const uint32_t nk[3], const uint32_t nt[3], const uint32_t mt[3], uint32_t leak,
                  double t_now)
{
    if (a->t_start < 0.0) a->t_start = t_now;
    a->t_last = t_now;
    for (int k = 0; k < 3; k++) {
        a->nk[k] += nk[k];
        a->nt[k] += nt[k];
        a->mt[k] += mt[k];
    }
    a->leak += leak;
}

pa_action_t pa_accum_decide(pa_accum_t *a, double t_now, uint32_t *ell_out)
{
    double n = a->nk[0] + a->nk[1] + a->nk[2];
    *ell_out = 0;
    a->split = 0;
    if (n <= 0.0 || a->nt[0] <= 0.0 || a->nt[1] <= 0.0 || a->nt[2] <= 0.0) return PA_WAIT;
    double ell = secure_length_decoy(a->nk, a->nt, a->mt, a->leak);
    if (ell > 0.0 && ell > a->best_ell) {                       /* new best point of this block */
        a->best_ell = ell;
        for (int k = 0; k < 3; k++) {
            a->best_nk[k] = a->nk[k];
            a->best_nt[k] = a->nt[k];
            a->best_mt[k] = a->mt[k];
        }
        a->best_leak = a->leak;
        a->best_t = a->t_last;
    }
    if (a->best_ell >= PA_SPLIT_MIN_ELL && ell < (1.0 - PA_DROP) * a->best_ell) {   /* channel got worse */
        a->split = 1;
        a->emit_n = a->best_nk[0] + a->best_nk[1] + a->best_nk[2];
        *ell_out = (uint32_t)a->best_ell / 64u * 64u;
        return PA_EMIT;
    }
    a->emit_n = n;
    double nks[3], nts[3], mts[3];
    for (int k = 0; k < 3; k++) {
        nks[k] = a->nk[k] * PA_ASYM_SCALE;
        nts[k] = a->nt[k] * PA_ASYM_SCALE;
        mts[k] = a->mt[k] * PA_ASYM_SCALE;
    }
    double asym = secure_length_decoy(nks, nts, mts, a->leak * PA_ASYM_SCALE) / (n * PA_ASYM_SCALE);
    if (asym <= 0.0 && n >= 200000.0) return PA_ABORT;          /* no key with any amount of data */
    if (ell > 0.0) {
        /* projected fraction of a block twice as large: the same statistics with every count doubled */
        for (int k = 0; k < 3; k++) {
            nks[k] = 2.0 * a->nk[k];
            nts[k] = 2.0 * a->nt[k];
            mts[k] = 2.0 * a->mt[k];
        }
        double frac  = ell / n;
        double frac2 = secure_length_decoy(nks, nts, mts, 2.0 * a->leak) / (2.0 * n);
        int old = a->t_start >= 0.0 && t_now - a->t_start >= PA_MAX_AGE_S;
        if (n >= PA_N_MAX || frac2 <= frac * (1.0 + PA_DOUBLE_GAIN) || frac >= PA_NEAR_ASYM * asym || old) {
            *ell_out = (uint32_t)ell / 64u * 64u;
            return PA_EMIT;
        }
    }
    if (n >= PA_N_MAX) return PA_ABORT;                         /* would need a larger PA block */
    return PA_WAIT;
}

/* after PA_EMIT: full reset, or after a split remove the emitted part and keep the later data */
void pa_accum_emitted(pa_accum_t *a)
{
    if (!a->split) {
        pa_accum_reset(a);
        return;
    }
    for (int k = 0; k < 3; k++) {
        a->nk[k] -= a->best_nk[k];
        a->nt[k] -= a->best_nt[k];
        a->mt[k] -= a->best_mt[k];
    }
    a->leak -= a->best_leak;
    a->t_start = a->best_t;
    a->best_ell = 0.0;
    a->split = 0;
}

/* ---------------- multi-context operation (2026-10-23) ----------------
 *
 * Up to QKD_NCTX blocks in flight share the decoder: while one block waits for Alice (syndrome or reveals, one
 * classical round trip each), the core decodes the others. Measured on the RTL (tb/tb_qkd_ir_ctx.v, 30 blocks of
 * the simulated sessions, RTT 100 us): 1 context 18.3 Mbit/s, 4 contexts 63.6 Mbit/s of reconciled key.
 * qkd_reconcile_block() above is the blocking single-block flow on context 0; the functions below are its
 * non-blocking multi-context form, driven from the application's main loop:
 *   ctx = qkd_mc_start_block(...)        plan the block, ask Alice for its syndrome (+ r0 reveals)
 *   qkd_mc_on_syndrome(ctx, ...)         Alice's answer arrived: stream the block into context ctx, start it
 *   qkd_mc_on_reveals(ctx, ...)          Alice's reveals after a failed attempt arrived: apply them, retry
 *   qkd_mc_poll(...)                     handle SUCCESS / FAIL events of all contexts
 * Key words: keep one 48-word receive DMA armed on m_axis_key. Keys stream one at a time (the decoder waits until
 * a key is consumed) and SUCCESS of a context is raised after its key has streamed, so every completed 48-word
 * transfer belongs to the next SUCCESS event (m_axis_key_tuser also carries the context).
 */
extern void alice_request_block(uint32_t ctx, uint32_t code, uint32_t r0);              /* asynchronous */
extern void alice_request_reveals(uint32_t ctx, uint32_t first, uint32_t count);        /* asynchronous */
extern int  dma_key_take(uint64_t *key_n);       /* returns 1 and copies the oldest completed 48-word key */

typedef struct {
    int            used;
    uint32_t       code, revealed;
    const uint8_t *bob_bits;
} qkd_mc_ctx_t;

static qkd_mc_ctx_t mc[QKD_NCTX];

typedef struct {
    uint32_t ctx, code, leak_bits, errcnt;
    int      ok;                                  /* 1 key reconciled and verified, 0 discarded */
} qkd_mc_result_t;

void qkd_mc_init(dyn_ctrl_t *c)
{
    qkd_init(c);
    for (uint32_t k = 0; k < QKD_NCTX; k++) mc[k].used = 0;
    QKD_CFG2 = CFG2_ET(CORE_ET) | CFG2_HOLD | CFG2_NMS;   /* every block starts after its r0 reveals + RETRY */
}

/* returns the context, or -1: no free context, or early discard (nothing sent) */
int qkd_mc_start_block(dyn_ctrl_t *c, float q_pe, uint32_t n_pe, const uint8_t *bob_bits)
{
    uint32_t sum = QKD_CTX_SUM, code, r0;
    for (uint32_t k = 0; k < QKD_NCTX; k++) {
        if (mc[k].used || !CTX_SUM_FREE(sum, k)) continue;
        if (!plan(c, q_pe, n_pe, &code, &r0)) {
            update(c, false, 0, 0);
            return -1;
        }
        mc[k].used = 1;
        mc[k].code = code;
        mc[k].revealed = r0;
        mc[k].bob_bits = bob_bits;
        alice_request_block(k, code, r0);
        return (int)k;
    }
    return -1;
}

/* Alice's syndrome and the r0 reveal words {val << 16 | pos} of block ctx arrived */
void qkd_mc_on_syndrome(uint32_t ctx, const uint32_t *syn_words, const uint32_t *rv, uint32_t n_r0)
{
    static uint32_t ch_words[QKD_N / 16u];
    QKD_CFG = (CORE_CFG & ~3u) | mc[ctx].code;           /* code is taken per block when its loading completes */
    QKD_LOAD_CTX = ctx;
    qkd_build_ch_words(mc[ctx].bob_bits, mc[ctx].code, ch_words);
    dma_to_stream_ch(ch_words, QKD_N / 16u);
    dma_to_stream_syn(syn_words, QKD_MB(mc[ctx].code) * QKD_ZC / 32u);
    while (!CTX_SUM_WAIT(QKD_CTX_SUM, ctx)) { }           /* loaded, HOLD */
    for (uint32_t i = 0; i < n_r0; i++) QKD_REVEAL = rv[i] | REVEAL_CTX(ctx);
    QKD_CTRL = CTRL_RETRY | CTRL_CTX(ctx);
}

/* Alice's reveals after a failed attempt of block ctx arrived */
void qkd_mc_on_reveals(uint32_t ctx, const uint32_t *rv, uint32_t count)
{
    for (uint32_t i = 0; i < count; i++) QKD_REVEAL = rv[i] | REVEAL_CTX(ctx);
    QKD_CTRL = CTRL_RETRY | CTRL_CTX(ctx);
}

/* handle the events of all contexts; returns the number of finished blocks written to res[] */
uint32_t qkd_mc_poll(dyn_ctrl_t *c, qkd_mc_result_t res[QKD_NCTX], uint64_t key_out[QKD_NCTX][QKD_N / 64u])
{
    uint32_t sum = QKD_CTX_SUM, nres = 0;
    for (uint32_t k = 0; k < QKD_NCTX; k++) {
        if (!mc[k].used) continue;
        if (CTX_SUM_SUCCESS(sum, k)) {
            static uint32_t vseed[VER_WORDS + PA_PRELOAD];
            uint32_t a = QKD_CTX_A(k), b = QKD_CTX_B(k);
            QKD_CTX_SUM = 1u << (16 + k);
            dma_key_take(key_out[nres]);
            trng_fill(vseed, VER_WORDS + PA_PRELOAD);
            int ok = verification_tag(key_out[nres], mc[k].code, vseed) ==
                     alice_verification_tag(vseed, VER_WORDS + PA_PRELOAD);
            res[nres].ctx = k;
            res[nres].code = mc[k].code;
            res[nres].leak_bits = QKD_MB(mc[k].code) * QKD_ZC - QKD_D + mc[k].revealed + 64u;  /* + tag */
            res[nres].errcnt = b & 0xFFFu;
            res[nres].ok = ok;
            update(c, ok, ok ? (b & 0xFFFu) : 0u, a >> 24);
            mc[k].used = 0;
            nres++;
        } else if (CTX_SUM_FAIL(sum, k)) {
            uint32_t a = QKD_CTX_A(k);
            QKD_CTX_SUM = 1u << (24 + k);
            if (mc[k].revealed >= QKD_D) {                  /* nothing left to reveal: discard */
                QKD_CTRL = CTRL_DISCARD | CTRL_CTX(k);
                update(c, false, 0, a >> 24);
                res[nres].ctx = k;
                res[nres].code = mc[k].code;
                res[nres].leak_bits = 0;
                res[nres].errcnt = 0;
                res[nres].ok = 0;
                mc[k].used = 0;
                nres++;
            } else {
                uint32_t delta = next_reveal(c, (a >> 12) & 0xFFFu, QKD_D - mc[k].revealed);
                alice_request_reveals(k, mc[k].revealed, delta);
                mc[k].revealed += delta;
            }
        }
    }
    return nres;
}
