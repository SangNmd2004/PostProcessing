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

