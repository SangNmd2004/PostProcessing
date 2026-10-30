/* UART vector receiver, protocol v1. Included after the existing DMA self-test
 * helpers by build_uart.py. Public test vectors only; context 0, polling. */
#include "xuartps_hw.h"
#define UART_BASE 0xe0001000u
#define FRAME_MAGIC 0x51564431u
#define MAX_WORDS 4096u
#include "hw_profiler.h"
static uint32_t frame[MAX_WORDS] __attribute__((aligned(64)));
static uint32_t channel_data[192] __attribute__((aligned(64)));
static uint32_t syndrome_data[48] __attribute__((aligned(64)));
static uint64_t expected_key[48] __attribute__((aligned(64)));

static int receive_bytes(void *dest, uint32_t bytes)
{
    unsigned char *p = dest;
    XTime start;
    XTime_GetTime(&start);
    for (uint32_t i = 0; i < bytes; i++) {
        while (!XUartPs_IsReceiveData(UART_BASE)) {
            XTime now;
            XTime_GetTime(&now);
            if (now - start > (XTime)COUNTS_PER_SECOND * 30u) return -1;
        }
        p[i] = Xil_In32(UART_BASE + XUARTPS_FIFO_OFFSET) & 255u;
    }
    return 0;
}
static uint32_t frame_crc(const unsigned char *p, uint32_t n)
{
    uint32_t c = 0xffffffffu;
    for (uint32_t i = 0; i < n; i++) {
        c ^= p[i];
        for (uint32_t k = 0; k < 8; k++) c = (c >> 1) ^ (0xedb88320u & (0u - (c & 1u)));
    }
    return ~c;
}
static int unpack_vector(uint32_t n, smoke_vector_t *v)
{
    if (n < 7u) return -1;
    v->cfg = frame[0]; v->cfg2 = frame[1]; v->pre = frame[2];
    v->attempts = frame[3]; v->syn_words = frame[4]; v->errcnt = frame[5];
    uint32_t nr = frame[6], a = v->attempts;
    const uint32_t syn_sizes[4] = {48u, 32u, 24u, 16u};
    if (!a || a > 16u || v->syn_words != syn_sizes[v->cfg & 3u] || nr > 3072u ||
        v->pre > nr || v->errcnt > 3072u ||
        n != 7u + 2u*a + 192u + v->syn_words + nr + 96u) return -1;
    v->expected = frame + 7; v->counts = v->expected + a;
    uint32_t total = v->pre;
    for (uint32_t i = 0; i < a; i++) {
        if (v->counts[i] > nr || (i + 1u < a && (v->expected[i] >> 31))) return -1;
        total += v->counts[i];
    }
    if (total != nr || v->counts[a-1] != 0u) return -1;
    const uint32_t *p = v->counts + a;
    memcpy(channel_data, p, sizeof(channel_data)); p += 192;
    memcpy(syndrome_data, p, v->syn_words * 4u); p += v->syn_words;
    v->reveal = p; p += nr;
    for (uint32_t i = 0; i < nr; i++)
        if ((v->reveal[i] & 0xfffe0000u) || (v->reveal[i] & 0xffffu) >= 3072u) return -1;
    memcpy(expected_key, p, sizeof(expected_key));
    v->ch = channel_data; v->syn = syndrome_data; v->key = expected_key;
    return 0;
}
#include "functional.h"
int main(void)
{
    uint32_t passed = 0;
    if (rd(QKD, 0) != 0x49520080u || rd(QKD, 0x30u) != 2u || test_pa()) {
        xil_printf("QKD_UART_FATAL startup\r\n"); return 1;
    }
    xil_printf("QKD_UART_READY version=1 max_words=%u\r\n", MAX_WORDS);
    for (;;) {
        uint32_t header[4];
        /* Waiting between frames is unbounded; a partial frame has a timeout. */
        while (!XUartPs_IsReceiveData(UART_BASE)) {}
        hp_begin_frame();hp_mark_t wire_start=hp_mark();
        if (receive_bytes(header, sizeof(header))) goto fatal;
        if ((header[0] != FRAME_MAGIC && header[0] != FUNC_MAGIC) || header[2] > MAX_WORDS) goto fatal;
        uint32_t seq = header[1], n = header[2];
        if (n == 0u) {
            if (header[3] != 0u) goto fatal;
            xil_printf("QKD_UART_DONE passed=%u\r\n", passed);
            xil_printf("QKD_UART_READY version=1 max_words=%u\r\n", MAX_WORDS);
            continue;
        }
        xil_printf("QKD_UART_ACCEPT seq=%u\r\n", seq);
        for (uint32_t off = 0; off < n * 4u;) {
            uint32_t chunk = n * 4u - off;
            if (chunk > 128u) chunk = 128u;
            if (receive_bytes((unsigned char *)frame + off, chunk)) goto fatal;
            off += chunk;
            xil_printf("QKD_UART_ACK seq=%u bytes=%u\r\n", seq, off);
        }
        hp_add(HP_UART_RX_ACK,wire_start);hp_mark_t crc_start=hp_mark();
        uint32_t payload_crc=frame_crc((unsigned char *)frame,n*4u);hp_add(HP_CRC,crc_start);
        if (payload_crc != header[3]) {
            xil_printf("QKD_UART_CRC_REJECT seq=%u\r\n", seq);
            continue;
        }
        if (header[0]==FUNC_MAGIC) {
            uint32_t command_op=frame[0];
            hp_mark_t operation_start=hp_mark();
            if (functional_command(n,seq)) goto fatal;
            if (command_op!=74u&&command_op!=75u) {
                hp_add(HP_COMMAND_PRINTF,operation_start);
                if (hp_enabled) {
                    hp_mark_t drain=hp_mark();
                    while (!(Xil_In32(UART_BASE+XUARTPS_SR_OFFSET)&XUARTPS_SR_TXEMPTY)||
                           (Xil_In32(UART_BASE+XUARTPS_SR_OFFSET)&XUARTPS_SR_TACTIVE))
                        if (expired(drain.tick)) goto fatal;
                    hp_add(HP_TX_DRAIN,drain);
                }
                hp_finish(seq,command_op);
            }
            continue;
        }
        smoke_vector_t v;
        if (unpack_vector(n, &v)) goto fatal;
        if (test_ir_vector(&v, seq)) goto fatal;
        passed++;
        xil_printf("QKD_UART_RESULT seq=%u crc=%08x conv=%u attempts=%u errcnt=%u\r\n",
                   seq, header[3], v.expected[v.attempts-1] >> 31, v.attempts,
                   rd(QKD, 0x24u) & 0xfffu);
    }
fatal:
    dma_reset(DMA_CH); dma_reset(DMA_SYN); dma_reset(DMA_PA); dma_reset(DMA_SEED);
    xil_printf("QKD_UART_FATAL stopped\r\n");
    return 1;
}
