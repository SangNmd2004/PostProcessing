/* ============================================================================
 * Non-Blocking Interrupt-Driven Event Scheduler for ZC702
 * Target: Xilinx ZC702 (Dual ARM Cortex-A9 + Zynq SCUGIC)
 * Reference: Work item P07, ARMv7-A Architecture Reference Manual
 *
 * Implements purely interrupt-driven DMA and context scheduling:
 *  1. Non-blocking event ring buffer with low-power WFI (Wait-For-Interrupt).
 *  2. GIC ISR dispatch for DMA MM2S/S2MM and QKD PL decode IRQs.
 *  3. Elimination of CPU polling loops during hardware compute and transfers.
 * ============================================================================ */

#ifndef EVENT_SCHEDULER_H
#define EVENT_SCHEDULER_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SCHED_MAX_EVENTS        32u
#define SCHED_MAX_CONTEXTS      4u

typedef enum {
    EVT_NONE            = 0,
    EVT_DMA_CH_DONE     = (1u << 0), /* Channel LLR DMA MM2S/S2MM complete */
    EVT_DMA_SYN_DONE    = (1u << 1), /* Syndrome DMA MM2S complete */
    EVT_QKD_DECODE_DONE = (1u << 2), /* PL QC-LDPC decoding finished (IRQ) */
    EVT_DMA_PA_DONE     = (1u << 3), /* PA key DMA MM2S/S2MM complete */
    EVT_DMA_SEED_DONE   = (1u << 4), /* PA seed DMA MM2S complete */
    EVT_UART_RX_READY   = (1u << 5), /* Classical packet available */
    EVT_TIMEOUT         = (1u << 6), /* Watchdog timer expiration */
    EVT_ERROR           = (1u << 7)  /* Hardware bus or DMA fault */
} sched_event_type_t;

typedef struct {
    sched_event_type_t type;
    uint8_t            context_id;   /* 0..3 */
    uint16_t           status_flags; /* Hardware status at interrupt time */
    uint32_t           timestamp;    /* Timer tick when event fired */
} sched_event_t;

typedef struct {
    sched_event_t queue[SCHED_MAX_EVENTS];
    volatile uint32_t head;
    volatile uint32_t tail;
    volatile uint32_t active_event_mask;
    uint32_t total_events_handled;
    uint32_t total_wfi_sleep_cycles;
    bool     initialized;
} event_scheduler_t;

/* Initialize event scheduler and non-blocking queue */
void event_scheduler_init(event_scheduler_t *sched);

/* Post an event from ISR (interrupt-safe, lockless single-producer single-consumer) */
bool event_scheduler_post_from_isr(event_scheduler_t *sched,
                                   sched_event_type_t type,
                                   uint8_t context_id,
                                   uint16_t status_flags);

/* Non-blocking poll for pending events matching mask */
bool event_scheduler_poll(event_scheduler_t *sched,
                          uint32_t event_mask,
                          sched_event_t *out_event);

/* Blocking sleep in WFI until an event matching mask is posted */
bool event_scheduler_wait_wfi(event_scheduler_t *sched,
                              uint32_t event_mask,
                              sched_event_t *out_event,
                              uint32_t max_spins_timeout);

#ifdef __cplusplus
}
#endif

#endif /* EVENT_SCHEDULER_H */
