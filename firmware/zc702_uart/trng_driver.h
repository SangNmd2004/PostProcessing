#ifndef TRNG_DRIVER_H
#define TRNG_DRIVER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * NIST SP 800-90B Online Continuous Health Testing Thresholds
 * Alpha = 2^-20 (false positive probability < 1 in 1,000,000)
 * Min-entropy estimate H >= 0.50 bits/bit
 */
#define TRNG_RCT_CUTOFF_DEFAULT     40U   /* Repetition Count Test Cutoff */
#define TRNG_APT_CUTOFF_DEFAULT    325U   /* Adaptive Proportion Test Cutoff in W=512 */
#define TRNG_APT_WINDOW_SIZE       512U

/* Register Offsets (AXI4-Lite) */
#define TRNG_REG_CTRL               0x00U
#define TRNG_REG_STATUS             0x04U
#define TRNG_REG_DATA               0x08U
#define TRNG_REG_HEALTH_CFG         0x0CU
#define TRNG_REG_DIAG               0x10U

/* Control Register Bit Masks */
#define TRNG_CTRL_ENABLE            (1U << 0)
#define TRNG_CTRL_SOFT_RESET        (1U << 1)
#define TRNG_CTRL_VN_EN             (1U << 2)
#define TRNG_CTRL_HEALTH_EN         (1U << 3)

/* Status Register Bit Masks */
#define TRNG_STATUS_READY           (1U << 0)
#define TRNG_STATUS_RCT_ALARM       (1U << 1)
#define TRNG_STATUS_APT_ALARM       (1U << 2)
#define TRNG_STATUS_HEALTH_PASS     (1U << 3)
#define TRNG_STATUS_FIFO_OCCUPANCY(x) (((x) >> 8) & 0x1FU)

typedef struct {
    uint32_t rct_alarms;
    uint32_t apt_alarms;
    uint32_t total_alarms;
    uint32_t total_samples_tested;
    bool     health_ok;
} trng_health_status_t;

/*
 * Core TRNG Driver Functions
 */
int trng_init(uintptr_t base_addr);
int trng_get_health_status(uintptr_t base_addr, trng_health_status_t *status);
int trng_read_u32(uintptr_t base_addr, uint32_t *out_word);
int trng_read_words(uintptr_t base_addr, uint32_t *out_buf, uint32_t count);
int trng_self_test(uintptr_t base_addr);

/*
 * Software Simulation / Verification Harness
 * Used when running on ARM PS without active PL synthesis or in unit testing
 */
typedef struct {
    uint16_t rct_cutoff;
    uint16_t apt_cutoff;
    uint16_t rct_count;
    uint8_t  rct_last_sample;
    bool     rct_alarm;

    uint16_t apt_window_idx;
    uint8_t  apt_target_sample;
    uint16_t apt_count;
    bool     apt_alarm;

    uint32_t total_words_generated;
} trng_sw_state_t;

void trng_sw_init(trng_sw_state_t *st, uint16_t rct_cutoff, uint16_t apt_cutoff);
bool trng_sw_feed_bit(trng_sw_state_t *st, uint8_t bit);
int  trng_sw_harvest_word(trng_sw_state_t *st, const uint8_t *raw_bits, uint32_t num_bits, uint32_t *out_word);

#ifdef __cplusplus
}
#endif

#endif /* TRNG_DRIVER_H */
