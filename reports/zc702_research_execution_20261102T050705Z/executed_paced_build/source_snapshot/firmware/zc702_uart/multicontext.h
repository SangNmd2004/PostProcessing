/* Four resident contexts, queued together. Simple DMA receives one frame at a
 * time; its completion is bound to the unique sticky SUCCESS before rearming.
 * No TUSER is presumed stored in DDR. Any ambiguous ownership stops the test. */
static int mc_mode,mc_rx_armed;
static int mc_command(uint32_t n,uint32_t seq)
{
    uint32_t op=frame[0];
    if (op==40u && n==1u) {
        if (functional_active || (rd(QKD,0x2cu)&15u)!=15u) return -1;
        if (dma_reset(DMA_CH) || dma_reset(DMA_SYN)) return -1;
        functional_key_valid=0;mc_rx_armed=0;mc_mode=1;
        wr(QKD,0x2cu,0xffff0000u);
        xil_printf("QKD_FUNC_MC_RESET seq=%u\r\n",seq);return 0;
    }
    if (!mc_mode) return -1;
    if (op==41u && n>=6u) {
        uint32_t ctx=frame[1],cfg=frame[2],ns=frame[4],pre=frame[5];
        const uint32_t sizes[4]={48u,32u,24u,16u};
        if (ctx>=4u || ns!=sizes[cfg&3u] || pre>307u || n!=6u+192u+ns+pre ||
            !(rd(QKD,0x2cu)&(1u<<ctx))) return -1;
        wr(QKD,0x28u,ctx);wr(QKD,0x08u,cfg);wr(QKD,0x20u,frame[3]|0x10u);
        memcpy(channel_data,frame+6,sizeof(channel_data));memcpy(syndrome_data,frame+198,ns*4u);
        if (dma_start(DMA_CH,0,channel_data,sizeof(channel_data)) || dma_start(DMA_SYN,0,syndrome_data,ns*4u) ||
            dma_wait(DMA_CH,0,sizeof(channel_data)) || dma_wait(DMA_SYN,0,ns*4u)) return -1;
        XTime start;XTime_GetTime(&start);
        while (((rd(QKD,0x84u+8u*ctx)>>28)&7u)!=1u) if (expired(start)) return -1;
        for (uint32_t k=0;k<pre;k++) {
            uint32_t value=frame[198+ns+k];
            if ((value&0xfffe0000u) || (value&0xffffu)>=3072u) return -1;
            wr(QKD,0x18u,value|(ctx<<20));
        }
        xil_printf("QKD_FUNC_MC_LOADED seq=%u ctx=%u\r\n",seq,ctx);return 0;
    }
    if (op==42u && n==2u && frame[1]<4u) {
        uint32_t ctx=frame[1];
        if (!mc_rx_armed) {
            if (dma_start(DMA_CH,RX,key_rx,sizeof(key_rx))) return -1;
            mc_rx_armed=1;
        }
        wr(QKD,0x2cu,(1u<<(16u+ctx))|(1u<<(24u+ctx)));
        wr(QKD,0x04u,1u|(ctx<<8));
        xil_printf("QKD_FUNC_MC_QUEUED seq=%u ctx=%u\r\n",seq,ctx);return 0;
    }
    if (op==43u && n==1u) {
        uint32_t dma_status=rd(DMA_CH,RX+4u);
        if (dma_status&DMA_ERROR) return -1;
        uint32_t ready=mc_rx_armed && (dma_status&0x1002u)==0x1002u;
        uint32_t summary=rd(QKD,0x2cu),owner=0;
        if (ready) {
            XTime start;XTime_GetTime(&start);
            while (!(summary&0x000f0000u)) {
                if (expired(start)) return -1;
                summary=rd(QKD,0x2cu);
            }
            uint32_t bits=(summary>>16)&15u;
            if (bits&(bits-1u)) return -1;
            while (!(bits&(1u<<owner))) owner++;
            if (dma_wait(DMA_CH,RX,sizeof(key_rx))) return -1;
            Xil_DCacheInvalidateRange((UINTPTR)key_rx,sizeof(key_rx));
        }
        xil_printf("QKD_FUNC_MC_STATUS seq=%u summary=%08x rx=%u owner=%u\r\n",seq,summary,ready,owner);
        for (uint32_t ctx=0;ctx<4u;ctx++)
            xil_printf("QKD_FUNC_MC_CTX seq=%u ctx=%u a=%08x b=%08x cycles=%u\r\n",
                       seq,ctx,rd(QKD,0x80u+8u*ctx),rd(QKD,0x84u+8u*ctx),rd(QKD,0xc0u+4u*ctx));
        if (ready) {
            for (uint32_t k=0;k<48u;k++)
                xil_printf("QKD_FUNC_MC_KEY seq=%u ctx=%u word=%u value=%08x%08x\r\n",
                           seq,owner,k,(uint32_t)(key_rx[k]>>32),(uint32_t)key_rx[k]);
            wr(QKD,0x2cu,1u<<(16u+owner));
            if (dma_start(DMA_CH,RX,key_rx,sizeof(key_rx))) return -1;
        }
        return 0;
    }
    if (op==44u && n>=3u && frame[1]<4u && frame[2]<=307u && n==3u+frame[2]) {
        uint32_t ctx=frame[1];
        for (uint32_t k=0;k<frame[2];k++) {
            uint32_t value=frame[3+k];
            if ((value&0xfffe0000u) || (value&0xffffu)>=3072u) return -1;
            wr(QKD,0x18u,value|(ctx<<20));
        }
        xil_printf("QKD_FUNC_MC_REVEALED seq=%u ctx=%u\r\n",seq,ctx);return 0;
    }
    if (op==45u && n==2u && frame[1]<4u) {
        uint32_t ctx=frame[1];wr(QKD,0x04u,2u|(ctx<<8));
        wr(QKD,0x2cu,1u<<(24u+ctx));
        xil_printf("QKD_FUNC_MC_DISCARD seq=%u ctx=%u\r\n",seq,ctx);return 0;
    }
    if (op==46u && n==1u && (rd(QKD,0x2cu)&15u)==15u) {
        if (dma_reset(DMA_CH)) return -1;
        mc_rx_armed=0;mc_mode=0;
        xil_printf("QKD_FUNC_MC_DONE seq=%u\r\n",seq);return 0;
    }
    return -1;
}
