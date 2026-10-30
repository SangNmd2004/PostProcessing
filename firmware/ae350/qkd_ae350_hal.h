#ifndef QKD_AE350_HAL_H
#define QKD_AE350_HAL_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Andes AE350 Base Addresses for QKD Post-Processing Subsystem
 */
#define AE350_QKD_IP_BASE          0xE0000000U
#define AE350_DMA_BASE             0xE4000000U
#define AE350_PLIC_BASE            0xE6400000U

/*
 * Memory-Mapped I/O Macros for RISC-V Architecture
 */
static inline uint32_t ae350_read32(uintptr_t addr)
{
    return (*(volatile uint32_t *)(addr));
}

static inline void ae350_write32(uintptr_t addr, uint32_t val)
{
    (*(volatile uint32_t *)(addr)) = val;
}

/*
 * RISC-V Low-Power Sleep Instruction
 */
static inline void ae350_wfi(void)
{
#if defined(__riscv)
    __asm__ volatile ("wfi" : : : "memory");
#else
    /* Non-RISC-V simulation fallback */
    (void)0;
#endif
}

/*
 * HAL Initialization and Control API
 */
int  ae350_hal_init(void);
void ae350_plic_enable_irq(uint32_t irq_source);
void ae350_plic_clear_irq(uint32_t irq_source);
int  ae350_dma_transfer(uintptr_t src, uintptr_t dst, uint32_t byte_len);

#ifdef __cplusplus
}
#endif

#endif /* QKD_AE350_HAL_H */
