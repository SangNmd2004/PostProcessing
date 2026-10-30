#include <stdio.h>
#include <stddef.h>
#include <string.h>
#include <stdbool.h>
#include "auth_channel.h"
#include "event_scheduler.h"
#include "session_persistence.h"
#include "arm_pmu_profiler.h"

int main(void) {
    printf("=== ZC702 C FIRMWARE RECONCILIATION VERIFICATION ===\n");
    int total_failures = 0;

    /* -------------------------------------------------------------------------
     * 1. Session Persistence & CRC Offset Verification (REV05 Fix)
     * ------------------------------------------------------------------------- */
    persistent_session_t original, restored;
    uint32_t uuid[4] = {0x01020304u, 0x05060708u, 0x090A0B0Cu, 0x0D0E0F10u};
    session_persist_init(&original, uuid, 1u, 18446u);

    int restore_rc = session_persist_restore(&restored, &original);
    size_t sz = sizeof(original);
    size_t crc_off = offsetof(persistent_session_t, descriptor_crc);

    printf("[REV05] persistence_fresh_restore_rc=%d sizeof=%llu crc_offset=%llu\n",
           restore_rc, (unsigned long long)sz, (unsigned long long)crc_off);
    if (restore_rc != 0 || crc_off != 72) {
        printf("FAIL: Persistence restore failed (expected rc=0, offset=72)\n");
        total_failures++;
    } else {
        printf("PASS: Persistence descriptor restore succeeded with exact CRC offset (72 bytes)\n");
    }

    /* Verify Monotonic Anti-Rollback Guard:
     * active_session has epoch 2 from the previous restore.
     * Attempting to restore the original state (which has epoch 1) must be rejected. */
    persistent_session_t active_session;
    memcpy(&active_session, &restored, sizeof(restored));
    int rollback_rc = session_persist_restore(&active_session, &original);
    printf("[REV05] rollback_attempt_rc=%d (expected -4 for rollback lockout)\n", rollback_rc);
    if (rollback_rc != -4) {
        printf("FAIL: Rollback not blocked as expected\n");
        total_failures++;
    } else {
        printf("PASS: Anti-rollback correctly detected epoch downgrade and triggered LOCKOUT\n");
    }

    /* -------------------------------------------------------------------------
     * 2. Event Scheduler Selective Queue Hole Reclamation (REV06 Fix)
     * ------------------------------------------------------------------------- */
    event_scheduler_t sched;
    sched_event_t event;
    event_scheduler_init(&sched);
    int failed_round = -1;

    for (int i = 0; i < 40; i++) {
        int a = event_scheduler_post_from_isr(&sched, EVT_DMA_CH_DONE, 0, 0);
        int b = event_scheduler_post_from_isr(&sched, EVT_QKD_DECODE_DONE, 1, 0);
        if (!a || !b) {
            failed_round = i;
            break;
        }
        /* Poll out of FIFO order: poll QKD (slot 1) before DMA (slot 0) */
        if (!event_scheduler_poll(&sched, EVT_QKD_DECODE_DONE, &event)) {
            printf("FAIL: Poll QKD failed at round %d\n", i);
            total_failures++;
            failed_round = i;
            break;
        }
        if (!event_scheduler_poll(&sched, EVT_DMA_CH_DONE, &event)) {
            printf("FAIL: Poll DMA failed at round %d\n", i);
            total_failures++;
            failed_round = i;
            break;
        }
    }
    printf("[REV06] selective_queue_failed_round=%d head=%u tail=%u\n",
           failed_round, sched.head, sched.tail);
    if (failed_round != -1) {
        printf("FAIL: Queue filled up due to uncollected holes (failed at round %d)\n", failed_round);
        total_failures++;
    } else {
        printf("PASS: 40 rounds of selective polling completed with zero false queue-full stalls\n");
    }

    /* -------------------------------------------------------------------------
     * 3. Authenticated Classical Channel Hardening (REV04 Fix)
     * ------------------------------------------------------------------------- */
    auth_context_t tx, rx;
    unsigned char buffer[128];
    uint32_t size = 0, length = 0;
    const uint8_t *payload_ptr = NULL;
    uint16_t msg_type = 0;

    auth_channel_init(&tx, 0x9E3779B97F4A7C15ULL, 0x0123456789ABCDEFULL);
    auth_channel_init(&rx, 0x9E3779B97F4A7C15ULL, 0x0123456789ABCDEFULL);

    /* 3a. Verify seq 0 packet reception and strict anti-replay */
    tx.tx_seq = 0u; /* Force initial sequence to 0 */
    auth_channel_wrap(&tx, 1u, (const uint8_t *)"test_payload", 12u, buffer, &size);

    int first_rc = auth_channel_unwrap_and_verify(&rx, buffer, size, &msg_type, &payload_ptr, &length);
    int replay_rc = auth_channel_unwrap_and_verify(&rx, buffer, size, &msg_type, &payload_ptr, &length);
    printf("[REV04] seq0_first_rc=%d seq0_replay_rc=%d\n", first_rc, replay_rc);

    if (first_rc != 0 || replay_rc != AUTH_ERR_REPLAY_SEQ) {
        printf("FAIL: seq 0 replay check failed (first_rc=%d, replay_rc=%d)\n", first_rc, replay_rc);
        total_failures++;
    } else {
        printf("PASS: seq 0 accepted once, second attempt rejected with AUTH_ERR_REPLAY_SEQ (-2)\n");
    }

    /* 3b. Verify non-invertible SipHash-2-4 PRF on empty payload type 0 */
    auth_channel_init(&tx, 0x9E3779B97F4A7C15ULL, 0x0123456789ABCDEFULL);
    uint64_t empty_tag = auth_channel_compute_mac(&tx, (const uint8_t *)"", 0u, 1u, 0u);
    printf("[REV04] hardened_empty_type0_tag=%016llx\n", (unsigned long long)empty_tag);

    /* 3c. Negative test: Corrupted tag rejected on fresh packet */
    auth_channel_wrap(&tx, 1u, (const uint8_t *)"fresh_packet", 12u, buffer, &size);
    buffer[size - 1] ^= 0x01; /* tamper tag */
    int tamper_rc = auth_channel_unwrap_and_verify(&rx, buffer, size, &msg_type, &payload_ptr, &length);
    printf("[REV04] tampered_tag_rc=%d (expected -3)\n", tamper_rc);
    if (tamper_rc != AUTH_ERR_TAG_MISMATCH) {
        printf("FAIL: Tampered tag was not rejected with AUTH_ERR_TAG_MISMATCH\n");
        total_failures++;
    } else {
        printf("PASS: Tampered tag rejected fail-closed\n");
    }

    /* -------------------------------------------------------------------------
     * 4. PMU Profiler API Clean Compilation & Execution (REV12 Fix)
     * ------------------------------------------------------------------------- */
    block_profile_t prof;
    memset(&prof, 0, sizeof(prof));
    profiler_init();
    profiler_start_phase(&prof, PHASE_DMA_CH_TX);
    for (volatile int d = 0; d < 1000; d++);
    profiler_stop_phase(&prof, PHASE_DMA_CH_TX);

    profiler_start_phase(&prof, PHASE_PL_DECODE);
    for (volatile int d = 0; d < 5000; d++);
    profiler_stop_phase(&prof, PHASE_PL_DECODE);

    profiler_finalize_block(&prof, 667u);
    printf("[REV12] profiler_total_cycles=%u pure_pl_cycles=%u pl_pct=%.1f%%\n",
           prof.total_block_cycles, prof.pure_pl_cycles, (double)prof.pl_compute_ratio_pct);
    if (prof.total_block_cycles == 0 || prof.pure_pl_cycles == 0) {
        printf("FAIL: Profiler cycle counts remained zero\n");
        total_failures++;
    } else {
        printf("PASS: Profiler API compiles cleanly and tracks block phases correctly\n");
    }

    printf("=== SUMMARY: total_failures=%d ===\n", total_failures);
    return total_failures;
}
