/* Isolated public-fixture DDR-paced IR component benchmark.
 * No UART inside timed loop. No PA/secret-yield/security claim.
 * Fixed f_adj per dispatch: only profile selection and plan() are exercised. */
typedef struct {
    uint32_t scheduled,arrived,dispatch,complete,profile,slot,backlog,outcome,attempts,leak,cycles;
} paced_row_t;
static paced_row_t paced_rows[128];
#include "paced_queue.h"
static uint32_t paced_job[4],paced_count;
static volatile uint32_t paced_debug[12];
static float paced_q[2]={.02f,.02f};
static uint32_t paced_npe[2]={10000u,10000u};
static uint32_t paced_us(XTime start){XTime now;XTime_GetTime(&now);return (uint32_t)((now-start)*1000000u/COUNTS_PER_SECOND);}
static int paced_command(uint32_t n,uint32_t seq){
    uint32_t op=frame[0];
    if(op==78u&&n==5u){
        float q[2];memcpy(q,frame+1,4);memcpy(q+1,frame+3,4);
        if(!(q[0]>=0.0f&&q[0]<=.11f)||!(q[1]>=0.0f&&q[1]<=.11f)||!frame[2]||!frame[4])return -1;
        paced_q[0]=q[0];paced_q[1]=q[1];paced_npe[0]=frame[2];paced_npe[1]=frame[4];
        xil_printf("QKD_PACED_CONFIG seq=%u n_pe0=%u n_pe1=%u\r\n",seq,paced_npe[0],paced_npe[1]);return 0;
    }
    if(op==77u&&n==1u){
        for(uint32_t i=0;i<paced_count;i++){
            paced_row_t *r=&paced_rows[i];
            xil_printf("QKD_PACED_JOB seq=%u id=%u scheduled=%u arrived=%u dispatch=%u complete=%u profile=%u slot=%u backlog=%u outcome=%u attempts=%u leak=%u cycles=%u\r\n",
                seq,i,r->scheduled,r->arrived,r->dispatch,r->complete,r->profile,r->slot,r->backlog,r->outcome,r->attempts,r->leak,r->cycles);
        }
        xil_printf("QKD_PACED_ROWS_DONE seq=%u rows=%u\r\n",seq,paced_count);return 0;
    }
    if(op!=76u||n!=7u||frame[1]<1u||frame[1]>4u||!frame[2]||frame[2]>128u||frame[3]>100000u||frame[4]>100000u||!frame[5]||frame[5]>128u||frame[6]>2u)return -1;
    uint32_t contexts=frame[1],jobs=frame[2],rtt=frame[3],interval=frame[4],capacity=frame[5],policy=frame[6];
    for(uint32_t i=0;i<4;i++)if(!bench_vectors[i].ready)return -1;
    if(functional_active||mc_mode||(rd(QKD,0x2cu)&15u)!=15u)return -1;
    wr(QKD,0x1cu,0u);wr(QKD,0x2cu,0xffff0000u);
    if(dma_reset(DMA_CH)||dma_reset(DMA_SYN))return -1;
    memset(bench_contexts,0,sizeof(bench_contexts));memset(paced_rows,0xff,sizeof(paced_rows));paced_count=jobs;
    uint32_t next=0,done=0,dropped=0,corrected=0,discarded=0;
    paced_queue_t queue;if(paced_queue_init(&queue,capacity))return -1;
    dyn_ctrl_t ctrl={PROF_EFFICIENCY,F_TARGET,0,0};XTime start;XTime_GetTime(&start);
    if(dma_start(DMA_CH,RX,key_rx,sizeof(key_rx)))return -1;
    while(done<jobs){
        paced_debug[0]=1;paced_debug[1]=next;paced_debug[2]=done;paced_debug[3]=queue.count;
        uint32_t now=paced_us(start);if(now>30000000u)return -1;
        while(next<jobs&&now>=next*interval){
            paced_row_t *r=&paced_rows[next];r->scheduled=next*interval;r->arrived=now;
            if(paced_queue_push(&queue,next)){r->outcome=2u;r->complete=now;dropped++;done++;}
            next++;
        }
        uint32_t status=rd(DMA_CH,RX+4u);if(status&DMA_ERROR)return -1;
        paced_debug[7]=status;
        if((status&0x1002u)==0x1002u){
            if(dma_wait(DMA_CH,RX,sizeof(key_rx)))return -1;
            uint32_t summary=rd(QKD,0x2cu);XTime began;XTime_GetTime(&began);
            while(!(summary&0xf0000u)){if(expired(began))return -1;summary=rd(QKD,0x2cu);}
            uint32_t bits=(summary>>16)&15u,owner=0;if(bits&(bits-1u))return -1;
            while(!(bits&(1u<<owner)))owner++;
            if(owner>=contexts||bench_contexts[owner].stage!=2u)return -1;
            Xil_DCacheInvalidateRange((UINTPTR)key_rx,sizeof(key_rx));if(bench_check(owner,1))return -1;
            bench_context_t *c=&bench_contexts[owner];smoke_vector_t *v=&bench_vectors[c->job%4u].v;paced_row_t *r=&paced_rows[paced_job[owner]];
            r->complete=paced_us(start);r->outcome=0;r->attempts=c->attempt+1u;r->cycles=rd(QKD,0xc0u+owner*4u);
            r->leak=QKD_MB(v->cfg&3u)*128u-307u+c->cursor;
            wr(QKD,0x2cu,1u<<(16u+owner));c->stage=0;done++;corrected++;
            if(dma_start(DMA_CH,RX,key_rx,sizeof(key_rx)))return -1;
        }
        for(uint32_t ctx=0;ctx<contexts;ctx++){
            bench_context_t *c=&bench_contexts[ctx];smoke_vector_t *v=&bench_vectors[c->job%4u].v;
            if(c->stage==2u&&(rd(QKD,0x2cu)&(1u<<(24u+ctx)))){
                if(bench_check(ctx,0))return -1;
                if(c->attempt+1u==v->attempts){
                    if(v->counts[c->attempt])return -1;
                    paced_row_t *r=&paced_rows[paced_job[ctx]];r->complete=paced_us(start);r->outcome=1;r->attempts=c->attempt+1u;r->cycles=rd(QKD,0xc0u+ctx*4u);
                    r->leak=QKD_MB(v->cfg&3u)*128u-307u+c->cursor;
                    wr(QKD,0x04u,2u|(ctx<<8));wr(QKD,0x2cu,1u<<(24u+ctx));c->stage=0;done++;discarded++;
                }else{XTime now_tick;XTime_GetTime(&now_tick);c->due=now_tick+(XTime)rtt*COUNTS_PER_SECOND/1000000u;c->stage=3;}
            }
        }
        uint32_t stages[4];for(uint32_t ctx=0;ctx<contexts;ctx++)stages[ctx]=bench_contexts[ctx].stage;
        /* REVEAL writes can stall in the AXI slave while KEY output owns the
         * CH read port. With one simple S2MM buffer, preparing more reveals
         * while another decoder can produce output creates circular wait.
         * Drain the active wave before blocking load/pre-reveal/reveal writes;
         * prepare every ready context before queueing the next wave. */
        if(paced_safe_to_prepare(stages,contexts)){
          for(uint32_t ctx=0;ctx<contexts;ctx++){
            bench_context_t *c=&bench_contexts[ctx];smoke_vector_t *v=&bench_vectors[c->job%4u].v;
            if(c->stage==3u){
                XTime now_tick;XTime_GetTime(&now_tick);
                if(now_tick>=c->due){
                    uint32_t count=v->counts[c->attempt];for(uint32_t i=0;i<count;i++)wr(QKD,0x18u,v->reveal[c->cursor++]|(ctx<<20));
                    c->attempt++;c->stage=1u;
                }
            }
            if(c->stage==0u&&queue.count){
                uint32_t id;if(paced_queue_pop(&queue,&id))return -1;
                uint32_t backlog=queue.count;
                paced_debug[0]=2;paced_debug[4]=ctx;paced_debug[5]=id;
                if(policy==2u)qkd_select_profile(&ctrl,backlog);else ctrl.profile=(qkd_profile_t)policy;
                ctrl.f_adj=F_TARGET;uint32_t code,r0;
                if(!plan(&ctrl,paced_q[id%2u],paced_npe[id%2u],&code,&r0))return -1;
                uint32_t slot=(id%2u)*2u+(uint32_t)ctrl.profile;smoke_vector_t *input=&bench_vectors[slot].v;
                if(code!=(input->cfg&3u)||r0!=input->pre)return -1;
                paced_rows[id].dispatch=paced_us(start);paced_rows[id].profile=ctrl.profile;paced_rows[id].slot=slot;paced_rows[id].backlog=backlog;paced_job[ctx]=id;
                paced_debug[0]=3;
                if(bench_load(ctx,slot))return -1;
                paced_debug[0]=4;
            }
          }
          for(uint32_t ctx=0;ctx<contexts;ctx++)if(bench_contexts[ctx].stage==1u)bench_retry(ctx);
        }
    }
    uint32_t elapsed=paced_us(start);if((rd(QKD,0x2cu)&15u)!=15u||dma_reset(DMA_CH))return -1;
    xil_printf("QKD_PACED_PASS seq=%u contexts=%u jobs=%u corrected=%u discarded=%u dropped=%u interval_us=%u policy=%u elapsed_us=%u\r\n",
        seq,contexts,jobs,corrected,discarded,dropped,interval,policy,elapsed);return 0;
}
