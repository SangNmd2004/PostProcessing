/* ============================================================================
 * Session Persistence & Verification Budget Architecture for ZC702
 * Implementation of Persistent Security Accounting
 * ============================================================================ */

#include "session_persistence.h"
#include <string.h>
#include <stddef.h>

static uint32_t calc_crc32(const uint8_t *data, uint32_t len)
{
    uint32_t crc = 0xFFFFFFFFu;
    for (uint32_t i = 0; i < len; i++) {
        crc ^= (uint32_t)data[i];
        for (uint32_t b = 0; b < 8u; b++) {
            crc = (crc >> 1) ^ (0xEDB88320u & (-(int32_t)(crc & 1u)));
        }
    }
    return ~crc;
}

void session_persist_init(persistent_session_t *s,
                          const uint32_t uuid[4],
                          uint32_t epoch,
                          uint32_t budget_limit)
{
    if (!s) return;
    memset(s, 0, sizeof(*s));
    s->magic = SESSION_MAGIC;
    s->version = 1u;
    if (uuid) {
        memcpy(s->session_uuid, uuid, sizeof(s->session_uuid));
    }
    s->epoch_id = epoch;
    s->state = SESSION_STATE_ACTIVE;
    s->budget_limit = (budget_limit > 0u && budget_limit <= VERIFY_BUDGET_MAX_BLOCKS)
                      ? budget_limit : VERIFY_BUDGET_MAX_BLOCKS;
    s->budget_used = 0u;
    s->tags_accepted = 0u;
    s->tags_rejected = 0u;
    s->total_reconciled_bits = 0u;
    s->total_emitted_bits = 0u;

    /* Update descriptor CRC over valid payload preceding descriptor_crc */
    uint32_t payload_len = (uint32_t)offsetof(persistent_session_t, descriptor_crc);
    s->descriptor_crc = calc_crc32((const uint8_t *)s, payload_len);
}

int session_persist_restore(persistent_session_t *s,
                            const persistent_session_t *nv_source)
{
    if (!s || !nv_source) {
        return -1;
    }

    /* Verify magic word */
    if (nv_source->magic != SESSION_MAGIC) {
        s->state = SESSION_STATE_UNINITIALIZED;
        return -1;
    }

    /* Verify CRC integrity of persistent state over payload preceding descriptor_crc */
    uint32_t payload_len = (uint32_t)offsetof(persistent_session_t, descriptor_crc);
    uint32_t expected_crc = calc_crc32((const uint8_t *)nv_source, payload_len);
    if (expected_crc != nv_source->descriptor_crc) {
        s->state = SESSION_STATE_LOCKOUT;
        return -2; /* State corrupted in NV storage */
    }

    /* Check anti-rollback / monotonicity */
    if (nv_source->budget_used > nv_source->budget_limit) {
        s->state = SESSION_STATE_LOCKOUT;
        return -3;
    }

    /* Verify monotonicity against current active session if previously initialized */
    if (s->state != SESSION_STATE_UNINITIALIZED && s->magic == SESSION_MAGIC) {
        if (nv_source->epoch_id < s->epoch_id || nv_source->budget_used < s->budget_used) {
            s->state = SESSION_STATE_LOCKOUT;
            return -4; /* Monotonic counter or epoch rollback detected */
        }
    }

    /* Copy validated state */
    memcpy(s, nv_source, sizeof(*s));
    s->epoch_id++; /* Increment epoch upon successful warm restore */

    /* Recalculate CRC with incremented epoch */
    s->descriptor_crc = calc_crc32((const uint8_t *)s, payload_len);
    return 0;
}

int session_persist_charge_verification(persistent_session_t *s,
                                        bool is_accepted)
{
    if (!s) return -1;

    if (s->state != SESSION_STATE_ACTIVE) {
        return -1; /* Session exhausted or locked out */
    }

    if (s->budget_used >= s->budget_limit) {
        s->state = SESSION_STATE_EXHAUSTED;
        return -2; /* Budget exhausted; fail-closed */
    }

    s->budget_used++;
    if (is_accepted) {
        s->tags_accepted++;
    } else {
        s->tags_rejected++;
    }

    if (s->budget_used >= s->budget_limit) {
        s->state = SESSION_STATE_EXHAUSTED;
    }

    /* Update CRC */
    uint32_t payload_len = (uint32_t)offsetof(persistent_session_t, descriptor_crc);
    s->descriptor_crc = calc_crc32((const uint8_t *)s, payload_len);

    return 0;
}

uint32_t session_persist_remaining(const persistent_session_t *s)
{
    if (!s || s->state != SESSION_STATE_ACTIVE) {
        return 0u;
    }
    if (s->budget_used >= s->budget_limit) {
        return 0u;
    }
    return s->budget_limit - s->budget_used;
}

double session_persist_calc_epsilon_cor(const persistent_session_t *s)
{
    if (!s) return 1.0;
    /* Union bound: eps_cor = N * 2^(-64) */
    double n = (double)s->budget_used;
    double two_to_64 = 18446744073709551616.0;
    return n / two_to_64;
}
