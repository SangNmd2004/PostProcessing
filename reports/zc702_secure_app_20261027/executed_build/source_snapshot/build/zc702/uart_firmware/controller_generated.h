#include <math.h>
#include <stdbool.h>
#include "qkd_pp_regs.h"
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

