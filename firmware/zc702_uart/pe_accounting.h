/* ============================================================================
 * PE Accounting: Parameter Estimation Sample Leakage Removal & Error Counting
 * Target: Xilinx ZC702 (ARM Cortex-A9 bare-metal / RTOS)
 * Reference: Lim et al. (2014), Tomamichel et al. (2012)
 *
 * Provides exact accounting of parameter estimation (PE) disclosure:
 *  1. Mode A (Independent X-basis): Zero key bits disclosed, zero PE leakage.
 *  2. Mode B1 (Z-basis Physical Removal): 256 PE bits excised before PA;
 *     compacts 2765 reconciled bits -> 2509 key bits for Hankel PA.
 *  3. Mode B2 (Z-basis Leakage Inflation): 256 PE bits retained in PA input,
 *     but 256 bits added to leak_EC to formally subtract Eve's knowledge.
 * ============================================================================ */

#ifndef PE_ACCOUNTING_H
#define PE_ACCOUNTING_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PE_SAMPLE_BITS_DEFAULT  256u
#define PE_RECONCILED_BITS_NKEY 2765u
#define PE_COMPACT_WORDS        79u   /* ceil((2765 - 256) / 32) = 79 uint32 words */
#define PE_RAW_WORDS            87u   /* ceil(2765 / 32) = 87 uint32 words */

typedef enum {
    PE_MODE_INDEPENDENT_X_BASIS = 0, /* Modern stream: PE from X-basis, 0 Z-key disclosure */
    PE_MODE_Z_BASIS_REMOVAL     = 1, /* Legacy/CSV: 256 bits excised prior to PA */
    PE_MODE_Z_BASIS_INFLATION   = 2  /* Legacy/CSV: 256 bits retained, leak_EC += 256 */
} pe_mode_t;

typedef struct {
    uint32_t session_id;
    pe_mode_t mode;
    uint32_t sample_size_bits;
    double eps_pe;                  /* Composable security parameter for PE */
    uint32_t cumulative_blocks;
    uint32_t cumulative_pe_bits_disclosed;
    uint32_t cumulative_pe_leak_charged;
    uint64_t total_reconciled_bits;
    uint64_t total_key_bits_to_pa;
} pe_session_t;

typedef struct {
    uint32_t block_index;
    pe_mode_t mode;
    uint32_t reconciled_bits;       /* 2765 for n=3072 minus D=307 */
    uint32_t pe_bits_sampled;       /* 256 */
    uint32_t pe_errors_observed;    /* Bit errors in sample */
    float    q_pe;                  /* Observed QBER = errors / sample_bits */
    uint32_t key_bits_to_pa;        /* 2765 (Mode A/B2) or 2509 (Mode B1) */
    uint32_t pe_leak_charged;       /* 0 (Mode A/B1) or 256 (Mode B2) */
    bool     valid;
} pe_block_record_t;

/* Initialize PE accounting session */
void pe_session_init(pe_session_t *s, uint32_t session_id, pe_mode_t mode, double eps_pe);

/* Excise 256 PE sample bits from a 2765-bit bitstream, compacting into 2509 bits.
 *  in_words:  87 uint32 words (2765 bits, LSB first)
 *  sample_mask: 87 uint32 words bitmask where 1 indicates a bit selected for PE
 *  out_words: 79 uint32 words buffer receiving 2509 compacted bits
 * Returns 0 on success, -1 on invalid parameter/mask count. */
int pe_remove_sample_bits(const uint32_t *in_words,
                          const uint32_t *sample_mask,
                          uint32_t in_bits,
                          uint32_t *out_words,
                          uint32_t *out_bits);

/* Account for one reconciled block under the configured mode */
int pe_account_block(pe_session_t *s,
                     uint32_t block_index,
                     uint32_t reconciled_bits,
                     uint32_t pe_bits,
                     uint32_t pe_errors,
                     pe_block_record_t *rec);

/* Verify that cumulative PE epsilon satisfies composable security bounds */
bool pe_verify_epsilon_budget(const pe_session_t *s, double max_budget);

#ifdef __cplusplus
}
#endif

#endif /* PE_ACCOUNTING_H */
