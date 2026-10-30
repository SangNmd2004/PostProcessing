/* ============================================================================
 * PE Accounting: Parameter Estimation Sample Leakage Removal & Error Counting
 * Implementation for Xilinx ZC702 Post-Processing Subsystem
 *
 * Formal Security Guarantees:
 * - Mode A: Independent X-basis test pulses ensure I(E; Z_key | X_PE) = 0.
 * - Mode B1: Disclosed Z-basis PE bits are excised before PA compression,
 *   preventing direct classical leakage into Hankel hashing.
 * - Mode B2: Disclosed Z-basis PE bits are charged as additional leakage in
 *   information reconciliation (leak_total = leak_EC + leak_tag + leak_PE).
 * ============================================================================ */

#include "pe_accounting.h"
#include <string.h>

void pe_session_init(pe_session_t *s, uint32_t session_id, pe_mode_t mode, double eps_pe)
{
    if (!s) return;
    s->session_id = session_id;
    s->mode = mode;
    s->sample_size_bits = PE_SAMPLE_BITS_DEFAULT;
    s->eps_pe = (eps_pe > 0.0) ? eps_pe : 1e-10;
    s->cumulative_blocks = 0;
    s->cumulative_pe_bits_disclosed = 0;
    s->cumulative_pe_leak_charged = 0;
    s->total_reconciled_bits = 0;
    s->total_key_bits_to_pa = 0;
}

int pe_remove_sample_bits(const uint32_t *in_words,
                          const uint32_t *sample_mask,
                          uint32_t in_bits,
                          uint32_t *out_words,
                          uint32_t *out_bits)
{
    if (!in_words || !sample_mask || !out_words || !out_bits) {
        return -1;
    }

    uint32_t in_words_count = (in_bits + 31u) / 32u;
    uint32_t kept_bits = 0;

    /* First pass: verify mask bit count */
    uint32_t mask_bits_count = 0;
    for (uint32_t w = 0; w < in_words_count; w++) {
        uint32_t m = sample_mask[w];
        /* Account for partial last word */
        if (w == in_words_count - 1u && (in_bits % 32u) != 0u) {
            m &= ((1u << (in_bits % 32u)) - 1u);
        }
        /* Brian Kernighan bit count */
        uint32_t temp = m;
        while (temp) {
            temp &= (temp - 1u);
            mask_bits_count++;
        }
    }

    if (mask_bits_count > in_bits) {
        return -1;
    }

    uint32_t expected_kept = in_bits - mask_bits_count;
    uint32_t out_words_count = (expected_kept + 31u) / 32u;
    memset(out_words, 0, out_words_count * sizeof(uint32_t));

    /* Second pass: extract and compact non-sampled bits */
    for (uint32_t i = 0; i < in_bits; i++) {
        uint32_t word_idx = i / 32u;
        uint32_t bit_idx  = i % 32u;
        uint32_t is_pe_sample = (sample_mask[word_idx] >> bit_idx) & 1u;

        if (!is_pe_sample) {
            uint32_t bit_val = (in_words[word_idx] >> bit_idx) & 1u;
            uint32_t out_word = kept_bits / 32u;
            uint32_t out_bit  = kept_bits % 32u;

            out_words[out_word] |= (bit_val << out_bit);
            kept_bits++;
        }
    }

    *out_bits = kept_bits;
    return (kept_bits == expected_kept) ? 0 : -1;
}

int pe_account_block(pe_session_t *s,
                     uint32_t block_index,
                     uint32_t reconciled_bits,
                     uint32_t pe_bits,
                     uint32_t pe_errors,
                     pe_block_record_t *rec)
{
    if (!s || !rec) {
        return -1;
    }
    if (pe_bits == 0u || pe_errors > pe_bits) {
        rec->valid = false;
        return -1;
    }

    rec->block_index = block_index;
    rec->mode = s->mode;
    rec->reconciled_bits = reconciled_bits;
    rec->pe_bits_sampled = pe_bits;
    rec->pe_errors_observed = pe_errors;
    rec->q_pe = (float)pe_errors / (float)pe_bits;
    rec->valid = true;

    switch (s->mode) {
    case PE_MODE_INDEPENDENT_X_BASIS:
        /* X-basis parameter estimation: 0 disclosed Z-basis key bits */
        rec->key_bits_to_pa = reconciled_bits;
        rec->pe_leak_charged = 0u;
        break;

    case PE_MODE_Z_BASIS_REMOVAL:
        /* Z-basis bits excised prior to PA */
        if (reconciled_bits < pe_bits) {
            rec->valid = false;
            return -1;
        }
        rec->key_bits_to_pa = reconciled_bits - pe_bits;
        rec->pe_leak_charged = 0u; /* Already removed from message length */
        s->cumulative_pe_bits_disclosed += pe_bits;
        break;

    case PE_MODE_Z_BASIS_INFLATION:
        /* Z-basis bits retained in Hankel input; charged as leakage */
        rec->key_bits_to_pa = reconciled_bits;
        rec->pe_leak_charged = pe_bits;
        s->cumulative_pe_bits_disclosed += pe_bits;
        s->cumulative_pe_leak_charged += pe_bits;
        break;

    default:
        rec->valid = false;
        return -1;
    }

    s->cumulative_blocks++;
    s->total_reconciled_bits += reconciled_bits;
    s->total_key_bits_to_pa += rec->key_bits_to_pa;

    return 0;
}

bool pe_verify_epsilon_budget(const pe_session_t *s, double max_budget)
{
    if (!s) return false;
    /* Composable epsilon allocation check */
    if (s->eps_pe > max_budget) {
        return false;
    }
    return true;
}
