/* Host adapter only: execute the real secure policy and real stream C code.
 * IR/PA DMA is instrumented; this is not an RTL or PL hashing test. */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include "accumulator_generated.h"
#include "qkd_punct_tables.h"
#define MAX_WORDS 4096u
#define QKD 0u
#define DMA_CH 1u
#define DMA_SYN 2u
#define DMA_PA 3u
#define DMA_SEED 4u
#define RX 1u
#define HP_PA_SETUP 0u
#define HP_PA_START 0u
#define HP_PA_DRAIN 0u
#define HP_PA_CALL 0u
#define HP_STREAM_WIPE 0u
#define HP_STRIP_D 0u
#define HP_STREAM_APPEND 0u
#define HP_STREAM_DECIDE 0u
#define HP_SEED_COPY 0u
#define HP_EMIT_PREP 0u
#define HP_EMIT_FINALIZE 0u
typedef uintptr_t UINTPTR;
typedef int hp_mark_t;
static int hp_mark(void){return 0;}
static void hp_add(unsigned p,int q){(void)p;(void)q;}
static void Xil_DCacheFlushRange(UINTPTR p,unsigned n){(void)p;(void)n;}
static void Xil_DCacheInvalidateRange(UINTPTR p,unsigned n){(void)p;(void)n;}
static unsigned host_dma,host_writes;
static int host_fail;
static int dma_reset(unsigned d){(void)d;host_dma++;return 0;}
static int dma_start(unsigned d,unsigned r,const void *p,unsigned n){(void)d;(void)r;(void)p;(void)n;host_dma++;return host_fail?-1:0;}
static int dma_wait(unsigned d,unsigned r,unsigned n){(void)d;(void)r;(void)n;host_dma++;return host_fail?-1:0;}
static void wr(unsigned d,unsigned a,unsigned v){(void)d;(void)a;(void)v;host_writes++;}
static int qkd_wait(unsigned x,uint32_t *s){(void)x;*s=0;return 0;}
static uint32_t frame[MAX_WORDS],channel_data[192],syndrome_data[48],functional_x[87],functional_seed[120];
static uint64_t key_rx[48],pa_rx[16],expected_key[48];
static int functional_active,functional_key_valid;
static uint32_t functional_code,verification_used,verification_limit=18446;
static uint32_t frame_crc(const unsigned char *p,uint32_t n){
    uint32_t c=~0u;for(unsigned i=0;i<n;i++){c^=p[i];for(unsigned j=0;j<8;j++)c=(c>>1)^(0xedb88320u&(0u-(c&1u)));}return ~c;
}
static int verification_reserve(uint32_t seq){
    (void)seq;functional_key_valid=0;
    if(verification_used>=verification_limit){memset(key_rx,0,sizeof(key_rx));memset(functional_x,0,sizeof(functional_x));return 0;}
    verification_used++;return 1;
}
static int functional_pa(const uint32_t *seed,uint32_t verify){
    (void)seed;(void)verify;host_dma++;pa_rx[0]=123;return host_fail?-1:0;
}
#include "secure_key_stream.h"
static int functional_command(uint32_t n,uint32_t seq){
    unsigned op=frame[0];
    if(op>=60&&op<=69)return key_stream_command(n,seq);
    if(op==10){functional_active=1;functional_key_valid=0;functional_code=frame[1]&3;functional_revealed=frame[4];host_dma++;return 0;}
    if(op==11){functional_active=0;functional_key_valid=1;for(unsigned i=0;i<48;i++)key_rx[i]=0x76543210abcdef01ULL+i;host_dma++;return 0;}
    if(op==12){functional_revealed+=frame[1];host_writes++;return 0;}
    if(op==72){verification_limit=frame[1];return 0;}
    if(op==73){xil_printf("budget=%u",verification_used);return 0;}
    return 0;
}
