/* DDR replay benchmark: no UART traffic inside the timed scheduler loop.
 * Reuses four public golden blocks; these are NOT independent FER trials. */
typedef struct {
    smoke_vector_t v;
    uint32_t raw[2048] __attribute__((aligned(64)));
    uint32_t ch[192] __attribute__((aligned(64)));
    uint32_t syn[48] __attribute__((aligned(64)));
    uint64_t key[48] __attribute__((aligned(64)));
    int ready;
} bench_vector_t;
static bench_vector_t bench_vectors[4];
typedef struct {uint32_t stage,job,attempt,cursor;XTime due;} bench_context_t;
static bench_context_t bench_contexts[4];
static int bench_load(uint32_t ctx,uint32_t job)
{
    smoke_vector_t *v=&bench_vectors[job%4u].v;
    if (!(rd(QKD,0x2cu)&(1u<<ctx))) return -1;
    wr(QKD,0x28u,ctx);wr(QKD,0x08u,v->cfg);wr(QKD,0x20u,v->cfg2|0x10u);
    if (dma_start(DMA_CH,0,v->ch,768u)||dma_start(DMA_SYN,0,v->syn,v->syn_words*4u)||
        dma_wait(DMA_CH,0,768u)||dma_wait(DMA_SYN,0,v->syn_words*4u)) return -1;
    XTime start;XTime_GetTime(&start);
    while (((rd(QKD,0x84u+ctx*8u)>>28)&7u)!=1u) if (expired(start)) return -1;
    for (uint32_t k=0;k<v->pre;k++) wr(QKD,0x18u,v->reveal[k]|(ctx<<20));
    bench_contexts[ctx].stage=1u;bench_contexts[ctx].job=job;bench_contexts[ctx].attempt=0;
    bench_contexts[ctx].cursor=v->pre;bench_contexts[ctx].due=0;return 0;
}
static void bench_retry(uint32_t ctx)
{
    wr(QKD,0x2cu,(1u<<(16u+ctx))|(1u<<(24u+ctx)));
    wr(QKD,0x04u,1u|(ctx<<8));bench_contexts[ctx].stage=2u;
}
static int bench_check(uint32_t ctx,int converged)
{
    bench_context_t *c=&bench_contexts[ctx];smoke_vector_t *v=&bench_vectors[c->job%4u].v;
    if (c->attempt>=v->attempts) return -1;
    uint32_t e=v->expected[c->attempt],a=rd(QKD,0x80u+ctx*8u),b=rd(QKD,0x84u+ctx*8u);
    if ((e>>31)!=(uint32_t)converged||(a&0xfffu)!=(e&0xfffu)||((a>>12)&0xfffu)!=((e>>16)&0xfffu)||
        (a>>24)!=c->attempt+1u||((b>>24)&3u)!=((e>>28)&3u)) return -1;
    if (converged) {
        if (c->attempt+1u!=v->attempts||(b&0xfffu)!=v->errcnt) return -1;
        for (uint32_t k=0;k<48u;k++) if (key_rx[k]!=v->key[k]) return -1;
    }
    return 0;
}
static int latency_benchmark_command(uint32_t n,uint32_t seq)
{
    uint32_t op=frame[0];
    if (op==70u && n>=4u && frame[1]<4u && frame[2]==n-3u && frame[2]<=2048u) {
        uint32_t index=frame[1],count=frame[2];smoke_vector_t v;
        memmove(frame,frame+3,count*4u);
        memcpy(bench_vectors[index].raw,frame,count*4u);
        if (unpack_vector(count,&v)) return -1;
        bench_vector_t *b=&bench_vectors[index];b->v=v;
        memcpy(b->ch,v.ch,sizeof(b->ch));memcpy(b->syn,v.syn,v.syn_words*4u);memcpy(b->key,v.key,sizeof(b->key));
        b->v.expected=b->raw+(v.expected-frame);b->v.counts=b->raw+(v.counts-frame);b->v.reveal=b->raw+(v.reveal-frame);
        b->v.ch=b->ch;b->v.syn=b->syn;b->v.key=b->key;b->ready=1;
        xil_printf("QKD_BENCH_VECTOR seq=%u index=%u\r\n",seq,index);return 0;
    }
    if (op!=71u||n!=4u||frame[1]<1u||frame[1]>4u||frame[2]<frame[1]||frame[2]>128u||frame[3]>100000u) return -1;
    uint32_t contexts=frame[1],jobs=frame[2],rtt=frame[3];
    for (uint32_t i=0;i<4u;i++) if (!bench_vectors[i].ready) return -1;
    if (functional_active||(rd(QKD,0x2cu)&15u)!=15u||mc_mode) return -1;
    wr(QKD,0x1cu,0u);wr(QKD,0x2cu,0xffff0000u);
    if (dma_reset(DMA_CH)||dma_reset(DMA_SYN)) return -1;
    memset(bench_contexts,0,sizeof(bench_contexts));
    uint32_t next=0,done=0,corrected=0,discarded=0,total_attempts=0;
    uint64_t busy_cycles=0;XTime start,finish;XTime_GetTime(&start);
    if (dma_start(DMA_CH,RX,key_rx,sizeof(key_rx))) return -1;
    for (uint32_t ctx=0;ctx<contexts;ctx++) {if (bench_load(ctx,next++)) return -1;bench_retry(ctx);}
    while (done<jobs) {
        XTime now;XTime_GetTime(&now);
        if (now-start>(XTime)COUNTS_PER_SECOND*30u) return -1;
        uint32_t status=rd(DMA_CH,RX+4u);
        if (status&DMA_ERROR) return -1;
        if ((status&0x1002u)==0x1002u) {
            if (dma_wait(DMA_CH,RX,sizeof(key_rx))) return -1;
            uint32_t summary=rd(QKD,0x2cu);XTime began;XTime_GetTime(&began);
            while (!(summary&0xf0000u)) {if (expired(began)) return -1;summary=rd(QKD,0x2cu);}
            uint32_t bits=(summary>>16)&15u,owner=0;
            if (bits&(bits-1u)) return -1;
            while (!(bits&(1u<<owner))) owner++;
            if (owner>=contexts||bench_contexts[owner].stage!=2u) return -1;
            Xil_DCacheInvalidateRange((UINTPTR)key_rx,sizeof(key_rx));
            if (bench_check(owner,1)) return -1;
            total_attempts+=bench_contexts[owner].attempt+1u;busy_cycles+=rd(QKD,0xc0u+owner*4u);
            wr(QKD,0x2cu,1u<<(16u+owner));bench_contexts[owner].stage=0;done++;corrected++;
            if (dma_start(DMA_CH,RX,key_rx,sizeof(key_rx))) return -1;
            if (next<jobs) {if (bench_load(owner,next++)) return -1;bench_retry(owner);}
        }
        for (uint32_t ctx=0;ctx<contexts;ctx++) {
            bench_context_t *c=&bench_contexts[ctx];smoke_vector_t *v=&bench_vectors[c->job%4u].v;
            if (c->stage==2u && (rd(QKD,0x2cu)&(1u<<(24u+ctx)))) {
                if (bench_check(ctx,0)) return -1;
                uint32_t count=v->counts[c->attempt];
                if (c->attempt+1u==v->attempts) {
                    if (count) return -1;
                    total_attempts+=c->attempt+1u;busy_cycles+=rd(QKD,0xc0u+ctx*4u);
                    wr(QKD,0x04u,2u|(ctx<<8));wr(QKD,0x2cu,1u<<(24u+ctx));c->stage=0;done++;discarded++;
                    if (next<jobs) {if (bench_load(ctx,next++)) return -1;bench_retry(ctx);}
                } else {
                    XTime_GetTime(&now);c->due=now+(XTime)rtt*COUNTS_PER_SECOND/1000000u;c->stage=3u;
                }
            }
            if (c->stage==3u) {
                XTime_GetTime(&now);
                if (now>=c->due) {
                    uint32_t count=v->counts[c->attempt];
                    for (uint32_t k=0;k<count;k++) wr(QKD,0x18u,v->reveal[c->cursor++]|(ctx<<20));
                    c->attempt++;bench_retry(ctx);
                }
            }
        }
    }
    XTime_GetTime(&finish);
    if ((rd(QKD,0x2cu)&15u)!=15u||dma_reset(DMA_CH)) return -1;
    uint32_t us=(uint32_t)((finish-start)*1000000u/COUNTS_PER_SECOND);
    xil_printf("QKD_BENCH_PASS seq=%u contexts=%u jobs=%u corrected=%u discarded=%u attempts=%u rtt_us=%u elapsed_us=%u busy_cycles=%u\r\n",
               seq,contexts,jobs,corrected,discarded,total_attempts,rtt,us,(uint32_t)busy_cycles);
    return 0;
}
