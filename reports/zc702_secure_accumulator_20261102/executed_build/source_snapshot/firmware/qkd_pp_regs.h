/*
 * Register map of the qkd_pp_axi IP (rtl/top/qkd_pp_axi.v). All registers 32 bit, word aligned.
 * QKD_PP_BASE must match the address assigned in the SoC (AE350 AXI / APB bridge).
 */
#ifndef QKD_PP_REGS_H
#define QKD_PP_REGS_H

#include <stdint.h>

#ifndef QKD_PP_BASE
#define QKD_PP_BASE 0x40000000u
#endif

#define QKD_REG(off) (*(volatile uint32_t *)(QKD_PP_BASE + (off)))

/* ---------------- information reconciliation ---------------- */
#define QKD_ID        QKD_REG(0x00)   /* R  {'I','R',ZC} = 0x49520080 for ZC = 128                          */
#define QKD_CTRL      QKD_REG(0x04)   /* W  [0] RETRY  [1] DISCARD  [8+:CTX_W] context                       */
#define QKD_CFG       QKD_REG(0x08)   /* RW code / lq / iter_max / pp_rounds / pp_min_usc / pp_max_usc      */
#define QKD_STATUS    QKD_REG(0x0C)   /* R  see STATUS_* ; W1C [0] [1] [8]                                   */
#define QKD_ITERS     QKD_REG(0x10)   /* R  [11:0] iterations of the last attempt  [23:16] attempts          */
#define QKD_CYCLES    QKD_REG(0x14)   /* R  decoder clock cycles of the block                                */
#define QKD_REVEAL    QKD_REG(0x18)   /* W  [15:0] position  [16] Alice's bit  [20+:CTX_W] context           */
#define QKD_IRQ_EN    QKD_REG(0x1C)   /* RW [0] SUCCESS [1] FAIL [2] PA_DONE                                 */
#define QKD_CFG2      QKD_REG(0x20)   /* RW [3:0] et_patience (0 = off)  [4] HOLD  [5] NMS (reset 1)         */
#define QKD_ERRCNT    QKD_REG(0x24)   /* R  [11:0] channel errors corrected in the last successful block     */
/* ---------------- block contexts (2^CTX_W blocks in flight share the decoder) ---------------- */
#define QKD_LOAD_CTX  QKD_REG(0x28)   /* RW context receiving the next streamed block (must be free)         */
#define QKD_CTX_SUM   QKD_REG(0x2C)   /* R  [7:0] free [15:8] waiting [23:16] SUCCESS [31:24] FAIL; W1C [31:16] */
#define QKD_CTX_CFG   QKD_REG(0x30)   /* R  [3:0] CTX_W                                                      */
#define QKD_CTX_A(c)  QKD_REG(0x80 + 8u * (c))  /* [11:0] iters  [23:12] n_usc  [31:24] attempts            */
#define QKD_CTX_B(c)  QKD_REG(0x84 + 8u * (c))  /* [11:0] ERRCNT  [25:24] pp_used  [30:28] state             */
#define QKD_CTX_CYC(c) QKD_REG(0xC0 + 4u * (c)) /* decoder cycles of the block                               */
#define QKD_NCTX      4u
#define CTRL_CTX(c)   ((uint32_t)(c) << 8)
#define REVEAL_CTX(c) ((uint32_t)(c) << 20)
#define CTX_SUM_FREE(s, c)    (((s) >> (c)) & 1u)
#define CTX_SUM_WAIT(s, c)    (((s) >> (8 + (c))) & 1u)
#define CTX_SUM_SUCCESS(s, c) (((s) >> (16 + (c))) & 1u)
#define CTX_SUM_FAIL(s, c)    (((s) >> (24 + (c))) & 1u)
/* ---------------- privacy amplification ---------------- */
#define QKD_PA_CTRL   QKD_REG(0x40)   /* W  [0] START                                                        */
#define QKD_PA_NWORDS QKD_REG(0x44)   /* RW [19:0] input length in 32-bit words                              */

/* CTRL */
#define CTRL_RETRY    (1u << 0)
#define CTRL_DISCARD  (1u << 1)

/* STATUS */
#define STATUS_SUCCESS  (1u << 0)     /* sticky, write 1 to clear                                            */
#define STATUS_FAIL     (1u << 1)     /* sticky, write 1 to clear                                            */
#define STATUS_BUSY     (1u << 2)     /* decoder running                                                     */
#define STATUS_WAIT     (1u << 3)     /* block waits for REVEAL / RETRY / DISCARD (after FAIL or in HOLD)    */
#define STATUS_PP_USED(s)  (((s) >> 4) & 0x3u)
#define STATUS_PA_DONE  (1u << 8)     /* sticky, write 1 to clear                                            */
#define STATUS_PA_BUSY  (1u << 9)
#define STATUS_N_USC(s) (((s) >> 16) & 0xFFFu)   /* unsatisfied checks of the last decode                    */

/* CFG fields */
enum { CODE_R12 = 0, CODE_R23 = 1, CODE_R34 = 2, CODE_R56 = 3 };
static inline uint32_t qkd_cfg(uint32_t code, uint32_t lq, uint32_t iter_max,
                               uint32_t pp_rounds, uint32_t pp_min_usc, uint32_t pp_max_usc)
{
    return (code & 3u) | ((lq & 31u) << 2) | ((iter_max & 255u) << 8) |
           ((pp_rounds & 3u) << 16) | ((pp_min_usc & 3u) << 18) | ((pp_max_usc & 0xFFFu) << 20);
}
#define CFG2_ET(p)    ((uint32_t)(p) & 0xFu)
#define CFG2_HOLD     (1u << 4)
#define CFG2_NMS      (1u << 5)        /* normalized min-sum x0.75 (0: offset min-sum)                         */

/* Geometry of the current build (ZC = 128) */
#define QKD_ZC        128u
#define QKD_N         (24u * QKD_ZC)          /* 3072 variable nodes per block                              */
#define QKD_D         307u                    /* round(0.10 * n) modulated positions (protocol choice)      */
#define QKD_NKEY      (QKD_N - QKD_D)         /* 2765 key bits per block                                    */
#define QKD_MB(code)  ((code) == CODE_R12 ? 12u : (code) == CODE_R23 ? 8u : (code) == CODE_R34 ? 6u : 4u)

#define PA_L_OUT      1024u                   /* hash bits per PA pass                                       */
#define PA_PRELOAD    33u                     /* seed words before the first input word                     */

#endif
