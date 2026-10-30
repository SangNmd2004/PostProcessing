#include "arm_pmu_profiler.h"

void profiler_init(void)
{
    pmu_enable_counters();
}

void profiler_start_phase(block_profile_t *prof, profile_phase_t phase)
{
    if (prof == 0 || (uint32_t)phase >= PHASE_COUNT_MAX) {
        return;
    }
    prof->phases[phase].start_cycles = pmu_get_cycle_count();
}

void profiler_stop_phase(block_profile_t *prof, profile_phase_t phase)
{
    if (prof == 0 || (uint32_t)phase >= PHASE_COUNT_MAX) {
        return;
    }
    uint32_t stop = pmu_get_cycle_count();
    prof->phases[phase].stop_cycles = stop;

    /* Handle 32-bit unsigned cycle counter wraparound cleanly */
    if (stop >= prof->phases[phase].start_cycles) {
        prof->phases[phase].elapsed_cycles = stop - prof->phases[phase].start_cycles;
    } else {
        prof->phases[phase].elapsed_cycles = (0xFFFFFFFFU - prof->phases[phase].start_cycles) + stop + 1U;
    }
}

void profiler_finalize_block(block_profile_t *prof, uint32_t cpu_freq_mhz)
{
    if (prof == 0 || cpu_freq_mhz == 0U) {
        return;
    }

    uint32_t total_cycles = 0U;
    for (uint32_t i = 0U; i < PHASE_COUNT_MAX; i++) {
        uint32_t c = prof->phases[i].elapsed_cycles;
        total_cycles += c;
        /* elapsed_ns = cycles * 1000 / cpu_freq_mhz */
        prof->phases[i].elapsed_ns = (uint32_t)(((uint64_t)c * 1000ULL) / (uint64_t)cpu_freq_mhz);
    }

    prof->total_block_cycles = total_cycles;
    prof->pure_pl_cycles = prof->phases[PHASE_PL_DECODE].elapsed_cycles;

    /* PS Overhead: DMA transfers + Tag verify */
    uint32_t ps_overhead = prof->phases[PHASE_DMA_CH_TX].elapsed_cycles +
                           prof->phases[PHASE_DMA_SYN_TX].elapsed_cycles +
                           prof->phases[PHASE_DMA_KEY_RX].elapsed_cycles +
                           prof->phases[PHASE_VERIFY_TAG].elapsed_cycles;
    prof->ps_dma_overhead_cycles = ps_overhead;

    if (total_cycles > 0U) {
        prof->pl_compute_ratio_pct = ((float)prof->pure_pl_cycles / (float)total_cycles) * 100.0f;
    } else {
        prof->pl_compute_ratio_pct = 0.0f;
    }
}
