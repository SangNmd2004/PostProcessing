/* ============================================================================
 * Session Persistence & Verification Budget Architecture for ZC702
 * Target: Xilinx ZC702 (ARM Cortex-A9 + Zynq OCM / BBRAM)
 * Reference: Work items PUB04 & P04, Tomamichel et al. (2012), Lim et al. (2014)
 *
 * Implements persistent security accounting across CPU warm resets:
 *  1. Authenticated Session ID (128-bit UUID + 32-bit epoch).
 *  2. Monotonic verification counter resisting reset-rollback attacks.
 *  3. Storage in persistent On-Chip Memory (OCM 0xFFFC0000) or BBRAM.
 *  4. Fail-closed lockout if state corruption or counter replay is detected.
 * ============================================================================ */

#ifndef SESSION_PERSISTENCE_H
#define SESSION_PERSISTENCE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Standard composable correctness threshold: eps_cor = 1e-15 */
#define EPS_COR_TARGET              1e-15
#define TAG_BITS_LEN                64u
#define VERIFY_BUDGET_MAX_BLOCKS    18446u /* floor(1e-15 * 2^64) */
#define OCM_PERSISTENT_ADDR         0xFFFC0000u /* Zynq OCM bank surviving warm reset */
#define SESSION_MAGIC               0x51534553u /* 'QSES' */

typedef enum {
    SESSION_STATE_UNINITIALIZED = 0,
    SESSION_STATE_ACTIVE        = 1,
    SESSION_STATE_EXHAUSTED     = 2,
    SESSION_STATE_LOCKOUT       = 3  /* Security violation or rollback detected */
} session_state_t;

/* Authenticated persistent session descriptor (64 bytes aligned) */
typedef struct __attribute__((aligned(64))) {
    uint32_t magic;                 /* SESSION_MAGIC */
    uint32_t version;               /* Protocol layout version */
    uint32_t session_uuid[4];       /* 128-bit unique session identifier */
    uint32_t epoch_id;              /* Monotonic boot/reconnect epoch counter */
    uint32_t state;                 /* session_state_t */
    uint32_t budget_limit;          /* Default 18446 */
    uint32_t budget_used;           /* Total tag checks executed across resets */
    uint32_t tags_accepted;         /* Successful verifications */
    uint32_t tags_rejected;         /* Failed/attack verifications */
    uint64_t total_reconciled_bits; /* Cumulative reconciled key volume */
    uint64_t total_emitted_bits;    /* Cumulative secret key volume */
    uint32_t auth_tag_low;          /* 64-bit authentication tag of state */
    uint32_t auth_tag_high;
    uint32_t descriptor_crc;        /* Integrity CRC of persistent descriptor */
} persistent_session_t;

/* Initialize persistent session descriptor */
void session_persist_init(persistent_session_t *s,
                          const uint32_t uuid[4],
                          uint32_t epoch,
                          uint32_t budget_limit);

/* Check and restore session from persistent memory across boot/reset */
int session_persist_restore(persistent_session_t *s,
                            const persistent_session_t *nv_source);

/* Charge one verification attempt; fail-closed when limit is reached */
int session_persist_charge_verification(persistent_session_t *s,
                                        bool is_accepted);

/* Query remaining verification checks permitted in current session */
uint32_t session_persist_remaining(const persistent_session_t *s);

/* Verify union bound composable security */
double session_persist_calc_epsilon_cor(const persistent_session_t *s);

#ifdef __cplusplus
}
#endif

#endif /* SESSION_PERSISTENCE_H */
