/* ZC702 functional test of PS DDR <-> simple AXI DMA <-> QKD RTL.
 * Public precomputed vectors, polling, context 0 only. No live QKD/security claim.
 * RX is armed BEFORE decode; PA input and seed MM2S channels run concurrently.
 */
#include <stdint.h>
#include <string.h>
#include "xil_cache.h"
#include "xil_io.h"
#include "xil_printf.h"
#include "xtime_l.h"
#include "smoke_vectors.h"

#define QKD 0x43c00000u
#define DMA_CH 0x40400000u
#define DMA_SYN 0x40410000u
#define DMA_PA 0x40420000u
#define DMA_SEED 0x40430000u
#define RX 0x30u
#define DMA_ERROR 0x770u
#define TIMEOUT_SECONDS 5u
static uint64_t key_rx[48] __attribute__((aligned(64)));
static uint64_t pa_rx[16] __attribute__((aligned(64)));

static uint32_t rd(uint32_t base, uint32_t off) { return Xil_In32(base + off); }
static void wr(uint32_t base, uint32_t off, uint32_t v) { Xil_Out32(base + off, v); }
static int expired(XTime start)
{
    XTime now;
    XTime_GetTime(&now);
    return now - start > (XTime)COUNTS_PER_SECOND * TIMEOUT_SECONDS;
}
static int dma_reset(uint32_t base)
{
    XTime start;
    XTime_GetTime(&start);
    wr(base, 0, 4u);  /* reset either channel resets the complete DMA */
    while (rd(base, 0) & 4u) if (expired(start)) return -1;
    return 0;
}
static int dma_start(uint32_t base, uint32_t channel, const void *buf, uint32_t bytes)
{
    UINTPTR address = (UINTPTR)buf;
    if ((address & 63u) || bytes == 0 || bytes > 0x3ffffffu) return -1;
    Xil_DCacheFlushRange(address, bytes);
    wr(base, channel + 4u, 0x7000u); /* clear old interrupt status; interrupts remain disabled */
    wr(base, channel, 1u);
    wr(base, channel + 0x18u, (uint32_t)address);
    wr(base, channel + 0x1cu, 0u);
    wr(base, channel + 0x28u, bytes); /* starts transfer */
    return 0;
}
static int dma_wait(uint32_t base, uint32_t channel, uint32_t bytes)
{
    XTime start;
    XTime_GetTime(&start);
    for (;;) {
        uint32_t st = rd(base, channel + 4u);
        if (st & DMA_ERROR) {
            xil_printf("DMA_ERROR base=%08x channel=%x status=%08x\r\n", base, channel, st);
            return -1;
        }
        if ((st & 0x1002u) == 0x1002u) {
            if (channel == RX && rd(base, channel + 0x28u) != bytes) return -1;
            return 0;
        }
        if (expired(start)) {
            xil_printf("DMA_TIMEOUT base=%08x channel=%x status=%08x\r\n", base, channel, st);
            return -1;
        }
    }
}
static int qkd_wait(uint32_t mask, uint32_t *status)
{
    XTime start;
    XTime_GetTime(&start);
    do {
        *status = rd(QKD, 0x0cu);
        if (*status & mask) return 0;
    } while (!expired(start));
    xil_printf("QKD_TIMEOUT mask=%08x status=%08x\r\n", mask, *status);
    return -1;
}
static int test_ir(uint32_t block)
{
    const smoke_vector_t *v = &smoke_vectors[block];
    uint32_t st, cursor = 0, a;
    if (dma_reset(DMA_CH) || dma_reset(DMA_SYN)) return -1;
    wr(QKD, 0x1cu, 0u);
    wr(QKD, 0x0cu, 0x103u);
    wr(QKD, 0x2cu, 0xffff0000u);
    wr(QKD, 0x28u, 0u);
    wr(QKD, 0x08u, v->cfg);
    wr(QKD, 0x20u, v->cfg2 | 0x10u); /* HOLD: arm RX before any attempt */
    memset(key_rx, 0xa5, sizeof(key_rx));
    if (dma_start(DMA_CH, RX, key_rx, sizeof(key_rx)) ||
        dma_start(DMA_CH, 0, v->ch, 192u * 4u) ||
        dma_start(DMA_SYN, 0, v->syn, v->syn_words * 4u)) return -1;
    if (dma_wait(DMA_CH, 0, 768u) || dma_wait(DMA_SYN, 0, v->syn_words * 4u) || qkd_wait(8u, &st)) return -1;
    for (uint32_t k = 0; k < v->pre; k++) wr(QKD, 0x18u, v->reveal[cursor++]);
    for (a = 0; a < v->attempts; a++) {
        uint32_t expected = v->expected[a];
        uint32_t converged = expected >> 31;
        wr(QKD, 0x0cu, 3u);
        wr(QKD, 0x04u, 1u);
        if (qkd_wait(3u, &st)) return -1;
        uint32_t iters = rd(QKD, 0x10u);
        uint32_t wanted_status = (converged ? 1u : 2u) | ((expected >> 28) & 3u) << 4 |
                                 (expected & 0x0fff0000u);
        if ((st & 0x0fff0033u) != wanted_status || (iters & 0xfffu) != (expected & 0xfffu) ||
            ((iters >> 16) & 255u) != a + 1u) {
            xil_printf("IR_STATUS_MISMATCH block=%u attempt=%u status=%08x iters=%08x\r\n", block, a, st, iters);
            return -1;
        }
        if (converged) {
            if (a + 1u != v->attempts || dma_wait(DMA_CH, RX, sizeof(key_rx))) return -1;
            Xil_DCacheInvalidateRange((UINTPTR)key_rx, sizeof(key_rx));
            for (uint32_t k = 0; k < 48; k++) {
                if (key_rx[k] != v->key[k]) {
                    xil_printf("IR_KEY_MISMATCH block=%u word=%u\r\n", block, k);
                    return -1;
                }
            }
            if ((rd(QKD, 0x24u) & 0xfffu) != v->errcnt) return -1;
        } else if (a + 1u == v->attempts) {
            if (rd(DMA_CH, RX + 4u) & (0x1000u | DMA_ERROR)) return -1;
            wr(QKD, 0x04u, 2u); /* discard a block that the golden model also discards */
            if (dma_reset(DMA_CH)) return -1; /* cancel the still-armed RX */
        } else {
            for (uint32_t k = 0; k < v->counts[a]; k++) wr(QKD, 0x18u, v->reveal[cursor++]);
        }
    }
    xil_printf("QKD_IR_VECTOR_PASS block=%u attempts=%u\r\n", block, v->attempts);
    return 0;
}
static int test_pa(void)
{
    uint32_t st;
    if (dma_reset(DMA_PA) || dma_reset(DMA_SEED)) return -1;
    memset(pa_rx, 0xa5, sizeof(pa_rx));
    if (dma_start(DMA_PA, RX, pa_rx, sizeof(pa_rx))) return -1;
    wr(QKD, 0x44u, SMOKE_PA_WORDS);
    wr(QKD, 0x0cu, 0x100u);
    wr(QKD, 0x40u, 1u);
    if (dma_start(DMA_SEED, 0, pa_seed, (SMOKE_PA_WORDS + 33u) * 4u) ||
        dma_start(DMA_PA, 0, pa_x, SMOKE_PA_WORDS * 4u)) return -1;
    if (dma_wait(DMA_SEED, 0, (SMOKE_PA_WORDS + 33u) * 4u) ||
        dma_wait(DMA_PA, 0, SMOKE_PA_WORDS * 4u) || dma_wait(DMA_PA, RX, sizeof(pa_rx)) ||
        qkd_wait(0x100u, &st)) return -1;
    Xil_DCacheInvalidateRange((UINTPTR)pa_rx, sizeof(pa_rx));
    for (uint32_t k = 0; k < 16; k++) if (pa_rx[k] != pa_y[k]) return -1;
    xil_printf("QKD_PA_VECTOR_PASS bits=%u\r\n", SMOKE_PA_WORDS * 32u);
    return 0;
}
int main(void)
{
    xil_printf("QKD_ZC702_SELFTEST_START context=0 vectors=%s\r\n", SMOKE_VECTOR_SHA256);
    if (rd(QKD, 0) != 0x49520080u || rd(QKD, 0x30u) != 2u) goto fail;
    for (uint32_t b = 0; b < SMOKE_BLOCKS; b++) if (test_ir(b)) goto fail;
    if (test_pa()) goto fail;
    xil_printf("QKD_ZC702_SELFTEST_PASS blocks=%u pa=1\r\n", SMOKE_BLOCKS);
    return 0;
fail:
    dma_reset(DMA_CH); dma_reset(DMA_SYN); dma_reset(DMA_PA); dma_reset(DMA_SEED);
    xil_printf("QKD_ZC702_SELFTEST_FAIL\r\n");
    return 1;
}
