#include "qkd_ae350_hal.h"

int ae350_hal_init(void)
{
    /* Check QKD Hardware ID */
    uint32_t hw_id = ae350_read32(AE350_QKD_IP_BASE + 0x00U);
    if ((hw_id >> 16) != 0x4952U) { // 'I', 'R'
        return -1;
    }
    return 0;
}

void ae350_plic_enable_irq(uint32_t irq_source)
{
    /* Andes PLIC Target 0 Enable Register */
    uintptr_t enable_reg = AE350_PLIC_BASE + 0x2000U + (irq_source / 32U) * 4U;
    uint32_t mask = 1U << (irq_source % 32U);
    ae350_write32(enable_reg, ae350_read32(enable_reg) | mask);
}

void ae350_plic_clear_irq(uint32_t irq_source)
{
    /* Andes PLIC Claim/Complete Register */
    uintptr_t claim_reg = AE350_PLIC_BASE + 0x200004U;
    ae350_write32(claim_reg, irq_source);
}

int ae350_dma_transfer(uintptr_t src, uintptr_t dst, uint32_t byte_len)
{
    if (src == 0U || dst == 0U || byte_len == 0U) {
        return -1;
    }

    /* ATCDMAC300 Channel 0 Configuration */
    ae350_write32(AE350_DMA_BASE + 0x020U, (uint32_t)src);      // Source Addr
    ae350_write32(AE350_DMA_BASE + 0x028U, (uint32_t)dst);      // Dest Addr
    ae350_write32(AE350_DMA_BASE + 0x030U, byte_len);           // Transfer Size
    ae350_write32(AE350_DMA_BASE + 0x038U, 0x00010001U);        // Enable Channel 0

    return 0;
}
