#ifndef ARM_PMU_PROFILER_H
#define ARM_PMU_PROFILER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Phase Identifiers for High-Resolution Timestamping
 */
typedef enum {
    PHASE_DMA_CH_TX     = 0, // DMA Transfer Channel bits
    PHASE_DMA_SYN_TX    = 1, // DMA Transfer Alice Syndrome
    PHASE_PL_DECODE     = 2, // Pure PL QC-LDPC Decode
    PHASE_DMA_KEY_RX    = 3, // DMA Receive Decoded Key
    PHASE_VERIFY_TAG    = 4, // 64-bit Verification Tag Evaluation
    PHASE_PA_PASS       = 5, // Hankel PA Pass
    PHASE_COUNT_MAX     = 6
} profile_phase_t;

typedef struct {
    uint32_t start_cycles;
    uint32_t stop_cycles;
    uint32_t elapsed_cycles;
    uint32_t elapsed_ns;
} phase_record_t;

typedef struct {
    phase_record_t phases[PHASE_COUNT_MAX];
    uint32_t       total_block_cycles;
    uint32_t       pure_pl_cycles;
    uint32_t       ps_dma_overhead_cycles;
    float          pl_compute_ratio_pct;
} block_profile_t;

/*
 * ARM Cortex-A9 Performance Monitor Unit (PMU) Inline Functions
 * Accesses CP15 Cycle Count Register (PMCCNTR)
 */
static inline uint32_t pmu_get_cycle_count(void)
{
    uint32_t cycles = 0U;
#if defined(__arm__) || defined(__aarch64__)
    __asm__ volatile ("mrc p15, 0, %0, c9, c13, 0" : "=r" (cycles));
#else
    /* Non-ARM fallback simulation counter */
    static uint32_t sim_cycle_cnt = 0U;
    sim_cycle_cnt += 100U;
    cycles = sim_cycle_cnt;
#endif
    return cycles;
}

static inline void pmu_enable_counters(void)
{
#if defined(__arm__) || defined(__aarch64__)
    /* Set PMCR E (bit 0) and C (bit 2) to enable and reset cycle counter */
    uint32_t pmcr = 0U;
    __asm__ volatile ("mrc p15, 0, %0, c9, c12, 0" : "=r" (pmcr));
    pmcr |= 0x05U;
    __asm__ volatile ("mcr p15, 0, %0, c9, c12, 0" : : "r" (pmcr));
    /* Enable cycle counter in PMCNTENSET (bit 31) */
    uint32_t mask = (1U << 31);
    __asm__ volatile ("mcr p15, 0, %0, c9, c12, 1" : : "r" (mask));
#endif
}

/*
 * Profiler Driver API
 */
void profiler_init(void);
void profiler_start_phase(block_profile_t *prof, profile_phase_t phase);
void profiler_stop_phase(block_profile_t *prof, profile_phase_t phase);
void profiler_finalize_block(block_profile_t *prof, uint32_t cpu_freq_mhz);

#ifdef __cplusplus
}
#endif

#endif /* ARM_PMU_PROFILER_H */
