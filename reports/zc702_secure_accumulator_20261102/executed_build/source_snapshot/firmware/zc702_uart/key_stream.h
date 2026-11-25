/* Coupled verified key buffer + same-block decoy metadata + PL multi-pass PA.
 * This is a functional simulated-session harness, not a security certification. */
#define KS_MAX_BITS 16000000u
#define KS_WORDS ((KS_MAX_BITS+31u)/32u)
static uint32_t ks_key[KS_WORDS] __attribute__((aligned(64)));
static uint32_t ks_work[KS_WORDS] __attribute__((aligned(64)));
static uint32_t ks_seed[2u*KS_WORDS+65u] __attribute__((aligned(64)));
static uint64_t ks_output[(KS_MAX_BITS+63u)/64u] __attribute__((aligned(64)));
static pa_accum_t ks_acc;
static uint32_t ks_bits,ks_next_id,ks_tags_rejected,ks_pending,ks_emit_bits,ks_ell;
static uint32_t ks_seed_words,ks_seed_loaded,ks_out_bits,ks_retired_bits,ks_aborted_bits;
static uint32_t functional_revealed;

static void ks_wipe(void *p,uint32_t bytes)
{
    volatile uint8_t *v=(volatile uint8_t *)p;
    for (uint32_t i=0;i<bytes;i++) v[i]=0;
    Xil_DCacheFlushRange((UINTPTR)p,bytes);
}
static int ks_reject(uint32_t seq,const char *reason)
{
    xil_printf("QKD_STREAM_REJECT seq=%u reason=%s bits=%u\r\n",seq,reason,ks_bits);return 0;
}
static int ks_pa_pass(uint32_t input_words,const uint32_t *seed)
{
    uint32_t st;hp_mark_t whole=hp_mark(),phase=hp_mark();
    if (dma_reset(DMA_PA)||dma_reset(DMA_SEED)) return -1;
    if (dma_start(DMA_PA,RX,pa_rx,sizeof(pa_rx))) return -1;
    wr(QKD,0x44u,input_words);wr(QKD,0x0cu,0x100u);wr(QKD,0x40u,1u);
    hp_add(HP_PA_SETUP,phase);phase=hp_mark();
    if (dma_start(DMA_SEED,0,seed,(input_words+33u)*4u)||dma_start(DMA_PA,0,ks_work,input_words*4u)) return -1;
    hp_add(HP_PA_START,phase);phase=hp_mark();
    if (dma_wait(DMA_SEED,0,(input_words+33u)*4u)||dma_wait(DMA_PA,0,input_words*4u)||
        dma_wait(DMA_PA,RX,sizeof(pa_rx))||qkd_wait(0x100u,&st)) return -1;
    Xil_DCacheInvalidateRange((UINTPTR)pa_rx,sizeof(pa_rx));
    hp_add(HP_PA_DRAIN,phase);hp_add(HP_PA_CALL,whole);return 0;
}
static int key_stream_command(uint32_t n,uint32_t seq)
{
    uint32_t op=frame[0];
    if (op==61u && n==1u) {
        if (functional_active) return ks_reject(seq,"ACTIVE");
        hp_mark_t phase=hp_mark();
        ks_wipe(ks_key,sizeof(ks_key));ks_wipe(ks_work,sizeof(ks_work));
        ks_wipe(ks_seed,sizeof(ks_seed));ks_wipe(ks_output,sizeof(ks_output));
        pa_accum_reset(&ks_acc);ks_bits=0;ks_next_id=0;ks_tags_rejected=0;
        ks_pending=0;ks_ell=0;ks_seed_words=0;ks_seed_loaded=0;ks_out_bits=0;
        ks_retired_bits=0;ks_aborted_bits=0;functional_key_valid=0;
        hp_add(HP_STREAM_WIPE,phase);
        xil_printf("QKD_STREAM_RESET seq=%u\r\n",seq);return 0;
    }
    if (op==60u && n==134u) {
        if (!functional_key_valid||functional_active) return ks_reject(seq,"NO_VERIFIED_INPUT");
        if (ks_pending||ks_out_bits) return ks_reject(seq,"PENDING_OUTPUT");
        if (frame[1]!=ks_next_id) return ks_reject(seq,"BLOCK_ID");
        if (frame[2]>2765u||frame[3]>2765u||frame[4]>2765u||frame[2]+frame[3]+frame[4]!=2765u||
            ks_bits>KS_MAX_BITS-2765u) return ks_reject(seq,"CAPACITY_COUNTS");
        for (uint32_t k=0;k<3u;k++) if (frame[8+k]>frame[5+k]) return ks_reject(seq,"TEST_COUNTS");
        hp_mark_t phase=hp_mark();memset(functional_x,0,sizeof(functional_x));uint32_t out=0;
        uint8_t is_d[3072];memset(is_d,0,sizeof(is_d));
        for (uint32_t k=0;k<307u;k++) is_d[qkd_punct_pos[functional_code][k]]=1;
        for (uint32_t k=0;k<3072u;k++) if (!is_d[k]) {
            functional_x[out/32u]|=(uint32_t)((key_rx[k/64u]>>(k%64u))&1u)<<(out%32u);out++;
        }
        if (out!=2765u) return -1;
        hp_add(HP_STRIP_D,phase);
        if (!verification_reserve(seq)) return 0;
        if (functional_pa(frame+12,1u)) return -1;
        uint64_t wanted=(uint64_t)frame[132]|((uint64_t)frame[133]<<32);
        functional_key_valid=0;
        if (pa_rx[0]!=wanted) {
            ks_tags_rejected++;ks_wipe(key_rx,sizeof(key_rx));ks_wipe(functional_x,sizeof(functional_x));
            xil_printf("QKD_STREAM_TAG_REJECT seq=%u bits=%u\r\n",seq,ks_bits);return 0;
        }
        phase=hp_mark();
        for (uint32_t k=0;k<2765u;k++) {
            uint32_t at=ks_bits+k,bit=(functional_x[k/32u]>>(k%32u))&1u;
            ks_key[at/32u]=(ks_key[at/32u]&~(1u<<(at%32u)))|(bit<<(at%32u));
        }
        const uint32_t mb[4]={12u,8u,6u,4u};
        uint32_t leak=mb[functional_code]*128u-307u+functional_revealed+64u;
        pa_accum_add(&ks_acc,frame+2,frame+5,frame+8,leak,(double)frame[11]);
        ks_bits+=2765u;ks_next_id++;
        ks_wipe(key_rx,sizeof(key_rx));ks_wipe(functional_x,sizeof(functional_x));
        hp_add(HP_STREAM_APPEND,phase);
        xil_printf("QKD_STREAM_ADDED seq=%u block=%u bits=%u leak=%u\r\n",seq,frame[1],ks_bits,leak);return 0;
    }
    if (op==62u && n==2u) {
        if (ks_out_bits||ks_pending) return ks_reject(seq,"PENDING_OUTPUT");
        hp_mark_t phase=hp_mark();
        uint32_t ell=0;pa_action_t action=pa_accum_decide(&ks_acc,(double)frame[1],&ell);
        if ((uint32_t)(ks_acc.nk[0]+ks_acc.nk[1]+ks_acc.nk[2])!=ks_bits) return -1;
        uint32_t emit=(uint32_t)ks_acc.emit_n;
        if (action==PA_EMIT) {
            if (!ell||ell>emit||emit>ks_bits) return -1;
            ks_pending=1;ks_emit_bits=emit;ks_ell=ell;ks_seed_loaded=0;
            ks_seed_words=(emit+31u)/32u+33u+((ell+1023u)/1024u-1u)*32u;
        }
        hp_add(HP_STREAM_DECIDE,phase);
        xil_printf("QKD_STREAM_DECISION seq=%u action=%u bits=%u ell=%u split=%u emit_bits=%u seed_words=%u\r\n",
                   seq,action,ks_bits,ell,ks_acc.split,emit,action==PA_EMIT?ks_seed_words:0u);
        if (action==PA_ABORT) {
            ks_aborted_bits+=ks_bits;ks_wipe(ks_key,sizeof(ks_key));ks_bits=0;pa_accum_reset(&ks_acc);
        }
        return 0;
    }
    if (op==63u && n>=4u) {
        if (!ks_pending||frame[1]!=ks_seed_words||frame[2]!=ks_seed_loaded||frame[3]!=n-4u||
            frame[3]>ks_seed_words-ks_seed_loaded) return ks_reject(seq,"SEED_RANGE");
        hp_mark_t phase=hp_mark();
        memcpy(ks_seed+ks_seed_loaded,frame+4,frame[3]*4u);ks_seed_loaded+=frame[3];
        hp_add(HP_SEED_COPY,phase);
        xil_printf("QKD_STREAM_SEED seq=%u loaded=%u\r\n",seq,ks_seed_loaded);return 0;
    }
    if (op==64u && n==1u) {
        if (!ks_pending||ks_seed_loaded!=ks_seed_words||ks_out_bits) return ks_reject(seq,"INCOMPLETE_SEED");
        hp_mark_t phase=hp_mark();
        uint32_t nw=(ks_emit_bits+31u)/32u;memcpy(ks_work,ks_key,nw*4u);
        if (ks_emit_bits%32u) ks_work[nw-1u]&=(1u<<(ks_emit_bits%32u))-1u;
        uint32_t passes=(ks_ell+1023u)/1024u;
        hp_add(HP_EMIT_PREP,phase);
        for (uint32_t pass=0;pass<passes;pass++) {
            if (ks_pa_pass(nw,ks_seed+pass*32u)) {
                ks_wipe(ks_output,sizeof(ks_output));ks_out_bits=0;return -1;
            }
            uint32_t count=(ks_ell-pass*1024u)/64u;if (count>16u) count=16u;
            memcpy(ks_output+pass*16u,pa_rx,count*8u);
        }
        phase=hp_mark();ks_out_bits=ks_ell;ks_retired_bits+=ks_emit_bits;
        uint32_t tail=ks_bits-ks_emit_bits,shift=ks_emit_bits%32u,base=ks_emit_bits/32u,tailwords=(tail+31u)/32u;
        for (uint32_t w=0;w<tailwords;w++) {
            uint32_t value=ks_key[base+w]>>shift;
            if (shift&&base+w+1u<KS_WORDS) value|=ks_key[base+w+1u]<<(32u-shift);
            ks_key[w]=value;
        }
        if (tail%32u) ks_key[tailwords-1u]&=(1u<<(tail%32u))-1u;
        ks_wipe(ks_key+tailwords,(KS_WORDS-tailwords)*4u);
        pa_accum_emitted(&ks_acc);ks_bits=tail;ks_pending=0;
        if ((uint32_t)(ks_acc.nk[0]+ks_acc.nk[1]+ks_acc.nk[2])!=tail) return -1;
        ks_wipe(ks_seed,sizeof(ks_seed));ks_wipe(ks_work,sizeof(ks_work));
        hp_add(HP_EMIT_FINALIZE,phase);
        xil_printf("QKD_STREAM_EMITTED seq=%u output_bits=%u input_bits=%u tail_bits=%u passes=%u\r\n",
                   seq,ks_out_bits,ks_emit_bits,tail,passes);return 0;
    }
    if (op==65u && n==3u) {
        if (!ks_out_bits||frame[1]>ks_out_bits/64u||frame[2]>256u||frame[2]>ks_out_bits/64u-frame[1]) return ks_reject(seq,"OUTPUT_RANGE");
        for (uint32_t k=frame[1];k<frame[1]+frame[2];k++)
            xil_printf("QKD_STREAM_WORD seq=%u word=%u value=%08x%08x\r\n",seq,k,(uint32_t)(ks_output[k]>>32),(uint32_t)ks_output[k]);
        return 0;
    }
    if (op==66u && n==1u) {
        ks_wipe(ks_output,sizeof(ks_output));ks_out_bits=0;
        xil_printf("QKD_STREAM_OUTPUT_CLEARED seq=%u\r\n",seq);return 0;
    }
    if (op==67u && n==1u) {
        xil_printf("QKD_STREAM_STATE seq=%u bits=%u next_id=%u pending=%u out_bits=%u rejected=%u retired=%u aborted=%u\r\n",
                   seq,ks_bits,ks_next_id,ks_pending,ks_out_bits,ks_tags_rejected,ks_retired_bits,ks_aborted_bits);return 0;
    }
    /* Public-test debug readback only; disable in any production interface. */
    if (op==68u && n==3u) {
        uint32_t nw=(ks_bits+31u)/32u;
        if (frame[1]>nw||frame[2]>128u||frame[2]>nw-frame[1]) return ks_reject(seq,"BUFFER_RANGE");
        for (uint32_t k=frame[1];k<frame[1]+frame[2];k++)
            xil_printf("QKD_STREAM_BUFFER seq=%u word=%u value=%08x\r\n",seq,k,ks_key[k]);
        return 0;
    }
    if (op==69u && n==1u) {
        xil_printf("QKD_STREAM_WIPE_CHECK seq=%u key_crc=%08x work_crc=%08x seed_crc=%08x output_crc=%08x\r\n",seq,
                   frame_crc((const unsigned char *)ks_key,sizeof(ks_key)),
                   frame_crc((const unsigned char *)ks_work,sizeof(ks_work)),
                   frame_crc((const unsigned char *)ks_seed,sizeof(ks_seed)),
                   frame_crc((const unsigned char *)ks_output,sizeof(ks_output)));return 0;
    }
    return -1;
}
