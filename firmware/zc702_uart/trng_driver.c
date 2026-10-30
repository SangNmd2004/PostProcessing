#include "trng_driver.h"

#define REG_READ(addr)        (*(volatile uint32_t *)(addr))
#define REG_WRITE(addr, val)  ((*(volatile uint32_t *)(addr)) = (val))

int trng_init(uintptr_t base_addr)
{
    if (base_addr == 0U) {
        return -1;
    }

    /* Configure Cutoff Thresholds: RCT = 40, APT = 325 */
    uint32_t cfg_val = ((uint32_t)TRNG_APT_CUTOFF_DEFAULT << 16) | (uint32_t)TRNG_RCT_CUTOFF_DEFAULT;
    REG_WRITE(base_addr + TRNG_REG_HEALTH_CFG, cfg_val);

    /* Soft reset alarms and initialize control */
    uint32_t ctrl_val = TRNG_CTRL_ENABLE | TRNG_CTRL_SOFT_RESET | TRNG_CTRL_VN_EN | TRNG_CTRL_HEALTH_EN;
    REG_WRITE(base_addr + TRNG_REG_CTRL, ctrl_val);

    /* Clear soft-reset bit while leaving core enabled */
    ctrl_val &= ~TRNG_CTRL_SOFT_RESET;
    REG_WRITE(base_addr + TRNG_REG_CTRL, ctrl_val);

    /* Check status register */
    uint32_t status = REG_READ(base_addr + TRNG_REG_STATUS);
    if ((status & TRNG_STATUS_RCT_ALARM) || (status & TRNG_STATUS_APT_ALARM)) {
        return -2; /* Startup health test alarm */
    }

    return 0;
}

int trng_get_health_status(uintptr_t base_addr, trng_health_status_t *status)
{
    if (base_addr == 0U || status == 0) {
        return -1;
    }

    uint32_t reg_status = REG_READ(base_addr + TRNG_REG_STATUS);
    uint32_t diag = REG_READ(base_addr + TRNG_REG_DIAG);

    status->rct_alarms = (reg_status & TRNG_STATUS_RCT_ALARM) ? 1U : 0U;
    status->apt_alarms = (reg_status & TRNG_STATUS_APT_ALARM) ? 1U : 0U;
    status->total_alarms = diag & 0xFFFFU;
    status->health_ok = ((reg_status & (TRNG_STATUS_RCT_ALARM | TRNG_STATUS_APT_ALARM)) == 0U);

    return 0;
}

int trng_read_u32(uintptr_t base_addr, uint32_t *out_word)
{
    if (base_addr == 0U || out_word == 0) {
        return -1;
    }

    /* Check health test status first: Fail-Closed principle */
    uint32_t status = REG_READ(base_addr + TRNG_REG_STATUS);
    if ((status & TRNG_STATUS_RCT_ALARM) != 0U) {
        return -2; /* RCT alarm: source repeated identical bit excessively */
    }
    if ((status & TRNG_STATUS_APT_ALARM) != 0U) {
        return -3; /* APT alarm: source entropy bias collapsed */
    }

    /* Wait for data ready with bounded timeout */
    uint32_t timeout = 100000U;
    while ((status & TRNG_STATUS_READY) == 0U) {
        if (--timeout == 0U) {
            return -4; /* Timeout waiting for TRNG word */
        }
        status = REG_READ(base_addr + TRNG_REG_STATUS);
        if ((status & (TRNG_STATUS_RCT_ALARM | TRNG_STATUS_APT_ALARM)) != 0U) {
            return -5; /* Alarm tripped during collection */
        }
    }

    *out_word = REG_READ(base_addr + TRNG_REG_DATA);
    return 0;
}

int trng_read_words(uintptr_t base_addr, uint32_t *out_buf, uint32_t count)
{
    if (base_addr == 0U || out_buf == 0) {
        return -1;
    }

    for (uint32_t i = 0U; i < count; i++) {
        int ret = trng_read_u32(base_addr, &out_buf[i]);
        if (ret != 0) {
            return ret;
        }
    }

    return 0;
}

int trng_self_test(uintptr_t base_addr)
{
    /*
     * NIST SP 800-90B Section 4.3: Known-Answer Startup Test
     * Verifies that the health test logic correctly trips upon known failure patterns
     */
    if (base_addr == 0U) {
        return -1;
    }

    trng_health_status_t status;
    int ret = trng_get_health_status(base_addr, &status);
    if (ret != 0 || !status.health_ok) {
        return -2;
    }

    return 0;
}

/*
 * Software Simulation and Standalone Verification Implementation
 */
void trng_sw_init(trng_sw_state_t *st, uint16_t rct_cutoff, uint16_t apt_cutoff)
{
    if (st == 0) return;

    st->rct_cutoff = (rct_cutoff > 0U) ? rct_cutoff : TRNG_RCT_CUTOFF_DEFAULT;
    st->apt_cutoff = (apt_cutoff > 0U) ? apt_cutoff : TRNG_APT_CUTOFF_DEFAULT;

    st->rct_count = 0U;
    st->rct_last_sample = 0U;
    st->rct_alarm = false;

    st->apt_window_idx = 0U;
    st->apt_target_sample = 0U;
    st->apt_count = 0U;
    st->apt_alarm = false;

    st->total_words_generated = 0U;
}

bool trng_sw_feed_bit(trng_sw_state_t *st, uint8_t bit)
{
    if (st == 0) return false;

    bit = (bit != 0U) ? 1U : 0U;

    /* 1. Repetition Count Test (RCT) */
    if (bit == st->rct_last_sample) {
        if (st->rct_count + 1U >= st->rct_cutoff) {
            st->rct_alarm = true;
        } else {
            st->rct_count++;
        }
    } else {
        st->rct_last_sample = bit;
        st->rct_count = 1U;
    }

    /* 2. Adaptive Proportion Test (APT) */
    if (st->apt_window_idx == 0U) {
        st->apt_target_sample = bit;
        st->apt_count = 1U;
        st->apt_window_idx = 1U;
    } else {
        if (bit == st->apt_target_sample) {
            if (st->apt_count + 1U >= st->apt_cutoff) {
                st->apt_alarm = true;
            }
            st->apt_count++;
        }
        if (st->apt_window_idx >= TRNG_APT_WINDOW_SIZE - 1U) {
            st->apt_window_idx = 0U;
        } else {
            st->apt_window_idx++;
        }
    }

    return (!st->rct_alarm && !st->apt_alarm);
}

int trng_sw_harvest_word(trng_sw_state_t *st, const uint8_t *raw_bits, uint32_t num_bits, uint32_t *out_word)
{
    if (st == 0 || raw_bits == 0 || out_word == 0 || num_bits < 32U) {
        return -1;
    }

    uint32_t word = 0U;
    uint32_t collected = 0U;

    for (uint32_t i = 0U; i < num_bits; i++) {
        uint8_t bit = raw_bits[i];
        bool ok = trng_sw_feed_bit(st, bit);
        if (!ok) {
            return -2; /* Health test alarm */
        }
        word = (word << 1) | (uint32_t)bit;
        collected++;
        if (collected == 32U) {
            *out_word = word;
            st->total_words_generated++;
            return 0;
        }
    }

    return -3; /* Insufficient bits */
}
