/* Functional bring-up with simulated Alice on the PC. No secret-key claim. */
#include "controller_generated.h"
#include "accumulator_generated.h"
#include "qkd_punct_tables.h"
#include "irq_test.h"
#define FUNC_MAGIC 0x51465532u
static dyn_ctrl_t functional_ctrl = {PROF_EFFICIENCY,F_TARGET,0.0f,0};
static int functional_active, functional_key_valid;
static uint32_t functional_code;
static uint32_t functional_x[87] __attribute__((aligned(64)));
static uint32_t functional_seed[120] __attribute__((aligned(64)));
static pa_accum_t functional_accumulator;
/* Boot-lifetime cap shared by both verification entry points. Buffer resets
 * never refund checks. A reboot starts a new accounting epoch; persistent
 * authenticated session accounting remains outside this public test harness. */
#define VERIFY_DEFAULT_LIMIT 18446u
static uint32_t verification_used,verification_limit=VERIFY_DEFAULT_LIMIT;
static int verification_reserve(uint32_t seq)
{
    functional_key_valid=0;
    if (verification_used>=verification_limit) {
        volatile uint8_t *p=(volatile uint8_t *)key_rx;
        for (uint32_t i=0;i<sizeof(key_rx);i++) p[i]=0;
        p=(volatile uint8_t *)functional_x;
        for (uint32_t i=0;i<sizeof(functional_x);i++) p[i]=0;
        Xil_DCacheFlushRange((UINTPTR)key_rx,sizeof(key_rx));
        Xil_DCacheFlushRange((UINTPTR)functional_x,sizeof(functional_x));
        xil_printf("QKD_FUNC_VERIFY_LIMIT seq=%u used=%u limit=%u\r\n",seq,verification_used,verification_limit);
        return 0;
    }
    verification_used++; /* Count rejected tags and attempted hashes on DMA failure. */
    return 1;
}

static int functional_pa(const uint32_t *seed,uint32_t verify)
{
    uint32_t st,base=verify?HP_VERIFY_SETUP:HP_PA_SETUP;
    hp_mark_t whole=hp_mark(),phase=hp_mark();
    memcpy(functional_seed,seed,sizeof(functional_seed));
    if (dma_reset(DMA_PA) || dma_reset(DMA_SEED)) return -1;
    if (dma_start(DMA_PA,RX,pa_rx,sizeof(pa_rx))) return -1;
    wr(QKD,0x44u,87u);wr(QKD,0x0cu,0x100u);wr(QKD,0x40u,1u);
    hp_add(base,phase);phase=hp_mark();
    if (dma_start(DMA_SEED,0,functional_seed,sizeof(functional_seed)) ||
        dma_start(DMA_PA,0,functional_x,sizeof(functional_x))) return -1;
    hp_add(base+1u,phase);phase=hp_mark();
    if (dma_wait(DMA_SEED,0,sizeof(functional_seed)) || dma_wait(DMA_PA,0,sizeof(functional_x)) ||
        dma_wait(DMA_PA,RX,sizeof(pa_rx)) || qkd_wait(0x100u,&st)) return -1;
    Xil_DCacheInvalidateRange((UINTPTR)pa_rx,sizeof(pa_rx));
    hp_add(base+2u,phase);hp_add(verify?HP_VERIFY_CALL:HP_PA_CALL,whole);
    return 0;
}
#include "multicontext.h"
#include "key_stream.h"
#include "latency_benchmark.h"
static int functional_command(uint32_t n, uint32_t seq)
{
    if (!n) return -1;
    uint32_t op=frame[0];
    if (op==74u && n==2u) {
        if (functional_active||mc_mode) return -1;
        return hp_control(seq,frame[1]);
    }
    if (op==75u && n==2u) return hp_read(seq,frame[1]);
    if (op==72u && n==2u) {
        if (functional_active||frame[1]>verification_limit||frame[1]<verification_used) {
            xil_printf("QKD_FUNC_BUDGET_REJECT seq=%u used=%u limit=%u\r\n",seq,verification_used,verification_limit);return 0;
        }
        verification_limit=frame[1];
        xil_printf("QKD_FUNC_BUDGET_SET seq=%u used=%u limit=%u\r\n",seq,verification_used,verification_limit);return 0;
    }
    if (op==73u && n==1u) {
        xil_printf("QKD_FUNC_BUDGET_STATE seq=%u used=%u limit=%u remaining=%u\r\n",
                   seq,verification_used,verification_limit,verification_limit-verification_used);return 0;
    }
    if (op==70u||op==71u) return latency_benchmark_command(n,seq);
    if (op>=60u && op<=69u) return key_stream_command(n,seq);
    if (op==50u && n==1u) {
        if (functional_irq_arm()) return -1;
        xil_printf("QKD_FUNC_IRQ_ARMED seq=%u id=%u\r\n",seq,XPAR_FABRIC_QKD_IRQ_INTR);return 0;
    }
    if (op==51u && n==1u) {
        wr(QKD,0x1cu,0u);
        xil_printf("QKD_FUNC_IRQ_RESULT seq=%u count=%u status=%08x\r\n",seq,functional_irq_count,functional_irq_status);return 0;
    }
    if (op>=40u && op<=46u) return mc_command(n,seq);
    if (op==30u && n==1u) {
        pa_accum_reset(&functional_accumulator);
        xil_printf("QKD_FUNC_ACC_RESET seq=%u\r\n",seq);return 0;
    }
    if (op==31u && n==12u) {
        for (uint32_t i=0;i<3u;i++) if (frame[7+i]>frame[4+i]) return -1;
        pa_accum_add(&functional_accumulator,frame+1,frame+4,frame+7,frame[10],(double)frame[11]);
        xil_printf("QKD_FUNC_ACC_ADDED seq=%u\r\n",seq);return 0;
    }
    if (op==32u && n==2u) {
        uint32_t ell=0;pa_action_t action=pa_accum_decide(&functional_accumulator,(double)frame[1],&ell);
        xil_printf("QKD_FUNC_ACC_DECISION seq=%u action=%u ell=%u split=%u emit_n=%u\r\n",
                   seq,action,ell,functional_accumulator.split,(uint32_t)functional_accumulator.emit_n);return 0;
    }
    if (op==33u && n==1u) {
        pa_accum_emitted(&functional_accumulator);
        xil_printf("QKD_FUNC_ACC_EMITTED seq=%u\r\n",seq);return 0;
    }
    if (op==0u && n==1u) {
        if (functional_active) return -1;
        functional_ctrl.profile=PROF_EFFICIENCY;functional_ctrl.f_adj=F_TARGET;
        functional_ctrl.q_ewma=0.0f;functional_ctrl.have_ewma=0;
        xil_printf("QKD_FUNC_RESET seq=%u\r\n",seq);return 0;
    }
    if (op==1u && n==4u) {
        float q;memcpy(&q,frame+2,4);
        if (!(q>=0.0f && q<=0.5f) || !frame[3]) return -1;
        qkd_select_profile(&functional_ctrl,frame[1]);
        uint32_t code=0,r0=0;
        int accepted=plan(&functional_ctrl,q,frame[3],&code,&r0);
        xil_printf("QKD_FUNC_PLAN seq=%u accept=%u profile=%u code=%u r0=%u\r\n",
                   seq,accepted,functional_ctrl.profile,code,r0);return 0;
    }
    if (op==2u && n==3u && frame[1]<=3072u && frame[2]<=307u) {
        xil_printf("QKD_FUNC_REVEAL_PLAN seq=%u count=%u\r\n",seq,next_reveal(&functional_ctrl,frame[1],frame[2]));return 0;
    }
    if (op==3u && n==4u && frame[1]<=1u && frame[2]<=3072u && frame[3]<=64u) {
        update(&functional_ctrl,frame[1]!=0u,frame[2],frame[3]);
        xil_printf("QKD_FUNC_UPDATE seq=%u f_scaled=%u\r\n",seq,(uint32_t)(functional_ctrl.f_adj*1000000.0f));return 0;
    }
    if (op==10u) {
        if (functional_active || n<5u || frame[3]>48u || frame[4]>307u) return -1;
        uint32_t cfg=frame[1],ns=frame[3],pre=frame[4];
        const uint32_t sizes[4]={48u,32u,24u,16u};
        if (ns!=sizes[cfg&3u] || n!=5u+192u+ns+pre) return -1;
        hp_mark_t phase=hp_mark();hp_waiting=0;
        functional_key_valid=0;functional_code=cfg&3u;
        if (dma_reset(DMA_CH) || dma_reset(DMA_SYN)) return -1;
        wr(QKD,0x1cu,0u);wr(QKD,0x0cu,0x103u);wr(QKD,0x2cu,0xffff0000u);wr(QKD,0x28u,0u);
        wr(QKD,0x08u,cfg);wr(QKD,0x20u,frame[2]|0x10u);
        hp_add(HP_IR_SETUP,phase);phase=hp_mark();
        memcpy(channel_data,frame+5,sizeof(channel_data));
        memcpy(syndrome_data,frame+5+192,ns*4u);
        if (dma_start(DMA_CH,RX,key_rx,sizeof(key_rx)) || dma_start(DMA_CH,0,channel_data,sizeof(channel_data)) ||
            dma_start(DMA_SYN,0,syndrome_data,ns*4u)) return -1;
        hp_add(HP_IR_COPY_START,phase);phase=hp_mark();
        uint32_t st;
        if (dma_wait(DMA_CH,0,sizeof(channel_data)) || dma_wait(DMA_SYN,0,ns*4u) || qkd_wait(8u,&st)) return -1;
        hp_add(HP_IR_INPUT_DRAIN,phase);phase=hp_mark();
        for (uint32_t k=0;k<pre;k++) {
            uint32_t value=frame[5+192+ns+k];
            if ((value&0xfffe0000u) || (value&0xffffu)>=3072u) return -1;
            wr(QKD,0x18u,value);
        }
        functional_revealed=pre;functional_active=1;
        hp_add(HP_IR_PRE_REVEAL,phase);
        xil_printf("QKD_FUNC_LOADED seq=%u\r\n",seq);return 0;
    }
    if (op==11u && n==1u && functional_active) {
        uint32_t st;XTime start,finish;
        hp_mark_t phase=hp_mark();
        wr(QKD,0x0cu,3u);XTime_GetTime(&start);wr(QKD,0x04u,1u);
        if (qkd_wait(3u,&st)) return -1;
        hp_add(HP_IR_DECODE_POLL,phase);phase=hp_mark();
        if (st&1u) {
            if (dma_wait(DMA_CH,RX,sizeof(key_rx))) return -1;
            Xil_DCacheInvalidateRange((UINTPTR)key_rx,sizeof(key_rx));
            functional_active=0;functional_key_valid=1;
            hp_add(HP_IR_KEY_RX,phase);
        } else hp_wait_begin();
        XTime_GetTime(&finish);
        xil_printf("QKD_FUNC_ATTEMPT seq=%u status=%08x iters=%08x errcnt=%u cycles=%u ticks=%u\r\n",
                   seq,st,rd(QKD,0x10u),rd(QKD,0x24u)&0xfffu,rd(QKD,0xc0u),(uint32_t)(finish-start));return 0;
    }
    if (op==12u && n>=2u && functional_active && frame[1]<=307u && n==2u+frame[1]) {
        if (functional_revealed+frame[1]>307u) return -1;
        hp_wait_end();hp_mark_t phase=hp_mark();
        for (uint32_t k=0;k<frame[1];k++) {
            uint32_t value=frame[2+k];
            if ((value&0xfffe0000u) || (value&0xffffu)>=3072u) return -1;
            wr(QKD,0x18u,value);
        }
        functional_revealed+=frame[1];
        hp_add(HP_REVEAL_WRITE,phase);
        xil_printf("QKD_FUNC_REVEALED seq=%u count=%u\r\n",seq,frame[1]);return 0;
    }
    if (op==13u && n==1u) {
        hp_waiting=0;
        if (functional_active) {wr(QKD,0x04u,2u);if (dma_reset(DMA_CH)) return -1;}
        functional_active=0;functional_key_valid=0;memset(key_rx,0,sizeof(key_rx));
        xil_printf("QKD_FUNC_DISCARD seq=%u\r\n",seq);return 0;
    }
    if (op==14u && n==1u && functional_key_valid) {
        for (uint32_t k=0;k<48u;k++)
            xil_printf("QKD_FUNC_KEY seq=%u word=%u value=%08x%08x\r\n",seq,k,(uint32_t)(key_rx[k]>>32),(uint32_t)key_rx[k]);
        return 0;
    }
    if (op==20u && n==583u) {
        if (!functional_key_valid || frame[1]!=functional_code) return -1;
        hp_mark_t strip=hp_mark();
        uint8_t is_d[3072];memset(is_d,0,sizeof(is_d));
        for (uint32_t k=0;k<307u;k++) {
            uint32_t pos=frame[2+k];
            if (pos>=3072u || is_d[pos] || pos!=qkd_punct_pos[functional_code][k]) return -1;
            is_d[pos]=1;
        }
        memset(functional_x,0,sizeof(functional_x));
        uint32_t out=0;
        for (uint32_t k=0;k<3072u;k++) if (!is_d[k]) {
            functional_x[out/32u]|=(uint32_t)((key_rx[k/64u]>>(k%64u))&1u)<<(out%32u);out++;
        }
        if (out!=2765u) return -1;
        hp_add(HP_STRIP_D,strip);
        if (!verification_reserve(seq)) return 0;
        if (functional_pa(frame+309,1u)) return -1;
        uint64_t wanted=(uint64_t)frame[429]|((uint64_t)frame[430]<<32);
        if (pa_rx[0]!=wanted) {
            functional_key_valid=0;memset(key_rx,0,sizeof(key_rx));memset(functional_x,0,sizeof(functional_x));
            xil_printf("QKD_FUNC_TAG_REJECT seq=%u pa_emitted=0\r\n",seq);return 0;
        }
        if (functional_pa(frame+431,0u)) return -1;
        for (uint32_t k=0;k<16u;k++) {
            uint64_t expected=(uint64_t)frame[551+k*2]|((uint64_t)frame[552+k*2]<<32);
            if (pa_rx[k]!=expected) return -1;
            xil_printf("QKD_FUNC_PA seq=%u word=%u value=%08x%08x\r\n",seq,k,(uint32_t)(pa_rx[k]>>32),(uint32_t)pa_rx[k]);
        }
        functional_key_valid=0;memset(key_rx,0,sizeof(key_rx));memset(functional_x,0,sizeof(functional_x));
        xil_printf("QKD_FUNC_PIPE_PASS seq=%u input_bits=2765 output_bits=1024\r\n",seq);return 0;
    }
    return -1;
}
