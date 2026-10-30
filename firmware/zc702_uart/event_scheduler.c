/* ============================================================================
 * Non-Blocking Interrupt-Driven Event Scheduler for ZC702
 * Implementation of Purely Interrupt-Driven Context Scheduling
 * ============================================================================ */

#include "event_scheduler.h"
#include <string.h>

void event_scheduler_init(event_scheduler_t *sched)
{
    if (!sched) return;
    memset(sched, 0, sizeof(*sched));
    sched->head = 0u;
    sched->tail = 0u;
    sched->active_event_mask = 0u;
    sched->total_events_handled = 0u;
    sched->total_wfi_sleep_cycles = 0u;
    sched->initialized = true;
}

bool event_scheduler_post_from_isr(event_scheduler_t *sched,
                                   sched_event_type_t type,
                                   uint8_t context_id,
                                   uint16_t status_flags)
{
    if (!sched || !sched->initialized) {
        return false;
    }

    uint32_t next_head = (sched->head + 1u) % SCHED_MAX_EVENTS;
    if (next_head == sched->tail) {
        /* Ring buffer full */
        return false;
    }

    sched_event_t *evt = &sched->queue[sched->head];
    evt->type = type;
    evt->context_id = context_id;
    evt->status_flags = status_flags;
    evt->timestamp = 0u; /* Populated by caller/hardware timer if available */

    sched->active_event_mask |= (uint32_t)type;
    sched->head = next_head;
    return true;
}

bool event_scheduler_poll(event_scheduler_t *sched,
                          uint32_t event_mask,
                          sched_event_t *out_event)
{
    if (!sched || !sched->initialized || sched->head == sched->tail) {
        return false;
    }

    /* Reclaim any leading EVT_NONE slots at tail */
    while (sched->tail != sched->head && sched->queue[sched->tail].type == EVT_NONE) {
        sched->tail = (sched->tail + 1u) % SCHED_MAX_EVENTS;
    }
    if (sched->head == sched->tail) {
        return false;
    }

    uint32_t curr = sched->tail;
    while (curr != sched->head) {
        if (sched->queue[curr].type & event_mask) {
            if (out_event) {
                *out_event = sched->queue[curr];
            }
            /* Advance tail if removing from front */
            if (curr == sched->tail) {
                sched->tail = (sched->tail + 1u) % SCHED_MAX_EVENTS;
            } else {
                /* Invalidate matched slot */
                sched->queue[curr].type = EVT_NONE;
            }
            /* Advance tail past any contiguous EVT_NONE slots (reclaim holes) */
            while (sched->tail != sched->head && sched->queue[sched->tail].type == EVT_NONE) {
                sched->tail = (sched->tail + 1u) % SCHED_MAX_EVENTS;
            }
            sched->total_events_handled++;
            return true;
        }
        curr = (curr + 1u) % SCHED_MAX_EVENTS;
    }
    return false;
}

bool event_scheduler_wait_wfi(event_scheduler_t *sched,
                              uint32_t event_mask,
                              sched_event_t *out_event,
                              uint32_t max_spins_timeout)
{
    if (!sched || !sched->initialized) {
        return false;
    }

    uint32_t spins = 0;
    while (spins < max_spins_timeout) {
        if (event_scheduler_poll(sched, event_mask, out_event)) {
            return true;
        }

        /* Low-power ARM Wait-For-Interrupt: halts execution pipeline
         * until an IRQ (GIC) or event occurs, zero CPU bus polling */
#if defined(__arm__) || defined(__aarch64__)
        __asm__ volatile ("wfi");
#endif
        sched->total_wfi_sleep_cycles++;
        spins++;
    }

    /* Timeout expired */
    return false;
}
